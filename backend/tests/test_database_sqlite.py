"""SQLite-only database layer: migrations reach the model schema, engine pragmas, URL rules."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from api.core import database

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}", "JWT_SECRET_KEY": "x" * 40}
    return subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )


def test_fresh_database_migrates_to_model_schema(tmp_path: Path) -> None:
    """Regression: 0003 re-added users.is_active and broke `alembic upgrade head` on a new DB."""
    db = tmp_path / "fresh.db"
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    check = _alembic(db, "check")
    assert check.returncode == 0, check.stdout + check.stderr


def test_legacy_rows_survive_reconciliation(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    assert _alembic(db, "upgrade", "0005").returncode == 0
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO users(id, username, password_hash, role, is_active, is_locked) "
                     "VALUES (1, 'admin', 'h', 'admin', 1, 0), (2, 'demo', 'h', NULL, NULL, NULL)")
        conn.execute("INSERT INTO login_sessions(id, user_id, refresh_token_hash, revoked) "
                     "VALUES (1, 1, 'x', 0)")
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT username, role, is_active, is_deleted, failed_login_attempts "
                            "FROM users ORDER BY id").fetchall()
        assert rows == [("admin", "admin", 1, 0, 0), ("demo", "user", 1, 0, 0)]
        assert conn.execute("SELECT expires_at IS NOT NULL FROM login_sessions").fetchone() == (1,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert _alembic(db, "check").returncode == 0


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://u:p@localhost/db",
    "sqlite:///./sync-driver.db",
])
def test_only_async_sqlite_urls_are_accepted(url: str) -> None:
    with pytest.raises(ValueError, match="SQLite is the only supported database"):
        database._validate_database_url(url)


async def test_engine_applies_pragmas(tmp_path: Path) -> None:
    engine = database._build_engine(f"sqlite+aiosqlite:///{tmp_path}/nested/dir/app.db")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
            assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
            assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 5000
    finally:
        await engine.dispose()


def test_copy_script_moves_rows_and_verifies_counts(tmp_path: Path) -> None:
    """scripts/pg_to_sqlite.py, exercised with a SQLite source standing in for PostgreSQL."""
    from sqlalchemy import create_engine

    import api.models  # noqa: F401
    from api.core.database import Base
    from scripts.pg_to_sqlite import copy

    source = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{source}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users(id, username, password_hash, role, is_active, is_locked, is_deleted,"
            " failed_login_attempts, created_at, updated_at) VALUES"
            " (1, 'admin', 'h', 'admin', 1, 0, 0, 0, '2026-01-01', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO audit_logs(id, username, action, created_at) VALUES"
            " (1, 'admin', 'login', '2026-01-01'), (2, 'admin', 'logout', '2026-01-02')"))
    engine.dispose()
    target = tmp_path / "target.db"
    assert _alembic(target, "upgrade", "head").returncode == 0

    copied = copy(f"sqlite:///{source}", str(target), replace=False)
    assert copied["users"] == 1 and copied["audit_logs"] == 2
    with pytest.raises(SystemExit, match="already has .* rows; use --replace"):
        copy(f"sqlite:///{source}", str(target), replace=False)
    assert copy(f"sqlite:///{source}", str(target), replace=True)["audit_logs"] == 2
