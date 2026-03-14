"""
Performance Metrics — Structured Timing for Hot Paths

Provides a lightweight context manager and decorator for measuring
wall-clock latency and throughput of critical operations.  Emits
structured log events that include operation name, duration, item
counts, and optional extra fields so they can be correlated with
request/session/user identity added by middleware.

Gated behind ``settings.FEATURE_PERF_METRICS``.  When the flag is
False the helpers are no-ops (nanosecond overhead).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from api.core.config import settings

logger = logging.getLogger("ret.metrics")

F = TypeVar("F", bound=Callable[..., Any])

_ENABLED: bool = getattr(settings, "FEATURE_PERF_METRICS", False)


# ------------------------------------------------------------------
# Core timing helper
# ------------------------------------------------------------------

@contextmanager
def timed_block(
    operation: str,
    *,
    items: Optional[int] = None,
    size_bytes: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """
    Context manager that logs structured timing on exit.

    Usage::

        with timed_block("convert_xml", items=len(files)):
            do_work()
    """
    if not _ENABLED:
        yield
        return

    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        payload: Dict[str, Any] = {
            "op": operation,
            "elapsed_ms": round(elapsed_ms, 2),
        }
        if items is not None:
            payload["items"] = items
            if elapsed_ms > 0:
                payload["items_per_sec"] = round(items / (elapsed_ms / 1000.0), 1)
        if size_bytes is not None:
            payload["size_bytes"] = size_bytes
            if elapsed_ms > 0:
                payload["mb_per_sec"] = round(
                    (size_bytes / (1024 * 1024)) / (elapsed_ms / 1000.0), 2
                )
        if extra:
            payload.update(extra)
        logger.info(
            "perf_metric: %s %.1fms", operation, elapsed_ms,
            extra={"extra_fields": payload},
        )


# ------------------------------------------------------------------
# Decorator for sync functions
# ------------------------------------------------------------------

def measure(operation: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator that wraps a **sync** function with ``timed_block``.

    The ``operation`` name defaults to the function's qualified name.
    """
    def decorator(fn: F) -> F:
        if not _ENABLED:
            return fn
        op = operation or fn.__qualname__

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with timed_block(op):
                return fn(*args, **kwargs)

        return cast(F, wrapper)
    return decorator


# ------------------------------------------------------------------
# Decorator for async functions
# ------------------------------------------------------------------

def measure_async(operation: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator that wraps an **async** function with timing.

    The ``operation`` name defaults to the function's qualified name.
    """
    def decorator(fn: F) -> F:
        if not _ENABLED:
            return fn
        op = operation or fn.__qualname__

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                logger.info(
                    "perf_metric: %s %.1fms", op, elapsed_ms,
                    extra={"extra_fields": {"op": op, "elapsed_ms": round(elapsed_ms, 2)}},
                )

        return cast(F, wrapper)
    return decorator
