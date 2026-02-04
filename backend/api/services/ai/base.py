"""
Base AI Service - Abstract interface for all AI strategies.

This module defines the contract that all AI service implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AIStrategy(str, Enum):
    """Available AI service strategies"""
    LITE = "lite"
    LANGCHAIN = "langchain"
    ADVANCED = "advanced"
    
    @classmethod
    def from_string(cls, value: str) -> "AIStrategy":
        """Convert string to AIStrategy enum, with fallback to LITE"""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.LITE


@dataclass
class IndexingStats:
    """Statistics from document indexing operation"""
    documents_indexed: int = 0
    chunks_created: int = 0
    groups_processed: int = 0
    total_size_mb: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "documents_indexed": self.documents_indexed,
            "chunks_created": self.chunks_created,
            "groups_processed": self.groups_processed,
            "total_size_mb": self.total_size_mb,
            "errors": self.errors,
        }


@dataclass
class Citation:
    """Source citation for AI response"""
    content: str
    source: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class ChatResponse:
    """Response from AI chat/query"""
    answer: str
    citations: List[Citation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "metadata": self.metadata,
        }


class BaseAIService(ABC):
    """
    Abstract base class for AI services.
    
    All AI service implementations must inherit from this class
    and implement the required methods.
    """
    
    def __init__(self, session_id: str, persist_dir: Optional[str] = None):
        """
        Initialize AI service for a session.
        
        Args:
            session_id: Unique identifier for the session
            persist_dir: Directory for persisting vector store and other data
        """
        self.session_id = session_id
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self._initialized = False
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the AI service (load models, connect to vector store, etc.)
        
        Returns:
            True if initialization was successful
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the AI service is available and properly configured.
        
        Returns:
            True if the service can process requests
        """
        pass
    
    @abstractmethod
    def index_documents(
        self,
        files: List[Path],
        groups: Optional[Dict[str, List[Path]]] = None,
    ) -> IndexingStats:
        """
        Index documents into the vector store.
        
        Args:
            files: List of file paths to index
            groups: Optional grouping of files
            
        Returns:
            IndexingStats with indexing results
        """
        pass
    
    @abstractmethod
    def chat(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> ChatResponse:
        """
        Chat with the AI using the indexed documents.
        
        Args:
            query: User's question
            history: Optional conversation history
            
        Returns:
            ChatResponse with answer and citations
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the AI service"""
        return {
            "session_id": self.session_id,
            "strategy": self.__class__.__name__,
            "initialized": self._initialized,
            "available": self.is_available(),
        }
    
    def cleanup(self) -> None:
        """Cleanup resources used by the AI service"""
        pass
