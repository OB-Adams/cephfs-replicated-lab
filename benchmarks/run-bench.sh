#!/usr/bin/env bash
# Run every fio profile several times against one target and keep fio's JSON output.
# Usage: run-bench.sh <target-name> <directory-under-test> [runs]
# Run as root: it drops the page cache before each run.
set -euo pipefail

target=${1:?usage: run-bench.sh <target-name> <directory> [runs]}
dir=${2:?usage: run-bench.sh <target-name> <directory> [runs]}
runs=${3:-3}
here=$(cd "$(dirname "$0")" && pwd)
out="$here/results/$target"

mkdir -p "$out" "$dir/small"
export BENCH_DIR="$dir"

for job in seq-write seq-read rand-read-4k rand-write-4k mixed-70-30 small-files; do
  for run in $(seq 1 "$runs"); do
    sync
    echo 3 > /proc/sys/vm/drop_caches
    printf '%s  %-14s run %s of %s\n' "$(date -u +%T)" "$job" "$run" "$runs"
    fio --output-format=json --output="$out/$job-run$run.json" "$here/fio/$job.fio"
  done
done
printf '%s  done: %s\n' "$(date -u +%T)" "$out"
