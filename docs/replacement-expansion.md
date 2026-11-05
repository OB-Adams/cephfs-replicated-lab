# OSD replacement, expansion and removal

Milestone 3. Three drills on the disks themselves, the Ceph counterparts of the Gluster lab's milestone 2: an OSD's disk wiped and the OSD rebuilt with the same ID, a third disk added to every server and three new OSDs created from it, and those three drained and removed again. See [milestones.md](milestones.md).

Run on 2026-11-05, times UTC. The client wrote throughout with [../scripts/drill-writer.sh](../scripts/drill-writer.sh), as in milestone 2. Before the drills, 2 GB of random data (100 files of 20 MiB) was written to `/mnt/cephfs/fill` and its checksums recorded, so data movements would last long enough to watch and could be verified afterwards with [../scripts/ceph-check.sh](../scripts/ceph-check.sh).

| Drill | What happened | Gluster counterpart |
|---|---|---|
| 5 | `osd.3`'s disk on `gluster3` wiped, the lost copies rebuilt elsewhere, then a new `osd.3` built on the disk | 2a, `reset-brick` |
| 6 | A 10 GB disk added to every server, then three new OSDs created on them | 2c, `add-brick` and rebalance |
| 7 | The three new OSDs drained and removed | 2b, `replace-brick` |

Ceph has no command to move an OSD's data to another disk, because no OSD owns a fixed share: CRUSH places data from the map. Moving a disk's role is adding one and draining another, which drills 6 and 7 do together. Drill 7 also returned the cluster to the six OSDs of milestones 1 and 2, on the disks the Gluster benchmark used.

## What "degraded" meant here

Every data movement in these drills was reported as **degraded**, including the expansion and the drain, where every copy existed on some OSD throughout. The runbook expected **misplaced** for those, the state Ceph uses when a copy exists but on the wrong OSD.

What the cluster showed instead: when a placement group's new acting set included an OSD that did not yet hold its data, the PG went `active+recovery_wait+degraded`, and the copy that new OSD should hold was counted as missing until recovery filled it (screenshot 07). The old copy, on an OSD that had left the PG's acting set, still existed but no longer counted. Only a few dozen objects were ever reported as misplaced.

So in these drills, "degraded" means "one of the three copies this PG now wants is not yet on its OSD". It did not mean data was at risk: no OSD holding a needed copy was stopped while any PG relied on it. Why Ceph filled the new OSDs by recovery rather than keeping the old OSDs in the acting set and backfilling was not established.

## Drill 5: an OSD's disk lost, and rebuilt with the same ID

**Goal.** Wipe one OSD's disk, see where the lost copies are rebuilt, then put a new OSD with the same ID on the disk and see it take back its place.

**Procedure, as planned.** Pause the OSD spec (`ceph orch set-unmanaged osd.data-disks`); stop `osd.3` and wipe its disk on `gluster3` with `cephadm ceph-volume -- lvm zap --destroy --osd-id 3`; mark it out; when clean, mark it destroyed with `ceph orch osd rm 3 --replace`; resume the spec so the orchestrator builds a new OSD on the empty disk, claiming ID 3.

**Observed.**

| Time | Event |
|---|---|
| 18:58 | Spec paused. `osd.3` on `gluster3`, `/dev/vdc`. `ceph orch daemon stop osd.3` returned `Scheduled to stop osd.3` |
| 19:03:10 | Writer started: 3000 files |
| 19:05:24 | First zap on `gluster3`: `error from zap: (16) Device or resource busy`. `osd.3` was still running: its container `Up 43 minutes`, the volume open 24 times |
| 19:09:19 | `osd.3` stopped with `systemctl stop` on `gluster3`; `marked itself down and dead`. The zap then succeeded |
| 19:09:23 | `2346/15102 objects degraded (15.534%), 69 pgs degraded`: every PG that had a copy on `osd.3` |
| 19:11:00 | `Client client.admin marked osd.3 out, after it was down for 100 seconds` |
| 19:11:14 | `Cluster is now healthy`: the lost copies rebuilt, at up to 87 MiB/s (screenshot 07) |

- **The lost copies were rebuilt on the same host, 14 seconds after the out.** With `osd.3` out but `gluster3` still in the map, CRUSH still chose `gluster3` for each PG's third copy and picked its remaining OSD. `osd.0` then held all 145 PGs, 2.1 GiB, 21% of its disk, while the other four OSDs held about 1 GiB each. In drill 1 the whole host was out and nothing could move; here one disk was lost and its share moved to its neighbour.
- **Between the stop and the out, nothing was rebuilt.** For 100 seconds `osd.3` was down but still in, and its PGs ran with two copies, waiting for it to return, as in drill 1. Marking it out by hand started the rebuild at once, instead of after the 10-minute `mon_osd_down_out_interval`.
- **The client never noticed.** The slowest of the writer's 3000 writes took 0.08 s, during the whole drill.
- **`ceph orch daemon stop` did not stop the OSD.** It was scheduled, and `osd.3` was still running five minutes later. The cause was not established; stopping it with `systemctl` on the host worked.

**Marking it destroyed, and a loop.** `ceph orch osd rm 3 --replace` replied `VG/LV for the OSDs won't be zapped (--zap wasn't passed)`, yet the removal queue listed it with `ZAP True`. `osd.3` became `destroyed`, still under `gluster3` with its CRUSH weight (screenshot 08), and the queue entry stayed at `done, waiting for purge`. With `--replace`, nothing is ever purged.

The spec was then resumed, as planned. From then on, the managed spec and the queue entry undid each other: the orchestrator found `/dev/vdc` empty and prepared a new `osd.3` on it, claiming the destroyed ID, and the queue entry, still set to replace and zap `osd.3`, removed it and zapped the disk again. The cephadm log shows the cycle every four seconds:

```text
Zapping devices for osd.3 on gluster3
osd.3 now down
Daemon osd.3 on gluster3 was already removed
Successfully destroyed old osd.3 on gluster3; ready for replacement
Zapping devices for osd.3 on gluster3
```

None of the OSDs built in the loop ever started, so none held data. Data was never at risk: all 145 PGs stayed `active+clean` on the other five OSDs.

**Untangling it.**

| Time | Step |
|---|---|
| 20:48 | `ceph orch osd rm stop 3` emptied the queue. It also reset `osd.3`: no longer `destroyed`, and marked in again, so it was marked out again at once (20:49:52) |
| 20:53 | `ceph osd destroy 3 --yes-i-really-mean-it`, after `ceph osd safe-to-destroy 3`, so a new OSD could claim ID 3 |
| about 20:58 | On `gluster3`: the leftover `osd.3` daemon, in error state, removed with `cephadm rm-daemon`, and `/dev/vdc` zapped by path |
| 21:00 | The orchestrator prepared a new `osd.3` on `/dev/vdc`, with a new UUID, but deployed no daemon for it |
| 21:05 | `ceph cephadm osd activate gluster3` deployed it; `osd.3` booted at 21:05:18 |
| 21:06:44 | All PGs `active+clean`. The new `osd.3` was filled in 86 seconds, peaking at `2533/22032 objects degraded (11.497%)` |

Afterwards `osd.0` and `osd.3` held 1.2 GiB and 1.0 GiB, back to an even share. The rebuilt `osd.3` belongs to a plain `osd` service, which cephadm creates for OSDs deployed outside a spec, not to `osd.data-disks`.

**What to do instead.** Keep the OSD spec unmanaged until the removal queue is empty and the replacement OSD has been built, and check with `ceph orch ls osd` that it really shows `<unmanaged>`. In this version, `ceph orch osd rm --replace` zaps the disk whether or not `--zap` is given. Stop an OSD with `systemctl` on its host before wiping its disk, and check that its volume's open count in `dmsetup info -c` is 0.

**Checks.** The writer recorded no failures; all 3000 files were correct, the 2 GB fill set matched its checksums and `test10M.bin` its reference checksum.

Evidence: [drill5-cephw.txt](evidence/drill5-cephw.txt), [drill5-session-gluster1.txt](evidence/drill5-session-gluster1.txt), [drill5-session-gluster3.txt](evidence/drill5-session-gluster3.txt), [drill5-session-gluster4.txt](evidence/drill5-session-gluster4.txt), [drill5-writes.log](evidence/drill5-writes.log), screenshots 07 and 08.

## Drill 6: a disk added to every server, then three new OSDs

### 6a: adding the disks

**Goal.** Add a third 10 GB disk to every server. Each VM had to be shut down for UTM to add a drive, so this was planned maintenance: the OSD spec paused so the new disks would not be used straight away, and `ceph osd set noout` so OSDs on a host that was down would not be marked out.

**What was done.** The runbook planned one server at a time, each back and clean before the next. In the run, `gluster3` and `gluster2` were shut down **together**, given their disks and started again, then `gluster1` on its own.

| Time | Event |
|---|---|
| 21:09:20 | `noout flag(s) set` |
| 21:09:44 | Writer started: 2400 files |
| 21:09:53 | `gluster3` and `gluster2` shut down. `osd.0` `marked itself down`. The writer's next write began, and waited |
| 21:09:53 to 21:10:41 | One monitor of three: no quorum. `gluster2`'s OSDs were never marked down, because there was no quorum to record it. `osd.1` reported a metadata-pool write `waiting for sub ops` from 21:10:32 |
| 21:10:41 to 21:10:49 | `gluster2`'s monitor back; quorum of two at 21:10:47, of three at 21:10:49 |
| 21:10:52 to 21:10:53 | All four OSDs of `gluster2` and `gluster3` `boot`. Up to `48 pgs inactive, 37 pgs peering` |
| 21:10:57 | **The waiting write completed, after 64.0 s.** The MDS cleared `1 slow metadata IOs are blocked > 30 secs, oldest blocked for 50 secs` |
| 21:10:58 | Every PG active again |
| about 21:12:25 | `gluster1` shut down: one write of 19.8 s while the other monitors elected `gluster2` (21:12:35 to 21:12:40) and the MDS on `gluster2` took rank 0 (21:12:44) |
| 21:13:02 | `gluster1` back; quorum of three; its OSDs `boot` |
| 21:13:58 | `noout` unset; `Cluster is now healthy` |

- **Two hosts at once is a majority lost, even for maintenance.** `noout` keeps OSDs in; it does nothing for the monitors. With `gluster2` and `gluster3` both down, the cluster was in drill 3's state for about 50 seconds: no quorum, PGs below `min_size`, and the client's request held until a majority was back. It then completed by itself, with no error.
- **One host at a time cost about 20 seconds**, the monitor election and the MDS failover of `gluster1`'s departure.
- `noout` did its job: no OSD was marked out during either outage, so nothing was moved. When the hosts returned, only the writes they had missed were recovered.

The writer recorded no failures in its 2400 writes.

### 6b: three new OSDs

**Procedure.** Add `/dev/vdd` to the OSD spec and apply it: a dry run first, then for real. Applying a spec also makes it managed again.

**Observed.**

| Time | Event |
|---|---|
| 21:59:30 | Writer started: 1200 files |
| 22:02:15 | `osd.6` (`gluster3`), `osd.7` (`gluster1`) and `osd.8` (`gluster2`) `boot`, together |
| 22:02:27 | Peak: `8392/30192 objects degraded (27.795%), 80 pgs degraded` |
| 22:04:13 | `Cluster is now healthy`, **under 2 minutes after the boot** |
| 22:05:05 to 22:05:13 | A second, brief movement: `2 pgs peering`, `81 objects degraded`, then healthy |

- **No rebalance command.** Adding three OSDs added CRUSH weight to every host, every PG was placed again from the new map, and about a third of the copies moved onto the new OSDs by themselves. In the Gluster lab, `add-brick` changed nothing until `rebalance` was run, and its first run skipped 320 files.
- **An even result.** Afterwards the nine OSDs held 720 to 907 MiB and 45 to 54 PGs each, 7.0 to 8.9% full (screenshot 09). The balancer, in `upmap` mode, reported `Unable to find further optimization ... or distribution is already perfect`. The PG autoscaler left the data pool at 128 PGs. The cause of the second, short movement at 22:05 was not established.
- **The client** saw two writes of about 2.3 s and one of 1.1 s as the new OSDs started, and none over 0.1 s otherwise. No failures.

**Checks.** All 2400 drill 6a and 1200 drill 6b files correct; the fill set and the reference file matched.

Evidence: [drill6a-cephw-gluster1.txt](evidence/drill6a-cephw-gluster1.txt), [drill6a-cephw-gluster2.txt](evidence/drill6a-cephw-gluster2.txt), [drill6a-session-gluster1.txt](evidence/drill6a-session-gluster1.txt), [drill6a-writes.log](evidence/drill6a-writes.log), [drill6b-cephw.txt](evidence/drill6b-cephw.txt), [drill6b-session-gluster1.txt](evidence/drill6b-session-gluster1.txt), [drill6b-writes.log](evidence/drill6b-writes.log), [drill6-session-gluster4.txt](evidence/drill6-session-gluster4.txt), screenshot 09.

## Drill 7: drain and remove the new OSDs

**Procedure.** Put the OSD spec back to `/dev/vdb` and `/dev/vdc`, so the orchestrator would not rebuild OSDs on the disks about to be freed; then `ceph orch osd rm 6 7 8 --zap`.

**Observed.**

| Time | Event |
|---|---|
| 22:14:26 | Removal queued for `osd.6`, `osd.7` and `osd.8` |
| 22:14:29 | `osd.7 weight is now 0.0`. Up to `6643/32988 objects degraded (20.138%)` as its copies moved |
| 22:15:36 | `Cluster is now healthy` |
| 22:15:43 to 22:15:47 | `osd.7` stopped, its key removed, purged, its disk zapped |
| 22:15:42 and 22:15:52 | `osd.6`, then `osd.8`, weight 0.0. Up to `8874/33420 objects degraded (26.553%)` |
| 22:15:46 to 22:15:50 | `1 pg inactive, 2 pgs peering` for 4 seconds |
| 22:17:35 | `Cluster is now healthy` |
| 22:17:41 to 22:17:49 | `osd.8` and `osd.6` stopped, purged, their disks zapped |

- **Draining is a CRUSH weight of 0.** cephadm set each OSD's CRUSH weight to 0, not its reweight: the OSDs stayed `in` throughout (`8 in` in `ceph -s`), but CRUSH placed no data on them, so every PG moved its copy elsewhere. Only when an OSD held nothing did the queue stop it.
- **Each OSD was stopped only after the cluster was healthy.** `osd.7` at 22:15:43, after 22:15:36; `osd.6` and `osd.8` at 22:17:41 and 22:17:45, after 22:17:35. `done, waiting for purge` was a step on the way here, lasting two minutes for `osd.6` while `osd.8` drained; in drill 5 it was the end state of a `--replace` entry.
- **Three OSDs out in 3 minutes 20 seconds**, from queuing to the last zap. The OSDs were purged: gone from the map with their keys, unlike drill 5's destroyed `osd.3`.
- **The client** saw one write of 1.9 s, at 22:15:52 as `osd.8`'s drain began, none other over 1 s, and no failures in 1800 writes.

Afterwards the cluster had six OSDs, `0` to `5`, 60 GiB raw, `HEALTH_OK`, and the three `vdd` disks were empty and unused by the spec.

**Checks.** After the drill, all 3000, 2400, 1200 and 1800 files of drills 5 to 7 were correct, the fill set matched and `test10M.bin` matched its reference checksum.

Evidence: [drill7-cephw.txt](evidence/drill7-cephw.txt), [drill7-session-gluster1.txt](evidence/drill7-session-gluster1.txt), [drill7-session-gluster4.txt](evidence/drill7-session-gluster4.txt), [drill7-writes.log](evidence/drill7-writes.log), [m3-checks-session-gluster4.txt](evidence/m3-checks-session-gluster4.txt).

## After the drills: scrub

Both CephFS pools were deep-scrubbed at 22:38:14. All 16 metadata and 128 data PGs were scrubbed after that time; `rados list-inconsistent-pg` returned `[]` for both pools; `HEALTH_OK`.

Evidence: [m3-scrub-session-gluster1.txt](evidence/m3-scrub-session-gluster1.txt).

## Summary

| | Gluster (phase 1) | Ceph (this lab) |
|---|---|---|
| A disk's data lost | Brick rebuilt at the same path with `reset-brick`; heal started only with `heal full`, then took about 26 s | Copies rebuilt on the host's other OSD 14 s after the OSD was marked out; the rebuilt OSD refilled in 86 s; no client stall |
| Replacing the disk's owner | `reset-brick` re-admitted the same brick | `osd rm --replace` kept ID 3 and its CRUSH place; with the spec managed, the orchestrator and the removal queue undid each other until the queue was cleared |
| Expansion | `add-brick` to 2 x 3, then a rebalance that skipped 320 files, then a forced rebalance | Three OSDs added; data spread by itself in under 2 minutes, 45 to 54 PGs per OSD |
| Taking a disk out of service | `replace-brick` to a new disk; heal in about 36 s | Three OSDs drained by CRUSH weight and purged in 3 min 20 s; none stopped before the cluster was healthy |
| Copies compared afterwards | Matching digests on every brick | Deep scrub: no inconsistent PGs |
