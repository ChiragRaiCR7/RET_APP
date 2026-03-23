"""
HTTP request/response logging middleware.

Improvements:
- time.monotonic() for accurate, clock-drift-immune duration measurement.
- Client IP included in every log entry for abuse detection.
- try/except around call_next ensures exceptions are logged before re-raising.
- Removes legacy thread_id field (dropped from RequestContext).
- Adds response_bytes from Content-Length when available.
- Type annotation for call_next parameter.
- Uses get_logger() for consistent structured logging.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.core.logging_config import get_logger
from api.core.request_context import get_request_context

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.monotonic()
        client_ip = request.client.host if request.client else "unknown"

        # Bind session context so the SessionSink routes to per-session files
        ctx = get_request_context()
        req_logger = (
            logger.bind(session_id=ctx.session_id)
            if ctx.session_id and hasattr(logger, "bind")
            else logger
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration = round((time.monotonic() - start) * 1000, 2)
            req_logger.error(
                "%s %s - error (%sms) [%s]",
                request.method,
                request.url.path,
                duration,
                client_ip,
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "duration_ms": duration,
                        "client_ip": client_ip,
                        "error": type(exc).__name__,
                    }
                },
            )
            raise

        duration = round((time.monotonic() - start) * 1000, 2)
        status_code = response.status_code

        extra_fields: dict = {
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "duration_ms": duration,
            "client_ip": client_ip,
        }

        content_length = response.headers.get("content-length")
        if content_length:
            extra_fields["response_bytes"] = int(content_length)

        msg = "%s %s - %d (%sms) [%s]"
        log_args = (request.method, request.url.path, status_code, duration, client_ip)
        if status_code >= 500:
            req_logger.error(msg, *log_args, extra={"extra_fields": extra_fields})
        else:
            req_logger.info(msg, *log_args, extra={"extra_fields": extra_fields})

        return response
