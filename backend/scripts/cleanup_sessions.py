
#!/usr/bin/env python3
"""
Cleanup expired login sessions (Async SQLAlchemy compatible).

Why this rewrite:
- Your DB layer is async; prior script used sync SessionLocal + query/delete.

Run:
  python scripts/cleanup_sessions.py
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete

import api.core.database as database

try:
    from api.models import LoginSession
except Exception:
    from api.models.models import LoginSession  # fallback


async def cleanup_sessions_async() -> int:
    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized (SessionLocal is None)")

    now = datetime.now(timezone.utc)

    try:
        async with database.SessionLocal() as db:
            stmt = delete(LoginSession).where(LoginSession.expires_at < now)
            result = await db.execute(stmt)
            await db.commit()

            rowcount = getattr(result, "rowcount", None)
            deleted = int(rowcount) if isinstance(rowcount, int) else 0
            print(f"Deleted {deleted} expired sessions")
            return 0
    finally:
        await database.close_db()


def main() -> int:
    return asyncio.run(cleanup_sessions_async())


if __name__ == "__main__":
    raise SystemExit(main())
