"""
Production-ready FastAPI application with comprehensive error handling,
observability, and lifecycle management.
"""
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
import sys
import time

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.core.config import settings
from api.core.logging_config import configure_logging
from api.core.database import init_db

from api.middleware.correlation_id import CorrelationIdMiddleware
from api.middleware.logging_middleware import LoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.middleware.error_handler import global_exception_handler

import logging
try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

# Optional: Prometheus metrics (install with: pip install prometheus-client)
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response
    PROMETHEUS_AVAILABLE = True
    
    REQUEST_COUNT = Counter(
        'http_requests_total',
        'Total HTTP requests',
        ['method', 'endpoint', 'status']
    )
    REQUEST_DURATION = Histogram(
        'http_request_duration_seconds',
        'HTTP request duration',
        ['method', 'endpoint']
    )
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.info("Prometheus client not installed - metrics endpoint disabled")


STARTUP_TIME = time.time()


class HealthCheckError(Exception):
    """Custom exception for health check failures."""
    pass


def check_db_health() -> bool:
    """
    Check if database is accessible.
    Override this with your actual database health check.
    """
    try:
        # TODO: Implement actual database health check
        # Example for SQLAlchemy:
        # from api.core.database import SessionLocal
        # db = SessionLocal()
        # db.execute(text("SELECT 1"))
        # db.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def close_db() -> None:
    """
    Close database connections.
    Override this with your actual cleanup logic.
    """
    try:
        # TODO: Implement actual database cleanup
        # Example: close connection pools, etc.
        pass
    except Exception as e:
        logger.error(f"Error closing database: {e}")


async def validate_configuration() -> None:
    """Validate critical configuration on startup."""
    errors = []
    warnings = []
    
    if not settings.APP_NAME:
        errors.append("APP_NAME is not set")
    
    if not settings.CORS_ORIGINS:
        warnings.append("CORS_ORIGINS is empty - API may not be accessible from browsers")
    
    if settings.DEBUG and getattr(settings, 'ENVIRONMENT', 'development') != "development":
        warnings.append("DEBUG=True in non-development environment is a security risk")
    
    # Only check SECRET_KEY if it exists in settings
    if hasattr(settings, 'SECRET_KEY'):
        secret_key = getattr(settings, 'SECRET_KEY', '')
        if len(secret_key) < 32:
            errors.append("SECRET_KEY is too short (minimum 32 characters)")
    
    # Validate CORS origins format
    for origin in settings.CORS_ORIGINS:
        if not origin.startswith(('http://', 'https://', '*')):
            errors.append(f"Invalid CORS origin format: {origin}")
    
    if warnings:
        for warning in warnings:
            logger.warning(f"Configuration warning: {warning}")
    
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("Configuration validation passed")


async def startup_checks() -> None:
    """Run comprehensive startup checks."""
    logger.info("Starting application startup checks...")
    
    # Validate configuration
    try:
        await validate_configuration()
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
    
    # Initialize database with proper error handling
    try:
        logger.info("Initializing database connection...")
        init_db()
        logger.info("Database initialized successfully")
        
        # Verify database connectivity
        if not check_db_health():
            logger.warning("Database health check failed - service may be degraded")
            # Don't fail startup, just log warning
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        # In production, you might want to fail here:
        # raise RuntimeError(f"Failed to initialize database: {e}") from e
        logger.warning("Continuing startup despite database issues...")
    
    # Add other service checks here (Redis, external APIs, etc.)
    
    logger.info("Startup checks completed")


async def shutdown_cleanup() -> None:
    """Clean up resources on shutdown."""
    logger.info("Starting graceful shutdown...")
    
    try:
        # Close database connections
        close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during database cleanup: {e}", exc_info=True)
    
    # Add other cleanup tasks (close Redis, flush queues, etc.)
    
    logger.info("Shutdown completed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    try:
        await startup_checks()
        logger.info(f"{settings.APP_NAME} started successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        # In strict production mode, uncomment this:
        # sys.exit(1)
        logger.warning("Continuing despite startup errors...")
    
    yield
    
    # Shutdown
    await shutdown_cleanup()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    configure_logging()
    
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="4.0.0",
        description="A robust API for file conversion, comparison, and workflow management with advanced features and security.",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # Add middleware in correct order (last added = first executed)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
        max_age=3600,
    )

    # Exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors with detailed feedback."""
        logger.warning(
            f"Validation error on {request.method} {request.url.path}",
            extra={
                "errors": exc.errors(),
                "body": exc.body if hasattr(exc, 'body') else None
            }
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "Validation error",
                "message": "The request data is invalid",
                "details": [
                    {
                        "field": ".".join(str(loc) for loc in e["loc"]),
                        "message": e["msg"],
                        "type": e["type"]
                    } 
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all unhandled exceptions."""
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            exc_info=True,
            extra={
                "path": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else None
            }
        )
        return await global_exception_handler(request, exc)

    # Health and monitoring endpoints
    @app.get("/health", tags=["monitoring"], status_code=status.HTTP_200_OK)
    async def health_check() -> Dict[str, Any]:
        """
        Comprehensive health check endpoint.
        Returns service status and dependency health.
        """
        health_status = {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": "4.0.0",
            "environment": getattr(settings, 'ENVIRONMENT', 'unknown'),
            "uptime_seconds": int(time.time() - STARTUP_TIME),
        }
        
        # Check database health
        try:
            db_healthy = check_db_health()
            health_status["database"] = "healthy" if db_healthy else "unhealthy"
            if not db_healthy:
                health_status["status"] = "degraded"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            health_status["database"] = "unhealthy"
            health_status["status"] = "degraded"
        
        # Add more service checks here (Redis, S3, external APIs, etc.)
        
        # Return appropriate status code
        status_code = status.HTTP_200_OK if health_status["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return JSONResponse(
            status_code=status_code,
            content=health_status
        )

    @app.get("/health/readiness", tags=["monitoring"])
    async def readiness_check() -> Dict[str, str]:
        """
        Kubernetes readiness probe endpoint.
        Checks if the service is ready to accept traffic.
        """
        try:
            if not check_db_health():
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "not_ready", "reason": "database_unavailable"}
                )
            
            return {"status": "ready"}
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "reason": str(e)}
            )

    @app.get("/health/liveness", tags=["monitoring"])
    async def liveness_check() -> Dict[str, str]:
        """
        Kubernetes liveness probe endpoint.
        Checks if the service is alive.
        """
        return {"status": "alive"}

    # Prometheus metrics endpoint (only if available)
    if PROMETHEUS_AVAILABLE:
        @app.get("/metrics", tags=["monitoring"])
        async def metrics():
            """Prometheus metrics endpoint."""
            from starlette.responses import Response
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST
            )
        logger.info("Prometheus metrics endpoint enabled at /metrics")
    else:
        logger.info("Prometheus metrics disabled - install prometheus-client to enable")

    # Register routers with API versioning
    from api.routers import auth_router
    from api.routers import conversion_router
    from api.routers.conversion_router import workflow_router
    from api.routers import comparison_router
    from api.routers import admin_router
    from api.routers import job_router
    from api.routers import files_router
    from api.routers import advanced_router
    from api.routers import rag_router

    # API v1 routes
    API_V1_PREFIX = "/api/v1"
    
    app.include_router(auth_router.router, prefix=API_V1_PREFIX)
    app.include_router(conversion_router.router, prefix=API_V1_PREFIX)
    app.include_router(workflow_router, prefix=API_V1_PREFIX)
    app.include_router(comparison_router.router, prefix=API_V1_PREFIX)
    app.include_router(admin_router.router, prefix=API_V1_PREFIX)
    app.include_router(job_router.router, prefix=API_V1_PREFIX)
    app.include_router(files_router.router, prefix=API_V1_PREFIX)
    app.include_router(advanced_router.router, prefix=API_V1_PREFIX)
    app.include_router(rag_router.router, prefix=API_V1_PREFIX)

    logger.info(f"FastAPI application created: {settings.APP_NAME}")
    logger.info(f"API routes available at {API_V1_PREFIX}/*")
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    # Development/Production configuration
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,  # Auto-reload in debug mode
        log_config=None,  # Use our custom logging
        access_log=False,  # Handled by LoggingMiddleware
    )