# Benchmarks

The `fio` kit from [glusterfs-replicated-lab](https://github.com/OB-Adams/glusterfs-replicated-lab/tree/main/benchmarks), copied unchanged so CephFS runs exactly the same tests as Gluster did. It is used in milestone 5.

| File | Purpose |
|---|---|
| `fio/*.fio` | One job file per workload. Each reads the directory under test from the `BENCH_DIR` environment variable. |
| `run-bench.sh` | Runs every profile several times against one target, dropping the page cache before each run, and keeps fio's JSON output in `results/<target>/`. Run as root. |
| `summarize.py` | Turns the JSON into Markdown tables: the median of the runs for each target and profile, and each target as a percentage of the baseline. |

```bash
./benchmarks/run-bench.sh cephfs-kernel /mnt/cephfs/bench 3               # on the client
python3 benchmarks/summarize.py <results-directory> [baseline-target]     # baseline defaults to raw-xfs
```

`results/` is ignored by git; the runs that are kept are copied into `docs/evidence/`.
