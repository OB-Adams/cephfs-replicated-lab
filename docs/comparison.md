# GlusterFS and CephFS compared

Milestone 6. A comparison of the two systems as this study ran them: on the same four VMs, the same disks and the same client, put through the same kinds of drills. Phase 1 is [glusterfs-replicated-lab](https://github.com/OB-Adams/glusterfs-replicated-lab); phase 2 is this repository. Every figure below comes from one of the two labs and links to where it was measured. See [milestones.md](milestones.md).

What this cannot say is how either system behaves at scale, on real disks and networks, or under many clients. Each drill ran once or a few times, on one Mac. The differences are worth reading for what they show about each design; the absolute numbers are not.

## At a glance

| | GlusterFS (phase 1) | CephFS (phase 2) |
|---|---|---|
| Version | GlusterFS 11.1 on CentOS Stream 9 | Ceph 20.2 Tentacle, containers deployed by `cephadm` |
| Layout | 2 × 3 distributed-replicated volume, two bricks per server | Six OSDs, pools `size 3 min_size 2`, 145 PGs |
| Where data lives | The file, whole, on a brick's XFS filesystem, found by hashing its name | 4 MiB objects, placed by CRUSH on raw disks under BlueStore |
| Who replicates | The client, to all three bricks at once | The primary OSD, to the other two |
| Metadata | On the bricks, as extended attributes | A separate MDS daemon, with its own pool and journal |
| Client | FUSE | The kernel client (a FUSE client also exists) |
| Daemons per server | `glusterd`, one process per brick, the self-heal daemon | A monitor, OSDs, and on two servers a manager and an MDS; plus exporters and `crash` |
| Losing a server | Writes carried on | Writes carried on, after an 11.9 s stall for the monitor election |
| Losing two of three | The mount failed and had to be remounted | Requests waited 433 s, then completed by themselves |
| Split-brain | Possible, and made and resolved in a drill | Not possible by design: writes go through one primary, and a PG below `min_size` stops |
| Replacing a disk | `reset-brick` or `replace-brick`, then heal | Mark out, rebuild elsewhere at once; a new OSD can take the old ID |
| Expanding | `add-brick`, then a manual rebalance, which skipped files until forced | Add OSDs; data moved by itself in under 2 minutes |
| Access control | By address (`auth.allow`) and certificate name | Per-key capabilities, by daemon type, path and read-only |
| Encryption | Mutual TLS with a lab CA | msgr2 `secure`, keyed from cephx; msgr1 still open |
| Monitoring | An exporter script and five rules written for the lab | Exporters and 99 rules shipped, deployed with `ceph orch apply` |
| Reads | 847 MiB/s, 12,260 IOPS | 1,225 MiB/s (145 %), 20,396 IOPS (166 %) |
| Writes | 199 MiB/s, 3,278 IOPS | 140 MiB/s (70 %), 1,639 IOPS (50 %), less certain |

## Architecture

**Gluster is a file system made of file systems.** Each brick is an ordinary directory on XFS. A file lives whole on the bricks of one replica set, chosen by hashing its name against ranges stored on each directory. Everything else happens in the client: the FUSE client process sends each write to all three bricks of the set and records in extended attributes which copies missed it. The servers mostly store and serve; `glusterd` manages configuration, and the self-heal daemon repairs what the attributes say is stale. A brick can be read with `ls`, and a file recovered from it with `cp`.

**Ceph is an object store with a file system on top.** RADOS stores objects on OSDs that own whole disks. A file is cut into 4 MiB objects; each object name hashes to a placement group, and CRUSH computes that group's three OSDs from the cluster map, so nothing has to be asked where data lives. The monitors keep the maps and agree on every change by Paxos. The client sends a write once, to the primary OSD, which replicates it. Names, directories and permissions are the MDS's job, with its own journal in a metadata pool; the data path does not go through it. Nothing on the disks is readable without Ceph.

**What that meant in practice.** Gluster had fewer moving parts to understand and fewer ways to fail at deployment, but put the cost of replication on the client and the knowledge of what was stale in attributes on each file. Ceph needed more parts and more to learn (milestone 1's deployment met four separate problems before all six OSDs were up) but kept the cluster's state in one place, the monitors, which every recovery below relied on.

## Failure behaviour

| Drill | GlusterFS | CephFS |
|---|---|---|
| One server shut down cleanly while the client wrote | Writes continued; 273 entries queued for heal | Writes continued; one write stalled 11.9 s while the remaining monitors re-formed quorum |
| One server silenced (hard failure), default timeout | Longest write 70.3 s at `network.ping-timeout` 42 s | Longest write 25.8 s at `osd_heartbeat_grace` 20 s |
| The same with a 10 s timeout | 13.2 s | 16.2 s, where the monitor election became the limit |
| Two of three servers lost | Client quorum lost: every lookup failed with `Transport endpoint is not connected`; the mount had to be remounted | No monitor quorum: requests held for 433 s, then completed by themselves when a majority returned; no remount |
| Metadata service lost | Not applicable: no separate metadata service | Active MDS killed: metadata stalled 13.4 s while the standby took over |
| Split-brain | Created by turning quorum off, then resolved with each CLI policy; a warm cache hid it until remount | Not tested; the design does not allow it |

Sources: [phase 1 failure drills](https://github.com/OB-Adams/glusterfs-replicated-lab/blob/main/docs/failure-drills.md), [failure-drills.md](failure-drills.md).

**Where each waits.** A Gluster client waits for a silent brick until `network.ping-timeout`, and then carries on with the other two. A Ceph client never decides anything: the OSDs report a silent peer, the monitors mark it down after the heartbeat grace, and the client follows the new map. The detection is faster on Ceph at default settings, but every change goes through the monitors. That is why even a clean shutdown cost Ceph an 11.9 s stall when a monitor left, and why its 10 s grace could not get below the election time.

**What a majority means.** Losing a majority stopped both, as it should. Gluster's client gave up and failed every request. Ceph held them: the client's request sat until the monitors had quorum again, and then finished. For an application, Ceph's behaviour is a long pause; Gluster's is a crash it has to recover from.

**Split-brain.** Gluster can end with two copies of a file that each claim to be newer, because each client writes to each brick, and a brick that was cut off may have accepted writes the others missed. Quorum prevents it, and with quorum turned off the lab produced one. In Ceph every write to a placement group goes through its primary, which orders it in the PG's log, and a PG with fewer than `min_size` copies stops accepting writes. There is no path for two divergent copies to arise, so there is nothing to resolve.

## Recovery, replacement and expansion

| Task | GlusterFS | CephFS |
|---|---|---|
| A returning server catching up | The self-heal daemon walked its index and healed 273 entries by itself | 2036 degraded objects recovered from PG logs in about 9 s after an hour away |
| A disk lost | `reset-brick` at the same path; the heal did not start until `heal full`, then took 26 s | The OSD marked out; its copies rebuilt on the host's other OSD 14 s later, with the client's slowest write 0.08 s |
| A replacement disk | `replace-brick ... commit force` to a new disk; heal started by itself and finished in about 36 s | The OSD rebuilt with the same ID and refilled in 86 s, after clearing a loop between the orchestrator and its removal queue |
| Adding capacity | `add-brick` refused a brick still carrying the volume ID; the rebalance skipped 320 files on a free-space rule until run with `force`; existing directories got no range on the new set until rebalanced | Three OSDs added; healthy in under 2 minutes, 45 to 54 PGs per OSD, no command |
| Removing capacity | Not done | Three OSDs drained by CRUSH weight and purged in 3 min 20 s, none stopped before the cluster was healthy |
| Planned maintenance on two servers at once | Not done | Lost monitor quorum for about 50 s and held a write 64 s, despite `noout` |

Sources: phase 1's [brick-replacement.md](https://github.com/OB-Adams/glusterfs-replicated-lab/blob/main/docs/brick-replacement.md) and [expansion.md](https://github.com/OB-Adams/glusterfs-replicated-lab/blob/main/docs/expansion.md); [replacement-expansion.md](replacement-expansion.md).

**Data placement is the big difference.** Gluster places files by name and stores the layout on directories, so adding a replica set changes nothing until a rebalance walks every directory and moves files, and its rules can leave files behind link files. CRUSH places objects by computation from the map, so adding OSDs changes the map and the data follows by itself, a little at a time. Ceph did in two minutes and no commands what took Gluster two rebalance runs and an investigation.

**Ceph's automation has its own traps.** In milestone 3, `ceph orch osd rm --replace` zapped the disk without being asked to, and with the OSD spec managed, the orchestrator rebuilt the OSD while the removal queue removed it again, in a loop. Gluster's commands did exactly what they were told; Ceph's orchestrator did more, and the lab had to learn when to set the spec unmanaged.

## Operations

| | GlusterFS | CephFS |
|---|---|---|
| Installing | Packages from the Storage SIG, a pool built by `peer probe`, a volume by one command | `cephadm` from the Storage SIG, EPEL and CRB for the client; a bootstrap, then hosts and services added through the orchestrator |
| Problems met while deploying | None recorded in the build; later, `glusterd` could not load certificates from `/etc/ssl` when TLS was enabled | A missing `python3-jinja2`, an old Pacific client that could not read the new key type, a bootstrap address on IPv6 link-local, and clock skew that stopped OSD creation |
| Describing the deployment | Ansible roles written for the lab | `cephadm` service specs ([../ceph/service-specs.yml](../ceph/service-specs.yml)) |
| Sensitivity to time | Low | High: clock skew blocked OSD creation, and every pause of the Mac produced false failures |
| State to look at | `volume status`, `heal info`, and the logs on each server | `ceph -s` and `ceph health detail` for the whole cluster from any admin host |
| Resource use per server | Modest; 3.5 GiB VMs were enough | Each OSD targets 1.5 GiB of memory; the servers were raised to 8 GiB |

**Clocks were Ceph's weak point here.** Monitors compare timestamps, and beacons and leases are judged by time. Clock skew stopped OSD creation in milestone 1. Each time the Mac slept in milestone 4b, the resumed VMs' clocks were stepped at different moments, and the monitors marked running OSDs down, failed over the MDS and the manager, and marked OSDs out. In milestone 5, gluster1's clock falling behind by minutes coincided with slow requests and dropped standbys. Gluster has no component that compares clocks between servers, and phase 1 recorded no problem from time on the same VMs.

**One place to look.** Ceph's health checks gave the state of the whole cluster in one command from any admin host, and named the problem (`OSD_DOWN`, `PG_DEGRADED`, `MON_CLOCK_SKEW`). Gluster's state was spread over `volume status`, `heal info` and the logs of each server and client.

## Security

| | GlusterFS | CephFS |
|---|---|---|
| Default traffic | Plain TCP | msgr2 `crc`: checksummed, readable on the wire; file contents seen in a capture |
| Who may connect | `auth.allow` by address, `auth.ssl-allow` by certificate name | A cephx key, checked by the monitors |
| What a client may do | The whole volume, subject to file permissions | Capabilities per daemon type: read-only, limited to a path, the metadata pool out of reach |
| A refused client | Refused at the TLS handshake or by the bricks, with clear errors | Refused by the monitors or the MDS; the kernel reports a bad key as `no mds is up` |
| Revocation | Removing the address from `auth.allow` dropped the existing mount at once | `ceph auth rm` stopped new mounts only; the open mount worked until evicted |
| Encryption | Mutual TLS, a lab CA, a certificate per machine | msgr2 `secure`, keyed from cephx, no certificates |
| Turning it on | The volume and `glusterd` stopped on every server | One daemon at a time while the client wrote |
| Plaintext afterwards | Refused | msgr2 `crc` refused; msgr1 still accepted |

Sources: phase 1's [security.md](https://github.com/OB-Adams/glusterfs-replicated-lab/blob/main/docs/security.md), [security.md](security.md).

Ceph's model is finer: a key can be limited to a path, to reading, and away from the metadata pool, where Gluster's access control is all or nothing per client. Encryption needed no certificate authority and no downtime. But it has gaps the lab found: a client with a valid key can still read any file's objects in the data pool directly, so a path limit is only as strong as the MDS; revoking a key does not cut off a mounted client until it is evicted; the mode settings left msgr1 open; and a leftover session of a revoked client stalled an MDS failover for 47 s. Gluster's simpler model behaved more predictably: removing a client's address cut it off at once.

## Monitoring

| | GlusterFS | CephFS |
|---|---|---|
| Exporter for the storage | A script written for the lab, every 30 s | The manager's exporter and `ceph-exporter`, shipped |
| Alert rules | 5, written for the lab | 99, shipped with Ceph |
| Deployment | Containers run by hand on `gluster4`, configuration written for them | `ceph orch apply`; configuration, targets and ports handled by cephadm |
| Notification | None | Alertmanager, into the Ceph Dashboard |
| Drill | One brick killed: both rules pending about 30 s later, then firing | One host's daemons stopped: `CephOSDDownHigh` firing 37 s later, four alerts through to the Dashboard |
| What went wrong | None recorded | Alerts on `OSD_DOWN` cleared when the OSDs were marked out though still down; one failed scrape reset every cluster alert; `CephadmDaemonFailed` lasted 8 minutes past recovery |

Sources: phase 1's [monitoring.md](https://github.com/OB-Adams/glusterfs-replicated-lab/blob/main/docs/monitoring.md), [monitoring.md](monitoring.md).

Ceph's monitoring is far more complete out of the box. Gluster's hand-made exporter covered exactly what the lab chose, and each rule was understood because it was written for it. Ceph's shipped rules are many and good, but the drill showed they inherit the health checks' meanings, which are not always what an operator assumes.

## Performance

| Profile | GlusterFS (FUSE) | CephFS (kernel) | CephFS vs Gluster |
|---|---|---|---|
| Sequential read, 1 MiB | 847 MiB/s | 1,225 MiB/s | 145 % |
| Random read, 4 KiB | 12,260 IOPS, 5.2 ms | 20,396 IOPS, 3.1 ms | 166 % |
| Sequential write, 1 MiB | 199 MiB/s | 140 MiB/s | 70 % |
| Random write, 4 KiB | 3,278 IOPS, 18.4 ms | 1,639 IOPS, 39 ms | 50 % |
| Mixed 70/30, 4 KiB | 6,838 IOPS | 4,244 IOPS | 62 % |
| Small files | 322 files/s | 241 files/s | 75 % |

Source: [benchmark.md](benchmark.md), with phase 1's runs in [evidence/benchmark](evidence/benchmark).

**Reads favoured Ceph, writes favoured Gluster.** A CephFS read went from the kernel straight to one OSD; a Gluster read also crossed into the FUSE process and back. A CephFS write went to the primary, then on to the other two, through BlueStore running with hard-disk settings, with the traffic between OSDs encrypted; a Gluster write went to all three bricks at once.

**Two conditions weaken the write comparison.** The Ceph servers ran with 8 GiB each against Gluster's 3.5 GiB, and the Mac was paging; gluster1's clock fell minutes behind during the run, and the writes varied by up to 50 % between runs. And each system was measured through its usual client, so the comparison includes FUSE against the kernel, not only Gluster against Ceph. The reads, steady within 2 %, are the firmer result.

## Which to use

From what these labs showed, not from general reputation:

- **GlusterFS fits** a small, fixed set of servers serving files to a few clients, where the operators want to read a brick with `ls`, know each command does only what it says, and keep the moving parts few. It needs care with quorum settings and with rebalancing after growth, and its clients do the work of replication.
- **CephFS fits** storage that will grow, shrink and lose disks routinely, many clients, or a need for block and object storage from the same cluster. It recovers and rebalances by itself, keeps one view of the cluster's health, and offers finer access control. In return it needs more memory, good clocks, more knowledge to run, and attention to what its orchestrator does on its own.

## What this study did not test

- More than one client, or more than one load level.
- Real disks and a real network; the virtual disks were cached in the Mac's memory.
- The same memory for both systems; a fair write comparison needs it.
- `ceph-fuse`, which would separate FUSE's cost from the systems' designs.
- RBD and RGW, Ceph's block and object interfaces, which Gluster has no counterpart for.
- Erasure coding, multiple active MDS daemons, snapshots and quotas, on either side.
- Upgrades between versions.
- Gluster's Ansible automation has no Ceph counterpart here beyond the exported service specs.
