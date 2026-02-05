"""
Enhanced AI Router with Advanced RAG

Provides endpoints for the LangChain/LangGraph Advanced RAG system:
- Query transformation and intent detection
- Query routing (vector/lexical/summary/fusion)
- Fusion retrieval combining multiple strategies
- Reranking and postprocessing
- Citation-aware response generation
"""

from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging
import json
from datetime import datetime

from api.core.config import settings
from api.core.dependencies import get_current_user
from api.services.storage_service import get_session_dir, get_session_metadata, save_session_metadata
from api.schemas.ai import (
    RAGChatRequest,
    RAGChatResponse,
    AutoIndexProgress,
    StartAutoIndexRequest,
    AutoIndexStatusResponse,
    GroupSelectionRequest,
    DetectedGroupsResponse,
    GroupInfo,
    SourceDocument,
    TranscriptRequest,
    TranscriptFormat,
    QueryTransformationInfo,
    RetrievalMetadata,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/ai", tags=["ai-v2"])


# ============================================================
# RAG Configuration Check
# ============================================================

@router.get("/status")
def get_ai_status(
    current_user_id: str = Depends(get_current_user),
):
    """Check AI service status and configuration"""
    is_configured = bool(
        settings.AZURE_OPENAI_API_KEY and 
        settings.AZURE_OPENAI_ENDPOINT
    )
    
    return {
        "status": "available" if is_configured else "not_configured",
        "configured": is_configured,
        "features": {
            "rag_chat": is_configured,
            "auto_indexing": is_configured,
            "embeddings": is_configured,
        },
        "settings": {
            "temperature": settings.RET_AI_TEMPERATURE,
            "strategy": settings.AI_STRATEGY,
        }
    }


# ============================================================
# AI Config Endpoint
# ============================================================

def _load_ai_config() -> dict:
    """Load AI config from data/ai_config.json"""
    config_path = Path(settings.RET_RUNTIME_ROOT).parent / "data" / "ai_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"auto_indexed_groups": [], "default_collection": "documents"}


@router.get("/config")
def get_ai_config(
    current_user_id: str = Depends(get_current_user),
):
    """
    Get AI configuration including auto-indexed groups.
    """
    try:
        config = _load_ai_config()
        return {
            "auto_indexed_groups": config.get("auto_indexed_groups", []),
            "default_collection": config.get("default_collection", "documents"),
            "chunk_size": config.get("chunk_size", 10000),
            "retrieval_top_k": config.get("retrieval_top_k", 16),
            "enable_auto_indexing": config.get("enable_auto_indexing", False),
        }
    except Exception as e:
        logger.error(f"Failed to get AI config: {e}")
        return {
            "auto_indexed_groups": [],
            "default_collection": "documents",
            "chunk_size": 10000,
            "retrieval_top_k": 16,
            "enable_auto_indexing": False,
        }


# ============================================================
# RAG Chat Endpoints
# ============================================================

@router.post("/chat", response_model=RAGChatResponse)
async def rag_chat(
    req: RAGChatRequest,
    current_user_id: str = Depends(get_current_user),
):
    """
    Send a message and get Advanced RAG-powered response.
    
    Features:
    - Query transformation for better retrieval
    - Intent detection and query routing
    - Fusion retrieval (vector + lexical + summary)
    - Reranking with hybrid scoring
    - Citation-aware response generation
    """
    from api.services.ai.session_manager import get_session_ai_manager
    from api.schemas.ai import QueryTransformationInfo, RetrievalMetadata
    
    try:
        # Verify session ownership
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get the query from either message or question field
        query_text = req.message or req.question or ""
        if not query_text.strip():
            raise HTTPException(status_code=400, detail="No message provided")
        
        # Get AI manager
        manager = get_session_ai_manager(req.session_id, current_user_id)
        
        if not manager.is_configured():
            raise HTTPException(
                status_code=503, 
                detail="AI service not configured. Set Azure OpenAI credentials."
            )
        
        # Execute chat with Advanced RAG
        result = manager.chat(
            message=query_text,
            use_rag=req.use_rag,
            group_filter=req.group_filter,
            top_k=req.top_k,
        )
        
        # Convert to response format with enhanced sources
        sources = [
            SourceDocument(
                file=src.get("source", ""),
                group=src.get("group"),
                snippet=src.get("content", "")[:500],
                score=src.get("score"),
                chunk_index=src.get("rank", i),
            )
            for i, src in enumerate(result.get("sources", []))
        ]
        
        # Build Advanced RAG metadata if available
        metadata = result.get("metadata", {})
        
        query_transformation = None
        if "query_transformation" in metadata:
            qt = metadata["query_transformation"]
            query_transformation = QueryTransformationInfo(
                original=qt.get("original", query_text),
                transformed=qt.get("transformed", query_text),
                intent=qt.get("intent", "factual"),
                keywords=qt.get("keywords", []),
            )
        
        retrieval_metadata = None
        if "retrieval_strategy" in metadata or "timing" in metadata:
            retrieval_metadata = RetrievalMetadata(
                retrieval_strategy=metadata.get("retrieval_strategy", "hybrid"),
                chunks_retrieved=metadata.get("chunks_retrieved", len(sources)),
                timing=metadata.get("timing"),
            )
        
        return RAGChatResponse(
            answer=result.get("answer", ""),
            sources=sources,
            citations=result.get("citations", []),
            query_time_ms=result.get("query_time_ms", 0),
            query_plan=metadata.get("query_plan"),
            chunks_retrieved=metadata.get("chunks_retrieved", len(sources)),
            query_transformation=query_transformation,
            retrieval_metadata=retrieval_metadata,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.get("/chat/history/{session_id}")
def get_chat_history(
    session_id: str,
    limit: int = 50,
    current_user_id: str = Depends(get_current_user),
):
    """Get chat history for a session"""
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(session_id, current_user_id)
        history = manager.get_chat_history(limit=limit)
        
        return {
            "session_id": session_id,
            "messages": history,
            "count": len(history),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chat history")


@router.delete("/chat/history/{session_id}")
def clear_chat_history(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Clear chat history for a session"""
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(session_id, current_user_id)
        manager.clear_chat_history()
        
        return {"status": "success", "message": "Chat history cleared"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear chat history")


# ============================================================
# Indexing Endpoints
# ============================================================

@router.get("/index/groups")
def get_available_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """
    Get available groups from XML inventory for indexing.
    Returns list of groups detected in the scanned ZIP file.
    """
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        
        # Load XML inventory from session
        inventory_path = session_dir / "xml_inventory.json"
        if not inventory_path.exists():
            return {
                "status": "no_inventory",
                "groups": [],
                "message": "No XML inventory found. Run ZIP scan first."
            }
        
        with open(inventory_path, "r", encoding="utf-8") as f:
            xml_inventory = json.load(f)
        
        # Extract unique groups from inventory
        groups_set = set()
        for item in xml_inventory:
            if isinstance(item, dict) and "group" in item:
                groups_set.add(item["group"])
        
        # Get already indexed groups
        indexed_groups = set(session_metadata.get("indexed_groups", []))
        
        # Build group info list
        groups_info = []
        for group in sorted(groups_set):
            # Count files in this group
            file_count = sum(1 for item in xml_inventory 
                           if isinstance(item, dict) and item.get("group") == group)
            groups_info.append({
                "name": group,
                "file_count": file_count,
                "indexed": group in indexed_groups,
            })
        
        return {
            "status": "success",
            "groups": groups_info,
            "total_groups": len(groups_info),
            "indexed_groups": list(indexed_groups),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get available groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to get available groups")


@router.post("/index/groups")
async def index_selected_groups(
    req: GroupSelectionRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user),
):
    """
    Index selected groups from scanned XML files.
    This is manual indexing triggered from the UI.
    """
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get groups from either field
        groups_to_index = req.selected_groups or req.groups or []
        if not groups_to_index:
            raise HTTPException(status_code=400, detail="No groups selected")
        
        session_dir = get_session_dir(req.session_id)
        
        # Get AI manager
        manager = get_session_ai_manager(req.session_id, current_user_id)
        
        if not manager.is_configured():
            raise HTTPException(
                status_code=503,
                detail="AI service not configured"
            )
        
        # Load XML inventory from session
        inventory_path = session_dir / "xml_inventory.json"
        if not inventory_path.exists():
            raise HTTPException(
                status_code=400,
                detail="No XML inventory found. Run ZIP scan first."
            )
        
        with open(inventory_path, "r", encoding="utf-8") as f:
            xml_inventory = json.load(f)
        
        # Run indexing
        result = manager.index_groups(
            xml_inventory=xml_inventory,
            groups=groups_to_index,
        )
        
        # Update session metadata
        metadata = get_session_metadata(req.session_id)
        indexed = set(metadata.get("indexed_groups", []))
        indexed.update(groups_to_index)
        metadata["indexed_groups"] = list(indexed)
        metadata["index_stats"] = result
        metadata["last_indexed"] = datetime.utcnow().isoformat()
        save_session_metadata(req.session_id, metadata)
        
        return {
            "status": "success",
            "message": f"Indexed {result.get('indexed_docs', 0)} documents",
            "indexed_groups": groups_to_index,
            **result,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/index/stats/{session_id}")
def get_index_stats(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get indexing statistics for a session"""
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(session_id, current_user_id)
        stats = manager.get_index_stats()
        
        # Merge with session metadata
        indexed_groups = session_metadata.get("indexed_groups", [])
        last_indexed = session_metadata.get("last_indexed")
        
        return {
            "session_id": session_id,
            "document_count": stats.get("documents", 0),
            "indexed_groups": list(set(indexed_groups + stats.get("groups", []))),
            "last_indexed": last_indexed,
            "is_indexed": stats.get("documents", 0) > 0,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get index stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get index stats")


@router.delete("/index/{session_id}")
def clear_index(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Clear all indexed data for a session"""
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(session_id, current_user_id)
        manager.clear_index()
        
        # Update session metadata
        metadata = get_session_metadata(session_id)
        metadata["indexed_groups"] = []
        metadata["index_stats"] = {}
        save_session_metadata(session_id, metadata)
        
        return {"status": "success", "message": "Index cleared"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear index: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear index")


# ============================================================
# Auto-Indexing Endpoints
# ============================================================

@router.post("/auto-index/start")
async def start_auto_indexing(
    req: StartAutoIndexRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user),
):
    """
    Start auto-indexing for admin-configured groups.
    Called automatically after ZIP scan.
    """
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(req.session_id, current_user_id)
        
        if not manager.is_configured():
            return {
                "status": "not_configured",
                "message": "AI service not configured - auto-indexing skipped",
                "eligible_groups": [],
            }
        
        result = manager.start_auto_index(
            xml_inventory=req.xml_inventory,
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-indexing start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Auto-indexing failed: {str(e)}")


@router.get("/auto-index/progress/{session_id}", response_model=AutoIndexStatusResponse)
def get_auto_index_progress(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get current auto-indexing progress"""
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(session_id, current_user_id)
        progress = manager.get_auto_index_progress()
        
        return AutoIndexStatusResponse(
            session_id=session_id,
            progress=AutoIndexProgress(
                status=progress.status,
                progress=progress.progress,
                files_done=progress.files_done,
                files_total=progress.files_total,
                docs_done=progress.docs_done,
                current_file=progress.current_file,
                groups_done=progress.groups_done,
                error=progress.error,
            ),
            eligible_groups=progress.groups_done,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get auto-index progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to get progress")


@router.post("/auto-index/stop/{session_id}")
def stop_auto_indexing(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Stop ongoing auto-indexing"""
    from api.services.ai.session_manager import get_session_ai_manager
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(session_id, current_user_id)
        manager.auto_indexer.stop()
        
        return {"status": "success", "message": "Stop requested"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop auto-indexing: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop")


# ============================================================
# Admin Config Endpoints
# ============================================================

@router.get("/admin/auto-index-groups")
def get_admin_auto_index_groups(
    current_user_id: str = Depends(get_current_user),
):
    """Get admin-configured auto-index groups (count only, names hidden)"""
    prefs_path = Path(settings.RET_RUNTIME_ROOT) / "admin_prefs.json"
    
    if prefs_path.exists():
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
                groups = prefs.get("auto_index_groups", [])
                return {
                    "count": len(groups),
                    "configured": len(groups) > 0,
                }
        except Exception:
            pass
    
    return {"count": 0, "configured": False}


# ============================================================
# Transcript Download
# ============================================================

@router.post("/transcript/download")
def download_transcript(
    req: TranscriptRequest,
    current_user_id: str = Depends(get_current_user),
):
    """Download chat transcript in specified format"""
    from api.services.ai.session_manager import get_session_ai_manager
    from fastapi.responses import Response
    
    try:
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        manager = get_session_ai_manager(req.session_id, current_user_id)
        history = manager.get_chat_history(limit=1000)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        if req.format == TranscriptFormat.JSON:
            content = json.dumps(history, indent=2, ensure_ascii=False)
            filename = f"RET_transcript_{req.session_id}_{timestamp}.json"
            media_type = "application/json"
            
        elif req.format == TranscriptFormat.TXT:
            lines = []
            for msg in history:
                role = msg.get("role", "").upper()
                content_text = msg.get("content", "")
                ts = msg.get("timestamp", "")
                lines.append(f"[{ts}] {role}:")
                lines.append(content_text)
                lines.append("")
            content = "\n".join(lines)
            filename = f"RET_transcript_{req.session_id}_{timestamp}.txt"
            media_type = "text/plain"
            
        else:  # Markdown
            lines = ["# RET AI Chat Transcript", f"Session: {req.session_id}", f"Exported: {timestamp}", "", "---", ""]
            for msg in history:
                role = msg.get("role", "")
                content_text = msg.get("content", "")
                ts = msg.get("timestamp", "")
                
                if role == "user":
                    lines.append(f"## 👤 User ({ts})")
                else:
                    lines.append(f"## 🤖 Assistant ({ts})")
                
                lines.append("")
                lines.append(content_text)
                lines.append("")
                
                if req.include_sources and msg.get("sources"):
                    lines.append("**Sources:**")
                    for src in msg["sources"][:5]:
                        lines.append(f"- {src.get('source', 'unknown')}")
                    lines.append("")
                
                lines.append("---")
                lines.append("")
            
            content = "\n".join(lines)
            filename = f"RET_transcript_{req.session_id}_{timestamp}.md"
            media_type = "text/markdown"
        
        return Response(
            content=content.encode("utf-8"),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate transcript: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate transcript")


# ============================================================
# Session Cleanup (called on logout)
# ============================================================

@router.post("/cleanup/{session_id}")
def cleanup_ai_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Cleanup AI resources for a session (deletes vector DB)"""
    from api.services.ai.session_manager import cleanup_session_ai
    
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cleanup_session_ai(session_id, current_user_id)
        
        return {"status": "success", "message": "AI session cleaned up"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup AI session: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup")
