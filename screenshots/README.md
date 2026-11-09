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
- Milestone 3's runbook planned a screenshot of drill 7's drain; it was not taken. The drain's `ceph orch osd rm status` and `ceph -s` output is in `../docs/evidence/drill7-session-gluster1.txt`. Numbering continues from 10 with milestone 4.
- Screenshots 11 and 13 show the client's commands as pasted, so each block of commands appears before its output.
- Screenshot 13 shows the monitors' private addresses in the mount options, unmasked. The same output is in `../docs/evidence/drill8-session-gluster4.txt` with the addresses masked.
- Screenshots 15 to 19 and 21 are of web pages: Prometheus, the Ceph Dashboard, Alertmanager and Grafana. The browser's address bar and tabs are cropped out of 17 and 21. Screenshot 15 shows the servers' private addresses in the target URLs, unmasked.
- Screenshot 20 shows the end of the cluster log rather than the alert log the runbook planned. The alert log is in `../docs/evidence/drill9-alertlog.txt`.
- Screenshot 21 has a gap from about 18:10 to 18:36: the Mac slept and the VMs were paused, so Prometheus has no samples; see [../docs/monitoring.md](../docs/monitoring.md#recovery).
- Screenshot 24 was taken during the first `seq-write` set, while the cluster was `HEALTH_WARN` with gluster1's clock 261 s behind; see [../docs/benchmark.md](../docs/benchmark.md#how-the-run-went).
- Screenshot 26 shows the summary before the write profiles were run again, so its `cephfs-kernel` write figures are the first set's. The final figures are in `../docs/evidence/benchmark/results.md`.
- In screenshots 23 and 25, the text after `run N of 3` on each progress line is the end of fio's last status line from the previous run.

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
| `10-drill8-plaintext-on-wire.png` | gluster4 | `tcpdump -nn -A -r /root/ceph-drill8-crc.pcap \| grep -o "$MARK line [0-9]" \| sort \| uniq -c`, drill 8, client in `ms_mode=prefer-crc` | All three marker lines of three test files read from the captured client traffic |
| `11-drill8-caps-refused.png` | gluster4 | Mounts with a forged key, an unknown name, the read-only key and the path-limited key; `rados ls` on both CephFS pools | Logins refused with `no mds is up`; the read-only write `Permission denied`; the scoped root mount error 13 and `/scoped` mounted; the data pool listed and the metadata pool `Operation not permitted` |
| `12-drill8-secure-on-wire.png` | gluster4 | `findmnt`, then the same capture search after remounting with `ms_mode=secure` | `ms_mode=secure`; 410 packets, 0 marker lines; the file reading back correctly |
| `13-drill8-crc-client-refused.png` | gluster4 | Mounts with `ms_mode=crc`, `prefer-crc` and `legacy` after the cluster was set to `secure`, then `findmnt -t ceph` | `crc` refused; `prefer-crc` and `legacy` mounted, the `legacy` mount on the monitors' msgr1 port 6789 |
| `14-drill9-monitoring-daemons.png` | gluster1 | `ceph orch ls`, `ceph orch ps gluster4` | The monitoring services placed by `label:monitoring` and on every host; Alertmanager, Grafana, Prometheus, the exporters and `crash` running on gluster4 |
| `15-drill9-prometheus-targets.png` | browser | Prometheus, Status, Target health | Nine targets `UP`: the active manager's exporter, four `ceph-exporter`, four `node-exporter` |
| `16-drill9-alert-rules.png` | gluster4 | `/root/ceph-alerts.py rules \| head -40` | `99 alert rules in 16 groups: 99 inactive`, with their `for` durations |
| `17-drill9-dashboard-healthy.png` | browser | Ceph Dashboard, Multi-cluster, Manage clusters | Before the incident: `OK`, 6 OSDs up and in, 3 monitors in quorum, 1 active and 1 standby manager |
| `18-drill9-alertmanager-firing.png` | browser | Alertmanager, Alerts | Four groups under the `ceph-dashboard` receiver; `CephMonDown` expanded with its description and labels, `CephOSDDownHigh` with its labels |
| `19-drill9-dashboard-incident.png` | browser | Ceph Dashboard, Observability, Alerts | The four active alerts, three critical and one warning, with notifications for `CephadmDaemonFailed` and `CephOSDDownHigh` |
| `20-drill9-alert-timeline.png` | gluster1 | `ceph -w`, after recovery | gluster3's OSDs booting, degraded objects falling to none, `CEPHADM_FAILED_DAEMON` cleared and `Cluster is now healthy` |
| `21-drill9-grafana-incident.png` | browser | Grafana, Ceph - Cluster, PG States | 145 PGs undersized and 143 degraded during the incident, the gap of the pause, then all `active+clean` from 18:45 |
| `22-bench-direct-io-check.png` | gluster4 | `fio --name=direct-check ... --direct=1 --ioengine=libaio` on `/mnt/cephfs/bench` | `err= 0`; 64 MiB written at 68.0 MiB/s with one request in flight |
| `23-bench-raw-run.png` | gluster1 | `./benchmarks/run-bench.sh raw-xfs-vdd /mnt/raw-vdd 3` | The control: 18 runs on XFS on the spare disk, and the `done:` line |
| `24-bench-cephfs-during-run.png` | gluster1 | `ceph -s`, `ceph osd perf` during `seq-write` | The client writing 179 MiB/s; every OSD taking 110 to 121 ms to commit; the cluster `HEALTH_WARN` with clock skew and slow requests |
| `25-bench-cephfs-run.png` | gluster4 | `./benchmarks/run-bench.sh cephfs-kernel /mnt/cephfs/bench 3` | 18 runs on CephFS, the stalled write runs visible in their times and estimates, and the `done:` line |
| `26-bench-results.png` | Mac | `python3 benchmarks/summarize.py ~/Downloads/ceph-m5/results gluster-fuse` | Both tables, before the write re-runs |
