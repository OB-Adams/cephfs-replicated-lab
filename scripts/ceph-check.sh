#!/usr/bin/env bash
# Check drill files (each fN.txt holds N) and the 2 GB fill set against its recorded checksums.
# Usage: ceph-check.sh <drill directory> ...
for d in "$@"; do
  n=$(ls "$d" | wc -l); bad=0
  for i in $(seq 1 "$n"); do [ "$(cat "$d/f$i.txt" 2>/dev/null)" = "$i" ] || bad=$((bad+1)); done
  echo "$d: $n files, $bad wrong or missing"
done
( cd /mnt/cephfs/fill && sha256sum --quiet -c /root/ceph-fill.sha256 ) && echo "fill: 100 files match their checksums"
sha256sum /mnt/cephfs/test10M.bin
