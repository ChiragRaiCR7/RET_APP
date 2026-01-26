from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import zipfile
import io

from api.schemas.conversion import (
    ZipScanResponse,
    ConversionResponse,
    ConversionRequest,
)
from api.services.conversion_service import scan_zip_with_groups, convert_session
from api.services.job_service import create_job
from api.workers.conversion_worker import conversion_task
from api.core.database import get_db
from api.core.dependencies import get_current_user

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/scan", response_model=ZipScanResponse)
async def scan_workflow(
    files: list[UploadFile] = File(...),
    current_user_id: str = Depends(get_current_user),
):
    """Scan uploaded ZIP files and extract document groups"""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    all_groups = []
    total_files = 0
    total_size = 0
    session_id = None

    for file in files:
        if not file.filename or not file.filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail=f"Invalid file: {file.filename} - ZIP required")

        data = await file.read()
        total_size += len(data)
        
        try:
            result = scan_zip_with_groups(data, file.filename, current_user_id)
            session_id = result.get("session_id")
            if result and result.get("groups"):
                all_groups.extend(result.get("groups", []))
                total_files += result.get("xml_count", 0)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process {file.filename}: {str(e)}")

    # Format size nicely
    if total_size < 1024:
        size_str = f"{total_size} B"
    elif total_size < 1024 * 1024:
        size_str = f"{(total_size / 1024):.1f} KB"
    else:
        size_str = f"{(total_size / (1024 * 1024)):.1f} MB"

    return {
        "session_id": session_id,
        "files": [],
        "group_count": len(all_groups),
        "xml_count": total_files,
        "groups": all_groups,
        "summary": {
            "totalGroups": len(all_groups),
            "totalFiles": total_files,
            "totalSize": size_str,
        }
    }


@router.post("/convert")
async def convert_workflow(
    req: ConversionRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Convert scanned documents to CSV format"""
    try:
        job = create_job(db, "conversion")
        conversion_task.delay(  # type: ignore[attr-defined]
            session_id=req.session_id,
            job_id=job.id,
            groups=req.groups,
        )
        return {"job_id": job.id, "status": "processing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@router.get("/download/{session_id}")
async def download_workflow(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Download converted files as ZIP"""
    try:
        from api.services.storage_service import get_session_dir, get_session_metadata

        metadata = get_session_metadata(session_id)
        if metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        sess_dir = get_session_dir(session_id)
        out_dir = sess_dir / "output"
        zip_path = sess_dir / "result.zip"

        if not out_dir.exists():
            raise HTTPException(status_code=404, detail="No conversion results found")

        with zipfile.ZipFile(zip_path, "w") as z:
            for f in out_dir.glob("*.csv"):
                z.write(f, f.name)

        return FileResponse(zip_path, filename="converted_csvs.zip")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
