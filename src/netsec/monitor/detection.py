"""Adapt persisted application events to the existing explainable rules."""

import ipaddress
import json
from datetime import datetime

from netsec.detectors.repeated_failures import detect_repeated_failures
from netsec.detectors.success_after_failures import correlate_successes
from netsec.models import AuthEvent
from netsec.monitor.database import identifier, now


def _evidence(event):
    return {"id": event.line_number, "timestamp": event.timestamp.isoformat(timespec="microseconds"),
            "host": event.host, "source_ip": event.source_ip, "username": event.username,
            "outcome": event.outcome, "method": event.method}


def analyze(conn, org, source_id, rows, *, extended=False):
    excluded = conn.execute("SELECT cidr FROM exclusions WHERE org_id=? AND source_id=? AND expires_at>?",
                            (org["id"], source_id, now())).fetchall()
    networks = [ipaddress.ip_network(row["cidr"]) for row in excluded]
    events = [AuthEvent(datetime.fromisoformat(row["timestamp"]), row["host"], row["source_ip"],
                        row["username"], "failed" if row["outcome"] == "failure" else "accepted",
                        row["method"], 0, row["id"]) for row in rows
              if row["event_type"] == "auth.login" and not any(ipaddress.ip_address(row["source_ip"]) in net for net in networks)]
    candidates = []
    if extended:
        from netsec.saas.detection import candidates as extended_candidates
        candidates.extend(extended_candidates(org, [row for row in rows if not any(ipaddress.ip_address(row['source_ip']) in net for net in networks)]))
    for finding in detect_repeated_failures(events, threshold=org["threshold"], window_seconds=org["window_seconds"]):
        candidates.append(("repeated_failures", "medium", finding.host, finding.source_ip, "",
                           "반복 인증 실패", [_evidence(event) for event in finding.evidence]))
    for item in correlate_successes(events, threshold=org["threshold"], window_seconds=org["window_seconds"],
                                    success_window_seconds=org["success_seconds"]):
        candidates.append(("success_after_failures", "high", item["host"], item["source_ip"], item["username"],
                           "반복 실패 후 인증 성공", [_evidence(event) for event in (*item["failure_events"], item["success_event"])]))
    created = []
    for rule, severity, host, address, username, title, evidence in candidates:
        first, last = evidence[0]["timestamp"], evidence[-1]["timestamp"]
        matches = conn.execute(
            "SELECT * FROM incidents WHERE org_id=? AND source_id=? AND rule=? AND source_ip=? "
            "AND username=? AND first_seen<=? AND last_seen>=? ORDER BY created_at,id",
            (org["id"], source_id, rule, address, username, last, first),
        ).fetchall()
        existing = next((row for row in matches if json.loads(row["evidence_json"])[0]["host"] == host and
                         (rule not in ("success_after_failures", 'privilege_change_after_login') or json.loads(row["evidence_json"])[-1]["id"] == evidence[-1]["id"])), None)
        stamp = now()
        if existing:
            combined = {item["id"]: item for item in json.loads(existing["evidence_json"])}
            combined.update({item["id"]: item for item in evidence})
            evidence = sorted(combined.values(), key=lambda item: (item["timestamp"], item["id"]))
            serialized = json.dumps(evidence, ensure_ascii=False)
            if serialized != existing["evidence_json"]:
                conn.execute("UPDATE incidents SET evidence_json=?,first_seen=?,last_seen=?,updated_at=?,version=version+1 WHERE id=?",
                             (serialized, evidence[0]["timestamp"], evidence[-1]["timestamp"], stamp, existing["id"]))
            continue
        incident_id = identifier()
        conn.execute("INSERT INTO incidents(id,org_id,source_id,rule,severity,source_ip,username,title,first_seen,last_seen,"
                     "evidence_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (incident_id, org["id"], source_id, rule, severity, address, username, title, first, last,
                      json.dumps(evidence, ensure_ascii=False), stamp, stamp))
        for channel in ("in_app", "webhook", "email"):
            conn.execute("INSERT INTO outbox(id,org_id,incident_id,channel,next_at,created_at) VALUES(?,?,?,?,?,?)",
                         (identifier(), org["id"], incident_id, channel, stamp, stamp))
        created.append(incident_id)
    return created
