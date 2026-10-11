"""Produce stable JSON with the evidence needed to inspect each finding."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from netsec.models import Finding, ParseStatistics


def _utc(timestamp: datetime) -> str:
    return timestamp.isoformat().replace("+00:00", "Z")


def build_report(
    *, source: str, statistics: ParseStatistics, findings: Iterable[Finding],
    window_seconds: int, threshold: int,
) -> dict:
    records = []
    for finding in findings:
        records.append({
            "host": finding.host,
            "source_ip": finding.source_ip,
            "start_time": _utc(finding.evidence[0].timestamp),
            "end_time": _utc(finding.evidence[-1].timestamp),
            "failure_count": len(finding.evidence),
            "peak_window_failures": finding.peak_window_failures,
            "usernames": sorted({event.username for event in finding.evidence}),
            "evidence": [{
                "line_number": event.line_number,
                "timestamp": _utc(event.timestamp),
                "username": event.username,
                "method": event.method,
                "source_port": event.port,
                "invalid_user": event.invalid_user,
            } for event in finding.evidence],
        })
    return {
        "schema_version": "1.0",
        "rule": "ssh_repeated_authentication_failures",
        "source": source,
        "parameters": {"window_seconds": window_seconds, "threshold": threshold},
        "statistics": {**asdict(statistics), "finding_count": len(records)},
        "findings": records,
    }


def serialize_report(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_report(report: dict, path: Path, *, overwrite: bool = False) -> None:
    # Exclusive creation prevents silently replacing an existing report.
    with path.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialize_report(report))
