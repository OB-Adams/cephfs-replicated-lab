# Milestones

Status values: Planned, In progress, Blocked, Complete. A milestone is marked Complete only when its acceptance criteria were actually met in the lab.

| # | Milestone | Status |
|---|---|---|
| 1 | Deploy Ceph and mount CephFS | In progress |
| 2 | Failure drills | Planned |
| 3 | OSD replacement and expansion | Planned |
| 4 | Security and monitoring | Planned |
| 5 | Benchmark against the Gluster baseline | Planned |
| 6 | Gluster and CephFS comparison | Planned |

## Milestone 1: deploy Ceph and mount CephFS

**Goal.** A healthy three-node Ceph cluster, deployed with `cephadm` on the disks wiped at the end of phase 1, serving a CephFS file system to a separate client, with the placement of a file's data traced to its OSDs.

**Changes.** Ceph 20.2 from the CentOS Storage SIG; three monitors, two managers, six OSDs (two per server) from a service spec, a CephFS file system with one active and one standby MDS; a client key limited to that file system; a kernel mount on `gluster4` in `/etc/fstab`.

**Concepts covered.** RADOS and pools, monitors and Paxos quorum, OSDs and BlueStore, placement groups and CRUSH, primary OSDs and replication, the MDS and CephFS's metadata and data pools, cephx keys and capabilities, the `cephadm` orchestrator.

**Acceptance criteria.**

| Criterion | Result |
|---|---|
| `HEALTH_OK` with three monitors in quorum, six OSDs up and in, all PGs `active+clean` | |
| CephFS with one active and one standby MDS; both pools `size 3 min_size 2` | |
| Client mounts with a key limited to `cephfs`, and the mount survives a remount from `/etc/fstab` | |
| A client file's objects traced to three OSDs on three different hosts | |
| Session recordings archived in `docs/evidence/` | |

## Milestone 2: failure drills

**Goal.** The phase 1 failure drills repeated on Ceph: a graceful node loss, a hard failure with the client stall measured, and the loss of a majority. Ceph's monitor quorum and `min_size` replace Gluster's server and client quorum; the drills record how each behaves.

## Milestone 3: OSD replacement and expansion

**Goal.** The Ceph equivalents of phase 1's milestone 2: a failed OSD destroyed and recreated, an OSD moved to a new disk, and the cluster expanded, with recovery and backfill observed.

## Milestone 4: security and monitoring

**Goal.** cephx capabilities tested by refusal, encryption on the wire with msgr2 secure mode, and metrics and alerts from the manager's Prometheus module and the Ceph dashboard.

## Milestone 5: benchmark against the Gluster baseline

**Goal.** The same six `fio` profiles as phase 1, run with the kit in [../benchmarks](../benchmarks), on the CephFS kernel mount, and compared with phase 1's results.

## Milestone 6: Gluster and CephFS comparison

**Goal.** A written comparison of the two systems on the same hardware: architecture, failure behaviour, recovery, operations, security and performance, from what both labs measured.
