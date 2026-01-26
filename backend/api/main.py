from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.core.config import settings
from api.core.logging_config import configure_logging
from api.core.database import init_db
from api.routers import auth_router
from api.routers import conversion_router
from api.routers import comparison_router
from api.routers import ai_router
from api.routers import admin_router
from api.routers import job_router
from api.routers import workflow_router
from api.routers import files_router

from api.middleware.correlation_id import CorrelationIdMiddleware
from api.middleware.logging_middleware import LoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.error_handler import global_exception_handler

import logging
try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    
    # Initialize database
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="4.0.0",
    )

    # Add middleware in correct order (last added = first executed)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Validation error",
                "details": [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()],
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        return await global_exception_handler(request, exc)

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "app": settings.APP_NAME}

    return app


app = create_app()

# Include all routers
app.include_router(auth_router.router)
app.include_router(conversion_router.router)
app.include_router(comparison_router.router)
app.include_router(ai_router.router)
app.include_router(admin_router.router)
app.include_router(job_router.router)
app.include_router(workflow_router.router)
app.include_router(files_router.router)
