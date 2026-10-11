"""Resolve tenant scope only from authenticated credentials, never request IDs."""

import hmac

from fastapi import HTTPException, Request

from netsec.monitor.database import now
from netsec.monitor.security import digest

COOKIE = "netsec_session"


def same_origin(request: Request):
    if request.headers.get("origin") != request.app.state.settings.origin:
        raise HTTPException(403, "허용되지 않은 요청 출처입니다.")
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(415, "JSON 요청이 필요합니다.")


def current_user(request: Request):
    raw = request.cookies.get(COOKIE, "")
    with request.app.state.db.connect() as conn:
        row = conn.execute("SELECT u.id,u.org_id,u.email,u.display_name,u.role,s.csrf FROM sessions s JOIN users u "
                           "ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
                           (digest(raw), now())).fetchone()
    if row is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    user = dict(row)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        same_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), user["csrf"]):
            raise HTTPException(403, "보안 토큰이 유효하지 않습니다. 다시 로그인하세요.")
    return user


def authorize(user, *roles):
    if user["role"] not in roles:
        raise HTTPException(403, "이 작업에 필요한 권한이 없습니다.")


def scoped(conn, table, org_id, item_id):
    if table not in ("incidents", "users", "sources", "exclusions"):
        raise ValueError("Invalid scoped table")
    row = conn.execute(f"SELECT * FROM {table} WHERE org_id=? AND id=?", (org_id, item_id)).fetchone()
    if row is None:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    return row
