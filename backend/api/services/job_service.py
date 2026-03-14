
"""
Job Service - Background job tracking and management.

Provides functions to create, update, and query background jobs.
"""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import desc, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.job import Job, JobStatus, JobType


def _utcnow() -> datetime:
    """Return naive UTC timestamp for DB timestamp columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_job_type(job_type: JobType | str) -> JobType:
    if isinstance(job_type, JobType):
        return job_type
    return JobType(str(job_type))


async def create_job(
    db: AsyncSession,
    job_type: JobType | str,
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
    commit: bool = True,
) -> Job:
    """
    Create a new background job.
    
    Args:
        db: Database session
        job_type: Type of job (conversion, comparison, etc.)
        user_id: Owner user ID (optional)
        session_id: Associated session ID (optional)
        commit: Whether to commit the transaction (default: True)
        
    Returns:
        Created Job object with ID assigned
    """
    job = Job(
        job_type=_normalize_job_type(job_type),
        status=JobStatus.PENDING,
        user_id=user_id,
        session_id=session_id,
    )
    db.add(job)
    
    if commit:
        await db.commit()
        await db.refresh(job)
    else:
        await db.flush()
    
    return job


async def get_job(db: AsyncSession, job_id: int) -> Optional[Job]:
    """
    Get a job by ID.
    
    Uses db.get() instead of deprecated query().get().
    
    Args:
        db: Database session
        job_id: Job ID to retrieve
        
    Returns:
        Job object or None if not found
    """
    return await db.get(Job, job_id)


async def find_active_job(
    db: AsyncSession,
    user_id: int,
    job_type: JobType | str,
    session_id: Optional[str] = None,
) -> Optional[Job]:
    """
    Find the most recent active job (PENDING/RUNNING) for a user and job type.

    Useful for idempotent async endpoints to avoid creating duplicate heavy jobs
    during retries or rapid repeated submits.
    """
    jt = _normalize_job_type(job_type)

    stmt = select(Job).where(
        Job.user_id == user_id,
        Job.job_type == jt,
        Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
    )

    if session_id:
        stmt = stmt.where(Job.session_id == session_id)

    stmt = stmt.order_by(desc(Job.created_at)).limit(1)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def update_job_status(
    db: AsyncSession,
    job_id: int,
    status: JobStatus,
    progress: Optional[int] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    commit: bool = True,
) -> Optional[Job]:
    """
    Update a job's status and optionally other fields.
    
    Args:
        db: Database session
        job_id: Job ID to update
        status: New status
        progress: Progress percentage (0-100)
        result: Result data (for SUCCESS status)
        error: Error message (for FAILED status)
        commit: Whether to commit the transaction
        
    Returns:
        Updated Job object or None if not found
    """
    job = await db.get(Job, job_id)
    if not job:
        return None
    
    job.status = status
    job.updated_at = _utcnow()
    
    if progress is not None:
        job.progress = max(0, min(100, progress))
    
    if result is not None:
        job.result = result
    
    if error is not None:
        job.error = error[:2048] if len(error) > 2048 else error  # Truncate if too long
    
    # Set timestamps based on status
    if status == JobStatus.RUNNING and job.started_at is None:
        job.started_at = _utcnow()
    elif status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
        job.completed_at = _utcnow()
        if status == JobStatus.SUCCESS:
            job.progress = 100
    
    if commit:
        await db.commit()
        await db.refresh(job)
    
    return job


async def mark_job_running(db: AsyncSession, job_id: int, commit: bool = True) -> Optional[Job]:
    """Mark a job as running."""
    return await update_job_status(db, job_id, JobStatus.RUNNING, progress=0, commit=commit)


async def mark_job_success(
    db: AsyncSession,
    job_id: int,
    result: Optional[dict] = None,
    commit: bool = True,
) -> Optional[Job]:
    """Mark a job as successful with optional result."""
    return await update_job_status(
        db, job_id, JobStatus.SUCCESS, progress=100, result=result, commit=commit
    )


async def mark_job_failed(
    db: AsyncSession,
    job_id: int,
    error: str,
    commit: bool = True,
) -> Optional[Job]:
    """Mark a job as failed with error message."""
    return await update_job_status(db, job_id, JobStatus.FAILED, error=error, commit=commit)


async def update_job_progress(
    db: AsyncSession,
    job_id: int,
    progress: int,
    commit: bool = True,
) -> Optional[Job]:
    """Update job progress (0-100)."""
    job = await db.get(Job, job_id)
    if not job:
        return None
    
    job.progress = max(0, min(100, progress))
    job.updated_at = _utcnow()
    
    if commit:
        await db.commit()
        await db.refresh(job)
    
    return job


async def get_user_jobs(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    status_filter: Optional[JobStatus] = None,
) -> List[Job]:
    """
    Get jobs for a specific user.
    
    Args:
        db: Database session
        user_id: User ID to filter by
        limit: Maximum number of jobs to return
        status_filter: Optional status filter
        
    Returns:
        List of Job objects, ordered by creation date (newest first)
    """
    stmt = select(Job).where(Job.user_id == user_id)

    if status_filter:
        stmt = stmt.where(Job.status == status_filter)

    stmt = stmt.order_by(desc(Job.created_at)).limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_session_jobs(
    db: AsyncSession,
    session_id: str,
    limit: int = 50,
) -> List[Job]:
    """
    Get jobs for a specific session.
    
    Args:
        db: Database session
        session_id: Session ID to filter by
        limit: Maximum number of jobs to return
        
    Returns:
        List of Job objects, ordered by creation date (newest first)
    """
    stmt = (
        select(Job)
        .where(Job.session_id == session_id)
        .order_by(desc(Job.created_at))
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def cleanup_old_jobs(db: AsyncSession, days: int = 30, commit: bool = True) -> int:
    """
    Delete jobs older than specified days.
    
    Args:
        db: Database session
        days: Delete jobs older than this many days
        commit: Whether to commit the transaction
        
    Returns:
        Number of jobs deleted
    """
    from datetime import timedelta
    
    cutoff = _utcnow() - timedelta(days=days)
    
    res = await db.execute(delete(Job).where(Job.created_at < cutoff))
    count = int(getattr(res, "rowcount", 0) or 0)
    
    if commit:
        await db.commit()
    
    return count
