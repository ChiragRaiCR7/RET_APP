
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from enum import Enum


# ============================================================
# Embedding (Manual) Schemas
# ============================================================

class EmbeddingMode(str, Enum):
    """Embedding mode"""
    FAST = "fast"  # Quick embedding with smaller chunks
    FULL = "full"  # Full embedding with larger context
    AUTO = "auto"  # Auto-select strategy based on size (NOT auto-embedding)


class EmbeddingRequest(BaseModel):
    """Request to embed groups from a session (manual indexing)"""
    session_id: str = Field(..., description="Session ID")
    groups: Optional[List[str]] = Field(None, description="Groups to embed (optional)")
    mode: EmbeddingMode = Field(default=EmbeddingMode.AUTO, description="Embedding mode")


class EmbeddingResponse(BaseModel):
    """Response from embedding operation"""
    status: Literal["success", "queued", "error"] = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Embedding statistics and details")


# ============================================================
# Chat Schemas (Legacy / Compatibility)
# ============================================================

class ChatRequest(BaseModel):
    """Request for chat or query"""
    session_id: str = Field(..., description="Session ID")
    question: Optional[str] = Field(None, description="User question")
    message: Optional[str] = Field(None, description="Alias for question (frontend compatibility)")
    messages: Optional[List[Dict[str, str]]] = Field(None, description="Conversation messages")
    instructions: Optional[str] = Field(None, description="Optional session instructions")
    use_rag: bool = Field(True, description="Enable RAG retrieval")
    top_k: int = Field(default=8, ge=1, le=50, description="Top-K chunks to retrieve")


class SourceDocument(BaseModel):
    """Source document citation"""
    file: str = Field(..., description="Source filename")
    group: Optional[str] = Field(None, description="Group/category")
    snippet: str = Field(..., description="Context snippet")
    score: Optional[float] = Field(None, description="Retrieval score (if available)")
    chunk_index: Optional[int] = Field(None, description="Chunk index in document")


class VisualizationArtifact(BaseModel):
    """Static visualization artifact (e.g., chart image)"""
    type: str = Field(default="chart", description="Artifact type")
    format: str = Field(default="png", description="Artifact format/encoding")
    data: str = Field(..., description="Encoded artifact data (e.g., base64)")
    title: Optional[str] = Field(None, description="Title")
    chart_type: Optional[str] = Field(None, description="Chart type (bar/line/etc.)")


class RetrievalInfo(BaseModel):
    """Retrieval information for transparency"""
    doc: str = Field(..., description="Document identifier")
    score: float = Field(..., description="Retrieval score")
    snippet: str = Field(..., description="Snippet")
    method: Optional[str] = Field(None, description="vector, lexical, hybrid")


class ChatResponse(BaseModel):
    """Response from chat/query (legacy)"""
    answer: str = Field(..., description="Assistant answer")
    sources: List[SourceDocument] = Field(default_factory=list, description="Cited sources")
    retrievals: List[RetrievalInfo] = Field(default_factory=list, description="Retrieval debug info")
    query_plan: Optional[Dict[str, Any]] = Field(None, description="Optional query plan")


# ============================================================
# ZIP Scanning Schemas
# (Only keep if some AI-side flows still use them)
# ============================================================

class ZipScanRequest(BaseModel):
    """Request to scan a ZIP file"""
    session_id: str = Field(..., description="Session ID")
    custom_prefixes: Optional[List[str]] = Field(None, description="Optional custom group prefixes")
    max_files: int = Field(default=10000, ge=1, le=50000, description="Max files")
    max_depth: int = Field(default=50, ge=1, le=100, description="Max nested zip depth")


class ZipScanProgress(BaseModel):
    """ZIP scanning progress update"""
    progress: float = Field(..., ge=0.0, le=1.0, description="0.0 to 1.0")
    label: str = Field(..., description="Progress label")
    entries_done: int = Field(..., ge=0, description="Entries processed")
    entries_total: int = Field(..., ge=0, description="Total entries")
    xml_found: int = Field(..., ge=0, description="XML files found")
    elapsed_seconds: float = Field(..., ge=0.0, description="Elapsed time")


class GroupInfo(BaseModel):
    """Information about a detected group"""
    name: str = Field(..., description="Group name")
    file_count: int = Field(..., ge=0, description="File count")
    total_size_bytes: int = Field(..., ge=0, description="Total size in bytes")


class ZipScanResponse(BaseModel):
    """Response from ZIP scanning"""
    status: str = Field(..., description="success or error")
    message: str = Field(..., description="Status message")
    xml_count: int = Field(..., ge=0, description="Number of XMLs")
    groups: List[GroupInfo] = Field(default_factory=list, description="Detected groups")
    total_extracted_bytes: int = Field(..., ge=0, description="Total extracted bytes")
    elapsed_seconds: float = Field(..., ge=0.0, description="Elapsed time")
    errors: List[str] = Field(default_factory=list, description="Any errors")


# ============================================================
# Comparison Schemas (keep only if still used somewhere)
# ============================================================

class CompareZipsRequest(BaseModel):
    """Request to compare two ZIP files"""
    session_id: str = Field(..., description="Session ID")
    left_filename: str = Field(..., description="Left ZIP filename")
    right_filename: str = Field(..., description="Right ZIP filename")
    selected_groups: Optional[List[str]] = Field(None, description="Optional selected groups")
    max_files: int = Field(default=5000, ge=1, le=20000, description="Max files to compare")


class FileComparisonInfo(BaseModel):
    """Comparison info for a single file"""
    filename: str = Field(..., description="Filename")
    logical_path: str = Field(..., description="Logical path")
    group: str = Field(..., description="Group")
    status: str = Field(..., description="added, removed, modified, same")
    left_row_count: int = Field(default=0, ge=0)
    right_row_count: int = Field(default=0, ge=0)
    rows_added: int = Field(default=0, ge=0)
    rows_removed: int = Field(default=0, ge=0)


class GroupComparisonInfo(BaseModel):
    """Comparison info for a group"""
    group: str = Field(..., description="Group")
    files_added: int = Field(default=0, ge=0)
    files_removed: int = Field(default=0, ge=0)
    files_modified: int = Field(default=0, ge=0)
    files_unchanged: int = Field(default=0, ge=0)
    rows_added: int = Field(default=0, ge=0)
    rows_removed: int = Field(default=0, ge=0)


class CompareZipsResponse(BaseModel):
    """Response from ZIP comparison"""
    status: str = Field(..., description="success or error")
    left_zip_name: str = Field(..., description="Left ZIP name")
    right_zip_name: str = Field(..., description="Right ZIP name")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Summary")
    group_comparisons: List[GroupComparisonInfo] = Field(default_factory=list)
    file_comparisons: List[FileComparisonInfo] = Field(default_factory=list)
    elapsed_seconds: float = Field(..., ge=0.0)
    errors: List[str] = Field(default_factory=list)


# ============================================================
# RAG Status Schemas
# ============================================================

class RAGStatus(BaseModel):
    """Status of RAG system for a session"""
    session_id: str = Field(..., description="Session ID")
    is_indexed: bool = Field(..., description="Whether session has indexed chunks")
    collection_name: Optional[str] = Field(None, description="Collection name")
    document_count: int = Field(default=0, ge=0, description="Number of docs indexed")
    groups_indexed: List[str] = Field(default_factory=list, description="Groups indexed")
    last_indexed: Optional[str] = Field(None, description="ISO timestamp")
    embedding_mode: Optional[EmbeddingMode] = Field(None, description="Last embedding mode used")


class AdminAIConfig(BaseModel):
    """AI configuration from admin panel (auto-embedding removed)"""
    default_collection: str = Field(default="documents", description="Default collection")
    chunk_size: int = Field(default=10000, ge=1000, le=50000, description="Chunk size")
    retrieval_top_k: int = Field(default=16, ge=1, le=100, description="Top-k for retrieval")
    hybrid_alpha: float = Field(default=0.70, ge=0.0, le=1.0, description="Hybrid alpha")
    hybrid_beta: float = Field(default=0.30, ge=0.0, le=1.0, description="Hybrid beta")


# ============================================================
# AI Session Schemas
# ============================================================

class SessionMessage(BaseModel):
    """A single chat message in a session"""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    sources: Optional[List[SourceDocument]] = Field(None, description="Sources/citations")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class AISessionState(BaseModel):
    """State of an AI chat session"""
    session_id: str = Field(..., description="Session ID")
    messages: List[SessionMessage] = Field(default_factory=list)
    instructions: str = Field(default="", description="Session instructions")
    created_at: Optional[str] = Field(None, description="Created timestamp")
    updated_at: Optional[str] = Field(None, description="Updated timestamp")
    indexed_groups: List[str] = Field(default_factory=list)
    document_count: int = Field(default=0, ge=0)


class CreateSessionRequest(BaseModel):
    """Request to create a new AI session"""
    instructions: Optional[str] = Field(default="", description="Initial instructions")


class CreateSessionResponse(BaseModel):
    """Response from creating an AI session"""
    session_id: str = Field(..., description="Session ID")
    messages: List[SessionMessage] = Field(default_factory=list)
    instructions: str = Field(default="")


class UpdateSessionRequest(BaseModel):
    """Request to update AI session instructions"""
    instructions: str = Field(..., description="New instructions")


class SessionListItem(BaseModel):
    """Summary info for listing sessions"""
    session_id: str = Field(..., description="Session ID")
    message_count: int = Field(..., ge=0, description="Message count")
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


# ============================================================
# Enhanced RAG Chat Schemas (used by /v2/ai/chat)
# ============================================================

class RAGChatRequest(BaseModel):
    """Request for RAG-based chat"""
    session_id: str = Field(..., description="Session ID")
    message: Optional[str] = Field(None, description="Message")
    question: Optional[str] = Field(None, description="Alias for message (frontend compatibility)")
    use_rag: bool = Field(True, description="Use retrieval")
    top_k: int = Field(default=16, ge=1, le=50, description="Top-K")
    group_filter: Optional[str] = Field(None, description="Group filter")
    file_filter: Optional[str] = Field(None, description="File filter")
    history: Optional[List[Dict[str, str]]] = Field(None, description="Optional history")
    thread_id: Optional[str] = Field(None, description="Thread ID for conversation continuity and checkpointing")

    @property
    def query(self) -> str:
        """Get the query from either message or question field"""
        return self.message or self.question or ""


class QueryTransformationInfo(BaseModel):
    """Information about query transformation (Advanced RAG)"""
    original: str = Field(..., description="Original query")
    transformed: str = Field(..., description="Transformed query")
    intent: str = Field(default="factual", description="factual, analytical, summary, exploratory, specific")
    sub_queries: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    filters: Dict[str, str] = Field(default_factory=dict)


class RetrievalMetadata(BaseModel):
    """Metadata about the retrieval process"""
    retrieval_strategy: str = Field(default="hybrid", description="vector, lexical, hybrid, summary, fusion")
    chunks_retrieved: int = Field(default=0, ge=0)
    vector_results: int = Field(default=0, ge=0)
    lexical_results: int = Field(default=0, ge=0)
    summary_results: int = Field(default=0, ge=0)
    timing: Optional[Dict[str, float]] = Field(None, description="Timing breakdown")


class SourceDocumentAdvanced(SourceDocument):
    """Enhanced source document with retrieval details"""
    rank: int = Field(default=0, ge=0)
    retrieval_method: str = Field(default="unknown", description="vector, lexical, summary, fusion")
    fusion_score: Optional[float] = Field(None)


class RAGChatResponse(BaseModel):
    """Response from RAG chat with Advanced RAG metadata"""
    answer: str = Field(..., description="Answer")
    sources: List[SourceDocument] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    query_time_ms: float = Field(..., ge=0.0)
    query_plan: Optional[Dict[str, Any]] = Field(default=None)
    chunks_retrieved: int = Field(default=0, ge=0)
    response_type: Optional[str] = Field(default=None, description="factual, analytical, comparison, trend, summary")
    visualizations: List[VisualizationArtifact] = Field(default_factory=list)

    # Advanced RAG metadata
    query_transformation: Optional[QueryTransformationInfo] = Field(default=None)
    retrieval_metadata: Optional[RetrievalMetadata] = Field(default=None)


# ============================================================
# Group Selection Schemas (Manual Indexing)
# ============================================================

class GroupSelectionRequest(BaseModel):
    """Request to select groups for indexing"""
    session_id: str = Field(..., description="Session ID")
    selected_groups: Optional[List[str]] = Field(None, description="Selected groups")
    groups: Optional[List[str]] = Field(None, description="Alias for selected_groups (frontend compatibility)")
    background: bool = Field(False, description="Run embedding in background worker")

    @property
    def group_list(self) -> List[str]:
        """Get the group list from either field"""
        return self.selected_groups or self.groups or []


class DetectedGroupsResponse(BaseModel):
    """Response with detected groups from ZIP scan (auto-embedding removed)"""
    session_id: str = Field(..., description="Session ID")
    groups: List[GroupInfo] = Field(default_factory=list)


# ============================================================
# Transcript Download Schema
# ============================================================

class TranscriptFormat(str, Enum):
    """Supported transcript export formats"""
    JSON = "json"
    TXT = "txt"
    MD = "markdown"


class TranscriptRequest(BaseModel):
    """Request to download chat transcript"""
    session_id: str = Field(..., description="Session ID")
    format: TranscriptFormat = Field(default=TranscriptFormat.JSON, description="Export format")
    include_sources: bool = Field(True, description="Include sources if available")


# ============================================================
# Feedback Schema
# ============================================================

class FeedbackRequest(BaseModel):
    """User feedback on a RAG answer (thumbs up/down)"""
    session_id: str = Field(..., description="Session ID")
    message_index: int = Field(..., ge=0, description="Index within conversation history")
    rating: int = Field(..., ge=-1, le=1, description="-1=bad, 0=neutral, 1=good")
    comment: Optional[str] = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    """Acknowledgement of feedback submission"""
    status: str = Field(default="ok")
    message: str = Field(default="Feedback recorded")


# ============================================================
# RAG Config Response (read-only exposure of settings)
# ============================================================

class RAGConfigResponse(BaseModel):
    """Public-facing RAG configuration (read-only)"""
    chunk_size: int
    chunk_overlap: int
    max_context_chars: int
    max_chunks: int
    vector_weight: float
    lexical_weight: float
    summary_weight: float
    top_k_vector: int
    top_k_summary: int
    enable_query_transform: bool
    enable_summaries: bool
    enable_citation_repair: bool
    rrf_k: int


# ============================================================
# HITL (Human-in-the-Loop) Schemas
# ============================================================

class HITLResumeRequest(BaseModel):
    """Resume a HITL-interrupted graph execution."""
    thread_id: str = Field(..., description="Thread ID of the interrupted conversation")
    session_id: str = Field(..., description="Session ID for ownership verification")
    decision: str = Field(
        "approve",
        description="Review decision: 'approve', 'reject', or 'edit'",
        pattern=r"^(approve|reject|edit)$",
    )
    edited_answer: Optional[str] = Field(
        None,
        description="Replacement answer text when decision is 'edit'",
    )


class HITLResumeResponse(BaseModel):
    """Response after resuming a HITL-interrupted execution."""
    answer: str = Field(..., description="Final answer (possibly edited)")
    sources: List[SourceDocument] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    query_time_ms: int = Field(0)
    hitl_decision: Optional[str] = Field(None, description="The decision that was applied")
    error: bool = Field(False)
    response_type: Optional[str] = None