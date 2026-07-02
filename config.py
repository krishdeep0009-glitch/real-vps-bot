import os
from dotenv import load_dotenv

load_dotenv()


def _bool(val: str, default=False):
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def _int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


class Config:
    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
    COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", ".")
    ADMIN_ROLE_IDS = [
        int(r) for r in os.getenv("ADMIN_ROLE_IDS", "").split(",") if r.strip().isdigit()
    ]
    LOG_CHANNEL_ID = _int(os.getenv("LOG_CHANNEL_ID"), None)

    # Proxmox
    PVE_HOST = os.getenv("PVE_HOST", "")
    PVE_USER = os.getenv("PVE_USER", "root@pam")
    PVE_TOKEN_NAME = os.getenv("PVE_TOKEN_NAME", "")
    PVE_TOKEN_VALUE = os.getenv("PVE_TOKEN_VALUE", "")
    PVE_VERIFY_SSL = _bool(os.getenv("PVE_VERIFY_SSL"), False)
    PVE_NODE = os.getenv("PVE_NODE", "pve1")
    PVE_TEMPLATE_ID = _int(os.getenv("PVE_TEMPLATE_ID"), 9000)
    PVE_STORAGE = os.getenv("PVE_STORAGE", "local-lvm")
    PVE_BRIDGE = os.getenv("PVE_BRIDGE", "vmbr0")
    PVE_DEFAULT_CPU_TYPE = os.getenv("PVE_DEFAULT_CPU_TYPE", "host")

    @staticmethod
    def _parse_os_templates(raw: str):
        mapping = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            key, val = pair.split("=", 1)
            if val.strip().isdigit():
                mapping[key.strip().lower()] = int(val.strip())
        return mapping

    PVE_OS_TEMPLATES = _parse_os_templates.__func__(
        os.getenv("PVE_OS_TEMPLATES", "ubuntu20=9020,ubuntu22=9022,ubuntu24=9024")
    )

    VMID_RANGE_START = _int(os.getenv("VMID_RANGE_START"), 10000)
    VMID_RANGE_END = _int(os.getenv("VMID_RANGE_END"), 19999)

    HOSTING_NAME = os.getenv("HOSTING_NAME", "Blined Cloud")


config = Config()
