"""
Session Cache Module
Implements LRU caching for session data, file metadata, and AI indices.
Uses in-memory LRU + SQLite persistence with WAL mode for concurrent access.
"""

import sqlite3
import threading
import time
import logging
from pathlib import Path
from typing import Any, Optional, Dict, Tuple

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


class SessionCache:
    """
    LRU-based session cache with SQLite backend for persistence.
    Uses WAL journal mode for better concurrent read/write performance.
    """

    def __init__(self, db_path: Optional[str] = None, max_size: int = 1000):
        self.db_path = Path(db_path or settings.RET_SESSION_DB)
        self.max_size = max_size
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.access_times: Dict[str, float] = {}
        self.lock = threading.RLock()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection with WAL mode and busy timeout."""
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        """Initialize SQLite database for cache persistence."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS session_cache (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize cache DB: {e}")

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set a cache entry with optional TTL."""
        with self.lock:
            now = time.time()
            expires_at = now + ttl_seconds if ttl_seconds else None

            self.cache[key] = (value, now)
            self.access_times[key] = now

            self._persist_to_db(key, value, expires_at)

            if len(self.cache) > self.max_size:
                self._evict_lru()

    def get(self, key: str) -> Optional[Any]:
        """Get a cache entry, returns None if not found or expired."""
        with self.lock:
            if key in self.cache:
                value, _ = self.cache[key]
                self.access_times[key] = time.time()
                return value

            value = self._load_from_db(key)
            if value is not None:
                now = time.time()
                self.cache[key] = (value, now)
                self.access_times[key] = now
                return value

            return None

    def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        with self.lock:
            existed = key in self.cache
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
            self._delete_from_db(key)
            return existed

    def clear_pattern(self, pattern: str) -> int:
        """Delete all cache entries matching a key prefix."""
        with self.lock:
            keys_to_delete = [k for k in self.cache if k.startswith(pattern)]
            count = len(keys_to_delete)
            for key in keys_to_delete:
                self.cache.pop(key, None)
                self.access_times.pop(key, None)

            # Batch delete from DB
            try:
                with self._get_conn() as conn:
                    conn.execute(
                        "DELETE FROM session_cache WHERE key LIKE ?",
                        (pattern + "%",),
                    )
                    conn.commit()
            except Exception as e:
                logger.debug(f"Failed to delete pattern from DB: {e}")

            return count

    def clear(self) -> None:
        """Clear entire cache (memory and disk)."""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
            try:
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM session_cache")
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to clear DB cache: {e}")

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _persist_to_db(
        self, key: str, value: Any, expires_at: Optional[float] = None
    ) -> None:
        """Persist cache entry to SQLite with retry logic."""
        value_json = _dumps(value) if not isinstance(value, str) else value
        now = time.time()

        for attempt in range(_MAX_WRITE_RETRIES):
            try:
                with self._get_conn() as conn:
                    conn.execute(
                        """INSERT OR REPLACE INTO session_cache
                           (key, value, created_at, expires_at)
                           VALUES (?, ?, ?, ?)""",
                        (key, value_json, now, expires_at),
                    )
                    conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < _MAX_WRITE_RETRIES - 1:
                    time.sleep(_RETRY_DELAY_S * (attempt + 1))
                else:
                    logger.debug(f"Failed to persist cache entry: {e}")
                    return
            except Exception as e:
                logger.debug(f"Failed to persist cache entry: {e}")
                return

    def _load_from_db(self, key: str) -> Optional[Any]:
        """Load cache entry from SQLite."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT value, expires_at FROM session_cache WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row:
                    value_json, expires_at = row
                    if expires_at and expires_at < time.time():
                        conn.execute(
                            "DELETE FROM session_cache WHERE key = ?", (key,)
                        )
                        conn.commit()
                        return None
                    try:
                        return _loads(value_json)
                    except (ValueError, TypeError):
                        return value_json
        except Exception as e:
            logger.debug(f"Failed to load from DB: {e}")
        return None

    def _delete_from_db(self, key: str) -> None:
        """Delete cache entry from SQLite."""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM session_cache WHERE key = ?", (key,))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to delete from DB: {e}")

    def _evict_lru(self) -> None:
        """Evict the least recently used item."""
        if not self.access_times:
            return
        lru_key = min(self.access_times, key=self.access_times.get)  # type: ignore[arg-type]
        self.cache.pop(lru_key, None)
        self.access_times.pop(lru_key, None)
        self._delete_from_db(lru_key)


# ---------------------------------------------------------------------------
# Global singleton & convenience functions
# ---------------------------------------------------------------------------
_session_cache: Optional[SessionCache] = None
_cache_lock = threading.Lock()


def get_session_cache() -> SessionCache:
    """Get or create global session cache instance."""
    global _session_cache
    if _session_cache is None:
        with _cache_lock:
            if _session_cache is None:
                _session_cache = SessionCache(
                    db_path=settings.RET_SESSION_DB,
                    max_size=settings.SESSION_CACHE_MAX_SIZE,
                )
    return _session_cache


def set_cache(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    get_session_cache().set(key, value, ttl_seconds)


def get_cache(key: str) -> Optional[Any]:
    return get_session_cache().get(key)


def delete_cache(key: str) -> bool:
    return get_session_cache().delete(key)


def clear_cache_pattern(pattern: str) -> int:
    return get_session_cache().clear_pattern(pattern)
