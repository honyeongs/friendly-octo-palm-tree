"""Detect and merge overlapping windows of SSH authentication failures."""

from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from netsec.models import AuthEvent, Finding


def detect_repeated_failures(
    events: Iterable[AuthEvent], *, window_seconds: int = 60, threshold: int = 5
) -> tuple[Finding, ...]:
    if not isinstance(window_seconds, int) or not 1 <= window_seconds <= 86400:
        raise ValueError("window_seconds must be an integer between 1 and 86400")
    if not isinstance(threshold, int) or threshold < 1:
        raise ValueError("threshold must be a positive integer")
    groups: dict[tuple[str, str], list[AuthEvent]] = defaultdict(list)
    for event in events:
        if event.outcome == "failed":
            groups[(event.host, event.source_ip)].append(event)
    duration = timedelta(seconds=window_seconds)
    findings: list[Finding] = []
    for (host, source_ip), group in sorted(groups.items()):
        ordered = sorted(group, key=lambda item: (item.timestamp, item.line_number))
        left = 0
        episode_start = None
        episode_end = 0
        peak = 0
        for right, event in enumerate(ordered):
            while event.timestamp - ordered[left].timestamp > duration:
                left += 1
            count = right - left + 1
            if count < threshold:
                continue
            # Sorted index intervals let us merge without repeatedly copying windows.
            if episode_start is not None and ordered[left].timestamp > ordered[episode_end].timestamp:
                findings.append(Finding(
                    host, source_ip, tuple(ordered[episode_start:episode_end + 1]), peak
                ))
                episode_start = None
                peak = 0
            if episode_start is None:
                episode_start = left
            peak = max(peak, count)
            episode_end = right
        if episode_start is not None:
            findings.append(Finding(
                host, source_ip, tuple(ordered[episode_start:episode_end + 1]), peak
            ))
    return tuple(
        sorted(findings, key=lambda item: (
            item.evidence[0].timestamp, item.host, item.source_ip
        ))
    )
