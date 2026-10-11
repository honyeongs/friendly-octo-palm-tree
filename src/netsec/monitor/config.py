"""Environment settings. No third-party service is required."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database: Path = Path("data/netsec.sqlite3")
    origin: str = "http://127.0.0.1:8890"
    session_hours: int = 8
    retention_days: int = 30
    webhook_url: str = ""
    webhook_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: str = "starttls"

    @property
    def secure(self):
        return self.origin.startswith("https://")

    def validate(self):
        parsed = urlsplit(self.origin)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("NETSEC_ORIGIN must be a single HTTP(S) origin")
        if not self.secure and parsed.hostname not in ("localhost", "127.0.0.1", "::1", "testserver"):
            raise ValueError("Non-loopback deployments require an HTTPS NETSEC_ORIGIN")
        if not 1 <= self.retention_days <= 3650 or not 1 <= self.session_hours <= 24:
            raise ValueError("Invalid retention days or session hours")
        if self.webhook_url:
            target = urlsplit(self.webhook_url)
            if target.scheme != "https" or not target.hostname or target.username or target.fragment:
                raise ValueError("Webhook requires HTTPS without userinfo or fragment")
        if self.smtp_tls not in ("starttls", "ssl"):
            raise ValueError("SMTP requires starttls or ssl")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("Invalid SMTP port")
        return self

    @classmethod
    def from_env(cls):
        return cls(
            database=Path(os.getenv("NETSEC_DB", "data/netsec.sqlite3")),
            origin=os.getenv("NETSEC_ORIGIN", "http://127.0.0.1:8890").rstrip("/"),
            session_hours=int(os.getenv("NETSEC_SESSION_HOURS", "8")),
            retention_days=int(os.getenv("NETSEC_RETENTION_DAYS", "30")),
            webhook_url=os.getenv("NETSEC_WEBHOOK_URL", ""),
            webhook_token=os.getenv("NETSEC_WEBHOOK_TOKEN", ""),
            smtp_host=os.getenv("NETSEC_SMTP_HOST", ""),
            smtp_port=int(os.getenv("NETSEC_SMTP_PORT", "587")),
            smtp_user=os.getenv("NETSEC_SMTP_USER", ""),
            smtp_password=os.getenv("NETSEC_SMTP_PASSWORD", ""),
            smtp_from=os.getenv("NETSEC_SMTP_FROM", ""),
            smtp_tls=os.getenv("NETSEC_SMTP_TLS", "starttls"),
        ).validate()
