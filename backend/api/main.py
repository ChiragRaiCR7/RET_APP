
"""
Production-ready FastAPI application with:
- lifecycle management (startup/shutdown)
- comprehensive error handling
- monitoring endpoints (health/readiness/liveness)
- middleware stack (security headers, rate limits, logging, correlation id, CORS)
- API versioning (settings.API_PREFIX, e.g. /api/v1)

"""

from __future__ import annotations

import sys
import time
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.core.config import settings
from api.core.logging_config import configure_logging

# ✅ Async-first DB functions (preferred)
from api.core.database import init_db, close_db, check_db_health

from api.middleware.correlation_id import CorrelationIdMiddleware
from api.middleware.logging_middleware import LoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.middleware.error_handler import global_exception_handler

try:
    from loguru import logger as loguru_logger  # type: ignore
    _HAS_LOGURU = True
except ImportError:
    loguru_logger = None
    _HAS_LOGURU = False


# -----------------------------
# Logging adapter (safe for stdlib + loguru)
# -----------------------------

_std_logger = logging.getLogger(__name__)
logger = loguru_logger if _HAS_LOGURU else _std_logger


def _log(level: str, msg: str, **fields: Any) -> None:
    """
    Unified logging helper:
    - If loguru exists, logs with structured fields via bind().
    - Else uses stdlib logger with extra fields (safe).
    """
    if _HAS_LOGURU and loguru_logger:
        loguru_logger.bind(**fields).log(level.upper(), msg)
        return

    # stdlib logging: put custom fields under `extra`
    extra = {"extra_fields": fields} if fields else None
    getattr(_std_logger, level.lower(), _std_logger.info)(msg, extra=extra)


# -----------------------------
# Helpers / Health checks
# -----------------------------

def _now() -> float:
    return time.time()


def _uptime_seconds(app: FastAPI) -> int:
    start = getattr(app.state, "start_time", None)
    if not start:
        return 0
    return int(_now() - start)


async def validate_configuration() -> None:
    """Validate critical configuration on startup."""
    errors: list[str] = []
    warnings: list[str] = []

    if not getattr(settings, "APP_NAME", ""):
        errors.append("APP_NAME is not set")

    cors_origins = getattr(settings, "CORS_ORIGINS", None)
    if cors_origins is None:
        warnings.append("CORS_ORIGINS is not defined; default behavior may block browser requests.")
    elif isinstance(cors_origins, list) and len(cors_origins) == 0:
        # In non-dev env, empty CORS should be treated as error for browser clients
        if not getattr(settings, "is_development", False):
            errors.append("CORS_ORIGINS is empty; must be configured outside development.")
        else:
            warnings.append("CORS_ORIGINS is empty - API may not be accessible from browsers.")

    # ✅ ENV drift fix: use ENV (and support ENVIRONMENT alias if present)
    env_value = getattr(settings, "ENVIRONMENT", None)
    if env_value is None:
        # ENV is an Enum in your config; .value gives 'development'/'production'/...
        env_value = getattr(getattr(settings, "ENV", None), "value", "development")

    if getattr(settings, "DEBUG", False) and env_value != "development":
        warnings.append("DEBUG=True in non-development environment is a security risk.")

    # ✅ SECRET_KEY mismatch fix: validate JWT_SECRET_KEY
    jwt_secret = getattr(settings, "JWT_SECRET_KEY", None)
    if not jwt_secret:
        if env_value != "development":
            errors.append("JWT_SECRET_KEY is required outside development.")
        else:
            warnings.append("JWT_SECRET_KEY is not set (development mode).")

    # Validate CORS origins format
    if isinstance(cors_origins, list):
        for origin in cors_origins:
            if origin == "*":
                continue
            if not str(origin).startswith(("http://", "https://")):
                errors.append(f"Invalid CORS origin format: {origin}")

    for w in warnings:
        _log("warning", "Configuration warning", warning=w)

    if errors:
        _log("error", "Configuration validation failed", errors=errors)
        raise ValueError("Configuration validation failed: " + "; ".join(errors))

    _log("info", "Configuration validation passed")


async def startup_checks(app: FastAPI) -> None:
    """Run comprehensive startup checks."""
    _log("info", "Starting application startup checks...")

    await validate_configuration()

    # Initialize database (async-first)
    try:
        _log("info", "Initializing database connection...")
        await init_db()
        _log("info", "Database initialized successfully")

        db_ok = await check_db_health()
        if not db_ok:
            _log("warning", "Database health check failed - service may be degraded.")
            if getattr(settings, "STRICT_STARTUP", False):
                raise RuntimeError("STRICT_STARTUP enabled and DB health check failed.")
    except Exception as e:
        _log("error", "Database initialization failed", error=str(e))
        if getattr(settings, "STRICT_STARTUP", False):
            raise
        _log("warning", "Continuing startup despite database issues (STRICT_STARTUP is off).")

    _log("info", "Startup checks completed")


async def shutdown_cleanup(app: FastAPI) -> None:
    """Clean up resources on shutdown."""
    _log("info", "Starting graceful shutdown...")

    # Stop async embedding worker
    try:
        from api.workers.embedding_worker import stop_embedding_worker

        await stop_embedding_worker()
        _log("info", "Embedding worker stopped")
    except Exception as e:
        _log("warning", "Failed stopping embedding worker", error=str(e))

    # Stop async background task manager
    try:
        from api.workers.celery_app import shutdown_task_manager

        await shutdown_task_manager()
        _log("info", "Background task manager shutdown complete")
    except Exception as e:
        _log("warning", "Failed shutting down background task manager", error=str(e))

    # Shutdown async Azure chat service (closes HTTP client)
    try:
        from api.services.ai.async_azure_openai_service import shutdown_async_chat_service

        await shutdown_async_chat_service()
        _log("info", "Async Azure chat service shutdown complete")
    except Exception as e:
        _log("warning", "Failed shutting down async chat service", error=str(e))

    try:
        await close_db()
    except Exception as e:
        _log("error", "Error during shutdown cleanup", error=str(e))
    _log("info", "Shutdown completed")


# -----------------------------
# Lifespan
# -----------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    app.state.start_time = _now()

    # Initialize async session cache on startup
    try:
        from api.core.session_cache import get_session_cache
        await get_session_cache()
        _log("info", "Session cache initialized")
    except Exception as e:
        _log("warning", "Session cache init failed (non-fatal)", error=str(e))

    # Initialize LLM response cache
    try:
        from api.services.ai.langgraph.cache import configure_llm_cache
        configure_llm_cache()
    except Exception as e:
        _log("warning", "LLM cache init failed (non-fatal)", error=str(e))

    # Configure LangSmith tracing (sets env vars when enabled)
    try:
        from api.services.ai.langgraph.tracing import configure_langsmith
        configure_langsmith()
    except Exception as e:
        _log("warning", "LangSmith tracing init failed (non-fatal)", error=str(e))

    # Configure DSPy modules and load optimised prompts when enabled
    if getattr(settings, "FEATURE_DSPY_ENABLED", False):
        try:
            from api.services.ai.langgraph.dspy_modules import configure_dspy_lm
            configure_dspy_lm()
            # Try loading optimised prompts if they exist
            from api.services.ai.langgraph.optimize_prompts import load_optimised_modules
            loaded = load_optimised_modules("eval/optimised")
            if any(loaded.values()):
                _log("info", "DSPy optimised modules loaded", modules=loaded)
            else:
                _log("info", "DSPy enabled (no optimised prompts found; using defaults)")
        except Exception as e:
            _log("warning", "DSPy init failed (non-fatal)", error=str(e))

    try:
        await startup_checks(app)
        _log("info", "App started successfully", app=settings.APP_NAME, env=getattr(settings, "ENVIRONMENT", None))
    except Exception as e:
        _log("error", "Startup failed", error=str(e))
        if getattr(settings, "STRICT_STARTUP", False):
            sys.exit(1)
        _log("warning", "Continuing despite startup errors (STRICT_STARTUP is off).")

    yield

    await shutdown_cleanup(app)


# -----------------------------
# Application factory
# -----------------------------

def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    configure_logging()

    app = FastAPI(
        title=settings.APP_NAME,
        debug=getattr(settings, "DEBUG", False),
        version=getattr(settings, "APP_VERSION", "4.0.0"),
        description=(
            "A robust API for file conversion, comparison, and workflow management "
            "with advanced features and security."
        ),
        docs_url="/docs" if getattr(settings, "DEBUG", False) else None,
        redoc_url="/redoc" if getattr(settings, "DEBUG", False) else None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # Optional: enterprise host allowlist (won't affect if empty)
    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", None)
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # Middleware order (last added = first executed)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    cors_origins = getattr(settings, "CORS_ORIGINS", ["http://localhost:5173"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600,
    )

    # -----------------------------
    # Exception handlers
    # -----------------------------

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors with detailed feedback."""
        _log(
            "warning",
            "Validation error",
            method=request.method,
            path=request.url.path,
            errors=exc.errors(),
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "Validation error",
                "message": "The request data is invalid",
                "details": [
                    {
                        "field": ".".join(str(loc) for loc in e.get("loc", [])),
                        "message": e.get("msg"),
                        "type": e.get("type"),
                    }
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all unhandled exceptions and delegate to global exception handler."""
        _log(
            "error",
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            client=(request.client.host if request.client else None),
            error=str(exc),
        )
        return await global_exception_handler(request, exc)

    # -----------------------------
    # Health endpoints
    # -----------------------------

    @app.get("/health", tags=["monitoring"])
    async def health_check():
        """
        Comprehensive health check.
        Returns 200 if healthy, 503 if degraded.
        """
        status_name = "healthy"
        db_ok = True
        try:
            db_ok = await check_db_health()  # ✅ async / non-blocking
            if not db_ok:
                status_name = "degraded"
        except Exception:
            status_name = "degraded"
            db_ok = False

        env_value = getattr(settings, "ENVIRONMENT", getattr(getattr(settings, "ENV", None), "value", "unknown"))
        payload = {
            "status": status_name,
            "app": settings.APP_NAME,
            "version": getattr(settings, "APP_VERSION", "4.0.0"),
            "environment": env_value,
            "uptime_seconds": _uptime_seconds(app),
            "database": "healthy" if db_ok else "unhealthy",
        }

        http_code = status.HTTP_200_OK if status_name == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=http_code, content=payload)

    @app.get("/health/readiness", tags=["monitoring"])
    async def readiness_check():
        """
        Readiness probe:
        - returns 200 if ready
        - returns 503 if DB is unavailable (or other readiness dependency fails)
        """
        try:
            if not await check_db_health():
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "not_ready", "reason": "database_unavailable"},
                )
            return {"status": "ready"}
        except Exception as e:
            _log("error", "Readiness check failed", error=str(e))
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "reason": str(e)},
            )

    @app.get("/health/liveness", tags=["monitoring"])
    async def liveness_check():
        """Liveness probe: if process is running, return alive."""
        return {"status": "alive"}

    # -----------------------------
    # Routers (API v1)
    # -----------------------------
    # ✅ Prefix drift fix: do not hardcode "/api/v1"
    API_PREFIX = getattr(settings, "API_PREFIX", "/api/v1")

    from api.routers import auth_router
    from api.routers import conversion_router
    from api.routers import comparison_router
    from api.routers import admin_router
    from api.routers import job_router
    from api.routers import rag_router

    # Include conversion sub-routers if present in your conversion_router.py
    try:
        from api.routers.conversion_router import workflow_router  # type: ignore
        app.include_router(workflow_router, prefix=API_PREFIX)
    except Exception:
        _log("warning", "workflow_router not available in conversion_router.py (skipping).")

    try:
        from api.routers.conversion_router import files_router  # type: ignore
        app.include_router(files_router, prefix=API_PREFIX)
    except Exception:
        _log("info", "files_router not available in conversion_router.py (skipping).")

    try:
        from api.routers.conversion_router import advanced_router  # type: ignore
        app.include_router(advanced_router, prefix=API_PREFIX)
    except Exception:
        _log("info", "advanced_router not available in conversion_router.py (skipping).")

    # Core routers
    app.include_router(auth_router.router, prefix=API_PREFIX)
    app.include_router(conversion_router.router, prefix=API_PREFIX)
    app.include_router(comparison_router.router, prefix=API_PREFIX)
    app.include_router(admin_router.router, prefix=API_PREFIX)
    app.include_router(job_router.router, prefix=API_PREFIX)
    app.include_router(rag_router.router, prefix=API_PREFIX)

    _log("info", "FastAPI application created", app=settings.APP_NAME, api_prefix=API_PREFIX)
    _log("info", "API routes available", prefix=f"{API_PREFIX}/*")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=getattr(settings, "API_HOST", "0.0.0.0"),
        port=getattr(settings, "API_PORT", 8000),
        reload=getattr(settings, "DEBUG", False),
        log_config=None,     # use your custom logging
        access_log=False,    # handled by LoggingMiddleware
    )