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

### `ceph` commands hang with no monitor quorum

- **Where:** milestone 2, drill 3, with only `gluster1` up.
- **Symptom:** `ceph -s`, `ceph osd tree` and every other `ceph` command wait with no output; Ctrl-C prints `Cluster connection aborted`.
- **Cause:** the `ceph` command asks the monitors, and a monitor without a majority will not answer. This is the quorum rule working, not a fault.
- **What still works:** each daemon's admin socket, which talks to that one daemon and needs no quorum: `ceph --admin-daemon /var/run/ceph/<fsid>/ceph-mon.gluster1.asok mon_status` showed `"state": "probing"` and `"quorum": []`. Put `timeout` in front of `ceph` commands during such a test so a shell is not lost.
- **Fix:** bring back enough monitors for a majority, here one more.

### A writer log shows failures from a run that had none

- **Where:** milestone 2, drill 3.
- **Symptom:** `grep -c FAIL ~/drill3-writes.log` printed 15 after a run with no failures.
- **Cause:** the writer appends to its log, and `~/drill3-writes.log` on `gluster4` already held 68 lines from the Gluster lab's drill 3, in that writer's older format. Every failure counted was from those lines.
- **Fix:** start each drill with a log name that has not been used, or remove the old file first. The archived log has the old lines removed.

### A shell function is missing in a new shell

- **Where:** milestone 2, drills 1 and 4.
- **Symptom:** `bash: check_files: command not found`.
- **Cause:** a function defined at the prompt exists only in that shell; each `script` recording starts a new one.
- **Fix:** define it again in the new shell, or keep such helpers in a script file. The checks were re-run afterwards in their own recorded session.

### An OSD's disk cannot be zapped: `Device or resource busy`

- **Where:** milestone 3, drill 5, on `gluster3`.
- **Symptom:** `cephadm ceph-volume -- lvm zap --destroy --osd-id 3` fails with `error from zap: (16) Device or resource busy`; nothing is wiped.
- **Cause:** the OSD was still running. `ceph orch daemon stop osd.3` had replied `Scheduled to stop osd.3`, but five minutes later the container was still up and `dmsetup info -c` showed the volume open 24 times. Why the scheduled stop did not happen was not established.
- **Fix:** on the host, `systemctl stop ceph-<fsid>@osd.3.service`; check `systemctl is-active` says `inactive` and the volume's `Open` count is 0; then zap.

### A replacement OSD is rebuilt and removed over and over

- **Where:** milestone 3, drill 5.
- **Symptom:** `ceph orch osd rm status` shows the OSD at `done, waiting for purge` with `REPLACE True` and `ZAP True` indefinitely; no new OSD appears on the free disk; the cephadm log (`ceph log last 100 debug cephadm`) repeats `Zapping devices for osd.3`, `osd.3 now down`, `Daemon osd.3 ... was already removed`, `Successfully destroyed old osd.3 ... ready for replacement` every few seconds. `CEPHADM_STRAY_DAEMON` names the OSD.
- **Cause:** two things undoing each other. `ceph orch osd rm 3 --replace` queued the OSD with zapping on, although `--zap` was not given and the command itself said the volumes would not be zapped. A `--replace` entry ends at destroyed and is never purged, so it stays in the queue. With the OSD spec managed, the orchestrator kept preparing a new OSD on the freed disk with the destroyed ID, and the queue entry kept removing it and zapping the disk.
- **Fix:** `ceph orch osd rm stop <id>` to empty the queue. That also resets the OSD: it is no longer destroyed and is marked in, so mark it out again at once (`ceph osd out <id>`), then destroy it with `ceph osd safe-to-destroy <id>` and `ceph osd destroy <id> --yes-i-really-mean-it`. Remove any leftover daemon on the host with `cephadm rm-daemon --name osd.<id> --fsid <fsid> --force`, and zap the disk by path.
- **Prevention:** keep the OSD spec unmanaged until the queue is empty and the replacement is built, and check with `ceph orch ls osd` that it shows `<unmanaged>`.

### An OSD is prepared on a disk but never started

- **Where:** milestone 3, drill 5, after the loop above.
- **Symptom:** `ceph osd dump` shows the OSD `exists,new` with a new UUID, `lsblk` shows a fresh `ceph-…` volume on the disk and `cephadm ceph-volume -- lvm list` lists it, but no daemon for it runs on the host and `ceph orch ps` shows an old record in `error`.
- **Cause:** creating an OSD under cephadm is two steps: `ceph-volume lvm batch` prepares it, then cephadm deploys a container for it. The second step did not happen; the likely reason is the orchestrator's stale record of the earlier OSD with the same ID. Not established.
- **Fix:** `ceph cephadm osd activate <host>`, which deploys a daemon for every OSD prepared on that host and not running. It replied `Created osd(s) 3 on host 'gluster3'`, and the OSD booted within a minute.

### A recording copied with a wildcard misses a file

- **Where:** milestone 3, drill 6a.
- **Symptom:** `ceph-drill6a-cephw-gluster1.txt` was not among the files copied with `scp 'root@gluster1:/root/ceph-drill*-cephw.txt'`.
- **Cause:** the file's name ends `-cephw-gluster1.txt`, which the pattern `*-cephw.txt` does not match.
- **Fix:** copy it by name, and check the copied set against the list of files the runbook made.

### A mount fails with `no mds is up` while the cluster is healthy

- **Where:** milestone 4a, drill 8, gluster4.
- **Symptom:** `mount error: no mds (Metadata Server) is up. The cluster might be laggy, or you may not be authorized`, exit 32, with `ceph -s` showing `HEALTH_OK` and an active MDS.
- **Cause:** the client could not log in or could not agree a connection mode, and the kernel reports any such failure this way. In drill 8 it came from a forged key, an unknown client name, a deleted key, and a client asking for `ms_mode=crc` after the cluster was set to accept only `secure`.
- **Fix:** read the kernel log first: `dmesg -T | grep -iE 'ceph|libceph' | tail`. `auth protocol 'cephx' msgr authentication failed: -13` means a wrong, unknown or deleted key: check the name, the keyring and `ceph auth get client.<name>`. For a mode mismatch, compare the mount's `ms_mode` with `ceph config dump | grep ms_`.

### A key is deleted but its mount keeps working

- **Where:** milestone 4a, drill 8.
- **Symptom:** after `ceph auth rm client.reader`, new mounts with the key fail, but `ls` on the existing mount still lists the directory.
- **Cause:** deleting a key stops new logins. A mounted client keeps its ticket and its MDS session.
- **Fix:** evict every session the key holds: `ceph tell mds.cephfs:0 client ls`, find each `id` whose `entity_id` is the key's name, and `ceph tell mds.cephfs:0 client evict id=<id>` for each. Eviction also blocklists the client, so the OSDs refuse it too. Then unmount it on the client with `umount -l`, repeated until `mountpoint` reports nothing, in case it was mounted more than once.

### MDS failover stalls clients for about 45 seconds

- **Where:** milestone 4a, drill 8, restarting the active MDS.
- **Symptom:** a client write held for 51 s. The cluster log shows the standby assigned rank 0 at once, then `evicting unresponsive client ... after waiting 47.3695 seconds during MDS startup`, then the MDS active.
- **Cause:** a new MDS waits in its reconnect state for every client that had a session with the old one. One session belonged to a client whose key had been deleted; it could not log in again, so the MDS waited for its reconnect timeout before evicting it. Every other client waited too.
- **Fix:** evict a revoked key's sessions when the key is deleted (see above), and before restarting an MDS check `client ls` for sessions of names that `ceph auth ls` no longer lists.

### The active manager cannot be restarted

- **Where:** milestone 4a, drill 8.
- **Symptom:** `ceph orch daemon restart mgr.gluster1.bxuyky` fails with `Error EINVAL: Unable to restart daemon mgr.gluster1.bxuyky: ALERT: Cannot stop active Mgr daemon, Please switch active Mgrs with 'ceph mgr fail gluster1.bxuyky'`.
- **Cause:** the orchestrator runs inside the active manager, so restarting that daemon is treated as a warning that needs `--force`. The `--force` given in the drill was passed to the restart helper, which used only its first argument, so the command never saw it.
- **Fix:** `ceph mgr fail gluster1.bxuyky`. The standby becomes active and the old active restarts as a standby.

### The Dashboard has no links to Grafana, Alertmanager or Prometheus

- **Where:** milestone 4b, drill 9, gluster1.
- **Symptom:** `ceph dashboard get-grafana-api-url`, `get-alertmanager-api-host` and `get-prometheus-api-host` print nothing; the Dashboard has no Grafana panels and no alerts.
- **Cause:** cephadm sets these when it deploys or reconfigures Grafana, Alertmanager and Prometheus. The dashboard module was enabled after those three had been deployed, so nothing set them.
- **Fix:** `ceph orch reconfig grafana`, `ceph orch reconfig alertmanager`, `ceph orch reconfig prometheus`, then check the three `get-` commands again. For the browser, `ceph dashboard set-grafana-frontend-api-url https://<monitoring host address>:3000` if the client machine cannot resolve the host name. Enabling the dashboard module before deploying the monitoring stack avoids it.

### The Dashboard cannot be reached on 8443

- **Where:** milestone 4b, drill 9, the manager hosts.
- **Symptom:** `ceph mgr services` lists the Dashboard, but the browser times out.
- **Cause:** cephadm opens the firewall ports of the daemons it deploys (9100, 9283, 9926, 8765 and the monitoring stack's), but the Dashboard is a module inside the manager, not a daemon cephadm deploys.
- **Fix:** on every manager host, `firewall-cmd --permanent --add-port=8443/tcp` and `firewall-cmd --reload`. Both hosts need it: the Dashboard follows the active manager.

### `CephadmDaemonFailed` stays up after the daemon is running again

- **Where:** milestone 4b, drill 9, after the Ceph target on gluster3 was started again.
- **Symptom:** `HEALTH_WARN 1 failed cephadm daemon(s)`, `node-exporter.gluster3 ... is in error state`, and the alert firing, eight minutes after every daemon on the host was back. `ceph orch ps` shows the host's daemons `stopped`, `REFRESHED 15m ago`.
- **Cause:** `ceph orch ps` and the health check read cephadm's cache of each host's daemons, which is refreshed every ten minutes or so. Stopping the host's Ceph target had also left node-exporter's unit failed, not stopped, which cephadm reports as `error`.
- **Fix:** `ceph orch ps <host> --refresh`, wait half a minute, then `ceph orch ps <host>`. If a daemon really is in error, `ceph orch daemon restart <name>`.

### False failures after the Mac sleeps

- **Where:** milestone 4b, drill 9 (twice) and milestone 1.
- **Symptom:** after the Mac sleeps, running OSDs are marked down `after no beacon for 2140 seconds`; the active MDS and manager are replaced; `slow ops` pile up on one monitor; `message from mon.1 was stamped 2406s in the future`; `MON_CLOCK_SKEW`; OSDs that were down are marked out at once.
- **Cause:** UTM pauses the VMs while the Mac sleeps. When they resume, each guest's clock is behind until chrony steps it, and they are stepped at different moments. Each daemon then judges the others by a clock that has jumped half an hour, and the pause looks like silence.
- **Fix:** keep the Mac awake for the whole session (`caffeinate -dims`, on mains power, lid open). After a pause, wait for `ceph -s` to settle: the daemons rejoin by themselves, and the cluster was `HEALTH_OK` again within a few minutes each time. Check `ceph time-sync-status` before starting a drill.

## Diagnostic commands

```bash
ceph -s                                   # overall state
ceph -w                                   # the cluster log, live, with timestamps: what the monitors decided and when
ceph health detail                        # the reason behind any HEALTH_WARN
ceph time-sync-status                     # each monitor's clock offset from the leader
ceph orch ps                              # every daemon, its host, state, memory use and limit
ceph orch device ls --wide                # disks cephadm can see, and why one is rejected
ceph log last 100 debug cephadm           # what the orchestrator did and what failed
cephadm shell -- ceph -s                  # the cluster's own client, when the host's is broken
cephadm ceph-volume lvm list              # on a host: OSDs ceph-volume has created there
tail -40 /var/log/ceph/<fsid>/ceph-volume.log   # on a host: the last commands ceph-volume ran
ps -eo pid,ppid,etime,stat,wchan:25,args  # what a stuck process is, how long it has run, what it waits on
ceph --admin-daemon /var/run/ceph/<fsid>/ceph-mon.<host>.asok mon_status   # one monitor's own view, no quorum needed
ceph pg dump_stuck inactive               # PGs not accepting I/O, and why
rados list-inconsistent-pg <pool>         # after a scrub: PGs whose copies disagree
ceph orch osd rm status                   # OSDs being drained, replaced or removed, and their state
ceph osd safe-to-destroy <id>             # whether an OSD's loss would leave any PG short of copies
ceph auth get client.<name>               # a key's capabilities
ceph tell mds.cephfs:0 client ls          # the MDS's client sessions: id, name, address, root
ceph config dump | grep ms_               # the msgr2 mode settings in force
dmesg -T | grep -iE 'ceph|libceph'        # on a client: why a mount or a session failed
ceph mgr services                         # the URLs of the Dashboard and the manager's exporter
ceph orch ps <host> --refresh             # refresh cephadm's view of a host's daemons
curl -s <prometheus host>:9095/api/v1/alerts    # the alerts Prometheus has pending or firing
ceph osd df tree                          # data and PGs per OSD and per host
cephadm ceph-volume -- lvm list           # on a host: the OSDs prepared on its disks, with IDs and UUIDs
dmsetup info -c                           # on a host: device-mapper volumes and how many processes hold each open
dmesg -T | grep -E 'ceph|libceph'         # on the client: the kernel client's view of monitors, MDS and OSDs
chronyc tracking                          # this machine's offset from its time source
```
