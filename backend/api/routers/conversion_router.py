from fastapi import APIRouter, UploadFile, File, HTTPException
from api.schemas.conversion import (
    ZipScanResponse,
    ConversionResponse,
    ConversionRequest,
)
from api.services.conversion_service import scan_zip, convert_session
from fastapi.responses import FileResponse
from pathlib import Path
import zipfile
from api.services.job_service import create_job
from api.workers.conversion_worker import conversion_task


router = APIRouter(prefix="/api/conversion", tags=["conversion"])


@router.post("/scan", response_model=ZipScanResponse)
async def scan(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "ZIP file required")

    data = await file.read()
    result = scan_zip(data, file.filename)
    return result


@router.post("/convert")
def convert_async(req: ConversionRequest, db: Session = Depends(get_db)):
    job = create_job(db, "conversion")
    conversion_task.delay(session_id=req.session_id, job_id=job.id)
    return {"job_id": job.id}


@router.get("/download/{session_id}")
def download(session_id: str):
    from api.services.storage_service import get_session_dir

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"

    zip_path = sess_dir / "result.zip"

    with zipfile.ZipFile(zip_path, "w") as z:
        for f in out_dir.glob("*.csv"):
            z.write(f, f.name)

    return FileResponse(zip_path, filename="converted_csvs.zip")
