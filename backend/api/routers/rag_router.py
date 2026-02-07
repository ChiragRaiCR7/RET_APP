"""
Unified AI Router — /api/v2/ai

Single entry-point for all AI / RAG operations:
  - Status & configuration
  - Chat (with or without RAG retrieval)
  - Embedding (manual group selection + auto-embed)
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
    AutoEmbedProgress,
    AutoEmbedStatusResponse,
    FeedbackRequest,
    FeedbackResponse,
    GroupSelectionRequest,
    QueryTransformationInfo,
    RAGChatRequest,
    RAGChatResponse,
    RAGConfigResponse,
    SourceDocument,
    StartAutoEmbedRequest,
    TranscriptFormat,
    TranscriptRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/ai", tags=["ai-v2"])


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
            "auto_embedding": configured,
            "embeddings": configured,
        },
        "settings": {
            "temperature": settings.RET_AI_TEMPERATURE,
            "chat_model": settings.AZURE_OPENAI_CHAT_MODEL,
            "embed_model": settings.AZURE_OPENAI_EMBED_MODEL,
        },
    }


@router.get("/config", response_model=RAGConfigResponse)
def get_ai_config(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get AI configuration (chunk sizes, retrieval top-k, etc.)."""
    return RAGConfigResponse(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        max_context_chars=settings.RAG_MAX_CONTEXT_CHARS,
        max_chunks=settings.RAG_MAX_CHUNKS,
        vector_weight=settings.RAG_VECTOR_WEIGHT,
        lexical_weight=settings.RAG_LEXICAL_WEIGHT,
        summary_weight=settings.RAG_SUMMARY_WEIGHT,
        top_k_vector=settings.RAG_TOP_K_VECTOR,
        top_k_summary=settings.RAG_TOP_K_SUMMARY,
        enable_query_transform=settings.RAG_ENABLE_QUERY_TRANSFORM,
        enable_summaries=settings.RAG_ENABLE_SUMMARIES,
        enable_citation_repair=getattr(settings, "RAG_ENABLE_CITATION_REPAIR", True),
        rrf_k=settings.RAG_RRF_K,
    )


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
        visualizations=result.get("visualizations", []),
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


@router.get("/embedding/groups")
def get_available_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    List groups available for **manual** embedding by the user.

    Groups that have already been auto-embedded by the admin configuration
    are excluded from the returned list so the user only sees the ones
    they still need to choose from.

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
            "auto_embedded_groups": [],
            "message": "No data found. Upload and scan a ZIP first.",
        }

    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "error", "groups": [], "auto_embedded_groups": [], "message": "Failed to read inventory."}

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
    auto_embedded: List[str] = []
    try:
        manager = _get_manager(session_id, current_user_id)
        embedding_status = manager.get_embedding_status()
        auto_embedded = [g.upper() for g in manager.auto_embedded_groups]
    except Exception:
        pass  # No manager yet — that's fine

    groups_info = []
    for grp in sorted(group_counts):
        es = embedding_status.get(grp, {})
        is_auto = grp.upper() in auto_embedded
        groups_info.append({
            "name": grp,
            "file_count": group_counts[grp],
            "indexed": es.get("indexed", False),
            "chunk_count": es.get("chunk_count", 0),
            "auto_embedded": is_auto,
        })

    # For the user selection UI, filter out auto-embedded groups
    user_selectable = [g for g in groups_info if not g["auto_embedded"]]

    return {
        "status": "success",
        "groups": user_selectable,
        "all_groups": groups_info,
        "auto_embedded_groups": auto_embedded,
        "total_groups": len(groups_info),
    }


@router.post("/embedding/groups")
async def embed_selected_groups(
    req: GroupSelectionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Embed user-selected groups.

    Groups that were already auto-embedded by the admin configuration are
    silently skipped so they are not re-embedded.

    Reads converted CSV files from the session output directory and embeds
    them into ChromaDB for RAG retrieval.
    """
    _verify_session_owner(req.session_id, current_user_id)

    groups = req.selected_groups or req.groups or []
    if not groups:
        raise HTTPException(status_code=400, detail="No groups selected")

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")

    # Filter out groups that were already auto-embedded
    auto_embedded = {g.upper() for g in manager.auto_embedded_groups}
    groups_to_embed = [g for g in groups if g.upper() not in auto_embedded]
    skipped = [g for g in groups if g.upper() in auto_embedded]

    if not groups_to_embed:
        return {
            "status": "success",
            "message": "All selected groups are already auto-embedded.",
            "embedded_groups": [],
            "skipped_groups": skipped,
            "files_embedded": 0,
            "embedded_count": 0,
            "chunks_embedded": 0,
            "errors": [],
        }

    # Background mode: queue a task and return immediately
    if req.background:
        try:
            from api.workers.embedding_worker import get_embedding_worker
            from api.services.storage_service import get_session_dir
            import uuid

            session_dir = get_session_dir(req.session_id)
            csv_dir = session_dir / "output"

            worker = get_embedding_worker()
            task = worker.submit_task(
                task_id=f"manual_embed_{req.session_id}_{uuid.uuid4().hex[:8]}",
                session_id=req.session_id,
                user_id=current_user_id,
                groups=groups_to_embed,
                csv_dir=csv_dir,
                rag_service=manager.rag_service,
                admin_config=None,
                enforce_admin_filter=False,
                callback=None,
            )

            return {
                "status": "queued",
                "message": "Embedding task queued",
                "task_id": task.task_id,
                "queued_groups": list(groups_to_embed),
                "skipped_groups": skipped,
            }
        except Exception as e:
            logger.error("Failed to queue embedding task: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to queue embedding task: {e}")

    try:
        stats = manager.embed_groups(groups=groups_to_embed)

        return {
            "status": "success",
            "message": (
                f"Embedded {stats.indexed_chunks} chunks from "
                f"{stats.indexed_files} files, "
                f"{stats.indexed_docs} documents"
            ),
            "embedded_groups": list(stats.groups_processed),
            "skipped_groups": skipped,
            "files_embedded": stats.indexed_files,
            "embedded_count": stats.indexed_files,
            "docs_embedded": stats.indexed_docs,
            "chunks_embedded": stats.indexed_chunks,
            "errors": stats.errors[:10],
        }
    except Exception as e:
        logger.error("Embedding failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")


@router.get("/embedding/tasks/{task_id}")
def get_embedding_task_status(
    task_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get status for a specific embedding task."""
    try:
        from api.workers.embedding_worker import get_embedding_worker

        worker = get_embedding_worker()
        task = worker.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Security: only allow the owner to view the task
        if task.user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        return task.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get embedding task status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get task status")


@router.get("/embedding/tasks")
def list_embedding_tasks(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """List all embedding tasks for a session."""
    try:
        from api.workers.embedding_worker import get_embedding_worker

        worker = get_embedding_worker()
        tasks = worker.get_session_tasks(session_id)

        # Filter by user ownership
        visible = [t.to_dict() for t in tasks if t.user_id == current_user_id]

        return {
            "session_id": session_id,
            "count": len(visible),
            "tasks": visible,
        }
    except Exception as e:
        logger.error("Failed to list embedding tasks: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list tasks")


@router.get("/embedding/status/{session_id}")
def get_embedding_status(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Get per-group embedding status from the vector store.

    Returns which groups are indexed and their chunk counts.
    """
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)

        try:
            status = manager.get_embedding_status()
            stats = manager.get_index_stats()
        except AttributeError as e:
            logger.error(
                "Method missing in SessionAIManager: %s. "
                "This indicates a code version mismatch.",
                str(e)
            )
            return {
                "session_id": session_id,
                "groups": {},
                "total_chunks": 0,
                "total_groups": 0,
                "is_indexed": False,
                "status_error": "configuration",
                "message": "AI service initialization error. Please restart the application.",
            }
        except Exception as e:
            logger.warning(
                "Error retrieving embedding status for %s: %s",
                session_id, str(e),
            )
            return {
                "session_id": session_id,
                "groups": {},
                "total_chunks": 0,
                "total_groups": 0,
                "is_indexed": False,
                "status_error": "temporary",
                "message": "Status check encountered a temporary issue. Try again.",
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
        return {
            "session_id": session_id,
            "groups": {},
            "total_chunks": 0,
            "total_groups": 0,
            "is_indexed": False,
            "status_error": "critical",
            "detail": str(e)[:100],
        }


@router.get("/embedding/stats/{session_id}")
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


@router.delete("/embedding/{session_id}")
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
# Auto-Embedding
# ==================================================================


@router.post("/auto-embed/start")
async def start_auto_embedding(
    req: StartAutoEmbedRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Start auto-embedding for admin-configured groups.

    Called automatically after ZIP scan when auto-embedding is enabled.
    """
    _verify_session_owner(req.session_id, current_user_id)

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        return {
            "status": "not_configured",
            "message": "AI not configured — auto-embedding skipped",
            "eligible_groups": [],
        }

    try:
        result = manager.start_auto_embed(xml_inventory=req.xml_inventory)
        return result
    except Exception as e:
        logger.error("Auto-embedding start failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Auto-embedding failed: {e}"
        )


@router.get(
    "/auto-embed/progress/{session_id}",
    response_model=AutoEmbedStatusResponse,
)
def get_auto_embed_progress(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get current auto-embedding progress."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        progress = manager.get_auto_embed_progress()

        return AutoEmbedStatusResponse(
            session_id=session_id,
            progress=AutoEmbedProgress(
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
        logger.error("Failed to get auto-embed progress: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get progress")


@router.post("/auto-embed/stop/{session_id}")
def stop_auto_embedding(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Stop ongoing auto-embedding."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        manager.stop_auto_embed()
        return {"status": "success", "message": "Stop requested"}
    except Exception as e:
        logger.error("Failed to stop auto-embedding: %s", e)
        raise HTTPException(status_code=500, detail="Failed to stop")


# ==================================================================
# Admin
# ==================================================================


@router.get("/admin/auto-embed-groups")
def get_admin_auto_embed_groups(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get admin-configured auto-embed groups."""
    # Check admin_prefs.json (used by AutoEmbedder)
    prefs_path = Path(settings.RET_RUNTIME_ROOT) / "admin_prefs.json"
    if prefs_path.exists():
        try:
            data = json.loads(prefs_path.read_text(encoding="utf-8"))
            groups = data.get("auto_embedded_groups", [])
            return {"count": len(groups), "configured": len(groups) > 0, "groups": groups}
        except Exception:
            pass

    # Also check AI config (used by conversion auto-embed)
    try:
        from api.services.admin_service import get_ai_indexing_config_data
        ai_config = get_ai_indexing_config_data()
        groups = ai_config.get("auto_indexed_groups", [])
        enabled = ai_config.get("enable_auto_indexing", False)
        return {"count": len(groups), "configured": enabled and len(groups) > 0, "groups": groups}
    except Exception:
        pass

    return {"count": 0, "configured": False, "groups": []}


@router.get("/admin/worker-status")
def get_worker_status(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get embedding worker status for debugging and monitoring."""
    try:
        from api.workers.embedding_worker import get_embedding_worker

        worker = get_embedding_worker()
        
        # Check if worker thread is running
        is_running = worker._worker_thread is not None and worker._worker_thread.is_alive()
        
        # Get task statistics
        with worker._lock:
            tasks = list(worker._tasks.values())
            pending = sum(1 for t in tasks if t.status == "pending")
            running = sum(1 for t in tasks if t.status == "running")
            completed = sum(1 for t in tasks if t.status == "completed")
            failed = sum(1 for t in tasks if t.status == "failed")
        
        return {
            "worker_running": is_running,
            "total_tasks": len(tasks),
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "max_workers": worker.max_workers,
            "batch_size": worker.batch_size,
            "message": "Worker starts automatically when tasks are submitted" if not is_running else "Worker is active",
        }
    except Exception as e:
        logger.error("Failed to get worker status: %s", e)
        return {
            "worker_running": False,
            "error": str(e),
        }


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
# Feedback
# ==================================================================


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    req: FeedbackRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Record user feedback (thumbs up/down) on a RAG response."""
    _verify_session_owner(req.session_id, current_user_id)

    try:
        manager = _get_manager(req.session_id, current_user_id)
        # Store feedback in session metadata for analytics
        meta = get_session_metadata(req.session_id)
        feedback_log = meta.get("feedback", [])
        feedback_log.append({
            "message_index": req.message_index,
            "rating": req.rating,
            "comment": req.comment,
            "user_id": current_user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        meta["feedback"] = feedback_log
        save_session_metadata(req.session_id, meta)

        return FeedbackResponse(status="ok", message="Feedback recorded")
    except Exception as e:
        logger.error("Failed to record feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to record feedback")


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
