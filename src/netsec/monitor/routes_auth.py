"""First-run setup and session lifecycle."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from netsec.monitor.accounts import create_organization
from netsec.monitor.database import audit, now
from netsec.monitor.dependencies import COOKIE, current_user, same_origin
from netsec.monitor.schemas import Credentials, PasswordChange, Setup
from netsec.monitor.security import digest, hash_password, rate_limit, token, verify_password

router = APIRouter(prefix="/api")


@router.get("/setup")
def setup_state(request: Request):
    with request.app.state.db.connect() as conn:
        required = conn.execute("SELECT count(*) FROM organizations").fetchone()[0] == 0
    return {"required": required}


@router.post("/setup", dependencies=[Depends(same_origin)])
def setup(payload: Setup, request: Request):
    settings = request.app.state.settings
    # Remote deployments must provision through the operator CLI before exposure.
    if settings.secure:
        raise HTTPException(403, "외부 배포의 첫 조직은 운영자 CLI에서 생성하세요.")
    rate_limit(request.app.state.db, "setup", limit=5, seconds=300)
    with request.app.state.db.connect(write=True) as conn:
        if conn.execute("SELECT count(*) FROM organizations").fetchone()[0]:
            raise HTTPException(409, "초기 설정이 이미 완료되었습니다.")
        org_id = create_organization(conn, payload)
    return {"org_id": org_id}


@router.post("/login", dependencies=[Depends(same_origin)])
def login(payload: Credentials, request: Request, response: Response):
    db, settings = request.app.state.db, request.app.state.settings
    ip = request.client.host if request.client else "unknown"
    rate_limit(db, "login-ip:" + digest(ip), limit=30, seconds=300)
    rate_limit(db, "login-account:" + digest(payload.org_id + ":" + payload.email.lower()), limit=10, seconds=300)
    with db.connect(write=True) as conn:
        user = conn.execute("SELECT * FROM users WHERE org_id=? AND email=? AND active=1",
                            (payload.org_id, payload.email.lower())).fetchone()
        encoded = user["password_hash"] if user else request.app.state.dummy_password
        valid = verify_password(payload.password, encoded)
        if not user or not valid:
            # Audit real organizations only; unknown emails are not retained.
            if conn.execute("SELECT 1 FROM organizations WHERE id=?", (payload.org_id,)).fetchone():
                audit(conn, payload.org_id, "anonymous", "login.failure")
            failed = True
        else:
            failed = False
            raw, csrf = token(), token()
            expiry = (datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)).isoformat(timespec="microseconds")
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now(),))
            conn.execute("INSERT INTO sessions VALUES(?,?,?,?)", (digest(raw), user["id"], csrf, expiry))
            audit(conn, user["org_id"], user["id"], "login.success")
    if failed:
        raise HTTPException(401, "조직 ID, 이메일 또는 비밀번호를 확인하세요.")
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.secure, samesite="strict",
                        max_age=settings.session_hours * 3600, path="/")
    return {"id": user["id"], "org_id": user["org_id"], "display_name": user["display_name"],
            "role": user["role"], "csrf": csrf}


@router.get("/me")
def me(user=Depends(current_user)):
    return user


@router.post("/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    with request.app.state.db.connect(write=True) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
        audit(conn, user["org_id"], user["id"], "logout")
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
def change_password(payload: PasswordChange, request: Request, response: Response, user=Depends(current_user)):
    rate_limit(request.app.state.db, "password:" + user["id"], limit=5, seconds=300)
    with request.app.state.db.connect(write=True) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(400, "현재 비밀번호가 일치하지 않습니다.")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(payload.new_password), user["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        audit(conn, user["org_id"], user["id"], "password.change")
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
