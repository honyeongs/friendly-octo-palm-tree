"""Line accounting shared by text and journal input adapters."""

from typing import Callable, Iterable

from netsec.models import AuthEvent, ParseResult, ParseStatistics


def collect_lines(lines: Iterable[str], parser: Callable[[str, int], AuthEvent | None]) -> ParseResult:
    events = []
    total = blank = ignored = 0
    malformed = []
    for line_number, line in enumerate(lines, 1):
        total += 1
        if not line.strip():
            blank += 1
            continue
        try:
            event = parser(line, line_number)
        except (ValueError, OverflowError, TypeError):
            malformed.append(line_number)
            continue
        if event is None:
            ignored += 1
        else:
            events.append(event)
    failed = sum(event.outcome == "failed" for event in events)
    return ParseResult(tuple(events), ParseStatistics(
        total, blank, ignored, len(malformed), tuple(malformed), len(events),
        failed, len(events) - failed,
    ))
