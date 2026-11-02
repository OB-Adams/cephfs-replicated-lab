#!/usr/bin/env python3
"""Summarise fio JSON results into Markdown tables.

Usage: summarize.py [results-directory] [baseline-target]
       (defaults: results next to this script, and raw-xfs as the baseline)
Expects results/<target>/<profile>-run<N>.json, as written by run-bench.sh.
Reports the median of the runs, and the lowest and highest value of each profile's main figure.
"""
import json
import pathlib
import statistics
import sys

PROFILES = ["seq-write", "seq-read", "rand-read-4k", "rand-write-4k", "mixed-70-30", "small-files"]
MAIN = {  # the figure that matters most for each profile
    "seq-write": ("write", "MiB/s"), "seq-read": ("read", "MiB/s"),
    "rand-read-4k": ("read", "IOPS"), "rand-write-4k": ("write", "IOPS"),
    "mixed-70-30": ("both", "IOPS"), "small-files": ("files", "files/s"),
}


def load(path):
    text = path.read_text()
    return json.loads(text[text.index("{"):])  # fio may print warnings before the JSON


def figures(path, profile):
    job = load(path)["jobs"][0]
    r, w = job["read"], job["write"]
    f = {
        "read_iops": r["iops"], "read_mibs": r["bw"] / 1024,
        "write_iops": w["iops"], "write_mibs": w["bw"] / 1024,
    }
    side = r if r["total_ios"] >= w["total_ios"] else w
    lat = side["clat_ns"]
    f["lat_mean_ms"] = lat["mean"] / 1e6
    f["lat_p99_ms"] = lat.get("percentile", {}).get("99.000000", 0) / 1e6
    if profile == "small-files":
        f["files_s"] = w["total_ios"] / (w["runtime"] / 1000)  # runtime is wall time; job_runtime sums all jobs
    kind, unit = MAIN[profile]
    if unit == "files/s":
        f["main"] = f["files_s"]
    elif kind == "both":
        f["main"] = f["read_iops"] + f["write_iops"]
    elif unit == "MiB/s":
        f["main"] = f[f"{kind}_mibs"]
    else:
        f["main"] = f[f"{kind}_iops"]
    return f


def main():
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent / "results"
    targets = sorted(p.name for p in root.iterdir() if p.is_dir())
    base = sys.argv[2] if len(sys.argv) > 2 else "raw-xfs"
    if base in targets:
        targets.remove(base)
        targets.insert(0, base)
    med = {}
    print("## Results (median of runs)\n")
    print("| Target | Profile | Runs | Main figure | Range | Read IOPS | Read MiB/s | Write IOPS | Write MiB/s | Mean latency (ms) | p99 latency (ms) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for t in targets:
        for p in PROFILES:
            runs = [figures(f, p) for f in sorted((root / t).glob(f"{p}-run*.json"))]
            if not runs:
                continue
            m = {k: statistics.median(x[k] for x in runs) for k in runs[0]}
            med[(t, p)] = m["main"]
            unit = MAIN[p][1]
            lo, hi = min(x["main"] for x in runs), max(x["main"] for x in runs)
            print(f"| {t} | {p} | {len(runs)} | {m['main']:,.0f} {unit} | {lo:,.0f} to {hi:,.0f} | "
                  f"{m['read_iops']:,.0f} | {m['read_mibs']:,.1f} | {m['write_iops']:,.0f} | {m['write_mibs']:,.1f} | "
                  f"{m['lat_mean_ms']:.2f} | {m['lat_p99_ms']:.2f} |")
    if len(targets) >= 2:
        base = targets[0]
        print(f"\n## Each target as a percentage of {base}\n")
        print("| Profile | " + " | ".join(targets[1:]) + " |")
        print("|---|" + "---|" * (len(targets) - 1))
        for p in PROFILES:
            if (base, p) not in med or not med[(base, p)]:
                continue
            cells = [f"{100 * med[(t, p)] / med[(base, p)]:.0f}%" if (t, p) in med else "" for t in targets[1:]]
            print(f"| {p} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
