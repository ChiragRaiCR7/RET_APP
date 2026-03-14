
"""
Azure OpenAI Integration — Retry Utility

Provides exponential-backoff retry for transient Azure OpenAI errors:
- 429 rate-limit (RateLimitError)
- timeouts (APITimeoutError)
- 5xx server errors (APIError status >= 500)

Used by UnifiedRAGService's EmbeddingService and ChatService.

Now supports BOTH:
- sync retry: _retry_with_backoff(...)
- async retry: _retry_with_backoff_async(...)
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, Mapping, Optional, TypeVar

T = TypeVar("T")

try:
    from openai import APIError, RateLimitError, APITimeoutError  # type: ignore
    OPENAI_AVAILABLE = True
except ImportError:
    APIError = Exception  # type: ignore[assignment, misc]
    RateLimitError = Exception  # type: ignore[assignment, misc]
    APITimeoutError = Exception  # type: ignore[assignment, misc]
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

_RETRYABLE = (RateLimitError, APITimeoutError)
_MAX_RETRIES = 4
_BASE_DELAY = 1.0  # seconds


# ---------------------------------------------------------------------------
# Shared helpers (used by both sync and async retry)
# ---------------------------------------------------------------------------

def _get_headers_from_exception(exc: Exception) -> Optional[Mapping[str, Any]]:
    headers = getattr(exc, "headers", None)
    if headers:
        return headers

    resp = getattr(exc, "response", None)
    if resp is not None:
        hdrs = getattr(resp, "headers", None)
        if hdrs:
            return hdrs

    return None


def _parse_retry_after(headers: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not headers:
        return None

    try:
        ra = headers.get("Retry-After") or headers.get("retry-after")
        if ra is None:
            return None

        if isinstance(ra, (int, float)):
            return float(ra)

        s = str(ra).strip()
        if not s:
            return None

        return float(s)
    except Exception:
        return None


def _status_code_from_api_error(exc: Exception) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if status is not None:
        try:
            return int(status)
        except Exception:
            return None

    resp = getattr(exc, "response", None)
    if resp is not None:
        status2 = getattr(resp, "status_code", None)
        if status2 is not None:
            try:
                return int(status2)
            except Exception:
                return None

    # Some variants store response as dict-like
    if isinstance(resp, dict) and "status_code" in resp:
        try:
            return int(resp["status_code"])
        except Exception:
            return None

    return None


def _compute_delay(
    *,
    attempt: int,
    base_delay: float,
    max_delay: float,
    retry_after: Optional[float],
) -> float:
    if retry_after is not None:
        delay = float(retry_after)
    else:
        jitter = random.uniform(0.8, 1.2)
        delay = base_delay * (2 ** attempt) * jitter

    # clamp
    delay = max(0.0, min(float(delay), float(max_delay)))
    return delay


# ---------------------------------------------------------------------------
# Sync retry (your original behavior, kept intact)
# ---------------------------------------------------------------------------

def _retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    max_delay: float = 60.0,
    name: str = "azure_openai_call",
    sleep_fn: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.monotonic,
) -> T:
    last_exc: Optional[Exception] = None
    started = time_fn()

    for attempt in range(max_retries + 1):
        try:
            return fn()

        except _RETRYABLE as exc:
            last_exc = exc
            if attempt == max_retries:
                break

            headers = _get_headers_from_exception(exc)
            retry_after = _parse_retry_after(headers)
            delay = _compute_delay(
                attempt=attempt,
                base_delay=base_delay,
                max_delay=max_delay,
                retry_after=retry_after,
            )

            logger.warning(
                "Azure OpenAI transient error (%s) attempt %d/%d; retrying in %.2fs",
                name, attempt + 1, max_retries + 1, delay,
                extra={
                    "name": name,
                    "attempt": attempt + 1,
                    "max_attempts": max_retries + 1,
                    "delay_s": round(delay, 3),
                    "elapsed_s": round(time_fn() - started, 3),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            sleep_fn(delay)

        except APIError as exc:
            status_code = _status_code_from_api_error(exc)
            if status_code is not None and status_code >= 500 and attempt < max_retries:
                last_exc = exc
                delay = _compute_delay(
                    attempt=attempt,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    retry_after=None,
                )

                logger.warning(
                    "Azure OpenAI server error (%s) status=%s attempt %d/%d; retrying in %.2fs",
                    name, status_code, attempt + 1, max_retries + 1, delay,
                    extra={
                        "name": name,
                        "status_code": status_code,
                        "attempt": attempt + 1,
                        "max_attempts": max_retries + 1,
                        "delay_s": round(delay, 3),
                        "elapsed_s": round(time_fn() - started, 3),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                sleep_fn(delay)
            else:
                raise

    if last_exc is None:
        raise RuntimeError(f"{name}: retry loop failed without capturing an exception")

    logger.error(
        "Azure OpenAI call failed after retries (%s) attempts=%d elapsed=%.2fs",
        name, max_retries + 1, time_fn() - started,
        extra={
            "name": name,
            "attempts": max_retries + 1,
            "elapsed_s": round(time_fn() - started, 3),
            "final_error_type": type(last_exc).__name__,
            "final_error": str(last_exc),
        },
    )
    raise last_exc


# ---------------------------------------------------------------------------
# ✅ NEW: Async retry (non-blocking sleep)
# ---------------------------------------------------------------------------

async def _retry_with_backoff_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    max_delay: float = 60.0,
    name: str = "azure_openai_call_async",
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    time_fn: Callable[[], float] = time.monotonic,
) -> T:
    """
    Async version of _retry_with_backoff.

    - `fn` must return an awaitable (e.g., an async function or lambda returning coroutine)
    - Uses non-blocking sleep via asyncio.sleep by default
    """
    last_exc: Optional[Exception] = None
    started = time_fn()

    for attempt in range(max_retries + 1):
        try:
            return await fn()

        except _RETRYABLE as exc:
            last_exc = exc
            if attempt == max_retries:
                break

            headers = _get_headers_from_exception(exc)
            retry_after = _parse_retry_after(headers)
            delay = _compute_delay(
                attempt=attempt,
                base_delay=base_delay,
                max_delay=max_delay,
                retry_after=retry_after,
            )

            logger.warning(
                "Azure OpenAI transient error (%s) attempt %d/%d; retrying in %.2fs",
                name, attempt + 1, max_retries + 1, delay,
                extra={
                    "name": name,
                    "attempt": attempt + 1,
                    "max_attempts": max_retries + 1,
                    "delay_s": round(delay, 3),
                    "elapsed_s": round(time_fn() - started, 3),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            await sleep_fn(delay)

        except APIError as exc:
            status_code = _status_code_from_api_error(exc)
            if status_code is not None and status_code >= 500 and attempt < max_retries:
                last_exc = exc
                delay = _compute_delay(
                    attempt=attempt,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    retry_after=None,
                )

                logger.warning(
                    "Azure OpenAI server error (%s) status=%s attempt %d/%d; retrying in %.2fs",
                    name, status_code, attempt + 1, max_retries + 1, delay,
                    extra={
                        "name": name,
                        "status_code": status_code,
                        "attempt": attempt + 1,
                        "max_attempts": max_retries + 1,
                        "delay_s": round(delay, 3),
                        "elapsed_s": round(time_fn() - started, 3),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                await sleep_fn(delay)
            else:
                raise

    if last_exc is None:
        raise RuntimeError(f"{name}: retry loop failed without capturing an exception")

    logger.error(
        "Azure OpenAI async call failed after retries (%s) attempts=%d elapsed=%.2fs",
        name, max_retries + 1, time_fn() - started,
        extra={
            "name": name,
            "attempts": max_retries + 1,
            "elapsed_s": round(time_fn() - started, 3),
            "final_error_type": type(last_exc).__name__,
            "final_error": str(last_exc),
        },
    )
    raise last_exc