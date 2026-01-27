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
from api.services.lite_ai_service import (
    get_ai_service,
    clear_ai_service,
)
from api.services.storage_service import (
    get_session_dir,
    get_session_metadata,
    cleanup_session,
)
from api.services.job_service import create_job
from api.workers.indexing_worker import indexing_task
from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/index")
def index_groups(
    req: IndexRequest,
    current_user_id: str = Depends(get_current_user),
):
    """Index selected groups from converted CSV files"""
    try:
        # Verify user owns this session
        session_metadata = get_session_metadata(req.session_id)
        
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get session directory
        session_dir = get_session_dir(req.session_id)
        output_dir = session_dir / "output"
        
        if not output_dir.exists():
            raise HTTPException(status_code=400, detail="No converted files in session")
        
        # Collect CSV files
        csv_files = list(output_dir.glob("*.csv"))
        
        if not csv_files:
            raise HTTPException(status_code=400, detail="No CSV files to index")
        
        # Get AI service
        ai_service = get_ai_service(req.session_id, str(session_dir / "ai_index"))
        
        # Index files
        result = ai_service.index_csv_files(csv_files)
        
        if result["status"] != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "Indexing failed"))
        
        return {
            "status": "success",
            "message": result.get("message", "Indexing complete"),
            "stats": {
                "documents_indexed": result.get("documents_indexed", 0),
                "chunks_created": result.get("chunks_created", 0),
                "total_size_mb": result.get("total_size_mb", 0.0),
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/indexed-groups/{session_id}")
def get_indexed_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get status of indexed groups for a session"""
    try:
        session_metadata = get_session_metadata(session_id)
        
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        ai_service = get_ai_service(session_id, str(session_dir / "ai_index"))
        
        return {
            "session_id": session_id,
            "is_indexed": ai_service.collection is not None,
            "status": "indexed" if ai_service.collection else "not_indexed",
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
        
        clear_ai_service(session_id)
        
        return {
            "status": "success",
            "message": "AI memory cleared successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear memory")


@router.post("/chat")
def chat(
    req: ChatRequest,
    current_user_id: str = Depends(get_current_user),
):
    """Chat with AI about indexed documents"""
    try:
        # Verify user owns this session
        session_metadata = get_session_metadata(req.session_id)
        
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get AI service
        session_dir = get_session_dir(req.session_id)
        ai_service = get_ai_service(req.session_id, str(session_dir / "ai_index"))
        
        # Query or chat
        if req.question:
            # RAG-based query
            result = ai_service.query(req.question)
            return ChatResponse(
                answer=result["answer"],
                sources=result.get("sources", []),
            )
        elif req.messages:
            # Regular chat
            response = ai_service.chat(req.messages)
            return ChatResponse(
                answer=response,
                sources=[],
            )
        else:
            raise HTTPException(status_code=400, detail="Provide either question or messages")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")
