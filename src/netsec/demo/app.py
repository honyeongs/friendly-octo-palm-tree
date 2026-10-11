"""A single-account sample, not a production authentication provider."""

import os
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from netsec.monitor.middleware import GuardMiddleware
from netsec.monitor.security import hash_password, verify_password
from netsec.sdk import MonitorClient


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


def create_demo(origin, client, database):
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS account(id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,password_hash TEXT NOT NULL)")
        conn.commit()

    @asynccontextmanager
    async def lifespan(app):
        client.start()
        yield
        client.stop()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
    app.add_middleware(GuardMiddleware)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "입력 형식과 길이를 확인하세요."}, status_code=422)

    def check_origin(request: Request):
        if request.headers.get("origin") != origin or "application/json" not in request.headers.get("content-type", ""):
            raise HTTPException(403, "허용되지 않은 요청입니다.")

    @app.get("/api/state")
    def state():
        with closing(sqlite3.connect(path)) as conn:
            row = conn.execute("SELECT username FROM account").fetchone()
        return {"registered": bool(row), "outbox": client.status()}

    @app.post("/api/register", dependencies=[Depends(check_origin)])
    def register(payload: Login):
        if len(payload.password) < 12:
            raise HTTPException(422, "비밀번호는 12자 이상이어야 합니다.")
        with closing(sqlite3.connect(path)) as conn:
            try:
                conn.execute("INSERT INTO account VALUES(1,?,?)", (payload.username, hash_password(payload.password)))
                conn.commit()
            except sqlite3.IntegrityError:
                raise HTTPException(409, "샘플 계정이 이미 있습니다.") from None
        return {"ok": True}

    @app.post("/api/login", dependencies=[Depends(check_origin)])
    def login(payload: Login, request: Request):
        with closing(sqlite3.connect(path)) as conn:
            row = conn.execute("SELECT username,password_hash FROM account").fetchone()
        if row is None:
            raise HTTPException(409, "먼저 샘플 계정을 생성하세요.")
        valid = verify_password(payload.password, row[1]) and payload.username == row[0]
        queued = client.emit(outcome="success" if valid else "failure", source_ip=request.client.host,
                             username=payload.username, host="sample-web-app", method="password")
        if not valid:
            return JSONResponse({"detail": "아이디 또는 비밀번호가 일치하지 않습니다.", "queued": queued is not None}, status_code=401)
        return {"ok": True, "username": row[0], "queued": queued is not None}

    ui = Path(__file__).with_name("ui")
    app.mount("/ui", StaticFiles(directory=ui), name="sample-ui")

    @app.get("/")
    def index():
        return FileResponse(ui / "index.html")
    return app


def run(args):
    key = os.getenv("NETSEC_SOURCE_KEY", "")
    if not key:
        raise ValueError("Set NETSEC_SOURCE_KEY to an application source key")
    client = MonitorClient(args.endpoint, key, os.getenv("NETSEC_DEMO_OUTBOX", "data/demo-outbox.sqlite3"))
    app = create_demo(f"http://127.0.0.1:{args.port}", client, os.getenv("NETSEC_DEMO_DB", "data/demo-app.sqlite3"))
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False, access_log=False)
    return 0
