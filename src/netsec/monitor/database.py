"""Small SQLite repository with explicit transaction boundaries."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def identifier():
    return uuid.uuid4().hex


class Database:
    def __init__(self, path):
        self.backend = 'postgres' if str(path).startswith(('postgresql://', 'postgres://')) else 'sqlite'
        self.dsn = str(path) if self.backend == 'postgres' else None
        base = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
        extension = (Path(__file__).parent.parent / 'saas' / 'schema.sql').read_text(encoding='utf-8')
        if self.backend == 'postgres':
            import psycopg
            from netsec.monitor.postgres import initialize
            with psycopg.connect(self.dsn) as conn:
                conn.execute('SELECT pg_advisory_xact_lock(846291)')
                initialize(conn, base, extension)
                version = conn.execute('SELECT max(version) FROM schema_version').fetchone()[0]
                if version != 1:
                    raise ValueError('Unsupported database schema')
            self.path = None
            return
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect(write=True) as conn:
            conn.executescript(base + extension)
            version = conn.execute("SELECT max(version) FROM schema_version").fetchone()[0]
            if version != 1:
                raise ValueError("Unsupported database schema; restore a compatible backup")

    @contextmanager
    def connect(self, *, write=False):
        if self.backend == 'postgres':
            import psycopg
            from netsec.monitor.postgres import Connection, row_factory
            with psycopg.connect(self.dsn, row_factory=row_factory) as conn:
                # Preserve atomic quota, dedup and lease claims across API/worker processes.
                if write:
                    conn.execute('SELECT pg_advisory_xact_lock(846292)')
                yield Connection(conn)
            return
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def audit(conn, org_id, actor_id, action, target_id="", detail=None):
    conn.execute("INSERT INTO audit(org_id,actor_id,action,target_id,detail,created_at) VALUES(?,?,?,?,?,?)",
                 (org_id, actor_id, action, target_id, json.dumps(detail or {}, ensure_ascii=False), now()))
