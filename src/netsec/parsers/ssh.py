"""Parse explicitly timestamped OpenSSH authentication log lines."""

import re
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Iterable

from netsec.models import AuthEvent, ParseResult
from netsec.parsers.common import collect_lines

_ENVELOPE = re.compile(
    r"^(?P<timestamp>\S+)\s+(?P<host>\S+)\s+"
    r"sshd(?:-session)?(?:\[\d+\])?:\s+(?P<message>.*)$"
)
_METHODS = r"(?:password|publickey|keyboard-interactive/pam)"
_CANDIDATE = re.compile(rf"^(?:Failed|Accepted) {_METHODS}\b")
_ANY_CANDIDATE = re.compile(
    rf"\bsshd(?:-session)?(?:\[\d+\])?:\s+(?:Failed|Accepted) {_METHODS}\b"
)
_AUTH = re.compile(
    rf"^(?P<outcome>Failed|Accepted) (?P<method>{_METHODS}) for "
    r"(?P<invalid>invalid user )?(?P<username>\S+) from (?P<ip>\S+) "
    r"port (?P<port>\d+) ssh2(?::)?(?:\s+.*)?$"
)


def parse_line(line: str, line_number: int) -> AuthEvent | None:
    """Return None for unrelated logs; raise ValueError for malformed auth logs."""
    envelope = _ENVELOPE.fullmatch(line.strip())
    if envelope is None:
        if _ANY_CANDIDATE.search(line):
            raise ValueError("Expected an ISO 8601 timestamp, host and sshd message")
        return None
    message = envelope["message"]
    if not _CANDIDATE.match(message):
        return None
    auth = _AUTH.fullmatch(message)
    if auth is None:
        raise ValueError("Unsupported authentication message structure")
    timestamp = datetime.fromisoformat(envelope["timestamp"])
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Timestamp must include a UTC offset or Z")
    timestamp = timestamp.astimezone(timezone.utc)
    address = ip_address(auth["ip"])
    if getattr(address, "scope_id", None) is not None:
        raise ValueError("Scoped IPv6 addresses are not supported")
    port = int(auth["port"])
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if auth["outcome"] == "Accepted" and auth["invalid"]:
        raise ValueError("An accepted user cannot be marked invalid")
    return AuthEvent(
        timestamp=timestamp,
        host=envelope["host"],
        source_ip=str(address),
        username=auth["username"],
        outcome=auth["outcome"].lower(),
        method=auth["method"],
        port=port,
        line_number=line_number,
        invalid_user=bool(auth["invalid"]),
    )


def parse_lines(lines: Iterable[str]) -> ParseResult:
    return collect_lines(lines, parse_line)
