
"""
Async Job Lifecycle Helpers

Provides async functions for updating Job rows in the database.
Used by background workers (conversion, comparison, embedding) to
track job progress, success, and failure.

All functions are native async — no sync→async bridge needed since
workers now run as asyncio tasks.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """UTC now as a timezone-naive datetime (matches TIMESTAMP WITHOUT TIME ZONE columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clamp_progress(pct: int) -> int:
    try:
        return max(0, min(100, int(pct)))
    except Exception:
        return 0


# -------------------------------------------------------------------
# Session acquisition
# -------------------------------------------------------------------
async def _get_async_session() -> AsyncSession:
    """
    Acquire an AsyncSession compatible with different database module styles.

    Priority:
    1) Use api.core.database.SessionLocal if it exists and is an async session factory
    2) Fallback to api.core.database.get_db() async generator dependency
    """
    try:
        from api.core import database as dbmod
        SessionLocal = getattr(dbmod, "SessionLocal", None)
        if SessionLocal is not None:
            session = SessionLocal()
            if hasattr(session, "__aenter__") and hasattr(session, "__aexit__"):
                return session
            if isinstance(session, AsyncSession):
                return session
    except Exception:
        pass

    from api.core.database import get_db

    async for session in get_db():
        return session

    raise RuntimeError("Unable to acquire AsyncSession")


# -------------------------------------------------------------------
# Core update logic
# -------------------------------------------------------------------
async def _update_job_async(
    job_id: int,
    *,
    status: Optional[JobStatus] = None,
    progress: Optional[int] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    """
    Update a Job row safely using an AsyncSession.
    """
    session_or_cm = await _get_async_session()

    if hasattr(session_or_cm, "__aenter__") and hasattr(session_or_cm, "__aexit__"):
        async with session_or_cm as db:
            await _update_job_with_session(
                db, job_id,
                status=status, progress=progress, result=result,
                error=error, started=started, completed=completed,
            )
        return

    db = session_or_cm
    try:
        await _update_job_with_session(
            db, job_id,
            status=status, progress=progress, result=result,
            error=error, started=started, completed=completed,
        )
    finally:
        try:
            await db.close()
        except Exception:
            pass


async def _update_job_with_session(
    db: AsyncSession,
    job_id: int,
    *,
    status: Optional[JobStatus],
    progress: Optional[int],
    result: Optional[Dict[str, Any]],
    error: Optional[str],
    started: bool,
    completed: bool,
) -> None:
    """Core update logic using an existing AsyncSession."""
    try:
        res = await db.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()

        if not job:
            logger.warning("Job not found for update (job_id=%s)", job_id)
            return

        if started and job.started_at is None:
            job.started_at = _utcnow()

        if status is not None:
            job.status = status

        if progress is not None:
            job.progress = _clamp_progress(progress)

        if result is not None:
            job.result = result

        if error is not None:
            job.error = str(error)[:2048]

        if completed:
            job.completed_at = _utcnow()

        await db.commit()

    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception("Failed to update job (job_id=%s)", job_id)


# -------------------------------------------------------------------
# Public async API (used by async workers)
# -------------------------------------------------------------------
async def mark_running(job_id: int, progress: int = 5) -> None:
    """Mark a job as RUNNING with initial progress."""
    await _update_job_async(job_id, status=JobStatus.RUNNING, progress=progress, started=True)


async def update_progress(job_id: int, progress: int, note: str = "") -> None:
    """Update job progress percentage."""
    await _update_job_async(job_id, status=JobStatus.RUNNING, progress=progress, started=True)


async def mark_success(job_id: int, result: Dict[str, Any]) -> None:
    """Mark a job as SUCCESS with result data."""
    await _update_job_async(
        job_id, status=JobStatus.SUCCESS, progress=100,
        result=result, error=None, completed=True,
    )


async def mark_failed(job_id: int, error: str) -> None:
    """Mark a job as FAILED with error message."""
    await _update_job_async(
        job_id, status=JobStatus.FAILED, progress=100,
        result=None, error=error, completed=True,
    )


async def mark_cancelled(job_id: int) -> None:
    """Mark a job as CANCELLED."""
    await _update_job_async(job_id, status=JobStatus.CANCELLED, completed=True)


# -------------------------------------------------------------------
# Backward compatibility — no-op for set_main_loop
# -------------------------------------------------------------------
def set_main_loop(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """No-op retained for backward compatibility with main.py lifespan.

    Previously used to register the event loop for sync→async bridge.
    Now that all workers are async, this is unnecessary.
    """
    pass

