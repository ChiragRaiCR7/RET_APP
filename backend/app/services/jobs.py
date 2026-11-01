"""In-process background jobs with durable status rows.

Job state lives in SQLite so the UI can poll it and so a restart is detectable: anything
still queued/running at startup was interrupted and is marked failed (the user can retry).
ponytail: single-process executor; move to a real queue only when running >1 API process.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, update

from app.db import new_session
from app.models import Job, Workspace, utcnow

log = logging.getLogger("ret.jobs")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ret-job")
# Tests flip this to run jobs inline for determinism.
RUN_INLINE = False

JobFn = Callable[[str], str]  # receives job id, returns final status message


def create_job(owner_id: int, kind: str, subject_id: str) -> Job:
    with new_session() as db:
        job = Job(owner_id=owner_id, kind=kind, subject_id=subject_id)
        db.add(job)
        db.commit()
        return job


def submit(job_id: str, fn: JobFn) -> None:
    if RUN_INLINE:
        _run(job_id, fn)
    else:
        _executor.submit(_run, job_id, fn)


def _run(job_id: str, fn: JobFn) -> None:
    started = time.perf_counter()
    _set(job_id, status="running")
    try:
        message = fn(job_id)
    except Exception as exc:  # job boundary: record failure, never crash the worker thread
        log.exception("job %s failed", job_id)
        _set(
            job_id,
            status="failed",
            message=str(exc)[:2000] or exc.__class__.__name__,
            finished_at=utcnow(),
        )
        return
    _set(job_id, status="succeeded", message=message, finished_at=utcnow())
    log.info("job %s succeeded in %.2fs", job_id, time.perf_counter() - started)


def _set(job_id: str, **values: object) -> None:
    with new_session() as db:
        db.execute(update(Job).where(Job.id == job_id).values(**values))
        db.commit()


def report_progress(job_id: str, progress: int, total: int) -> None:
    _set(job_id, progress=progress, total=total)


def active_job(db_kind: str, subject_id: str) -> Job | None:
    with new_session() as db:
        return db.scalar(
            select(Job)
            .where(
                Job.kind == db_kind,
                Job.subject_id == subject_id,
                Job.status.in_(("queued", "running")),
            )
            .order_by(Job.created_at.desc())
        )


def recover_interrupted() -> int:
    """Mark jobs orphaned by a restart as failed and unstick their workspaces."""
    with new_session() as db:
        orphans = db.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
        for job in orphans:
            job.status, job.message, job.finished_at = "failed", "Interrupted by restart.", utcnow()
            if job.kind == "convert":
                ws = db.get(Workspace, job.subject_id)
                if ws is not None and ws.status == "converting":
                    ws.status = "failed"
        db.commit()
        if orphans:
            log.warning("marked %d interrupted jobs as failed", len(orphans))
        return len(orphans)
