import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Try to import loguru, fall back to standard logging
try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)

        if HAS_LOGURU:
            logger.info(
                f"{request.method} {request.url.path} - {response.status_code} ({duration}ms)",
                extra={
                    "correlation_id": getattr(request.state, "correlation_id", None),
                }
            )
        else:
            logger.info(
                f"{request.method} {request.url.path} - {response.status_code} ({duration}ms)"
            )

        return response
