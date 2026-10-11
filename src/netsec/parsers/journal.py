"""Adapter for newline-delimited `journalctl -o json` exports."""

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from netsec.models import AuthEvent, ParseResult
from netsec.parsers.common import collect_lines
from netsec.parsers.ssh import parse_line as parse_ssh_line


def parse_line(line: str, line_number: int) -> AuthEvent | None:
    record = json.loads(line)
    if not isinstance(record, dict):
        raise ValueError("Each journal line must be an object")
    if record.get("SYSLOG_IDENTIFIER", record.get("_COMM")) not in {"sshd", "sshd-session"}:
        return None
    stamp = record.get("__REALTIME_TIMESTAMP")
    host, message = record.get("_HOSTNAME"), record.get("MESSAGE")
    if not isinstance(stamp, str) or not stamp.isascii() or not stamp.isdigit():
        raise ValueError("Journal record needs __REALTIME_TIMESTAMP in microseconds")
    if not isinstance(host, str) or not host or any(char.isspace() for char in host):
        raise ValueError("Journal record needs a hostname")
    if not isinstance(message, str):
        raise ValueError("Binary or repeated journal MESSAGE fields are unsupported")
    timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(stamp))
    return parse_ssh_line(f"{timestamp.isoformat()} {host} sshd: {message}", line_number)


def parse_lines(lines: Iterable[str]) -> ParseResult:
    return collect_lines(lines, parse_line)
