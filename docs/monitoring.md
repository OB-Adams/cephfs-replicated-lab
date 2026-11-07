# Monitoring and alerts

Milestone 4b, drill 9: the Ceph counterpart of the Gluster lab's milestone 3b. Ceph's own monitoring stack was deployed with `cephadm`, its daemons on `gluster4`, and the Ceph Dashboard was turned on. Then every Ceph daemon on `gluster3` was stopped while the client wrote, and the alerts were followed from Prometheus to Alertmanager and the Dashboard, and back to resolved.

Run on 2026-11-07, times UTC. See [milestones.md](milestones.md).

The Mac slept during the incident. The VMs were paused for 31 minutes in the middle of it, and the drill records what that did to the cluster and to the monitoring as well as what it was meant to show.

## What was deployed

| Daemon | Where | Port | Image |
|---|---|---|---|
| The manager's `prometheus` module | Inside the active manager | 9283 | The Ceph image, 20.2.5 |
| The Ceph Dashboard (manager module) | Inside the active manager | 8443, HTTPS | The Ceph image |
| `ceph-exporter` | Every host | 9926 | The Ceph image |
| `node-exporter` | Every host | 9100 | `quay.io/prometheus/node-exporter:v1.9.1` |
| Prometheus | `gluster4` | 9095 | `quay.io/prometheus/prometheus:v3.6.0` |
| Alertmanager | `gluster4` | 9093 | `quay.io/prometheus/alertmanager:v0.28.1` |
| Grafana | `gluster4` | 3000, HTTPS | `quay.io/ceph/grafana:12.3.1` |

All four images pulled for arm64 without a substitute. The specs, exported after the drill, are in [../ceph/service-specs.yml](../ceph/service-specs.yml).

### Where the metrics come from

Prometheus pulls: every 15 seconds or so it fetches `/metrics` from each target and stores each number with its labels. Ceph has three kinds of target:

- **The manager's exporter** reports the cluster as a whole: health and each health check (`ceph_health_detail{name="OSD_DOWN"}`), each OSD's up and in state, PG states, pool usage, monitor quorum, MDS and file system state. Only the active manager serves it. cephadm's service discovery lists only that one endpoint, so Prometheus showed a single `ceph` target, `gluster2:9283` at the time of screenshot 15.
- **`ceph-exporter`**, one per host, reads the performance counters of the Ceph daemons on its host from their admin sockets.
- **`node-exporter`**, one per host, reports the host itself: CPU, memory, disks, network.

Prometheus showed nine targets, all `UP`: one `ceph`, four `ceph-exporter`, four `node` (screenshot 15).

The Gluster lab had no Gluster exporter, so it wrote one: a script turning `gluster volume status` and `heal info` into metrics for node-exporter's textfile collector. Ceph ships its exporters.

### The alert rules ship with Ceph

cephadm loaded **99 alert rules in 16 groups**, all `inactive` before the incident (screenshot 16, [drill9-rules.txt](evidence/drill9-rules.txt)). They come from Ceph's container image and cover cluster health, monitors, OSDs, PGs, MDS and CephFS, pools, hosts, hardware, cephadm, NVMe-oF and RBD mirroring. The Gluster lab had five, written by hand.

A rule is a PromQL expression evaluated every 15 seconds:

- While the expression returns nothing, the alert is *inactive*.
- When it starts returning something, the alert is *pending*.
- If it keeps returning something for the rule's `for` duration, the alert *fires*, and Prometheus sends it to Alertmanager.
- When the expression returns nothing again, the alert *resolves*.

The rules that took part in the drill:

| Rule | `for` | Built on |
|---|---|---|
| `CephOSDDownHigh` | 0 s | `ceph_osd_up`: 10 % or more of the OSDs down |
| `CephMonDown` | 30 s | The `MON_DOWN` health check |
| `CephMonDownQuorumAtRisk` | 30 s | `MON_DOWN` with exactly a bare majority in quorum |
| `CephadmDaemonFailed` | 30 s | The `CEPHADM_FAILED_DAEMON` health check |
| `CephMgrPrometheusModuleInactive` | 60 s | `up{job="ceph"} == 0`: the manager's exporter not scraped |
| `CephOSDDown`, `CephOSDHostDown` | 300 s | The `OSD_DOWN` and `OSD_HOST_DOWN` health checks |
| `CephPGsInactive` | 300 s | PGs not active |
| `CephHealthWarning`, `CephPGsUnclean` | 900 s | `HEALTH_WARN`; PGs not clean |

### Alertmanager and the Dashboard

cephadm configures Alertmanager with one receiver, `ceph-dashboard`, a webhook into the Dashboard. Alertmanager groups the alerts by name and forwards them, and the Dashboard lists them under **Observability → Alerts** and pops up a notification for each. Grafana runs with anonymous viewing, so the dashboards cephadm provisions can be read without logging in, and the Dashboard embeds some of them.

## Setting it up

**gluster4 as a cephadm host.** cephadm's SSH key went to `gluster4` through the Mac, as for the other servers in milestone 1. `ceph cephadm check-host` reported Podman, LVM, chrony and the hostname all present, and `gluster4` was added with the label `monitoring`. Within a minute cephadm placed `crash` on it, as on every host, and nothing else. The OSD spec stays limited to `gluster[1-3]`, and the monitors, managers and MDS have explicit host lists, so `gluster4` is still only a client to the cluster.

**The stack.** `ceph mgr module enable prometheus`, then `ceph orch apply` for node-exporter and ceph-exporter on `*` and for Prometheus, Alertmanager and Grafana on `label:monitoring`. Every daemon was running within a minute (screenshot 14). Enabling a manager module restarts the active manager, which the cluster log recorded each time (`Active manager daemon gluster2.qhtcrw restarted`).

**Firewall.** cephadm opened the ports of the daemons it deployed: 9100, 9283, 9926 and 8765 (service discovery) on the servers, and 3000, 9093, 9094, 9095, 9100 and 9926 on `gluster4`. The Dashboard's 8443 was not opened, because the Dashboard is a manager module, not a daemon cephadm deploys; it was added by hand.

**The Dashboard.** `ceph mgr module enable dashboard`, a self-signed certificate, and an `admin` user whose password was read from a file. The Dashboard showed `HEALTH_OK` with every OSD, monitor and manager up (screenshot 17).

The Dashboard's links to Grafana, Alertmanager and Prometheus (`get-grafana-api-url` and the rest) came back **empty**. cephadm sets them when it deploys or reconfigures those three services, and the dashboard module was enabled after they had been deployed. `ceph orch reconfig` for each of the three set them to `https://gluster4:3000`, `http://gluster4:9093` and `http://gluster4:9095`. The Grafana address for the browser was set to `gluster4`'s IP address, since the Mac does not resolve the VM names.

**A pause during setup.** Between about 16:40 and 17:33 by gluster1's clock, the Mac slept and the VMs were paused for about 40 minutes. When they resumed, their clocks were stepped back to the right time at different moments, and for about five minutes the monitors saw each other's messages stamped 2406 s apart. The cluster recorded the gap as failures:

- the active MDS on `gluster2` was replaced by `gluster1`'s;
- the active manager moved from `gluster2` to `gluster1`;
- `mon.gluster2` built up 1346 slow requests, and `MON_CLOCK_SKEW` was raised;
- `osd.0` and `osd.3` were marked down "after no beacon for 2457 seconds" and booted again.

It all cleared by itself, `HEALTH_OK` at 17:33:27, and the drill started from there. The active MDS and manager stay on `gluster1`.

## The incident

At about 18:01:05, `systemctl stop ceph-<fsid>.target` on `gluster3` stopped `mon.gluster3`, `osd.0`, `osd.3` and that host's `crash`, `node-exporter` and `ceph-exporter`. The client's writer had started at 18:00:12, writing one file with `fsync` every half second. There is no recording from `gluster3`; the stop is placed by the cluster log.

**Before the pause** ([drill9-cephw.txt](evidence/drill9-cephw.txt), [drill9-alertlog.txt](evidence/drill9-alertlog.txt), [drill9-alerts.txt](evidence/drill9-alerts.txt)):

| Time | Cluster | Prometheus and Alertmanager |
|---|---|---|
| 18:01:07 | `2 osds down`, `1 host (2 osds) down` | |
| 18:01:16 to 18:01:21 | Election; quorum `gluster1,gluster2`; `MON_DOWN` | |
| 18:01:26 | `14380/43140 objects degraded (33.333%), 143 pgs degraded` | |
| 18:01:42 | | `CephMonDown`, `CephMonDownQuorumAtRisk` pending |
| 18:01:44 | | `CephOSDDownHigh` **firing** (`for: 0`); `CephOSDDown`, `CephOSDHostDown` pending; `CephHealthWarning`, `CephPGsUnclean` pending |
| 18:01:58 | `CEPHADM_FAILED_DAEMON`: `node-exporter.gluster3` in error | |
| 18:02:08 | | `CephadmDaemonFailed` pending |
| 18:02:12 | | `CephMonDown`, `CephMonDownQuorumAtRisk` **firing** |
| 18:02:38 | | `CephadmDaemonFailed` **firing** |

- **Detection took 21 to 37 seconds.** The monitors had the OSDs down at 18:01:07 and the monitor out of quorum at 18:01:21; Prometheus first saw them at 18:01:44 and 18:01:42. That is the manager's exporter refreshing, a scrape and a rule evaluation, one after another.
- **Four alerts fired and reached Alertmanager**, each under the `ceph-dashboard` receiver, with `startsAt` 18:01:44, 18:02:12, 18:02:12 and 18:02:38. The Dashboard showed the same four, critical in red with one warning, and popped up notifications (screenshots 18 and 19).
- **The rules with longer `for` durations stayed pending**, as their durations said they would: 300 s for `CephOSDDown` and `CephOSDHostDown`, 900 s for `CephHealthWarning` and `CephPGsUnclean`.
- **`node-exporter.gluster3` went into `error`** rather than `stopped` when its unit was stopped, which raised `CEPHADM_FAILED_DAEMON` and so `CephadmDaemonFailed`, an alert the drill had not expected.
- **The client** had one slow write: 11.6 s from 18:01:12, ending as the election finished. Milestone 2 measured 11.9 s when a host took its monitor away.

**The pause.** The writer's last write before the gap started at 18:05:19; its next started at 18:36:30, 1870.7 s later. Every VM, `gluster4` included, was paused while the Mac slept. Paused guests count no time, so the stall does not appear in any write's duration; it shows only as the gap.

**After the pause:**

| Time | Cluster | Prometheus |
|---|---|---|
| 18:36:30 | The VMs resume | |
| 18:36:33 to 18:36:53 | | Most alerts drop out and come back as pending; `PrometheusJobMissing` pending; `CephOSDDownHigh` firing again |
| 18:37:09 | `osd.4` and `osd.5` (gluster2, running throughout) marked down "after no beacon for 2140 seconds"; `osd.0` and `osd.3` **marked out**, "down for 2146 seconds" | |
| 18:37:10 to 18:37:13 | `osd.4` and `osd.5` boot again; 140 PGs peering; `OSD_DOWN` and `OSD_HOST_DOWN` **cleared** | |
| 18:37:23 | | Every alert gone but `CephMgrPrometheusModuleInactive` pending; back 10 s later |
| 18:38:03 | | `CephMonDown`, `CephMonDownQuorumAtRisk`, `CephadmDaemonFailed` firing again |
| 18:43:14 | | The same again: every alert but `CephMgrPrometheusModuleInactive` gone for 5 s |
| 18:43:49 | | The monitor and cephadm alerts firing again |

- **The monitors counted the pause as silence.** When gluster1's clock was stepped forward, the monitor saw gluster2's OSDs as having sent no beacon for 35 minutes, marked them down, and they booted again within four seconds. The client's write at 18:37:09 took 5.2 s while 140 PGs peered.
- **The 10-minute out interval had passed by the monitors' clock**, so `osd.0` and `osd.3` were marked out. No data moved: the CRUSH rule puts each copy on a different host, and with `gluster3` gone there is no third host to copy to. The PGs stayed `active+undersized+degraded`.
- **Marking the OSDs out cleared `OSD_DOWN`** although they were still down. The health check counts only OSDs that are down and in, so `CephOSDDown` and `CephOSDHostDown`, built on it, dropped out without firing. Only `CephOSDDownHigh`, built on `ceph_osd_up`, kept saying that two OSDs were down.
- **One failed scrape of the manager's exporter reset every Ceph alert.** Twice, Prometheus got nothing from `gluster1:9283` for one scrape. All the `ceph_*` series vanished, so every alert built on them went inactive, and `CephMgrPrometheusModuleInactive` went pending in their place. When the next scrape succeeded, the alerts started again as pending, with their `for` clocks back at zero. Every cluster-level alert depends on that one target. Why the two scrapes failed was not recorded; both came after the pause, while the manager was catching up.

## Recovery

Shortly before 18:44:42, `systemctl start` of the same target on `gluster3`.

| Time | Cluster | Prometheus |
|---|---|---|
| 18:44:42 | `MON_DOWN` cleared, three monitors in quorum | |
| 18:44:49 | `osd.0` and `osd.3` boot and are marked in | |
| 18:44:59 | | The monitor alerts resolved |
| 18:45:00 | `PG_DEGRADED` cleared: from 15740 degraded objects to none in 11 s, only the objects written while `gluster3` was away needing a copy | |
| 18:45:14 | | `CephOSDDownHigh` resolved |
| 18:52:41 | `CEPHADM_FAILED_DAEMON` cleared after `ceph orch ps gluster3 --refresh`; `HEALTH_OK` | `CephadmDaemonFailed` resolved |

The client's writes at 18:44:50 and 18:44:52 took 1.9 s and 1.1 s as the OSDs rejoined. The writer finished at 18:45:03; all 1500 writes returned `ok`.

**`CephadmDaemonFailed` outlived the failure by eight minutes.** Every daemon on `gluster3` had been running since about 18:44:40, but cephadm's daemon list is a cache, refreshed every ten minutes or so. Until it was refreshed, `ceph orch ps` still showed the old states (`stopped`, and `error` for node-exporter, "refreshed 15m ago"), and the health check and the alert built on it stayed up. `ceph orch ps gluster3 --refresh` showed everything `running (8m)`, and the warning cleared; the end of the cluster log, from the OSDs' return to `Cluster is now healthy`, is screenshot 20.

Prometheus's alert list was empty afterwards, and so were Alertmanager and the Dashboard's active alerts.

**What Grafana shows.** The **Ceph - Cluster** dashboard's PG states panel (screenshot 21) shows 145 PGs undersized and 143 degraded from 18:01, a gap, a second block from 18:36:30 to 18:45, then all 145 `active+clean`. The gap is the pause: Prometheus has no samples from 18:05:20 to 18:36:30. A series is drawn for up to five minutes after its last sample, so the first block runs on to about 18:10.

## Checks

Afterwards: `HEALTH_OK`, six OSDs up and in, 145 PGs `active+clean`, every service at full count. All 1500 writes of the drill returned `ok`. The file check (`ceph-check.sh`) was not run in this session.

The Dashboard password was read into a file for one command, but the file was then printed with `cat` twice in the recording and left on `gluster1`. It is redacted from the evidence.

Evidence: [drill9-session-gluster1.txt](evidence/drill9-session-gluster1.txt), [drill9-session-gluster4.txt](evidence/drill9-session-gluster4.txt), [drill9-cephw.txt](evidence/drill9-cephw.txt), [drill9-writes.log](evidence/drill9-writes.log), [drill9-alertlog.txt](evidence/drill9-alertlog.txt), [drill9-alerts.txt](evidence/drill9-alerts.txt), [drill9-rules.txt](evidence/drill9-rules.txt). The alert log comes from [../scripts/ceph-alerts.py](../scripts/ceph-alerts.py).

## Summary

| | Gluster (phase 1) | Ceph (this lab) |
|---|---|---|
| Exporter for the storage system | Written for the lab: a script feeding node-exporter's textfile collector every 30 s | Shipped: the manager's exporter and `ceph-exporter` |
| Alert rules | 5, written by hand | 99, shipped with Ceph and loaded by cephadm |
| Deployment | Prometheus and Grafana containers run by hand on `gluster4`, configuration files written for them | `ceph orch apply`; cephadm writes the configuration, discovers the targets and opens the ports |
| Notification | None: Prometheus's alert page and the dashboard only | Alertmanager, forwarding to the Ceph Dashboard |
| The drill | One brick killed | Every Ceph daemon on one host stopped |
| Alerts fired | `GlusterBrickDown`, `GlusterHealBacklog` | `CephOSDDownHigh`, `CephMonDown`, `CephMonDownQuorumAtRisk`, `CephadmDaemonFailed` |
| What the monitoring got wrong | | Alerts built on `OSD_DOWN` cleared once the OSDs were marked out; one failed scrape of the manager reset every cluster alert; `CephadmDaemonFailed` lasted until cephadm's cache was refreshed |
