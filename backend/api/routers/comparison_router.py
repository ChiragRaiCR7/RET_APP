from fastapi import APIRouter, HTTPException
from api.schemas.comparison import ComparisonRequest, ComparisonResponse
from api.services.comparison_service import compare_sessions
from api.services.job_service import create_job
from api.workers.comparison_worker import comparison_task

router = APIRouter(prefix="/api/comparison", tags=["comparison"])


@router.post("/compare")
def compare_async(req: ComparisonRequest, db: Session = Depends(get_db)):
    job = create_job(db, "comparison")
    comparison_task.delay(
        left_session_id=req.left_session_id,
        right_session_id=req.right_session_id,
        job_id=job.id,
    )
    return {"job_id": job.id}