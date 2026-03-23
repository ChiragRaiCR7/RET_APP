
"""
Session Cache Module — Async

Implements LRU caching for session data, file metadata, and AI indices.
Uses in-memory LRU + async SQLite persistence (aiosqlite) with WAL mode.

Key changes from sync version:
- aiosqlite replaces sqlite3 for non-blocking DB access
- asyncio.Lock replaces threading.RLock
- All public methods are async def
- Periodic cleanup uses async path
- Global convenience functions are async
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import aiosqlite

try:
    import orjson

    def _dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode()

    def _loads(s: str) -> Any:
        return orjson.loads(s)
except ImportError:
    import json

    _dumps = json.dumps  # type: ignore[assignment]
    _loads = json.loads  # type: ignore[assignment]

from api.core.config import settings

logger = logging.getLogger(__name__)

_MAX_WRITE_RETRIES = 3
_RETRY_DELAY_S = 0.05

# Periodic cleanup cadence
_CLEANUP_EVERY_N_WRITES = 500
_CLEANUP_DELETE_LIMIT = 5000


class SessionCache:
    """
    Async LRU-based session cache with aiosqlite backend for persistence.
    Uses WAL journal mode for better concurrent read/write performance.
    """

    def __init__(self, db_path: Optional[str] = None, max_size: int = 1000):
        self.db_path = Path(db_path or settings.RET_SESSION_DB)
        self.max_size = max_size

        # In-memory cache: key -> (value, created_at)
        self.cache: Dict[str, Tuple[Any, float]] = {}
        # LRU tracking: key -> last_access_ts
        self.access_times: Dict[str, float] = {}

        self.lock = asyncio.Lock()
        self._write_count = 0
        self._initialized = False

        # Cache performance counters
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    async def initialize(self) -> None:
        """Create DB dir and init schema. Must be called once before use."""
        if self._initialized:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        await self._init_db()
        self._initialized = True

    async def _get_conn(self) -> aiosqlite.Connection:
        """Open an aiosqlite connection with WAL mode."""
        conn = await aiosqlite.connect(str(self.db_path), timeout=10)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        return conn

    async def _init_db(self) -> None:
        """Initialize SQLite database for cache persistence."""
        try:
            conn = await self._get_conn()
            try:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_cache (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS ix_session_cache_expires_at "
                    "ON session_cache(expires_at)"
                )
                await conn.commit()
            finally:
                await conn.close()
        except Exception as e:
            logger.error("Failed to initialize cache DB: %s", e, exc_info=True)

    # -----------------------------------------------------------------
    # Public API (all async)
    # -----------------------------------------------------------------

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set a cache entry with optional TTL."""
        trigger_cleanup = False
        async with self.lock:
            if not self._initialized:
                await self.initialize()

            now = time.time()
            expires_at = now + ttl_seconds if ttl_seconds else None

            self.cache[key] = (value, now)
            self.access_times[key] = now

            await self._persist_to_db(key, value, expires_at)

            if len(self.cache) > self.max_size:
                await self._evict_lru()

            self._write_count += 1
            if self._write_count % _CLEANUP_EVERY_N_WRITES == 0:
                trigger_cleanup = True

        # Schedule expired-row cleanup outside the write lock so it does not
        # block concurrent writers for the duration of the DB DELETE.
        if trigger_cleanup:
            asyncio.ensure_future(self._cleanup_expired(limit=_CLEANUP_DELETE_LIMIT))

    async def get(self, key: str) -> Optional[Any]:
        """Get a cache entry, returns None if not found or expired."""
        async with self.lock:
            if not self._initialized:
                await self.initialize()

            if key in self.cache:
                value, _ = self.cache[key]
                self.access_times[key] = time.time()
                self._hits += 1
                return value

            value = await self._load_from_db(key)
            if value is not None:
                now = time.time()
                self.cache[key] = (value, now)
                self.access_times[key] = now
                self._hits += 1
                return value

            self._misses += 1
            return None

    async def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        async with self.lock:
            if not self._initialized:
                await self.initialize()

            existed = key in self.cache
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
            await self._delete_from_db(key)
            return existed

    async def clear_pattern(self, pattern: str) -> int:
        """Delete all cache entries matching a key prefix.

        Returns the number of rows deleted from the persistent store (more
        accurate than the in-memory key count when entries were written
        directly to SQLite by another process).
        """
        async with self.lock:
            if not self._initialized:
                await self.initialize()

            for key in [k for k in list(self.cache.keys()) if k.startswith(pattern)]:
                self.cache.pop(key, None)
                self.access_times.pop(key, None)

            try:
                conn = await self._get_conn()
                try:
                    cursor = await conn.execute(
                        "DELETE FROM session_cache WHERE key LIKE ?", (pattern + "%",)
                    )
                    await conn.commit()
                    return cursor.rowcount or 0
                finally:
                    await conn.close()
            except Exception as e:
                logger.debug("Failed to delete pattern from DB: %s", e, exc_info=True)
                return 0

    async def clear(self) -> None:
        """Clear entire cache (memory and disk)."""
        async with self.lock:
            if not self._initialized:
                await self.initialize()

            self.cache.clear()
            self.access_times.clear()
            try:
                conn = await self._get_conn()
                try:
                    await conn.execute("DELETE FROM session_cache")
                    await conn.commit()
                finally:
                    await conn.close()
            except Exception as e:
                logger.error("Failed to clear DB cache: %s", e, exc_info=True)

    # -----------------------------------------------------------------
    # Internal helpers (all async, called under lock)
    # -----------------------------------------------------------------

    async def _cleanup_expired(self, limit: int = 5000) -> int:
        """Proactively delete expired rows."""
        now = time.time()
        try:
            conn = await self._get_conn()
            try:
                cursor = await conn.execute(
                    "DELETE FROM session_cache "
                    "WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (now,),
                )
                await conn.commit()
                return cursor.rowcount or 0
            finally:
                await conn.close()
        except Exception as e:
            logger.debug("Cache cleanup failed: %s", e, exc_info=True)
            return 0

    async def _persist_to_db(
        self, key: str, value: Any, expires_at: Optional[float] = None
    ) -> None:
        """Persist cache entry to SQLite with retry logic."""
        value_json = _dumps(value) if not isinstance(value, str) else value
        now = time.time()

        for attempt in range(_MAX_WRITE_RETRIES):
            try:
                conn = await self._get_conn()
                try:
                    await conn.execute(
                        """INSERT OR REPLACE INTO session_cache
                           (key, value, created_at, expires_at)
                           VALUES (?, ?, ?, ?)""",
                        (key, value_json, now, expires_at),
                    )
                    await conn.commit()
                finally:
                    await conn.close()
                return
            except Exception as e:
                err_str = str(e).lower()
                if "locked" in err_str and attempt < _MAX_WRITE_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAY_S * (attempt + 1))
                else:
                    logger.debug("Failed to persist cache entry: %s", e, exc_info=True)
                    return

    async def _load_from_db(self, key: str) -> Optional[Any]:
        """Load cache entry from SQLite."""
        try:
            conn = await self._get_conn()
            try:
                cursor = await conn.execute(
                    "SELECT value, expires_at FROM session_cache WHERE key = ?",
                    (key,),
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                value_json, expires_at = row

                if expires_at and expires_at < time.time():
                    await conn.execute(
                        "DELETE FROM session_cache WHERE key = ?", (key,)
                    )
                    await conn.commit()
                    return None

                try:
                    return _loads(value_json)
                except (ValueError, TypeError):
                    return value_json
            finally:
                await conn.close()
        except Exception as e:
            logger.debug("Failed to load from DB: %s", e, exc_info=True)
            return None

    async def _delete_from_db(self, key: str) -> None:
        """Delete cache entry from SQLite."""
        try:
            conn = await self._get_conn()
            try:
                await conn.execute(
                    "DELETE FROM session_cache WHERE key = ?", (key,)
                )
                await conn.commit()
            finally:
                await conn.close()
        except Exception as e:
            logger.debug("Failed to delete from DB: %s", e, exc_info=True)

    async def _evict_lru(self) -> None:
        """Evict the least recently used item."""
        if not self.cache:
            self.access_times.clear()
            return

        # Clean up stale access_times entries
        for k in list(self.access_times.keys()):
            if k not in self.cache:
                self.access_times.pop(k, None)

        if not self.access_times:
            now = time.time()
            for k in self.cache:
                self.access_times[k] = now

        lru_key = min(self.access_times, key=self.access_times.get)  # type: ignore[arg-type]
        self.cache.pop(lru_key, None)
        self.access_times.pop(lru_key, None)
        await self._delete_from_db(lru_key)
        self._evictions += 1

    def get_stats(self) -> dict:
        """Return cache performance metrics (hits, misses, evictions, hit_rate)."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": round(hit_rate, 4),
            "in_memory_keys": len(self.cache),
            "max_size": self.max_size,
        }

    async def close(self) -> None:
        """Release resources.  Safe to call multiple times."""
        self._initialized = False


# ---------------------------------------------------------------------------
# Global singleton & async convenience functions
# ---------------------------------------------------------------------------
_session_cache: Optional[SessionCache] = None
_cache_lock = asyncio.Lock()


async def get_session_cache() -> SessionCache:
    """Get or create global async session cache instance."""
    global _session_cache
    if _session_cache is None:
        async with _cache_lock:
            if _session_cache is None:
                _session_cache = SessionCache(
                    db_path=settings.RET_SESSION_DB,
                    max_size=settings.SESSION_CACHE_MAX_SIZE,
                )
                await _session_cache.initialize()
    return _session_cache


async def set_cache(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    cache = await get_session_cache()
    await cache.set(key, value, ttl_seconds)


async def get_cache(key: str) -> Optional[Any]:
    cache = await get_session_cache()
    return await cache.get(key)


async def delete_cache(key: str) -> bool:
    cache = await get_session_cache()
    return await cache.delete(key)


async def clear_cache_pattern(pattern: str) -> int:
    cache = await get_session_cache()
    return await cache.clear_pattern(pattern)