"""Tenant-scoped event search and collaborative incident workflow."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from netsec.monitor.database import audit, identifier, now
from netsec.monitor.dependencies import authorize, current_user, scoped
from netsec.monitor.ingestion import ingest
from netsec.monitor.schemas import Batch, CommentCreate, IncidentUpdate
from netsec.monitor.security import digest, rate_limit

router = APIRouter(prefix="/api")


@router.post("/v1/events", status_code=202)
def events_ingest(payload: Batch, request: Request):
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or len(header) > 200:
        raise HTTPException(401, "수집 키가 필요합니다.")
    db = request.app.state.db
    ip = request.client.host if request.client else "unknown"
    rate_limit(db, "ingest-ip:" + digest(ip), limit=600)
    with db.connect() as conn:
        source = conn.execute("SELECT * FROM sources WHERE token_hash=? AND active=1", (digest(header[7:]),)).fetchone()
    if source is None:
        raise HTTPException(401, "유효하지 않은 수집 키입니다.")
    rate_limit(db, "ingest-source:" + source["id"], limit=120)
    settings = request.app.state.settings
    return ingest(db, source, payload, 365 if settings.saas.enabled else settings.retention_days, saas=settings.saas.enabled)


@router.get("/summary")
def summary(request: Request, user=Depends(current_user)):
    with request.app.state.db.connect() as conn:
        org = conn.execute("SELECT id,name,threshold,window_seconds,success_seconds FROM organizations WHERE id=?", (user["org_id"],)).fetchone()
        counts = conn.execute("SELECT count(*) total,coalesce(sum(CASE WHEN outcome='failure' AND event_type='auth.login' THEN 1 ELSE 0 END),0) failures "
                              "FROM events WHERE org_id=?", (user["org_id"],)).fetchone()
        incidents = conn.execute("SELECT count(*) total,coalesce(sum(CASE WHEN status IN ('open','investigating') THEN 1 ELSE 0 END),0) active,"
                                 "coalesce(sum(CASE WHEN severity='high' AND status IN ('open','investigating') THEN 1 ELSE 0 END),0) high FROM incidents WHERE org_id=?",
                                 (user["org_id"],)).fetchone()
        sources = conn.execute("SELECT count(*) FROM sources WHERE org_id=? AND active=1", (user["org_id"],)).fetchone()[0]
    return {"organization": dict(org), "events": dict(counts), "incidents": dict(incidents), "active_sources": sources,
            "retention_days": request.app.state.settings.retention_days}


def _filters(org_id, q, source_id):
    where, params = "org_id=?", [org_id]
    if source_id:
        where += " AND source_id=?"
        params.append(source_id)
    if q:
        where += " AND (source_ip LIKE ? ESCAPE '\\' OR username LIKE ? ESCAPE '\\')"
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.extend(["%" + escaped + "%"] * 2)
    return where, params


@router.get("/events")
def events(request: Request, q: str = Query(default="", max_length=128), source_id: str = "",
           page: int = Query(default=1, ge=1, le=100000), user=Depends(current_user)):
    where, params = _filters(user["org_id"], q, source_id)
    with request.app.state.db.connect() as conn:
        total = conn.execute(f"SELECT count(*) FROM events WHERE {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT id,source_id,event_id,timestamp,event_type,outcome,source_ip,username,host,method "
                            f"FROM events WHERE {where} ORDER BY timestamp DESC,id DESC LIMIT 50 OFFSET ?", (*params, (page - 1) * 50)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": 50}


@router.get("/incidents")
def incidents(request: Request, q: str = Query(default="", max_length=128), status: str = "", source_id: str = "",
              page: int = Query(default=1, ge=1, le=100000), user=Depends(current_user)):
    where, params = _filters(user["org_id"], q, source_id)
    if status:
        if status not in ("open", "investigating", "resolved", "false_positive"):
            raise HTTPException(422, "유효하지 않은 상태입니다.")
        where += " AND status=?"
        params.append(status)
    with request.app.state.db.connect() as conn:
        total = conn.execute(f"SELECT count(*) FROM incidents WHERE {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT id,source_id,rule,severity,source_ip,username,title,first_seen,last_seen,status,assignee_id,version "
                            f"FROM incidents WHERE {where} ORDER BY last_seen DESC,id DESC LIMIT 50 OFFSET ?", (*params, (page - 1) * 50)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": 50}


@router.get("/incidents/{item_id}")
def incident_detail(item_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.connect() as conn:
        row = dict(scoped(conn, "incidents", user["org_id"], item_id))
        comments = conn.execute("SELECT c.id,c.body,c.created_at,u.display_name author FROM comments c JOIN users u ON c.author_id=u.id "
                                "WHERE c.org_id=? AND c.incident_id=? ORDER BY c.created_at,c.id", (user["org_id"], item_id)).fetchall()
    row["evidence"] = json.loads(row.pop("evidence_json"))
    row["comments"] = [dict(comment) for comment in comments]
    return row


@router.patch("/incidents/{item_id}")
def incident_update(item_id: str, payload: IncidentUpdate, request: Request, user=Depends(current_user)):
    authorize(user, "admin", "analyst")
    with request.app.state.db.connect(write=True) as conn:
        row = scoped(conn, "incidents", user["org_id"], item_id)
        if row["version"] != payload.version:
            raise HTTPException(409, "다른 변경이 있습니다. 사건을 다시 열어 확인하세요.")
        if payload.assignee_id:
            assignee = scoped(conn, "users", user["org_id"], payload.assignee_id)
            if not assignee["active"] or assignee["role"] == "viewer":
                raise HTTPException(422, "활성 관리자 또는 분석가를 지정하세요.")
        conn.execute("UPDATE incidents SET status=?,assignee_id=?,updated_at=?,version=version+1 WHERE id=? AND org_id=?",
                     (payload.status, payload.assignee_id, now(), item_id, user["org_id"]))
        audit(conn, user["org_id"], user["id"], "incident.update", item_id,
              {"from": row["status"], "to": payload.status, "assignee_id": payload.assignee_id})
    return {"ok": True}


@router.post("/incidents/{item_id}/comments", status_code=201)
def comment(item_id: str, payload: CommentCreate, request: Request, user=Depends(current_user)):
    authorize(user, "admin", "analyst")
    with request.app.state.db.connect(write=True) as conn:
        scoped(conn, "incidents", user["org_id"], item_id)
        conn.execute("INSERT INTO comments VALUES(?,?,?,?,?,?)", (identifier(), item_id, user["org_id"], user["id"], payload.body, now()))
        audit(conn, user["org_id"], user["id"], "incident.comment", item_id)
    return {"ok": True}


@router.get("/export")
def export(request: Request, user=Depends(current_user)):
    authorize(user, "admin", "analyst")
    with request.app.state.db.connect(write=True) as conn:
        rows = conn.execute("SELECT id,source_id,rule,severity,source_ip,username,title,status,first_seen,last_seen,evidence_json "
                            "FROM incidents WHERE org_id=? ORDER BY last_seen DESC LIMIT 1001", (user["org_id"],)).fetchall()
        items = []
        for row in rows[:1000]:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            items.append(item)
        audit(conn, user["org_id"], user["id"], "incidents.export", detail={"count": len(items)})
    return {"schema_version": "monitor-1.0", "exported_at": now(), "truncated": len(rows) > 1000, "incidents": items}
