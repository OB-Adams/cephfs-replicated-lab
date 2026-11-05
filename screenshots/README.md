# Screenshots

This folder holds screenshots of real terminal output from the lab. Each one is embedded in the [main README](../README.md#screenshots-and-evidence). This file records what each image shows and the commands behind it, so the set can be reproduced.

## Rules

- Capture genuine output from the running lab, live during the run. Never mock up or edit output.
- Make the machine visible: keep the shell prompt (`root@gluster1:~#` and similar) in frame.
- Crop to the relevant output. Prefer a few clear images over many similar ones.
- Check each image for private addresses, keys or personal information before committing. Never capture a keyring's contents.
- Use the exact file names below.
- Screenshot 01 was taken before the client wrote any data, so it shows 3 pools with 3 PGs in all. The PG autoscaler raised that to 145 soon afterwards; see [../docs/deploy.md](../docs/deploy.md#placement-groups).
- Screenshot 02 was taken after `HEX` had been set to the file's inode number in hexadecimal, `10000000001`, so the commands show `$HEX`.
- Screenshot 03 was taken after the drill 1 writer had finished, so `ceph -s` has no `client:` I/O line. The writer's log shows every write during the outage.
- In screenshot 05, the `grep` for `name`, `rank` and `quorum` also matches fields further down the monitor status: the key types (`aes256k`) and the monitor map's three entries. The lines that matter are the first four.
- Screenshot 07 shows the PGs in `recovery_wait`, not `backfilling` as the runbook expected; see [../docs/replacement-expansion.md](../docs/replacement-expansion.md#what-degraded-meant-here).
- The runbook planned a tenth screenshot, of drill 7's drain; it was not taken. The drain's `ceph orch osd rm status` and `ceph -s` output is in `../docs/evidence/drill7-session-gluster1.txt`.

## The set

| File | Machine | What was run | What it shows |
|---|---|---|---|
| `01-ceph-cluster-health.png` | gluster1 | `ceph -s`, `ceph osd tree` | The healthy cluster: three monitors in quorum, six OSDs on three hosts, CephFS with an active and a standby MDS |
| `02-ceph-object-placement.png` | gluster1 | `rados -p cephfs.cephfs.data ls`, `ceph osd map`, `ceph df` | A client file's objects, each placed on three OSDs on three different hosts, and the pool storing three copies |
| `03-drill1-degraded-writes-continue.png` | gluster1 | `ceph -s`, drill 1, gluster3 down for 57 minutes | Two OSDs down and out (`4 up, 4 in`), 40 GiB capacity, every PG `active+undersized`, `2036/6108 objects degraded (33.333%)`, no backfill |
| `04-drill2-write-stall.png` | gluster4 | `sort -k3 -rn ~/drill2a-writes.log \| head -3` and the same for `drill2b` | One write of 25.803 s at the default grace and one of 16.166 s at 10 s, against normal writes of a few hundredths of a second |
| `05-drill3-no-quorum.png` | gluster1 | `timeout 20 ceph -s; echo "exit $?"`, then `ceph --admin-daemon .../ceph-mon.gluster1.asok mon_status \| grep ...`, drill 3 with only gluster1 up | `ceph -s` killed by the timeout (`exit 124`); the monitor `probing` with an empty quorum |
| `06-drill4-mds-failover.png` | gluster1 | `ceph fs status cephfs`, then `grep -iE 'mds\|fsmap' ~/drill4-cephw.txt \| tail -12`, after drill 4's failover | `cephfs.gluster2.stwcqc` active and `cephfs.gluster1.wmvdvt` standby; the monitors' log of the restart, the standby assigned rank 0, and it becoming active 2 s later |
| `07-drill5-backfill.png` | gluster1 | `ceph -s`, drill 5, 8 s after `osd.3` was marked out | `5 up, 5 in`; `985/15687 objects degraded (6.279%)`, 25 PGs `recovery_wait+degraded`; recovery at 87 MiB/s with client writes continuing |
| `08-drill5-osd-destroyed.png` | gluster1 | `ceph osd tree`, after `ceph orch osd rm 3 --replace` | `osd.3` `destroyed`, still under `host gluster3` with CRUSH weight 0.0098 and reweight 0 |
| `09-drill6-nine-osds.png` | gluster1 | `ceph osd df tree`, after drill 6b's data had moved | Nine OSDs, three per host, 90 GiB; 720 to 907 MiB and 45 to 54 PGs per OSD |
