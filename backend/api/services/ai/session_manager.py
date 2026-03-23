
"""
AI Session Manager — Simplified Single-Stack Manager.

Wraps UnifiedRAGService for session lifecycle management:
  - Creates/retrieves UnifiedRAGService per session
  - Manages auto-embedding lifecycle
  - Handles cleanup on logout
  - Provides chat, embedding, and status APIs

Replaces the dual-stack (AdvancedRAGEngine/RAGEngine) approach.
"""

import json
import logging
import shutil
import threading
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.core.config import settings
from api.services.advanced_ai_service import (
    UnifiedRAGService,
    EmbeddingStats,
    get_rag_service,
    clear_rag_service,
)

logger = logging.getLogger(__name__)


class SessionAIManager:
    """
    Manages AI resources for a single user session.

    Delegates all RAG operations to UnifiedRAGService.
    Manages auto-embedding, metadata persistence, and cleanup.
    """

    AUTO_EMBED_SUPPRESSED_KEY = "auto_embed_suppressed"
    AUTO_EMBED_SUPPRESSED_AT_KEY = "auto_embed_suppressed_at"
    AUTO_EMBED_SUPPRESSED_REASON_KEY = "auto_embed_suppressed_reason"
    AUTO_EMBED_SUPPRESSED_BY_KEY = "auto_embed_suppressed_by"

    def __init__(self, session_id: str, user_id: str, session_dir: Path):
        self.session_id = session_id
        self.user_id = user_id
        self.session_dir = session_dir

        # Metadata persistence
        self.metadata_path = session_dir / "ai_metadata.json"
        self._metadata: Dict[str, Any] = {}
        self._load_metadata()
        self._metadata.setdefault(self.AUTO_EMBED_SUPPRESSED_KEY, False)

        # Auto-embedder reference (lazy init)
        self._auto_embedder = None
        self._lock = threading.Lock()

        # Lazily initialised RAG service
        self._rag_service: Optional[UnifiedRAGService] = None
        self._rag_init_in_progress = False

        # Track which groups were auto-embedded vs user-selected
        self._auto_embedded_groups: List[str] = self._metadata.get(
            "auto_embedded_groups", []
        )

        logger.info(
            f"SessionAIManager initialised: session={session_id}, user={user_id}"
        )
        
        # Eagerly initialize RAG service if configured (prevents delays on first status check)
        if self.is_configured():
            try:
                # This will initialize embeddings and chat clients in the background
                _ = self.rag_service
                logger.info(f"RAG service eagerly initialized for session {session_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to eagerly initialize RAG service for {session_id}: {e}"
                )

    # ------------------------------------------------------------------
    # RAG Service Access
    # ------------------------------------------------------------------

    @property
    def rag_service(self) -> UnifiedRAGService:
        """Get or create the UnifiedRAGService for this session."""
        if self._rag_service is None:
            with self._lock:
                if self._rag_service is None:
                    self._rag_service = get_rag_service(
                        self.session_dir, self.session_id, self.user_id
                    )
        return self._rag_service

    def is_configured(self) -> bool:
        """Check if AI services are properly configured."""
        return bool(settings.AZURE_OPENAI_API_KEY) and bool(
            settings.AZURE_OPENAI_ENDPOINT
        )

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat(
        self,
        message: str,
        use_rag: bool = True,
        group_filter: Optional[str] = None,
        top_k: int = 16,
    ) -> Dict[str, Any]:
        """
        Send a chat message and get a response.

        Args:
            message: User message
            use_rag: Whether to use RAG retrieval
            group_filter: Optional group to filter retrieval
            top_k: Number of chunks to retrieve

        Returns:
            Response dict with answer, sources, citations
        """
        if not self.is_configured():
            return {
                "answer": (
                    "AI is not configured. Please set Azure OpenAI credentials "
                    "in your environment (AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT)."
                ),
                "sources": [],
                "citations": [],
                "error": "not_configured",
            }

        if use_rag:
            result = self.rag_service.chat(
                query=message,
                group_filter=group_filter,
                top_k=top_k,
            )
        else:
            answer = self.rag_service.chat_direct(message)
            result = {
                "answer": answer,
                "sources": [],
                "citations": [],
                "query_time_ms": 0,
                "error": False,
            }

        # Persist metadata
        self._save_metadata()

        return result

    async def chat_async(
        self,
        message: str,
        use_rag: bool = True,
        group_filter: Optional[str] = None,
        top_k: int = 16,
        thread_id: str = "",
    ) -> Dict[str, Any]:
        """
        Async chat — fully non-blocking.

        When FEATURE_LANGGRAPH_ENABLED is True and use_rag is True, delegates
        to the LangGraph RAG pipeline.  Otherwise falls back to the existing
        UnifiedRAGService async/sync paths.
        """
        if not self.is_configured():
            return {
                "answer": (
                    "AI is not configured. Please set Azure OpenAI credentials "
                    "in your environment (AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT)."
                ),
                "sources": [],
                "citations": [],
                "error": "not_configured",
            }

        if use_rag and getattr(settings, "FEATURE_LANGGRAPH_ENABLED", False):
            try:
                from api.services.ai.langgraph.graph import run_rag_graph

                history = [
                    {"role": m.role, "content": m.content}
                    for m in getattr(self.rag_service, "conversation_history", [])
                ]
                result = await run_rag_graph(
                    query=message,
                    session_id=self.session_id,
                    user_id=self.user_id,
                    group_filter=group_filter,
                    top_k=top_k,
                    conversation_history=history[-6:],
                    thread_id=thread_id,
                )
                # Keep conversation history in sync
                self.rag_service._append_history("user", message)
                self.rag_service._append_history("assistant", result.get("answer", ""))
                self._save_metadata()
                return result
            except Exception:
                logger.warning(
                    "LangGraph RAG failed; falling back to legacy async path",
                    exc_info=True,
                )

        if use_rag:
            # Use the native async RAG pipeline (AsyncAzureOpenAI + asyncio.to_thread)
            try:
                result = await self.rag_service.chat_async(
                    query=message,
                    group_filter=group_filter,
                    top_k=top_k,
                )
            except Exception:
                logger.warning(
                    "Async RAG chat failed; falling back to sync-in-thread",
                    exc_info=True,
                )
                result = await asyncio.to_thread(
                    self.chat, message, True, group_filter, top_k,
                )
        else:
            try:
                from api.services.ai.async_azure_openai_service import (
                    get_async_azure_chat_service,
                )

                service = get_async_azure_chat_service()
                answer = await service.generate(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant for the RET Application.",
                        },
                        {"role": "user", "content": message},
                    ],
                    temperature=settings.RET_AI_TEMPERATURE,
                    max_tokens=getattr(settings, "AI_MAX_TOKENS", 1200),
                )

                result = {
                    "answer": answer,
                    "sources": [],
                    "citations": [],
                    "query_time_ms": 0,
                    "error": False,
                }
            except Exception:
                logger.warning(
                    "Async direct chat failed; falling back to sync",
                    exc_info=True,
                )
                result = await asyncio.to_thread(
                    self.chat, message, False, group_filter, top_k,
                )

        # Persist metadata in background
        await asyncio.to_thread(self._save_metadata)
        return result

    async def chat_stream(
        self,
        message: str,
        group_filter: Optional[str] = None,
        top_k: int = 16,
        thread_id: str = "",
    ):
        """
        Async generator that yields SSE events for a streaming RAG chat.

        Falls back to a single ``done`` event wrapping ``chat_async`` when
        LangGraph streaming is unavailable or FEATURE_CHAT_STREAMING is off.
        """
        import json as _json

        if not self.is_configured():
            yield (
                'event: error\ndata: {"detail":"AI is not configured."}\n\n'
            )
            return

        if not getattr(settings, "FEATURE_CHAT_STREAMING", False):
            # Feature flag off — fall back to non-streaming response
            result = await self.chat_async(
                message=message,
                use_rag=True,
                group_filter=group_filter,
                top_k=top_k,
            )
            yield f"event: done\ndata: {_json.dumps(result, default=str)}\n\n"
            return

        try:
            from api.services.ai.langgraph.graph import stream_rag_graph

            history = [
                {"role": m.role, "content": m.content}
                for m in getattr(self.rag_service, "conversation_history", [])
            ]

            final_answer: str = ""

            async for event in stream_rag_graph(
                query=message,
                session_id=self.session_id,
                user_id=self.user_id,
                group_filter=group_filter,
                top_k=top_k,
                conversation_history=history[-6:],
                thread_id=thread_id,
            ):
                yield event
                # Capture answer from the done event
                if event.startswith("event: done"):
                    try:
                        data_line = event.split("data: ", 1)[1]
                        done_payload = _json.loads(data_line.strip())
                        final_answer = done_payload.get("answer", "")
                    except Exception:
                        pass

            # Keep conversation history in sync
            if final_answer:
                self.rag_service._append_history("user", message)
                self.rag_service._append_history("assistant", final_answer)
            await asyncio.to_thread(self._save_metadata)

        except Exception as exc:
            logger.warning(
                "LangGraph streaming failed; falling back to non-streaming",
                exc_info=True,
            )
            result = await self.chat_async(
                message=message,
                use_rag=True,
                group_filter=group_filter,
                top_k=top_k,
            )
            yield f"event: done\ndata: {_json.dumps(result, default=str)}\n\n"

    async def resume_hitl(
        self,
        thread_id: str,
        decision: str = "approve",
        edited_answer: str = "",
    ) -> Dict[str, Any]:
        """
        Resume a HITL-interrupted graph execution.

        Delegates to ``resume_rag_graph`` from the LangGraph module.
        """
        try:
            from api.services.ai.langgraph.graph import resume_rag_graph

            result = await resume_rag_graph(
                thread_id=thread_id,
                decision=decision,
                edited_answer=edited_answer,
            )

            # Keep conversation history in sync
            if result.get("answer") and not result.get("error"):
                self.rag_service._append_history("assistant", result["answer"])
            await asyncio.to_thread(self._save_metadata)
            return result

        except Exception as exc:
            logger.error("HITL resume failed in session manager: %s", exc, exc_info=True)
            return {
                "answer": f"Resume failed: {exc}",
                "sources": [],
                "citations": [],
                "query_time_ms": 0,
                "error": True,
                "response_type": "error",
            }

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed_groups(
        self,
        groups: List[str],
        csv_dir: Optional[Path] = None,
        conversion_index: Optional[Dict] = None,
    ) -> EmbeddingStats:
        """
        Embed CSV files for specified groups.

        Args:
            groups: List of group names
            csv_dir: Directory with CSV files (defaults to session/output)
            conversion_index: Optional conversion_index.json content

        Returns:
            EmbeddingStats
        """
        if not self.is_configured():
            stats = EmbeddingStats()
            stats.errors.append("AI not configured")
            return stats

        output_dir = csv_dir or (self.session_dir / "output")
        if not output_dir.exists():
            stats = EmbeddingStats()
            stats.errors.append("No output directory found")
            return stats

        # Load conversion index if not provided
        if conversion_index is None:
            index_path = self.session_dir / "conversion_index.json"
            if index_path.exists():
                try:
                    conversion_index = json.loads(index_path.read_text())
                except Exception:
                    pass

        stats = self.rag_service.embed_groups(
            groups=groups,
            csv_dir=output_dir,
            conversion_index=conversion_index,
        )

        # Update metadata
        existing_groups = set(self._metadata.get("embedded_groups", []))
        existing_groups.update(stats.groups_processed)
        self._metadata["embedded_groups"] = sorted(existing_groups)
        self._metadata["last_embedded"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata()

        return stats

    def embed_csv_files(
        self,
        csv_paths: List[str],
        group_override: Optional[str] = None,
    ) -> EmbeddingStats:
        """
        Embed specific CSV files directly.

        Args:
            csv_paths: Absolute paths to CSV files
            group_override: Optional group name override

        Returns:
            EmbeddingStats
        """
        if not self.is_configured():
            stats = EmbeddingStats()
            stats.errors.append("AI not configured")
            return stats

        stats = self.rag_service.embed_csv_files(csv_paths, group_override)

        # Update metadata
        existing_groups = set(self._metadata.get("embedded_groups", []))
        existing_groups.update(stats.groups_processed)
        self._metadata["embedded_groups"] = sorted(existing_groups)
        self._metadata["last_embedded"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata()

        return stats

    # ------------------------------------------------------------------
    # Embedding Status
    # ------------------------------------------------------------------

    def get_embedding_status(self) -> Dict[str, Dict[str, Any]]:
        """Get per-group embedding status from the vector store."""
        return self.rag_service.get_embedding_status()

    def get_embedding_stats(self) -> Dict[str, Any]:
        """Get overall embedding statistics."""
        return self.rag_service.get_stats()
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics (alias for get_embedding_stats for compatibility)."""
        return self.get_embedding_stats()

    # ------------------------------------------------------------------
    # Auto-Embedding
    # ------------------------------------------------------------------

    @property
    def auto_embedder(self):
        """Get or create auto-embedder."""
        if self._auto_embedder is None:
            with self._lock:
                if self._auto_embedder is None:
                    from api.services.ai.auto_embedder import AutoEmbedder

                    self._auto_embedder = AutoEmbedder(
                        session_id=self.session_id,
                        session_dir=self.session_dir,
                        rag_service=self.rag_service,
                    )
        return self._auto_embedder

    def start_auto_embed(
        self,
        xml_inventory: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Start auto-embedding for admin-configured groups ONLY.

        Only groups that appear in admin_prefs.json → auto_embedded_groups AND
        are actually present in the ZIP inventory will be embedded.

        Args:
            xml_inventory: List of XML file entries from ZIP scan

        Returns:
            Status dict
        """
        if self.is_auto_embed_suppressed:
            return {
                "status": "suppressed",
                "eligible_groups": [],
                "message": "Auto-embedding is suppressed for this session until manually resumed",
            }

        # Always refresh admin config at trigger time so latest admin changes apply.
        try:
            self.auto_embedder.reload_admin_config()
        except Exception as e:
            logger.warning("Failed to reload admin config before auto-embed trigger: %s", e)

        if not self.auto_embedder.is_auto_embed_enabled:
            return {
                "status": "disabled",
                "eligible_groups": [],
                "message": "Auto-embedding is disabled in admin configuration",
            }

        eligible = self.auto_embedder.detect_eligible_groups(xml_inventory)

        if not eligible:
            return {
                "status": "no_eligible_groups",
                "eligible_groups": [],
                "message": "No groups match admin auto-embed configuration",
            }

        self.auto_embedder.start_auto_embed(
            xml_inventory=xml_inventory,
            groups_to_embed=eligible,
            group_callback=self._on_group_embed_update,
        )

        # Track auto-embedded groups so the UI can hide them from manual selection
        self._auto_embedded_groups = list(set(self._auto_embedded_groups + eligible))
        self._metadata["auto_embedded_groups"] = self._auto_embedded_groups

        # Initialize per-group status
        group_status = self._metadata.get("embed_group_status", {})
        for g in eligible:
            group_status[g] = {"status": "queued", "updated_at": datetime.now(timezone.utc).isoformat()}
        self._metadata["embed_group_status"] = group_status
        self._save_metadata()

        return {
            "status": "started",
            "eligible_groups": eligible,
            "message": f"Auto-embedding started for {len(eligible)} groups",
        }

    @property
    def auto_embedded_groups(self) -> List[str]:
        """Groups that were automatically embedded (admin-configured)."""
        return list(self._auto_embedded_groups)

    def get_embed_group_status(self) -> Dict[str, Any]:
        """Return persistent per-group embedding status."""
        return dict(self._metadata.get("embed_group_status", {}))

    def _on_group_embed_update(self, group: str, status: str, detail: str = "") -> None:
        """Callback invoked by the auto-embedder as each group progresses."""
        try:
            gs = self._metadata.setdefault("embed_group_status", {})
            gs[group] = {
                "status": status,
                "detail": detail,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_metadata()
        except Exception as exc:
            logger.debug("Failed to persist group embed status for %s: %s", group, exc)

    def get_auto_embed_progress(self):
        """Get current auto-embedding progress."""
        return self.auto_embedder.progress

    @property
    def is_auto_embed_suppressed(self) -> bool:
        """Whether automatic embedding re-triggers are suppressed for this session."""
        return bool(self._metadata.get(self.AUTO_EMBED_SUPPRESSED_KEY, False))

    def set_auto_embed_suppressed(
        self,
        suppressed: bool,
        reason: str = "",
        source: str = "",
    ) -> None:
        """Persist session-scoped auto-embed suppression state."""
        self._metadata[self.AUTO_EMBED_SUPPRESSED_KEY] = bool(suppressed)

        if suppressed:
            self._metadata[self.AUTO_EMBED_SUPPRESSED_AT_KEY] = datetime.now(timezone.utc).isoformat()
            if reason:
                self._metadata[self.AUTO_EMBED_SUPPRESSED_REASON_KEY] = str(reason)
            if source:
                self._metadata[self.AUTO_EMBED_SUPPRESSED_BY_KEY] = str(source)
        else:
            self._metadata.pop(self.AUTO_EMBED_SUPPRESSED_AT_KEY, None)
            self._metadata.pop(self.AUTO_EMBED_SUPPRESSED_REASON_KEY, None)
            self._metadata.pop(self.AUTO_EMBED_SUPPRESSED_BY_KEY, None)

        self._save_metadata()

    def clear_auto_embed_suppression(self) -> None:
        """Clear auto-embed suppression for this session."""
        if not self.is_auto_embed_suppressed:
            return
        self.set_auto_embed_suppressed(False)

    def stop_auto_embed(
        self,
        suppress_auto_start: bool = False,
        reason: str = "",
        source: str = "",
    ) -> None:
        """Stop auto-embedding if running and optionally suppress auto-restarts."""
        if self._auto_embedder:
            self._auto_embedder.stop()

        if suppress_auto_start:
            self.set_auto_embed_suppressed(True, reason=reason, source=source)

    async def stop_all_embedding(
        self,
        suppress_auto_start: bool = True,
        reason: str = "Stopped by user",
        source: str = "user",
    ) -> Dict[str, Any]:
        """Stop both auto-embedder and any EmbeddingWorker tasks for this session."""
        self.stop_auto_embed(
            suppress_auto_start=suppress_auto_start,
            reason=reason,
            source=source,
        )
        worker_cancelled = 0
        try:
            from api.workers.embedding_worker import get_embedding_worker

            worker = await get_embedding_worker()
            worker_cancelled = await worker.cancel_session_tasks(self.session_id)
        except Exception as e:
            logger.warning("Failed to cancel worker tasks for session %s: %s", self.session_id, e)
        return {
            "auto_embed_stopped": True,
            "worker_tasks_cancelled": worker_cancelled,
            "auto_embed_suppressed": self.is_auto_embed_suppressed,
        }

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_chat_history(self, limit: int = 50) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.rag_service.get_history(limit)

    def clear_chat_history(self) -> None:
        """Clear conversation history."""
        self.rag_service.clear_history()
        self._save_metadata()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_embeddings(self) -> None:
        """Clear all embedded data (keep session alive)."""
        self.rag_service.clear()
        self._metadata["embedded_groups"] = []
        self._save_metadata()

    def clear_index(self) -> None:
        """Compatibility alias for older router callers."""
        self.clear_embeddings()

    def cleanup(self) -> None:
        """Full cleanup — destroy vector store, clear history, delete metadata."""
        try:
            if self._auto_embedder:
                self._auto_embedder.stop()

            if self._rag_service:
                self._rag_service.destroy()

            # Also clear from global registry
            clear_rag_service(self.session_id, self.user_id)

            # Remove AI-related directories
            for subdir in ("chroma", "ai_index"):
                path = self.session_dir / subdir
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)

            # Remove metadata file
            if self.metadata_path.exists():
                self.metadata_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Cleanup error for session {self.session_id}: {e}")

    # ------------------------------------------------------------------
    # Metadata Persistence
    # ------------------------------------------------------------------

    def _load_metadata(self) -> None:
        """Load AI session metadata from disk."""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self._metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading AI metadata: {e}")
                self._metadata = {}

    def _save_metadata(self) -> None:
        """Save AI session metadata to disk."""
        try:
            self._metadata["session_id"] = self.session_id
            self._metadata["user_id"] = self.user_id
            self._metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving AI metadata: {e}")


def _load_conversion_inventory_for_auto_embed(session_dir: Path) -> List[Dict[str, Any]]:
    """Load best-effort conversion inventory for auto-embedding decisions."""
    for candidate in ("conversion_index.json", "xml_inventory.json"):
        path = session_dir / candidate
        if not path.exists():
            continue

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to parse %s for auto-embed trigger: %s", path.name, e)
            continue

        if isinstance(raw, dict):
            files = raw.get("files")
            if isinstance(files, list):
                return [x for x in files if isinstance(x, dict)]

        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]

    return []


def trigger_auto_embed_after_conversion(
    session_id: str,
    user_id: str,
    conversion_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Best-effort auto-embed trigger after conversion completion.

    Returns a metadata payload suitable for conversion responses and async job result.
    """
    meta: Dict[str, Any] = {
        "status": "not_attempted",
        "attempted": False,
        "triggered": False,
        "eligible_groups": [],
        "message": "Auto-embedding not attempted",
    }

    if not session_id or not user_id:
        meta["message"] = "Auto-embedding not attempted: missing session/user context"
        return meta

    try:
        if isinstance(conversion_result, dict):
            stats = conversion_result.get("stats") or {}
            success_count = int(stats.get("success", 0) or 0)
            failed_count = int(stats.get("failed", 0) or 0)
            if failed_count > 0 and success_count == 0:
                meta["message"] = "Auto-embedding skipped: conversion produced no successful outputs"
                return meta

        manager = get_session_ai_manager(session_id, user_id)

        if manager.is_auto_embed_suppressed:
            meta.update(
                {
                    "attempted": True,
                    "status": "suppressed",
                    "eligible_groups": [],
                    "message": "Auto-embedding is suppressed for this session until manually resumed",
                }
            )
            return meta

        if not manager.is_configured():
            meta.update(
                {
                    "status": "disabled",
                    "attempted": True,
                    "message": "AI service not configured",
                }
            )
            return meta

        inventory = _load_conversion_inventory_for_auto_embed(manager.session_dir)
        if not inventory:
            meta.update(
                {
                    "status": "no_inventory",
                    "attempted": True,
                    "message": "No conversion inventory available for auto-embedding",
                }
            )
            return meta

        try:
            manager.auto_embedder.reload_admin_config()
        except Exception as e:
            logger.warning("Failed to reload admin config for auto-embed trigger: %s", e)

        if not manager.auto_embedder.is_auto_embed_enabled:
            meta.update(
                {
                    "attempted": True,
                    "status": "disabled",
                    "eligible_groups": [],
                    "message": "Auto-embedding is disabled in admin configuration",
                }
            )
            return meta

        eligible = manager.auto_embedder.detect_eligible_groups(inventory)
        meta["attempted"] = True
        meta["eligible_groups"] = list(eligible)

        if not eligible:
            meta.update(
                {
                    "status": "no_eligible_groups",
                    "message": "No groups matched admin auto-embed configuration",
                }
            )
            return meta

        try:
            in_progress = str(getattr(manager.get_auto_embed_progress(), "status", "") or "").lower()
            if in_progress in {"preparing", "embedding"}:
                meta.update(
                    {
                        "status": "already_running",
                        "message": "Auto-embedding is already running",
                    }
                )
                return meta
        except Exception:
            # Non-fatal; continue with trigger checks.
            pass

        try:
            existing = manager.get_embedding_status() or {}
            if all(bool((existing.get(g) or {}).get("indexed")) for g in eligible):
                meta.update(
                    {
                        "status": "already_indexed",
                        "message": "Eligible groups are already indexed",
                    }
                )
                return meta
        except Exception as e:
            logger.debug("Unable to verify existing embedding status before trigger: %s", e)

        started = manager.start_auto_embed(inventory)
        status = str(started.get("status", "not_attempted"))
        meta.update(
            {
                "status": status,
                "triggered": status == "started",
                "eligible_groups": list(started.get("eligible_groups", eligible) or eligible),
                "message": str(started.get("message", "")),
            }
        )
        return meta

    except Exception as e:
        logger.warning("Auto-embed trigger failed for session %s: %s", session_id, e, exc_info=True)
        meta.update(
            {
                "status": "failed",
                "attempted": True,
                "triggered": False,
                "message": f"Auto-embedding trigger failed: {e}",
            }
        )
        return meta


# ============================================================
# Global Registry
# ============================================================

_session_managers: Dict[str, SessionAIManager] = {}
_registry_lock = threading.Lock()


def get_session_ai_manager(
    session_id: str,
    user_id: str,
    session_dir: Optional[Path] = None,
) -> SessionAIManager:
    """
    Get or create AI manager for a session.

    Args:
        session_id: Session identifier
        user_id: User identifier
        session_dir: Session directory path (auto-resolved if None)

    Returns:
        SessionAIManager instance
    """
    key = f"{user_id}:{session_id}"

    with _registry_lock:
        if key not in _session_managers:
            if session_dir is None:
                from api.services.storage_service import get_session_dir

                session_dir = get_session_dir(session_id)

            _session_managers[key] = SessionAIManager(
                session_id=session_id,
                user_id=user_id,
                session_dir=session_dir,
            )
        return _session_managers[key]


def cleanup_session_ai(session_id: str, user_id: str) -> None:
    """Cleanup AI resources for a session (called on logout)."""
    key = f"{user_id}:{session_id}"

    with _registry_lock:
        if key in _session_managers:
            try:
                _session_managers[key].cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up AI session: {e}")
            finally:
                del _session_managers[key]
