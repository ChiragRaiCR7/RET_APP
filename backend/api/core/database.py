
"""
Database setup using SQLAlchemy (AsyncEngine/AsyncSession).

- SQLite is the only supported database: settings.DATABASE_URL must be
  sqlite+aiosqlite:///path/to/file.db. Every connection runs with WAL,
  foreign keys on, and a busy timeout.
- Provides Declarative Base, async engine/session factory, init_db, and get_db() dependency.

Note:
Use Alembic for schema migrations in staging/production environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.core.config import settings

logger = logging.getLogger(__name__)

# Lazy globals (avoid import-time crashes)
_engine: Optional[AsyncEngine] = None
SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    """Declarative Base for ORM models."""
    pass


# ---------------------------------------------------------------------------
# URL rules and engine creation (SQLite is the only supported database)
# ---------------------------------------------------------------------------

SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite://"


def _validate_database_url(url: str) -> None:
    """Rejects anything but an async SQLite URL with a message that says how to fix it."""
    if not url.startswith(SQLITE_ASYNC_PREFIX):
        scheme = url.split("://", 1)[0] + "://" if "://" in url else url
        raise ValueError(
            "Unsupported DATABASE_URL: SQLite is the only supported database. Use "
            f"'{SQLITE_ASYNC_PREFIX}/./runtime/ret.db' (got {scheme}). To move existing "
            "PostgreSQL data, run scripts/pg_to_sqlite.py."
        )


def _set_sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    # WAL lets readers proceed during a write; busy_timeout absorbs short write-lock waits
    # instead of failing with "database is locked"; SQLite leaves FKs off unless asked.
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def _build_engine(url: str) -> AsyncEngine:
    """Builds the AsyncEngine and applies SQLite pragmas on every new connection."""
    if url.startswith(SQLITE_ASYNC_PREFIX + "/"):
        db_path = url[len(SQLITE_ASYNC_PREFIX + "/"):]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url, future=True, echo=False)
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    return engine


async def init_db() -> None:
    """
    Initialize DB engine and session factory lazily.

    Dev/testing convenience:
    - Creates tables (create_all) only in development/testing.
    - In staging/production use Alembic migrations.
    - Retries the initial connection up to DB_CONNECT_RETRIES times with
      exponential back-off to tolerate transient startup races.
    """
    global _engine, SessionLocal

    if _engine is not None and SessionLocal is not None:
        return

    url = getattr(settings, "DATABASE_URL", None)
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Use 'sqlite+aiosqlite:///./runtime/ret.db'."
        )

    _validate_database_url(url)

    max_retries = getattr(settings, "DB_CONNECT_RETRIES", 5)
    for attempt in range(max_retries):
        try:
            _engine = _build_engine(url)
            engine = _engine
            # Probe the connection before handing the engine to the app.
            async with engine.connect() as probe:
                await probe.execute(text("SELECT 1"))
            break
        except Exception as exc:
            engine_to_dispose = _engine
            if engine_to_dispose is not None:
                await engine_to_dispose.dispose()
            _engine = None
            if attempt < max_retries - 1:
                delay = 2 ** attempt  # 1 s, 2 s, 4 s, 8 s …
                logger.warning(
                    "Database connection failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, max_retries, delay, exc,
                )
                import asyncio as _asyncio
                await _asyncio.sleep(delay)
            else:
                raise RuntimeError(
                    f"Failed to connect to database after {max_retries} attempts: {exc}"
                ) from exc

    engine = _engine
    if engine is None:
        raise RuntimeError("Database engine is not initialized")

    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Create tables only in development/testing to avoid production accidents
    if getattr(settings, "is_development", False) or getattr(settings, "ENVIRONMENT", "") == "testing":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Safety net: ensure login_sessions has token-rotation columns.
    # Only run in dev/test — staging/production rely on Alembic migrations.
    await _ensure_login_sessions_schema()


async def _ensure_login_sessions_schema() -> None:
    """
    Ensure token-rotation columns/indexes exist on login_sessions.

    This is intentionally additive-only and safe to run repeatedly.  It runs
    **only** in development/testing environments — staging/production rely on
    Alembic migrations exclusively.
    """
    if _engine is None:
        return
    engine = _engine

    env = (
        getattr(settings, "ENVIRONMENT", None)
        or getattr(getattr(settings, "ENV", None), "value", "development")
    )
    if env not in {"development", "testing"}:
        return

    async with engine.begin() as conn:
        metadata = await conn.run_sync(_inspect_login_sessions_metadata)
        if metadata is None:
            return

        columns: set[str] = metadata["columns"]
        indexes: set[str] = metadata["indexes"]

        if "token_family" not in columns:
            await conn.execute(text("ALTER TABLE login_sessions ADD COLUMN token_family VARCHAR(64)"))
            logger.warning("Patched schema drift: added login_sessions.token_family")

        if "replaced_by_id" not in columns:
            await conn.execute(text("ALTER TABLE login_sessions ADD COLUMN replaced_by_id INTEGER"))
            logger.warning("Patched schema drift: added login_sessions.replaced_by_id")

        if "revoked" not in columns:
            await conn.execute(
                text("ALTER TABLE login_sessions ADD COLUMN revoked BOOLEAN NOT NULL DEFAULT FALSE")
            )
            logger.warning("Patched schema drift: added login_sessions.revoked")

        if "refresh_jti" not in columns:
            await conn.execute(text("ALTER TABLE login_sessions ADD COLUMN refresh_jti VARCHAR(64)"))
            logger.warning("Patched schema drift: added login_sessions.refresh_jti")

        if "ix_login_session_family" not in indexes:
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_login_session_family ON login_sessions (token_family)")
            )

        if "ix_login_session_refresh_jti" not in indexes:
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_login_session_refresh_jti ON login_sessions (refresh_jti)")
            )


def _inspect_login_sessions_metadata(sync_conn: Any) -> Optional[Dict[str, set[str]]]:
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "login_sessions" not in tables:
        return None

    columns = {c["name"] for c in inspector.get_columns("login_sessions")}
    indexes = {i["name"] for i in inspector.get_indexes("login_sessions")}
    return {"columns": columns, "indexes": indexes}


async def close_db() -> None:
    """
    Dispose engine (shutdown cleanup). Safe no-op if not initialized.
    Handles already-disposed engines gracefully.
    """
    global _engine, SessionLocal

    if _engine is not None:
        engine = _engine
        logger.warning(
            "Disposing database engine — any in-flight connections may be interrupted"
        )
        try:
            await engine.dispose()
        except Exception:
            logger.debug("Engine dispose raised (may already be disposed)", exc_info=True)

    _engine = None
    SessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an AsyncSession and handles rollback.

    Usage:
        async def route(db: AsyncSession = Depends(get_db)): ...
    """
    if SessionLocal is None:
        await init_db()

    assert SessionLocal is not None
    async with SessionLocal() as db:
        try:
            yield db
        except Exception:
            await db.rollback()
            raise


async def check_db_health() -> bool:
    """
    Async health check: SELECT 1.

    Returns:
        True if DB reachable, else False.
    """
    try:
        if _engine is None:
            await init_db()
        assert _engine is not None

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False