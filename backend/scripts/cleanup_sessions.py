
#!/usr/bin/env python3
"""
Cleanup expired login sessions.

Improvements over legacy version:
  1. Structured logging (logging module with timestamps)
  2. Batch deletion — avoids locking the table on large datasets
  3. Dry-run mode (--dry-run) — preview count without committing
  4. Archive to JSON (--archive) — preserves sessions before deletion
  5. Monitoring metrics — reports total deleted, elapsed time, rows/second
  6. Index existence check on expires_at — warns when missing

Usage:
  python scripts/cleanup_sessions.py
  python scripts/cleanup_sessions.py --dry-run
  python scripts/cleanup_sessions.py --archive
  python scripts/cleanup_sessions.py --batch-size 500
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Sequence, cast

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import api.core.database as database

try:
    from api.models import LoginSession
except Exception:
    from api.models.models import LoginSession  # fallback

if TYPE_CHECKING:
    from api.models.models import LoginSession as LoginSessionModel

# ------------------------------------------------
# Logging
# ------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("cleanup_sessions")

# ------------------------------------------------
# Constants
# ------------------------------------------------

BATCH_SIZE_DEFAULT = 1000
ARCHIVE_DIR = BASE_DIR / "runtime" / "archive"


# ------------------------------------------------
# CLI
# ------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cleanup expired login sessions.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count expired sessions and exit without deleting.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help=f"Rows deleted per batch (default: {BATCH_SIZE_DEFAULT}).",
    )
    p.add_argument(
        "--archive",
        action="store_true",
        help="Serialize expired sessions to a JSON file before deletion.",
    )
    return p.parse_args()


# ------------------------------------------------
# 6. Index check
# ------------------------------------------------

async def _check_index(db: AsyncSession) -> None:
    """Warn if ix_login_session_expires index is missing (Postgres only)."""
    try:
        result = await db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'login_sessions' "
                "AND indexname = 'ix_login_session_expires'"
            )
        )
        if result.fetchone():
            logger.info("Index ix_login_session_expires: present")
        else:
            logger.warning(
                "Index ix_login_session_expires is MISSING on login_sessions.expires_at. "
                "Cleanup queries may be slow. "
                "Fix: CREATE INDEX ix_login_session_expires ON login_sessions(expires_at);"
            )
    except Exception as exc:
        logger.debug(f"Index check skipped (non-postgres or unsupported dialect): {exc}")


# ------------------------------------------------
# 4. Archive
# ------------------------------------------------

async def _archive_sessions(expired: Sequence["LoginSessionModel"]) -> Path | None:
    """Write expired session records to a timestamped JSON file."""
    if not expired:
        return None

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / f"sessions_{ts}.json"

    records = []
    for s in expired:
        records.append({
            "id": s.id,
            "user_id": s.user_id,
            "ip_address": s.ip_address,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "revoked": s.revoked,
        })

    with archive_path.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)

    logger.info(f"Archived {len(records)} sessions → {archive_path}")
    return archive_path


# ------------------------------------------------
# Core cleanup logic
# ------------------------------------------------

async def cleanup_sessions_async(args: argparse.Namespace) -> int:
    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized (SessionLocal is None)")

    now = datetime.now(timezone.utc)
    start_time = time.monotonic()
    total_deleted = 0

    try:
        async with database.SessionLocal() as db:
            # 6. Index check
            await _check_index(db)

            # Count expired rows
            count_result = await db.execute(
                select(func.count())
                .select_from(LoginSession)
                .where(LoginSession.expires_at < now)
            )
            total_expired = count_result.scalar_one()

            logger.info(
                f"Expired sessions: {total_expired} "
                f"(cutoff: {now.strftime('%Y-%m-%d %H:%M:%S UTC')})"
            )

            if total_expired == 0:
                logger.info("Nothing to clean up.")
                return 0

            # 3. Dry-run mode
            if args.dry_run:
                logger.info(
                    f"[DRY-RUN] Would delete {total_expired} session(s) — no changes made."
                )
                return 0

            # 4. Archive before deletion
            if args.archive:
                rows_result = await db.execute(
                    select(LoginSession).where(LoginSession.expires_at < now)
                )
                expired_rows = cast(Sequence["LoginSessionModel"], rows_result.scalars().all())
                await _archive_sessions(expired_rows)

            # 2. Batch deletion
            batch_size = args.batch_size
            batches = (total_expired + batch_size - 1) // batch_size
            logger.info(f"Deleting in {batches} batch(es) of up to {batch_size} rows")

            for batch_num in range(batches):
                id_result = await db.execute(
                    select(LoginSession.id)
                    .where(LoginSession.expires_at < now)
                    .limit(batch_size)
                )
                ids = [row[0] for row in id_result.fetchall()]
                if not ids:
                    break

                del_result = await db.execute(
                    delete(LoginSession).where(LoginSession.id.in_(ids))
                )
                await db.commit()

                batch_deleted = del_result.rowcount
                if not isinstance(batch_deleted, int) or batch_deleted < 0:
                    batch_deleted = len(ids)
                total_deleted += batch_deleted
                logger.info(
                    f"  Batch {batch_num + 1}/{batches}: "
                    f"deleted {batch_deleted} rows (running total: {total_deleted})"
                )

    finally:
        await database.close_db()

    # 5. Monitoring metrics
    elapsed = time.monotonic() - start_time
    rate = total_deleted / elapsed if elapsed > 0 else 0
    logger.info(
        f"Cleanup complete — "
        f"deleted={total_deleted}, elapsed={elapsed:.2f}s, rate={rate:.1f} rows/s"
    )
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(cleanup_sessions_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
