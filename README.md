# Blined Cloud — VPS Deployer Discord Bot

A Discord bot that deploys **real KVM virtual machines** — not Docker containers —
by talking to a [Proxmox VE](https://www.proxmox.com/en/proxmox-ve) hypervisor's
API. Each `.deploy` creates a genuine, fully isolated virtual machine with its
own kernel, disk, and IP address, cloned from a cloud-init template.

> ⚠️ A Discord bot cannot spin up hardware-virtualized VMs on its own — that
> requires a real hypervisor underneath it. This bot is the control layer;
> Proxmox VE is the actual VM engine. See **Requirements** below for what you
> need on the infrastructure side before this bot can deploy anything.

---

## Features

- `.deploy <@user> <memory_mb> <cores> <disk_gb> <suspend_time>` — clone a
  cloud-init template into a brand-new real VM, resize it to spec, boot it,
  and DM the owner their IP + root password.
- `.list [@user]` — list all deployed VPS instances (or one user's).
- `.info <vmid>` — full spec/status for a single VPS.
- `.suspend <vmid>` / `.unsuspend <vmid>` — stop/start a VM on demand.
- `.renew <vmid> <suspend_time>` — change a VM's auto-suspend timer.
- `.delete <vmid>` — permanently destroy a VM (with reaction confirmation).
- `.help` — full command reference.
- Background scheduler auto-suspends VMs once their `suspend_time` expires.
- SQLite-backed record of every VPS: owner, specs, IP, credentials, status.

---

## Requirements

### 1. Proxmox VE host
A working Proxmox VE node (bare metal or nested virtualization) with:
- API reachable at `https://<host>:8006`
- An **API token** (Datacenter → Permissions → API Tokens) with VM admin
  rights (`PVEVMAdmin` or Administrator on the target node/pool).
- A **cloud-init template** already prepared, e.g.:

```bash
# On the Proxmox node, import a cloud image and turn it into a template:
wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
qm create 9000 --name ubuntu-2204-cloudinit --memory 1024 --cores 1 --net0 virtio,bridge=vmbr0
qm importdisk 9000 jammy-server-cloudimg-amd64.img local-lvm
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --ide2 local-lvm:cloudinit
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm template 9000
```

Note the resulting VMID (`9000` above) — that goes into `PVE_TEMPLATE_ID`.

### 2. Python environment
- Python 3.10+
- A Discord bot application + token (Discord Developer Portal), with the
  **Server Members Intent** and **Message Content Intent** enabled.

---

## One-click install

On the Linux machine that will run the bot:

```bash
curl -fsSL https://raw.githubusercontent.com/krishdeep0009-glitch/real-vps-bot/main/install.sh | bash
```

This installs git/python3/venv, clones the repo, creates a virtualenv,
installs dependencies, copies `.env.example` → `.env`, and registers a
`systemd` service (`blined-cloud-bot`) so the bot auto-starts and
auto-restarts on crash/reboot. You still need to **edit `.env`** with your
Discord token and Proxmox details before starting it — see below.

```bash
sudo systemctl start blined-cloud-bot
sudo journalctl -u blined-cloud-bot -f   # tail logs
```

## Manual setup

```bash
git clone https://github.com/krishdeep0009-glitch/real-vps-bot.git
cd real-vps-bot

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# now edit .env with your Discord token + Proxmox host/token/template info

python bot.py
```

The bot will create `data/blined.db` automatically on first run.

---

## Configuration reference (`.env`)

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your Discord bot token |
| `COMMAND_PREFIX` | Command prefix, default `.` |
| `ADMIN_ROLE_IDS` | Comma-separated role IDs allowed to run deploy/admin commands. Empty = open to everyone |
| `LOG_CHANNEL_ID` | Optional channel ID for deploy/suspend logs |
| `PVE_HOST` | Proxmox host URL, e.g. `https://pve.example.com:8006` |
| `PVE_USER` | Proxmox API user, e.g. `root@pam` |
| `PVE_TOKEN_NAME` / `PVE_TOKEN_VALUE` | Proxmox API token credentials |
| `PVE_VERIFY_SSL` | `true`/`false` — verify TLS cert of Proxmox host |
| `PVE_NODE` | Node name to deploy VMs on |
| `PVE_TEMPLATE_ID` | VMID of the cloud-init template to clone |
| `PVE_STORAGE` | Storage pool for new disks |
| `PVE_BRIDGE` | Network bridge for new VMs |
| `VMID_RANGE_START` / `VMID_RANGE_END` | Range the bot may allocate new VMIDs from |
| `HOSTING_NAME` | Branding shown in embeds (default `Blined Cloud`) |

---

## Command usage

### `.create` — OS + custom CPU selection (recommended)

```
.create @user <memory_mb> <cpu_cores> <disk_gb> <os> [cpu_name] [suspend_days]
```

```
.create @Bob 2048 2 20 ubuntu22 host 30
```
Creates a VPS for `@Bob`: 2048 MB RAM, 2 cores, 20 GB disk, Ubuntu 22.04,
CPU model `host`, auto-suspends in 30 days.

- `os` must be one of the keys configured in `.env` → `PVE_OS_TEMPLATES`
  (defaults: `ubuntu20`, `ubuntu22`, `ubuntu24` — add `debian11`, `debian12`,
  etc. by preparing more templates and adding them to that variable).
- `cpu_name` is optional — any valid Proxmox CPU model (`host`, `kvm64`,
  `x86-64-v2-AES`, ...). Defaults to `PVE_DEFAULT_CPU_TYPE` (`host`).
- `suspend_days` is optional and numeric (e.g. `7`, `30`, `0.5`). Omit or
  pass `0` for a VPS that never auto-suspends.

### `.deploy` — simpler legacy command

```
.deploy @user 2048 2 20 30d
```
Same idea but no OS/CPU choice (always clones `PVE_TEMPLATE_ID`), and
`suspend_time` uses unit suffixes: `30s`, `10m`, `12h`, `7d`, `2w`, `6mo`,
`1y`, or `never`.

Run `.help` in Discord any time for the full, live command list.

---

## Project structure

```
blined-cloud-bot/
├── bot.py                 # Entry point, event loop, auto-suspend scheduler
├── config.py               # Loads .env into a Config object
├── cogs/
│   ├── deploy.py           # .deploy .list .info .suspend .unsuspend .renew .delete
│   └── help.py              # .help
├── utils/
│   ├── proxmox.py           # Proxmox VE API wrapper (real VM provisioning)
│   ├── database.py          # SQLite persistence for VPS records
│   ├── timeparse.py          # suspend_time string parsing
│   └── checks.py              # permission helpers
├── data/                    # SQLite DB lives here (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Notes on "real VPS, not containers"

This bot deliberately targets Proxmox VE's `qemu` (KVM) API endpoints rather
than `lxc` containers or Docker. Each deployed instance is a full hardware-
virtualized machine with its own virtual disk, virtual NIC, and independent
kernel — indistinguishable from a VPS sold by a commercial hosting provider.
If you'd rather provision on a different backend (e.g. a bare-metal cloud
API, libvirt directly, or VMware), swap out `utils/proxmox.py` for an
equivalent wrapper — the bot commands and database layer stay the same.

## License
MIT — do whatever you want with it.
