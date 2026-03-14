import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.core.request_context import RequestContext, set_request_context


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Sets ``request.state.correlation_id`` from the incoming header
    (or generates one) and installs a :class:`RequestContext` so that
    downstream code can call ``get_request_context()`` without
    needing access to the ``Request`` object.

    ``user_id`` is populated later by the auth dependency and is
    patched onto the existing context in ``dependencies.py``.
    """

    async def dispatch(self, request: Request, call_next):
        corr_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        request.state.correlation_id = corr_id

        # Seed request context — user_id will be enriched by auth dependency
        ctx = RequestContext(
            correlation_id=corr_id,
            session_id=request.headers.get("X-Session-ID"),
            thread_id=request.headers.get("X-Thread-ID"),
        )
        set_request_context(ctx)
        request.state.request_context = ctx

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response
