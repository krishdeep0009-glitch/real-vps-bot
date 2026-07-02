"""
Thin wrapper around the Proxmox VE REST API (via proxmoxer) for provisioning
REAL KVM virtual machines — full hardware-virtualized VPS, not containers.

Requires:
  - A Proxmox VE node reachable at config.PVE_HOST
  - An API token with PVEVMAdmin (or Administrator) privileges
  - A cloud-init-enabled template VM already created on the node
    (Ubuntu/Debian cloud image imported + `qm template <id>`), whose
    VMID is set in config.PVE_TEMPLATE_ID

This module clones that template, resizes CPU/RAM/disk to the requested
spec, sets a cloud-init root password, starts the VM, and waits for the
guest agent to report a real DHCP/static IP address.
"""

import secrets
import string
import time

from proxmoxer import ProxmoxAPI

from config import config


class ProvisionError(Exception):
    pass


def _client():
    return ProxmoxAPI(
        config.PVE_HOST.replace("https://", "").replace("http://", "").split(":")[0],
        port=int(config.PVE_HOST.split(":")[-1]) if ":" in config.PVE_HOST.split("//")[-1] else 8006,
        user=config.PVE_USER,
        token_name=config.PVE_TOKEN_NAME,
        token_value=config.PVE_TOKEN_VALUE,
        verify_ssl=config.PVE_VERIFY_SSL,
    )


def gen_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^*_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _wait_task(prox, node, upid, timeout=180):
    """Block until a Proxmox task (UPID) completes."""
    start = time.time()
    while time.time() - start < timeout:
        status = prox.nodes(node).tasks(upid).status.get()
        if status["status"] == "stopped":
            if status.get("exitstatus") != "OK":
                raise ProvisionError(f"Proxmox task failed: {status}")
            return
        time.sleep(2)
    raise ProvisionError(f"Timed out waiting for task {upid}")


def create_vps(vmid: int, hostname: str, memory_mb: int, cores: int, disk_gb: int,
                template_id: int = None, cpu_type: str = None):
    """
    Clone the template into a new real VM with the given specs, start it,
    and return connection info once it has booted.

    template_id: VMID of the OS-specific cloud-init template to clone
                 (defaults to config.PVE_TEMPLATE_ID).
    cpu_type:    Proxmox CPU model to expose to the guest, e.g. "host",
                 "kvm64", "x86-64-v2-AES" (defaults to config.PVE_DEFAULT_CPU_TYPE).

    Returns dict: {vmid, ip_address, root_password}
    """
    prox = _client()
    node = config.PVE_NODE
    root_password = gen_password()
    template_id = template_id or config.PVE_TEMPLATE_ID
    cpu_type = cpu_type or config.PVE_DEFAULT_CPU_TYPE

    # 1. Clone template -> new full VM (not linked clone, so it's a fully
    #    independent real VM with its own disk).
    clone_upid = prox.nodes(node).qemu(template_id).clone.post(
        newid=vmid,
        name=hostname,
        full=1,
        storage=config.PVE_STORAGE,
    )
    _wait_task(prox, node, clone_upid, timeout=300)

    # 2. Resize CPU / RAM / cloud-init user + network to spec.
    prox.nodes(node).qemu(vmid).config.post(
        cores=cores,
        sockets=1,
        cpu=cpu_type,
        memory=memory_mb,
        ciuser="root",
        cipassword=root_password,
        ipconfig0="ip=dhcp",
        net0=f"virtio,bridge={config.PVE_BRIDGE}",
        agent="enabled=1",
    )

    # 3. Grow the OS disk to the requested size (only grows, never shrinks).
    try:
        prox.nodes(node).qemu(vmid).resize.put(disk="scsi0", size=f"{disk_gb}G")
    except Exception:
        # Some templates use virtio0/ide0 instead of scsi0 — try common alternatives.
        for disk_name in ("virtio0", "ide0"):
            try:
                prox.nodes(node).qemu(vmid).resize.put(disk=disk_name, size=f"{disk_gb}G")
                break
            except Exception:
                continue

    # 4. Boot the VM.
    start_upid = prox.nodes(node).qemu(vmid).status.start.post()
    _wait_task(prox, node, start_upid, timeout=120)

    # 5. Wait for the QEMU guest agent to report a real IP address.
    ip_address = _wait_for_ip(prox, node, vmid, timeout=180)

    return {
        "vmid": vmid,
        "ip_address": ip_address or "pending (check `.info` shortly)",
        "root_password": root_password,
    }


def _wait_for_ip(prox, node, vmid, timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = prox.nodes(node).qemu(vmid).agent("network-get-interfaces").get()
            for iface in result.get("result", []):
                if iface.get("name") == "lo":
                    continue
                for addr in iface.get("ip-addresses", []):
                    if addr.get("ip-address-type") == "ipv4":
                        return addr["ip-address"]
        except Exception:
            pass
        time.sleep(5)
    return None


def suspend_vps(vmid: int):
    prox = _client()
    upid = prox.nodes(config.PVE_NODE).qemu(vmid).status.stop.post()
    _wait_task(prox, config.PVE_NODE, upid, timeout=60)


def resume_vps(vmid: int):
    prox = _client()
    upid = prox.nodes(config.PVE_NODE).qemu(vmid).status.start.post()
    _wait_task(prox, config.PVE_NODE, upid, timeout=60)


def delete_vps(vmid: int):
    prox = _client()
    # Must be stopped before deletion.
    try:
        stop_upid = prox.nodes(config.PVE_NODE).qemu(vmid).status.stop.post()
        _wait_task(prox, config.PVE_NODE, stop_upid, timeout=60)
    except Exception:
        pass
    del_upid = prox.nodes(config.PVE_NODE).qemu(vmid).delete()
    _wait_task(prox, config.PVE_NODE, del_upid, timeout=120)


def vps_status(vmid: int):
    prox = _client()
    return prox.nodes(config.PVE_NODE).qemu(vmid).status.current.get()
