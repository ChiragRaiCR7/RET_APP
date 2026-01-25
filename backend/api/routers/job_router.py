from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.services.job_service import get_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("/{job_id}")
def job_status(job_id: int, db: Session = Depends(get_db)):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "job_id": job.id,
        "type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }
