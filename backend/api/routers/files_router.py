from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Literal, Optional

from api.core.dependencies import get_current_user, get_current_user_id
from api.core.database import get_db
from api.schemas.conversion import ZipScanResponse
from api.schemas.common import MessageResponse
from api.services.conversion_service import scan_zip_with_groups, get_session_info
from api.services.storage_service import cleanup_session

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/scan", response_model=ZipScanResponse)
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
    db: Session = Depends(get_db),
):
    """
    Scan a ZIP (recursively, including nested ZIPs) or XML file.
    Groups by MODULE PREFIX of business ZIPs (AR, ATK, CST, etc.).
    """
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not (filename.lower().endswith(".zip") or filename.lower().endswith(".xml")):
        raise HTTPException(status_code=400, detail="ZIP or XML file required")

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


@router.get("/session/{session_id}")
async def get_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Get session information"""
    try:
        info = get_session_info(session_id, current_user_id)
        return info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/session/{session_id}", response_model=MessageResponse)
async def delete_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Delete a session and clean up all associated data"""
    try:
        cleanup_session(session_id)
        return MessageResponse(success=True, message=f"Session {session_id} deleted")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete session: {str(e)}")
