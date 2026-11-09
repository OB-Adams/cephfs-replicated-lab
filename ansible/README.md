# Ansible automation

Milestone 7. Playbooks that build the whole lab as it stands after milestone 5:
- the repositories and packages, with chrony stepping the clock
- a cluster bootstrapped with `cephadm`, every msgr2 connection `secure` from the first monitor
- three monitors, two managers, six OSDs from a service spec, and the `cephfs` file system with an active and a standby MDS
- the kernel client on `gluster4` with its own key, mounted from `/etc/fstab` with `ms_mode=secure`
- the Ceph Dashboard and cephadm's monitoring stack, with `gluster4` as the monitoring host

Every task checks the current state before it acts, so that a second run against a built lab has nothing to change. The playbooks pass `ansible-lint` at the `production` profile and a syntax check, which CI runs on every push. They follow the layout of phase 1's playbooks in [glusterfs-replicated-lab](https://github.com/OB-Adams/glusterfs-replicated-lab/tree/main/ansible).

**Status: written and checked, not yet run against the lab.** See [Rebuilding from scratch](#rebuilding-from-scratch) for the run that completes the milestone.

## Layout

```text
ansible/
├── ansible.cfg                 inventory, roles path, root over SSH, pipelining, keep-alives
├── .ansible-lint               production profile
├── requirements.yml            collections, minimum versions pinned
├── inventory/
│   ├── hosts.yml               the four VMs by name, in groups; no addresses
│   └── group_vars/all.yml      the lab described once, and the role inputs wired from it
├── site.yml                    build, or converge to the declared state
├── verify.yml                  read-only checks, from each role's tasks/verify.yml
├── teardown.yml                remove everything, from each role's tasks/teardown.yml
└── roles/<role>/
    ├── defaults/main.yml       the role's inputs and their defaults
    ├── meta/argument_specs.yml the inputs' types, checked before the role runs
    ├── tasks/main.yml          build
    ├── tasks/verify.yml        check what main.yml builds
    ├── tasks/teardown.yml      remove what main.yml builds
    ├── handlers/main.yml       restarts
    └── templates/              service specs
```

The CI workflow in [../.github/workflows/ansible-ci.yml](../.github/workflows/ansible-ci.yml) runs `ansible-lint` and a syntax check of every playbook on each push that touches `ansible/`.

## Roles

| Role | Runs on | Builds | verify | teardown |
|---|---|---|---|---|
| `common` | all VMs | Asserts SELinux is enforcing; IPv4 `/etc/hosts` entries from facts; chrony with one source and `makestep 1.0 -1`; firewalld | yes | |
| `ceph_packages` | all VMs | Removes older Ceph release repositories; enables CRB; EPEL and the Storage SIG's Tentacle repository; `cephadm` and its requirements (with `python3-jinja2`) on cephadm hosts, `ceph-common` on admin hosts and the client, `fio` on the client; stops if a package is not 20.2 | yes | yes |
| `ceph_bootstrap` | first server | `cephadm bootstrap` with the host's IPv4 address and an initial `ceph.conf` that sets every msgr2 mode, only if `/etc/ceph/ceph.conf` is absent; the memory limits for OSDs and the MDS | yes | yes: `cephadm rm-cluster --zap-osds` on every cephadm host |
| `ceph_hosts` | first server | cephadm's public key to every host; the hosts added by IPv4 address; the `_admin` and `monitoring` labels | yes | |
| `ceph_services` | first server | Service specs for the monitors, managers, OSDs and MDS, applied when they change; the file system; waits for every OSD and an active MDS | yes | yes: data disks cleared and checked empty |
| `ceph_security` | first server | The six msgr2 mode settings, in the monitors' configuration database | yes | |
| `ceph_client` | client | The client's key from `ceph fs authorize`, the minimal `ceph.conf`, the keyring (mode 0600), and the fstab mount | yes | yes |
| `ceph_monitoring` | first server | The `prometheus` and `dashboard` manager modules, the Dashboard's certificate and administrator, port 8443 on the manager hosts, the five monitoring services, the Dashboard's links to them, and Grafana's address for the browser | yes | yes: port 8443 closed |

## Variables

Each role's inputs are in its `defaults/main.yml`, prefixed with the role's name. `meta/argument_specs.yml` gives each input a type and says which are required; Ansible checks them before a role's first task.

`inventory/group_vars/all.yml` describes the lab once (`lab_fs_name`, `lab_mon_hosts`, `lab_mgr_hosts`, `lab_mds_hosts`, `lab_admin_hosts`, `lab_cephadm_hosts`, `lab_osd_devices`, `lab_msgr_mode`, `lab_client_mount_point`), then sets each role's inputs from it. The msgr2 mode, for example, reaches the bootstrap's initial configuration, the security role and the client's mount option from one variable, so they cannot disagree.

## Running it

From this directory, on a control node that reaches the VMs by name as root over SSH keys:

```bash
ansible-galaxy collection install -r requirements.yml
ansible all -m ping

read -rsp 'Dashboard admin password: ' DASHBOARD_ADMIN_PASSWORD; echo; export DASHBOARD_ADMIN_PASSWORD
ansible-playbook site.yml                  # build, or converge
ansible-playbook site.yml                  # again: changed=0
ansible-playbook verify.yml                # read-only checks
ansible-playbook site.yml --check --diff   # what a run would change, against a built lab
ansible-lint                               # what CI runs
```

Tags select parts of the build: `common`, `packages`, `bootstrap`, `hosts`, `services`, `security`, `client`, `monitoring`.

**Against the hand-built lab, read the check run before a real one.** The Dashboard password in the environment replaces the one set by hand if they differ, and the OSD spec is written with a host list instead of milestone 1's `host_pattern`, which the check run reports as a new spec file. Neither moves data.

## Rebuilding from scratch

A full rebuild from the current VMs. It destroys the cluster and everything on CephFS, and zaps the data disks.

1. Keep the Mac awake for the whole run (`caffeinate -dims`, on mains power, lid open). A pause during the bootstrap or OSD creation leaves the clocks skewed.
2. Run `ansible-playbook site.yml --check --diff` against the hand-built lab and read what it would change.
3. Run `ansible-playbook teardown.yml -e confirm_teardown=cephfs`. Then check on a server that `lsblk /dev/vdb /dev/vdc` shows no LVM volumes and `cephadm` is not installed.
4. Run `ansible-playbook site.yml` to build from scratch.
5. Run `ansible-playbook site.yml` again. Expect `changed=0` on every host; any `changed` is a bug in the playbooks.
6. Run `ansible-playbook verify.yml`, then milestone 1's checks by hand: `ceph -s`, `ceph osd tree`, `ceph fs status`, a file written on the client and traced to its OSDs.

The spare `vdd` disks are not used by the build and not touched by the teardown.

## Design notes

**Idempotence with the ceph CLI.** Like the `gluster` CLI, `ceph` has no "ensure" mode, and Ansible has no maintained Ceph collection, so the cluster is managed with `command` tasks. Each change is guarded by a read of the current state that runs even in check mode and never reports a change: `ceph config get`, `ceph orch host ls`, `ceph orch ls`, `ceph fs ls`, `ceph mgr module ls`, `ceph auth get`. `ceph orch apply` always says it scheduled an update, so it runs only when a spec file on the bootstrap host changed or its service does not exist.

**The bootstrap runs once.** `cephadm bootstrap` has `creates: /etc/ceph/ceph.conf`, so a host that already holds a cluster's configuration is never bootstrapped again.

**Encrypted from the first daemon.** Milestone 4a turned on msgr2 `secure` mode on a running cluster, which needed every daemon restarted one at a time. The build writes the six mode settings into the configuration `cephadm bootstrap` reads, so the first monitor and every daemon after it start encrypted. `ceph_security` keeps the setting in the monitors' database and does not restart daemons on a running cluster; a change there needs the rolling restart.

**Lessons from the hand-built lab, built in.**
- The monitor's address comes from the host's IPv4 facts, never from a name lookup that returned an IPv6 link-local address (milestone 1).
- chrony steps the clock at any time and every VM uses one source, and `verify.yml` checks the offset is under 50 ms (milestones 1, 4b and 5).
- `python3-jinja2` is installed for the Storage SIG's `cephadm`, and the build stops if `ceph-common` is not from 20.2, the Pacific client that could not read Tentacle's keys (milestone 1).
- The Dashboard is enabled before the monitoring services are deployed, so cephadm links it to them, and the role reconfigures them if a link is still empty (milestone 4b).
- Port 8443 is opened on every manager host, because cephadm does not open it (milestone 4b).

**Secrets.** The Dashboard password is read from the control node's environment, never written to a file, and reaches `ceph` on standard input. The role logs in through the Dashboard's API to check it, and sets it only if the login fails. The client's key is read on the bootstrap host and written to the client with mode 0600. Every task that holds a secret has `no_log`. No keyring is stored on the control node or in the repository.

**Teardown is guarded.** `teardown.yml` refuses to run without `-e confirm_teardown=cephfs`, and refuses to wipe a device that holds the root filesystem. It removes the cluster with `cephadm rm-cluster --zap-osds` on every host it finds daemons on, then clears and checks the data disks.

**Not managed.** The OS install, SSH access, static addresses, the UTM disks, and msgr1, which stays bound as in the hand-built lab. Ansible connects as `root`, as the lab always has; a dedicated user with `become` is the better practice. The milestone 4a test keys and the milestone 3 spare disks are not part of the build.
