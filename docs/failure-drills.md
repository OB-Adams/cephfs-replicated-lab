# Failure drills

Milestone 2. Four drills against the cluster from milestone 1, the Ceph counterparts of the Gluster lab's drills 1 to 3 plus one Gluster had no equivalent for, and a deep scrub afterwards. Each section states the goal, how it was run, what was observed, and what remains unexplained. Raw output is in [evidence/](evidence). See [milestones.md](milestones.md).

Run on 2026-11-04, times UTC. Conventions: `gluster1` to `gluster3` are the servers, `gluster4` is the client with CephFS mounted at `/mnt/cephfs`. At the start of the session `gluster1` held the monitor leader and the active manager; the MDS roles changed during the drills, as described below.

| Drill | What failed | Gluster counterpart |
|---|---|---|
| 1 | `gluster3`, shut down cleanly, for 61 minutes | Drill 1, graceful node loss |
| 2 | `gluster3`, force-stopped in UTM, twice | Drill 2, hard failure and `network.ping-timeout` |
| 3 | `gluster3`, then `gluster2`: a majority | Drill 3, quorum loss |
| 4 | The active MDS process, killed | none |

Gluster's drill 4, split-brain, has no counterpart. Ceph's monitor quorum and the pools' `min_size` exist so that two halves of the cluster can never both accept writes, and drill 3 tests that directly.

## Measuring the client

Every drill ran [../scripts/drill-writer.sh](../scripts/drill-writer.sh) on `gluster4`: it creates one small file every 0.5 seconds and records when each write started and how long it took. The Gluster lab's writer used `echo "$i" > file`. On the CephFS kernel client that write would land in the client's page cache and return at once, with the data sent to the OSDs later, so it would have measured the cache. This writer writes each file with `dd ... conv=fsync`, which returns only once the data is stored on the OSDs.

A normal write took 0.023 to 0.027 s (the median of each run), and 99% of writes took under 0.041 s.

The cluster log was recorded throughout with `ceph -w`, so each stall in the writer's log can be lined up with what the monitors did at that moment.

## Drill 1: graceful host loss, down and out, recovery

**Goal.** Show that writes carry on with two copies, see what Ceph does after ten minutes with nowhere to put a third copy, and measure how the host catches up.

**Procedure.**

1. Start the writer: 2000 files, from 15:28:49.
2. Shut `gluster3` down from its own shell with `poweroff`.
3. Leave it down past the 10-minute `mon_osd_down_out_interval`, then for most of an hour.
4. Start it again from UTM and watch the placement groups.

**Observed.**

| Time | Event |
|---|---|
| 15:30:45 | `osd.3` and `osd.0` `marked itself down and dead`: a stopping OSD tells the monitors, so nothing had to be detected |
| 15:30:50 to 15:31:02 | **One write took 11.9 s**, the only slow one of the 2000 |
| 15:30:55 to 15:31:00 | The other two monitors held an election and formed a quorum without `gluster3` |
| 15:31:03 to 15:31:07 | `Reduced data availability: 78 pgs peering`, then cleared |
| 15:41:02 | `OSD_DOWN` cleared: the two OSDs had been marked `out`, so they no longer counted as down. Capacity fell from 60 to 40 GiB |
| 15:46:56 | The writer finished: 2000 files, no failures |
| 16:31:35 | `gluster3` started; its monitor rejoined the quorum |
| 16:31:43 | Both OSDs `boot` and were marked `in` again by themselves |
| 16:31:52 | `PG_DEGRADED` cleared: every PG `active+clean` |

- **Writes carried on with two copies.** While `gluster3` was away every PG was `active+undersized+degraded`, and `2036/6108 objects degraded (33.333%)`: every object was missing exactly one of its three copies.
- **"Out" moved nothing.** Marking an OSD out tells CRUSH to place its share of data elsewhere. The CRUSH rule needs each copy on a different host, and with `gluster3` gone only two hosts were left, so there was no valid place for a third copy and no backfill started (screenshot 03). The PGs stayed undersized for the whole hour, and the monitors logged them as `stuck undersized` every ten minutes.
- **The host caught up in about 9 seconds.** After an hour away, `gluster3`'s OSDs were brought up to date from each PG's log, which still covered the few writes each PG had received while they were away: this was **recovery**, copying only the changed objects, not **backfill**. `ceph -s` showed `recovery: 247 objects/s` 10 seconds after the OSDs came up. When `gluster3` returned, its monitor's clock was 0.35 s off; chrony stepped it and the warning cleared within 30 seconds.
- **The 11.9 s write.** The OSDs had marked themselves down at 15:30:45, and the next nine writes were normal. The slow write began at 15:30:50, as `gluster3`'s monitor stopped, and ended at 15:31:02, two seconds after the election among the remaining monitors finished. It lines up with the election, not with the OSDs. What exactly the write was waiting on was not established; the likely factor is that the monitors cannot commit any change to the cluster maps while they are without a quorum, and a placement group re-peering after a map change needs the monitors to record it before it can accept writes again. The same 10-second stall appeared when `gluster3` was shut down in drill 3, again lined up with an election.

Before the drill, at 15:10, `gluster3`'s two OSDs had logged that the monitors marked them down while they were still running. They were up again by the time the drill started from `HEALTH_OK`; the cause was not established.

Evidence: [drill1-cephw.txt](evidence/drill1-cephw.txt), [drill1-writes.log](evidence/drill1-writes.log), [drill1-session-gluster4.txt](evidence/drill1-session-gluster4.txt), [drill1-gluster1-terminal.txt](evidence/drill1-gluster1-terminal.txt), screenshot 03.

## Drill 2: hard failure and `osd_heartbeat_grace`

**Goal.** Measure what a client experiences when a host disappears without telling anyone, and whether a shorter `osd_heartbeat_grace` shortens it.

**Procedure.**

1. Run A, at the default grace of 20 seconds: start the writer (400 files), force-stop `gluster3` in UTM, wait for the writer to finish, start `gluster3` and wait for `HEALTH_OK`.
2. Set `ceph config set global osd_heartbeat_grace 10`, and repeat as run B.
3. Remove the setting with `ceph config rm global osd_heartbeat_grace`.

**Observed.**

| Run | `osd_heartbeat_grace` | OSDs marked down after | Longest write | Typical write |
|---|---|---|---|---|
| A | 20 s (default) | 24.7 s | **25.8 s** | 0.025 s |
| B | 10 s | 14.0 s | **16.2 s** | 0.023 s |

The "marked down after" figures are from the monitors' own log line, for example `osd.0 failed (root=default,host=gluster3) (2 reporters from different host after 24.653650 >= grace 20.000000)`. In each run exactly one write was slow, and it completed about 2 seconds after the OSDs were marked down. No write failed (screenshot 04).

- **A silent host has to be detected.** OSDs check on each other with heartbeats every 6 seconds; an OSD that has heard nothing from a peer for longer than the grace reports it, and the monitors mark it down once OSDs on two different hosts have reported it. Each write waited for that, then for its PG to re-peer without the dead OSD. With three hosts every PG has a copy on `gluster3`, so any write in that window would have waited.
- **Detection takes longer than the grace.** In run A it took 24.7 s against a grace of 20: the heartbeat interval means a peer is checked only every few seconds, so the silence has already lasted some time before a check finds it overdue.
- **In run B the monitors were the limit.** `gluster3` also ran a monitor, and its loss started an election from 16:56:07.8 to 16:56:12.8. The OSD reports were due at about 10 seconds, during the election, and the OSDs were marked down 0.06 s after it ended: 14.0 s in all. In run A the election ended at 16:47:34, long before the 20-second reports arrived, so it made no difference. With a monitor on every OSD host, a grace shorter than the monitors' own failure detection and election (about 10 + 5 seconds here) no longer shortens the stall.
- **Recovery** after each return took 3.6 and 5.3 seconds, for 2436 and 2837 degraded objects.

**Compared with Gluster.** Gluster's drill 2 measured 70.3 s at its default `network.ping-timeout` of 42 s, and 13.2 s at 10 s. Ceph's default detection is about a third of Gluster's default. At a 10-second setting, Gluster's stall was shorter, because a Gluster client detects a dead brick by itself, while a Ceph OSD has to be reported by peers on two hosts and marked down by the monitors.

**Trade-off.** A short grace shortens the stall, but makes it more likely that a busy or briefly unreachable OSD is marked down by mistake. Each wrong mark-down makes every PG on it re-peer, and an OSD flapping up and down repeatedly causes far more disruption than one slow failure. The default is deliberately conservative.

Evidence: [drill2-cephw.txt](evidence/drill2-cephw.txt), [drill2a-writes.log](evidence/drill2a-writes.log), [drill2b-writes.log](evidence/drill2b-writes.log), [drill2-session-gluster1.txt](evidence/drill2-session-gluster1.txt), [drill2-session-gluster4.txt](evidence/drill2-session-gluster4.txt), screenshot 04.

## Drill 3: a majority lost

**Goal.** See what a client experiences with only one of three hosts left, and whether it recovers by itself.

**Procedure.**

1. Start the writer: 600 files.
2. Shut `gluster3` down, wait, then shut `gluster2` down, both with `poweroff`.
3. With only `gluster1` up, ask the monitors for the cluster state, and ask `gluster1`'s monitor directly through its admin socket.
4. Start `gluster2`, then `gluster3`, and wait for `HEALTH_OK`.

At the start of this drill the active MDS was on `gluster2` and the standby on `gluster1`.

**Observed.**

| Time | Event |
|---|---|
| 17:11:13 | `gluster3`'s OSDs down |
| 17:11:18 to 17:11:28 | One write took 10.1 s; the remaining monitors held an election from 17:11:22 to 17:11:27 |
| 17:12:04 | `gluster2` shut down. Its MDS was the active one: `gluster1`'s standby was assigned rank 0 straight away. `gluster2`'s OSDs marked themselves down |
| 17:12:04.8 | **The writer's next write began, and did not return** |
| 17:12:04 to 17:19:08 | No quorum: one monitor of three. Nothing could be logged to the cluster log |
| 17:19:08 | `gluster2`'s monitor back; quorum of two |
| 17:19:15 | `gluster2`'s OSDs `boot` |
| 17:19:16 | `gluster1`'s MDS `now active in filesystem cephfs as rank 0` |
| 17:19:17.8 | **The stuck write completed, after 433 s, with no error**, and the writer carried on |
| 17:20:04 to 17:20:13 | `gluster3` back; two writes of 2.8 s and 1.0 s while its OSDs rejoined |

- **The monitors.** With one monitor left, `ceph -s` waited and was killed by `timeout` (`exit 124`). `gluster1`'s monitor, asked through its admin socket, reported `"state": "probing"` and `"quorum": []` (screenshot 05): a monitor without a majority keeps looking for its peers and will not act on its own. When quorum returned, it reported `1571 slow ops, oldest one blocked for 423 sec`: the requests it had been holding.
- **The data.** With two hosts down every PG had one copy left, below `min_size 2`, so the OSDs would not accept I/O. Nothing returned an error; requests were held.
- **The file system.** The standby MDS on `gluster1` took rank 0 the moment `gluster2` left, but could not become active: to take over it must replay the journal from the metadata pool, whose PGs were not accepting I/O, and it needs the monitors to record each change of its state. It became active nine seconds after quorum returned, and the stuck write finished one second later.
- **The client.** Its kernel log ([drills-checks-session-gluster4.txt](evidence/drills-checks-session-gluster4.txt)) shows it losing its monitor session at 17:12:04 and hunting for another every few seconds for the whole outage: `gluster1`'s monitor accepted the connection and then closed it each time, and the other two refused. At 17:17:15 it logged `No mds server is up or the cluster is laggy`. When the cluster returned: `mds0 reconnect start`, `reconnect success`, then at 17:19:17 `caps stale`, `caps renewed`, `recovery completed`. Its capabilities had expired during the outage and were renewed, not revoked.
- **No eviction.** The outage lasted seven minutes, longer than the 300-second `mds_session_autoclose` after which an MDS evicts a client that has stopped renewing its session. The client was not evicted. The likely reason is that no MDS was active during the outage to enforce the timeout; this was not tested further.
- **The data was intact.** All 600 files checked correct, and the reference checksum of `test10M.bin` was unchanged.

**Compared with Gluster.** In the Gluster lab's drill 3, losing client quorum made the whole mount fail: reads and writes returned `Transport endpoint is not connected`, a new mount failed, and the old mount was unmounted and mounted again once a second server was back. Here nothing failed: the client's request waited for seven minutes, then completed by itself once a majority was back, with no remount and no lost write. Gluster stops the client with errors; Ceph makes it wait.

**Why it matters.** With one host left, Ceph could not know whether the other two had accepted writes it had missed, or whether they were still running on the other side of a network split. Refusing to serve below `min_size` and without a monitor majority is what makes it impossible for two halves to diverge. Waiting instead of failing means applications see a pause rather than errors, but also that a process can hang for as long as the outage lasts.

Evidence: [drill3-cephw.txt](evidence/drill3-cephw.txt), [drill3-writes.log](evidence/drill3-writes.log), [drill3-session-gluster1.txt](evidence/drill3-session-gluster1.txt), [drill3-session-gluster4.txt](evidence/drill3-session-gluster4.txt), [drills-checks-session-gluster4.txt](evidence/drills-checks-session-gluster4.txt), screenshot 05.

## Drill 4: MDS failover

**Goal.** Measure how long file operations are blocked when the active MDS dies, and watch the standby take over.

**Procedure.**

1. Confirm the active MDS: `cephfs.gluster1.wmvdvt`, with `cephfs.gluster2.stwcqc` as standby.
2. Start the writer: 400 files.
3. Kill the active MDS's container with `podman kill --signal KILL`, so it could not hand over cleanly.

**Observed.**

| Time | Event |
|---|---|
| about 17:32:55 | Active MDS killed. The writer's next write, at 17:32:55.5, waited |
| 17:32:57 to 17:33:03 | The client's connection to the MDS on `gluster1` closed, three times, as it retried |
| 17:33:05.70 | `daemon mds.cephfs.gluster1.wmvdvt restarted`, `1 filesystem is offline` |
| 17:33:05.72 | `Standby daemon mds.cephfs.gluster2.stwcqc assigned to filesystem cephfs as rank 0` |
| 17:33:06 | Client: `mds0 reconnect start`, `reconnect success` |
| 17:33:07.80 | `mds.cephfs.gluster2.stwcqc is now active` |
| 17:33:08.9 | **The write completed, after 13.4 s.** Client: `mds0 recovery completed` |

- **The restart triggered the failover.** The monitors did not wait for the active MDS's beacons to stop for 15 seconds (`mds_beacon_grace`). systemd restarted the killed container about 10 seconds later, and when the new instance of the old MDS reported to the monitors, they recognised the active one was gone, logged it as `restarted`, and gave rank 0 to the standby at once. If the host itself had died, the failover would have waited for the beacon grace.
- **The takeover took 2 seconds.** `gluster2`'s MDS went from rank 0 assigned to active in 2.1 seconds: replaying the journal, waiting for the client to reconnect and report its caps, and rebuilding its cache. The client reconnected within a second of being told.
- **The old MDS became the standby** (screenshot 06). The roles stayed swapped: `gluster2` active, `gluster1` standby.
- Only metadata operations go through the MDS, but the writer creates a new file every time, so each of its writes needed one. A process writing to a file it already had open would have kept going, because file data goes straight to the OSDs.

Evidence: [drill4-cephw.txt](evidence/drill4-cephw.txt), [drill4-writes.log](evidence/drill4-writes.log), [drill4-session-gluster1.txt](evidence/drill4-session-gluster1.txt), [drill4-session-gluster4.txt](evidence/drill4-session-gluster4.txt), screenshot 06.

## After the drills: scrub and file checks

A **deep scrub** reads every object of a PG on each of its OSDs, checksums the data, and compares the copies: the counterpart of the Gluster lab's digest comparison across bricks. Both CephFS pools were deep-scrubbed after drill 4.

| Check | Result |
|---|---|
| Deep scrub | All 16 metadata and 128 data PGs scrubbed after 17:37:56; `rados list-inconsistent-pg` returned `[]` for both pools; `HEALTH_OK` |
| Files | `drill1` 2000, `drill2a` 400, `drill2b` 400, `drill3` 600, `drill4` 400: every file present with the right contents |
| Failures | No `FAIL` in any writer log |
| Reference file | `test10M.bin` SHA-256 `04e8ee19...86aa6`, unchanged from milestone 1 |

Evidence: [drills-scrub-session-gluster1.txt](evidence/drills-scrub-session-gluster1.txt), [drills-checks-session-gluster1.txt](evidence/drills-checks-session-gluster1.txt), [drills-checks-session-gluster4.txt](evidence/drills-checks-session-gluster4.txt).

## Summary

| | Gluster (phase 1) | Ceph (this lab) |
|---|---|---|
| Graceful loss of one server | Writes continued | Writes continued; one write of 11.9 s while the monitors re-formed their quorum |
| Hard failure, default setting | 70.3 s stall (`network.ping-timeout` 42 s) | 25.8 s stall (`osd_heartbeat_grace` 20 s) |
| Hard failure, 10 s setting | 13.2 s | 16.2 s, limited by the monitor election |
| Two of three servers lost | Mount failed, reads included; remounted to recover | Requests held for 7 minutes, then completed by themselves; no errors, no remount |
| Catching up after a return | 273 pending entries healed with no commands | 2036 objects recovered from PG logs in about 9 s, after an hour away |
| Metadata service lost | No equivalent | 13.4 s stall; standby active 2 s after taking over |
| Copies compared afterwards | Matching digests on every brick | Deep scrub: no inconsistent PGs |
