"""SQLite engine and request-scoped sessions."""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _on_connect(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    # WAL lets readers proceed while a job writes; busy_timeout absorbs short writer contention.
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.close()


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
        event.listen(_engine, "connect", _on_connect)
        _session_factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (tests switch data_dir between runs)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine, _session_factory = None, None


def new_session() -> Session:
    get_engine()
    assert _session_factory is not None
    return _session_factory()


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    finally:
        db.close()
