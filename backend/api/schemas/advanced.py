
"""
Advanced Features Schemas

Pydantic models for XLSX conversion, comparison, and (legacy) RAG endpoints.

NOTE:
- XLSX schemas are actively used by /advanced/xlsx/* endpoints.
- Comparison endpoints are typically served by comparison_router.py (/api/comparison).
- Unified AI endpoints use api.schemas.ai (preferred). RAG models below are kept
  only for backward compatibility unless you remove legacy RAG routes.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal


# ============================================================
# XLSX Conversion Schemas (ACTIVE)
# ============================================================

class XLSXConversionRequest(BaseModel):
    """Request to convert CSV to XLSX."""
    session_id: str = Field(..., description="Session ID")
    csv_filename: str = Field(..., description="CSV filename in session output")


class XLSXConversionResponse(BaseModel):
    """Response from XLSX conversion."""
    status: Literal["success", "error"] = Field(..., description="success or error")
    filename: str = Field(..., description="Output XLSX filename")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    message: str = Field(..., description="Status message")


# ============================================================
# Comparison Schemas (USED BY /comparison if still enabled)
# ============================================================

class ComparisonChange(BaseModel):
    """A detected change in comparison."""
    type: Literal["added", "removed", "modified", "same"] = Field(..., description="Change type")
    row_id: str = Field(..., description="Stable row identifier")
    row_index: Optional[int] = Field(None, ge=0)
    row_index_a: Optional[int] = Field(None, ge=0)
    row_index_b: Optional[int] = Field(None, ge=0)
    row_data: Optional[Dict[str, Any]] = None
    field_changes: Optional[List[Dict[str, Any]]] = None
    indicator: Optional[str] = None


class ComparisonRequest(BaseModel):
    """Request to compare files."""
    file_a_name: str = Field(..., description="First filename")
    file_b_name: str = Field(..., description="Second filename")
    ignore_case: bool = Field(False, description="Ignore case while comparing text")
    trim_whitespace: bool = Field(True, description="Trim whitespace before compare")
    similarity_pairing: bool = Field(True, description="Use similarity pairing for best match")
    similarity_threshold: float = Field(0.65, ge=0.0, le=1.0, description="Threshold for similarity pairing")


class ComparisonResponse(BaseModel):
    """Response from file comparison."""
    status: Literal["success", "error"] = Field(..., description="success or error")
    message: str = Field(..., description="Status message")
    similarity: float = Field(..., ge=0.0, le=1.0, description="Overall similarity ratio")
    added: int = Field(..., ge=0)
    removed: int = Field(..., ge=0)
    modified: int = Field(..., ge=0)
    same: int = Field(..., ge=0)
    total_changes: int = Field(..., ge=0)
    changes: List[ComparisonChange] = Field(default_factory=list)


# ============================================================
# RAG Schemas (LEGACY / BACKWARD COMPAT)
# Preferred: api.schemas.ai for /v2/ai routes
# ============================================================

class SourceDocument(BaseModel):
    """Citation source for RAG answer."""
    file: str = Field(..., description="Source filename")
    group: Optional[str] = Field(None, description="Group/category")
    snippet: str = Field(..., description="Context snippet from document")
    chunk_index: Optional[int] = Field(None, description="Chunk index in document")
    # Added for compatibility with newer RAG responses
    score: Optional[float] = Field(None, description="Retrieval score (if available)")


class RAGEmbeddingRequest(BaseModel):
    """Request to embed documents."""
    session_id: str = Field(..., description="Session ID")
    groups: Optional[List[str]] = Field(None, description="Optional group filter")


class RAGEmbeddingResponse(BaseModel):
    """Response from document embedding."""
    status: Literal["success", "partial", "error"] = Field(..., description="success, partial, or error")
    indexed_files: int = Field(..., ge=0, description="Number of files embedded")
    indexed_docs: int = Field(..., ge=0, description="Number of documents embedded")
    indexed_chunks: int = Field(..., ge=0, description="Number of chunks created")
    errors: List[str] = Field(default_factory=list, description="Any errors")
    message: str = Field(..., description="Status message")


class RAGQueryRequest(BaseModel):
    """Request to query RAG."""
    session_id: str = Field(..., description="Session ID")
    query: str = Field(..., min_length=1, description="User question/query")
    group_filter: Optional[str] = Field(None, description="Filter by group")
    file_filter: Optional[str] = Field(None, description="Filter by filename")


class RAGQueryResponse(BaseModel):
    """Response from RAG query."""
    status: Literal["success", "error"] = Field(..., description="success or error")
    answer: str = Field(..., description="Generated answer")
    sources: List[SourceDocument] = Field(default_factory=list, description="Source citations")
    message: str = Field(..., description="Status message")


class RAGClearRequest(BaseModel):
    """Request to clear RAG index."""
    session_id: str = Field(..., description="Session ID")


class RAGClearResponse(BaseModel):
    """Response from RAG clear."""
    status: Literal["success", "error"] = Field(..., description="success or error")
    message: str = Field(..., description="Status message")

