from pydantic import BaseModel
from typing import List, Dict, Optional, Any


class IndexRequest(BaseModel):
    """Request to index CSV files from a session"""
    session_id: str
    groups: Optional[List[str]] = None


class IndexResponse(BaseModel):
    """Response from indexing operation"""
    status: str
    message: str
    stats: Dict[str, Any]


class ChatRequest(BaseModel):
    """Request for chat or query"""
    session_id: str
    question: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None  # For conversation


class SourceDocument(BaseModel):
    """Source document citation"""
    file: str
    group: Optional[str] = None
    snippet: str


class ChatResponse(BaseModel):
    """Response from chat/query"""
    answer: str
    sources: List[SourceDocument] = []

