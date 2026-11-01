"""FastAPI application factory."""

import contextvars
import logging
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import func, select, text

from app.config import BACKEND_DIR, get_settings
from app.db import new_session
from app.models import User
from app.routers import admin, auth, comparisons, workspaces
from app.security import hash_password, origin_allowed
from app.services import jobs

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_SAFE_RID = re.compile(r"[A-Za-z0-9\-]{8,64}")
log = logging.getLogger("ret")

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; font-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def migrate() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def bootstrap_admin() -> None:
    """Create the first admin on an empty database. Production requires an explicit password."""
    s = get_settings()
    with new_session() as db:
        if db.scalar(select(func.count(User.id))):
            return
        if s.bootstrap_admin_password is not None:
            password = s.bootstrap_admin_password.get_secret_value()
            shown = False
        elif s.env == "production":
            log.warning(
                "No users exist. Set BOOTSTRAP_ADMIN_PASSWORD and restart to create "
                "the '%s' account.",
                s.bootstrap_admin_username,
            )
            return
        else:
            password, shown = secrets.token_urlsafe(12), True
        db.add(
            User(
                username=s.bootstrap_admin_username,
                password_hash=hash_password(password),
                role="admin",
            )
        )
        db.commit()
    if shown:
        # Development only: printed to the console once, never written to the log handlers.
        print(
            f"\n  RET dev admin created → username: {s.bootstrap_admin_username}  "
            f"password: {password}\n",
            flush=True,
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.workspaces_dir.mkdir(parents=True, exist_ok=True)
    migrate()
    configure_logging()  # alembic's fileConfig resets logging; reapply ours afterwards
    bootstrap_admin()
    jobs.recover_interrupted()
    log.info("RET ready env=%s llm=%s", settings.env, settings.llm_configured)
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="RET API",
        version="5.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.env != "production" else None,
        openapi_url="/api/openapi.json" if settings.env != "production" else None,
    )

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        # Client-supplied ids land in logs: accept only a short safe alphabet.
        rid = supplied if _SAFE_RID.fullmatch(supplied) else uuid.uuid4().hex[:16]
        token = _request_id.set(rid)
        request.state.request_id = rid
        started = time.perf_counter()
        try:
            if request.url.path.startswith("/api/") and not origin_allowed(request):
                response: Response = JSONResponse(
                    {"detail": "Cross-origin request blocked."}, status_code=403
                )
            else:
                response = await call_next(request)
            if request.url.path.startswith("/api/"):
                logging.getLogger("ret.http").info(
                    "%s %s %s %.0fms",
                    request.method,
                    request.url.path,
                    response.status_code,
                    (time.perf_counter() - started) * 1000,
                )
        finally:
            _request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if settings.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ())[1:])
        msg = f"{where}: {first.get('msg')}" if where else str(first.get("msg", "Invalid input"))
        return JSONResponse({"detail": msg, "errors": exc.errors()}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        log.exception("unhandled error [%s]", rid)
        return JSONResponse(
            {"detail": f"Unexpected server error. Reference: {rid}"}, status_code=500
        )

    for r in (auth.router, admin.router, workspaces.router, comparisons.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/ready", tags=["ops"])
    def ready() -> dict[str, str]:
        with new_session() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready"}

    _mount_spa(app, settings.frontend_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built frontend from the API origin (one origin => no CORS in production)."""
    index = dist / "index.html"
    if not index.exists():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            cache = (
                "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            )
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
