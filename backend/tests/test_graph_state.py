"""Tests for the RAG graph state and node contracts."""

from __future__ import annotations

import pytest

from api.services.ai.langgraph.state import RAGState, QueryTransform, SourceDoc


class TestRAGState:
    """Validate RAGState TypedDict contract."""

    def test_minimal_state(self):
        """Required keys only."""
        state: RAGState = {
            "query": "test question",
            "session_id": "s123",
            "user_id": "u456",
        }
        assert state["query"] == "test question"

    def test_full_state(self):
        """All optional keys populated."""
        state: RAGState = {
            "query": "test",
            "session_id": "s1",
            "user_id": "u1",
            "thread_id": "t1",
            "group_filter": "articles",
            "top_k": 20,
            "conversation_history": [{"role": "user", "content": "hi"}],
            "query_transform": {
                "transformed_query": "expanded test",
                "intent": "factual",
                "sub_queries": [],
                "keywords": ["test"],
                "filters": {},
            },
            "search_query": "expanded test",
            "intent": "factual",
            "extra_queries": [],
            "query_embeddings": [[0.1, 0.2]],
            "query_tokens": ["test"],
            "ranked_lists": [],
            "ranked_weights": [0.7],
            "hits": [],
            "context": "Some context",
            "context_sufficient": True,
            "raw_answer": "Raw answer text",
            "answer": "Final answer",
            "citations_valid": True,
            "sources": [],
            "citations": ["[csv:0]"],
            "visualizations": [],
            "start_time": 1000.0,
            "query_time_ms": 500,
            "error": None,
            "response_type": "factual",
            "early_exit": False,
            "early_exit_answer": "",
            "hitl_required": False,
            "hitl_reason": "",
            "hitl_decision": "",
            "hitl_edited_answer": "",
        }
        assert state["intent"] == "factual"
        assert state["context_sufficient"] is True


class TestQueryTransform:
    def test_structure(self):
        qt: QueryTransform = {
            "transformed_query": "expanded query",
            "intent": "analytical",
            "sub_queries": ["q1", "q2"],
            "keywords": ["kw1"],
            "filters": {"group": "articles"},
        }
        assert qt["intent"] == "analytical"


class TestSourceDoc:
    def test_structure(self):
        sd: SourceDoc = {
            "file": "data.csv",
            "group": "articles",
            "snippet": "Some text...",
            "chunk_index": 0,
            "score": 0.95,
        }
        assert sd["score"] == 0.95
