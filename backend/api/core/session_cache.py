"""
Session Cache Module
Implements LRU caching for session data, file metadata, and AI indices
Replaces Redis with in-memory LRU + SQLite persistence
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional, Dict, Tuple
from datetime import datetime, timedelta
import logging

from api.core.config import settings

logger = logging.getLogger(__name__)


class SessionCache:
    """
    LRU-based session cache with SQLite backend for persistence
    Inspired by Streamlit's session state management pattern
    """
    
    def __init__(self, db_path: Optional[str] = None, max_size: int = 1000):
        """
        Initialize session cache
        
        Args:
            db_path: Path to SQLite database for persistence
            max_size: Maximum number of entries in memory cache
        """
        self.db_path = Path(db_path or settings.RET_SESSION_DB)
        self.max_size = max_size
        self.cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, timestamp)
        self.access_times: Dict[str, float] = {}  # key -> last access time
        self.lock = threading.RLock()
        
        # Initialize database
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for cache persistence"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
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
    
    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Set a cache entry with optional TTL
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: Time to live in seconds
        """
        with self.lock:
            now = datetime.now().timestamp()
            expires_at = now + ttl_seconds if ttl_seconds else None
            
            # Store in memory
            self.cache[key] = (value, now)
            self.access_times[key] = now
            
            # Persist to SQLite
            self._persist_to_db(key, value, expires_at)
            
            # Evict LRU if cache too large
            if len(self.cache) > self.max_size:
                self._evict_lru()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a cache entry, returns None if not found or expired
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        with self.lock:
            # Check memory cache
            if key in self.cache:
                value, timestamp = self.cache[key]
                self.access_times[key] = datetime.now().timestamp()
                return value
            
            # Try to load from DB
            value = self._load_from_db(key)
            if value is not None:
                self.cache[key] = (value, datetime.now().timestamp())
                self.access_times[key] = datetime.now().timestamp()
                return value
            
            return None
    
    def delete(self, key: str) -> bool:
        """
        Delete a cache entry
        
        Args:
            key: Cache key
            
        Returns:
            True if key existed
        """
        with self.lock:
            existed = key in self.cache
            
            # Remove from memory
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
            
            # Remove from DB
            self._delete_from_db(key)
            
            return existed
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Delete all cache entries matching a pattern (prefix)
        Used for clearing session data
        
        Args:
            pattern: Key prefix to match
            
        Returns:
            Number of entries deleted
        """
        with self.lock:
            keys_to_delete = [k for k in self.cache.keys() if k.startswith(pattern)]
            count = len(keys_to_delete)
            
            for key in keys_to_delete:
                self.cache.pop(key, None)
                self.access_times.pop(key, None)
                self._delete_from_db(key)
            
            return count
    
    def clear(self) -> None:
        """Clear entire cache (memory and disk)"""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
            
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.execute("DELETE FROM session_cache")
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to clear DB cache: {e}")
    
    def _persist_to_db(
        self,
        key: str,
        value: Any,
        expires_at: Optional[float] = None
    ) -> None:
        """Persist cache entry to SQLite"""
        try:
            value_json = json.dumps(value) if not isinstance(value, str) else value
            now = datetime.now().timestamp()
            
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO session_cache
                    (key, value, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                """, (key, value_json, now, expires_at))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to persist cache entry: {e}")
    
    def _load_from_db(self, key: str) -> Optional[Any]:
        """Load cache entry from SQLite"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute("""
                    SELECT value, expires_at FROM session_cache
                    WHERE key = ?
                """, (key,))
                row = cursor.fetchone()
                
                if row:
                    value_json, expires_at = row
                    
                    # Check expiration
                    if expires_at and expires_at < datetime.now().timestamp():
                        conn.execute("DELETE FROM session_cache WHERE key = ?", (key,))
                        conn.commit()
                        return None
                    
                    try:
                        return json.loads(value_json)
                    except json.JSONDecodeError:
                        return value_json
        except Exception as e:
            logger.debug(f"Failed to load from DB: {e}")
        
        return None
    
    def _delete_from_db(self, key: str) -> None:
        """Delete cache entry from SQLite"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("DELETE FROM session_cache WHERE key = ?", (key,))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to delete from DB: {e}")
    
    def _evict_lru(self) -> None:
        """Evict least recently used item"""
        if not self.access_times:
            return
        
        # Find least recently accessed key
        lru_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        self.cache.pop(lru_key, None)
        self.access_times.pop(lru_key, None)
        self._delete_from_db(lru_key)


# Global session cache instance
_session_cache: Optional[SessionCache] = None
_cache_lock = threading.Lock()


def get_session_cache() -> SessionCache:
    """Get or create global session cache instance"""
    global _session_cache
    
    if _session_cache is None:
        with _cache_lock:
            if _session_cache is None:
                _session_cache = SessionCache(
                    db_path=settings.RET_SESSION_DB,
                    max_size=settings.SESSION_CACHE_MAX_SIZE
                )
    
    return _session_cache


def set_cache(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    """Set a cache value"""
    cache = get_session_cache()
    cache.set(key, value, ttl_seconds)


def get_cache(key: str) -> Optional[Any]:
    """Get a cache value"""
    cache = get_session_cache()
    return cache.get(key)


def delete_cache(key: str) -> bool:
    """Delete a cache entry"""
    cache = get_session_cache()
    return cache.delete(key)


def clear_cache_pattern(pattern: str) -> int:
    """Clear all cache entries matching a pattern"""
    cache = get_session_cache()
    return cache.clear_pattern(pattern)
