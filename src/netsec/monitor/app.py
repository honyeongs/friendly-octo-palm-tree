"""ASGI composition. Routes, persistence, rules and UI remain separate modules."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlsplit

from netsec.monitor.config import Settings
from netsec.monitor.database import Database
from netsec.monitor.dependencies import authorize, current_user
from netsec.monitor.middleware import GuardMiddleware
from netsec.monitor.notifications import Worker
from netsec.monitor.security import hash_password, token
from netsec.monitor import routes_admin, routes_auth, routes_ops


def create_app(settings=None, *, run_worker=True):
    settings = (settings or Settings.from_env()).validate()
    db = Database(settings.database)
    vault = None
    if settings.saas.enabled:
        from netsec.saas.secrets import Vault
        vault = Vault(settings, db)
    worker = Worker(db, settings, vault)

    @asynccontextmanager
    async def lifespan(app):
        if run_worker and settings.saas.embedded_worker:
            worker.start()
        yield
        if run_worker and settings.saas.embedded_worker:
            worker.stop()

    app = FastAPI(title="NetSec Monitor", version="0.4.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings, app.state.db = settings, db
    app.state.vault = vault
    app.state.dummy_password = hash_password(token())
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.origin).hostname])
    app.add_middleware(GuardMiddleware, trusted_proxies=settings.trusted_proxies)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default validation payload echoes rejected passwords and tokens.
        return JSONResponse(status_code=422, content={"detail": [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in exc.errors()]})

    @app.get("/healthz")
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/openapi")
    def openapi(user=Depends(current_user)):
        authorize(user, "admin")
        return app.openapi()

    @app.get('/readyz')
    def ready():
        from datetime import datetime, timedelta, timezone
        with db.connect() as conn:
            conn.execute('SELECT 1')
            last = conn.execute('SELECT max(updated_at) FROM worker_heartbeats').fetchone()[0]
        alive = not settings.saas.enabled or bool(last and last > (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec='microseconds'))
        return JSONResponse({'status': 'ready' if alive else 'worker_unavailable'}, status_code=200 if alive else 503)

    app.include_router(routes_auth.router)
    app.include_router(routes_ops.router)
    app.include_router(routes_admin.router)
    from netsec.saas import billing, identity, integrations, oidc, operations
    for module in (billing, identity, integrations, oidc, operations):
        app.include_router(module.router)
    ui = Path(__file__).with_name("ui")
    original = Path(__file__).parent.parent / "web"
    app.mount("/assets", StaticFiles(directory=original / "assets"), name="icons")
    app.mount("/ui", StaticFiles(directory=ui), name="monitor-ui")
    app.mount("/compare", StaticFiles(directory=original, html=True), name="compare")

    @app.get("/")
    def index():
        return FileResponse(ui / "index.html")

    @app.get('/legal/{kind}', response_class=PlainTextResponse)
    def legal_draft(kind: str):
        if kind == 'privacy':
            return 'DEVELOPMENT DRAFT ONLY\n로컬 테스트에서는 이메일·이름·인증 기록(IP/계정/호스트)을 저장합니다. 실제 개인정보를 넣지 마세요. 운영자·처리 근거·위탁·국외이전·보관·파기·문의처를 확정한 개인정보 처리방침이 아닙니다.'
        return 'DEVELOPMENT DRAFT ONLY\n개발용 체험입니다. 결제 의무나 SLA를 약정하지 않습니다. 허가받은 시스템의 합성 데이터만 사용하세요. 판매 전 사업자·가격·해지·환불·책임·분쟁 조건을 검토하여 별도 약관을 게시해야 합니다.'

    return app
