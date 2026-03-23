
"""
Unified AI Router — /api/v2/ai

Single entry-point for all AI / RAG operations:
  - Status & configuration
  - Chat (with or without RAG retrieval)
  - Embedding (manual group selection)
  - Embedding status per group
  - Transcript download
  - Session cleanup

NOTE: Manual embedding is primary. Legacy auto-embed endpoints are retained for
frontend compatibility and map to SessionAIManager auto-embed controls.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from api.core.config import settings
from api.core.dependencies import get_current_user_id
from api.services.storage_service import (
    get_session_dir,
    get_session_metadata,
    save_session_metadata,
)
from api.schemas.ai import (
    FeedbackRequest,
    FeedbackResponse,
    GroupSelectionRequest,
    HITLResumeRequest,
    HITLResumeResponse,
    QueryTransformationInfo,
    RAGChatRequest,
    RAGChatResponse,
    RAGConfigResponse,
    SourceDocument,
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
    stored = meta.get("user_id")
    if not stored or stored != current_user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return meta


def _get_manager(session_id: str, user_id: str):
    """Lazy import and return SessionAIManager."""
    from api.services.ai.session_manager import get_session_ai_manager
    return get_session_ai_manager(session_id, user_id)


def _load_xml_inventory(session_dir: Path, fallback_raw: Any = None) -> List[Dict[str, Any]]:
    """Load xml inventory from disk, with best-effort fallbacks."""
    inventory_path = session_dir / "xml_inventory.json"

    if inventory_path.exists():
        try:
            data = json.loads(inventory_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict) and "files" in data and isinstance(data["files"], list):
                return [x for x in data["files"] if isinstance(x, dict)]
        except Exception:
            pass

    # Fallback from conversion index style payload
    if isinstance(fallback_raw, dict):
        files = fallback_raw.get("files")
        if isinstance(files, list):
            return [x for x in files if isinstance(x, dict)]

    if isinstance(fallback_raw, list):
        return [x for x in fallback_raw if isinstance(x, dict)]

    return []


# ==================================================================
# Status
# ==================================================================

@router.get("/status")
async def get_ai_status(
    current_user_id: str = Depends(get_current_user_id),
):
    """Check AI service availability and configuration."""
    configured = bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT)
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
async def get_ai_config(
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
    from api.utils.metrics import timed_block

    with timed_block("rag_chat_endpoint", extra={"session_id": req.session_id}):
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
            result = await manager.chat_async(
                message=query_text,
                use_rag=req.use_rag,
                group_filter=req.group_filter,
                top_k=req.top_k,
                thread_id=req.thread_id or "",
            )
        except Exception as e:
            logger.error("RAG chat failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Chat failed: {e}")

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

        qt = result.get("query_transformation")
        qt_info = None
        if qt and isinstance(qt, dict):
            # Filter out None values from filters dict — Pydantic expects Dict[str, str]
            raw_filters = qt.get("filters") or {}
            if not isinstance(raw_filters, dict):
                raw_filters = {}

            sub_queries = qt.get("sub_queries", [])
            if not isinstance(sub_queries, list):
                sub_queries = []

            keywords = qt.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []

            clean_filters = {str(k): str(v) for k, v in raw_filters.items() if v is not None}
            qt_info = QueryTransformationInfo(
                original=result.get("original_query", qt.get("original", "")),
                transformed=qt.get("transformed_query", ""),
                intent=qt.get("intent", "factual"),
                sub_queries=[str(x) for x in sub_queries if x is not None],
                keywords=[str(x) for x in keywords if x is not None],
                filters=clean_filters,
            )

        return RAGChatResponse(
            answer=result.get("answer", ""),
            sources=sources,
            citations=result.get("citations", []),
            query_time_ms=result.get("query_time_ms", 0),
            query_plan=result.get("query_plan"),
            chunks_retrieved=len(sources),
            response_type=result.get("response_type"),
            query_transformation=qt_info,
            visualizations=result.get("visualizations", []),
            retrieval_metadata=result.get("retrieval_metadata"),
        )


# ==================================================================
# Streaming Chat
# ==================================================================

@router.post("/chat/stream")
async def rag_chat_stream(
    req: RAGChatRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Streaming RAG chat endpoint via Server-Sent Events (SSE).

    Requires ``FEATURE_CHAT_STREAMING=true``.  Falls back to a single
    ``done`` event containing the full response when the flag is off.

    SSE event types:
    - ``node_start`` / ``node_end`` — pipeline progress
    - ``token`` — incremental LLM output
    - ``sources`` — retrieved source documents
    - ``citations`` — citation references
    - ``metadata`` — timing, query transform info
    - ``done`` — final payload with complete answer
    - ``error`` — on failure
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

    return StreamingResponse(
        manager.chat_stream(
            message=query_text,
            group_filter=req.group_filter,
            top_k=req.top_k,
            thread_id=req.thread_id or "",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================================================================
# HITL Resume
# ==================================================================

@router.post("/chat/resume", response_model=HITLResumeResponse)
async def rag_chat_resume(
    req: HITLResumeRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Resume a HITL-interrupted chat execution.

    Requires ``FEATURE_HITL_ENABLED=true`` and active checkpointing.

    The frontend calls this after receiving an ``hitl_required`` SSE event
    and collecting the reviewer's decision.
    """
    _verify_session_owner(req.session_id, current_user_id)

    if not getattr(settings, "FEATURE_HITL_ENABLED", False):
        raise HTTPException(status_code=400, detail="HITL is not enabled")

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured.",
        )

    try:
        result = await manager.resume_hitl(
            thread_id=req.thread_id,
            decision=req.decision,
            edited_answer=req.edited_answer or "",
        )
    except Exception as e:
        logger.error("HITL resume failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")

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

    return HITLResumeResponse(
        answer=result.get("answer", ""),
        sources=sources,
        citations=result.get("citations", []),
        query_time_ms=result.get("query_time_ms", 0),
        hitl_decision=result.get("hitl_decision", req.decision),
        error=result.get("error", False),
        response_type=result.get("response_type"),
    )


@router.get("/chat/history/{session_id}")
async def get_chat_history(
    session_id: str,
    limit: int = 50,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get conversation history for a session."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        history = await asyncio.to_thread(manager.get_chat_history, limit=limit)
        return {
            "session_id": session_id,
            "messages": history,
            "history": history,
            "count": len(history),
        }
    except Exception as e:
        logger.error("Failed to get chat history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get chat history")


@router.delete("/chat/history/{session_id}")
async def clear_chat_history(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Clear conversation history for a session."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        await asyncio.to_thread(manager.clear_chat_history)
        return {"status": "success", "message": "Chat history cleared"}
    except Exception as e:
        logger.error("Failed to clear chat history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to clear chat history")


# ==================================================================
# Indexing (Manual Embedding Only)
# ==================================================================

@router.get("/embedding/groups")
async def get_available_groups(
    session_id: str,
    eligible_only: bool = Query(False, description="Return only auto-embed eligible groups"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    List groups available for manual embedding by the user.

    Reads conversion_index.json (post-conversion) or xml_inventory.json (pre-conversion)
    and merges with embedding status from the vector store.
    """
    _verify_session_owner(session_id, current_user_id)
    session_dir = get_session_dir(session_id)

    index_path = session_dir / "conversion_index.json"
    if not index_path.exists():
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

    group_counts: Dict[str, int] = {}

    if isinstance(raw, dict):
        if "groups" in raw and isinstance(raw["groups"], dict):
            for grp_name, files_list in raw["groups"].items():
                group_counts[grp_name] = len(files_list) if isinstance(files_list, list) else 0
        elif "files" in raw and isinstance(raw["files"], list):
            for item in raw["files"]:
                if isinstance(item, dict):
                    grp = item.get("group", "MISC")
                    group_counts[grp] = group_counts.get(grp, 0) + 1
        else:
            for _fname, info in raw.items():
                if isinstance(info, dict) and "group" in info:
                    grp = info["group"]
                    group_counts[grp] = group_counts.get(grp, 0) + 1
    elif isinstance(raw, list):
        for item in raw:
            grp = item.get("group", "MISC") if isinstance(item, dict) else "MISC"
            group_counts[grp] = group_counts.get(grp, 0) + 1

    embedding_status: Dict[str, Dict[str, Any]] = {}
    excluded_groups: List[str] = []
    excluded_set: set[str] = set()

    try:
        from api.services.admin_service import get_ai_indexing_config_data

        cfg = get_ai_indexing_config_data() or {}
        excluded_groups = [str(g).strip().upper() for g in (cfg.get("excluded_groups") or []) if str(g).strip()]
        excluded_set = set(excluded_groups)
    except Exception:
        excluded_groups = []
        excluded_set = set()

    manager = None
    try:
        manager = _get_manager(session_id, current_user_id)
        embedding_status = manager.get_embedding_status()
    except Exception:
        pass

    auto_embedded_groups: List[str] = []
    eligible_set = None
    try:
        if manager:
            auto_embedded_groups = manager.auto_embedded_groups
            if eligible_only:
                xml_inventory = _load_xml_inventory(session_dir, raw)
                eligible = manager.auto_embedder.detect_eligible_groups(xml_inventory)
                eligible_set = {g.upper() for g in eligible}
    except Exception:
        # keep response resilient when auto-embed metadata isn't available
        pass

    groups_info = []
    for grp in sorted(group_counts):
        is_excluded = grp.upper() in excluded_set
        if eligible_set is not None and grp.upper() not in eligible_set:
            continue
        if is_excluded:
            # Excluded groups are hidden from eligible-only responses.
            if eligible_only:
                continue

        es = embedding_status.get(grp, {})
        groups_info.append({
            "name": grp,
            "file_count": group_counts[grp],
            "fileCount": group_counts[grp],
            "indexed": es.get("indexed", False),
            "chunk_count": es.get("chunk_count", 0),
            "excluded_by_admin": is_excluded,
        })

    return {
        "status": "success",
        "groups": groups_info,
        "all_groups": groups_info,
        "auto_embedded_groups": auto_embedded_groups,
        "excluded_groups": sorted(excluded_set),
        "total_groups": len(groups_info),
    }


@router.post("/embedding/groups")
async def embed_selected_groups(
    req: GroupSelectionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Embed user-selected groups (manual embedding).

    Reads converted CSV files from the session output directory and embeds
    them into the vector store for RAG retrieval.

    Supports background embedding via embedding_worker when req.background=True.
    """
    _verify_session_owner(req.session_id, current_user_id)

    groups = req.selected_groups or req.groups or []
    if not groups:
        raise HTTPException(status_code=400, detail="No groups selected")

    excluded_set: set[str] = set()
    try:
        from api.services.admin_service import get_ai_indexing_config_data

        cfg = get_ai_indexing_config_data() or {}
        excluded_set = {
            str(g).strip().upper()
            for g in (cfg.get("excluded_groups") or [])
            if str(g).strip()
        }
    except Exception:
        excluded_set = set()

    groups_to_embed = [g for g in groups if str(g).strip().upper() not in excluded_set]
    skipped_excluded = [g for g in groups if str(g).strip().upper() in excluded_set]
    if not groups_to_embed:
        raise HTTPException(
            status_code=400,
            detail="Selected groups are excluded by admin and cannot be embedded",
        )

    manager = _get_manager(req.session_id, current_user_id)

    if not manager.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")

    suppression_cleared = False
    try:
        if manager.is_auto_embed_suppressed:
            manager.clear_auto_embed_suppression()
            suppression_cleared = True
    except Exception as e:
        logger.warning("Failed to clear auto-embed suppression for session %s: %s", req.session_id, e)

    # Background mode: queue a task and return immediately
    if req.background:
        try:
            from api.workers.embedding_worker import get_embedding_worker
            from api.services.storage_service import get_session_dir
            import uuid

            session_dir = get_session_dir(req.session_id)
            csv_dir = session_dir / "output"

            worker = await get_embedding_worker()
            task = await worker.submit_task(
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
                "skipped_excluded_groups": skipped_excluded,
                "auto_embed_suppression_cleared": suppression_cleared,
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
            "files_embedded": stats.indexed_files,
            "embedded_count": stats.indexed_files,
            "docs_embedded": stats.indexed_docs,
            "chunks_embedded": stats.indexed_chunks,
            "errors": stats.errors[:10],
            "skipped_excluded_groups": skipped_excluded,
            "auto_embed_suppression_cleared": suppression_cleared,
        }
    except Exception as e:
        logger.error("Embedding failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")


@router.get("/embedding/tasks/{task_id}")
async def get_embedding_task_status(
    task_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get status for a specific embedding task."""
    try:
        from api.workers.embedding_worker import get_embedding_worker

        worker = await get_embedding_worker()
        task = await worker.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        return task.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get embedding task status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get task status")


@router.get("/embedding/tasks")
async def list_embedding_tasks(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """List all embedding tasks for a session."""
    try:
        from api.workers.embedding_worker import get_embedding_worker

        worker = await get_embedding_worker()
        tasks = await worker.get_session_tasks(session_id)
        visible = [t.to_dict() for t in tasks if t.user_id == current_user_id]

        return {"session_id": session_id, "count": len(visible), "tasks": visible}
    except Exception as e:
        logger.error("Failed to list embedding tasks: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list tasks")


@router.get("/embedding/status/{session_id}")
async def get_embedding_status(
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
                "Method missing in SessionAIManager: %s. Code version mismatch.",
                str(e),
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
            logger.warning("Error retrieving embedding status for %s: %s", session_id, str(e))
            return {
                "session_id": session_id,
                "groups": {},
                "total_chunks": 0,
                "total_groups": 0,
                "is_indexed": False,
                "status_error": "temporary",
                "message": "Status check encountered a temporary issue. Try again.",
            }

        total_chunks = stats.get("total_chunks", 0)
        total_documents = stats.get("documents", 0)
        return {
            "session_id": session_id,
            "groups": status,
            "total_chunks": total_chunks,
            "total_documents": total_documents,
            "documents": total_documents,
            "total_groups": stats.get("total_groups", 0),
            "is_indexed": total_chunks > 0,
        }
    except Exception as e:
        logger.error("Failed to get embedding status: %s", e)
        return {
            "session_id": session_id,
            "groups": {},
            "total_chunks": 0,
            "total_documents": 0,
            "documents": 0,
            "total_groups": 0,
            "is_indexed": False,
            "status_error": "critical",
            "detail": str(e)[:100],
        }


@router.get("/embedding/stats/{session_id}")
async def get_index_stats(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get overall indexing statistics for a session."""
    _verify_session_owner(session_id, current_user_id)

    try:
        manager = _get_manager(session_id, current_user_id)
        stats = manager.get_index_stats()
        payload = {"session_id": session_id, **stats}
        if "documents" in payload and "total_documents" not in payload:
            payload["total_documents"] = payload["documents"]
        return payload
    except Exception as e:
        logger.error("Failed to get index stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get index stats")


@router.delete("/embedding/{session_id}")
async def clear_index(
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
# Auto-Embedding (Compatibility Endpoints)
# ==================================================================

@router.post("/auto-embed/start")
async def start_auto_embed(
    body: Dict[str, Any],
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Compatibility endpoint for legacy auto-embed UI flows.

    Request body supports:
      - session_id (required)
      - xml_inventory (optional)
    """
    session_id = str(body.get("session_id", "")).strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    _verify_session_owner(session_id, current_user_id)

    manager = _get_manager(session_id, current_user_id)
    if not manager.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")

    try:
        if manager.is_auto_embed_suppressed:
            await asyncio.to_thread(manager.clear_auto_embed_suppression)
    except Exception as e:
        logger.warning("Failed to clear auto-embed suppression for session %s: %s", session_id, e)

    session_dir = get_session_dir(session_id)
    xml_inventory = body.get("xml_inventory")
    if not isinstance(xml_inventory, list):
        xml_inventory = _load_xml_inventory(session_dir)

    result = await asyncio.to_thread(manager.start_auto_embed, xml_inventory)
    started = result.get("status") == "started"

    return {
        "started": started,
        "status": result.get("status", "idle"),
        "eligible_groups": result.get("eligible_groups", []),
        "message": result.get("message", ""),
    }


@router.get("/auto-embed/progress/{session_id}")
async def get_auto_embed_progress(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Compatibility endpoint for auto-embed progress polling."""
    _verify_session_owner(session_id, current_user_id)

    manager = _get_manager(session_id, current_user_id)
    progress = await asyncio.to_thread(manager.get_auto_embed_progress)

    raw_status = getattr(progress, "status", "idle") or "idle"
    status = "embedding" if raw_status in ("preparing", "embedding") else raw_status

    files_done = int(getattr(progress, "files_done", 0) or 0)
    files_total = int(getattr(progress, "files_total", 0) or 0)
    docs_done = int(getattr(progress, "docs_done", 0) or 0)
    chunks_done = int(getattr(progress, "chunks_done", 0) or 0)
    groups_done = list(getattr(progress, "groups_done", []) or [])
    elapsed_seconds = float(getattr(progress, "elapsed_seconds", 0.0) or 0.0)

    # Per-group persistent status from Phase 2.5 callback
    group_status = await asyncio.to_thread(manager.get_embed_group_status)

    return {
        "status": status,
        "processed": files_done,
        "total": files_total,
        "current_file": getattr(progress, "current_file", "") or "",
        "current_group_index": len(groups_done),
        "groups": manager.auto_embedded_groups or groups_done,
        "group_status": group_status,
        "stats": {
            "totalDocuments": docs_done,
            "totalChunks": chunks_done,
        },
        "error": getattr(progress, "error", None),
        "duration": int(elapsed_seconds * 1000),
    }


@router.get("/embedding/group-status/{session_id}")
async def get_embedding_group_status(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Return per-group embedding status (queued / embedding / completed / failed).

    Reads persistent metadata written by auto-embedder group callbacks.
    """
    _verify_session_owner(session_id, current_user_id)

    manager = _get_manager(session_id, current_user_id)
    group_status = await asyncio.to_thread(manager.get_embed_group_status)

    return {
        "session_id": session_id,
        "group_status": group_status,
        "total_groups": len(group_status),
        "completed": sum(1 for g in group_status.values() if g.get("status") == "completed"),
        "failed": sum(1 for g in group_status.values() if g.get("status") == "failed"),
    }


@router.post("/auto-embed/stop/{session_id}")
async def stop_auto_embed(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Stop ALL embedding for a session (both auto-embed and manual worker tasks)."""
    _verify_session_owner(session_id, current_user_id)

    manager = _get_manager(session_id, current_user_id)
    stop_result = await manager.stop_all_embedding(
        suppress_auto_start=True,
        reason="Stopped by user",
        source=current_user_id,
    )

    return {
        "stopped": True,
        "status": "idle",
        "message": "All embedding stopped. Auto-embedding is suppressed for this session until manually resumed.",
        "worker_tasks_cancelled": int(stop_result.get("worker_tasks_cancelled", 0) or 0),
        "auto_embed_suppressed": bool(stop_result.get("auto_embed_suppressed", False)),
    }


# ==================================================================
# SSE Progress Streams (replaces polling for real-time progress)
# ==================================================================


@router.get("/auto-embed/progress/{session_id}/stream")
async def stream_auto_embed_progress(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    SSE stream that pushes auto-embed progress until completion.

    Replaces the 1.5 s polling pattern in AutoEmbedProgress.vue.
    Clients should fall back to the polling GET endpoint if SSE
    is not supported or the connection drops.

    Event types:
      - ``progress`` — full progress snapshot (same shape as polling response)
      - ``done`` — terminal event when embedding finishes or fails
    """
    import json as _json

    _verify_session_owner(session_id, current_user_id)

    async def _generator():
        manager = _get_manager(session_id, current_user_id)
        terminal = {"completed", "failed", "idle", "stopped"}
        max_ticks = 600  # ~5 min at 500 ms

        for _ in range(max_ticks):
            try:
                progress = await asyncio.to_thread(manager.get_auto_embed_progress)
                raw_status = getattr(progress, "status", "idle") or "idle"
                status = "embedding" if raw_status in ("preparing", "embedding") else raw_status

                files_done = int(getattr(progress, "files_done", 0) or 0)
                files_total = int(getattr(progress, "files_total", 0) or 0)
                docs_done = int(getattr(progress, "docs_done", 0) or 0)
                chunks_done = int(getattr(progress, "chunks_done", 0) or 0)
                groups_done = list(getattr(progress, "groups_done", []) or [])
                elapsed = float(getattr(progress, "elapsed_seconds", 0.0) or 0.0)

                group_status = await asyncio.to_thread(manager.get_embed_group_status)

                payload = {
                    "status": status,
                    "processed": files_done,
                    "total": files_total,
                    "current_file": getattr(progress, "current_file", "") or "",
                    "current_group_index": len(groups_done),
                    "groups": manager.auto_embedded_groups or groups_done,
                    "group_status": group_status,
                    "stats": {
                        "totalDocuments": docs_done,
                        "totalChunks": chunks_done,
                    },
                    "error": getattr(progress, "error", None),
                    "duration": int(elapsed * 1000),
                }

                event_name = "done" if status in terminal else "progress"
                yield f"event: {event_name}\ndata: {_json.dumps(payload, default=str)}\n\n"

                if status in terminal:
                    return

            except Exception as exc:
                yield f"event: error\ndata: {_json.dumps({'detail': str(exc)})}\n\n"
                return

            await asyncio.sleep(0.5)

        # Max ticks reached
        yield 'event: done\ndata: {"status":"timeout"}\n\n'

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/embedding/tasks/{task_id}/stream")
async def stream_embedding_task_progress(
    task_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    SSE stream for a specific embedding task's progress.

    Replaces the 2.5 s polling pattern in MainView.vue.

    Event types:
      - ``progress`` — task snapshot (same shape as GET /embedding/tasks/{task_id})
      - ``done``     — terminal event
    """
    import json as _json

    async def _generator():
        from api.workers.embedding_worker import get_embedding_worker

        worker = await get_embedding_worker()
        terminal = {"completed", "failed", "cancelled"}
        max_ticks = 600

        for _ in range(max_ticks):
            try:
                task = await worker.get_task(task_id)
                if not task:
                    yield f'event: error\ndata: {{"detail":"Task not found"}}\n\n'
                    return

                if task.user_id != current_user_id:
                    yield f'event: error\ndata: {{"detail":"Unauthorized"}}\n\n'
                    return

                payload = task.to_dict()
                event_name = "done" if payload.get("status") in terminal else "progress"
                yield f"event: {event_name}\ndata: {_json.dumps(payload, default=str)}\n\n"

                if payload.get("status") in terminal:
                    return

            except Exception as exc:
                yield f"event: error\ndata: {_json.dumps({'detail': str(exc)})}\n\n"
                return

            await asyncio.sleep(0.5)

        yield 'event: done\ndata: {"status":"timeout"}\n\n'

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ==================================================================
# Admin (Worker Diagnostics Only)
# ==================================================================

@router.get("/admin/worker-status")
async def get_worker_status(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get embedding worker status for debugging and monitoring."""
    try:
        from api.workers.embedding_worker import get_embedding_worker

        worker = await get_embedding_worker()
        is_running = worker._consumer_task is not None and not worker._consumer_task.done()

        async with worker._lock:
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
        return {"worker_running": False, "error": str(e)}


# ==================================================================
# Transcript Download
# ==================================================================

@router.post("/transcript/download")
async def download_transcript(
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
                        if isinstance(src, dict):
                            lines.append(f"- {src.get('source', src.get('file', 'unknown'))}")
                        else:
                            lines.append(f"- {str(src)}")
                    lines.append("")
                lines.append("---")
                lines.append("")
            content = "\n".join(lines)
            filename = f"RET_transcript_{req.session_id}_{timestamp}.md"
            media_type = "text/markdown"

        return Response(
            content=content.encode("utf-8"),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Failed to generate transcript: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate transcript")


# ==================================================================
# Feedback
# ==================================================================

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    req: FeedbackRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Record user feedback (thumbs up/down) on a RAG response."""
    _verify_session_owner(req.session_id, current_user_id)

    try:
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
async def cleanup_ai_session(
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
        raise HTTPException(status_code=500, detail="Failed to cleanup AI session")