"""User, source, policy, exclusions, notification and audit administration."""

import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from netsec.monitor.database import audit, identifier, now
from netsec.monitor.dependencies import authorize, current_user, scoped
from netsec.monitor.schemas import ExclusionCreate, NewUser, PolicyUpdate, SourceCreate, UserUpdate
from netsec.monitor.security import digest, hash_password, token

router = APIRouter(prefix="/api")


@router.get("/users")
def users(request: Request, user=Depends(current_user)):
    fields = "id,display_name,role,active" + (",email,created_at" if user["role"] == "admin" else "")
    with request.app.state.db.connect() as conn:
        rows = conn.execute(f"SELECT {fields} FROM users WHERE org_id=? ORDER BY display_name", (user["org_id"],)).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/users", status_code=201)
def create_user(payload: NewUser, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect(write=True) as conn:
        count = conn.execute("SELECT count(*) FROM users WHERE org_id=?", (user["org_id"],)).fetchone()[0]
        if count >= 100:
            raise HTTPException(409, "조직당 사용자는 최대 100명입니다.")
        user_id = identifier()
        try:
            conn.execute("INSERT INTO users(id,org_id,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?,?)",
                         (user_id, user["org_id"], payload.email, payload.display_name, hash_password(payload.password), payload.role, now()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 등록된 이메일입니다.") from None
        audit(conn, user["org_id"], user["id"], "user.create", user_id, {"role": payload.role})
    return {"id": user_id}


@router.patch("/users/{item_id}")
def update_user(item_id: str, payload: UserUpdate, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect(write=True) as conn:
        scoped(conn, "users", user["org_id"], item_id)
        if item_id == user["id"]:
            raise HTTPException(409, "본인의 역할이나 활성 상태는 변경할 수 없습니다.")
        conn.execute("UPDATE users SET role=?,active=? WHERE id=? AND org_id=?", (payload.role, payload.active, item_id, user["org_id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (item_id,))
        audit(conn, user["org_id"], user["id"], "user.update", item_id, {"role": payload.role, "active": payload.active})
    return {"ok": True}


@router.get("/sources")
def sources(request: Request, user=Depends(current_user)):
    with request.app.state.db.connect() as conn:
        rows = conn.execute("SELECT id,name,kind,active,created_at,last_seen FROM sources WHERE org_id=? ORDER BY created_at DESC", (user["org_id"],)).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/sources", status_code=201)
def create_source(payload: SourceCreate, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    raw, item_id = "nsk_" + token(), identifier()
    with request.app.state.db.connect(write=True) as conn:
        if conn.execute("SELECT count(*) FROM sources WHERE org_id=? AND active=1", (user["org_id"],)).fetchone()[0] >= 100:
            raise HTTPException(409, "활성 수집 소스는 최대 100개입니다.")
        conn.execute("INSERT INTO sources(id,org_id,name,kind,token_hash,created_at) VALUES(?,?,?,?,?,?)",
                     (item_id, user["org_id"], payload.name, payload.kind, digest(raw), now()))
        audit(conn, user["org_id"], user["id"], "source.create", item_id)
    return {"id": item_id, "token": raw}


@router.delete("/sources/{item_id}")
def revoke_source(item_id: str, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect(write=True) as conn:
        scoped(conn, "sources", user["org_id"], item_id)
        conn.execute("UPDATE sources SET active=0 WHERE id=?", (item_id,))
        audit(conn, user["org_id"], user["id"], "source.revoke", item_id)
    return {"ok": True}


@router.get("/policy")
def policy(request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    settings = request.app.state.settings
    with request.app.state.db.connect() as conn:
        row = conn.execute("SELECT threshold,window_seconds,success_seconds,notification_email,webhook_enabled FROM organizations WHERE id=?", (user["org_id"],)).fetchone()
        exclusions = conn.execute("SELECT * FROM exclusions WHERE org_id=? ORDER BY created_at DESC", (user["org_id"],)).fetchall()
    return {**dict(row), "webhook_available": bool(settings.webhook_url), "email_available": bool(settings.smtp_host and settings.smtp_from),
            "retention_days": settings.retention_days, "exclusions": [dict(row) for row in exclusions]}


@router.put("/policy")
def policy_update(payload: PolicyUpdate, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect(write=True) as conn:
        conn.execute("UPDATE organizations SET threshold=?,window_seconds=?,success_seconds=?,notification_email=?,webhook_enabled=? WHERE id=?",
                     (payload.threshold, payload.window_seconds, payload.success_seconds, payload.notification_email, payload.webhook_enabled, user["org_id"]))
        audit(conn, user["org_id"], user["id"], "policy.update", detail={"threshold": payload.threshold, "window_seconds": payload.window_seconds,
              "success_seconds": payload.success_seconds, "email_enabled": bool(payload.notification_email), "webhook_enabled": payload.webhook_enabled})
    return {"ok": True}


@router.post("/exclusions", status_code=201)
def exclusion_create(payload: ExclusionCreate, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    clock = datetime.now(timezone.utc)
    if not clock < payload.expires_at <= clock + timedelta(days=30):
        raise HTTPException(422, "예외 만료는 현재부터 30일 이내여야 합니다.")
    with request.app.state.db.connect(write=True) as conn:
        scoped(conn, "sources", user["org_id"], payload.source_id)
        if conn.execute("SELECT count(*) FROM exclusions WHERE org_id=?", (user["org_id"],)).fetchone()[0] >= 100:
            raise HTTPException(409, "예외 규칙은 최대 100개입니다.")
        item_id = identifier()
        conn.execute("INSERT INTO exclusions VALUES(?,?,?,?,?,?,?)", (item_id, user["org_id"], payload.source_id, payload.cidr,
                     payload.reason, payload.expires_at.isoformat(timespec="microseconds"), now()))
        audit(conn, user["org_id"], user["id"], "exclusion.create", item_id, {"cidr": payload.cidr})
    return {"id": item_id}


@router.delete("/exclusions/{item_id}")
def exclusion_delete(item_id: str, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect(write=True) as conn:
        scoped(conn, "exclusions", user["org_id"], item_id)
        conn.execute("DELETE FROM exclusions WHERE id=?", (item_id,))
        audit(conn, user["org_id"], user["id"], "exclusion.delete", item_id)
    return {"ok": True}


@router.get("/audit")
def audit_list(request: Request, page: int = Query(default=1, ge=1, le=100000), user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect() as conn:
        total = conn.execute("SELECT count(*) FROM audit WHERE org_id=?", (user["org_id"],)).fetchone()[0]
        rows = conn.execute("SELECT * FROM audit WHERE org_id=? ORDER BY id DESC LIMIT 50 OFFSET ?", (user["org_id"], (page - 1) * 50)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": 50}


@router.get("/notifications")
def notifications(request: Request, page: int = Query(default=1, ge=1, le=100000), user=Depends(current_user)):
    with request.app.state.db.connect() as conn:
        total = conn.execute("SELECT count(*) FROM outbox WHERE org_id=?", (user["org_id"],)).fetchone()[0]
        rows = conn.execute("SELECT o.id,o.incident_id,o.channel,o.status,o.attempts,o.error,o.created_at,i.title "
                            "FROM outbox o JOIN incidents i ON i.id=o.incident_id WHERE o.org_id=? "
                            "ORDER BY o.created_at DESC,o.channel LIMIT 50 OFFSET ?", (user["org_id"], (page - 1) * 50)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": 50}


@router.post("/notifications/{item_id}/retry")
def retry_notification(item_id: str, request: Request, user=Depends(current_user)):
    authorize(user, "admin")
    with request.app.state.db.connect(write=True) as conn:
        row = conn.execute("SELECT * FROM outbox WHERE org_id=? AND id=?", (user["org_id"], item_id)).fetchone()
        if row is None:
            raise HTTPException(404, "항목을 찾을 수 없습니다.")
        if row["status"] not in ("failed", "skipped"):
            raise HTTPException(409, "실패하거나 설정이 없어 건너뛴 알림만 재시도할 수 있습니다.")
        conn.execute("UPDATE outbox SET status='pending',attempts=0,next_at=?,lease_until=NULL,error='' WHERE id=?", (now(), item_id))
        audit(conn, user["org_id"], user["id"], "notification.retry", item_id)
    return {"ok": True}
