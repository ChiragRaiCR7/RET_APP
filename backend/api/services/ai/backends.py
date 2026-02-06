"""
AI Backend Abstractions

Provides unified interfaces for embedding and vector store backends.
This enables swapping implementations (Azure, local, etc.) without changing service code.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Protocol
from pathlib import Path
import logging

try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)


# =========================
# EMBEDDING BACKEND
# =========================

@dataclass
class EmbeddingResult:
    """Result from embedding operation."""
    embeddings: List[List[float]]
    model: str = ""
    token_count: int = 0


class EmbeddingBackend(ABC):
    """
    Abstract base class for embedding backends.
    
    Implementations should handle batching, retries, and error handling.
    """
    
    @abstractmethod
    def embed(self, texts: List[str]) -> EmbeddingResult:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            EmbeddingResult with embeddings list matching input order
        """
        pass
    
    @abstractmethod
    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string to embed
            
        Returns:
            Embedding vector as list of floats
        """
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension for this backend."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is available and configured."""
        pass


# =========================
# VECTOR STORE BACKEND
# =========================

@dataclass
class Document:
    """Document for vector store."""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """Result from vector query."""
    documents: List[Document]
    scores: List[float]
    total_count: int = 0


class VectorStoreBackend(ABC):
    """
    Abstract base class for vector store backends.
    
    Implementations should handle persistence, querying, and session isolation.
    """
    
    @abstractmethod
    def upsert(self, documents: List[Document]) -> int:
        """
        Insert or update documents in the vector store.
        
        Args:
            documents: List of documents to upsert
            
        Returns:
            Number of documents upserted
        """
        pass
    
    @abstractmethod
    def query(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """
        Query the vector store for similar documents.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Optional metadata filters
            
        Returns:
            QueryResult with matching documents and scores
        """
        pass
    
    @abstractmethod
    def delete(self, ids: List[str]) -> int:
        """
        Delete documents by ID.
        
        Args:
            ids: List of document IDs to delete
            
        Returns:
            Number of documents deleted
        """
        pass
    
    @abstractmethod
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """
        Delete documents matching a filter.
        
        Args:
            filters: Metadata filters for deletion
            
        Returns:
            Number of documents deleted
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear all documents from the store."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Return the total number of documents in the store."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is available."""
        pass


# =========================
# RAG CONFIG
# =========================

@dataclass
class RAGConfig:
    """Configuration for RAG engine."""
    # Retrieval settings
    top_k_vector: int = 20
    top_k_lexical: int = 15
    top_k_summary: int = 5
    max_chunks: int = 15
    max_context_chars: int = 40000
    
    # Fusion weights
    vector_weight: float = 0.6
    lexical_weight: float = 0.3
    summary_weight: float = 0.1
    
    # Chunking settings
    chunk_size: int = 1500
    chunk_overlap: int = 200
    
    # Feature flags
    enable_query_transform: bool = True
    enable_summaries: bool = True
    enable_reranking: bool = True
    
    @classmethod
    def from_settings(cls) -> "RAGConfig":
        """Create RAGConfig from application settings."""
        from api.core.config import settings
        
        return cls(
            top_k_vector=settings.RAG_TOP_K_VECTOR,
            top_k_lexical=settings.RAG_TOP_K_LEXICAL,
            top_k_summary=settings.RAG_TOP_K_SUMMARY,
            max_chunks=settings.RAG_MAX_CHUNKS,
            max_context_chars=settings.RAG_MAX_CONTEXT_CHARS,
            vector_weight=settings.RAG_VECTOR_WEIGHT,
            lexical_weight=settings.RAG_LEXICAL_WEIGHT,
            summary_weight=settings.RAG_SUMMARY_WEIGHT,
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            enable_query_transform=settings.RAG_ENABLE_QUERY_TRANSFORM,
            enable_summaries=settings.RAG_ENABLE_SUMMARIES,
        )


# =========================
# AI SERVICE INTERFACE
# =========================

@dataclass
class ChatMessage:
    """Chat message with role and content."""
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class ChatResponse:
    """Response from AI chat."""
    answer: str
    sources: List[Document] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AIServiceInterface(ABC):
    """
    Abstract interface for AI services.
    
    Implementations handle indexing, retrieval, and chat.
    """
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the service. Returns True if successful."""
        pass
    
    @abstractmethod
    def index_documents(
        self,
        documents: List[Document],
        group: Optional[str] = None,
    ) -> int:
        """
        Index documents for retrieval.
        
        Args:
            documents: Documents to index
            group: Optional group name for organization
            
        Returns:
            Number of documents indexed
        """
        pass
    
    @abstractmethod
    def chat(
        self,
        message: str,
        use_rag: bool = True,
        group_filter: Optional[str] = None,
    ) -> ChatResponse:
        """
        Chat with the AI assistant.
        
        Args:
            message: User message
            use_rag: Whether to use RAG retrieval
            group_filter: Optional group filter for retrieval
            
        Returns:
            ChatResponse with answer and sources
        """
        pass
    
    @abstractmethod
    def get_indexed_groups(self) -> List[str]:
        """Return list of indexed group names."""
        pass
    
    @abstractmethod
    def clear_index(self, group: Optional[str] = None) -> None:
        """
        Clear indexed documents.
        
        Args:
            group: Optional group to clear (None clears all)
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the service is available and configured."""
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Clean up resources."""
        pass
