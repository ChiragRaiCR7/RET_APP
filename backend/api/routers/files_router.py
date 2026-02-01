from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from api.core.dependencies import get_current_user
from api.core.database import get_db
from api.services.conversion_service import scan_zip_with_groups, get_session_info
from api.services.storage_service import cleanup_session

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/scan")
async def scan_files(
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scan a single ZIP file for XML content and group detection"""
    filename = file.filename
    if not filename or not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="ZIP file required")

    data = await file.read()
    return scan_zip_with_groups(data, filename, current_user_id)


@router.get("/session/{session_id}")
async def get_session(session_id: str, current_user_id: str = Depends(get_current_user)):
    """Get session information"""
    try:
        info = get_session_info(session_id, current_user_id)
        return info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, current_user_id: str = Depends(get_current_user)):
    """Delete a session and clean up all associated data"""
    try:
        cleanup_session(session_id)
        return {"success": True, "message": f"Session {session_id} deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete session: {str(e)}")
