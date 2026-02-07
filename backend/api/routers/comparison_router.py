from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from api.schemas.comparison import (
    ComparisonRequest,
    ComparisonSummary,
    ZipComparisonResponse,
    FileComparisonDetail,
    FolderChange,
    GroupChange,
)
from api.schemas.common import JobCreatedResponse
from api.services.comparison_service import (
    compare_files,
    get_file_drilldown,
    compare_sessions as service_compare_sessions,
)
from api.services.job_service import create_job
from api.workers.comparison_worker import comparison_task
from api.core.database import get_db
from api.core.dependencies import get_current_user, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparison", tags=["comparison"])


@router.post("/run")
async def compare_files_endpoint(
    sideA: UploadFile = File(...),
    sideB: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Compare two files (CSV, XML, or ZIP) with delta analysis.
    Returns detailed field-level changes with indicators.
    """
    try:
        file_a_data = await sideA.read()
        file_b_data = await sideB.read()

        result = compare_files(
            file_a_data, sideA.filename or "file_a",
            file_b_data, sideB.filename or "file_b"
        )

        return result.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.post("/compare-zip", response_model=ZipComparisonResponse)
async def compare_zip_files_endpoint(
    sideA: UploadFile = File(...),
    sideB: UploadFile = File(...),
    ignore_case: bool = Query(False, description="Ignore case when comparing"),
    trim_whitespace: bool = Query(True, description="Trim whitespace from values"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Compare two ZIP files containing XML/CSV data.
    Returns comprehensive comparison with file-level and row-level changes.
    """
    try:
        file_a_data = await sideA.read()
        file_b_data = await sideB.read()

        result = compare_files(
            file_a_data, sideA.filename or "file_a.zip",
            file_b_data, sideB.filename or "file_b.zip"
        )

        return ZipComparisonResponse(
            summary=ComparisonSummary(
                total_files=result.same + result.modified + result.added + result.removed,
                same=result.same,
                modified=result.modified,
                added=result.added,
                removed=result.removed,
                overall_similarity=result.similarity,
            ),
            files=[FileComparisonDetail(**c) for c in result.changes] if result.changes else [],
            folder_changes=[FolderChange(**fc) for fc in result.folder_changes] if result.folder_changes else [],
            group_changes=[GroupChange(**gc) for gc in result.group_deltas] if result.group_deltas else [],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"ZIP Comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.post("/drilldown")
async def drilldown_comparison(
    csv_path_a: Optional[str] = Query(None, description="Path to CSV file A"),
    csv_path_b: Optional[str] = Query(None, description="Path to CSV file B"),
    ignore_case: bool = Query(False, description="Ignore case when comparing"),
    trim_whitespace: bool = Query(True, description="Trim whitespace from values"),
    similarity_pairing: bool = Query(True, description="Use similarity pairing for row matching"),
    sim_threshold: float = Query(0.65, description="Similarity threshold for pairing (0.0-1.0)"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Get detailed row-level comparison for a specific file pair.
    Returns cell-level changes with indicators for GitHub-style diff display.
    """
    try:
        result = get_file_drilldown(
            csv_path_a,
            csv_path_b,
            ignore_case=ignore_case,
            trim_whitespace=trim_whitespace,
            similarity_pairing=similarity_pairing,
            sim_threshold=sim_threshold,
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Drilldown comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Drilldown failed: {str(e)}")


@router.post("/compare", response_model=JobCreatedResponse)
def compare_async(
    req: ComparisonRequest,
    db: Session = Depends(get_db),
):
    """
    Start async comparison of two session outputs.
    Returns a job ID that can be used to check status.
    """
    job = create_job(db, "comparison")
    comparison_task.delay(  # type: ignore[attr-defined]
        left_session_id=req.left_session_id,
        right_session_id=req.right_session_id,
        job_id=job.id,
    )
    return JobCreatedResponse(job_id=job.id)


@router.get("/sessions/{left_id}/{right_id}")
async def compare_sessions_endpoint(
    left_id: str,
    right_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Compare output files from two sessions synchronously.
    Returns detailed comparison results.
    """
    try:
        result = service_compare_sessions(left_id, right_id)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session comparison failed: {str(e)}")
