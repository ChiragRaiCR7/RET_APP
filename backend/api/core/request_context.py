"""
Request Context — Thread-safe identity propagation for the request lifecycle.

Stores correlation_id, user_id, session_id, ip_address, user_agent,
request_path, and method in a ``contextvars.ContextVar`` so any code
running inside a request (including ``asyncio.to_thread`` callees) can
read them without passing arguments through every layer.

Middleware sets the context early; services read it via ``get_request_context()``.
The ``set_request_context()`` return value (a reset Token) should be passed to
``clear_request_context()`` at the end of each request to prevent leakage.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Optional

_REQUEST_CTX: ContextVar["RequestContext"] = ContextVar("request_ctx")


@dataclass(slots=True)
class RequestContext:
    """Identity bag carried through a single request."""
    # Auto-generate a unique correlation ID if one is not supplied.
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    # HTTP metadata — wired up by CorrelationIdMiddleware / LoggingMiddleware
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    method: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_path": self.request_path,
            "method": self.method,
        }


def set_request_context(ctx: RequestContext) -> Token:
    """
    Install the context for the current async task / thread.

    Returns the reset Token so callers can restore the previous state via
    ``clear_request_context(token)``.
    """
    return _REQUEST_CTX.set(ctx)


def get_request_context() -> RequestContext:
    """
    Return the current request context.

    Returns a new ``RequestContext`` (with an auto-generated correlation_id)
    if none has been set — safe for background workers outside a request.
    """
    return _REQUEST_CTX.get(RequestContext())


def clear_request_context(token: Optional[Token] = None) -> None:
    """
    Reset the context after request completion.

    Pass the Token returned by ``set_request_context`` to restore the
    previous context frame.  Without a token, installs a fresh blank
    context — still prevents leakage between tasks.
    """
    if token is not None:
        _REQUEST_CTX.reset(token)
    else:
        _REQUEST_CTX.set(RequestContext())
