from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pathlib import Path
import zipfile
import io
import logging
from typing import List, Optional

from api.schemas.conversion import (
    ZipScanResponse, 
    ConversionFilesResponse,
    FilePreviewResponse,
    GroupsListResponse,
)
from api.services.conversion_service import (
    scan_zip_with_groups, 
    convert_session,
    list_converted_files,
    get_file_preview,
    build_download_zip,
    download_single_file,
    get_conversion_index,
)
from api.services.job_service import create_job
from api.core.database import get_db
from api.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversion", tags=["conversion"])
workflow_router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/scan", response_model=ZipScanResponse)
async def scan(
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user),
):
    """Scan a ZIP or XML file for content and detect groups"""
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="No file provided")

    is_zip = filename.lower().endswith(".zip")
    is_xml = filename.lower().endswith(".xml")
    if not is_zip and not is_xml:
        raise HTTPException(status_code=400, detail="File must be ZIP or XML format")

    try:
        data = await file.read()
        result = scan_zip_with_groups(data, filename, current_user_id)
        return result
    except Exception as e:
        logger.exception("Scan failed")
        raise HTTPException(status_code=400, detail=f"Failed to scan: {str(e)}")


@router.post("/convert")
async def convert_async(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start conversion job.
    - session_id: Session ID (required)
    - groups: Optional list of groups to convert
    - output_format: Output format (csv or xlsx)
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        job = create_job(db, "conversion")
        result = convert_session(session_id, groups)
        return {"success": True, "job_id": job.id, **result}
    except Exception as e:
        logger.exception("Conversion failed")
        raise HTTPException(status_code=400, detail=f"Conversion failed: {str(e)}")


@router.get("/download/{session_id}")
def download(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Package converted CSVs into a zip and return it"""
    from api.services.storage_service import get_session_dir, get_session_metadata

    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        # Check ownership - allow if user matches or if no user was stored
        if stored_user and stored_user != current_user_id:
            logger.warning(f"Download auth mismatch: stored={stored_user}, current={current_user_id}")
            raise HTTPException(status_code=403, detail="Unauthorized - session belongs to another user")
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.warning(f"Session metadata check failed: {e}")
        # Continue anyway if we can't read metadata but session exists

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"
    
    if not out_dir.exists():
        raise HTTPException(status_code=404, detail="No output directory found. Run conversion first.")
    
    csv_files = list(out_dir.glob("*.csv"))
    xlsx_files = list(out_dir.glob("*.xlsx"))
    all_files = csv_files + xlsx_files
    
    if not all_files:
        raise HTTPException(status_code=404, detail="No converted files found. Run conversion first.")
    
    zip_path = sess_dir / "result.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in all_files:
                z.write(f, f.name)
        
        logger.info(f"Created download zip with {len(all_files)} files for session {session_id}")
        return FileResponse(
            zip_path, 
            filename="converted_output.zip",
            media_type="application/zip"
        )
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/files/{session_id}", response_model=ConversionFilesResponse)
def get_converted_files(
    session_id: str,
    group: Optional[str] = Query(None, description="Filter by group name"),
    current_user_id: str = Depends(get_current_user),
):
    """
    List all converted files for a session.
    Provides data for file dropdown and group selection.
    """
    try:
        result = list_converted_files(session_id, current_user_id, group)
        return result
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
    current_user_id: str = Depends(get_current_user),
):
    """
    Get preview data for a converted CSV file.
    Returns headers and rows for table display.
    """
    try:
        result = get_file_preview(session_id, current_user_id, filename, max_rows)
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to preview file")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups/{session_id}", response_model=GroupsListResponse)
def get_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
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


@router.post("/download-custom/{session_id}")
def download_custom(
    session_id: str,
    output_format: str = Form("csv"),
    groups: Optional[List[str]] = Form(None),
    preserve_structure: bool = Form(False),
    current_user_id: str = Depends(get_current_user),
):
    """
    Download converted files with custom options.
    - output_format: 'csv' or 'xlsx'
    - groups: Optional list of groups to include
    - preserve_structure: Whether to preserve original folder structure
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
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
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
    current_user_id: str = Depends(get_current_user),
):
    """
    Download a single converted file.
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
            headers={"Content-Disposition": f'attachment; filename="{out_filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e))


# Frontend-compatible endpoints (legacy routes)
@workflow_router.post("/scan", response_model=ZipScanResponse)
async def workflow_scan(
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user),
):
    return await scan(file, current_user_id)


@workflow_router.post("/convert")
async def workflow_convert(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = create_job(db, "conversion")
    result = convert_session(session_id, groups)
    return {"success": True, "job_id": job.id, **result}


@workflow_router.get("/download/{session_id}")
def workflow_download(session_id: str, current_user_id: str = Depends(get_current_user)):
    return download(session_id, current_user_id)
