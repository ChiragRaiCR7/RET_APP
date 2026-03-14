
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional, Any, Dict, Tuple

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user_id
from api.schemas.common import JobCreatedResponse
from api.schemas.comparison import (
    ComparisonRequest,
    ComparisonSummary,
    ZipComparisonResponse,
    FileComparisonDetail,
    FolderChange,
    GroupChange,
)
from api.services.comparison_service import (
    compare_files,
    get_file_drilldown,
    compare_sessions as service_compare_sessions,
)
from api.services.storage_service import get_session_metadata
from api.services.job_service import create_job

# ✅ Celery tasks
from api.workers.comparison_worker import comparison_task, comparison_files_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparison", tags=["comparison"])


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _http_400(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _http_500(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _safe_filename(name: Optional[str], fallback: str) -> str:
    n = (name or "").strip()
    return n if n else fallback


def _validate_threshold(sim_threshold: float) -> float:
    """
    Ensures sim_threshold is a float in [0.0, 1.0].
    Query already constrains this, but we keep a defensive check.
    """
    try:
        st = float(sim_threshold)
    except Exception as e:
        raise _http_400(f"Invalid sim_threshold: {e}") from e
    if st < 0.0 or st > 1.0:
        raise _http_400("Similarity threshold must be between 0.0 and 1.0.")
    return st


async def _read_upload_file(upload: UploadFile, fallback_name: str) -> Tuple[bytes, str]:
    """
    Read upload content safely and return (bytes, resolved_name).
    """
    name = _safe_filename(upload.filename, fallback_name)
    try:
        data = await upload.read()
    except Exception as e:
        raise _http_400(f"Failed to read uploaded file '{name}': {e}") from e

    if not data:
        raise _http_400(f"Uploaded file '{name}' is empty.")

    return data, name


def _make_job_workspace(job_id: int) -> Path:
    """
    Create a temp workspace folder for this job upload.
    Worker will delete it via cleanup_dir (best effort).
    """
    base = Path(tempfile.gettempdir())
    work_dir = Path(tempfile.mkdtemp(prefix=f"comparison_job_{job_id}_", dir=str(base)))
    return work_dir


# -------------------------------------------------------------------
# ✅ NEW: Async ZIP/XML/CSV compare for uploads (ALWAYS-ASYNC UI path)
# -------------------------------------------------------------------
@router.post(
    "/run-async",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start async comparison of two inputs (ZIP/XML/CSV) as a job",
)
async def compare_files_run_async(
    sideA: UploadFile = File(..., description="Side A input file (ZIP/XML/CSV)"),
    sideB: UploadFile = File(..., description="Side B input file (ZIP/XML/CSV)"),
    ignore_case: bool = Query(False, description="Ignore case when comparing values"),
    trim_whitespace: bool = Query(True, description="Trim whitespace from values"),
    similarity_pairing: bool = Query(True, description="Use similarity pairing for row matching"),
    sim_threshold: float = Query(0.65, ge=0.0, le=1.0, description="Similarity threshold for pairing (0.0-1.0)"),
    ignore_columns: Optional[str] = Query(
        None,
        description="Comma-separated list of columns to ignore during diff (e.g. WHO columns)",
    ),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobCreatedResponse:
    """
    Always-async upload comparison endpoint.

    Flow:
      1) Create job in DB
      2) Save both uploads to a job temp workspace
      3) Enqueue Celery task comparison_files_task
      4) Return { job_id } immediately
    """
    try:
        st = _validate_threshold(sim_threshold)

        file_a_data, file_a_name = await _read_upload_file(sideA, "sideA")
        file_b_data, file_b_name = await _read_upload_file(sideB, "sideB")

        job = await create_job(db, "comparison", user_id=int(current_user_id))
        work_dir = _make_job_workspace(job.id)

        a_path = work_dir / f"A_{file_a_name}"
        b_path = work_dir / f"B_{file_b_name}"
        a_path.write_bytes(file_a_data)
        b_path.write_bytes(file_b_data)

        logger.info(
            "comparison.run-async queued user=%s job_id=%s A=%s B=%s ignore_case=%s trim_ws=%s sim_pair=%s st=%.3f",
            current_user_id,
            job.id,
            file_a_name,
            file_b_name,
            ignore_case,
            trim_whitespace,
            similarity_pairing,
            st,
        )

        comparison_files_task.delay(  # type: ignore[attr-defined]
            file_a_path=str(a_path),
            file_a_name=file_a_name,
            file_b_path=str(b_path),
            file_b_name=file_b_name,
            job_id=job.id,
            ignore_case=ignore_case,
            trim_whitespace=trim_whitespace,
            similarity_pairing=similarity_pairing,
            sim_threshold=st,
            ignore_columns=ignore_columns,
            cleanup_dir=str(work_dir),
        )

        return JobCreatedResponse(job_id=job.id)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Async file comparison submission failed")
        raise _http_500(f"Failed to start async comparison: {e}") from e


# -------------------------------------------------------------------
# Sync ZIP/XML/CSV comparison for UI (fallback/debug)
# NOTE: UI should prefer /run-async. Keep /run for compatibility.
# -------------------------------------------------------------------
@router.post(
    "/run",
    status_code=status.HTTP_200_OK,
    summary="Compare two inputs (ZIP/XML/CSV) synchronously (fallback/debug)",
)
async def compare_files_endpoint(
    sideA: UploadFile = File(..., description="Side A input file (ZIP/XML/CSV)"),
    sideB: UploadFile = File(..., description="Side B input file (ZIP/XML/CSV)"),
    ignore_case: bool = Query(False, description="Ignore case when comparing values"),
    trim_whitespace: bool = Query(True, description="Trim whitespace from values"),
    similarity_pairing: bool = Query(True, description="Use similarity pairing for row matching"),
    sim_threshold: float = Query(0.65, ge=0.0, le=1.0, description="Similarity threshold for pairing (0.0-1.0)"),
    ignore_columns: Optional[str] = Query(
        None,
        description="Comma-separated list of columns to ignore during diff (e.g. WHO columns)",
    ),
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Synchronous compare endpoint (kept for compatibility).

    If frontend calls this endpoint, it MUST use long timeout
    because upload time alone can exceed 30 seconds for large ZIPs.
    """
    try:
        st = _validate_threshold(sim_threshold)

        file_a_data, file_a_name = await _read_upload_file(sideA, "sideA")
        file_b_data, file_b_name = await _read_upload_file(sideB, "sideB")

        logger.info(
            "comparison.run (sync) user=%s A=%s B=%s ignore_case=%s trim_ws=%s sim_pair=%s st=%.3f",
            current_user_id,
            file_a_name,
            file_b_name,
            ignore_case,
            trim_whitespace,
            similarity_pairing,
            st,
        )

        result = compare_files(
            file_a_data,
            file_a_name,
            file_b_data,
            file_b_name,
            ignore_case=ignore_case,
            trim_whitespace=trim_whitespace,
            similarity_pairing=similarity_pairing,
            sim_threshold=st,
            ignore_columns=ignore_columns,
        )

        return result.to_dict()

    except HTTPException:
        raise
    except ValueError as e:
        raise _http_400(str(e)) from e
    except Exception as e:
        logger.exception("Comparison failed")
        raise _http_500(f"Comparison failed: {e}") from e


# -------------------------------------------------------------------
# Optional: ZIP compare with typed response model (sync)
# -------------------------------------------------------------------
@router.post(
    "/compare-zip",
    response_model=ZipComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare two ZIP files (typed response)",
)
async def compare_zip_files_endpoint(
    sideA: UploadFile = File(..., description="Side A ZIP"),
    sideB: UploadFile = File(..., description="Side B ZIP"),
    ignore_case: bool = Query(False, description="Ignore case when comparing"),
    trim_whitespace: bool = Query(True, description="Trim whitespace from values"),
    similarity_pairing: bool = Query(True, description="Use similarity pairing for row matching"),
    sim_threshold: float = Query(0.65, ge=0.0, le=1.0, description="Similarity threshold for pairing"),
    ignore_columns: Optional[str] = Query(
        None,
        description="Comma-separated list of columns to ignore during diff (e.g. WHO columns)",
    ),
    current_user_id: str = Depends(get_current_user_id),
) -> ZipComparisonResponse:
    """
    Compare two ZIP files containing XML/CSV data.
    Returns typed response with file-level changes and structure deltas.
    """
    try:
        st = _validate_threshold(sim_threshold)

        file_a_data, file_a_name = await _read_upload_file(sideA, "sideA.zip")
        file_b_data, file_b_name = await _read_upload_file(sideB, "sideB.zip")

        logger.info(
            "comparison.compare-zip user=%s A=%s B=%s ignore_case=%s trim_ws=%s sim_pair=%s st=%.3f",
            current_user_id,
            file_a_name,
            file_b_name,
            ignore_case,
            trim_whitespace,
            similarity_pairing,
            st,
        )

        result = compare_files(
            file_a_data,
            file_a_name,
            file_b_data,
            file_b_name,
            ignore_case=ignore_case,
            trim_whitespace=trim_whitespace,
            similarity_pairing=similarity_pairing,
            sim_threshold=st,
            ignore_columns=ignore_columns,
        )

        return ZipComparisonResponse(
            summary=ComparisonSummary(
                total_files=result.same + result.modified + result.added + result.removed,
                matched_files=result.same + result.modified,
                same=result.same,
                modified=result.modified,
                added=result.added,
                removed=result.removed,
                overall_similarity=result.similarity,
            ),
            files=[FileComparisonDetail(**c) for c in (result.changes or [])],
            folder_changes=[FolderChange(**fc) for fc in (result.folder_changes or [])],
            group_changes=[GroupChange(**gc) for gc in (result.group_deltas or [])],
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise _http_400(str(e)) from e
    except Exception as e:
        logger.exception("ZIP comparison failed")
        raise _http_500(f"ZIP comparison failed: {e}") from e


# -------------------------------------------------------------------
# Drilldown: used by Compare Data modal
# -------------------------------------------------------------------
@router.post(
    "/drilldown",
    status_code=status.HTTP_200_OK,
    summary="Get detailed drilldown diff for a file pair (tabular CSV diff)",
)
async def drilldown_comparison(
    csv_path_a: Optional[str] = Query(None, description="Path to CSV file A"),
    csv_path_b: Optional[str] = Query(None, description="Path to CSV file B"),
    ignore_case: bool = Query(False, description="Ignore case when comparing"),
    trim_whitespace: bool = Query(True, description="Trim whitespace from values"),
    similarity_pairing: bool = Query(True, description="Use similarity pairing for row matching"),
    sim_threshold: float = Query(0.65, ge=0.0, le=1.0, description="Similarity threshold for pairing (0.0-1.0)"),
    ignore_columns: Optional[str] = Query(None, description="Comma-separated columns to ignore (e.g. WHO columns)"),
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Drilldown comparison for a specific file pair.
    Returns deltaA/deltaB tables with row-level and cell-level markers.
    """
    try:
        st = _validate_threshold(sim_threshold)

        if not csv_path_a and not csv_path_b:
            raise _http_400("Missing CSV paths (csv_path_a or csv_path_b is required).")

        logger.info(
            "comparison.drilldown user=%s A=%s B=%s ignore_case=%s trim_ws=%s sim_pair=%s st=%.3f",
            current_user_id,
            csv_path_a,
            csv_path_b,
            ignore_case,
            trim_whitespace,
            similarity_pairing,
            st,
        )

        result = get_file_drilldown(
            csv_path_a=csv_path_a,
            csv_path_b=csv_path_b,
            ignore_case=ignore_case,
            trim_whitespace=trim_whitespace,
            similarity_pairing=similarity_pairing,
            sim_threshold=st,
            ignore_columns=ignore_columns,
        )

        if isinstance(result, dict) and "error" in result:
            raise _http_400(str(result.get("error") or "Drilldown failed."))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Drilldown comparison failed")
        raise _http_500(f"Drilldown failed: {e}") from e


# -------------------------------------------------------------------
# Async session-to-session comparison (jobs) (existing behavior)
# -------------------------------------------------------------------
@router.post(
    "/compare",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start async comparison of two session outputs (job-based)",
)
async def compare_async(
    req: ComparisonRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobCreatedResponse:
    """
    Start async comparison of two session outputs.
    Returns a job ID that can be used to check status.
    """
    try:
        if not req.left_session_id or not req.right_session_id:
            raise _http_400("left_session_id and right_session_id are required.")

        job = await create_job(
            db,
            "comparison",
            user_id=int(current_user_id),
            session_id=req.left_session_id,
        )

        comparison_task.delay(  # type: ignore[attr-defined]
            left_session_id=req.left_session_id,
            right_session_id=req.right_session_id,
            job_id=job.id,
        )

        return JobCreatedResponse(job_id=job.id)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Async comparison job creation failed")
        raise _http_500(f"Failed to create comparison job: {e}") from e


@router.get(
    "/sessions/{left_id}/{right_id}",
    status_code=status.HTTP_200_OK,
    summary="Compare output files from two sessions synchronously",
)
async def compare_sessions_endpoint(
    left_id: str,
    right_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Compare output files from two sessions synchronously.
    Returns detailed comparison results.
    """
    try:
        if not left_id or not right_id:
            raise _http_400("Both left_id and right_id are required.")

        left_meta = get_session_metadata(left_id)
        right_meta = get_session_metadata(right_id)

        left_owner = left_meta.get("user_id")
        right_owner = right_meta.get("user_id")

        if left_owner != current_user_id or right_owner != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

        logger.info("comparison.sessions user=%s left=%s right=%s", current_user_id, left_id, right_id)

        result = service_compare_sessions(left_id, right_id)
        if isinstance(result, dict) and "error" in result:
            raise _http_400(str(result.get("error") or "Session comparison failed."))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Session comparison failed")
        raise _http_500(f"Session comparison failed: {e}") from e
