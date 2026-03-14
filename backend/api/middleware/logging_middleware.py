import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.core.request_context import get_request_context

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

        ctx = get_request_context()

        fields = {
            "correlation_id": ctx.correlation_id or getattr(request.state, "correlation_id", None),
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
            "thread_id": ctx.thread_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration,
        }

        msg = f"{request.method} {request.url.path} - {response.status_code} ({duration}ms)"

        if HAS_LOGURU:
            logger.info(msg, extra=fields)
        else:
            logger.info(msg, extra={"extra_fields": fields})

        return response
