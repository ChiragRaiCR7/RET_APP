
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.core.database import get_db
from api.core.dependencies import get_current_user_id
from api.models.job import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def job_status(
    job_id: int,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id is None or job.user_id != int(current_user_id):
        # Hide resource existence for non-owners.
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.id,
        "type": job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }
