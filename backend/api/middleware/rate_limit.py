"""
Rate limiting middleware with optional trusted-proxy X-Forwarded-For support and configurable limits.

Non-breaking improvements:
- Uses settings.RATE_LIMIT_EXEMPT_PATHS (should be built using settings.API_PREFIX in config)
- Trusts X-Forwarded-For ONLY if enabled and request comes from a trusted proxy
- Better key strategy: prefer authenticated user_id if available; else IP (+ small UA suffix)
- Unified logging for stdlib + loguru
- Fail-open on cache errors (do not block requests if cache fails)
"""

from __future__ import annotations

import time
import logging
from typing import Callable, Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from api.core.config import settings
from api.core.session_cache import get_session_cache, SessionCache

try:
    from loguru import logger as loguru_logger  # type: ignore
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    loguru_logger = None

_std_logger = logging.getLogger(__name__)

# Lazy-initialized async session cache (set on first dispatch)
_cache: SessionCache | None = None


def _log(level: str, msg: str, **fields) -> None:
    """
    Unified logging helper for stdlib + loguru.

    - loguru: logger.bind(**fields).log(...)
    - stdlib: logger.<level>(..., extra={...})
    """
    if HAS_LOGURU and loguru_logger is not None:
        loguru_logger.bind(**fields).log(level.upper(), msg)
    else:
        extra = {"extra_fields": fields} if fields else None
        getattr(_std_logger, level.lower(), _std_logger.info)(msg, extra=extra)


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

                _log(
                    "warning",
                    "Rate limit exceeded",
                    key=key,
                    window_key=window_key,
                    current=current,
                    max=self.max_requests,
                    retry_after=retry_after,
                    path=request.url.path,
                )

                # Raise 429 with Retry-After
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please slow down your requests.",
                    headers={"Retry-After": str(retry_after)},
                )

            # Increment counter with TTL matching window
            await _cache.set(window_key, current + 1, ttl_seconds=self.window)

        except HTTPException:
            raise
        except Exception as e:
            # Fail-open: log cache failure but do not block request
            _log("warning", "Rate limiter cache error (fail-open)", error=str(e), key=key, path=request.url.path)

        return await call_next(request)