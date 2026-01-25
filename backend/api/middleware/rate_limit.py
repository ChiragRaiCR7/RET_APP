import time
import redis
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from api.core.config import settings

redis_client = redis.Redis.from_url(settings.REDIS_URL)

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        key = f"rate:{ip}"

        current = redis_client.get(key)
        if current and int(current) > 100:
            raise HTTPException(429, "Rate limit exceeded")

        pipe = redis_client.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, 60)
        pipe.execute()

        return await call_next(request)
