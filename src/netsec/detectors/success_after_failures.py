"""Correlate a successful authentication with a preceding same-user burst."""

from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from netsec.models import AuthEvent


def correlate_successes(
    events: Iterable[AuthEvent], *, window_seconds: int = 60,
    threshold: int = 5, success_window_seconds: int = 300,
) -> tuple[dict, ...]:
    if any(type(value) is not int or not 1 <= value <= 86400
           for value in (window_seconds, success_window_seconds)):
        raise ValueError("Time windows must be integers between 1 and 86400")
    if type(threshold) is not int or threshold < 1:
        raise ValueError("threshold must be a positive integer")
    groups = defaultdict(list)
    for event in events:
        groups[(event.host, event.source_ip, event.username)].append(event)
    results = []
    for (host, address, username), group in sorted(groups.items()):
        failures = []
        left = 0
        latest_burst = None
        for event in sorted(group, key=lambda item: (item.timestamp, item.line_number)):
            if event.outcome == "accepted":
                if latest_burst:
                    start, end = latest_burst
                    last = failures[end]
                    elapsed = (event.timestamp - last.timestamp).total_seconds()
                    if (event.timestamp, event.line_number) > (last.timestamp, last.line_number) and 0 <= elapsed <= success_window_seconds:
                        results.append({
                            "host": host, "source_ip": address, "username": username,
                            "failure_events": tuple(failures[start:end + 1]), "success_event": event,
                            "seconds_after_last_failure": elapsed,
                        })
                failures = []
                left = 0
                latest_burst = None
                continue
            if event.outcome != "failed":
                continue
            failures.append(event)
            while event.timestamp - failures[left].timestamp > timedelta(seconds=window_seconds):
                left += 1
            if len(failures) - left >= threshold:
                # Keep the latest qualifying burst; later isolated failures cannot extend it.
                latest_burst = (left, len(failures) - 1)
    return tuple(sorted(results, key=lambda item: (
        item["success_event"].timestamp, item["host"], item["source_ip"], item["username"]
    )))
