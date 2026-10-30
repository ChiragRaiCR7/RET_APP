
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException,
    Depends,
    Form,
    Query,
    Response,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import zipfile
import io
import logging
from typing import List, Optional, Literal

from api.schemas.conversion import (
    ZipScanResponse,
    ConversionFilesResponse,
    FilePreviewResponse,
    GroupsListResponse,
    ExclusionListResponse,
    AddRowRequest,
    AddFileRequest,
    SaveEditsRequest,
    UpdateCellsRequest,
)

from api.schemas.common import MessageResponse
from api.schemas.common import JobCreatedResponse

from api.schemas.advanced import (
    XLSXConversionRequest,
    XLSXConversionResponse,
)

from api.services.conversion_service import (
    scan_zip_with_groups,
    convert_session,
    list_converted_files,
    get_exclusion_list,
    set_exclusion_list,
    get_file_preview,
    build_download_zip,
    download_single_file,
    get_conversion_index,
    add_row_to_file,
    add_new_file,
    delete_file,
    apply_cell_changes,
    refresh_conversion_index,
    get_session_info,
)

from api.services.xlsx_service import get_xlsx_bytes_from_csv
from api.services.storage_service import (
    cleanup_session as cleanup_session_storage,
    get_session_metadata,
    save_session_metadata,
)
from api.services.business_structure_service import build_business_structure
from api.schemas.business_structure import BusinessStructureResponse
from api.services.job_service import create_job, get_job, find_active_job
from api.core.database import get_db
from api.core.dependencies import get_current_user_id
from api.workers.conversion_worker import conversion_task
from api.services.ai.session_manager import trigger_auto_embed_after_conversion

logger = logging.getLogger(__name__)

# Routers
router = APIRouter(prefix="/conversion", tags=["conversion"])
workflow_router = APIRouter(prefix="/workflow", tags=["workflow"])
advanced_router = APIRouter(prefix="/advanced", tags=["Advanced Features"])
files_router = APIRouter(prefix="/files", tags=["files"])

SUPPORTED_UPLOAD_EXTENSIONS = (".zip", ".xml", ".xml.gz", ".csv", ".xlsx", ".xls")


def _normalize_idempotency_key(value: Optional[str]) -> Optional[str]:
    """Normalize user-provided idempotency key for async job dedupe."""
    if value is None:
        return None
    key = str(value).strip()
    if not key:
        return None
    if len(key) > 128:
        key = key[:128]
    return key


def _default_embedding_meta(message: str = "Auto-embedding not attempted") -> dict:
    return {
        "status": "not_attempted",
        "attempted": False,
        "triggered": False,
        "eligible_groups": [],
        "message": message,
    }


def _attach_embedding_metadata(payload: dict, embedding_meta: Optional[dict]) -> dict:
    meta = embedding_meta if isinstance(embedding_meta, dict) else _default_embedding_meta()
    payload["embedding_status"] = str(meta.get("status", "not_attempted"))
    payload["embedding"] = meta
    return payload


# ============================================================
# /files endpoints (consolidated)
# ============================================================

@files_router.post("/scan", response_model=ZipScanResponse)
async def scan_files(
    file: UploadFile = File(...),
    group_mode: Literal["zip", "folder", "hybrid"] = Query("zip"),
    group_prefix_len: Optional[int] = Query(
        None, ge=1, le=10, description="Optional: limit group prefix length (2/3/4)."
    ),
    max_depth: int = Query(10, ge=0, le=50),
    max_files: int = Query(20000, ge=100, le=200000),
    max_unzipped_mb: int = Query(300, ge=1, le=50000),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),  # kept for parity/future auditing
):
    """
    Scan a ZIP (recursively, including nested ZIPs) OR a single file.

    Supports:
      - ZIP
      - XML / XML.GZ
      - CSV
      - XLSX / XLS
    """
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="No file provided")

    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in SUPPORTED_UPLOAD_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(SUPPORTED_UPLOAD_EXTENSIONS)}",
        )

    data = await file.read()
    try:
        return scan_zip_with_groups(
            file_bytes=data,
            filename=filename,
            user_id=current_user_id,
            group_mode=group_mode,
            group_prefix_len=group_prefix_len,
            max_depth=max_depth,
            max_files=max_files,
            max_unzipped_bytes=max_unzipped_mb * 1024 * 1024,
        )
    except Exception as e:
        logger.exception("Files scan failed")
        raise HTTPException(status_code=400, detail=f"Failed to scan: {str(e)}")


@files_router.get("/session/{session_id}")
async def get_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Get session information (ownership enforced in service)."""
    try:
        info = get_session_info(session_id, current_user_id)
        return info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@files_router.delete("/session/{session_id}", response_model=MessageResponse)
async def delete_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Delete a session and clean up all associated data (strict ownership enforced)."""
    from api.services.storage_service import get_session_metadata

    try:
        meta = get_session_metadata(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session metadata: {str(e)}")

    stored_user = meta.get("user_id")
    if not stored_user or stored_user != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        await cleanup_session_storage(session_id)
        return MessageResponse(success=True, message=f"Session {session_id} deleted")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete session: {str(e)}")


# ============================================================
# /conversion endpoints
# ============================================================

@router.post("/scan", response_model=ZipScanResponse)
async def scan(
    file: UploadFile = File(...),
    group_mode: Literal["zip", "folder", "hybrid"] = Query("zip"),
    group_prefix_len: Optional[int] = Query(
        None, ge=1, le=10,
        description="Optional: limit group prefix length (2/3/4). Default uses full prefix token."
    ),
    max_depth: int = Query(10, ge=0, le=50, description="Max nested zip recursion depth."),
    max_files: int = Query(20000, ge=100, le=200000, description="Max files to collect."),
    max_unzipped_mb: int = Query(
        300, ge=1, le=50000,
        description="Max total bytes copied during scan (MB)."
    ),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Scan a ZIP (recursively, including nested ZIPs) OR a single file.

    Supports:
      - ZIP
      - XML / XML.GZ
      - CSV
      - XLSX / XLS
    """
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="No file provided")

    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in SUPPORTED_UPLOAD_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(SUPPORTED_UPLOAD_EXTENSIONS)}",
        )

    try:
        data = await file.read()
        return scan_zip_with_groups(
            file_bytes=data,
            filename=filename,
            user_id=current_user_id,
            group_mode=group_mode,
            group_prefix_len=group_prefix_len,
            max_depth=max_depth,
            max_files=max_files,
            max_unzipped_bytes=max_unzipped_mb * 1024 * 1024,
        )
    except Exception as e:
        logger.exception("Scan failed")
        raise HTTPException(status_code=400, detail=f"Failed to scan: {str(e)}")


@router.post("/convert")
async def convert_async(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Start conversion job.

    ✅ Updated validation:
    - Conversion is allowed even if XML count is 0 (CSV/XLSX/XLS-only sessions are valid).
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    logger.info(f"Conversion request: session={session_id}, groups={groups}, format={output_format}")

    from api.services.storage_service import get_session_dir, get_session_metadata

    # Validate session exists and contains any supported extracted content
    try:
        sess_dir = get_session_dir(session_id)
        if not sess_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found. Please scan a file first."
            )

        extract_dir = sess_dir / "extracted"
        if not extract_dir.exists():
            raise HTTPException(status_code=400, detail="No extracted files found. Please scan a file first.")

        found_any = False
        for ext in (".xml", ".csv", ".xlsx", ".xls"):
            if list(extract_dir.rglob(f"*{ext}")):
                found_any = True
                break

        if not found_any:
            raise HTTPException(
                status_code=400,
                detail="No supported extracted files found. Please scan a ZIP/XML/CSV/XLSX/XLS first."
            )

        # Ownership check (best-effort; service enforces as well)
        try:
            meta = get_session_metadata(session_id)
            stored_user = meta.get("user_id")
            if stored_user and stored_user != current_user_id:
                raise HTTPException(status_code=403, detail="Not authorized")
        except HTTPException:
            raise
        except Exception:
            pass

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error during validation: {str(e)}")

    try:
        job = await create_job(
            db,
            "conversion",
            user_id=int(current_user_id),
            session_id=session_id,
        )
        result = convert_session(session_id, groups, output_format)

        stats = result.get("stats", {})
        if stats.get("success", 0) == 0 and stats.get("failed", 0) > 0:
            error_details = result.get("errors", [])
            error_msg = (
                f"All {stats.get('failed')} files failed to convert. "
                f"First error: {error_details[0].get('error', 'Unknown')}"
                if error_details else "All files failed to convert"
            )
            logger.error(error_msg)
            return _attach_embedding_metadata(
                {"success": False, "job_id": job.id, "message": error_msg, **result},
                _default_embedding_meta("Auto-embedding skipped: conversion failed"),
            )

        embedding_meta = trigger_auto_embed_after_conversion(
            session_id=session_id,
            user_id=current_user_id,
            conversion_result=result if isinstance(result, dict) else None,
        )

        return _attach_embedding_metadata({"success": True, "job_id": job.id, **result}, embedding_meta)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Conversion failed")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@router.post("/convert-async", response_model=JobCreatedResponse)
async def convert_async_job(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    idempotency_key: Optional[str] = Form(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Queue conversion as a background job (non-blocking).

    Keeps existing /convert behavior unchanged for compatibility,
    while offering a production-grade async path for large workloads.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    from api.services.storage_service import get_session_dir

    owner_meta: dict = {}
    clean_key = _normalize_idempotency_key(idempotency_key)

    try:
        sess_dir = get_session_dir(session_id)
        if not sess_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found. Please scan a file first.",
            )

        extract_dir = sess_dir / "extracted"
        if not extract_dir.exists():
            raise HTTPException(status_code=400, detail="No extracted files found. Please scan a file first.")

        found_any = False
        for ext in (".xml", ".csv", ".xlsx", ".xls"):
            if list(extract_dir.rglob(f"*{ext}")):
                found_any = True
                break

        if not found_any:
            raise HTTPException(
                status_code=400,
                detail="No supported extracted files found. Please scan a ZIP/XML/CSV/XLSX/XLS first.",
            )

        owner_meta = get_session_metadata(session_id)
        stored_user = owner_meta.get("user_id")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session validation error for async conversion: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error during validation: {str(e)}")

    try:
        # 1) If caller provided idempotency key, try exact prior mapping first.
        if clean_key:
            async_map = owner_meta.get("async_idempotency", {}) or {}
            conversion_map = async_map.get("conversion", {}) or {}
            mapped_job_id = conversion_map.get(clean_key)

            if mapped_job_id is not None:
                existing_job = await get_job(db, int(mapped_job_id))
                if (
                    existing_job is not None
                    and existing_job.user_id == int(current_user_id)
                    and str(existing_job.session_id or "") == session_id
                    and str(existing_job.job_type.value if hasattr(existing_job.job_type, "value") else existing_job.job_type) == "conversion"
                    and str(existing_job.status.value if hasattr(existing_job.status, "value") else existing_job.status)
                    in {"PENDING", "RUNNING", "SUCCESS"}
                ):
                    logger.info(
                        "Idempotent conversion reuse: session=%s user=%s key=%s job_id=%s",
                        session_id,
                        current_user_id,
                        clean_key,
                        existing_job.id,
                    )
                    return JobCreatedResponse(job_id=existing_job.id)

        # 2) Safety dedupe: if an active conversion for this session/user already exists, reuse it.
        active_job = await find_active_job(
            db,
            user_id=int(current_user_id),
            job_type="conversion",
            session_id=session_id,
        )
        if active_job is not None:
            if clean_key:
                async_map = owner_meta.get("async_idempotency", {}) or {}
                conversion_map = async_map.get("conversion", {}) or {}
                conversion_map[clean_key] = int(active_job.id)
                async_map["conversion"] = conversion_map
                owner_meta["async_idempotency"] = async_map
                save_session_metadata(session_id, owner_meta)

            logger.info(
                "Active conversion dedupe hit: session=%s user=%s existing_job_id=%s",
                session_id,
                current_user_id,
                active_job.id,
            )
            return JobCreatedResponse(job_id=active_job.id)

        job = await create_job(
            db,
            "conversion",
            user_id=int(current_user_id),
            session_id=session_id,
        )

        if clean_key:
            async_map = owner_meta.get("async_idempotency", {}) or {}
            conversion_map = async_map.get("conversion", {}) or {}
            conversion_map[clean_key] = int(job.id)
            async_map["conversion"] = conversion_map
            owner_meta["async_idempotency"] = async_map
            save_session_metadata(session_id, owner_meta)

        conversion_task.delay(
            session_id=session_id,
            job_id=job.id,
            groups=groups,
            output_format=output_format,
        )

        return JobCreatedResponse(job_id=job.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Async conversion queueing failed")
        raise HTTPException(status_code=500, detail=f"Failed to queue conversion: {str(e)}")


@router.get("/download/{session_id}")
def download(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Legacy download endpoint:
    Packages output files (CSV/XLSX/XLS) into a zip and returns it.
    """
    from api.services.storage_service import get_session_dir, get_session_metadata

    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            logger.warning(f"Download auth mismatch: stored={stored_user}, current={current_user_id}")
            raise HTTPException(status_code=403, detail="Unauthorized - session belongs to another user")
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.warning(f"Session metadata check failed: {e}")

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"
    if not out_dir.exists():
        raise HTTPException(status_code=404, detail="No output directory found. Run conversion first.")

    csv_files = list(out_dir.glob("*.csv")) + list(out_dir.glob("*.CSV"))
    xlsx_files = list(out_dir.glob("*.xlsx")) + list(out_dir.glob("*.XLSX"))
    xls_files = list(out_dir.glob("*.xls")) + list(out_dir.glob("*.XLS"))
    all_files = csv_files + xlsx_files + xls_files

    if not all_files:
        raise HTTPException(status_code=404, detail="No output files found. Run conversion first.")

    zip_path = sess_dir / "result.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in all_files:
                z.write(f, f.name)

        logger.info(f"Created download zip with {len(all_files)} files for session {session_id}")
        return FileResponse(zip_path, filename="converted_output.zip", media_type="application/zip")
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/files/{session_id}", response_model=ConversionFilesResponse)
def get_converted_files(
    session_id: str,
    group: Optional[str] = Query(None, description="Filter by group name"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    List all output files for a session (CSV/XLSX/XLS).
    """
    try:
        return list_converted_files(session_id, current_user_id, group)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list converted files")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/{session_id}/{filename}", response_model=FilePreviewResponse)
def preview_file(
    session_id: str,
    filename: str,
    max_rows: int = Query(100, ge=1, le=1000, description="Max rows to preview"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Preview output file.

    - CSV supported
    - XLSX supported (pandas + openpyxl)
    - XLS supported depending on service:
        * BIFF XLS (xlrd) OR
        * HTML-as-XLS (pandas.read_html)

    ✅ Runtime parsing errors return 422 (not 500).
    """
    try:
        return get_file_preview(session_id, current_user_id, filename, max_rows)

    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except RuntimeError as e:
        logger.warning(f"Preview unavailable for {filename}: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("Failed to preview file")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups/{session_id}", response_model=GroupsListResponse)
def get_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Get list of groups for a session with file counts.
    """
    try:
        index = get_conversion_index(session_id, current_user_id)
        groups_data = index.get("groups", {})

        groups = [
            {
                "name": g,
                "file_count": len(files),
                "total_rows": sum(f.get("rows", 0) for f in files),
                "total_size": sum(f.get("size_bytes", 0) for f in files),
            }
            for g, files in groups_data.items()
        ]

        return {
            "session_id": session_id,
            "total_groups": len(groups),
            "groups": groups,
        }
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get groups")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exclusions/{session_id}", response_model=ExclusionListResponse)
def get_exclusions(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get session exclusion list (logical paths skipped during conversion)."""
    try:
        excluded = get_exclusion_list(session_id, current_user_id)
        return ExclusionListResponse(
            session_id=session_id,
            excluded_count=len(excluded),
            excluded=excluded,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get exclusions")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exclusions/{session_id}", response_model=ExclusionListResponse)
def set_exclusions(
    session_id: str,
    excluded: Optional[List[str]] = Form(None),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Set session exclusion list.

    Accepts repeated form field `excluded` for compatibility with existing frontend FormData.
    """
    try:
        result = set_exclusion_list(session_id, current_user_id, excluded or [])
        return ExclusionListResponse(
            session_id=session_id,
            excluded_count=int(result.get("excluded_count", 0)),
            excluded=list(result.get("excluded", []) or []),
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Failed to set exclusions")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-custom/{session_id}")
def download_custom(
    session_id: str,
    output_format: str = Form("csv"),
    groups: Optional[List[str]] = Form(None),
    preserve_structure: bool = Form(False),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Download output files with custom options.
    - output_format: 'csv' or 'xlsx'
    - groups: Optional list of groups to include
    - preserve_structure: preserve original logical_path folder structure
    """
    try:
        zip_bytes, filename = build_download_zip(
            session_id,
            current_user_id,
            output_format,
            groups,
            preserve_structure,
        )
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download-file/{session_id}/{filename}")
def download_single(
    session_id: str,
    filename: str,
    format: str = Query("csv", description="Output format: csv or xlsx"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Download a single output file.
    """
    try:
        file_bytes, out_filename, mime_type = download_single_file(
            session_id,
            current_user_id,
            filename,
            format,
        )
        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{out_filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# /workflow legacy endpoints
# ============================================================

@workflow_router.post("/scan", response_model=ZipScanResponse)
async def workflow_scan(
    file: UploadFile = File(...),
    group_mode: Literal["zip", "folder", "hybrid"] = Query("zip"),
    group_prefix_len: Optional[int] = Query(None, ge=1, le=10),
    max_depth: int = Query(10, ge=0, le=50),
    max_files: int = Query(20000, ge=100, le=200000),
    max_unzipped_mb: int = Query(300, ge=1, le=50000),
    current_user_id: str = Depends(get_current_user_id),
):
    return await scan(
        file=file,
        group_mode=group_mode,
        group_prefix_len=group_prefix_len,
        max_depth=max_depth,
        max_files=max_files,
        max_unzipped_mb=max_unzipped_mb,
        current_user_id=current_user_id,
    )


@workflow_router.post("/convert")
async def workflow_convert(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Workflow conversion request: session={session_id}, groups={groups}, format={output_format}")
    return await convert_async(
        session_id=session_id,
        groups=groups,
        output_format=output_format,
        current_user_id=current_user_id,
        db=db,
    )


@workflow_router.post("/convert-async", response_model=JobCreatedResponse)
async def workflow_convert_async(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    idempotency_key: Optional[str] = Form(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await convert_async_job(
        session_id=session_id,
        groups=groups,
        output_format=output_format,
        idempotency_key=idempotency_key,
        current_user_id=current_user_id,
        db=db,
    )


@workflow_router.get("/download/{session_id}")
def workflow_download(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    return download(session_id, current_user_id)


# ============================================================
# Edit & save helpers
# ============================================================

@router.post("/add-row/{session_id}")
def add_row_api(
    session_id: str,
    payload: AddRowRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return add_row_to_file(session_id, current_user_id, payload.filename, payload.row)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Add row failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-file/{session_id}")
def add_file_api(
    session_id: str,
    payload: AddFileRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return add_new_file(session_id, current_user_id, payload.filename, payload.group, payload.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Add file failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-file/{session_id}/{filename}")
def delete_file_api(
    session_id: str,
    filename: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return delete_file(session_id, current_user_id, filename)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Delete file failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-cells/{session_id}")
def update_cells_api(
    session_id: str,
    payload: UpdateCellsRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # pydantic v1/v2 safe conversion
        changes = []
        for c in payload.changes:
            if hasattr(c, "model_dump"):
                changes.append(c.model_dump())
            else:
                changes.append(c.dict())
        return apply_cell_changes(session_id, current_user_id, payload.filename, changes)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Batch cell update failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-edits/{session_id}")
def save_edits_api(
    session_id: str,
    payload: SaveEditsRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Placeholder endpoint to align with frontend workflow.
    Rebuilds conversion index after prior edits.
    """
    try:
        index = refresh_conversion_index(session_id)
        return {"success": True, "changes": len(payload.changes or []), "index": index}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Save edits failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download-modified/{session_id}")
def download_modified(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Alias for download that packages current output (including edits)."""
    return download(session_id, current_user_id)


@router.post("/cleanup/{session_id}")
def cleanup_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Clean up extracted and output files from a session"""
    from api.services.storage_service import get_session_dir, get_session_metadata
    import shutil

    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized - session belongs to another user")
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        sess_dir = get_session_dir(session_id)
        extract_dir = sess_dir / "extracted"
        out_dir = sess_dir / "output"

        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        if out_dir.exists():
            shutil.rmtree(out_dir)

        index_file = sess_dir / "conversion_index.json"
        if index_file.exists():
            index_file.unlink()

        logger.info(f"Cleaned up session {session_id}")
        return {"success": True, "message": "Session cleaned up successfully"}
    except Exception as e:
        logger.exception("Cleanup failed")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


# ============================================================
# Business Structure
# ============================================================

@router.get("/business-structure/{session_id}", response_model=BusinessStructureResponse)
def get_business_structure(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
    business_group: Optional[str] = Query(None, description="Business Group label"),
):
    """Build 5-layer Business Structure hierarchy from converted CSV contents."""
    try:
        return build_business_structure(
            session_id=session_id,
            user_id=current_user_id,
            business_group_name=business_group,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Business structure build failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# XLSX Endpoints (legacy advanced)
# ============================================================

@advanced_router.post("/xlsx/convert", response_model=XLSXConversionResponse)
async def convert_csv_to_xlsx(
    request: XLSXConversionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Convert CSV file from session to XLSX format."""
    try:
        from api.services.storage_service import contained_path, get_session_dir, get_session_metadata

        session_dir = get_session_dir(request.session_id)

        meta = get_session_metadata(request.session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        csv_path = contained_path(session_dir / "output", request.csv_filename)
        if not csv_path.exists():
            csv_path = contained_path(session_dir / "output", request.csv_filename.upper())
        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="CSV file not found")

        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))
        output_filename = request.csv_filename.replace(".csv", ".xlsx").upper()

        return XLSXConversionResponse(
            status="success",
            filename=output_filename,
            size_bytes=len(xlsx_bytes),
            message="Conversion successful",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"XLSX conversion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@advanced_router.get("/xlsx/download/{session_id}/{filename}")
async def download_xlsx(
    session_id: str,
    filename: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Download converted XLSX file (generated from CSV)."""
    try:
        from api.services.storage_service import contained_path, get_session_dir, get_session_metadata

        session_dir = get_session_dir(session_id)

        meta = get_session_metadata(session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        csv_name = filename.replace(".xlsx", ".csv")
        csv_path = contained_path(session_dir / "output", csv_name)
        if not csv_path.exists():
            csv_path = contained_path(session_dir / "output", csv_name.upper())
        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="CSV file not found")

        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))

        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename.upper()}"'},
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"XLSX download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
