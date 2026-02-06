"""
Unified AI Router — /api/v2/ai

Single entry-point for all AI / RAG operations:
  - Status & configuration
  - Chat (with or without RAG retrieval)
  - Indexing (manual group selection + auto-index)
  - Embedding status per group
  - Transcript download
  - Session cleanup
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response

from api.core.config import settings
from api.core.dependencies import get_current_user_id
from api.services.storage_service import (
    get_session_dir,
    get_session_metadata,
    save_session_metadata,
)
from api.schemas.ai import (
    AutoIndexProgress,
    AutoIndexStatusResponse,
    GroupSelectionRequest,
    QueryTransformationInfo,
    RAGChatRequest,
    RAGChatResponse,
    SourceDocument,
    StartAutoIndexRequest,
    TranscriptFormat,
    TranscriptRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/ai", tags=["ai-v2"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _verify_session_owner(session_id: str, current_user_id: str) -> dict:
    """Verify the current user owns the session. Returns metadata."""
    meta = get_session_metadata(session_id)
    stored = meta.get("user_id", "")
    if stored and stored != current_user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return meta


def _get_manager(session_id: str, user_id: str):
    """Lazy import and return SessionAIManager."""
    from api.services.ai.session_manager import get_session_ai_manager

    return get_session_ai_manager(session_id, user_id)


# ==================================================================
# Status
# ==================================================================


@router.get("/status")
def get_ai_status(
    current_user_id: str = Depends(get_current_user_id),
):
    """Check AI service availability and configuration."""
    configured = bool(
        settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT
    )
    return {
        "status": "available" if configured else "not_configured",
        "configured": configured,
        "features": {
            "rag_chat": configured,
            "auto_indexing": configured,
            "embeddings": configured,
        },
        "settings": {
            "temperature": settings.RET_AI_TEMPERATURE,
            "chat_model": settings.AZURE_OPENAI_CHAT_MODEL,
            "embed_model": settings.AZURE_OPENAI_EMBED_MODEL,
        },
    }


@router.get("/config")
def get_ai_config(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get AI configuration (chunk sizes, retrieval top-k, etc.)."""
    return {
        "chunk_size": settings.CHUNK_TARGET_CHARS,
        "retrieval_top_k": settings.RAG_TOP_K_VECTOR,
        "temperature": settings.RET_AI_TEMPERATURE,
        "max_context_chars": settings.RAG_MAX_CONTEXT_CHARS,
        "hybrid_alpha": settings.RAG_VECTOR_WEIGHT,
        "hybrid_beta": settings.RAG_LEXICAL_WEIGHT,
    }


# ==================================================================
# Chat
# ==================================================================


@router.post("/chat", response_model=RAGChatResponse)
async def rag_chat(
    req: RAGChatRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Send a message and get RAG-powered response.

    Uses hybrid retrieval (vector + lexical) with citation-aware generation.
    """
    _verify_session_owner(req.session_id, current_user_id)

    query_text = req.message or req.question or ""
    if not query_text.strip():
        raise HTTPException(status_code=400, detail="No message provided")

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set Azure OpenAI credentials.",
        )

    try:
        result = manager.chat(
            message=query_text,
            use_rag=req.use_rag,
            group_filter=req.group_filter,
            top_k=req.top_k,
        )
    except Exception as e:
        logger.error("RAG chat failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")

    # Build response
    sources = [
        SourceDocument(
            file=src.get("file", src.get("source", "")),
            group=src.get("group"),
            snippet=(src.get("snippet", src.get("content", "")) or "")[:500],
            score=src.get("score"),
            chunk_index=src.get("chunk_index", i),
        )
        for i, src in enumerate(result.get("sources", []))
    ]

    # Map query transformation if present
    qt = result.get("query_transformation")
    qt_info = None
    if qt and isinstance(qt, dict):
        qt_info = QueryTransformationInfo(
            original=result.get("original_query", qt.get("original", "")),
            transformed=qt.get("transformed_query", ""),
            intent=qt.get("intent", "factual"),
            sub_queries=qt.get("sub_queries", []),
            keywords=qt.get("keywords", []),
        )

    return RAGChatResponse(
        answer=result.get("answer", ""),
        sources=sources,
        citations=result.get("citations", []),
        query_time_ms=result.get("query_time_ms", 0),
        chunks_retrieved=len(sources),
        response_type=result.get("response_type"),
        query_transformation=qt_info,
    )


@router.get("/chat/history/{session_id}")
def get_chat_history(
    session_id: str,
    limit: int = 50,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get conversation history for a session."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        history = manager.get_chat_history(limit=limit)
        return {
            "session_id": session_id,
            "messages": history,
            "count": len(history),
        }
    except Exception as e:
        logger.error("Failed to get chat history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get chat history")


@router.delete("/chat/history/{session_id}")
def clear_chat_history(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Clear conversation history for a session."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        manager.clear_chat_history()
        return {"status": "success", "message": "Chat history cleared"}
    except Exception as e:
        logger.error("Failed to clear chat history: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to clear chat history"
        )


# ==================================================================
# Indexing
# ==================================================================


@router.get("/index/groups")
def get_available_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    List groups available for indexing.

    Reads the conversion_index.json to find which groups have been
    converted to CSV.  Merges with embedding status from the vector store.
    """
    _verify_session_owner(session_id, current_user_id)

    session_dir = get_session_dir(session_id)

    # Try conversion_index first (post-conversion groups with CSVs)
    index_path = session_dir / "conversion_index.json"
    if not index_path.exists():
        # Fall back to xml_inventory (pre-conversion)
        index_path = session_dir / "xml_inventory.json"

    if not index_path.exists():
        return {
            "status": "no_inventory",
            "groups": [],
            "message": "No data found. Upload and scan a ZIP first.",
        }

    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "error", "groups": [], "message": "Failed to read inventory."}

    # Extract unique groups and file counts from conversion_index.json
    group_counts: Dict[str, int] = {}
    if isinstance(raw, dict):
        # Standard conversion_index.json format: {"groups": {"GRP": [...], ...}, "files": [...]}
        if "groups" in raw and isinstance(raw["groups"], dict):
            for grp_name, files_list in raw["groups"].items():
                group_counts[grp_name] = len(files_list) if isinstance(files_list, list) else 0
        elif "files" in raw and isinstance(raw["files"], list):
            for item in raw["files"]:
                if isinstance(item, dict):
                    grp = item.get("group", "MISC")
                    group_counts[grp] = group_counts.get(grp, 0) + 1
        else:
            # Legacy format: {filename: {group, ...}, ...}
            for _fname, info in raw.items():
                if isinstance(info, dict) and "group" in info:
                    grp = info["group"]
                    group_counts[grp] = group_counts.get(grp, 0) + 1
    elif isinstance(raw, list):
        # xml_inventory format: [{group, filename, ...}, ...]
        for item in raw:
            grp = item.get("group", "MISC") if isinstance(item, dict) else "MISC"
            group_counts[grp] = group_counts.get(grp, 0) + 1

    # Get embedding status from the vector store (if manager exists)
    embedding_status: Dict[str, Dict[str, Any]] = {}
    try:
        manager = _get_manager(session_id, current_user_id)
        embedding_status = manager.get_embedding_status()
    except Exception:
        pass  # No manager yet — that's fine

    groups_info = []
    for grp in sorted(group_counts):
        es = embedding_status.get(grp, {})
        groups_info.append({
            "name": grp,
            "file_count": group_counts[grp],
            "indexed": es.get("indexed", False),
            "chunk_count": es.get("chunk_count", 0),
        })

    return {
        "status": "success",
        "groups": groups_info,
        "total_groups": len(groups_info),
    }


@router.post("/index/groups")
async def index_selected_groups(
    req: GroupSelectionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Index selected groups.

    Reads converted CSV files from the session output directory and indexes
    them into ChromaDB for RAG retrieval.
    """
    _verify_session_owner(req.session_id, current_user_id)

    groups = req.selected_groups or req.groups or []
    if not groups:
        raise HTTPException(status_code=400, detail="No groups selected")

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")

    try:
        stats = manager.index_groups(groups=groups)

        return {
            "status": "success",
            "message": (
                f"Indexed {stats.indexed_chunks} chunks from "
                f"{stats.indexed_files} files"
            ),
            "indexed_groups": list(stats.groups_processed),
            "files_indexed": stats.indexed_files,
            "indexed_count": stats.indexed_files,
            "chunks_indexed": stats.indexed_chunks,
            "errors": stats.errors[:10],
        }
    except Exception as e:
        logger.error("Indexing failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")


@router.get("/index/status/{session_id}")
def get_embedding_status(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Get per-group embedding status from the vector store.

    Returns which groups are indexed and their chunk counts.
    Includes timeout protection to prevent hanging on slow Azure responses.
    """
    import signal
    from contextlib import contextmanager
    
    _verify_session_owner(session_id, current_user_id)

    @contextmanager
    def timeout_handler(seconds=5):
        """Context manager for operation timeout."""
        class TimeoutException(Exception):
            pass
        
        def signal_handler(signum, frame):
            raise TimeoutException("Operation timed out")
        
        # Note: signal.alarm only works on Unix. For Windows, we use a simpler approach
        old_handler = signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
        
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    
    try:
        manager = _get_manager(session_id, current_user_id)
        
        # Get status with attempt to handle slow responses
        try:
            status = manager.get_embedding_status()
            stats = manager.get_index_stats()
        except Exception as e:
            logger.warning(
                f"Error retrieving embedding status for {session_id}, "
                f"returning empty status: {e}"
            )
            # Return valid response even if status check fails
            return {
                "session_id": session_id,
                "groups": {},
                "total_chunks": 0,
                "total_groups": 0,
                "is_indexed": False,
                "status_error": "temporary",
                "message": "Status check encountered a temporary issue. Try again in a moment."
            }

        return {
            "session_id": session_id,
            "groups": status,
            "total_chunks": stats.get("total_chunks", 0),
            "total_groups": stats.get("total_groups", 0),
            "is_indexed": stats.get("total_chunks", 0) > 0,
        }
    except Exception as e:
        logger.error("Failed to get embedding status: %s", e)
        # Return 200 with error details instead of 500 to prevent frontend retry storms
        return {
            "session_id": session_id,
            "groups": {},
            "total_chunks": 0,
            "total_groups": 0,
            "is_indexed": False,
            "status_error": "critical",
            "detail": str(e)[:100],
        }


@router.get("/index/stats/{session_id}")
def get_index_stats(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get overall indexing statistics for a session."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        stats = manager.get_index_stats()
        return {"session_id": session_id, **stats}
    except Exception as e:
        logger.error("Failed to get index stats: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to get index stats"
        )


@router.delete("/index/{session_id}")
def clear_index(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Clear all indexed data for a session (keeps the session alive)."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        manager.clear_index()
        return {"status": "success", "message": "Index cleared"}
    except Exception as e:
        logger.error("Failed to clear index: %s", e)
        raise HTTPException(status_code=500, detail="Failed to clear index")


# ==================================================================
# Auto-Indexing
# ==================================================================


@router.post("/auto-index/start")
async def start_auto_indexing(
    req: StartAutoIndexRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Start auto-indexing for admin-configured groups.

    Called automatically after ZIP scan when auto-indexing is enabled.
    """
    _verify_session_owner(req.session_id, current_user_id)

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        return {
            "status": "not_configured",
            "message": "AI not configured — auto-indexing skipped",
            "eligible_groups": [],
        }

    try:
        result = manager.start_auto_index(xml_inventory=req.xml_inventory)
        return result
    except Exception as e:
        logger.error("Auto-indexing start failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Auto-indexing failed: {e}"
        )


@router.get(
    "/auto-index/progress/{session_id}",
    response_model=AutoIndexStatusResponse,
)
def get_auto_index_progress(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get current auto-indexing progress."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
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
    except Exception as e:
        logger.error("Failed to get auto-index progress: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get progress")


@router.post("/auto-index/stop/{session_id}")
def stop_auto_indexing(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Stop ongoing auto-indexing."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        manager.stop_auto_index()
        return {"status": "success", "message": "Stop requested"}
    except Exception as e:
        logger.error("Failed to stop auto-indexing: %s", e)
        raise HTTPException(status_code=500, detail="Failed to stop")


# ==================================================================
# Admin
# ==================================================================


@router.get("/admin/auto-index-groups")
def get_admin_auto_index_groups(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get admin-configured auto-index groups (count only)."""
    prefs_path = Path(settings.RET_RUNTIME_ROOT) / "admin_prefs.json"
    if prefs_path.exists():
        try:
            data = json.loads(prefs_path.read_text(encoding="utf-8"))
            groups = data.get("auto_index_groups", [])
            return {"count": len(groups), "configured": len(groups) > 0}
        except Exception:
            pass
    return {"count": 0, "configured": False}


# ==================================================================
# Transcript Download
# ==================================================================


@router.post("/transcript/download")
def download_transcript(
    req: TranscriptRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Download the chat transcript in JSON, TXT, or Markdown format."""
    _verify_session_owner(req.session_id, current_user_id)

    try:
        manager = _get_manager(req.session_id, current_user_id)
        history = manager.get_chat_history(limit=1000)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if req.format == TranscriptFormat.JSON:
            content = json.dumps(history, indent=2, ensure_ascii=False)
            filename = f"RET_transcript_{req.session_id}_{timestamp}.json"
            media_type = "application/json"

        elif req.format == TranscriptFormat.TXT:
            lines = []
            for msg in history:
                role = msg.get("role", "").upper()
                text = msg.get("content", "")
                ts = msg.get("timestamp", "")
                lines.append(f"[{ts}] {role}:")
                lines.append(text)
                lines.append("")
            content = "\n".join(lines)
            filename = f"RET_transcript_{req.session_id}_{timestamp}.txt"
            media_type = "text/plain"

        else:  # Markdown
            lines = [
                "# RET AI Chat Transcript",
                f"Session: {req.session_id}",
                f"Exported: {timestamp}",
                "",
                "---",
                "",
            ]
            for msg in history:
                role = msg.get("role", "")
                text = msg.get("content", "")
                ts = msg.get("timestamp", "")
                header = "User" if role == "user" else "Assistant"
                lines.append(f"## {header} ({ts})")
                lines.append("")
                lines.append(text)
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
            },
        )
    except Exception as e:
        logger.error("Failed to generate transcript: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to generate transcript"
        )


# ==================================================================
# Session Cleanup
# ==================================================================


@router.post("/cleanup/{session_id}")
def cleanup_ai_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Cleanup AI resources for a session (deletes vector store)."""
    _verify_session_owner(session_id, current_user_id)

    try:
        from api.services.ai.session_manager import cleanup_session_ai

        cleanup_session_ai(session_id, current_user_id)
        return {"status": "success", "message": "AI session cleaned up"}
    except Exception as e:
        logger.error("Failed to cleanup AI session: %s", e)
        raise HTTPException(status_code=500, detail="Failed to cleanup")
