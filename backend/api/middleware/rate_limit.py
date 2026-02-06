"""
Rate limiting middleware with X-Forwarded-For support and configurable limits.
"""
import time
import logging
from typing import Callable, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from api.core.config import settings
from api.core.session_cache import get_session_cache

try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)

# Get session cache for rate limiting
_cache = get_session_cache()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit middleware using LRU session cache.
    
    Features:
    - X-Forwarded-For support for proxied requests
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
        self.max_requests = max_requests or settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        self.window = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self.key_func = key_func or self._default_key
    
    def _default_key(self, request: Request) -> str:
        """
        Get the rate limit key for a request.
        
        Uses X-Forwarded-For if available (for proxied requests),
        otherwise falls back to client IP.
        """
        # Prefer X-Forwarded-For if set (behind proxies/load balancers)
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # Take the first IP in the chain (original client)
            ip = xff.split(",")[0].strip()
        elif request.client:
            ip = request.client.host
        else:
            ip = "unknown"
        
        return f"rate:{ip}"
    
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.client is None:
            return await call_next(request)
        
        # Get exempt paths from settings
        exempt_paths = getattr(
            settings, 
            "RATE_LIMIT_EXEMPT_PATHS", 
            ["/health", "/api/auth/refresh", "/api/auth/me", "/docs", "/openapi.json"]
        )
        
        # Check if path should be exempted
        if any(request.url.path.startswith(path) for path in exempt_paths):
            return await call_next(request)
        
        key = self.key_func(request)
        now = int(time.time())
        window_key = f"{key}:{now // self.window}"
        
        try:
            # Get current count from cache
            current = _cache.get(window_key)
            if current is None:
                current = 0
            else:
                current = int(current)
            
            # Check rate limit
            if current >= self.max_requests:
                # Calculate retry-after time
                retry_after = int(self.window - (now % self.window))
                
                # Log rate limit hit
                log_msg = f"Rate limit exceeded for {key} (current: {current}, max: {self.max_requests})"
                if HAS_LOGURU:
                    logger.warning(log_msg)
                else:
                    logger.warning(log_msg)
                
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please slow down your requests.",
                    headers={"Retry-After": str(retry_after)},
                )
            
            # Increment counter with TTL matching window
            _cache.set(window_key, current + 1, ttl_seconds=self.window)
            
        except HTTPException:
            raise
        except Exception as e:
            # Log cache failure but don't block the request
            log_msg = f"Rate limiter cache error: {e}"
            if HAS_LOGURU:
                logger.warning(log_msg)
            else:
                logger.warning(log_msg)
        
        return await call_next(request)

