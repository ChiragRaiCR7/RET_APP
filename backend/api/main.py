from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.core.logging_config import configure_logging
from api.routers import auth_router
from api.routers import conversion_router
from api.routers import comparison_router
from api.routers import ai_router
from api.routers import admin_router
from api.routers import job_router

from api.middleware.correlation_id import CorrelationIdMiddleware
from api.middleware.logging_middleware import LoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.error_handler import global_exception_handler


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="4.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()

app.include_router(auth_router.router)
app.include_router(conversion_router.router)
app.include_router(comparison_router.router)
app.include_router(ai_router.router)
app.include_router(admin_router.router)
app.include_router(job_router.router)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

app.add_exception_handler(Exception, global_exception_handler)
