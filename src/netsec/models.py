"""Shared, immutable analysis records."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuthEvent:
    timestamp: datetime
    host: str
    source_ip: str
    username: str
    outcome: str
    method: str
    port: int
    line_number: int
    invalid_user: bool = False


@dataclass(frozen=True)
class ParseStatistics:
    total_lines: int
    blank_lines: int
    ignored_lines: int
    malformed_lines: int
    malformed_line_numbers: tuple[int, ...]
    parsed_events: int
    failed_events: int
    accepted_events: int


@dataclass(frozen=True)
class ParseResult:
    events: tuple[AuthEvent, ...]
    statistics: ParseStatistics


@dataclass(frozen=True)
class Finding:
    host: str
    source_ip: str
    evidence: tuple[AuthEvent, ...]
    peak_window_failures: int
