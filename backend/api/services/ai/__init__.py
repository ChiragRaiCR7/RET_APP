"""
AI Services Package — UnifiedRAGService Architecture

Active modules (imported directly where needed):
- api.services.ai.session_manager  — Per-session AI resource management
- api.services.ai.auto_indexer     — Background auto-indexing after ZIP scans
- api.services.ai.backends         — Azure OpenAI chat/embedding clients
- api.services.ai.embedding_backend — Embedding service
- api.services.ai.vector_store     — ChromaDB vector store

Deprecated modules moved to api/_deprecated/:
- ai_lite.py, ai_factory.py, ai_langchain_strategy.py
- ai_rag_engine.py, ai_advanced_rag_engine.py
"""

from api.services.ai.base import IndexingStats, ChatResponse
from api.services.ai.auto_indexer import AutoIndexer, IndexingProgress
from api.services.ai.session_manager import (
    SessionAIManager,
    get_session_ai_manager,
    cleanup_session_ai,
)

__all__ = [
    "IndexingStats",
    "ChatResponse",
    "AutoIndexer",
    "IndexingProgress",
    "SessionAIManager",
    "get_session_ai_manager",
    "cleanup_session_ai",
]
