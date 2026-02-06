"""
Job Service - Background job tracking and management.

Provides functions to create, update, and query background jobs.
"""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from api.models.job import Job, JobStatus, JobType


def create_job(
    db: Session, 
    job_type: JobType, 
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
        job_type=job_type,
        status=JobStatus.PENDING,
        user_id=user_id,
        session_id=session_id,
    )
    db.add(job)
    
    if commit:
        db.commit()
        db.refresh(job)
    else:
        db.flush()
    
    return job


def get_job(db: Session, job_id: int) -> Optional[Job]:
    """
    Get a job by ID.
    
    Uses db.get() instead of deprecated query().get().
    
    Args:
        db: Database session
        job_id: Job ID to retrieve
        
    Returns:
        Job object or None if not found
    """
    return db.get(Job, job_id)


def update_job_status(
    db: Session,
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
    job = db.get(Job, job_id)
    if not job:
        return None
    
    job.status = status
    job.updated_at = datetime.now(timezone.utc)
    
    if progress is not None:
        job.progress = max(0, min(100, progress))
    
    if result is not None:
        job.result = result
    
    if error is not None:
        job.error = error[:2048] if len(error) > 2048 else error  # Truncate if too long
    
    # Set timestamps based on status
    if status == JobStatus.RUNNING and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    elif status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
        job.completed_at = datetime.now(timezone.utc)
        if status == JobStatus.SUCCESS:
            job.progress = 100
    
    if commit:
        db.commit()
        db.refresh(job)
    
    return job


def mark_job_running(db: Session, job_id: int, commit: bool = True) -> Optional[Job]:
    """Mark a job as running."""
    return update_job_status(db, job_id, JobStatus.RUNNING, progress=0, commit=commit)


def mark_job_success(
    db: Session, 
    job_id: int, 
    result: Optional[dict] = None,
    commit: bool = True,
) -> Optional[Job]:
    """Mark a job as successful with optional result."""
    return update_job_status(
        db, job_id, JobStatus.SUCCESS, progress=100, result=result, commit=commit
    )


def mark_job_failed(
    db: Session, 
    job_id: int, 
    error: str,
    commit: bool = True,
) -> Optional[Job]:
    """Mark a job as failed with error message."""
    return update_job_status(db, job_id, JobStatus.FAILED, error=error, commit=commit)


def update_job_progress(
    db: Session, 
    job_id: int, 
    progress: int,
    commit: bool = True,
) -> Optional[Job]:
    """Update job progress (0-100)."""
    job = db.get(Job, job_id)
    if not job:
        return None
    
    job.progress = max(0, min(100, progress))
    job.updated_at = datetime.now(timezone.utc)
    
    if commit:
        db.commit()
        db.refresh(job)
    
    return job


def get_user_jobs(
    db: Session,
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
    query = db.query(Job).filter(Job.user_id == user_id)
    
    if status_filter:
        query = query.filter(Job.status == status_filter)
    
    return query.order_by(desc(Job.created_at)).limit(limit).all()


def get_session_jobs(
    db: Session,
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
    return (
        db.query(Job)
        .filter(Job.session_id == session_id)
        .order_by(desc(Job.created_at))
        .limit(limit)
        .all()
    )


def cleanup_old_jobs(db: Session, days: int = 30, commit: bool = True) -> int:
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
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    count = db.query(Job).filter(Job.created_at < cutoff).delete()
    
    if commit:
        db.commit()
    
    return count
