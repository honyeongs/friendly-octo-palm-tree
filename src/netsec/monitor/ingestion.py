"""Transactional ingestion, immutable idempotency keys and bounded correlation."""

import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from netsec.monitor.database import audit, now
from netsec.monitor.detection import analyze
from netsec.monitor.security import digest


def ingest(db, source, batch, retention_days=30, *, saas=False):
    clock = datetime.now(timezone.utc)
    for event in batch.events:
        if not clock - timedelta(days=retention_days) <= event.timestamp <= clock + timedelta(minutes=5):
            raise HTTPException(422, "이벤트 시각이 보관 기간 밖이거나 현재보다 5분 이상 미래입니다.")
    accepted, duplicates, times = 0, 0, []
    with db.connect(write=True) as conn:
        # Recheck revocation inside the same write transaction as the event insert.
        live = conn.execute("SELECT * FROM sources WHERE id=? AND active=1", (source["id"],)).fetchone()
        if live is None:
            raise HTTPException(401, "수집 키가 폐기되었습니다.")
        org = conn.execute("SELECT * FROM organizations WHERE id=?", (source["org_id"],)).fetchone()
        if saas:
            from netsec.saas.plans import entitlement
            _, plan, _ = entitlement(conn, org['id'])
            if any(event.timestamp < clock - timedelta(days=plan['retention_days']) for event in batch.events):
                raise HTTPException(422, '이벤트 시각이 요금제 보관 기간 밖입니다.')
        for event in batch.events:
            payload = event.model_dump(mode="json")
            timestamp = event.timestamp.isoformat(timespec="microseconds")
            fingerprint = digest(json.dumps(payload, sort_keys=True, ensure_ascii=False))
            old = conn.execute("SELECT fingerprint FROM events WHERE source_id=? AND event_id=?",
                               (source["id"], event.event_id)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise HTTPException(409, "같은 event_id에 다른 내용이 있습니다. 배치 전체를 취소했습니다.")
                duplicates += 1
                continue
            conn.execute("INSERT INTO events(org_id,source_id,event_id,timestamp,received_at,event_type,outcome,source_ip,"
                         "username,method,host,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (org["id"], source["id"], event.event_id, timestamp, now(), event.event_type, event.outcome,
                          event.source_ip, event.username, event.method, event.host, fingerprint))
            accepted += 1
            if event.event_type == "auth.login" or saas:
                times.append(event.timestamp)
        if saas:
            from netsec.saas.plans import reserve_events
            reserve_events(conn, org['id'], accepted)
        created = []
        if times:
            horizon = timedelta(seconds=org["window_seconds"] + org["success_seconds"])
            lower = (min(times) - horizon).isoformat(timespec="microseconds")
            upper = (max(times) + horizon).isoformat(timespec="microseconds")
            rows = conn.execute("SELECT * FROM events WHERE org_id=? AND source_id=? "
                                "AND timestamp BETWEEN ? AND ? ORDER BY timestamp,id LIMIT 10001",
                                (org["id"], source["id"], lower, upper)).fetchall()
            if len(rows) > 10000:
                raise HTTPException(413, "상관분석 구간의 이벤트가 10,000개를 초과했습니다. 별도 소스로 분리하세요.")
            created = analyze(conn, org, source["id"], rows, extended=saas)
        conn.execute("UPDATE sources SET last_seen=? WHERE id=?", (now(), source["id"]))
        audit(conn, org["id"], "source:" + source["id"], "events.ingest", source["id"],
              {"accepted": accepted, "duplicates": duplicates, "incidents": len(created)})
    return {"accepted": accepted, "duplicates": duplicates, "incidents_created": len(created)}
