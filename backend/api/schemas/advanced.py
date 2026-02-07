"""
Advanced Features Schemas

Pydantic models for XLSX conversion, comparison, and RAG endpoints.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any


# ============================================================
# XLSX Conversion Schemas
# ============================================================


class XLSXConversionRequest(BaseModel):
    """Request to convert CSV to XLSX."""
    session_id: str = Field(..., description="Session ID")
    csv_filename: str = Field(..., description="CSV filename in session output")


class XLSXConversionResponse(BaseModel):
    """Response from XLSX conversion."""
    status: str = Field(..., description="success or error")
    filename: str = Field(..., description="Output XLSX filename")
    size_bytes: int = Field(..., description="File size in bytes")
    message: str = Field(..., description="Status message")


# ============================================================
# Comparison Schemas
# ============================================================


class ComparisonChange(BaseModel):
    """A detected change in comparison."""
    type: str  # "added", "removed", "modified", "same"
    row_id: str
    row_index: Optional[int] = None
    row_index_a: Optional[int] = None
    row_index_b: Optional[int] = None
    row_data: Optional[Dict[str, Any]] = None
    field_changes: Optional[List[Dict[str, Any]]] = None
    indicator: Optional[str] = None


class ComparisonRequest(BaseModel):
    """Request to compare files."""
    file_a_name: str
    file_b_name: str
    ignore_case: bool = False
    trim_whitespace: bool = True
    similarity_pairing: bool = True
    similarity_threshold: float = 0.65


class ComparisonResponse(BaseModel):
    """Response from file comparison."""
    status: str
    message: str
    similarity: float
    added: int
    removed: int
    modified: int
    same: int
    total_changes: int
    changes: List[ComparisonChange] = []


# ============================================================
# RAG Schemas
# ============================================================


class SourceDocument(BaseModel):
    """Citation source for RAG answer."""
    file: str = Field(..., description="Source filename")
    group: Optional[str] = Field(None, description="Group/category")
    snippet: str = Field(..., description="Context snippet from document")
    chunk_index: Optional[int] = Field(None, description="Chunk index in document")


class RAGEmbeddingRequest(BaseModel):
    """Request to embed documents."""
    session_id: str = Field(..., description="Session ID")
    groups: Optional[List[str]] = Field(None, description="Optional group filter")


class RAGEmbeddingResponse(BaseModel):
    """Response from document embedding."""
    status: str = Field(..., description="success, partial, or error")
    indexed_files: int = Field(..., description="Number of files embedded")
    indexed_docs: int = Field(..., description="Number of documents embedded")
    indexed_chunks: int = Field(..., description="Number of chunks created")
    errors: List[str] = Field(default_factory=list, description="Any errors")
    message: str = Field(..., description="Status message")


class RAGQueryRequest(BaseModel):
    """Request to query RAG."""
    session_id: str = Field(..., description="Session ID")
    query: str = Field(..., description="User question/query")
    group_filter: Optional[str] = Field(None, description="Filter by group")
    file_filter: Optional[str] = Field(None, description="Filter by filename")


class RAGQueryResponse(BaseModel):
    """Response from RAG query."""
    status: str = Field(..., description="success or error")
    answer: str = Field(..., description="Generated answer")
    sources: List[SourceDocument] = Field(default_factory=list, description="Source citations")
    message: str = Field(..., description="Status message")


class RAGClearRequest(BaseModel):
    """Request to clear RAG index."""
    session_id: str = Field(..., description="Session ID")


class RAGClearResponse(BaseModel):
    """Response from RAG clear."""
    status: str = Field(..., description="success or error")
    message: str = Field(..., description="Status message")
