"""Persistent monitoring contracts, permissions and security regressions."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    from netsec.monitor.app import create_app
except ImportError:
    TestClient = None

from netsec.sdk import MonitorClient


@unittest.skipIf(TestClient is None, "Install .[monitor,test] for monitoring tests")
class MonitorTests(unittest.TestCase):
    def setUp(self):
        from netsec.monitor.config import Settings
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "monitor.sqlite3"
        self.settings = Settings(database=self.path, origin="http://testserver")
        self.app = create_app(self.settings, run_worker=False)
        self.client = TestClient(self.app)
        self.client.headers.update({"Origin": "http://testserver"})
        result = self.client.post("/api/setup", json={"organization": "Alpha", "display_name": "Admin", "email": "admin@example.test", "password": "correct horse battery"})
        self.assertEqual(result.status_code, 200, result.text)
        self.org_id = result.json()["org_id"]
        self.login()
        result = self.client.post("/api/sources", json={"name": "app-a", "kind": "app"})
        self.assertEqual(result.status_code, 201, result.text)
        self.source = result.json()

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def login(self, client=None, email="admin@example.test", password="correct horse battery", org_id=None):
        client = client or self.client
        response = client.post("/api/login", json={"org_id": org_id or self.org_id, "email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        return response.json()

    def events(self, count=6, *, host="app-a", address="192.0.2.5", prefix="e", start=None):
        start = start or datetime.now(timezone.utc) - timedelta(seconds=90)
        return [{"event_id": f"{prefix}{i}", "timestamp": (start + timedelta(seconds=i * 5)).isoformat(),
                 "outcome": "success" if i == count - 1 and count >= 6 else "failure", "source_ip": address,
                 "username": "alice", "host": host} for i in range(count)]

    def send(self, events, client=None, key=None):
        return (client or self.client).post("/api/v1/events", json={"events": events}, headers={"Authorization": "Bearer " + (key or self.source["token"])})

    def incident(self):
        response = self.send(self.events())
        self.assertEqual(response.status_code, 202, response.text)
        return self.client.get("/api/incidents").json()["items"][0]

    def second_org(self):
        from netsec.monitor.accounts import create_organization
        from netsec.monitor.schemas import Setup
        with self.app.state.db.connect(write=True) as conn:
            org_id = create_organization(conn, Setup(organization="Beta", display_name="Beta admin", email="beta@example.test", password="another correct password"))
        other = TestClient(self.app); self.addCleanup(other.close)
        other.headers["Origin"] = "http://testserver"
        self.login(other, "beta@example.test", "another correct password", org_id)
        return other, org_id

    def test_setup_one_time(self):
        self.assertFalse(self.client.get("/api/setup").json()["required"])
        self.assertEqual(self.client.post("/api/setup", json={"organization": "Other", "email": "a@b.test", "display_name": "A", "password": "long secure password"}).status_code, 409)

    def test_ingestion_detects_and_deduplicates(self):
        events = self.events()
        result = self.send(events).json()
        self.assertEqual(result, {"accepted": 6, "duplicates": 0, "incidents_created": 2})
        self.assertEqual(self.send(events).json(), {"accepted": 0, "duplicates": 6, "incidents_created": 0})
        self.assertEqual(self.client.get("/api/events").json()["total"], 6)
        self.assertEqual(self.client.get("/api/notifications").json()["total"], 6)

    def test_cross_batch_and_out_of_order(self):
        events = self.events()
        self.assertEqual(self.send(events[3:]).status_code, 202)
        self.assertEqual(self.send(events[:3][::-1]).json()["incidents_created"], 2)

    def test_conflicting_id_rolls_back_whole_batch(self):
        events = self.events(1)
        self.send(events)
        changed = {**events[0], "username": "changed"}
        response = self.send([{**events[0], "event_id": "new"}, changed])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/events").json()["total"], 1)

    def test_repeated_episode_extends_without_alert_storm(self):
        start = datetime.now(timezone.utc) - timedelta(seconds=100)
        events = self.events(5, start=start)
        self.send(events)
        for i in range(5, 12):
            self.send([{**events[0], "event_id": f"e{i}", "timestamp": (start + timedelta(seconds=i * 5)).isoformat()}])
        self.assertEqual(self.client.get("/api/incidents").json()["total"], 1)
        self.assertEqual(self.client.get("/api/notifications").json()["total"], 3)

    def test_two_hosts_do_not_combine(self):
        self.send(self.events(3, host="one", prefix="one"))
        self.send(self.events(3, host="two", prefix="two"))
        self.assertEqual(self.client.get("/api/incidents").json()["total"], 0)

    def test_isolation_lists_details_mutations_and_assignees(self):
        item = self.incident()
        other, _ = self.second_org()
        for route in ("incidents", "events", "sources", "notifications"):
            data = other.get("/api/" + route).json()
            self.assertEqual(data.get("total", len(data.get("items", []))), 0)
        self.assertTrue(all(row["org_id"] != self.org_id for row in other.get("/api/audit").json()["items"]))
        self.assertEqual(other.get(f"/api/incidents/{item['id']}").status_code, 404)
        self.assertEqual(other.patch(f"/api/incidents/{item['id']}", json={"version": item["version"], "status": "resolved"}).status_code, 404)
        self.assertEqual(other.post(f"/api/incidents/{item['id']}/comments", json={"body": "bad"}).status_code, 404)
        self.assertEqual(other.request("DELETE", f"/api/sources/{self.source['id']}", json={}).status_code, 404)
        self.assertEqual(other.post("/api/exclusions", json={"source_id": self.source["id"], "cidr": "192.0.2.5/32", "reason": "bad", "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}).status_code, 404)

    def test_viewer_cannot_write_and_analyst_can_investigate(self):
        item = self.incident()
        for role in ("viewer", "analyst"):
            email = role + "@example.test"
            self.client.post("/api/users", json={"email": email, "display_name": role, "password": "a twelve char password", "role": role})
            client = TestClient(self.app); self.addCleanup(client.close); client.headers["Origin"] = "http://testserver"
            self.login(client, email, "a twelve char password")
            response = client.patch(f"/api/incidents/{item['id']}", json={"version": item["version"], "status": "investigating"})
            self.assertEqual(response.status_code, 403 if role == "viewer" else 200)
            self.assertEqual(client.post("/api/sources", json={"name": "no", "kind": "app"}).status_code, 403)
            self.assertEqual(client.get("/api/audit").status_code, 403)

    def test_csrf_and_origin(self):
        headers = {"X-CSRF-Token": "wrong"}
        self.assertEqual(self.client.post("/api/logout", json={}, headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/sources", json={"name": "no"}, headers={"Origin": "https://evil.test"}).status_code, 403)
        anonymous = TestClient(self.app); self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.post("/api/login", json={"org_id": self.org_id, "email": "admin@example.test", "password": "correct horse battery"}).status_code, 403)

    def test_passwords_and_source_tokens_not_persisted_plaintext(self):
        with self.app.state.db.connect() as conn:
            user = conn.execute("SELECT password_hash FROM users").fetchone()[0]
            token_hash = conn.execute("SELECT token_hash FROM sources").fetchone()[0]
            audit = " ".join(row[0] for row in conn.execute("SELECT detail FROM audit"))
        self.assertNotIn("correct horse", user)
        self.assertNotEqual(token_hash, self.source["token"])
        self.assertNotIn(self.source["token"], audit)
        self.assertNotIn("token", self.client.get("/api/sources").text)

    def test_cookie_flags_and_session_revocation(self):
        self.login()
        self.assertTrue(self.client.cookies.get("netsec_session"))
        response = self.client.post("/api/password", json={"current_password": "correct horse battery", "new_password": "changed password now"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.login(password="changed password now")

    def test_validation_does_not_echo_secrets(self):
        secret = "super secret credential"
        response = self.client.post("/api/users", json={"email": "invalid", "display_name": "A", "password": secret, "unknown": secret})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)

    def test_body_limit_and_timestamp_validation(self):
        self.assertEqual(self.client.post("/api/v1/events", content=b"x" * (1024 * 1024 + 1)).status_code, 413)
        event = self.events(1)[0]
        self.assertEqual(self.send([{**event, "timestamp": "2026-01-01T12:00:00"}]).status_code, 422)
        self.assertEqual(self.send([{**event, "timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}]).status_code, 422)
        self.assertEqual(self.send([{**event, "access_token": "not-allowed"}]).status_code, 422)

    def test_source_revocation(self):
        self.assertEqual(self.client.request("DELETE", f"/api/sources/{self.source['id']}", json={}).status_code, 200)
        self.assertEqual(self.send(self.events()).status_code, 401)

    def test_incident_version_comments_and_export(self):
        item = self.incident()
        self.assertEqual(self.client.patch(f"/api/incidents/{item['id']}", json={"version": item["version"], "status": "resolved"}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/incidents/{item['id']}", json={"version": item["version"], "status": "open"}).status_code, 409)
        self.client.post(f"/api/incidents/{item['id']}/comments", json={"body": "<script>alert(1)</script>"})
        detail = self.client.get(f"/api/incidents/{item['id']}").json()
        self.assertEqual(detail["comments"][0]["body"], "<script>alert(1)</script>")
        self.assertEqual(len(self.client.get("/api/export").json()["incidents"]), 2)

    def test_policy_and_expiring_exclusion(self):
        result = self.client.post("/api/exclusions", json={"source_id": self.source["id"], "cidr": "192.0.2.5/32", "reason": "lab", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
        self.assertEqual(result.status_code, 201, result.text)
        self.send(self.events())
        self.assertEqual(self.client.get("/api/incidents").json()["total"], 0)
        self.assertEqual(self.client.get("/api/events").json()["total"], 6)

    def test_persistence_backup_and_retention(self):
        from netsec.monitor.maintenance import backup, prune
        self.incident()
        second = create_app(self.settings, run_worker=False)
        with second.state.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM incidents").fetchone()[0], 2)
        target = backup(self.app.state.db, Path(self.temp.name) / "backup.sqlite3")
        with closing(sqlite3.connect(target)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM events").fetchone()[0], 6)
        with self.assertRaises(ValueError):
            backup(self.app.state.db, target)
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("UPDATE events SET timestamp='2000-01-01T00:00:00.000000+00:00'")
            conn.execute("UPDATE incidents SET last_seen='2000-01-01T00:00:00.000000+00:00'")
        self.assertEqual(prune(self.app.state.db, 30)["events_removed"], 6)
        self.assertEqual(self.client.get("/api/notifications").json()["total"], 0)

    def test_notification_missing_config_and_retry(self):
        from netsec.monitor.notifications import dispatch_one
        self.incident()
        while dispatch_one(self.app.state.db, self.settings):
            pass
        statuses = [item["status"] for item in self.client.get("/api/notifications").json()["items"]]
        self.assertEqual(statuses.count("sent"), 2)
        self.assertEqual(statuses.count("skipped"), 4)

    def test_notification_errors_redact_and_backoff(self):
        from netsec.monitor.notifications import dispatch_one
        self.incident()
        def failing(*args):
            raise OSError("https://SECRET_TOKEN.example/password")
        dispatch_one(self.app.state.db, self.settings, sender=failing)
        rows = self.client.get("/api/notifications").json()["items"]
        failed = [row for row in rows if row["attempts"] == 1][0]
        self.assertEqual(failed["status"], "pending")
        self.assertNotIn("SECRET_TOKEN", failed["error"])

    def test_login_throttling(self):
        payload = {"org_id": self.org_id, "email": "missing@example.test", "password": "wrong"}
        for _ in range(10):
            self.assertEqual(self.client.post("/api/login", json=payload).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json=payload).status_code, 429)

    def test_host_guard_and_security_headers(self):
        self.assertEqual(self.client.get("/", headers={"Host": "evil.test"}).status_code, 400)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(self.client.get("/docs").status_code, 404)
        self.assertEqual(self.client.get("/ui/app.js").status_code, 200)

    def test_cross_org_assignment_user_mutation_and_notification_retry(self):
        item = self.incident()
        other, _ = self.second_org()
        other_user = other.get("/api/me").json()["id"]
        self.assertEqual(self.client.patch(f"/api/incidents/{item['id']}", json={"version": item["version"], "status": "open", "assignee_id": other_user}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/users/{other_user}", json={"role": "viewer", "active": False}).status_code, 404)
        alert = self.client.get("/api/notifications").json()["items"][0]
        self.assertEqual(other.post(f"/api/notifications/{alert['id']}/retry", json={}).status_code, 404)

    def test_disabled_user_loses_session_immediately(self):
        created = self.client.post("/api/users", json={"email": "staff@example.test", "display_name": "Staff", "password": "staff long password", "role": "analyst"}).json()
        staff = TestClient(self.app); self.addCleanup(staff.close); staff.headers["Origin"] = "http://testserver"
        self.login(staff, "staff@example.test", "staff long password")
        self.client.patch("/api/users/" + created["id"], json={"role": "analyst", "active": False})
        self.assertEqual(staff.get("/api/me").status_code, 401)

    def test_notification_success_uses_stable_delivery_identity(self):
        from netsec.monitor.notifications import dispatch_one
        self.incident()
        calls = []
        def sender(settings, channel, org, incident, delivery_id):
            calls.append((channel, org["id"], incident["id"], delivery_id))
            return "sent"
        while dispatch_one(self.app.state.db, self.settings, sender=sender):
            pass
        self.assertEqual(len(calls), 6)
        self.assertEqual(len({item[3] for item in calls}), 6)
        self.assertTrue(all(item[1] == self.org_id for item in calls))

    def test_policy_updates_detection_without_deleting_history(self):
        response = self.client.put("/api/policy", json={"threshold": 3, "window_seconds": 60, "success_seconds": 300})
        self.assertEqual(response.status_code, 200)
        self.send(self.events(3))
        self.assertEqual(self.client.get("/api/incidents").json()["total"], 1)
        self.assertEqual(self.client.get("/api/events").json()["total"], 3)

    def test_https_setup_closed_and_cookie_secure(self):
        from netsec.monitor.accounts import create_organization
        from netsec.monitor.config import Settings
        from netsec.monitor.schemas import Setup
        secure_app = create_app(Settings(database=Path(self.temp.name) / "secure.sqlite3", origin="https://testserver"), run_worker=False)
        with secure_app.state.db.connect(write=True) as conn:
            org_id = create_organization(conn, Setup(organization="Secure", display_name="Admin", email="tls@example.test", password="long secure password"))
        client = TestClient(secure_app, base_url="https://testserver"); self.addCleanup(client.close); client.headers["Origin"] = "https://testserver"
        self.assertEqual(client.post("/api/setup", json={"organization": "No", "display_name": "A", "email": "a@b.test", "password": "long enough password"}).status_code, 403)
        response = client.post("/api/login", json={"org_id": org_id, "email": "tls@example.test", "password": "long secure password"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Secure", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])

    def test_password_whitespace_is_significant(self):
        from netsec.monitor.security import hash_password, verify_password
        value = "  a password with spaces  "
        hashed = hash_password(value)
        self.assertTrue(verify_password(value, hashed))
        self.assertFalse(verify_password(value.strip(), hashed))

    def test_old_event_rejected_and_batch_size_bounded(self):
        event = self.events(1)[0]
        event["timestamp"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        self.assertEqual(self.send([event]).status_code, 422)
        self.assertEqual(self.send(self.events(201)).status_code, 422)


class SDKTests(unittest.TestCase):
    def test_outbox_survives_restart_and_network_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "outbox.sqlite3"
            client = MonitorClient("http://127.0.0.1:1", "not-a-real-key", path, timeout=.1)
            event_id = client.emit(outcome="failure", source_ip="192.0.2.1", username="test")
            self.assertIsNotNone(event_id)
            self.assertEqual(client.flush(), 0)
            self.assertEqual(MonitorClient("http://127.0.0.1:1", "key", path).status(), {"pending": 1})

    def test_remote_plaintext_rejected(self):
        with self.assertRaises(ValueError):
            MonitorClient("http://example.com", "key")

    def test_agent_cursor_reuses_ids(self):
        from netsec.monitor.agent import collect
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as folder:
            client = MonitorClient("http://127.0.0.1:1", "key", Path(folder) / "queue.sqlite3")
            collect(client, root / "samples/ssh/correlated.log", "auto")
            count = client.status()["pending"]
            collect(client, root / "samples/ssh/correlated.log", "auto")
            self.assertEqual(client.status()["pending"], count)


if __name__ == "__main__":
    unittest.main()
