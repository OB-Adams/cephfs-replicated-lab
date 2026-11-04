#!/usr/bin/env bash
# Create numbered files on CephFS, each written with fsync, and record when each write started and how long it took.
# Run on the client, against a directory on the CephFS mount.
# Usage: drill-writer.sh <directory> [count] [interval-seconds] [logfile]
# Output lines: <UTC time the write started> <file number> <seconds> <ok|FAIL: reason>
set -uo pipefail

dir=${1:?usage: drill-writer.sh <directory> [count] [interval-seconds] [logfile]}
count=${2:-300}
interval=${3:-0.5}
logfile=${4:-/dev/null}

errfile=$(mktemp)
trap 'rm -f "$errfile"' EXIT

mkdir -p "$dir"

for i in $(seq 1 "$count"); do
  stamp=$(date -u +%T.%3N)
  start=$(date +%s.%N)
  if printf '%s\n' "$i" | dd of="$dir/f$i.txt" conv=fsync status=none 2> "$errfile"; then
    status=ok
  else
    status="FAIL: $(tr -d '\n' < "$errfile")"
  fi
  end=$(date +%s.%N)
  awk -v t="$stamp" -v s="$start" -v e="$end" -v i="$i" -v st="$status" \
    'BEGIN { printf "%s %d %.3f %s\n", t, i, e - s, st }' | tee -a "$logfile"
  sleep "$interval"
done
