"""JSON representation of authentication correlations."""

from netsec.reporters.json_report import _utc


def success_records(correlations):
    return [{
        "host": item["host"], "source_ip": item["source_ip"], "username": item["username"],
        "start_time": _utc(item["failure_events"][0].timestamp),
        "end_time": _utc(item["failure_events"][-1].timestamp),
        "failure_count": len(item["failure_events"]),
        "failure_line_numbers": [event.line_number for event in item["failure_events"]],
        "success_time": _utc(item["success_event"].timestamp),
        "success_line_number": item["success_event"].line_number,
        "success_method": item["success_event"].method,
        "seconds_after_last_failure": item["seconds_after_last_failure"],
        "interpretation": "Authentication succeeded after repeated failures; review required.",
    } for item in correlations]
