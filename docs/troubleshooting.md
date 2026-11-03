# Troubleshooting

Issues that were actually hit during this lab, followed by the diagnostic commands used. Causes marked "not established" were not confirmed.

## Issues encountered

### `cephadm` fails with `No module named 'jinja2'`

- **Where:** milestone 1, every server, the first `cephadm` command after installing it.
- **Symptom:** a Python traceback ending in `cephadmlib/templating.py ... ModuleNotFoundError: No module named 'jinja2'`.
- **Cause:** the Storage SIG's `cephadm` 20.2.4 RPM does not require `python3-jinja2`. The upstream single-file build carries its own copy; the distribution build expects the system package.
- **Fix:** `dnf -y install python3-jinja2 python3-pyyaml`. PyYAML is needed for service specs.

### `ceph pull` fails with `conf_read_file`

- **Where:** milestone 1, gluster1, before the bootstrap.
- **Symptom:** `Error initializing cluster client: ObjectNotFound('RADOS object not found (error calling conf_read_file)')`.
- **Cause:** a typing slip: `ceph` is the cluster client, which reads `/etc/ceph/ceph.conf` first, and there was no cluster yet. Pulling the image is `cephadm pull`.

### Bootstrap fails with `OSError: [Errno 22] Invalid argument`

- **Where:** milestone 1, gluster1, the first bootstrap.
- **Symptom:** `Verifying IP fe80::... port 3300 ...` followed by `OSError: [Errno 22] Invalid argument`. cephadm then deletes the half-made cluster.
- **Cause:** `MON_IP=$(getent hosts gluster1 | ...)` returned the IPv6 link-local address. `getent hosts` asks for IPv6 first; `/etc/hosts` has no IPv6 entry, so the answer for the machine's own name came from systemd's `myhostname` NSS module. A link-local address cannot be bound without an interface name, hence `EINVAL`.
- **Fix:** `MON_IP=$(getent ahostsv4 gluster1 | awk 'NR==1 {print $1}')`, which asks for IPv4 only. Check the value with `echo "$MON_IP"` before bootstrapping.

### `ceph -s` on the host: `error parsing file ... Malformed input`

- **Where:** milestone 1, gluster1, right after the bootstrap.
- **Symptom:** `auth: error parsing file /etc/ceph/ceph.client.admin.keyring: error setting modifier for [client.admin] type=key val=...: Malformed input`, then `RADOS I/O error (error connecting to the cluster)`.
- **Cause:** the host's `ceph` command was the Pacific 16.2.15 client, left from an earlier install. The Tentacle monitors created a type 2 (AES-256) cephx key, which Pacific cannot parse. `dnf install ceph-common` had reported the old package as already installed and not upgraded it.
- **Check:** `ceph -v` on the host against `cephadm shell -- ceph -v`; `dnf list installed ceph-common librados2`. `cephadm shell -- ceph -s` works meanwhile, because it runs the cluster's own image.
- **Fix:** remove the old repository (`dnf remove centos-release-ceph-pacific`), enable CRB and EPEL (next issue), then `dnf upgrade ceph-common`.
- **Note:** the error message prints the admin key. Paste such output with the value cut out: `ceph -s 2>&1 | sed 's/val=[^:]*/val=<redacted>/'`.

### `dnf remove centos-ceph-pacific`: no match

- **Where:** milestone 1, all four VMs.
- **Cause:** `centos-ceph-pacific` is the repository's name. The package that installs the repository file is `centos-release-ceph-pacific`. `dnf repolist` shows repository names; `rpm -qf /etc/yum.repos.d/<file>` shows which package owns a repository file.

### `ceph-common` 20.2 cannot be installed: `nothing provides libarrow.so.900`

- **Where:** milestone 1, every VM that needs the client.
- **Symptom:** `nothing provides libarrow.so.900()(64bit)`, `libparquet.so.900`, `libblake3.so.0` and `libthrift-0.15.0.so`.
- **Cause:** Tentacle's client libraries link against Apache Arrow and Parquet, BLAKE3 and Apache Thrift, which come from EPEL, not from CentOS Stream or the Storage SIG.
- **Fix:** `dnf config-manager --set-enabled crb` and `dnf -y install epel-release`. Confirm with `dnf repoquery --whatprovides 'libarrow.so.900()(64bit)'` before upgrading.

### OSDs created on two hosts but not the third

- **Where:** milestone 1, gluster2.
- **Symptom:** `ceph osd stat` shows 4 OSDs; `gluster2` has none in `ceph osd tree`, and its disks are bare in `lsblk`. `cephadm ceph-volume lvm list` on gluster2 waits indefinitely.
- **Evidence:** `ps` shows two `ceph-volume lvm batch` containers, one of them with no `cephadm` parent, and a `ceph ... osd new <uuid>` child of each, sleeping in `futex_do_wait`. `ceph-volume.log` ends each attempt at `osd new`. `ceph health detail` shows `MON_CLOCK_SKEW` for gluster2 (15.3 s) and gluster3 (5.7 s).
- **Cause:** gluster2's clock; the mechanism is not established. `osd new` asks the monitors to register the OSD, and the client retries without a timeout of its own, so each attempt waited until cephadm's 895-second limit ended its call. That limit ends the `cephadm` call but not the container it started, which is why one container had no parent. The waiting `lvm list` was blocked on cephadm's per-cluster lock in `/run/cephadm/`, held by the current attempt.
- **Fix:** stop the stuck containers (`podman stop`), which is safe while the disks are still bare; correct the clocks (next issue). The orchestrator retried by itself and created both OSDs within minutes. Timeline in [deploy.md](deploy.md#findings).

### `MON_CLOCK_SKEW` and VM clocks minutes behind

- **Where:** milestone 1, after the Mac had slept with the VMs paused.
- **Symptom:** `clock skew detected on mon.gluster2, mon.gluster3`; `ceph time-sync-status` shows skews of seconds against a limit of 0.05 s. The VMs' clocks were also about 15 minutes behind real time.
- **Cause:** a paused VM's clock stops. CentOS's default chrony configuration, `makestep 1.0 3`, steps the clock only in its first three updates after starting; after that it slews, which takes hours to close a gap of minutes.
- **Fix:** on every VM, one `server` line for the same time source and `makestep 1.0 -1`, which steps the clock whenever it is more than a second out; then `systemctl restart chronyd` and `chronyc makestep`. The monitors re-check about every 30 seconds after a skew warning. Use one source everywhere: Google's servers smear leap seconds, so they must not be mixed with servers that do not.
- **Prevention:** keep the Mac awake during a session with `caffeinate -dis`.

### Session recordings cut short

- **Where:** milestone 1, all four VMs.
- **Symptom:** each recording ends partway through output, with no `Script done` line, and its size is an exact multiple of 4 KiB.
- **Cause:** most likely, `script` buffers what it records and writes it out in blocks; the SSH sessions were dropped while the Mac slept, `script` was killed with them, and the buffer was lost. Later commands were typed in new, unrecorded terminals.
- **Fix:** keep the Mac awake (`caffeinate -dis`), and check that a recording ends with `Script done` before relying on it.

## Diagnostic commands

```bash
ceph -s                                   # overall state
ceph health detail                        # the reason behind any HEALTH_WARN
ceph time-sync-status                     # each monitor's clock offset from the leader
ceph orch ps                              # every daemon, its host, state, memory use and limit
ceph orch device ls --wide                # disks cephadm can see, and why one is rejected
ceph log last 100 debug cephadm           # what the orchestrator did and what failed
cephadm shell -- ceph -s                  # the cluster's own client, when the host's is broken
cephadm ceph-volume lvm list              # on a host: OSDs ceph-volume has created there
tail -40 /var/log/ceph/<fsid>/ceph-volume.log   # on a host: the last commands ceph-volume ran
ps -eo pid,ppid,etime,stat,wchan:25,args  # what a stuck process is, how long it has run, what it waits on
chronyc tracking                          # this machine's offset from its time source
```
