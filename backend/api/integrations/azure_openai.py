"""
Azure OpenAI Integration — Retry Utility
=========================================
Resilient exponential-backoff retry for transient Azure OpenAI errors.

Handles:
  - 429 rate-limit      (RateLimitError)
  - Timeouts            (APITimeoutError, TimeoutError, httpx.TimeoutException)
  - 5xx server errors   (APIError with status >= 500)
  - Network turbulence  (ConnectionError, httpx.NetworkError, aiohttp.ClientError)

Public API:
  retry_sync(fn, ...)         — blocking retry
  retry_async(fn, ...)        — non-blocking async retry
  retry(fn, ...)              — auto-detects sync vs async
  @retryable(...)             — decorator form

  RetryConfig                 — tuneable configuration object
  CircuitBreaker              — plug-in circuit breaker
  RetryMetrics                — observable counters
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generator, Mapping, NoReturn, Optional, TypeVar, Union, cast, overload

T = TypeVar("T")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Graceful import — sentinel classes preserve semantic meaning if openai
#    or httpx/aiohttp are absent, rather than collapsing everything to Exception.
# ---------------------------------------------------------------------------

try:
    from openai import APIError, APITimeoutError, RateLimitError  # type: ignore
    OPENAI_AVAILABLE = True
except ImportError:
    class RateLimitError(Exception):   pass   # type: ignore[no-redef]
    class APITimeoutError(Exception):  pass   # type: ignore[no-redef]
    class APIError(Exception):         pass   # type: ignore[no-redef]
    OPENAI_AVAILABLE = False

try:
    import httpx  # type: ignore
    _HTTPX_ERRORS = (httpx.TimeoutException, httpx.NetworkError)
except ImportError:
    class _HttpxTimeoutException(Exception): pass
    class _HttpxNetworkError(Exception):     pass
    _HTTPX_ERRORS = (_HttpxTimeoutException, _HttpxNetworkError)  # type: ignore[assignment]

try:
    import aiohttp  # type: ignore
    _AIOHTTP_ERRORS = (aiohttp.ClientError,)
except ImportError:
    class _AiohttpClientError(Exception): pass
    _AIOHTTP_ERRORS = (_AiohttpClientError,)  # type: ignore[assignment]

# All errors that warrant a retry attempt (before 5xx APIError check)
_RETRYABLE = (
    RateLimitError,
    APITimeoutError,
    TimeoutError,
    ConnectionError,
    *_HTTPX_ERRORS,
    *_AIOHTTP_ERRORS,
)


# ---------------------------------------------------------------------------
# 2. Configuration object — no more buried magic numbers
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """
    All retry knobs in one place. Pass a custom instance to any retry function
    or use RetryConfig.from_env() to load from environment variables.

    Example — high-traffic production:
        cfg = RetryConfig(max_retries=6, base_delay=0.5, total_timeout=120.0)

    Example — background batch job:
        cfg = RetryConfig(max_retries=8, base_delay=2.0, total_timeout=300.0)
    """
    max_retries:   int   = 4
    base_delay:    float = 1.0    # seconds
    max_delay:     float = 60.0   # seconds
    total_timeout: float = 120.0  # abort if elapsed exceeds this (seconds)
    full_jitter:   bool  = True   # AWS-style full jitter vs ±20% multiplicative

    @classmethod
    def from_env(cls) -> "RetryConfig":
        """Load configuration from environment variables, falling back to defaults."""
        import os
        return cls(
            max_retries   = int(os.getenv("AZURE_RETRY_MAX",     cls.max_retries)),
            base_delay    = float(os.getenv("AZURE_RETRY_BASE",  cls.base_delay)),
            max_delay     = float(os.getenv("AZURE_RETRY_MAX_D", cls.max_delay)),
            total_timeout = float(os.getenv("AZURE_RETRY_TIMEOUT", cls.total_timeout)),
            full_jitter   = os.getenv("AZURE_RETRY_FULL_JITTER", "1") != "0",
        )


# ---------------------------------------------------------------------------
# 3. Metrics — lightweight counters; swap body for Prometheus/OTel as needed
# ---------------------------------------------------------------------------

@dataclass
class RetryMetrics:
    """
    Observable retry counters. Wire these into your telemetry layer.

    Usage with Prometheus (conceptual):
        metrics = RetryMetrics()
        ...
        # replace increment() with prometheus_client.Counter.inc()
    """
    attempts:       int = field(default=0, repr=True)
    successes:      int = field(default=0, repr=True)
    failures:       int = field(default=0, repr=True)
    rate_limits:    int = field(default=0, repr=True)
    server_errors:  int = field(default=0, repr=True)
    circuit_breaks: int = field(default=0, repr=True)

    def record_attempt(self)      -> None: self.attempts      += 1
    def record_success(self)      -> None: self.successes      += 1
    def record_failure(self)      -> None: self.failures       += 1
    def record_rate_limit(self)   -> None: self.rate_limits    += 1
    def record_server_error(self) -> None: self.server_errors  += 1
    def record_circuit_break(self)-> None: self.circuit_breaks += 1

    def as_dict(self) -> dict[str, int]:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}  # type: ignore[attr-defined]


# Module-level default metrics singleton — importable for process-wide aggregation
default_metrics = RetryMetrics()


# ---------------------------------------------------------------------------
# 4. Circuit breaker — calm the storm when upstream is truly down
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    """
    Simple half-open circuit breaker.

    States:
      CLOSED  — normal operation, calls pass through
      OPEN    — upstream is broken; calls are rejected immediately
      HALF-OPEN — a probe call is allowed to test recovery

    Example:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        retry_sync(fn, circuit_breaker=breaker)
    """
    failure_threshold: int   = 5
    recovery_timeout:  float = 30.0   # seconds before moving to HALF-OPEN

    _failures:     int   = field(default=0,   init=False, repr=False)
    _opened_at:    float = field(default=0.0, init=False, repr=False)
    _state:        str   = field(default="CLOSED", init=False)

    def is_open(self) -> bool:
        if self._state == "OPEN":
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = "HALF-OPEN"
                return False
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._state = "CLOSED"

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state    = "OPEN"
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker OPENED after %d consecutive failures",
                self._failures,
            )

    @property
    def state(self) -> str:
        return self._state


# ---------------------------------------------------------------------------
# 5. Internal helpers
# ---------------------------------------------------------------------------

def _headers(exc: Exception) -> Optional[Mapping[str, Any]]:
    for src in (exc, getattr(exc, "response", None)):
        if src is None:
            continue
        hdrs = getattr(src, "headers", None)
        if hdrs:
            return hdrs
        if isinstance(src, dict):
            hdrs = src.get("headers")
            if hdrs:
                return hdrs
    return None


def _retry_after_hint(exc: Exception) -> Optional[float]:
    hdrs = _headers(exc)
    if not hdrs:
        return None
    ra = hdrs.get("Retry-After") or hdrs.get("retry-after")
    try:
        return float(ra) if ra is not None else None
    except (TypeError, ValueError):
        return None


def _status_code(exc: Exception) -> Optional[int]:
    for src in (exc, getattr(exc, "response", None)):
        if src is None:
            continue
        code = getattr(src, "status_code", None) or (src.get("status_code") if isinstance(src, dict) else None)
        if code is not None:
            try:
                return int(code)
            except (TypeError, ValueError):
                pass
    return None


def _compute_delay(attempt: int, cfg: RetryConfig, hint: Optional[float]) -> float:
    """
    Full-jitter (AWS-recommended) or bounded multiplicative jitter.

    Full jitter:        random.uniform(0, base * 2^attempt)
    Multiplicative:     base * 2^attempt * uniform(0.8, 1.2)

    Full jitter produces better thundering-herd protection in distributed systems.
    """
    if hint is not None:
        return max(0.0, min(hint, cfg.max_delay))
    cap = min(cfg.base_delay * (2 ** attempt), cfg.max_delay)
    if cfg.full_jitter:
        return random.uniform(0.0, cap)
    return cap * random.uniform(0.8, 1.2)


# ---------------------------------------------------------------------------
# 6. Core retry engine — all decision logic lives here, zero sleep calls
# ---------------------------------------------------------------------------

class _RetryEngine:
    """
    Encapsulates the full retry decision loop.

    Sync/async wrappers call next_delay() and only differ in how they sleep.
    This is the single source of truth for retry logic.
    """

    def __init__(
        self,
        cfg: RetryConfig,
        name: str,
        request_id: str,
        metrics: RetryMetrics,
        circuit_breaker: Optional[CircuitBreaker],
    ) -> None:
        self.cfg             = cfg
        self.name            = name
        self.request_id      = request_id
        self.metrics         = metrics
        self.circuit_breaker = circuit_breaker
        self.last_exc: Optional[Exception] = None
        self._started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started

    def timed_out(self) -> bool:
        return self.elapsed >= self.cfg.total_timeout

    def check_circuit(self) -> None:
        """Raise immediately if the circuit breaker is open."""
        if self.circuit_breaker and self.circuit_breaker.is_open():
            self.metrics.record_circuit_break()
            raise RuntimeError(
                f"{self.name}: circuit breaker is OPEN "
                f"(state={self.circuit_breaker.state}, request_id={self.request_id})"
            )

    def evaluate(self, exc: Exception, attempt: int) -> tuple[bool, float]:
        """
        Returns (should_retry, delay).
        Side-effects: updates metrics, logs.
        """
        # --- 7. Global timeout guard ---
        if self.timed_out():
            logger.warning(
                "Azure OpenAI retry aborted: total_timeout=%.1fs exceeded (%s, request_id=%s)",
                self.cfg.total_timeout, self.name, self.request_id,
            )
            return False, 0.0

        if attempt >= self.cfg.max_retries:
            return False, 0.0

        hint = None

        if isinstance(exc, _RETRYABLE):
            if isinstance(exc, RateLimitError):
                self.metrics.record_rate_limit()
            hint = _retry_after_hint(exc)
            delay = _compute_delay(attempt, self.cfg, hint)
            self._log_retry(exc, attempt, delay, status_code=None)
            return True, delay

        if isinstance(exc, APIError):
            code = _status_code(exc)
            if code and code >= 500:
                self.metrics.record_server_error()
                delay = _compute_delay(attempt, self.cfg, None)
                self._log_retry(exc, attempt, delay, status_code=code)
                return True, delay

        return False, 0.0

    def on_success(self) -> None:
        self.metrics.record_success()
        if self.circuit_breaker:
            self.circuit_breaker.record_success()

    def on_final_failure(self, exc: Exception) -> None:
        self.metrics.record_failure()
        if self.circuit_breaker:
            self.circuit_breaker.record_failure()
        logger.error(
            "Azure OpenAI call failed after %d attempts (%.2fs elapsed) — "
            "name=%s request_id=%s error_type=%s error=%s",
            self.cfg.max_retries + 1, self.elapsed,
            self.name, self.request_id, type(exc).__name__, exc,
            extra=self._base_log_extra(exc),
        )

    def _log_retry(self, exc: Exception, attempt: int, delay: float,
                   status_code: Optional[int]) -> None:
        self.metrics.record_attempt()
        kind = f"server_error status={status_code}" if status_code else type(exc).__name__
        logger.warning(
            "Azure OpenAI transient error — %s attempt %d/%d retrying in %.2fs "
            "(name=%s request_id=%s elapsed=%.2fs)",
            kind, attempt + 1, self.cfg.max_retries + 1, delay,
            self.name, self.request_id, self.elapsed,
            extra={
                **self._base_log_extra(exc),
                "attempt":      attempt + 1,
                "max_attempts": self.cfg.max_retries + 1,
                "delay_s":      round(delay, 3),
                "status_code":  status_code,
            },
        )

    def _base_log_extra(self, exc: Exception) -> dict[str, Any]:
        return {
            "name":            self.name,
            "request_id":      self.request_id,
            "elapsed_s":       round(self.elapsed, 3),
            "error_type":      type(exc).__name__,
            "error":           str(exc),
            "metrics":         self.metrics.as_dict(),
        }

    def finalize(self) -> NoReturn:
        if self.last_exc is None:
            raise RuntimeError(
                f"{self.name}: retry loop exited without capturing an exception "
                f"(request_id={self.request_id})"
            )
        self.on_final_failure(self.last_exc)
        raise self.last_exc


# ---------------------------------------------------------------------------
# 7. Public retry functions
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = RetryConfig()


def retry_sync(
    fn: Callable[[], T],
    *,
    config:          RetryConfig              = _DEFAULT_CONFIG,
    name:            str                      = "azure_openai_call",
    request_id:      Optional[str]            = None,
    metrics:         RetryMetrics             = default_metrics,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> T:
    """
    Blocking retry with exponential backoff.

        result = retry_sync(
            lambda: client.embeddings.create(model=..., input=...),
            config=RetryConfig(max_retries=3),
            name="embedding_call",
        )
    """
    engine = _RetryEngine(
        cfg=config,
        name=name,
        request_id=request_id or str(uuid.uuid4()),
        metrics=metrics,
        circuit_breaker=circuit_breaker,
    )
    for attempt in range(config.max_retries + 1):
        engine.check_circuit()
        try:
            result = fn()
            engine.on_success()
            return result
        except Exception as exc:
            should_retry, delay = engine.evaluate(exc, attempt)
            engine.last_exc = exc
            if should_retry:
                time.sleep(delay)
            else:
                break
    engine.finalize()


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    config:          RetryConfig              = _DEFAULT_CONFIG,
    name:            str                      = "azure_openai_call_async",
    request_id:      Optional[str]            = None,
    metrics:         RetryMetrics             = default_metrics,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> T:
    """
    Non-blocking async retry with exponential backoff.

        result = await retry_async(
            lambda: async_client.chat.completions.create(...),
            config=RetryConfig(total_timeout=60.0),
            name="chat_call",
        )
    """
    engine = _RetryEngine(
        cfg=config,
        name=name,
        request_id=request_id or str(uuid.uuid4()),
        metrics=metrics,
        circuit_breaker=circuit_breaker,
    )
    for attempt in range(config.max_retries + 1):
        engine.check_circuit()
        try:
            result = await fn()
            engine.on_success()
            return result
        except Exception as exc:
            should_retry, delay = engine.evaluate(exc, attempt)
            engine.last_exc = exc
            if should_retry:
                await asyncio.sleep(delay)
            else:
                break
    engine.finalize()


@overload
def retry(
    fn: Callable[[], T],
    **kwargs: Any,
) -> T:
    ...


@overload
def retry(
    fn: Callable[[], Awaitable[T]],
    **kwargs: Any,
) -> Awaitable[T]:
    ...


def retry(
    fn: Union[Callable[[], T], Callable[[], Awaitable[T]]],
    **kwargs: Any,
) -> Any:
    """
    Unified entry point — auto-detects sync vs async callable.

        # sync
        result = retry(lambda: client.embeddings.create(...), name="embed")

        # async — returns a coroutine, must be awaited
        result = await retry(lambda: async_client.chat.completions.create(...))
    """
    if inspect.iscoroutinefunction(fn):
        async_fn = cast(Callable[[], Awaitable[T]], fn)
        return retry_async(async_fn, **kwargs)
    sync_fn = cast(Callable[[], T], fn)
    return retry_sync(sync_fn, **kwargs)


# ---------------------------------------------------------------------------
# 8. Decorator interface
# ---------------------------------------------------------------------------

def retryable(
    *,
    config:          RetryConfig              = _DEFAULT_CONFIG,
    name:            Optional[str]            = None,
    metrics:         RetryMetrics             = default_metrics,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Callable:
    """
    Decorator that wraps a function (sync or async) with retry logic.

    Usage:

        @retryable(config=RetryConfig(max_retries=3), name="embed_call")
        def get_embedding(text: str):
            return client.embeddings.create(model=..., input=text)

        @retryable(config=RetryConfig(total_timeout=60.0))
        async def chat_completion(messages: list):
            return await async_client.chat.completions.create(...)
    """
    def decorator(fn: Callable) -> Callable:
        resolved_name = name or fn.__qualname__

        if inspect.iscoroutinefunction(fn):
            async def async_wrapper(*args: Any, **kw: Any) -> Any:
                return await retry_async(
                    lambda: fn(*args, **kw),
                    config=config, name=resolved_name,
                    metrics=metrics, circuit_breaker=circuit_breaker,
                )
            async_wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
            return async_wrapper
        else:
            def sync_wrapper(*args: Any, **kw: Any) -> Any:
                return retry_sync(
                    lambda: fn(*args, **kw),
                    config=config, name=resolved_name,
                    metrics=metrics, circuit_breaker=circuit_breaker,
                )
            sync_wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
            return sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# 9. Backwards-compatible aliases
# ---------------------------------------------------------------------------

def _retry_with_backoff(
    fn: Callable[[], T],
    **kwargs: Any,
) -> T:
    """
    Backwards-compatible alias for retry_sync.
    Used by advanced_ai_service.py for synchronous retry with exponential backoff.
    """
    return retry_sync(fn, **kwargs)


async def _retry_with_backoff_async(
    fn: Callable[[], Awaitable[T]],
    **kwargs: Any,
) -> T:
    """
    Backwards-compatible alias for retry_async.
    Used by advanced_ai_service.py for asynchronous retry with exponential backoff.
    """
    return await retry_async(fn, **kwargs)