# Milestones

Status values: Planned, In progress, Blocked, Complete. A milestone is marked Complete only when its acceptance criteria were actually met in the lab.

| # | Milestone | Status |
|---|---|---|
| 1 | Deploy Ceph and mount CephFS | Complete |
| 2 | Failure drills | Complete |
| 3 | OSD replacement and expansion | Complete |
| 4a | cephx capabilities and encryption on the wire | Complete |
| 4b | Monitoring and alerts | Complete |
| 5 | Benchmark against the Gluster baseline | Complete |
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

**Goal.** The Ceph equivalents of phase 1's milestone 2: a failed OSD's disk lost and the OSD rebuilt with the same ID, the cluster expanded with a disk per server, and disks taken out of service, with the data movements observed and the client's writes measured.

**Changes.** 2 GB of test data with recorded checksums and a check script ([../scripts/ceph-check.sh](../scripts/ceph-check.sh)); `gluster2` labelled `_admin` with `ceph-common` installed, as a second admin host; a 10 GB `vdd` disk added to every server; three OSDs created on them and removed again. The cluster ends as it started: six OSDs on `vdb` and `vdc`, the spec unchanged, the `vdd` disks empty and unused.

**Concepts covered.** Degraded against misplaced; one OSD out against a whole host; CRUSH weight, reweight, in and out; destroyed against purged; draining; `noout` for planned maintenance; managed and unmanaged specs and the orchestrator's removal queue; the balancer and the PG autoscaler.

**Acceptance criteria and result.**

| Criterion | Result |
|---|---|
| A lost OSD's copies rebuilt, and a replacement OSD built with the same ID | Met: copies rebuilt on the host's other OSD 14 s after the out; a new `osd.3` refilled in 86 s, after clearing a removal-queue loop |
| The cluster expanded by one disk per server, with data spread onto the new OSDs | Met: healthy under 2 minutes after the three new OSDs booted; 45 to 54 PGs per OSD |
| OSDs taken out of service without stopping one that a PG still needed | Met: three OSDs drained and purged in 3 min 20 s, each stopped only after the cluster was healthy |
| No data lost or damaged | Met: all 8400 drill files correct, the 2 GB fill set and the reference file matching, deep scrub found no inconsistent PGs |
| Recordings, cluster logs and writer logs archived | Met, in `docs/evidence/` |

**Result (2026-11-05).** Met. Losing a disk cost the client nothing: its slowest write during drill 5 took 0.08 s. Every data movement, including the expansion and the drain, was reported as degraded rather than misplaced. Marking the OSD destroyed with `ceph orch osd rm --replace` zapped the disk although `--zap` was not given, and with the OSD spec managed the orchestrator and the removal queue rebuilt and removed the replacement in a loop until the queue entry was stopped. In drill 6a two servers were shut down together for their disks, which lost monitor quorum for about 50 seconds and held one client write for 64 s, despite `noout`; one server alone cost about 20 s. Full write-up in [replacement-expansion.md](replacement-expansion.md).

## Milestone 4: security and monitoring

Split in two, as in phase 1: 4a for access control and encryption, 4b for monitoring and alerts.

### 4a: cephx capabilities and encryption on the wire

**Goal.** Show what crosses the network with the default settings; test cephx keys and capabilities by refusal; encrypt every msgr2 connection without taking the cluster down, and check which clients are still accepted.

**Changes.** All six msgr2 mode settings (`ms_cluster_mode`, `ms_service_mode`, `ms_client_mode` and their `ms_mon_` versions) set to `secure`, and every daemon but the active manager restarted one at a time; the client's `/etc/fstab` line now ends `ms_mode=secure`. Two test keys, `client.reader` and `client.scoped`, were made and deleted again.

**Concepts covered.** cephx tickets and service keys; capabilities per daemon type, with path and read-only limits; why the metadata pool is out of a client's reach and the data pool is not; revocation, eviction and the blocklist; msgr1 and msgr2, the `crc` and `secure` modes and how they are negotiated; the MDS reconnect state.

**Acceptance criteria and result.**

| Criterion | Result |
|---|---|
| File contents shown readable on the wire in the default mode | Met: every marker line found in the client's and in gluster2's captures, screenshot 10 |
| Forged, unknown, read-only and path-limited keys refused, each by the daemon that owns the cap | Met: logins refused by the monitors, the write and the root mount by the MDS, the metadata pool by the OSDs, screenshot 11 |
| A key revoked and its client cut off | Met, with a finding: deleting the key stopped new mounts only; the open mount worked until its session was evicted |
| Client and cluster traffic encrypted, with no marker found in either capture | Met: 0 of 410 packets on the client, 0 of 4550 on gluster2, screenshot 12 |
| Encryption turned on without stopping the file system | Met, with one 51 s stall at MDS failover caused by a stale client session |
| A client asking for plaintext refused | Partly met: `ms_mode=crc` refused (screenshot 13); `ms_mode=legacy`, msgr1, still mounts |
| No data lost or damaged | Met: all 1500 drill 8 files and 3000 drill 5 files correct, the fill set and the reference file matching |
| Recordings, cluster log and writer log archived | Met, in `docs/evidence/`, addresses masked; packet captures kept on the VMs |

**Result (2026-11-06).** Met, with msgr1 left open. In `crc` mode the contents of three test files were read straight from the client's traffic. A wrong key fails at the monitor, but the kernel reports it as `no mds is up`; the real reason is only in `dmesg`. Deleting a key with `ceph auth rm` did not cut off a mounted client: its session had to be evicted. The secure-mode change was rolled through every monitor and OSD with the client writing and no write over 1.2 s. Restarting the active MDS stalled the client for 51.1 s, because the new MDS waited 47 s for a revoked client's leftover session to reconnect before evicting it. Afterwards no marker was found in client or cluster traffic, and a `crc` client was refused, but a `legacy` (msgr1) client still mounted, because the mode settings govern msgr2 only. The active manager was not restarted: `ceph orch daemon restart` refuses it. Full write-up in [security.md](security.md).

### 4b: monitoring and alerts

**Goal.** Metrics and alerts from the manager's Prometheus module, cephadm's monitoring stack and the Ceph Dashboard, with alerts seen to fire during a failure and clear afterwards.

**Changes.** `gluster4` added to the cluster as a cephadm host labelled `monitoring`; Prometheus, Alertmanager and Grafana placed there; `node-exporter`, `ceph-exporter` and `crash` on every host; the manager's `prometheus` and `dashboard` modules enabled, with a Dashboard `admin` user; port 8443 opened on the manager hosts. The specs are in [../ceph/service-specs.yml](../ceph/service-specs.yml), and the alert-reading script in [../scripts/ceph-alerts.py](../scripts/ceph-alerts.py).

**Concepts covered.** Health checks against metrics; Prometheus's pull model, targets and service discovery; the manager's exporter, `ceph-exporter` and `node-exporter`; alert rules, `for` durations and the pending, firing and resolved states; Alertmanager's grouping and receivers; the Dashboard; cephadm hosts, labels and placement; down against out in the health checks.

**Acceptance criteria and result.**

| Criterion | Result |
|---|---|
| Prometheus scraping the cluster, a dashboard showing it, the alert rules loaded | Met: 9 targets `UP`, 99 rules in 16 groups, the Dashboard and Grafana showing the cluster, screenshots 14 to 17 |
| At least two alerts seen to fire during the incident and resolve afterwards, with the times | Met: `CephOSDDownHigh`, `CephMonDown`, `CephMonDownQuorumAtRisk` and `CephadmDaemonFailed` fired and resolved, timed in `drill9-alertlog.txt` |
| Firing alerts reaching Alertmanager and the Ceph Dashboard | Met: all four under the `ceph-dashboard` receiver, screenshots 18 and 19 |
| No data lost | Met for the writer: all 1500 writes `ok`. The full file check was not run |
| Recordings, cluster log, writer log and alert state archived | Met, in `docs/evidence/`, addresses masked and the Dashboard password redacted; no recording from `gluster3` |

**Result (2026-11-07).** Met. Ceph's stack went up with six `ceph orch apply` commands and shipped 99 alert rules, against the Gluster lab's hand-written exporter and five rules. Stopping every Ceph daemon on `gluster3` had alerts firing 37 s after the OSDs went down, through Alertmanager to the Dashboard. The Mac slept in the middle of the incident and paused the VMs for 31 minutes; on resume the monitors marked running OSDs down for missed beacons and marked `gluster3`'s OSDs out, with no data moved because there was no third host to move it to. Three weaknesses showed: alerts built on `OSD_DOWN` cleared once the OSDs were out though they were still down, one failed scrape of the manager's exporter reset every cluster alert to pending, and `CephadmDaemonFailed` stayed up eight minutes after recovery until cephadm's daemon cache was refreshed. The Dashboard's links to Grafana, Alertmanager and Prometheus stayed empty until the three services were reconfigured. Full write-up in [monitoring.md](monitoring.md).

## Milestone 5: benchmark against the Gluster baseline

**Goal.** The same six `fio` profiles as phase 1, run with the kit in [../benchmarks](../benchmarks), on the CephFS kernel mount, and compared with phase 1's results.

**Changes.** None left behind: `fio` installed on `gluster1` and `gluster4`, an XFS filesystem made on `gluster1`'s spare `vdd` for the control run and wiped again, and the test directory on CephFS removed.

**Concepts covered.** Bandwidth, IOPS and latency, and Little's law between them; the path of a CephFS request against a Gluster one: kernel client against FUSE, primary-copy replication against client fan-out; BlueStore's hard-disk settings and deferred writes; the mClock scheduler; why a guest's clock falls behind when its host is short of resources.

**Acceptance criteria and result.**

| Criterion | Result |
|---|---|
| All six profiles run three times against CephFS without errors, at the configured load | Met: 18 runs with `error` 0, queue depth 16 for 100 % of the time; the write profiles run again, 8 more runs |
| The results compared with Gluster's, with the limits recorded | Met: [benchmark.md](benchmark.md), with phase 1's runs and a control on the same Mac |
| The cluster healthy before and after, test data removed, the spare disk left empty | Partly met: the first CephFS run started on `HEALTH_WARN` (clock skew on gluster1); test data removed and `vdd` wiped |

**Result (2026-11-09).** Met, with the writes less certain than the reads. Against Gluster through FUSE, CephFS through the kernel client read faster: 1,225 MiB/s against 847 for large blocks (145 %), and 20,396 against 12,260 IOPS for 4 KiB (166 %), each 4 KiB read taking 3.1 ms against 5.2. It wrote slower: 140 against 199 MiB/s (70 %), 1,639 against 3,278 random 4 KiB IOPS (50 %), a 70/30 mix at 62 %, and 241 against 322 small files a second (75 %), where the 4 KiB write, not the file creation, took the time. The control on a spare disk matched phase 1's raw figures within 10 %. During the run gluster1's clock fell behind by minutes four times, a sign of its VM being starved by a host that had 27.5 of its 36 GiB given to VMs and was paging; the writes, which wait for all three hosts, varied by up to 50 % between runs while the reads stayed within 2 %. Full write-up in [benchmark.md](benchmark.md).

## Milestone 6: Gluster and CephFS comparison

**Goal.** A written comparison of the two systems on the same hardware: architecture, failure behaviour, recovery, operations, security and performance, from what both labs measured.
