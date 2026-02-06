from typing import Generator, cast
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase
from api.core.config import settings

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
_database_url: str = cast(str, settings.DATABASE_URL) if settings.DATABASE_URL else "sqlite:///./test.db"
_is_sqlite = _database_url.startswith("sqlite")

# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------
_engine_kwargs: dict = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if _is_sqlite:
    # SQLite requires check_same_thread=False for FastAPI's async workers
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    _engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
    _engine_kwargs["pool_timeout"] = settings.DATABASE_POOL_TIMEOUT

engine = create_engine(_database_url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# SQLite pragmas for performance and reliability
# ---------------------------------------------------------------------------
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables that don't yet exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and handles rollback."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
