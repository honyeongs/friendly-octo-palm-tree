"""ASGI composition. Routes, persistence, rules and UI remain separate modules."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
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
    worker = Worker(db, settings)

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            worker.start()
        yield
        if run_worker:
            worker.stop()

    app = FastAPI(title="NetSec Monitor", version="0.3.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings, app.state.db = settings, db
    app.state.dummy_password = hash_password(token())
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.origin).hostname])
    app.add_middleware(GuardMiddleware)

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

    app.include_router(routes_auth.router)
    app.include_router(routes_ops.router)
    app.include_router(routes_admin.router)
    ui = Path(__file__).with_name("ui")
    original = Path(__file__).parent.parent / "web"
    app.mount("/assets", StaticFiles(directory=original / "assets"), name="icons")
    app.mount("/ui", StaticFiles(directory=ui), name="monitor-ui")
    app.mount("/compare", StaticFiles(directory=original, html=True), name="compare")

    @app.get("/")
    def index():
        return FileResponse(ui / "index.html")

    return app
