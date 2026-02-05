"""
Unified AI Service Module

This module consolidates all AI services into a single factory pattern.
Use AIServiceFactory.create() to get the appropriate AI service instance.

Architecture:
- AdvancedRAGEngine: LangGraph-powered Advanced RAG with:
  - Query Transformation
  - Query Routing (vector/lexical/summary/fusion)
  - Fusion Retrieval
  - Reranking & Postprocessing
  - Citation-aware Generation
- RAGEngine: Basic LangChain RAG with ChromaDB
- AutoIndexer: Background auto-indexing after ZIP scans
- SessionAIManager: Per-session AI resource management
"""

from api.services.ai.base import BaseAIService, AIStrategy, IndexingStats, ChatResponse
from api.services.ai.factory import AIServiceFactory
from api.services.ai.lite import LiteAIStrategy
from api.services.ai.langchain_strategy import LangChainAIStrategy
from api.services.ai.advanced import AdvancedAIStrategy
from api.services.ai.rag_engine import RAGEngine, RAGResponse, RetrievedChunk, QueryPlan
from api.services.ai.auto_indexer import AutoIndexer, IndexingProgress, XMLRecordExtractor
from api.services.ai.session_manager import (
    SessionAIManager,
    get_session_ai_manager,
    cleanup_session_ai,
)

# Advanced RAG Engine imports
try:
    from api.services.ai.advanced_rag_engine import (
        AdvancedRAGEngine,
        RAGResponse as AdvancedRAGResponse,
        RetrievedChunk as AdvancedRetrievedChunk,
        TransformedQuery,
        QueryIntent,
        RetrievalStrategy,
        RAGConfig,
        create_advanced_rag_engine,
    )
    ADVANCED_RAG_AVAILABLE = True
except ImportError:
    ADVANCED_RAG_AVAILABLE = False
    AdvancedRAGEngine = None
    AdvancedRAGResponse = None
    TransformedQuery = None
    QueryIntent = None
    RetrievalStrategy = None
    RAGConfig = None
    create_advanced_rag_engine = None

__all__ = [
    # Base classes
    "BaseAIService",
    "AIStrategy",
    "AIServiceFactory",
    "IndexingStats",
    "ChatResponse",
    # Strategies
    "LiteAIStrategy",
    "LangChainAIStrategy",
    "AdvancedAIStrategy",
    # Basic RAG components
    "RAGEngine",
    "RAGResponse",
    "RetrievedChunk",
    "QueryPlan",
    # Advanced RAG components
    "AdvancedRAGEngine",
    "AdvancedRAGResponse",
    "AdvancedRetrievedChunk",
    "TransformedQuery",
    "QueryIntent",
    "RetrievalStrategy",
    "RAGConfig",
    "create_advanced_rag_engine",
    "ADVANCED_RAG_AVAILABLE",
    # Auto-indexing
    "AutoIndexer",
    "IndexingProgress",
    "XMLRecordExtractor",
    # Session management
    "SessionAIManager",
    "get_session_ai_manager",
    "cleanup_session_ai",
]
