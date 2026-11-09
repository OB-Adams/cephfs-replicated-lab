# Milestone 5: benchmark results

Output of `python3 benchmarks/summarize.py docs/evidence/benchmark gluster-fuse`, run on 2026-11-09.

- `gluster-fuse` and `raw-xfs` are phase 1's runs (2026-10-30), copied from glusterfs-replicated-lab.
- `cephfs-kernel` is the full CephFS run; `cephfs-kernel-w2` and `cephfs-kernel-w3` are re-runs of the write profiles. `cephfs-kernel-w2` holds only the runs that were not overwritten: rand-write-4k runs 2 and 3, and mixed-70-30 runs 1 to 3.
- `raw-xfs-vdd` is the control: plain XFS on gluster1's spare disk.

See ../../benchmark.md for how to read these figures.

## Results (median of runs)

| Target | Profile | Runs | Main figure | Range | Read IOPS | Read MiB/s | Write IOPS | Write MiB/s | Mean latency (ms) | p99 latency (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| gluster-fuse | seq-write | 3 | 199 MiB/s | 196 to 205 | 0 | 0.0 | 198 | 198.6 | 302.86 | 400.56 |
| gluster-fuse | seq-read | 3 | 847 MiB/s | 811 to 858 | 846 | 846.7 | 0 | 0.0 | 70.91 | 106.43 |
| gluster-fuse | rand-read-4k | 3 | 12,260 IOPS | 12,056 to 12,465 | 12,260 | 47.9 | 0 | 0.0 | 5.21 | 10.29 |
| gluster-fuse | rand-write-4k | 3 | 3,278 IOPS | 3,041 to 3,316 | 0 | 0.0 | 3,278 | 12.8 | 18.40 | 38.54 |
| gluster-fuse | mixed-70-30 | 3 | 6,838 IOPS | 6,784 to 6,884 | 4,783 | 18.7 | 2,055 | 8.0 | 8.60 | 25.30 |
| gluster-fuse | small-files | 3 | 322 files/s | 318 to 322 | 0 | 0.0 | 322 | 1.3 | 3.08 | 4.55 |
| cephfs-kernel | seq-write | 3 | 129 MiB/s | 84 to 135 | 0 | 0.0 | 128 | 128.7 | 501.34 | 2365.59 |
| cephfs-kernel | seq-read | 3 | 1,225 MiB/s | 1,204 to 1,228 | 1,224 | 1,225.2 | 0 | 0.0 | 52.11 | 80.22 |
| cephfs-kernel | rand-read-4k | 3 | 20,396 IOPS | 20,222 to 20,496 | 20,396 | 79.7 | 0 | 0.0 | 3.11 | 6.32 |
| cephfs-kernel | rand-write-4k | 3 | 1,639 IOPS | 1,109 to 1,739 | 0 | 0.0 | 1,639 | 6.4 | 38.98 | 164.63 |
| cephfs-kernel | mixed-70-30 | 3 | 3,244 IOPS | 3,059 to 5,329 | 2,269 | 8.9 | 975 | 3.8 | 4.39 | 44.30 |
| cephfs-kernel | small-files | 3 | 241 files/s | 209 to 246 | 0 | 0.0 | 241 | 0.9 | 15.82 | 29.49 |
| cephfs-kernel-w2 | rand-write-4k | 2 | 1,622 IOPS | 1,371 to 1,874 | 0 | 0.0 | 1,622 | 6.3 | 40.35 | 144.70 |
| cephfs-kernel-w2 | mixed-70-30 | 3 | 5,064 IOPS | 3,425 to 5,188 | 3,546 | 13.9 | 1,517 | 5.9 | 3.94 | 27.39 |
| cephfs-kernel-w3 | seq-write | 3 | 140 MiB/s | 134 to 145 | 0 | 0.0 | 139 | 139.5 | 459.80 | 1417.67 |
| raw-xfs | seq-write | 3 | 18,804 MiB/s | 17,892 to 19,148 | 0 | 0.0 | 18,803 | 18,803.7 | 3.27 | 6.78 |
| raw-xfs | seq-read | 3 | 21,703 MiB/s | 21,396 to 21,707 | 21,702 | 21,703.1 | 0 | 0.0 | 2.90 | 5.41 |
| raw-xfs | rand-read-4k | 3 | 154,184 IOPS | 151,883 to 154,212 | 154,184 | 602.3 | 0 | 0.0 | 0.41 | 0.99 |
| raw-xfs | rand-write-4k | 3 | 133,920 IOPS | 129,625 to 135,406 | 0 | 0.0 | 133,920 | 523.1 | 0.47 | 1.14 |
| raw-xfs | mixed-70-30 | 3 | 124,562 IOPS | 118,066 to 124,785 | 87,203 | 340.6 | 37,359 | 145.9 | 0.49 | 1.27 |
| raw-xfs | small-files | 3 | 31,128 files/s | 25,641 to 34,783 | 0 | 0.0 | 31,128 | 121.6 | 0.08 | 0.18 |
| raw-xfs-vdd | seq-write | 3 | 18,537 MiB/s | 17,082 to 19,107 | 0 | 0.0 | 18,536 | 18,536.9 | 3.36 | 6.72 |
| raw-xfs-vdd | seq-read | 3 | 22,095 MiB/s | 20,817 to 22,342 | 22,094 | 22,095.4 | 0 | 0.0 | 2.88 | 5.14 |
| raw-xfs-vdd | rand-read-4k | 3 | 166,349 IOPS | 165,970 to 166,461 | 166,349 | 649.8 | 0 | 0.0 | 0.38 | 0.91 |
| raw-xfs-vdd | rand-write-4k | 3 | 140,214 IOPS | 125,975 to 143,332 | 0 | 0.0 | 140,214 | 547.7 | 0.45 | 1.06 |
| raw-xfs-vdd | mixed-70-30 | 3 | 135,473 IOPS | 130,875 to 136,724 | 94,840 | 370.5 | 40,633 | 158.7 | 0.45 | 1.12 |
| raw-xfs-vdd | small-files | 3 | 33,613 files/s | 26,316 to 36,199 | 0 | 0.0 | 33,613 | 131.3 | 0.08 | 0.15 |

## Each target as a percentage of gluster-fuse

| Profile | cephfs-kernel | cephfs-kernel-w2 | cephfs-kernel-w3 | raw-xfs | raw-xfs-vdd |
|---|---|---|---|---|---|
| seq-write | 65% |  | 70% | 9468% | 9334% |
| seq-read | 145% |  |  | 2563% | 2610% |
| rand-read-4k | 166% |  |  | 1258% | 1357% |
| rand-write-4k | 50% | 49% |  | 4085% | 4277% |
| mixed-70-30 | 47% | 74% |  | 1821% | 1981% |
| small-files | 75% |  |  | 9680% | 10453% |
