import sqlite3
import time
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "blined.db"
DB_PATH.parent.mkdir(exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS vps (
    vmid INTEGER PRIMARY KEY,
    discord_id INTEGER NOT NULL,
    hostname TEXT NOT NULL,
    memory_mb INTEGER NOT NULL,
    cores INTEGER NOT NULL,
    disk_gb INTEGER NOT NULL,
    ip_address TEXT,
    root_password TEXT,
    status TEXT DEFAULT 'running',
    created_at INTEGER NOT NULL,
    suspend_at INTEGER,          -- unix timestamp, NULL = never
    suspended INTEGER DEFAULT 0
);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(_conn()) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def add_vps(vmid, discord_id, hostname, memory_mb, cores, disk_gb,
            ip_address, root_password, suspend_at):
    with closing(_conn()) as conn:
        conn.execute(
            """INSERT INTO vps
               (vmid, discord_id, hostname, memory_mb, cores, disk_gb,
                ip_address, root_password, status, created_at, suspend_at, suspended)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, 0)""",
            (vmid, discord_id, hostname, memory_mb, cores, disk_gb,
             ip_address, root_password, int(time.time()), suspend_at),
        )
        conn.commit()


def get_vps(vmid):
    with closing(_conn()) as conn:
        row = conn.execute("SELECT * FROM vps WHERE vmid = ?", (vmid,)).fetchone()
        return dict(row) if row else None


def list_vps(discord_id=None):
    with closing(_conn()) as conn:
        if discord_id:
            rows = conn.execute(
                "SELECT * FROM vps WHERE discord_id = ? ORDER BY created_at DESC", (discord_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vps ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_vps(vmid):
    with closing(_conn()) as conn:
        conn.execute("DELETE FROM vps WHERE vmid = ?", (vmid,))
        conn.commit()


def set_suspended(vmid, suspended: bool):
    with closing(_conn()) as conn:
        conn.execute(
            "UPDATE vps SET suspended = ?, status = ? WHERE vmid = ?",
            (1 if suspended else 0, "suspended" if suspended else "running", vmid),
        )
        conn.commit()


def update_suspend_at(vmid, suspend_at):
    with closing(_conn()) as conn:
        conn.execute("UPDATE vps SET suspend_at = ? WHERE vmid = ?", (suspend_at, vmid))
        conn.commit()


def due_for_suspension():
    """Return VPS rows whose suspend_at has passed and are not yet suspended."""
    now = int(time.time())
    with closing(_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM vps WHERE suspend_at IS NOT NULL AND suspend_at <= ? AND suspended = 0",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]


def next_free_vmid(start, end):
    with closing(_conn()) as conn:
        used = {r["vmid"] for r in conn.execute("SELECT vmid FROM vps").fetchall()}
    for vmid in range(start, end + 1):
        if vmid not in used:
            return vmid
    return None
