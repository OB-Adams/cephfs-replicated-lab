# cephfs-replicated-lab

A hands-on Ceph lab: a three-node Ceph cluster deployed with `cephadm` on the same Linux VMs and disks that ran the GlusterFS lab, with a CephFS file system mounted on a separate client. The cluster is taken through the same kinds of recorded drills as the Gluster volume (failure, disk replacement, expansion, access control, monitoring and a `fio` benchmark), and the two systems are compared from what was measured.

This is phase 2 of a storage study. Phase 1, the GlusterFS build and its nine drills, is in [glusterfs-replicated-lab](https://github.com/OB-Adams/glusterfs-replicated-lab). Its milestone 6 removed Gluster from the VMs and wiped the data disks, which is where this repository starts.

## Project status

| Item | Status |
|---|---|
| Milestone 1: deploy Ceph and mount CephFS | In progress |
| Milestone 2: failure drills | Planned |
| Milestone 3: OSD replacement and expansion | Planned |
| Milestone 4: security and monitoring | Planned |
| Milestone 5: `fio` benchmark against the Gluster baseline | Planned |
| Milestone 6: Gluster and CephFS comparison | Planned |

The full tracker is in [docs/milestones.md](docs/milestones.md). Anything not listed as complete is not implemented.

## Objectives

- Deploy a replicated Ceph cluster and understand each layer: monitors and quorum, OSDs and BlueStore, placement groups and CRUSH, pools, the metadata server and the CephFS client.
- Repeat the Gluster lab's tests on the same hardware, so the differences come from the storage system and not the environment.
- Observe real failure and recovery behaviour instead of describing it from documentation.
- Record what was measured, what surprised me, and what remains unexplained.

## Environment

| Item | Value |
|---|---|
| Hypervisor | UTM, virtualization mode (not emulation), on an Apple Silicon Mac |
| Guest architecture | aarch64 |
| Guest OS | CentOS Stream 9 |
| Ceph release | 20.2 "Tentacle", from the CentOS Storage SIG, deployed with `cephadm` |
| Servers | `gluster1`, `gluster2`, `gluster3`, 8 GB RAM each, two 10 GB data disks each (`/dev/vdb`, `/dev/vdc`) |
| Client | `gluster4`, kernel CephFS client |

The VMs keep their names from phase 1. The behaviour recorded here applies to this OS release and Ceph version only.

## Repository structure

```text
cephfs-replicated-lab/
├── README.md
├── LICENSE
├── .gitignore
├── benchmarks/                the fio kit from phase 1, unchanged, so both systems run the same tests
│   ├── README.md
│   ├── run-bench.sh
│   ├── summarize.py
│   └── fio/                   one job file per workload
├── docs/
│   ├── milestones.md
│   └── evidence/              session recordings and command output from each milestone
└── screenshots/
    └── README.md              what each screenshot shows and the commands behind it
```

## Security notes

- Ceph keyrings (`ceph.client.admin.keyring` and every `ceph.client.*.keyring`) are the cluster's secrets. They stay on the VMs and are excluded by `.gitignore`.
- The lab runs as root over SSH for convenience. A real deployment should separate administrative access.

## Licence

MIT. See [LICENSE](LICENSE).
