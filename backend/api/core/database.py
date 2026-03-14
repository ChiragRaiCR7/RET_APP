
"""
Database setup using SQLAlchemy (AsyncEngine/AsyncSession).

- Expects an async-compatible DSN in settings.DATABASE_URL, e.g.:
    PostgreSQL (recommended):
        postgresql+asyncpg://user:password@host:5432/dbname?sslmode=require
    SQLite (testing/dev only):
        sqlite+aiosqlite:///./runtime/test.db

- Applies pool settings from configuration (Postgres only; SQLite ignores pool sizing).
- Provides Declarative Base, async engine/session factory, init_db, and get_db() dependency.

Note:
Use Alembic for schema migrations in staging/production environments.
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import inspect, text
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
engine: Optional[AsyncEngine] = None  # compatibility alias for older scripts
SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    """Declarative Base for ORM models."""
    pass


# ---------------------------------------------------------------------------
# URL / dialect rules
# ---------------------------------------------------------------------------

def _is_sqlite_async(url: str) -> bool:
    return url.startswith("sqlite+aiosqlite://")


def _is_postgres_async(url: str) -> bool:
    return url.startswith("postgresql+asyncpg://") or url.startswith("postgresql+psycopg://")


def _validate_database_url(url: str) -> None:
    """
    Validate DATABASE_URL.

    - Production/staging: require postgres async dialect (asyncpg/psycopg)
    - Testing/dev: allow sqlite+aiosqlite as well
    """
    env = getattr(settings, "ENV", None)
    env_value = getattr(env, "value", str(env)) if env is not None else "development"

    if _is_sqlite_async(url):
        # SQLite allowed only in dev/testing
        if env_value not in {"development", "testing"}:
            raise ValueError("SQLite is not supported in staging/production. Use PostgreSQL.")
        return

    if _is_postgres_async(url):
        return

    # If user gave sync postgres URL by mistake, guide them
    scheme = url.split("://", 1)[0] + "://" if "://" in url else url
    raise ValueError(
        "Unsupported DATABASE_URL for async SQLAlchemy. Expected one of:\n"
        "  - postgresql+asyncpg://...\n"
        "  - postgresql+psycopg://...\n"
        "  - sqlite+aiosqlite:///... (dev/testing only)\n"
        f"Got: {scheme}"
    )


def _ensure_async_driver_installed(url: str) -> None:
    """Ensure required async DB driver is installed for the configured URL."""
    if url.startswith("postgresql+asyncpg://"):
        if importlib.util.find_spec("asyncpg") is None:
            raise RuntimeError(
                "DATABASE_URL uses postgresql+asyncpg but 'asyncpg' is not installed. "
                "Install it with: pip install asyncpg"
            )
        return

    if url.startswith("postgresql+psycopg://"):
        if importlib.util.find_spec("psycopg") is None:
            raise RuntimeError(
                "DATABASE_URL uses postgresql+psycopg but 'psycopg' is not installed. "
                "Install it with: pip install psycopg[binary]"
            )
        return

    if url.startswith("sqlite+aiosqlite://"):
        if importlib.util.find_spec("aiosqlite") is None:
            raise RuntimeError(
                "DATABASE_URL uses sqlite+aiosqlite but 'aiosqlite' is not installed. "
                "Install it with: pip install aiosqlite"
            )
        return


# ---------------------------------------------------------------------------
# Engine/session creation (lazy)
# ---------------------------------------------------------------------------

def _build_engine(url: str) -> AsyncEngine:
    """
    Build AsyncEngine with pool settings (Postgres only).
    """
    engine_kwargs = {
        "pool_pre_ping": True,   # drop stale connections automatically
        "pool_recycle": 1800,    # recycle connections every 30 min (was 60 min)
        "future": True,
        "echo": bool(getattr(settings, "DEBUG", False)),
    }

    if not _is_sqlite_async(url):
        # Pool sizing only makes sense for server DBs (Postgres)
        engine_kwargs.update(
            {
                "pool_size": settings.DATABASE_POOL_SIZE,
                "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
            }
        )

    return create_async_engine(url, **engine_kwargs)


async def init_db() -> None:
    """
    Initialize DB engine and session factory lazily.

    Dev/testing convenience:
    - Creates tables (create_all) only in development/testing.
    - In staging/production use Alembic migrations.
    """
    global _engine, engine, SessionLocal

    if _engine is not None and SessionLocal is not None:
        return

    url = getattr(settings, "DATABASE_URL", None)
    if not url:
        # ✅ Do NOT crash at import time; raise only when init is called.
        raise RuntimeError(
            "DATABASE_URL is not set. Provide an async DSN like "
            "'postgresql+asyncpg://user:password@host:5432/dbname'."
        )

    _validate_database_url(url)
    _ensure_async_driver_installed(url)

    _engine = _build_engine(url)
    engine = _engine
    SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False)

    # Create tables only in development/testing to avoid production accidents
    if getattr(settings, "is_development", False) or getattr(settings, "ENVIRONMENT", "") == "testing":
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Safety net for dev/test/stale local DBs:
    # ensure login_sessions has token-rotation columns expected by current models.
    # This prevents runtime login failures when an existing database missed a migration.
    await _ensure_login_sessions_schema()


async def _ensure_login_sessions_schema() -> None:
    """
    Ensure token-rotation columns/indexes exist on login_sessions.

    This is intentionally additive-only and safe to run repeatedly. Alembic
    remains the source of truth for managed migrations in staging/production.
    """
    if _engine is None:
        return

    async with _engine.begin() as conn:
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


def _inspect_login_sessions_metadata(sync_conn: Any) -> Optional[dict[str, set[str]]]:
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
    global _engine, engine, SessionLocal

    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception:
            logger.debug("Engine dispose raised (may already be disposed)", exc_info=True)

    _engine = None
    engine = None
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