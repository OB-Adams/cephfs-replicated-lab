# Security: cephx capabilities and encryption on the wire

Milestone 4a, drill 8. It is the Ceph counterpart of the Gluster lab's milestone 3a, which used `auth.allow` and mutual TLS. The drill answers three questions:

1. What crosses the network in clear with the default settings?
2. What can a key do, and what is refused?
3. Can every connection be encrypted and plaintext clients refused, without taking the cluster down?

Run on 2026-11-06, times UTC. See [milestones.md](milestones.md). Monitoring and alerts (milestone 4b) will follow in their own document.

| Part | What was done | Gluster counterpart |
|---|---|---|
| 1 | Client traffic captured in the default `crc` mode, looking for a file's contents | `openssl s_client` against the brick ports |
| 2 | Mounts tried with a forged key, an unknown name, a read-only key and a key limited to one directory; RADOS tried directly | No certificate, a self-signed certificate, a signed certificate with the wrong name |
| 3 | A key revoked while mounted, then its session evicted | Not tested |
| 4 | Every msgr2 mode set to `secure`, every daemon restarted one at a time while the client wrote, traffic captured again | `client.ssl` and `server.ssl`, which needed the volume stopped |
| 5 | Mounts tried with each `ms_mode` to see which the cluster still accepts | Not tested |

## How Ceph secures a connection

**cephx is who you are.** Every client and daemon has a key: a secret shared with the monitors. Logging in never sends the key. The monitor sends a challenge encrypted with the key; a client that can decrypt it gets a ticket, valid for an hour by default and renewed automatically. The client shows the ticket to OSDs and MDS daemons, which check it with service keys they get from the monitors, so they never need the client's own key. This is the Kerberos design. A wrong key fails at the monitor, before the client reaches any OSD or MDS.

**Capabilities are what you may do.** Each key carries one capability ("cap") per kind of daemon, and that daemon enforces it:

| Cap | Checked by | `client.gluster4` | Meaning |
|---|---|---|---|
| `mon` | monitors | `allow r fsname=cephfs` | Read the maps that concern `cephfs` |
| `mds` | the MDS | `allow rw fsname=cephfs` | Read and change metadata anywhere in `cephfs` |
| `osd` | OSDs | `allow rw tag cephfs data=cephfs` | Read and write objects only in `cephfs`'s data pools |

`ceph fs authorize` narrows the `mds` cap by path (`path=/scoped`) or by mode (`r`). Gluster's `auth.allow` and `auth.ssl-allow` decide only whether a client may connect. Ceph's caps decide what it may do once connected, separately for each kind of daemon.

**The messenger is how bytes travel.** Ceph's network layer has two protocols:

- **msgr1** ("legacy", monitors on port 6789) has cephx login but no encryption at all.
- **msgr2** (monitors on 3300, other daemons from 6800) runs each connection in a mode chosen when it opens:
  - `crc`: each message is checksummed but readable by anyone on the network.
  - `secure`: AES-GCM encryption, keyed from the cephx session.

The side opening a connection offers a list of modes. The kernel client takes its list from the `ms_mode` mount option; daemons use `ms_client_mode` and `ms_cluster_mode`. The side accepting picks the first entry in its own list (`ms_service_mode`) that the other side offered. The defaults list `crc` first on both sides, so before the drill every connection used `crc`. Connections to monitors have their own three settings (`ms_mon_*_mode`). Encryption needs no certificates, because the cephx session already gives both ends a shared secret; the Gluster lab needed a certificate authority for the same result.

## Part 1: what crosses the network in clear

The client was mounted with `ms_mode=prefer-crc`, its setting since milestone 1. gluster4 captured its traffic to the OSD and MDS ports for 30 seconds while writing three small files. Each file held a marker line, `CEPHFS-DRILL8-1794002185 line N`. gluster2 captured the same ports for 60 seconds.

| Capture | Packets | Marker lines found |
|---|---|---|
| gluster4, client traffic | 201 | All three, once each (screenshot 10) |
| gluster2, client and replication traffic | 4531 | Line 1 once, line 2 three times, line 3 once |

**The contents of every file crossed the network in clear**, on the client's link and between the servers.

The counts on gluster2 follow from how Ceph replicates. A client writes each object to the placement group's primary OSD, which sends it on to the other two. Where an OSD on gluster2 was the primary, as for line 2, the data passed gluster2's interface three times: once in from the client, then out to each replica. Where gluster2 held a replica, as for lines 1 and 3, it passed once, coming in.

## Part 2: what keys can do

On gluster1 two keys were made for the test:

```text
client.reader   mds "allow r fsname=cephfs"                 osd "allow r tag cephfs data=cephfs"
client.scoped   mds "allow rw fsname=cephfs path=/scoped"   osd "allow rw tag cephfs data=cephfs"
```

Both keyrings were copied to gluster4. A random key was also generated there (`ceph-authtool --gen-print-key`) to stand in for a forged one.

| Test | Result | Refused by |
|---|---|---|
| `client.reader` with the forged key | `mount error: no mds (Metadata Server) is up. The cluster might be laggy, or you may not be authorized`, exit 32 | Monitor, at login |
| An unknown name, `client.nobody` | The same message, exit 32 | Monitor, at login |
| `client.reader`: mount, read, write | Mounted; `hello.txt` read; the write failed with `Permission denied` | MDS |
| `client.scoped` mounting `/` | `mount error 13 = Permission denied` | MDS |
| `client.scoped` mounting `/scoped` | Mounted; `ok.txt` read | |
| `client.gluster4` listing the data pool with `rados` | Listed objects | |
| `client.gluster4` listing the metadata pool with `rados` | `rados_nobjects_list_next2: Operation not permitted`, exit 1 | OSDs |

Screenshot 11 shows all of these.

- **The kernel reports a failed login as a missing MDS.** For both the forged key and the unknown name, the mount's only message was "no mds is up". The real reason was in the kernel log: `libceph: auth protocol 'cephx' msgr authentication failed: -13`, followed by `ceph: No mds server is up or the cluster is laggy`. With a wrong key, check `dmesg` before looking for a fault in the cluster.
- **Each refusal came from the daemon that owns the cap.** The monitor refused the logins. The MDS refused the read-only write and the scoped root mount; the cluster log recorded `client session with non-allowable root '/' denied` and the kernel `mds0 rejected session`. The OSDs refused the metadata pool.
- **The metadata pool is out of reach, the data pool is not.** A client with a valid key can read the raw objects of every file in the data pool directly from RADOS, bypassing the MDS and its permission checks. `client.scoped`'s `osd` cap is the same as `client.gluster4`'s, `data=cephfs` with no path. So its path limit appears to be enforced only by the MDS, and the key could probably still read other directories' file objects straight from the pool. That was not tried. Confining it would mean a separate data pool or a RADOS namespace for the directory.

## Part 3: revoking a key

With `client.reader` mounted at `/mnt/t-reader`, the key was deleted on gluster1 with `ceph auth rm client.reader`.

| Step | Result |
|---|---|
| `ls /mnt/t-reader`, twice | Listed the directory: the mount kept working |
| A new mount with the deleted key | `no mds is up`, exit 32 |
| `ceph tell mds.cephfs:0 client ls` | Two sessions for `reader`, 134280 and 134120 |
| `ceph tell mds.cephfs:0 client evict id=134280` at 22:17:36 | `Evicting (and blocklisting) client session 134280` |
| `ls /mnt/t-reader` | `Permission denied` |

**Deleting a key stops new logins only.** A mounted client keeps its ticket and its MDS session until the ticket expires or the session ends. Revocation is the deletion plus evicting every session the key holds. Eviction also blocklists the client's address and instance, so the OSDs refuse its requests too; the kernel logged `mds0 session blocklisted` and `mds0 rejected session`.

The second session had a consequence later. The Part 2 commands had been pasted twice, so `reader` and `scoped` were each mounted twice, one mount on top of the other. Only the newest `reader` session was evicted, and `umount -l` removed only the top mount. Session 134120 stayed open with its key deleted, and it delayed the MDS failover in Part 4 by about 45 seconds.

## Part 4: secure mode for every connection

**The client.** `ms_mode=secure` was added to gluster4's `/etc/fstab` line, and `/mnt/cephfs` was remounted. The first remount warned that systemd still used the old file; after `systemctl daemon-reload` the remount showed `ms_mode=secure`. A new 30-second capture while three marker files were written (screenshot 12):

| Capture | Packets | Marker lines found |
|---|---|---|
| gluster4, `ms_mode=secure` | 410 | 0 |

The file read back correctly through the mount.

**The cluster.** On gluster1, all six mode settings were set to `secure` alone:

```bash
ceph config set global ms_cluster_mode secure
ceph config set global ms_service_mode secure
ceph config set global ms_client_mode secure
ceph config set global ms_mon_cluster_mode secure
ceph config set global ms_mon_service_mode secure
ceph config set global ms_mon_client_mode secure
```

A daemon reads these when it starts, so `noout` was set and every daemon was restarted one at a time with `ceph orch daemon restart`. Each restart waited for `HEALTH_OK` (or only the `noout` warning) before the next. The client wrote 1500 files, one every half second, throughout.

| Time | Daemons restarted | Slowest client write |
|---|---|---|
| 22:34:14 to 22:35:15 | `mon.gluster3`, `mon.gluster2`, `mon.gluster1`; three elections, quorum kept | 0.048 s |
| 22:35:15 to 22:37:39 | `osd.0` to `osd.5`; each marked itself down, then booted 9 to 11 s later | 1.170 s |
| 22:45:44 to 22:46:05 | The standby MDS, `cephfs.gluster2.stwcqc` | 0.046 s |
| 22:46:05 to 22:47:02 | The active MDS, `cephfs.gluster1.wmvdvt`; the standby took rank 0 | **51.100 s** |
| 22:47:02 to 22:47:22 | The standby manager, `gluster2.qhtcrw` | 0.033 s |
| 22:47:22 | The active manager, `gluster1.bxuyky`: refused | |

Restarting the monitors one at a time cost the client nothing measurable. In milestone 2, a host taking its monitor away stalled a write for 11.9 s; the difference was not established. Each OSD restart cost about a second, while its placement groups peered without it and again when it returned.

**The 51-second stall.** The cluster log shows the failover itself was quick:

```text
22:46:10.863 Health check failed: 1 filesystem is offline (MDS_ALL_DOWN)
22:46:10.892 Standby daemon mds.cephfs.gluster2.stwcqc assigned to filesystem cephfs as rank 0
22:46:59.317 evicting unresponsive client gluster4: (134120), after waiting 47.3695 seconds during MDS startup
22:47:01.321 daemon mds.cephfs.gluster2.stwcqc is now active in filesystem cephfs as rank 0
```

A new MDS starts in a **reconnect** state: before serving anyone, it waits for every client that had a session with the old one to come back and restate what it holds. Session 134120 was the `reader` mount left over from Part 3. With its key deleted, it could not log in again, so the MDS waited out its reconnect timeout and then evicted it. The writer's write that started at 22:46:11.269 finished at 22:47:02.37, a second after the MDS became active. In milestone 2, killing the active MDS stalled the client for 13.4 s with no stale client present.

**One stale session delayed the file system for every client.** After revoking a key, evict all of its sessions (`client ls`, then `client evict` for each ID), not just one.

**The active manager was not restarted.** `ceph orch daemon restart` refuses to restart the active manager: `Cannot stop active Mgr daemon, Please switch active Mgrs with 'ceph mgr fail gluster1.bxuyky'`. A second attempt with `--force` after the name was ignored, because the restart helper passed only its first argument. The manager is not on the client's path to CephFS, so no result here depends on it. Until it restarts it keeps the old settings, so it would still accept a `crc` connection from a client that asked for one; the restarted daemons offer only `secure`, so their connections to it use that. `ceph mgr fail` hands its role to the standby and lets it restart.

**The traffic between the servers.** After the restarts, gluster4 wrote six marker files while gluster2 captured the OSD and MDS ports for 60 seconds: 4550 packets, no marker found. In `crc` mode, Part 1's capture on gluster2 had found all three.

The writer's 1500 files were all correct afterwards, with no failed writes.

## Part 5: which clients the cluster still accepts

| Mount option | Result |
|---|---|
| `ms_mode=crc` | Refused: `no mds is up`, exit 32 (screenshot 13) |
| `ms_mode=prefer-crc` | Mounted. The client offers `crc` then `secure`, and the cluster picks `secure` |
| `ms_mode=legacy` (msgr1) | **Mounted**, to the monitors on port 6789 |

**msgr1 is still open.** The six mode settings govern msgr2 only, and msgr1 has no modes at all. Every daemon still listens on msgr1 as well as msgr2: the OSDs announced both addresses when they booted after their restarts, for example `osd.0 [v2:…:6808/…,v1:…:6809/…] boot`. A client asking for msgr1 can still use CephFS without encryption. Reading, writing and capturing over the legacy mount were not tried.

Closing it means stopping every daemon from binding msgr1 (`ms_bind_msgr1 false`), removing the `v1` addresses from the monitor map, and restarting everything again; any client that still knows only msgr1 then stops working. That was left for later, so the cluster ends the drill with msgr2 encrypted and msgr1 open.

## After the drill

`client.reader` and `client.scoped` were deleted and their keyrings removed from both machines; `ceph auth ls` lists only the admin, bootstrap and crash keys and `client.gluster4`. The cluster was `HEALTH_OK`, 145 PGs `active+clean`, with all six mode settings `secure`. On gluster4, the 3000 files of drill 5 and the 1500 of drill 8 were correct, the fill set matched and `test10M.bin` matched its reference checksum.

The active MDS is now `cephfs.gluster2.stwcqc`, with `cephfs.gluster1.wmvdvt` as standby.

Left over: the stacked `reader` and `scoped` mounts were still on `/mnt/t-reader` and `/mnt/t-scoped` at the end of the recording. With their keys deleted, the next MDS failover would wait for them as it waited in Part 4, so they need unmounting (`umount -l` until `mountpoint` reports nothing) before milestone 5.

The packet captures stayed on the VMs.

Evidence: [drill8-session-gluster1.txt](evidence/drill8-session-gluster1.txt), [drill8-session-gluster2.txt](evidence/drill8-session-gluster2.txt), [drill8-session-gluster4.txt](evidence/drill8-session-gluster4.txt), [drill8-cephw.txt](evidence/drill8-cephw.txt), [drill8-writes.log](evidence/drill8-writes.log).

## Summary

| | Gluster (phase 1) | Ceph (this lab) |
|---|---|---|
| Default traffic | Plain TCP | msgr2 `crc`: checksummed, not encrypted; file contents readable on the wire |
| Who may connect | `auth.allow` by address, `auth.ssl-allow` by certificate name | A cephx key, checked by the monitors at login |
| What a client may do | The whole volume, subject to file permissions | Caps per daemon type: read-only, limited to a path, no access to the metadata pool |
| A bad credential | Refused at the TLS handshake or by the brick | Refused at the monitor; the mount reports `no mds is up` |
| Revocation | Not tested | `auth rm` stops new logins only; the sessions must be evicted |
| Encryption | Mutual TLS, a lab CA and a certificate per machine | msgr2 `secure`, keyed from cephx; no certificates |
| Turning encryption on | The volume and `glusterd` stopped on every server | One daemon at a time while the client wrote; the only stall came from a stale client at MDS failover |
| Plaintext clients afterwards | Refused | msgr2 `crc` refused; msgr1 still accepted |
