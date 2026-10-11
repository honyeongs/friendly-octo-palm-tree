"""Durable, leased notification delivery. Missing external settings are harmless."""

import json
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from netsec.monitor.database import now


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deliver(settings, channel, org, incident, delivery_id):
    if channel == "in_app":
        return "sent"
    # Minimal external payload: raw evidence, user identifiers and IPs stay in the UI.
    payload = {"delivery_id": delivery_id, "organization_id": org["id"], "incident_id": incident["id"],
               "rule": incident["rule"], "severity": incident["severity"], "title": incident["title"],
               "url": settings.origin + "/#incidents/" + incident["id"]}
    if channel == "webhook":
        if not settings.webhook_url or not org["webhook_enabled"]:
            return "skipped"
        headers = {"Content-Type": "application/json", "Idempotency-Key": delivery_id}
        if settings.webhook_token:
            headers["Authorization"] = "Bearer " + settings.webhook_token
        request = urllib.request.Request(settings.webhook_url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise OSError("Webhook delivery failed")
    elif channel == "email":
        if not settings.smtp_host or not settings.smtp_from or not org["notification_email"]:
            return "skipped"
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = org["notification_email"]
        message["Subject"] = "[NetSec] " + incident["title"]
        message["Message-ID"] = f"<{delivery_id}@netsec.local>"
        message.set_content(json.dumps(payload, ensure_ascii=False, indent=2))
        context = ssl.create_default_context()
        smtp_class = smtplib.SMTP_SSL if settings.smtp_tls == "ssl" else smtplib.SMTP
        kwargs = {"context": context} if settings.smtp_tls == "ssl" else {}
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=10, **kwargs) as smtp:
            if settings.smtp_tls == "starttls":
                smtp.starttls(context=context)
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    return "sent"


def dispatch_one(db, settings, sender=deliver):
    stamp = now()
    with db.connect(write=True) as conn:
        row = conn.execute("SELECT * FROM outbox WHERE (status='pending' AND next_at<=?) "
                           "OR (status='processing' AND lease_until<=?) ORDER BY created_at,id LIMIT 1", (stamp, stamp)).fetchone()
        if row is None:
            return False
        lease = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(timespec="microseconds")
        conn.execute("UPDATE outbox SET status='processing',attempts=attempts+1,lease_until=? WHERE id=?", (lease, row["id"]))
        org = conn.execute("SELECT * FROM organizations WHERE id=?", (row["org_id"],)).fetchone()
        incident = conn.execute("SELECT * FROM incidents WHERE id=?", (row["incident_id"],)).fetchone()
    try:
        status = sender(settings, row["channel"], org, incident, row["id"])
        error = ""
    except Exception:
        # Exception text can contain passwords, URLs or SMTP responses; never persist it.
        status = "failed" if row["attempts"] + 1 >= 5 else "pending"
        error = "외부 전송 실패. 서버 설정과 수신 서비스 상태를 확인하세요."
    delay = min(3600, 30 * 2 ** row["attempts"])
    next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="microseconds")
    with db.connect(write=True) as conn:
        conn.execute("UPDATE outbox SET status=?,error=?,next_at=?,lease_until=NULL WHERE id=? AND lease_until=?",
                     (status, error, next_at, row["id"], lease))
    return True


class Worker:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="netsec-notifications", daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        last_cleanup = -86400
        while not self.stop_event.is_set():
            try:
                if time.monotonic() - last_cleanup >= 86400:
                    from netsec.monitor.maintenance import prune
                    prune(self.db, self.settings.retention_days)
                    last_cleanup = time.monotonic()
                has_work = dispatch_one(self.db, self.settings)
            except Exception:
                has_work = False
            if not has_work:
                self.stop_event.wait(2)

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=25)
