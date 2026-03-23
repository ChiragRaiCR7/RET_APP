"""
Correlation ID middleware.

Improvements over baseline:
- Validates / sanitises incoming X-Correlation-ID (max 64 chars, safe charset).
- Accepts X-Request-ID as a fall-back alias.
- Supports W3C ``traceparent`` header (extracts 32-hex trace-id component for
  compatibility with OpenTelemetry, Datadog, Jaeger, AWS X-Ray, etc.).
- Populates all RequestContext fields available at middleware level
  (ip_address, user_agent, request_path, method).
- Clears the ContextVar in a ``finally`` block to prevent context leakage
  across async tasks when coroutines are reused by ASGI transport layers.
- Debug-level logging records whether a correlation ID was received or generated.
"""

from __future__ import annotations

import re
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.core.logging_config import get_logger
from api.core.request_context import RequestContext, clear_request_context, set_request_context

logger = get_logger(__name__)

# Allowed chars: alphanumeric, hyphens, underscores — blocks log-injection characters.
_SAFE_CORR_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
_MAX_CORR_ID_LEN = 64

# W3C Trace Context: version(2)-traceId(32)-parentId(16)-flags(2)
# e.g. 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$",
    re.ASCII,
)


def _extract_correlation_id(request: Request) -> tuple[str, bool]:
    """
    Return ``(correlation_id, was_generated)`` for this request.

    Priority:
    1. ``X-Correlation-ID`` header (validated, sanitised).
    2. ``X-Request-ID`` header (validated alias — some proxies use this).
    3. W3C ``traceparent`` trace-id component (32 hex chars).
    4. Fresh UUID hex generated internally.
    """
    for header in ("X-Correlation-ID", "X-Request-ID"):
        raw = request.headers.get(header, "").strip()
        if raw and len(raw) <= _MAX_CORR_ID_LEN and _SAFE_CORR_ID_RE.match(raw):
            return raw, False

    tp = request.headers.get("traceparent", "").strip()
    m = _TRACEPARENT_RE.match(tp)
    if m:
        return m.group(1), False  # 32-hex trace-id portion

    return uuid.uuid4().hex, True


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Sets ``request.state.correlation_id`` from the incoming header (or
    generates one) and installs a fully-populated :class:`RequestContext`
    for the duration of each request.

    The context is **always** cleared in a ``finally`` block to prevent
    leakage across async tasks.  ``user_id`` is enriched later by the
    auth dependency (``dependencies.py``).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        corr_id, was_generated = _extract_correlation_id(request)

        if was_generated:
            logger.debug("Generated correlation ID (none provided): %s", corr_id)
        else:
            logger.debug("Using incoming correlation ID: %s", corr_id)

        request.state.correlation_id = corr_id

        ctx = RequestContext(
            correlation_id=corr_id,
            session_id=request.headers.get("X-Session-ID"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            request_path=request.url.path,
            method=request.method,
        )
        token = set_request_context(ctx)
        request.state.request_context = ctx

        try:
            response = await call_next(request)
        finally:
            # Always restore the previous context frame to prevent leakage.
            clear_request_context(token)

        response.headers["X-Correlation-ID"] = corr_id
        return response
