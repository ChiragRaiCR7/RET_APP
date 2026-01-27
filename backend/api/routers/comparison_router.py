from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import logging

from api.schemas.comparison import ComparisonRequest, ComparisonResponse
from api.services.comparison_service import compare_files
from api.services.job_service import create_job
from api.workers.comparison_worker import comparison_task
from api.core.database import get_db
from api.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comparison", tags=["comparison"])


@router.post("/run")
async def compare_files_endpoint(
    sideA: UploadFile = File(...),
    sideB: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user),
):
    """
    Compare two files (CSV or JSON) with delta analysis
    Returns detailed field-level changes with indicators
    """
    try:
        file_a_data = await sideA.read()
        file_b_data = await sideB.read()
        
        result = compare_files(file_a_data, sideA.filename or "file_a", 
                              file_b_data, sideB.filename or "file_b")
        
        return result.to_dict()
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.post("/compare")
def compare_async(
    req: ComparisonRequest,
    db: Session = Depends(get_db),
):
    job = create_job(db, "comparison")
    comparison_task.delay(  # type: ignore[attr-defined]
        left_session_id=req.left_session_id,
        right_session_id=req.right_session_id,
        job_id=job.id,
    )
    return {"job_id": job.id}
