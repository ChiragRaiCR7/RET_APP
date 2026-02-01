import time
from typing import Optional, Any
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from api.core.session_cache import get_session_cache

# Get session cache for rate limiting
_cache = get_session_cache()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit middleware using LRU session cache
    Replaces Redis with SQLite-backed in-memory cache
    """
    
    async def dispatch(self, request: Request, call_next):
        if request.client is None:
            return await call_next(request)
        
        # Exempt certain endpoints from rate limiting
        exempt_paths = [
            "/health",
            "/api/auth/refresh",
            "/api/auth/me",
            "/docs",
            "/openapi.json",
        ]
        
        # Check if path should be exempted
        if any(request.url.path.startswith(path) for path in exempt_paths):
            return await call_next(request)
        
        ip = request.client.host
        key = f"rate:{ip}"
        
        try:
            # Get current count from cache
            current = _cache.get(key)
            if current is None:
                current = 0
            else:
                current = int(current)
            
            # Check rate limit (500 requests per minute - more reasonable for admin dashboards)
            if current > 500:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please slow down your requests."
                )
            
            # Increment counter
            _cache.set(key, current + 1, ttl_seconds=60)
            
        except HTTPException:
            raise
        except Exception as e:
            # If cache fails, just pass through
            # This ensures rate limit errors don't break the app
            pass
        
        return await call_next(request)

