from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum


class IndexMode(str, Enum):
    """Indexing mode"""
    FAST = "fast"  # Quick indexing with smaller chunks
    FULL = "full"  # Full indexing with larger context
    AUTO = "auto"  # Auto-detect based on size


class IndexRequest(BaseModel):
    """Request to index CSV files from a session"""
    session_id: str
    groups: Optional[List[str]] = None
    mode: IndexMode = IndexMode.AUTO


class IndexResponse(BaseModel):
    """Response from indexing operation"""
    status: str
    message: str
    stats: Dict[str, Any]


class ChatRequest(BaseModel):
    """Request for chat or query"""
    session_id: str
    question: Optional[str] = None
    message: Optional[str] = None  # Alias for question (frontend compatibility)
    messages: Optional[List[Dict[str, str]]] = None  # For conversation
    instructions: Optional[str] = None  # Optional session instructions
    use_rag: bool = True  # Enable RAG retrieval
    top_k: int = Field(default=8, ge=1, le=50)


class SourceDocument(BaseModel):
    """Source document citation"""
    file: str
    group: Optional[str] = None
    snippet: str
    score: Optional[float] = None
    chunk_index: Optional[int] = None


class RetrievalInfo(BaseModel):
    """Retrieval information for transparency"""
    doc: str
    score: float
    snippet: str
    method: Optional[str] = None  # vector, lexical, hybrid


class ChatResponse(BaseModel):
    """Response from chat/query"""
    answer: str
    sources: List[SourceDocument] = []
    retrievals: List[RetrievalInfo] = []
    query_plan: Optional[Dict[str, Any]] = None


# ============================================================
# ZIP Scanning Schemas
# ============================================================

class ZipScanRequest(BaseModel):
    """Request to scan a ZIP file"""
    session_id: str
    custom_prefixes: Optional[List[str]] = None
    max_files: int = Field(default=10000, ge=1, le=50000)
    max_depth: int = Field(default=50, ge=1, le=100)


class ZipScanProgress(BaseModel):
    """ZIP scanning progress update"""
    progress: float  # 0.0 to 1.0
    label: str
    entries_done: int
    entries_total: int
    xml_found: int
    elapsed_seconds: float


class GroupInfo(BaseModel):
    """Information about a detected group"""
    name: str
    file_count: int
    total_size_bytes: int


class ZipScanResponse(BaseModel):
    """Response from ZIP scanning"""
    status: str
    message: str
    xml_count: int
    groups: List[GroupInfo]
    total_extracted_bytes: int
    elapsed_seconds: float
    errors: List[str] = []


# ============================================================
# Auto-Index Schemas
# ============================================================

class AutoIndexRequest(BaseModel):
    """Request for auto-indexing based on admin config"""
    session_id: str
    groups: List[str]  # Groups to index
    mode: IndexMode = IndexMode.AUTO


class AutoIndexStatus(BaseModel):
    """Status of auto-indexing"""
    session_id: str
    status: str  # pending, in_progress, completed, failed
    progress: float = 0.0
    groups_indexed: List[str] = []
    groups_pending: List[str] = []
    error: Optional[str] = None


# ============================================================
# Comparison Schemas
# ============================================================

class CompareZipsRequest(BaseModel):
    """Request to compare two ZIP files"""
    session_id: str
    left_filename: str
    right_filename: str
    selected_groups: Optional[List[str]] = None
    max_files: int = Field(default=5000, ge=1, le=20000)


class FileComparisonInfo(BaseModel):
    """Comparison info for a single file"""
    filename: str
    logical_path: str
    group: str
    status: str  # added, removed, modified, same
    left_row_count: int = 0
    right_row_count: int = 0
    rows_added: int = 0
    rows_removed: int = 0


class GroupComparisonInfo(BaseModel):
    """Comparison info for a group"""
    group: str
    files_added: int = 0
    files_removed: int = 0
    files_modified: int = 0
    files_unchanged: int = 0
    rows_added: int = 0
    rows_removed: int = 0


class CompareZipsResponse(BaseModel):
    """Response from ZIP comparison"""
    status: str
    left_zip_name: str
    right_zip_name: str
    summary: Dict[str, Any]
    group_comparisons: List[GroupComparisonInfo]
    file_comparisons: List[FileComparisonInfo]
    elapsed_seconds: float
    errors: List[str] = []


# ============================================================
# RAG Status Schemas
# ============================================================

class RAGStatus(BaseModel):
    """Status of RAG system for a session"""
    session_id: str
    is_indexed: bool
    collection_name: Optional[str] = None
    document_count: int = 0
    groups_indexed: List[str] = []
    last_indexed: Optional[str] = None
    index_mode: Optional[IndexMode] = None


class AdminAIConfig(BaseModel):
    """AI configuration from admin panel"""
    auto_indexed_groups: List[str] = []
    default_collection: str = "documents"
    chunk_size: int = Field(default=10000, ge=1000, le=50000)
    retrieval_top_k: int = Field(default=16, ge=1, le=100)
    hybrid_alpha: float = Field(default=0.70, ge=0.0, le=1.0)
    hybrid_beta: float = Field(default=0.30, ge=0.0, le=1.0)


# ============================================================
# AI Session Schemas
# ============================================================

class SessionMessage(BaseModel):
    """A single chat message in a session"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: Optional[str] = None


class AISessionState(BaseModel):
    """State of an AI chat session"""
    session_id: str
    messages: List[SessionMessage] = []
    instructions: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """Request to create a new AI session"""
    instructions: Optional[str] = ""


class CreateSessionResponse(BaseModel):
    """Response from creating an AI session"""
    session_id: str
    messages: List[SessionMessage] = []
    instructions: str = ""


class UpdateSessionRequest(BaseModel):
    """Request to update AI session instructions"""
    instructions: str


class SessionListItem(BaseModel):
    """Summary info for listing sessions"""
    session_id: str
    message_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

