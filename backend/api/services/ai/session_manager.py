"""
AI Session Manager — Simplified Single-Stack Manager.

Wraps UnifiedRAGService for session lifecycle management:
  - Creates/retrieves UnifiedRAGService per session
  - Manages auto-indexing lifecycle
  - Handles cleanup on logout
  - Provides chat, index, and status APIs

Replaces the dual-stack (AdvancedRAGEngine/RAGEngine) approach.
"""

import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.core.config import settings
from api.services.advanced_ai_service import (
    UnifiedRAGService,
    IndexingStats,
    get_rag_service,
    clear_rag_service,
)

logger = logging.getLogger(__name__)


class SessionAIManager:
    """
    Manages AI resources for a single user session.

    Delegates all RAG operations to UnifiedRAGService.
    Manages auto-indexing, metadata persistence, and cleanup.
    """

    def __init__(self, session_id: str, user_id: str, session_dir: Path):
        self.session_id = session_id
        self.user_id = user_id
        self.session_dir = session_dir

        # Metadata persistence
        self.metadata_path = session_dir / "ai_metadata.json"
        self._metadata: Dict[str, Any] = {}
        self._load_metadata()

        # Auto-indexer reference (lazy init)
        self._auto_indexer = None
        self._lock = threading.Lock()

        # Lazily initialised RAG service
        self._rag_service: Optional[UnifiedRAGService] = None
        self._rag_init_in_progress = False

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

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_groups(
        self,
        groups: List[str],
        csv_dir: Optional[Path] = None,
        conversion_index: Optional[Dict] = None,
    ) -> IndexingStats:
        """
        Index CSV files for specified groups.

        Args:
            groups: List of group names
            csv_dir: Directory with CSV files (defaults to session/output)
            conversion_index: Optional conversion_index.json content

        Returns:
            IndexingStats
        """
        if not self.is_configured():
            stats = IndexingStats()
            stats.errors.append("AI not configured")
            return stats

        output_dir = csv_dir or (self.session_dir / "output")
        if not output_dir.exists():
            stats = IndexingStats()
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

        stats = self.rag_service.index_groups(
            groups=groups,
            csv_dir=output_dir,
            conversion_index=conversion_index,
        )

        # Update metadata
        existing_groups = set(self._metadata.get("indexed_groups", []))
        existing_groups.update(stats.groups_processed)
        self._metadata["indexed_groups"] = sorted(existing_groups)
        self._metadata["last_indexed"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata()

        return stats

    def index_csv_files(
        self,
        csv_paths: List[str],
        group_override: Optional[str] = None,
    ) -> IndexingStats:
        """
        Index specific CSV files directly.

        Args:
            csv_paths: Absolute paths to CSV files
            group_override: Optional group name override

        Returns:
            IndexingStats
        """
        if not self.is_configured():
            stats = IndexingStats()
            stats.errors.append("AI not configured")
            return stats

        stats = self.rag_service.index_csv_files(csv_paths, group_override)

        # Update metadata
        existing_groups = set(self._metadata.get("indexed_groups", []))
        existing_groups.update(stats.groups_processed)
        self._metadata["indexed_groups"] = sorted(existing_groups)
        self._metadata["last_indexed"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata()

        return stats

    # ------------------------------------------------------------------
    # Embedding Status
    # ------------------------------------------------------------------

    def get_embedding_status(self) -> Dict[str, Dict[str, Any]]:
        """Get per-group embedding status from the vector store."""
        return self.rag_service.get_embedding_status()

    def get_index_stats(self) -> Dict[str, Any]:
        """Get overall indexing statistics."""
        return self.rag_service.get_stats()

    # ------------------------------------------------------------------
    # Auto-Indexing
    # ------------------------------------------------------------------

    @property
    def auto_indexer(self):
        """Get or create auto-indexer."""
        if self._auto_indexer is None:
            with self._lock:
                if self._auto_indexer is None:
                    from api.services.ai.auto_indexer import AutoIndexer

                    self._auto_indexer = AutoIndexer(
                        session_id=self.session_id,
                        session_dir=self.session_dir,
                        rag_service=self.rag_service,
                    )
        return self._auto_indexer

    def start_auto_index(
        self,
        xml_inventory: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Start auto-indexing for admin-configured groups.

        Args:
            xml_inventory: List of XML file entries from ZIP scan

        Returns:
            Status dict
        """
        eligible = self.auto_indexer.detect_eligible_groups(xml_inventory)

        if not eligible:
            return {
                "status": "no_eligible_groups",
                "eligible_groups": [],
                "message": "No groups match admin auto-index configuration",
            }

        self.auto_indexer.start_auto_index(
            xml_inventory=xml_inventory,
            groups_to_index=eligible,
        )

        return {
            "status": "started",
            "eligible_groups": eligible,
            "message": f"Auto-indexing started for {len(eligible)} groups",
        }

    def get_auto_index_progress(self):
        """Get current auto-indexing progress."""
        return self.auto_indexer.progress

    def stop_auto_index(self) -> None:
        """Stop auto-indexing if running."""
        if self._auto_indexer:
            self._auto_indexer.stop()

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

    def clear_index(self) -> None:
        """Clear all indexed data (keep session alive)."""
        self.rag_service.clear()
        self._metadata["indexed_groups"] = []
        self._save_metadata()

    def cleanup(self) -> None:
        """Full cleanup — destroy vector store, clear history, delete metadata."""
        try:
            if self._auto_indexer:
                self._auto_indexer.stop()

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
