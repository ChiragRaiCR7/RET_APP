"""
Rate limiting middleware with optional trusted-proxy X-Forwarded-For support and configurable limits.

Improvements:
- Uses settings.RATE_LIMIT_EXEMPT_PATHS (should be built using settings.API_PREFIX in config)
- Trusts X-Forwarded-For ONLY if enabled and request comes from a trusted proxy
- Better key strategy: prefer authenticated user_id if available; else IP (+ small UA suffix)
- Correlation ID included in rate-limit exceeded log entries.
- Structured JSONResponse (matching API error schema) returned on 429 instead of HTTPException.
- In-memory block/allow/error counters exposed via get_rate_limit_stats().
- Fail-open on cache errors (do not block requests if cache fails)
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from api.core.config import settings
from api.core.logging_config import get_logger
from api.core.session_cache import get_session_cache, SessionCache

logger = get_logger(__name__)

# Lazy-initialized async session cache (set on first dispatch)
_cache: SessionCache | None = None

# In-memory rate-limit event counters (reset on process restart)
_rate_limit_stats: dict[str, int] = {"allowed": 0, "blocked": 0, "errors": 0}


def get_rate_limit_stats() -> dict[str, int]:
    """Return a snapshot of in-memory rate-limit event counters."""
    return dict(_rate_limit_stats)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit middleware using LRU session cache.

    Features:
    - Optional X-Forwarded-For support with trusted proxies
    - Configurable limits from settings
    - Retry-After header on 429 responses
    - Exempt paths for health checks and auth endpoints
    """

    def __init__(
        self,
        app,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
        key_func: Optional[Callable[[Request], str]] = None,
    ):
        super().__init__(app)
        # Keep compatibility: fall back to RATE_LIMIT_REQUESTS_PER_MINUTE if present
        self.max_requests = max_requests or getattr(settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", settings.RATE_LIMIT_REQUESTS)
        self.window = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self.key_func = key_func or self._default_key

        # Trusted proxy config (safe defaults)
        self._trust_xff = bool(getattr(settings, "RATE_LIMIT_TRUST_XFF", False))
        self._trusted_proxies = set(getattr(settings, "RATE_LIMIT_TRUSTED_PROXIES", []) or [])

    def _client_ip(self, request: Request) -> str:
        """
        Determine client IP with optional proxy awareness.

        Security-first:
        - Do NOT trust X-Forwarded-For unless RATE_LIMIT_TRUST_XFF=True
        - If trusted proxies list is set, only trust XFF when immediate client is trusted
        """
        direct_ip = request.client.host if request.client else "unknown"

        if not self._trust_xff:
            return direct_ip

        # If a trusted proxy list exists, only honor XFF if request came from that proxy
        if self._trusted_proxies and direct_ip not in self._trusted_proxies:
            return direct_ip

        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # Take the first IP in chain (original client)
            return xff.split(",")[0].strip()

        return direct_ip

    def _default_key(self, request: Request) -> str:
        """
        Build a rate limit key.

        Improvement:
        - Prefer authenticated user id if available (set by auth dependency/middleware)
        - Else fallback to IP (+ short UA suffix to reduce NAT collisions)
        """
        user_id = getattr(request.state, "user_id", None)
        if user_id is not None:
            return f"rate:user:{user_id}"

        ip = self._client_ip(request)
        ua = (request.headers.get("User-Agent") or "")[:32]
        return f"rate:ip:{ip}:{ua}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.client is None:
            return await call_next(request)

        # Use settings-provided exempt paths (should be prefix-correct from config)
        exempt_paths = getattr(settings, "RATE_LIMIT_EXEMPT_PATHS", None) or [
            "/health",
            "/docs",
            "/openapi.json",
        ]

        if any(request.url.path.startswith(path) for path in exempt_paths):
            return await call_next(request)

        key = self.key_func(request)
        now = int(time.time())
        window_key = f"{key}:{now // self.window}"

        try:
            global _cache
            if _cache is None:
                _cache = await get_session_cache()

            current = await _cache.get(window_key)
            current = int(current) if current is not None else 0

            if current >= self.max_requests:
                retry_after = int(self.window - (now % self.window))
                corr_id = getattr(request.state, "correlation_id", None)

                logger.warning(
                    "Rate limit exceeded: %s %s (cid=%s key=%s current=%d max=%d)",
                    request.method,
                    request.url.path,
                    corr_id,
                    key,
                    current,
                    self.max_requests,
                    extra={"extra_fields": {"retry_after": retry_after}},
                )
                _rate_limit_stats["blocked"] += 1

                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "Rate limit exceeded. Please slow down your requests.",
                        "error_code": "rate_limit_exceeded",
                        "correlation_id": corr_id,
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            # Increment counter with TTL matching window
            await _cache.set(window_key, current + 1, ttl_seconds=self.window)
            _rate_limit_stats["allowed"] += 1

        except Exception as e:
            _rate_limit_stats["errors"] += 1
            # Fail-open: log cache error but do not block the request
            logger.warning(
                "Rate limiter cache error (fail-open): %s | key=%s path=%s",
                e,
                key,
                request.url.path,
            )

        return await call_next(request)