# Milestones

Status values: Planned, In progress, Blocked, Complete. A milestone is marked Complete only when its acceptance criteria were actually met in the lab.

| # | Milestone | Status |
|---|---|---|
| 1 | Deploy Ceph and mount CephFS | Complete |
| 2 | Failure drills | Complete |
| 3 | OSD replacement and expansion | Planned |
| 4 | Security and monitoring | Planned |
| 5 | Benchmark against the Gluster baseline | Planned |
| 6 | Gluster and CephFS comparison | Planned |

## Milestone 1: deploy Ceph and mount CephFS

**Goal.** A healthy three-node Ceph cluster, deployed with `cephadm` on the disks wiped at the end of phase 1, serving a CephFS file system to a separate client, with the placement of a file's data traced to its OSDs.

**Changes.** Ceph 20.2 from the CentOS Storage SIG, with CRB and EPEL for the client libraries; three monitors, two managers, six OSDs (two per server) from a service spec, a CephFS file system with one active and one standby MDS; a client key limited to that file system; a kernel mount on `gluster4` in `/etc/fstab`; chrony set to step the clock on every VM.

**Concepts covered.** RADOS and pools, monitors and Paxos quorum, OSDs and BlueStore, placement groups and CRUSH, primary OSDs and replication, the MDS and CephFS's metadata and data pools, cephx keys and capabilities, the `cephadm` orchestrator, the placement-group autoscaler.

**Acceptance criteria and result.**

| Criterion | Result |
|---|---|
| `HEALTH_OK` with three monitors in quorum, six OSDs up and in, all PGs `active+clean` | Met, screenshot 01 and `docs/evidence/verify-session-gluster1.txt` |
| CephFS with one active and one standby MDS; both pools `size 3 min_size 2` | Met, `verify-session-gluster1.txt` |
| Client mounts with a key limited to `cephfs`, and the mount survives a remount from `/etc/fstab` | Met, `verify-session-gluster4.txt` |
| A client file's objects traced to three OSDs on three different hosts | Met, screenshot 02 |
| Session recordings archived in `docs/evidence/` | Met, admin key redacted |

**Result (2026-11-03).** Met. The cluster runs Ceph 20.2.5 in containers, with 20.2.4 host tools. The two chunks of a 10 MiB file traced in Part 9 landed in different placement groups, with one copy on each server. Getting there needed fixes for a missing `python3-jinja2` dependency in the SIG's `cephadm`, a Pacific client left on the VMs that could not read the new AES-256 admin key, Tentacle client libraries that come from EPEL, and a bootstrap address that resolved to IPv6 link-local. gluster2's OSDs were created only after clock skew of up to 15 s between the monitors was corrected: every earlier attempt stopped at `osd new`. After an unattended restart of every VM, the cluster and the client's mount came back healthy by themselves. Full write-up in [deploy.md](deploy.md); issues in [troubleshooting.md](troubleshooting.md).

## Milestone 2: failure drills

**Goal.** The phase 1 failure drills repeated on Ceph: a graceful node loss, a hard failure with the client stall measured, and the loss of a majority, plus the loss of the active MDS, which Gluster has no equivalent for. Ceph's monitor quorum and `min_size` replace Gluster's server and client quorum; the drills record how each behaves.

**Changes.** A writer that creates each file with `fsync` and records when each write started ([../scripts/drill-writer.sh](../scripts/drill-writer.sh)); four drills with the cluster log recorded throughout; a deep scrub of both CephFS pools afterwards. No configuration was left changed: `osd_heartbeat_grace` was set to 10 s for drill 2's second run and removed again.

**Concepts covered.** OSD heartbeats, failure reports and the grace period; `down` against `out` and `mon_osd_down_out_interval`; peering and the PG states; recovery from PG logs against backfill; `min_size` holding I/O rather than failing it; monitor leases, elections and quorum; MDS beacons, ranks and the replay, reconnect, rejoin and active states; client sessions and capabilities; deep scrub.

**Acceptance criteria and result.**

| Criterion | Result |
|---|---|
| Graceful loss of one host survived, the host caught up by itself on return | Met: writes continued, 2036 degraded objects recovered in about 9 s after an hour away |
| Hard-failure client stall measured with two `osd_heartbeat_grace` values | Met: 25.8 s at 20 s, 16.2 s at 10 s, single run each |
| Behaviour with a majority lost recorded, and recovery afterwards | Met: requests held for 433 s, then completed by themselves |
| MDS failover measured | Met: 13.4 s stall, standby active 2 s after taking rank 0 |
| No data lost or damaged | Met: all 3800 drill files correct, reference checksum unchanged, deep scrub found no inconsistent PGs |
| Session recordings, cluster logs and writer logs archived | Met, in `docs/evidence/` |

**Result (2026-11-04).** Met. Writes carried on through a clean host shutdown, but one write stalled 11.9 s while the remaining monitors re-formed their quorum; the same stall appeared whenever a host running a monitor left. A silent host was marked down after 24.7 s at the default grace, and after 14.0 s at a grace of 10 s, where the monitors' own election was the limit. With two of three hosts down nothing failed: the client's request waited seven minutes and completed once a majority was back, where the Gluster mount failed and had to be remounted. Killing the active MDS stalled metadata for 13.4 s; the failover was triggered when systemd restarted the killed daemon, before the beacon grace ran out. Full write-up in [failure-drills.md](failure-drills.md).

## Milestone 3: OSD replacement and expansion

**Goal.** The Ceph equivalents of phase 1's milestone 2: a failed OSD destroyed and recreated, an OSD moved to a new disk, and the cluster expanded, with recovery and backfill observed.

## Milestone 4: security and monitoring

**Goal.** cephx capabilities tested by refusal, encryption on the wire with msgr2 secure mode, and metrics and alerts from the manager's Prometheus module and the Ceph dashboard.

## Milestone 5: benchmark against the Gluster baseline

**Goal.** The same six `fio` profiles as phase 1, run with the kit in [../benchmarks](../benchmarks), on the CephFS kernel mount, and compared with phase 1's results.

## Milestone 6: Gluster and CephFS comparison

**Goal.** A written comparison of the two systems on the same hardware: architecture, failure behaviour, recovery, operations, security and performance, from what both labs measured.
