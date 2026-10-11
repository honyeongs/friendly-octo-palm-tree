"""Dependency-free application client with a durable local outbox.

emit() does local I/O only. Network failures never block application login.
The background worker retries with stable event IDs; the server deduplicates.
"""

import ipaddress
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MonitorClient:
    def __init__(self, endpoint, source_key, outbox="data/app-outbox.sqlite3", *, timeout=3):
        url = urlsplit(endpoint)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.fragment or url.query:
            raise ValueError("Invalid monitor origin")
        if url.scheme != "https" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Remote collection requires HTTPS")
        if url.path not in ("", "/"):
            raise ValueError("Endpoint must be an origin, without a path")
        self.endpoint, self.source_key, self.timeout = endpoint.rstrip("/"), source_key, timeout
        self.path = Path(outbox)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stop_event = threading.Event()
        self.thread = None
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS queue(event_id TEXT PRIMARY KEY,payload TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,"
                         "next_at REAL NOT NULL DEFAULT 0,lease_until REAL NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending')")
            conn.execute("CREATE TABLE IF NOT EXISTS agent_seen(event_id TEXT PRIMARY KEY,created REAL NOT NULL)")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=3)
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def emit(self, *, outcome, source_ip, username, host="app", method="password", event_type="auth.login",
             event_id=None, timestamp=None, remember=False):
        """Queue an allowlisted event; return None on local failure or full queue."""
        if outcome not in ("success", "failure") or event_type not in ("auth.login", "password.change", "role.change"):
            raise ValueError("Unsupported outcome or event type")
        stamp = timestamp or datetime.now(timezone.utc).isoformat()
        value = datetime.fromisoformat(stamp)
        if value.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        payload = {"event_id": event_id or uuid.uuid4().hex, "timestamp": stamp, "event_type": event_type,
                   "outcome": outcome, "source_ip": str(ipaddress.ip_address(source_ip)),
                   "username": username, "host": host, "method": method}
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if remember and conn.execute("SELECT 1 FROM agent_seen WHERE event_id=?", (payload["event_id"],)).fetchone():
                    return payload["event_id"]
                if conn.execute("SELECT count(*) FROM queue").fetchone()[0] >= 10000:
                    return None
                conn.execute("INSERT OR IGNORE INTO queue(event_id,payload) VALUES(?,?)", (payload["event_id"], json.dumps(payload)))
                if remember:
                    conn.execute("INSERT OR IGNORE INTO agent_seen VALUES(?,?)", (payload["event_id"], time.time()))
                    conn.execute("DELETE FROM agent_seen WHERE created<?", (time.time() - 30 * 86400,))
            return payload["event_id"]
        except (OSError, sqlite3.Error):
            return None

    def flush(self):
        clock = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT event_id,payload,attempts FROM queue WHERE state='pending' AND next_at<=? AND lease_until<=? "
                                "ORDER BY rowid LIMIT 200", (clock, clock)).fetchall()
            if not rows:
                return 0
            conn.executemany("UPDATE queue SET lease_until=? WHERE event_id=?", [(clock + 30, row[0]) for row in rows])
        body = json.dumps({"events": [json.loads(row[1]) for row in rows]}).encode()
        request = urllib.request.Request(self.endpoint + "/api/v1/events", data=body,
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.source_key}, method="POST")
        permanent = False
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                if response.status != 202:
                    raise OSError("Unexpected collector response")
                result = json.loads(response.read(65536))
                if result.get("accepted", 0) + result.get("duplicates", 0) != len(rows):
                    raise OSError("Incomplete collector acknowledgement")
        except urllib.error.HTTPError as error:
            permanent = error.code in (400, 401, 403, 404, 409, 413, 415, 422)
        except (OSError, ValueError):
            pass
        else:
            with self._connect() as conn:
                conn.executemany("DELETE FROM queue WHERE event_id=?", [(row[0],) for row in rows])
            return len(rows)
        with self._connect() as conn:
            conn.executemany("UPDATE queue SET state=?,attempts=attempts+1,next_at=?,lease_until=0 WHERE event_id=?",
                             [("dead" if permanent else "pending", clock + min(300, 2 ** min(row[2] + 1, 8)), row[0]) for row in rows])
        return 0

    def status(self):
        with self._connect() as conn:
            return dict(conn.execute("SELECT state,count(*) FROM queue GROUP BY state").fetchall())

    def retry_dead(self):
        with self._connect() as conn:
            conn.execute("UPDATE queue SET state='pending',next_at=0,lease_until=0 WHERE state='dead'")

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name="netsec-sdk")
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.flush()
            except (OSError, sqlite3.Error):
                pass
            self.stop_event.wait(2)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.timeout + 3)
