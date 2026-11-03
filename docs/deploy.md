# Deploying Ceph and CephFS

Milestone 1. A three-node Ceph cluster was deployed with `cephadm` on the VMs and disks wiped at the end of the Gluster lab, a CephFS file system was created on it and mounted on `gluster4`, and one file's data was traced to the disks holding it. See [milestones.md](milestones.md).

Run on 2026-11-02 and 2026-11-03. The details below come from the session recordings in [evidence/](evidence) and screenshots 01 and 02. The recordings `deploy-session-*.txt` cover the server preparation, the bootstrap and the package problems; `verify-session-*.txt` record the finished cluster, one command per acceptance criterion.

## The cluster

| Host | Ceph daemons | Disks |
|---|---|---|
| `gluster1` | monitor (leader), manager (active), MDS (active), `osd.1`, `osd.2`, crash collector | `vdb`, `vdc` |
| `gluster2` | monitor, manager (standby), MDS (standby), `osd.4`, `osd.5`, crash collector | `vdb`, `vdc` |
| `gluster3` | monitor, `osd.0`, `osd.3`, crash collector | `vdb`, `vdc` |
| `gluster4` | none: kernel CephFS client, mounted at `/mnt/cephfs` | |

| Item | Value |
|---|---|
| Release | Ceph 20.2 "Tentacle" |
| Daemons | Container image `quay.io/ceph/ceph:v20`, Ceph **20.2.5**, run by Podman |
| Host packages | `cephadm` and `ceph-common` **20.2.4**, from the CentOS Storage SIG (`centos-ceph-tentacle`) |
| Raw capacity | Six 10 GB disks, 60 GiB |
| File system | `cephfs`: pools `cephfs.cephfs.meta` and `cephfs.cephfs.data`, both `replicated size 3 min_size 2` |
| Client identity | `client.gluster4`, limited to `cephfs` |

The daemons and the host tools differ by a point release because they come from different places. `cephadm` deploys whatever image the `v20` tag pointed to when it pulled it, while the RPMs are built and published separately by the Storage SIG.

## How Ceph is put together

Ceph covers the same ground as the Gluster volume in phase 1, three copies of every piece of data on three servers, with a different design.

| Gluster (phase 1) | Ceph (this lab) | Role |
|---|---|---|
| `glusterd` on every server | Monitors | Hold the cluster state and agree on it by majority |
| Brick: a directory on XFS | OSD: a daemon that owns a whole disk | Stores the data |
| Replica 3 volume | Pool with `size 3` | Three copies |
| DHT hash of the file name | Placement groups and CRUSH | Decide where data goes |
| Client-side replication (AFR) | The primary OSD copies to the others | Writes reach every copy |
| Self-heal daemon | Recovery and backfill by the OSDs | Copy data back after a failure |
| The directory tree on the bricks | MDS (metadata server) | Names, directories, permissions |
| `auth.allow`, TLS certificates | cephx keys and capabilities | Who may connect and what they may do |

**RADOS and pools.** Everything is stored as objects in RADOS, Ceph's object store. Each object belongs to a pool, and the pool sets the protection: here three copies (`size 3`), with writes accepted while two are available (`min_size 2`), the same rule as Gluster's client quorum on replica 3.

**Monitors.** The three monitors keep the cluster map: which OSDs exist and are up, the pools, where each placement group lives, and the cephx keys. They agree on every change with Paxos, which needs a majority, so any two of the three can carry on. The leader also grants the others time-limited leases to answer reads, which is why monitors tolerate only 0.05 s of clock difference.

**OSDs and BlueStore.** Each OSD owns one disk and stores objects on it with BlueStore, directly on the device, with no partition table or filesystem. `ceph-volume` puts one LVM logical volume on each disk for BlueStore to use. Each OSD keeps a RocksDB database and a write-ahead log on its disk, which is why the cluster shows about 190 MiB raw used before holding any data.

**Placement groups and CRUSH.** A client hashes an object's name to one of its pool's placement groups, then runs CRUSH on the cluster map to get that group's ordered list of three OSDs. The default rule puts each copy under a different host, so no two copies share a server. The first OSD in the list is the primary: the client writes to it, and it forwards the write to the other two before acknowledging. Every client and daemon computes placement itself, from the same map, without asking a central server.

**CephFS and the MDS.** A file's contents are split into 4 MiB objects named `<inode in hex>.<chunk>` in the data pool. Names, directories and attributes live in the metadata pool and are served by the active MDS, which caches them. The client reads and writes file data directly to the OSDs; the MDS is not in the data path. A standby MDS waits to take over.

**cephx.** Every daemon and client has a key, and each key carries capabilities. `client.gluster4` may read the maps for `cephfs`, use that file system's metadata, and read and write only the data pools tagged for it.

**cephadm.** `cephadm` runs every daemon as a Podman container under a systemd unit, and the active manager's orchestrator reaches the other hosts over SSH to make the cluster match what was asked for: `ceph orch apply` states how many daemons of a kind to run and where, and the orchestrator deploys, moves or retries until it is true.

## Procedure

This is the procedure as it works on these VMs, with the fixes found during the run included. Each fix is explained under [Findings](#findings).

### 1. Prepare the servers (gluster1, gluster2, gluster3)

Check for Ceph packages and repositories left from earlier, and remove an older release's repository:

```bash
rpm -qa 'ceph*' 'cephadm*' 'centos-release-ceph*'
dnf remove centos-release-ceph-pacific      # only if it is listed
```

Install the tools and the repositories Tentacle needs:

```bash
dnf -y install podman lvm2 chrony python3 python3-jinja2 python3-pyyaml
dnf config-manager --set-enabled crb
dnf -y install epel-release centos-release-ceph-tentacle
dnf -y install cephadm
cephadm version
```

Set chrony to step the clock whenever it is more than a second out, and use one time source everywhere. In `/etc/chrony.conf`, the only `server` or `pool` line and the `makestep` line are:

```text
server time.google.com iburst
makestep 1.0 -1
```

```bash
systemctl restart chronyd
chronyc makestep
chronyc tracking | grep -E 'System time|Leap status'
cephadm check-host --expect-hostname $(hostname -s)
lsblk -f /dev/vdb /dev/vdc
```

On `gluster1` only, pull the image before the bootstrap:

```bash
cephadm pull
```

### 2. Bootstrap (gluster1)

```bash
MON_IP=$(getent ahostsv4 gluster1 | awk 'NR==1 {print $1}')
cephadm bootstrap --mon-ip "$MON_IP" --skip-dashboard --skip-monitoring-stack
dnf -y install ceph-common
ceph -v
ceph -s
```

`ceph -v` must report 20.2. If it reports an older release, an older `ceph-common` was already installed and `dnf install` left it; `dnf -y upgrade ceph-common` replaces it.

Memory limits, before any OSD or MDS exists. The VMs have 7.4 GiB and each server runs two OSDs, so the defaults (about 4 GiB per OSD, 4 GiB for the MDS cache) are lowered:

```bash
ceph config set osd osd_memory_target_autotune false
ceph config set osd osd_memory_target 1610612736       # 1.5 GiB
ceph config set mds mds_cache_memory_limit 1073741824  # 1 GiB
```

### 3. Add the hosts and place the monitors and managers (gluster1)

The bootstrap's SSH public key, `/etc/ceph/ceph.pub`, goes to `root` on `gluster2` and `gluster3` through the Mac (`ssh-copy-id -f -i`), since the VMs cannot log in to each other as root. Then:

```bash
for h in gluster2 gluster3; do ceph orch host add $h $(getent ahostsv4 $h | awk 'NR==1 {print $1}'); done
ceph orch apply mon --placement="gluster1,gluster2,gluster3"
ceph orch apply mgr --placement="gluster1,gluster2"
```

### 4. OSDs (gluster1)

The OSDs are described in a service spec, [../ceph/osd-spec.yml](../ceph/osd-spec.yml): both data disks on every host matching `gluster[1-3]`.

```bash
ceph orch device ls
ceph orch apply -i osd-spec.yml
ceph osd tree
```

### 5. CephFS and the client key (gluster1)

```bash
ceph fs volume create cephfs --placement="gluster1,gluster2"
ceph fs authorize cephfs client.gluster4 / rw > /root/ceph.client.gluster4.keyring
ceph config generate-minimal-conf > /root/ceph-client.conf
```

### 6. Mount on gluster4

`gluster4` gets the same CRB, EPEL and Tentacle repositories and `ceph-common` 20.2, the minimal configuration as `/etc/ceph/ceph.conf`, and the client keyring as `/etc/ceph/ceph.client.gluster4.keyring` (mode 600), both copied from `gluster1` through the Mac with `scp -3`. The keyring is never copied anywhere else.

```bash
mkdir -p /mnt/cephfs
echo 'gluster4@.cephfs=/  /mnt/cephfs  ceph  noatime,_netdev  0 0' >> /etc/fstab
mount /mnt/cephfs
```

## Results

### Health

| Check | Result |
|---|---|
| Cluster | `HEALTH_OK`; 3 monitors in quorum, leader `gluster1`; 1 active and 1 standby manager; 1 active and 1 standby MDS; 6 OSDs up and in; 145 of 145 PGs `active+clean` (screenshot 01, [verify-session-gluster1.txt](evidence/verify-session-gluster1.txt)) |
| OSD layout | Two OSDs under each host in the CRUSH tree, each weighted 0.0098 (10 GB) |
| Pools | `cephfs.cephfs.meta` and `cephfs.cephfs.data`: `replicated size 3 min_size 2` |
| Memory limits | `osd_memory_target` 1536 MiB, autotune off, `mds_cache_memory_limit` 1 GiB. In use: 72 to 104 MB per OSD, 98 to 128 MB per monitor, 234 and 304 MB per manager, 39 and 59 MB per MDS |
| Clocks | Monitor skews of −5.6 ms and −9.4 ms from the leader, against the 50 ms limit; every VM synchronised to Google's NTP servers |
| Restart | All VMs restarted about 82 minutes before the verification session. Every daemon came back by itself, the cluster returned to `HEALTH_OK`, and the client's mount came back from `/etc/fstab` |

### Where a file's data lives

The client wrote `hello.txt`, a 10 MiB file `test10M.bin` of random data, and 20 empty files. `test10M.bin` has inode `0x10000000001`, and its data is three objects in the data pool (screenshot 02):

| Object | Placement group | Acting set | Hosts |
|---|---|---|---|
| `10000000001.00000000` | 3.47 | [3, 5, 2], primary 3 | gluster3, gluster2, gluster1 |
| `10000000001.00000001` | 3.2f | [5, 0, 2], primary 5 | gluster2, gluster3, gluster1 |

The two chunks land in different placement groups with different primaries, and each has one copy on each server, as the CRUSH rule requires.

`ceph df` agrees: the data pool stores 10 MiB in 4 objects (three chunks of `test10M.bin` and one for `hello.txt`) and uses 30 MiB, three copies. The 20 empty files have no data objects at all; they exist only as metadata, in the 22 objects of the metadata pool. `MAX AVAIL` is 19 GiB per pool and the client sees a 19 GiB file system: 60 GiB raw divided by three copies, less the 5% Ceph holds back before it calls the cluster full.

### Placement groups

Screenshot 01 was taken before any data was written and shows 3 pools with 3 PGs in all. By the verification session there were 145: 1 for `.mgr`, 16 for the metadata pool, 128 for the data pool. The PG autoscaler made the change by itself. `ceph fs volume create` marks the data pool `bulk`, meaning it is expected to hold most of the cluster's data, so the autoscaler gives it its full share of PGs up front rather than growing it as data arrives. The metadata pool has a floor of 16 (`pg_num_min`) and a higher bias, because metadata operations are small and frequent.

### The client

| Check | Result |
|---|---|
| Key capabilities | `mon 'allow r fsname=cephfs'`, `mds 'allow rw fsname=cephfs'`, `osd 'allow rw tag cephfs data=cephfs'` |
| Mount | Kernel 5.14.0-759, client 20.2.4; `gluster4@<fsid>.cephfs=/` on `/mnt/cephfs`, type `ceph`, 19G |
| Persistence | Unmounted and mounted again from the fstab line `gluster4@.cephfs=/  /mnt/cephfs  ceph  noatime,_netdev  0 0` |
| Data | 22 entries; `hello ceph`; `test10M.bin` SHA-256 `04e8ee196308cfebb07475bfc9c2d73fc37b214f7de8b15035f5c514ad486aa6`, kept for later milestones to compare against after failures |
| Wire protocol | The mount negotiated `ms_mode=prefer-crc`: traffic is checksummed, not encrypted. Milestone 4 changes this |

## Findings

**Pacific was already on every VM.** `cephadm` 16.2.14 and `ceph-common` 16.2.15, the Pacific release, had been installed on 2026-10-25 (`dnf history` transaction 8), with the `centos-release-ceph-pacific` repository. The Tentacle `cephadm` replaced the old one as an upgrade, but `dnf install ceph-common` reports a package that is already installed and stops, so the host kept a Pacific client.

**The Storage SIG's `cephadm` is missing a dependency.** `cephadm` is a Python program packed into a single file. The upstream build carries its own copies of the libraries it uses; the distribution build relies on RPM dependencies, and the Tentacle package does not require `python3-jinja2`. Every command failed with `No module named 'jinja2'` until it was installed. cephadm uses Jinja2 to generate each daemon's systemd unit and container command line.

**`getent hosts` gave the bootstrap an IPv6 link-local address.** The first bootstrap failed with `OSError: [Errno 22] Invalid argument` while checking port 3300 on `fe80::...`. `getent hosts` asks for an IPv6 address first. `/etc/hosts` has only IPv4 entries, so the IPv6 answer for the machine's own name came from systemd's `myhostname` module: the interface's link-local address, which cannot be used without naming the interface. `getent ahostsv4` asks for IPv4 only. For the other hosts the same command had worked, because `myhostname` answers only for the local name.

**A new key type that the old client could not read.** The bootstrap wrote the admin key as cephx key type 2, an AES-256 key with a 32-byte secret, where older keys are type 1 (AES-128, 16 bytes). The base64 of a type 2 key starts `Ag`, a type 1 key `AQ`. The Pacific client rejected the keyring as `Malformed input`, while `cephadm shell -- ceph -s`, which runs the cluster's own image, showed the cluster healthy.

**Tentacle's client needs EPEL.** Upgrading `ceph-common` failed on `libarrow.so.900`, `libparquet.so.900`, `libblake3.so.0` and `libthrift-0.15.0.so`, which neither CentOS Stream nor the Storage SIG ships. They come from EPEL, and some EPEL packages depend on CodeReady Builder (CRB), which CentOS Stream ships disabled. None of the four is used by CephFS; the client packages are built with every feature, including the object gateway's S3 Select and tracing.

**Clock skew stopped gluster2's OSDs.** gluster1 and gluster3 got their OSDs from the spec at once; gluster2 got none for over half an hour. `ceph-volume`'s log on gluster2 ([verify-session-gluster2.txt](evidence/verify-session-gluster2.txt)) shows each attempt passing its disk checks, generating keys, and then sending `osd new`, the request that asks the monitors to register a new OSD, and getting no answer:

| gluster2's clock | Event |
|---|---|
| 00:31:51 | Attempt 1 sends `osd new`; no reply |
| 00:46:54 | Attempt 2 sends `osd new`; no reply. Attempt 1's container is still running: cephadm's 895-second limit ended the call that started it, but not the container |
| 01:01:56 | Attempt 3 sends `osd new` |
| 01:05:10 | Attempt 3's `osd new` returns. Volume groups on `vdb` and `vdc`, then `ceph-osd --mkfs` for `osd.5` and `osd.4`, within 7 seconds |

The Ceph command-line client has no timeout of its own, so each attempt waited until cephadm gave up on it. While they waited, `ceph health detail` showed `MON_CLOCK_SKEW`: gluster2 was 15.3 s ahead of the leader and gluster3 5.7 s behind. The VMs' clocks were also about 15 minutes behind real time: `ps` run at about 01:13 showed attempt 1's container, started at 00:31:51 by gluster2's clock, running for 26 minutes. The Mac had slept with the VMs paused, and chrony's default `makestep 1.0 3` corrects a large error by stepping only in its first three updates after starting; after that it slews, at a rate that takes hours to close a gap of minutes. With `makestep 1.0 -1` and one time source on every VM, chrony stepped the clocks, and attempt 3's `osd new` returned within minutes, at about 01:20 real time.

The clock was the one fault found on gluster2, and the first attempt after it was corrected succeeded. The log does not show why the monitors never answered, and the journal that would have recorded the monitors' side and chrony's step was lost when the VMs restarted, so the mechanism is not established. The stuck requests left nothing behind: the OSD IDs run 0 to 5 with no gaps or stray entries.

**Three disks share one serial number.** `ceph orch device ls` shows `/dev/vdb` with the device ID `F6766C50FDA84EEE829F` on all three servers, while each `/dev/vdc` has its own. The `vdb` disks were copied with the VM when `gluster2` and `gluster3` were cloned from `gluster1`; the `vdc` disks were added to each VM separately. Placement is not affected, but Ceph's device health tracking (`ceph device ls`) identifies a physical disk by this ID, so it will treat the three as one device.

The commands, symptoms and fixes for each of these are in [troubleshooting.md](troubleshooting.md).

## Verification

| Criterion | Result |
|---|---|
| `HEALTH_OK`, three monitors in quorum, six OSDs up and in, all PGs `active+clean` | Met (screenshot 01, verify session on gluster1) |
| CephFS with one active and one standby MDS; both pools `size 3 min_size 2` | Met |
| Client mounts with a key limited to `cephfs`, and the mount survives a remount from `/etc/fstab` | Met (verify session on gluster4) |
| A client file's objects traced to three OSDs on three different hosts | Met (screenshot 02) |
| Session recordings archived | Met: [evidence/](evidence), the admin key from the deploy session replaced by `<redacted>` and private addresses masked |

## Evidence

| File | Contents |
|---|---|
| [deploy-session-gluster1.txt](evidence/deploy-session-gluster1.txt) | Server preparation, the failed and the successful bootstrap, the Pacific client errors, the Pacific repository removed, CRB and EPEL enabled |
| [deploy-session-gluster2.txt](evidence/deploy-session-gluster2.txt), [deploy-session-gluster3.txt](evidence/deploy-session-gluster3.txt) | Server preparation and the package fixes |
| [deploy-session-gluster4.txt](evidence/deploy-session-gluster4.txt) | The Pacific repository removed, CRB and EPEL enabled on the client |
| [verify-session-gluster1.txt](evidence/verify-session-gluster1.txt) | The finished cluster: versions, health, daemons, OSDs, memory limits, OSD spec, file system, pools, client capabilities, clock skew, chrony |
| [verify-session-gluster2.txt](evidence/verify-session-gluster2.txt) | `ceph-volume`'s log of the OSD attempts, chrony |
| [verify-session-gluster3.txt](evidence/verify-session-gluster3.txt) | chrony |
| [verify-session-gluster4.txt](evidence/verify-session-gluster4.txt) | chrony, the client, the remount, the data and its checksum |
