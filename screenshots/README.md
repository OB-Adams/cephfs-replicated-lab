# Screenshots

This folder holds screenshots of real terminal output from the lab. This file records what each image shows and the commands behind it, so the set can be reproduced.

## Rules

- Capture genuine output from the running lab, live during the run. Never mock up or edit output.
- Make the machine visible: keep the shell prompt (`root@gluster1:~#` and similar) in frame.
- Crop to the relevant output. Prefer a few clear images over many similar ones.
- Check each image for private addresses, keys or personal information before committing. Never capture a keyring's contents.
- Use the exact file names below.

## The set

| File | Machine | What was run | What it shows |
|---|---|---|---|
| `01-ceph-cluster-health.png` | gluster1 | `ceph -s`, `ceph osd tree` | The healthy cluster: three monitors in quorum, six OSDs on three hosts, CephFS with an active and a standby MDS |
| `02-ceph-object-placement.png` | gluster1 | `rados -p cephfs.cephfs.data ls`, `ceph osd map`, `ceph df` | A client file's objects, each placed on three OSDs on three different hosts, and the pool storing three copies |
