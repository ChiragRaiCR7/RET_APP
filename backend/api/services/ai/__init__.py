"""
Unified AI Service Module

This module consolidates all AI services into a single factory pattern.
Use AIServiceFactory.create() to get the appropriate AI service instance.

New Architecture:
- RAGEngine: LangChain/LangGraph powered RAG with ChromaDB
- AutoIndexer: Background auto-indexing after ZIP scans
"""

from api.services.ai.base import BaseAIService, AIStrategy, IndexingStats, ChatResponse
from api.services.ai.factory import AIServiceFactory
from api.services.ai.lite import LiteAIStrategy
from api.services.ai.langchain_strategy import LangChainAIStrategy
from api.services.ai.advanced import AdvancedAIStrategy
from api.services.ai.rag_engine import RAGEngine, RAGResponse, RetrievedChunk, QueryPlan
from api.services.ai.auto_indexer import AutoIndexer, IndexingProgress, XMLRecordExtractor

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
    # New RAG components
    "RAGEngine",
    "RAGResponse",
    "RetrievedChunk",
    "QueryPlan",
    # Auto-indexing
    "AutoIndexer",
    "IndexingProgress",
    "XMLRecordExtractor",
]
