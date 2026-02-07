"""
AI Services Package — UnifiedRAGService Architecture

Active modules:
- api.services.advanced_ai_service — Core RAG engine (UnifiedRAGService)
- api.services.ai.session_manager  — Per-session AI resource management
- api.services.ai.auto_embedder    — Background auto-embedding after conversions
"""

from api.services.advanced_ai_service import EmbeddingStats
from api.services.ai.auto_embedder import AutoEmbedder, EmbeddingProgress
from api.services.ai.session_manager import (
    SessionAIManager,
    get_session_ai_manager,
    cleanup_session_ai,
)

__all__ = [
    "EmbeddingStats",
    "AutoEmbedder",
    "EmbeddingProgress",
    "SessionAIManager",
    "get_session_ai_manager",
    "cleanup_session_ai",
]
