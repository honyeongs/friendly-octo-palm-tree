"""Operator-only, consistent SQLite backup and retention cleanup."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from netsec.monitor.database import audit, now


def backup(db, destination):
    target = Path(destination)
    if target.exists() or target.resolve() == db.path.resolve():
        raise ValueError("Backup destination must be a new file, not the active database")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement even with concurrent operators.
    with target.open("xb"):
        pass
    try:
        with db.connect() as source:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            finally:
                dest.close()
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def prune(db, retention_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="microseconds")
    with db.connect(write=True) as conn:
        organizations = conn.execute("SELECT id FROM organizations").fetchall()
        events = conn.execute("DELETE FROM events WHERE timestamp<?", (cutoff,)).rowcount
        incidents = conn.execute("DELETE FROM incidents WHERE last_seen<?", (cutoff,)).rowcount
        audits = conn.execute("DELETE FROM audit WHERE created_at<?", (cutoff,)).rowcount
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now(),))
        conn.execute("DELETE FROM exclusions WHERE expires_at<=?", (now(),))
        for org in organizations:
            audit(conn, org["id"], "operator", "retention.prune", detail={"cutoff": cutoff})
    return {"events_removed": events, "incidents_removed": incidents, "audit_removed": audits}
