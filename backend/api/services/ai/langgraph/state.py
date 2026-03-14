"""
LangGraph RAG State — Typed state flowing through the graph.

Every node reads from and writes to this state dict.
LangGraph uses TypedDict for type-safe state management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class QueryTransform(TypedDict, total=False):
    """Result of LLM-based query analysis."""
    transformed_query: str
    intent: str
    sub_queries: List[str]
    keywords: List[str]
    filters: Dict[str, Optional[str]]


class SourceDoc(TypedDict, total=False):
    """Citation source returned to the caller."""
    file: str
    group: Optional[str]
    snippet: str
    chunk_index: Optional[int]
    score: Optional[float]


class _RAGStateRequired(TypedDict):
    """Keys that are always present from initial invocation."""
    query: str
    session_id: str
    user_id: str


class RAGState(_RAGStateRequired, total=False):
    """
    Complete state for the RAG graph.

    Fields are populated progressively as nodes execute.
    Nodes MUST only write to their designated output keys.

    The three keys in _RAGStateRequired are always set by the caller,
    so direct ``state["query"]`` access is safe and type-clean.
    """

    # ── Input (set by the caller before graph invocation) ──
    thread_id: str
    group_filter: Optional[str]
    top_k: int
    conversation_history: List[Dict[str, str]]

    # ── Query transformation (node: transform_query) ──
    query_transform: Optional[QueryTransform]
    search_query: str
    intent: str
    extra_queries: List[str]

    # ── Retrieval intermediate (node: embed_query, retrieve_*) ──
    query_embeddings: List[List[float]]
    query_tokens: List[str]
    ranked_lists: List[Any]       # List[List[RetrievalResult]] — kept as Any to avoid circular import
    ranked_weights: List[float]

    # ── Post-retrieval (node: fuse_rerank) ──
    hits: List[Any]               # List[RetrievalResult]

    # ── Context assembly (node: build_context) ──
    context: str
    context_sufficient: bool

    # ── Generation (node: generate_answer) ──
    raw_answer: str

    # ── Citation repair (node: validate_citations) ──
    answer: str
    citations_valid: bool

    # ── Response assembly (node: assemble_response) ──
    sources: List[SourceDoc]
    citations: List[str]
    visualizations: List[Any]

    # ── Timing / metadata ──
    start_time: float
    query_time_ms: int
    error: Optional[str]
    response_type: str

    # ── Early-exit signal ──
    early_exit: bool
    early_exit_answer: str

    # ── HITL (human-in-the-loop) ──
    hitl_required: bool
    hitl_reason: str
    hitl_decision: str                 # "approve" | "reject" | "edit" | ""
    hitl_edited_answer: str            # user-edited answer (if decision == "edit")
    confidence_score: float            # 0.0–1.0, computed from retrieval quality
