import re
import time

UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "mo": 2592000,  # 30 days
    "y": 31536000,
}

PATTERN = re.compile(r"^(\d+)(mo|[smhdwy])$", re.IGNORECASE)


def parse_duration(value: str):
    """
    Parse strings like '30d', '12h', '1w', '6mo', 'never' into a unix
    timestamp (suspend_at) or None for 'never'.
    """
    if value is None:
        return None
    value = value.strip().lower()
    if value in ("never", "none", "0", "off"):
        return None

    match = PATTERN.match(value)
    if not match:
        raise ValueError(
            "Invalid suspend time. Use formats like 30d, 12h, 6mo, 1w, 1y, or 'never'."
        )
    amount, unit = match.groups()
    seconds = int(amount) * UNITS[unit]
    return int(time.time()) + seconds


def humanize_remaining(suspend_at):
    if suspend_at is None:
        return "Never"
    remaining = suspend_at - int(time.time())
    if remaining <= 0:
        return "Due now"
    days, rem = divmod(remaining, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "<1m"
