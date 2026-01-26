from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import zipfile

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

router = APIRouter(prefix="/api/conversion", tags=["conversion"])


@router.post("/scan", response_model=ZipScanResponse)
async def scan(
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user),
):
    """Scan a ZIP file for XML content and detect groups"""
    filename = file.filename
    if not filename or not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="ZIP file required")

    try:
        data = await file.read()
        result = scan_zip_with_groups(data, filename, current_user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to scan: {str(e)}")


@router.post("/convert")
def convert_async(
    req: ConversionRequest,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start async conversion job for specific groups"""
    job = create_job(db, "conversion")
    conversion_task.delay(  # type: ignore[attr-defined]
        session_id=req.session_id,
        job_id=job.id,
        groups=req.groups,
    )
    return {"job_id": job.id}


@router.get("/download/{session_id}")
def download(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Download converted CSV files"""
    from api.services.storage_service import get_session_dir, get_session_metadata
    
    try:
        metadata = get_session_metadata(session_id)
        if metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
    except:
        raise HTTPException(status_code=404, detail="Session not found")

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"
    zip_path = sess_dir / "result.zip"

    with zipfile.ZipFile(zip_path, "w") as z:
        for f in out_dir.glob("*.csv"):
            z.write(f, f.name)

    return FileResponse(zip_path, filename="converted_csvs.zip")

