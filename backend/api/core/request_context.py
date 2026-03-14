"""
Request Context — Thread-safe identity propagation for the request lifecycle.

Stores correlation_id, user_id, session_id, and thread_id in a
``contextvars.ContextVar`` so any code running inside a request
(including ``asyncio.to_thread`` callees) can read them without
passing arguments through every layer.

Middleware sets the context early; services read it via ``get_request_context()``.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

_REQUEST_CTX: ContextVar["RequestContext"] = ContextVar("request_ctx")


@dataclass(slots=True)
class RequestContext:
    """Identity bag carried through a single request."""
    correlation_id: str = ""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "thread_id": self.thread_id,
        }


def set_request_context(ctx: RequestContext) -> None:
    """Install the context for the current async task / thread."""
    _REQUEST_CTX.set(ctx)


def get_request_context() -> RequestContext:
    """
    Return the current request context.

    Returns a blank ``RequestContext`` if none has been set (e.g. background
    workers not running inside a request).
    """
    return _REQUEST_CTX.get(RequestContext())
