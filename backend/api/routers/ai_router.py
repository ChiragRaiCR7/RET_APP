from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
import logging

from api.schemas.ai import (
    IndexRequest,
    IndexResponse,
    ChatRequest,
    ChatResponse,
)
from api.services.ai_service import index_session, chat_with_collection
from api.services.ai_indexing_service import get_session_indexer
from api.services.storage_service import get_session_dir, get_session_metadata, cleanup_session
from api.services.job_service import create_job
from api.workers.indexing_worker import indexing_task
from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/index")
def index_async(
    req: IndexRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Index selected groups for AI context"""
    try:
        # Get session information
        session_metadata = get_session_metadata(req.session_id)
        
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get indexer for this session
        runtime_root = Path(settings.RET_RUNTIME_ROOT)
        indexer = get_session_indexer(req.session_id, runtime_root)
        
        # Build groups data from session
        session_dir = get_session_dir(req.session_id)
        extracted_dir = session_dir / "extracted"
        
        # Get group files
        groups_data = {}
        for group_name in req.groups:
            files = []
            for xml_file in extracted_dir.rglob("*.xml"):
                # Check if file belongs to this group
                relative_path = str(xml_file.relative_to(extracted_dir))
                if group_name.upper() in relative_path.upper() or relative_path.startswith(group_name):
                    files.append({
                        "filename": xml_file.name,
                        "path": relative_path,
                        "group": group_name,
                        "size": xml_file.stat().st_size,
                    })
            if files:
                groups_data[group_name] = files
        
        if not groups_data:
            raise HTTPException(status_code=400, detail="No files found for selected groups")
        
        # Index the groups
        stats = indexer.index_groups(groups_data, extracted_dir)
        
        return {
            "status": "success",
            "message": f"Indexed {stats.groups_indexed} groups with {stats.total_documents} documents",
            "indexed_groups": indexer.get_indexed_groups(),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/indexed-groups/{session_id}")
def get_indexed_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get list of indexed groups for a session"""
    try:
        session_metadata = get_session_metadata(session_id)
        
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        runtime_root = Path(settings.RET_RUNTIME_ROOT)
        indexer = get_session_indexer(session_id, runtime_root)
        
        return {
            "session_id": session_id,
            "indexed_groups": indexer.get_indexed_groups(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get indexed groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to get indexed groups")


@router.post("/clear-memory/{session_id}")
def clear_ai_memory(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Clear all AI indexing memory for a session"""
    try:
        session_metadata = get_session_metadata(session_id)
        
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        runtime_root = Path(settings.RET_RUNTIME_ROOT)
        indexer = get_session_indexer(session_id, runtime_root)
        indexer.clear()
        
        return {
            "status": "success",
            "message": "AI memory cleared successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear memory")


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return chat_with_collection(req.collection, req.question)


@router.post("/index-async")
def index_async_old(
    req: IndexRequest,
    db: Session = Depends(get_db),
):
    """Legacy async indexing (deprecated - use /index instead)"""
    job = create_job(db, "indexing")
    indexing_task.delay(  # type: ignore[attr-defined]
        req.session_id,
        req.collection,
        job.id,
    )
    return {"job_id": job.id}
