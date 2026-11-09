# Benchmark against the Gluster baseline

Milestone 5. Phase 1's six `fio` profiles, unchanged, were run against CephFS through the kernel client on `gluster4` and compared with phase 1's results for Gluster through its FUSE client. As a control, the same profiles ran on plain XFS on `gluster1`'s spare disk, to check that the Mac itself had not changed speed since phase 1. See [milestones.md](milestones.md).

Run on 2026-11-09, times UTC. Phase 1's runs are from 2026-10-30.

**Read every figure as a comparison on one Mac, not as a measure of Ceph or Gluster.** All four VMs share one Mac's CPU, memory and SSD, the virtual disks are cached in its memory, and the network is a virtual switch. On top of that, the Mac was short of memory during this run (see [below](#the-host-was-short-of-memory)), which disturbed the write results more than the reads.

## Setup

| Item | Phase 1 (Gluster) | This run (CephFS) |
|---|---|---|
| VMs | CentOS Stream 9, kernel `5.14.0-759.el9.aarch64`, 5 vCPUs | The same |
| Server memory | 3.5 GiB each | 8 GiB each (7.4 GiB usable), raised for Ceph |
| Client memory | 3.5 GiB | The same |
| On the client besides fio | Prometheus and Grafana containers | Prometheus, Alertmanager, Grafana and the exporters, as cephadm daemons |
| fio | 3.35 | 3.35 |
| Client | FUSE (`glusterfs`), mutual TLS | Kernel client, msgr2 `secure` (`ms_mode=secure`) |
| Storage | XFS on LVM thin volumes, `strict-o-direct on` | BlueStore on the raw disks, `osd_memory_target` 1.5 GiB |
| Replication | `replica 3`, 2 x 3 bricks | Pools `size 3`, six OSDs |

| Target | Where fio ran | Directory |
|---|---|---|
| `gluster-fuse` | gluster4, phase 1 | `/mnt/gv0/bench` |
| `raw-xfs` | gluster1, phase 1 | XFS under a brick, outside the brick directory |
| `cephfs-kernel` | gluster4 | `/mnt/cephfs/bench` |
| `raw-xfs-vdd` | gluster1 | XFS made directly on the spare `vdd` disk, wiped again afterwards |

The six profiles and their settings are in [phase 1's benchmark document](https://github.com/OB-Adams/glusterfs-replicated-lab/blob/main/docs/benchmark.md#setup) and in [../benchmarks/fio](../benchmarks/fio). In short:
- The five time-based profiles keep 64 requests in flight: 4 workers, each with 16 outstanding.
- Each runs 10 s of warm-up then 60 s measured, on four 1 GiB files, with `O_DIRECT` and the client's page cache dropped before every run.
- `small-files` has 4 workers each create 2,000 files of 4 KiB, one at a time.

### What the OSDs were running with

| Setting | Value | What it means |
|---|---|---|
| `rotational` | `1` on every OSD | The virtual disks report themselves as spinning disks |
| `bluestore_bdev_type` | `hdd` | So BlueStore uses its hard-disk settings, including deferred writes: a small write goes first into its RocksDB log, then to its final place, two writes on the same disk |
| `osd_op_queue` | `mclock_scheduler`, profile `balanced` | The scheduler that shares each OSD between client I/O and background work |
| mClock capacity | 315 IOPS, the hard-disk default | At start-up each OSD measured itself at 7,388 to 14,158 IOPS, but that is outside the 50 to 500 IOPS the scheduler accepts for a hard disk, so it kept the default |
| File layout | `object_size=4194304 stripe_count=1` | Each file is cut into 4 MiB objects |

## How the run went

| Time | Event |
|---|---|
| 00:44:34 | Direct-I/O check on CephFS: `err= 0`, 64 MiB written at 68.0 MiB/s with one request in flight (screenshot 22) |
| 00:54 to 01:12 | `raw-xfs-vdd`, first run, on gluster1 |
| 01:21 to about 01:25 | First CephFS run, stopped by hand during `seq-write` at 34 to 62 MiB/s; OSD commit latency 200 to 400 ms. Its files were replaced |
| 01:25 to 01:43 | `raw-xfs-vdd` run again; these are the results kept (screenshot 23) |
| 01:44 to 02:12 | `cephfs-kernel`, all six profiles (screenshot 25) |
| 02:36 to 02:47 | Re-run of the three write profiles: `cephfs-kernel-w2` |
| 02:52 to 02:58 | Re-run of `seq-write`: `cephfs-kernel-w3` |

**The CephFS run started on an unhealthy cluster.** At 01:44 the cluster was `HEALTH_WARN`:
- `clock skew detected on mon.gluster2`, its messages stamped 261 s in the future;
- slow requests piling up on `mon.gluster2`;
- the standby MDS and standby manager on `gluster2` dropped as unavailable.

The skew was gluster1's clock, 261 s slow, not gluster2's being fast. chrony stepped gluster1's clock at 01:50:50, and the cluster was healthy again at 01:52:07 ([bench-cephw.txt](evidence/bench-cephw.txt), screenshot 24). Before that, `osd.0` reported 17 requests "waiting for sub ops", that is, waiting for the other copies. All three runs of the first `seq-write` overlapped this window; run 3 took 5½ minutes to finish, not 70 seconds.

**The write profiles stalled even on a healthy cluster.** In `rand-write-4k` run 3 and `mixed-70-30` run 1, fio's estimate of the time left jumped to 9 to 15 minutes, and `mixed-70-30` run 1 took 4 min 49 s to finish. The cluster log showed nothing, and it would not have: `ceph -w` runs on gluster1. So the three write profiles were run again, and `seq-write` a third time.

**Some re-run results were overwritten.** The re-run's commands had been pasted while `script` was starting, and the outer shell ran them again after the recording ended. They were stopped with Ctrl-C, but not before they had replaced `seq-write` runs 1 to 3 and `rand-write-4k` run 1 of the re-run with runs of a few seconds. Those four files are left out of the evidence; `seq-write` was run a third time instead.

### The host was short of memory

chrony on gluster1 found its clock slow four times in under three hours, by 307, 262, 233 and 140 seconds, and stepped it each time ([bench-chrony-gluster1.txt](evidence/bench-chrony-gluster1.txt)). A guest's clock falls behind like that when the host does not give the VM's processors time to run. The monitors stayed in quorum throughout, so gluster1 was never stopped for more than a few seconds at once. The time was lost in many short stalls, and the requests in flight to gluster1 waited through each of them.

The Mac has 36 GiB of memory, of which the four VMs are configured for 27.5 GiB. It had 2.9 of its 4 GiB of swap in use afterwards, which means macOS had been paging memory out to disk. In phase 1 the servers had 3.5 GiB each, 14 GiB for all four VMs. The memory was raised for Ceph, and it has made this comparison less clean than phase 1's.

Every write goes to three OSDs on three hosts and completes only when all three have it, so a stalled gluster1 holds up every write with a copy there. A read goes to one OSD, so it is held up only when that OSD's host stalls. That fits the results: the reads were steady to within 2 %, the writes varied by up to 50 %.

### The control

| Profile | `raw-xfs` (phase 1) | `raw-xfs-vdd` (now) | Change |
|---|---|---|---|
| `seq-write` | 18,804 MiB/s | 18,537 MiB/s | −1 % |
| `seq-read` | 21,703 MiB/s | 22,095 MiB/s | +2 % |
| `rand-read-4k` | 154,184 IOPS | 166,349 IOPS | +8 % |
| `rand-write-4k` | 133,920 IOPS | 140,214 IOPS | +5 % |
| `mixed-70-30` | 124,562 IOPS | 135,473 IOPS | +9 % |
| `small-files` | 31,128 files/s | 33,613 files/s | +8 % |

The raw speed of a VM writing to its own disk is within 10 % of phase 1's, and both run at the speed of the Mac's memory, not its SSD. So the Mac had not become slower in itself. What changed is how much memory the VMs ask of it, which a single VM writing to its own disk does not show.

## Results

Medians, with the range of the main figure across runs. The full tables, with every target and run set, are in [evidence/benchmark/results.md](evidence/benchmark/results.md).

| Profile | Gluster (FUSE) | CephFS (kernel) | CephFS runs | CephFS vs Gluster |
|---|---|---|---|---|
| `seq-read` | 847 MiB/s | **1,225 MiB/s** | 1,204 to 1,228 (3 runs) | **145 %** |
| `rand-read-4k` | 12,260 IOPS | **20,396 IOPS** | 20,222 to 20,496 (3) | **166 %** |
| `seq-write` | 199 MiB/s | 140 MiB/s | 134 to 145 (3, re-run on a healthy cluster) | 70 % |
| `rand-write-4k` | 3,278 IOPS | 1,639 IOPS | 1,109 to 1,874 (5 runs, from two sets) | 50 % (34 to 57 %) |
| `mixed-70-30` | 6,838 IOPS | 4,244 IOPS | 3,059 to 5,329 (6 runs, from two sets) | 62 % (45 to 78 %) |
| `small-files` | 322 files/s | 241 files/s | 209 to 246 (3) | 75 % |

The first `seq-write` set, 84 to 135 MiB/s, ran while gluster1's clock was wrong and is not used above. Phase 1's Gluster runs were all within 8 % of their medians.

| Profile | Gluster mean / p99 latency (ms) | CephFS mean / p99 latency (ms) |
|---|---|---|
| `seq-read` | 70.9 / 106.4 | 52.1 / 80.2 |
| `rand-read-4k` | 5.21 / 10.29 | 3.11 / 6.32 |
| `seq-write` | 302.9 / 400.6 | 459.8 / 1,417.7 |
| `rand-write-4k` | 18.4 / 38.5 | 39.0 / 164.6 |
| `mixed-70-30` (reads) | 8.60 / 25.30 | 3.94 to 4.39 / 27.4 to 44.3 |
| `small-files` (the 4 KiB write) | 3.08 / 4.55 | 15.82 / 29.49 |

## Findings

**Reads were faster on CephFS, by 45 % for large blocks and 66 % for small ones.** With 64 requests in flight, Little's law ties throughput to time per request: 20,396 IOPS × 3.11 ms ≈ 63 in flight, as configured. Each 4 KiB read took 3.1 ms against Gluster's 5.2 ms. A CephFS read goes from the kernel client straight to the primary OSD. A Gluster read also goes from the kernel through FUSE to the `glusterfs` process in user space, and back the same way. The reads ran on a healthy cluster, and each set's three runs were within 2 % of each other.

**Writes were slower on CephFS, by 30 to 50 %, and the latency says why.** A 4 KiB random write took 39 ms on average, against 18 ms on Gluster. The direct-I/O check, one 1 MiB write at a time, shows the same thing without any queueing: 68 MiB/s, about 15 ms per write, against Gluster's 182 MiB/s and 5.5 ms. `ceph osd perf` during `seq-write` showed each OSD taking 110 to 121 ms to commit a write (screenshot 24), and 200 to 400 ms during the first, abandoned attempt. Four things add time to a CephFS write that a Gluster write does not pay. They were not separated in this run, so their shares are not known:

- **Two hops, one after the other.** A Ceph client sends the write to the primary OSD, which sends it to the other two and replies only when both have answered. A Gluster client sends the write to all three bricks at once.
- **BlueStore on hard-disk settings.** The OSDs take the virtual disks for spinning disks, so a small write is deferred: written into RocksDB's log, then to its place on the disk, each with its own metadata update, all on one disk.
- **Encryption on more links.** msgr2 `secure` encrypts the client's link and the traffic between OSDs. Gluster's TLS covered client to brick, and there is no brick-to-brick traffic in a Gluster write.
- **The stalls.** Every write waits for gluster1 whenever one of its copies is there, and gluster1 was losing minutes to its host (above).

The writes' spread is the stalls' doing; the gap to Gluster is not only that. Even the best CephFS runs (1,874 IOPS, 5,329 IOPS, 145 MiB/s) stayed below Gluster's medians.

**Creating a file was cheap; writing it was not.** In `small-files`, the four workers together made 241 files a second, so each worker took about 16.6 ms per file. The 4 KiB write inside that took 15.8 ms on average, which leaves under a millisecond to create, open and close each file. On Gluster the write took 3.1 ms of 12.4 ms per file: about three quarters of the time went on creating and closing. The MDS grants the client capabilities over the new files, so most of the metadata work happens without a round trip to it. CephFS lost `small-files` on the write, not the create.

**The mixed profile came out in two groups.** The six `mixed-70-30` runs fell at about 3,000 to 3,400 IOPS or about 5,000 to 5,300, with no run in between. A stall during the minute either happened or did not.

**More requests in flight helped CephFS's sequential writes more than Gluster's.** With one 1 MiB write at a time, Gluster reached 182 MiB/s and with 64 in flight 199 MiB/s: it was already near its limit. CephFS went from 68 MiB/s to 140 MiB/s, so it could use the parallelism, spreading writes over more placement groups and OSDs. Neither reached the speed of the disks below: with 64 in flight, each 1 MiB write waited 460 ms on CephFS and 303 ms on Gluster, mostly in queues.

## Verification

| Check | Result |
|---|---|
| Direct I/O through the CephFS mount | `err= 0`, 64 MiB written (screenshot 22) |
| Runs completed | 18 runs for `cephfs-kernel` and 18 for `raw-xfs-vdd`, every one with `error` 0; 5 and 3 for the re-runs |
| Load as configured | Queue depth 16 for 100 % of the time in every asynchronous run |
| Cluster before the CephFS run | `HEALTH_WARN`: clock skew, slow requests, no standby MDS or manager. Healthy by 01:52 |
| Cluster before the re-runs | `HEALTH_OK` from 02:36:21, after another clock step at 02:35:51 |
| Test data removed | `/mnt/cephfs/bench` removed; data in the cluster back to 2.2 GiB |
| Spare disk | `wipefs -a /dev/vdd`: no filesystem left, as milestone 3 left it |

Screenshot 26 was taken after the first CephFS run, before the re-runs, so it shows only the `cephfs-kernel` set: `seq-write` at 65 %, `mixed-70-30` at 47 %. The tables above and [evidence/benchmark/results.md](evidence/benchmark/results.md) include the re-runs.

## Limitations

- **Host memory.** The servers have more than twice phase 1's memory, the Mac was paging, and gluster1's clock showed it losing minutes. The writes are the least reliable figures here. Running both systems again with the VMs at the same, smaller memory would remove this difference.
- **Kernel client against FUSE.** Each system was measured through its usual client, but that bundles two differences: Ceph's design, and the absence of FUSE. `ceph-fuse` would separate them.
- **No `size 3` raw baseline for Ceph.** BlueStore has no filesystem to run fio on underneath, so there is no Ceph equivalent of `raw-xfs`. `rados bench` on a test pool would measure RADOS without CephFS and the MDS.
- **Hard-disk tuning.** The OSDs ran with their hard-disk settings. Marking the devices as SSDs (`ceph osd crush set-device-class ssd`) or setting `osd_mclock_max_capacity_iops_hdd` would show how much that costs.
- **One client, one load level,** one block size per pattern, as in phase 1.

## Evidence

- fio's JSON output: [evidence/benchmark/](evidence/benchmark), with phase 1's `gluster-fuse` and `raw-xfs` runs copied in, so [results.md](evidence/benchmark/results.md) can be rebuilt with `python3 benchmarks/summarize.py docs/evidence/benchmark gluster-fuse`.
- Session logs: [bench-session-gluster1.txt](evidence/bench-session-gluster1.txt), [bench-session-gluster4.txt](evidence/bench-session-gluster4.txt) and [bench-w2-session-gluster4.txt](evidence/bench-w2-session-gluster4.txt).
- Cluster logs: [bench-cephw.txt](evidence/bench-cephw.txt) and [bench-w2-cephw.txt](evidence/bench-w2-cephw.txt).
- Clock steps and the Mac's memory: [bench-chrony-gluster1.txt](evidence/bench-chrony-gluster1.txt).
- Screenshots 22 to 26.
