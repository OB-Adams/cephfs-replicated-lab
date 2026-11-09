# cephfs-replicated-lab

A hands-on Ceph lab: a three-node Ceph cluster deployed with `cephadm` on the same Linux VMs and disks that ran the GlusterFS lab, with a CephFS file system mounted on a separate client. The cluster is taken through the same kinds of recorded drills as the Gluster volume (failure, disk replacement, expansion, access control, monitoring and a `fio` benchmark), and the two systems are compared from what was measured.

This is phase 2 of a storage study. Phase 1, the GlusterFS build and its nine drills, is in [glusterfs-replicated-lab](https://github.com/OB-Adams/glusterfs-replicated-lab). Its milestone 6 removed Gluster from the VMs and wiped the data disks, which is where this repository starts.

## Project status

| Item | Status |
|---|---|
| Milestone 1: deploy Ceph and mount CephFS | Complete ([docs/deploy.md](docs/deploy.md)) |
| Milestone 2: failure drills | Complete ([docs/failure-drills.md](docs/failure-drills.md)) |
| Milestone 3: OSD replacement and expansion | Complete ([docs/replacement-expansion.md](docs/replacement-expansion.md)) |
| Milestone 4a: cephx capabilities and encryption on the wire | Complete ([docs/security.md](docs/security.md)) |
| Milestone 4b: monitoring and alerts | Complete ([docs/monitoring.md](docs/monitoring.md)) |
| Milestone 5: `fio` benchmark against the Gluster baseline | Complete ([docs/benchmark.md](docs/benchmark.md)) |
| Milestone 6: Gluster and CephFS comparison | Complete ([docs/comparison.md](docs/comparison.md)) |
| Milestone 7: Ansible automation | In progress: playbooks written and passing `ansible-lint` in CI, not yet run against the lab ([ansible/](ansible)) |
| Raw evidence (session recordings) | Added in [docs/evidence](docs/evidence) |
| Screenshots | Added in [screenshots/](screenshots) |

The full tracker is in [docs/milestones.md](docs/milestones.md). Anything not listed as complete is not implemented.

**The comparison with GlusterFS, area by area, is in [docs/comparison.md](docs/comparison.md).**

## Key results

| Milestone | What happened |
|---|---|
| 1. Deploy | `HEALTH_OK` with 3 monitors, 2 managers, 2 MDS daemons and 6 OSDs on Ceph 20.2.5. A 10 MiB file's chunks traced to different placement groups, each with one copy on every server |
| 1. Deploy | gluster2's OSDs stalled for over half an hour, every attempt stopping at `osd new`, until clock skew of up to 15 s between the monitors was corrected |
| 1. Deploy | A Pacific client left on the VMs could not read the AES-256 admin key the Tentacle monitors created; Tentacle's own client needed EPEL |
| 1. Deploy | After an unattended restart of every VM, the cluster and the client's mount came back healthy by themselves |
| 2. Graceful host loss | Writes continued with two copies. After an hour away, 2036 degraded objects were recovered from PG logs in about 9 s. One write stalled 11.9 s while the monitors re-formed their quorum |
| 2. Hard failure | A silent host stalled the client 25.8 s at the default `osd_heartbeat_grace` of 20 s (Gluster: 70.3 s), and 16.2 s at 10 s, where the monitor election became the limit |
| 2. Majority lost | With two of three hosts down, a write waited 433 s and then completed by itself, with no error and no remount. The Gluster mount failed outright |
| 2. MDS failover | Killing the active MDS stalled metadata for 13.4 s; the standby was active 2 s after taking over |
| 2. Scrub | A deep scrub of both pools after the drills found no inconsistent PGs; all 3800 drill files intact |
| 3. Disk lost | An OSD's disk wiped: its copies were rebuilt on the host's other OSD 14 s after it was marked out, and the client's slowest write was 0.08 s |
| 3. Replacement | `ceph orch osd rm --replace` zapped the disk without `--zap`; with the spec managed, the orchestrator and the removal queue rebuilt and removed the new OSD in a loop until the queue was cleared |
| 3. Expansion | Three new OSDs: data spread by itself in under 2 minutes, 45 to 54 PGs per OSD, no rebalance command |
| 3. Drain | Three OSDs drained by CRUSH weight and purged in 3 min 20 s, none stopped before the cluster was healthy |
| 3. Maintenance | Two of three servers down together for disks lost monitor quorum for 50 s and held a write 64 s, despite `noout` |
| 4a. On the wire | In the default `crc` mode, three test files' contents were read straight from captured client traffic; after switching to `secure`, none of 410 client packets or 4550 server packets contained them |
| 4a. Keys | Forged, unknown, read-only and path-limited keys each refused by the daemon that owns the cap; a wrong key is reported by the kernel as `no mds is up` |
| 4a. Revocation | `ceph auth rm` stopped new mounts only; the open mount worked until its session was evicted |
| 4a. Rolling restart | Every monitor and OSD restarted into secure mode with the client writing and no write over 1.2 s. The MDS failover held one write 51 s, waiting for a revoked client's leftover session |
| 4a. Plaintext clients | An `ms_mode=crc` client refused; an msgr1 (`legacy`) client still mounts, because the mode settings govern msgr2 only |
| 4b. Monitoring stack | Prometheus, Alertmanager, Grafana and the exporters deployed with six `ceph orch apply` commands; 99 alert rules shipped with Ceph, against 5 hand-written for Gluster |
| 4b. Host down | With every Ceph daemon on gluster3 stopped, `CephOSDDownHigh` fired 37 s after the OSDs went down; four alerts reached Alertmanager and the Ceph Dashboard, and resolved after recovery |
| 4b. Blind spots | Alerts built on `OSD_DOWN` cleared once the OSDs were marked out, though still down; one failed scrape of the manager reset every cluster alert; `CephadmDaemonFailed` lasted 8 minutes past recovery, until cephadm's cache refreshed |
| 4b. Mac asleep | The VMs were paused 31 minutes mid-drill. On resume the monitors marked running OSDs down for missed beacons and marked gluster3's out; no data moved, with no third host to move it to |
| 5. Reads | CephFS through the kernel client read faster than Gluster through FUSE: 1,225 against 847 MiB/s (145 %), and 20,396 against 12,260 random 4 KiB IOPS (166 %), 3.1 ms per read against 5.2 |
| 5. Writes | CephFS wrote slower: 140 against 199 MiB/s (70 %), 1,639 against 3,278 random 4 KiB IOPS (50 %), 241 against 322 small files a second (75 %). A 4 KiB write took 39 ms against 18 |
| 5. Conditions | gluster1's clock fell minutes behind four times during the run, its VM starved by a Mac with 27.5 of 36 GiB given to VMs; the writes varied by up to 50 % between runs, the reads by under 2 %. A control on a spare disk matched phase 1 within 10 % |
| 6. Comparison | Ceph recovered, expanded and drained by itself, kept requests through the loss of a majority, and offered finer access control and shipped monitoring; Gluster was simpler, its commands did only what they said, and it was not troubled by clocks |

## Objectives

- Deploy a replicated Ceph cluster and understand each layer: monitors and quorum, OSDs and BlueStore, placement groups and CRUSH, pools, the metadata server and the CephFS client.
- Repeat the Gluster lab's tests on the same hardware, so the differences come from the storage system and not the environment.
- Observe real failure and recovery behaviour instead of describing it from documentation.
- Record what was measured, what surprised me, and what remains unexplained.

## Architecture

```mermaid
flowchart LR
    subgraph clientvm["Client VM"]
        C["gluster4<br/>kernel CephFS client, mounted at /mnt/cephfs<br/>Prometheus, Alertmanager, Grafana"]
    end
    subgraph cluster["Ceph cluster: 3 monitors, 6 OSDs, pools size 3"]
        N1["gluster1<br/>mon (leader), mgr (active), mds (active)<br/>osd.1, osd.2"]
        N2["gluster2<br/>mon, mgr (standby), mds (standby)<br/>osd.4, osd.5"]
        N3["gluster3<br/>mon<br/>osd.0, osd.3"]
    end
    C -->|"cluster maps (monitor), metadata (active MDS), file data (OSDs)"| N1
    C -->|"file data (OSDs)"| N2
    C -->|"file data (OSDs)"| N3
    N1 <-->|"Paxos, heartbeats, replication"| N2
    N2 <-->|"Paxos, heartbeats, replication"| N3
    N1 <-->|"Paxos, heartbeats, replication"| N3
    C -.->|"scrapes metrics: manager, ceph-exporter, node-exporter"| cluster
```

Every host also runs `node-exporter`, `ceph-exporter` and `crash`. `gluster4` is a cephadm host labelled `monitoring`, so the monitoring daemons are placed there, but no monitor, manager, MDS or OSD.

### How it works

- The monitors hold the cluster map and agree on every change by majority (Paxos), so any two of the three keep the cluster running.
- Each OSD owns one whole disk and stores objects on it with BlueStore, with no filesystem in between.
- A client hashes an object's name to a placement group and runs CRUSH on the cluster map to find that group's three OSDs, one per host. Nothing central is asked where data lives.
- A write goes to the placement group's primary OSD, which forwards it to the other two before acknowledging, so the client sends each byte once, where a Gluster client sends it to all three bricks.
- CephFS splits files into 4 MiB objects in a data pool. The MDS serves names, directories and attributes from a metadata pool; it is not in the data path.

The concepts are explained in more depth in [docs/deploy.md](docs/deploy.md#how-ceph-is-put-together).

## Environment

| Item | Value |
|---|---|
| Hypervisor | UTM, virtualization mode (not emulation), on an Apple Silicon Mac |
| Guest architecture | aarch64 |
| Guest OS | CentOS Stream 9 |
| Ceph release | 20.2 "Tentacle": daemons from the `quay.io/ceph/ceph:v20` image (20.2.5), `cephadm` and `ceph-common` 20.2.4 from the CentOS Storage SIG |
| Extra repositories | CRB and EPEL, for libraries Tentacle's client needs |
| Servers | `gluster1`, `gluster2`, `gluster3`, 8 GB RAM each, two 10 GB data disks each (`/dev/vdb`, `/dev/vdc`) |
| Client | `gluster4`, kernel CephFS client (kernel 5.14.0-759) |
| Time | chrony on every VM, one source (`time.google.com`), `makestep 1.0 -1` |

The VMs keep their names from phase 1. The behaviour recorded here applies to this OS release and Ceph version only.

## Configuration

| Name | Value used |
|---|---|
| Daemon placement | Monitors on all three servers; managers and MDS daemons on `gluster1` and `gluster2` |
| OSD spec | [ceph/osd-spec.yml](ceph/osd-spec.yml): `/dev/vdb` and `/dev/vdc` on hosts matching `gluster[1-3]` |
| File system | `cephfs`, pools `cephfs.cephfs.meta` (16 PGs) and `cephfs.cephfs.data` (128 PGs), `size 3 min_size 2` |
| Memory limits | `osd_memory_target` 1.5 GiB with autotune off; `mds_cache_memory_limit` 1 GiB |
| Client identity | `client.gluster4`, from `ceph fs authorize cephfs client.gluster4 / rw` |
| Client files | `/etc/ceph/ceph.conf` (minimal configuration) and `/etc/ceph/ceph.client.gluster4.keyring` (mode 600) |
| Client mount | `gluster4@.cephfs=/  /mnt/cephfs  ceph  noatime,_netdev,ms_mode=secure  0 0` in `/etc/fstab` |
| Messenger | `ms_cluster_mode`, `ms_service_mode`, `ms_client_mode` and the three `ms_mon_*_mode` settings all `secure` (milestone 4a); msgr1 still bound |
| Monitoring | Prometheus (9095), Alertmanager (9093) and Grafana (3000) on `label:monitoring` (gluster4); `node-exporter`, `ceph-exporter` and `crash` on every host; the manager's `prometheus` module (9283). Specs in [ceph/service-specs.yml](ceph/service-specs.yml) |
| Ceph Dashboard | Manager module on 8443 (HTTPS, self-signed), user `admin`; alerts arrive from Alertmanager's `ceph-dashboard` receiver |

## Installation and deployment

The procedure, with the reasoning and the fixes found during the run, is in [docs/deploy.md](docs/deploy.md#procedure). In outline:

1. On each server: remove any older Ceph repository, install Podman, LVM, chrony, `python3-jinja2` and `python3-pyyaml`, enable CRB and EPEL, install `cephadm` from the Tentacle repository, and set chrony to step the clock.
2. On `gluster1`: `cephadm bootstrap` with the host's IPv4 address, then install `ceph-common` 20.2 and set the memory limits.
3. Copy cephadm's SSH key to the other servers, add them with `ceph orch host add`, and place three monitors and two managers.
4. Apply the OSD spec.
5. `ceph fs volume create cephfs`, then `ceph fs authorize` a key for the client.
6. On `gluster4`: install `ceph-common`, copy in the configuration and key, and mount from `/etc/fstab`.

## Verification and testing

On `gluster1`:

```bash
ceph -s
ceph osd tree
ceph fs status cephfs
ceph osd pool ls detail | grep cephfs
ceph time-sync-status
```

Expected: `HEALTH_OK`; three monitors in quorum; two OSDs per host, all `up`; one active and one standby MDS; both pools `size 3 min_size 2`; every monitor's skew below 0.05.

To trace a file, write it on the client and map its objects:

```bash
printf '%x\n' $(stat -c %i /mnt/cephfs/test10M.bin)     # on gluster4: the inode in hex
rados -p cephfs.cephfs.data ls | grep "^$HEX\."          # on gluster1, with HEX set to that value
ceph osd map cephfs.cephfs.data $HEX.00000000
```

## Security considerations

- Ceph keyrings (`ceph.client.admin.keyring` and every `ceph.client.*.keyring`) are the cluster's secrets. They stay on the VMs, are excluded by `.gitignore`, and the one key printed in an error message during the deploy is replaced by `<redacted>` in the evidence.
- The client's key is limited to the `cephfs` file system and its data pools. It cannot read the metadata pool directly, but it can read any file's objects in the data pool through RADOS, bypassing the MDS.
- Every msgr2 connection, client and cluster, is encrypted (`secure` mode, AES-GCM keyed from cephx) since milestone 4a, and msgr2 clients asking for `crc` are refused. **msgr1 is still open:** a client mounting with `ms_mode=legacy` gets an unencrypted connection. See [docs/security.md](docs/security.md#part-5-which-clients-the-cluster-still-accepts).
- Revoking a key takes `ceph auth rm` and evicting each of its sessions from the MDS; deleting the key alone leaves open mounts working.
- Packet captures made during the drills stayed on the VMs.
- The Dashboard is the cluster's admin console; its password is never stored in the repository and is redacted from the evidence. Grafana allows anonymous viewing, and Prometheus and Alertmanager answer over plain HTTP without authentication: acceptable on a lab network, not beyond it.
- The lab runs as root over SSH for convenience. A real deployment should separate administrative access.

## Troubleshooting

Issues actually encountered, with causes and fixes, are in [docs/troubleshooting.md](docs/troubleshooting.md). Highlights:

| Symptom | Where it was seen |
|---|---|
| `cephadm` fails with `No module named 'jinja2'` | Milestone 1, every server |
| Bootstrap fails with `OSError: [Errno 22]` on an `fe80::` address | Milestone 1, gluster1 |
| `ceph -s` on the host: keyring `Malformed input` | Milestone 1, gluster1 |
| `nothing provides libarrow.so.900` when installing `ceph-common` 20.2 | Milestone 1, every VM |
| One host never gets its OSDs; `osd new` waits for ever | Milestone 1, gluster2 |
| `MON_CLOCK_SKEW` after the Mac slept | Milestone 1 |
| `ceph` commands hang with no monitor quorum | Milestone 2, drill 3 |
| An OSD's disk cannot be zapped: `Device or resource busy` | Milestone 3, drill 5 |
| A replacement OSD is rebuilt and removed over and over | Milestone 3, drill 5 |
| An OSD is prepared on a disk but never started | Milestone 3, drill 5 |
| A mount fails with `no mds is up` while the cluster is healthy | Milestone 4a, drill 8 |
| MDS failover stalls clients for about 45 seconds | Milestone 4a, drill 8 |
| The Dashboard has no links to Grafana, Alertmanager or Prometheus | Milestone 4b, drill 9 |
| `CephadmDaemonFailed` stays up after the daemon is running again | Milestone 4b, drill 9 |
| False failures after the Mac sleeps | Milestones 1 and 4b |
| A host VM's clock falls minutes behind, and writes stall | Milestone 5 |

## Repository structure

```text
cephfs-replicated-lab/
├── README.md
├── LICENSE
├── .gitignore
├── .github/workflows/ansible-ci.yml   ansible-lint and syntax checks on every push to ansible/
├── ansible/                   milestone 7: site.yml, verify.yml, teardown.yml and eight roles; see ansible/README.md
├── benchmarks/                the fio kit from phase 1, unchanged, so both systems run the same tests
│   ├── README.md
│   ├── run-bench.sh
│   ├── summarize.py
│   └── fio/                   one job file per workload
├── ceph/
│   ├── osd-spec.yml           the OSD service spec applied in milestone 1
│   └── service-specs.yml      every service spec, exported after milestone 4b
├── docs/
│   ├── deploy.md              milestone 1: concepts, procedure, results and findings
│   ├── failure-drills.md      milestone 2: four failure drills and a deep scrub
│   ├── replacement-expansion.md   milestone 3: an OSD rebuilt, the cluster expanded and shrunk
│   ├── security.md            milestone 4a: cephx keys and caps, msgr2 secure mode
│   ├── monitoring.md          milestone 4b: Prometheus, Alertmanager, Grafana and the Dashboard, and a host-down drill
│   ├── benchmark.md           milestone 5: the fio profiles on CephFS against Gluster, and a control
│   ├── comparison.md          milestone 6: GlusterFS and CephFS compared, area by area
│   ├── milestones.md
│   ├── troubleshooting.md
│   └── evidence/
│       ├── deploy-session-gluster{1,2,3,4}.txt
│       ├── verify-session-gluster{1,2,3,4}.txt
│       ├── drill1-cephw.txt, drill1-writes.log, drill1-session-gluster4.txt, drill1-gluster1-terminal.txt
│       ├── drill2-cephw.txt, drill2a-writes.log, drill2b-writes.log, drill2-session-gluster{1,4}.txt
│       ├── drill3-cephw.txt, drill3-writes.log, drill3-session-gluster{1,4}.txt
│       ├── drill4-cephw.txt, drill4-writes.log, drill4-session-gluster{1,4}.txt
│       ├── drills-scrub-session-gluster1.txt
│       ├── drills-checks-session-gluster{1,4}.txt
│       ├── drill5-cephw.txt, drill5-writes.log, drill5-session-gluster{1,3,4}.txt
│       ├── drill6a-cephw-gluster{1,2}.txt, drill6a-writes.log, drill6a-session-gluster1.txt
│       ├── drill6b-cephw.txt, drill6b-writes.log, drill6b-session-gluster1.txt, drill6-session-gluster4.txt
│       ├── drill7-cephw.txt, drill7-writes.log, drill7-session-gluster{1,4}.txt
│       ├── m3-scrub-session-gluster1.txt, m3-checks-session-gluster4.txt
│       ├── drill8-cephw.txt, drill8-writes.log, drill8-session-gluster{1,2,4}.txt
│       ├── drill9-cephw.txt, drill9-writes.log, drill9-alertlog.txt, drill9-alerts.txt, drill9-rules.txt, drill9-session-gluster{1,4}.txt
│       ├── bench-session-gluster{1,4}.txt, bench-w2-session-gluster4.txt, bench-cephw.txt, bench-w2-cephw.txt, bench-chrony-gluster1.txt
│       └── benchmark/         fio's JSON for every target, with phase 1's copied in, and results.md
├── scripts/
│   ├── drill-writer.sh        the client writer used in the drills: one file per write, with fsync, timed
│   ├── ceph-check.sh          checks the drill files, the 2 GB fill set and the reference file on the client
│   └── ceph-alerts.py         reads Prometheus's alert rules and alerts; `follow` logs every change
└── screenshots/
    ├── README.md
    ├── 01-ceph-cluster-health.png
    ├── 02-ceph-object-placement.png
    ├── 03-drill1-degraded-writes-continue.png
    ├── 04-drill2-write-stall.png
    ├── 05-drill3-no-quorum.png
    ├── 06-drill4-mds-failover.png
    ├── 07-drill5-backfill.png
    ├── 08-drill5-osd-destroyed.png
    ├── 09-drill6-nine-osds.png
    ├── 10-drill8-plaintext-on-wire.png
    ├── 11-drill8-caps-refused.png
    ├── 12-drill8-secure-on-wire.png
    ├── 13-drill8-crc-client-refused.png
    ├── 14-drill9-monitoring-daemons.png
    ├── 15-drill9-prometheus-targets.png
    ├── 16-drill9-alert-rules.png
    ├── 17-drill9-dashboard-healthy.png
    ├── 18-drill9-alertmanager-firing.png
    ├── 19-drill9-dashboard-incident.png
    ├── 20-drill9-alert-timeline.png
    ├── 21-drill9-grafana-incident.png
    ├── 22-bench-direct-io-check.png
    ├── 23-bench-raw-run.png
    ├── 24-bench-cephfs-during-run.png
    ├── 25-bench-cephfs-run.png
    └── 26-bench-results.png
```

## Screenshots and evidence

### The healthy cluster

![ceph -s and ceph osd tree: HEALTH_OK, three monitors in quorum, six OSDs on three hosts](screenshots/01-ceph-cluster-health.png)

### A file's objects and their OSDs

![rados ls, ceph osd map and ceph df: three objects of a 10 MiB file, each on three OSDs on three hosts](screenshots/02-ceph-object-placement.png)

### Drill 1: a host out, writes continuing

![ceph -s with gluster3 down and out: 4 of 6 OSDs in, every PG undersized, a third of the objects degraded, nothing backfilling](screenshots/03-drill1-degraded-writes-continue.png)

### Drill 2: the write stall at two heartbeat graces

![The slowest writes of drill 2: 25.8 s at the default grace, 16.2 s at a grace of 10 s](screenshots/04-drill2-write-stall.png)

### Drill 3: one monitor left, no quorum

![ceph -s timing out and gluster1's monitor reporting state probing with an empty quorum](screenshots/05-drill3-no-quorum.png)

### Drill 4: the standby MDS active

![ceph fs status with gluster2's MDS active and gluster1's as standby, and the cluster log lines of the takeover](screenshots/06-drill4-mds-failover.png)

### Drill 5: a lost OSD's copies rebuilt

![ceph -s after osd.3 was marked out: degraded objects falling, PGs recovery_wait, recovery at 87 MiB/s](screenshots/07-drill5-backfill.png)

### Drill 5: osd.3 destroyed, keeping its place

![ceph osd tree with osd.3 destroyed under host gluster3, its CRUSH weight kept](screenshots/08-drill5-osd-destroyed.png)

### Drill 6: nine OSDs

![ceph osd df tree after the expansion: nine OSDs, three per host, 45 to 54 PGs each](screenshots/09-drill6-nine-osds.png)

### Drill 8: file contents on the wire in crc mode

![tcpdump on the client finding all three marker lines of the test files in its captured traffic](screenshots/10-drill8-plaintext-on-wire.png)

### Drill 8: keys refused

![Mounts refused for a forged key and an unknown name, a write refused for the read-only key, the root refused for the path-limited key, and the metadata pool refused to rados](screenshots/11-drill8-caps-refused.png)

### Drill 8: secure mode, nothing readable

![The mount in ms_mode=secure, 410 captured packets and no marker line found](screenshots/12-drill8-secure-on-wire.png)

### Drill 8: a crc client refused, msgr1 still accepted

![An ms_mode=crc mount refused; prefer-crc and legacy mounts accepted, the legacy one on port 6789](screenshots/13-drill8-crc-client-refused.png)

### Drill 9: the monitoring stack on gluster4

![ceph orch ls and ceph orch ps gluster4: Prometheus, Alertmanager, Grafana and the exporters running](screenshots/14-drill9-monitoring-daemons.png)

### Drill 9: Prometheus's targets

![Nine targets up: the manager's exporter, four ceph-exporters and four node-exporters](screenshots/15-drill9-prometheus-targets.png)

### Drill 9: the alert rules Ceph ships

![99 alert rules in 16 groups, all inactive, with their for-durations](screenshots/16-drill9-alert-rules.png)

### Drill 9: the Ceph Dashboard, healthy

![The Ceph Dashboard: health OK, six OSDs up and in, three monitors in quorum](screenshots/17-drill9-dashboard-healthy.png)

### Drill 9: Alertmanager during the incident

![Alertmanager with four firing alerts grouped by name under the ceph-dashboard receiver](screenshots/18-drill9-alertmanager-firing.png)

### Drill 9: the alerts in the Dashboard

![The Ceph Dashboard's active alerts: CephMonDown, CephMonDownQuorumAtRisk, CephOSDDownHigh and CephadmDaemonFailed, with notifications](screenshots/19-drill9-dashboard-incident.png)

### Drill 9: recovery in the cluster log

![ceph -w: gluster3's OSDs booting, degraded objects falling to none and the cluster healthy again](screenshots/20-drill9-alert-timeline.png)

### Drill 9: the incident in Grafana

![Grafana's PG states panel: PGs undersized and degraded during the incident, a gap while the VMs were paused, then all active+clean](screenshots/21-drill9-grafana-incident.png)

### Benchmark: direct I/O on CephFS

![A 64 MiB O_DIRECT write to CephFS with err= 0, at 68 MiB/s](screenshots/22-bench-direct-io-check.png)

### Benchmark: the control on a spare disk

![run-bench.sh on XFS on gluster1's vdd: 18 runs and the done line](screenshots/23-bench-raw-run.png)

### Benchmark: the cluster under a sequential write

![ceph -s showing 179 MiB/s of client writes and ceph osd perf with every OSD at 110 to 121 ms](screenshots/24-bench-cephfs-during-run.png)

### Benchmark: the CephFS run

![run-bench.sh on /mnt/cephfs/bench: 18 runs and the done line](screenshots/25-bench-cephfs-run.png)

### Benchmark: the summary, before the write re-runs

![summarize.py with gluster-fuse as the baseline: every target's medians and percentages](screenshots/26-bench-results.png)

What each screenshot shows and the commands behind it are in [screenshots/README.md](screenshots/README.md). The session recordings are in [docs/evidence](docs/evidence).

## Licence

MIT. See [LICENSE](LICENSE).
