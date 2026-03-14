"""Tests for RAG graph node functions.

All LLM and embedding calls are mocked; these tests validate
input/output contracts and branching logic.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.ai.langgraph.state import RAGState


def _base_state(**overrides) -> RAGState:
    """Create a minimal RAGState with optional overrides."""
    state: dict = {
        "query": "What is the DOI?",
        "session_id": "test-session",
        "user_id": "test-user",
    }
    state.update(overrides)
    return state  # type: ignore[return-value]


# ── transform_query ──


class TestTransformQuery:
    @pytest.mark.asyncio
    async def test_disabled_returns_passthrough(self):
        """When RAG_ENABLE_QUERY_TRANSFORM is False, query passes through."""
        from api.services.ai.langgraph.nodes import transform_query

        with patch("api.services.ai.langgraph.nodes.settings") as mock_settings:
            mock_settings.RAG_ENABLE_QUERY_TRANSFORM = False
            result = await transform_query(_base_state())

        assert result["search_query"] == "What is the DOI?"
        assert result["intent"] == "factual"
        assert result["query_transform"] is None

    @pytest.mark.asyncio
    async def test_successful_transform(self):
        """Valid LLM JSON response is parsed correctly."""
        from api.services.ai.langgraph.nodes import transform_query

        llm_response = json.dumps({
            "intent": "analytical",
            "keywords": ["DOI", "identifier"],
            "filters": {"group": "articles"},
            "expanded_query": "What is the Digital Object Identifier (DOI)?",
            "sub_queries": ["What DOIs exist?"],
        })

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch("api.services.ai.langgraph.nodes.async_chat_generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.RAG_ENABLE_QUERY_TRANSFORM = True
            mock_settings.FEATURE_DSPY_ENABLED = False
            mock_llm.return_value = llm_response

            result = await transform_query(_base_state())

        assert result["intent"] == "analytical"
        assert result["search_query"] == "What is the Digital Object Identifier (DOI)?"
        assert "DOI" in result["query_transform"]["keywords"]

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(self):
        """Malformed LLM response falls back to defaults."""
        from api.services.ai.langgraph.nodes import transform_query

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch("api.services.ai.langgraph.nodes.async_chat_generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.RAG_ENABLE_QUERY_TRANSFORM = True
            mock_settings.FEATURE_DSPY_ENABLED = False
            mock_llm.return_value = "not json {{"

            result = await transform_query(_base_state())

        assert result["intent"] == "factual"
        assert result["query_transform"] is None

    @pytest.mark.asyncio
    async def test_invalid_intent_normalized(self):
        """Invalid intent in LLM response is normalized to 'factual'."""
        from api.services.ai.langgraph.nodes import transform_query

        llm_response = json.dumps({
            "intent": "INVALID_INTENT",
            "keywords": [],
            "filters": {},
            "expanded_query": "query",
            "sub_queries": [],
        })

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch("api.services.ai.langgraph.nodes.async_chat_generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.RAG_ENABLE_QUERY_TRANSFORM = True
            mock_settings.FEATURE_DSPY_ENABLED = False
            mock_llm.return_value = llm_response

            result = await transform_query(_base_state())

        assert result["intent"] == "factual"


# ── build_context ──


class TestBuildContext:
    @pytest.mark.asyncio
    async def test_empty_context_triggers_early_exit(self):
        """Thin context should set early_exit=True."""
        from api.services.ai.langgraph.nodes import build_context

        with patch(
            "api.services.advanced_ai_service.build_context_from_hits",
            return_value="(empty)",
        ):
            state = _base_state(hits=[])
            result = await build_context(state)

        assert result["early_exit"] is True
        assert result["context_sufficient"] is False

    @pytest.mark.asyncio
    async def test_sufficient_context(self):
        """Adequate context should pass through."""
        from api.services.ai.langgraph.nodes import build_context

        with patch(
            "api.services.advanced_ai_service.build_context_from_hits",
            return_value="A" * 100,
        ):
            state = _base_state(hits=[MagicMock()])
            result = await build_context(state)

        assert result["context_sufficient"] is True
        assert result.get("early_exit") is not True


# ── fuse_rerank ──


class TestFuseRerank:
    @pytest.mark.asyncio
    async def test_no_hits_early_exit(self):
        """No fused results should trigger early exit."""
        from api.services.ai.langgraph.nodes import fuse_rerank

        with patch("api.services.ai.langgraph.nodes._get_rag_service") as mock_svc:
            mock_svc.return_value = MagicMock()
            mock_svc.return_value._build_where.return_value = {}

            state = _base_state(
                ranked_lists=[],
                ranked_weights=[],
                query_tokens=[],
                query_embeddings=[],
                intent="factual",
                top_k=16,
            )

            with patch(
                "api.services.advanced_ai_service.UnifiedRAGService._apply_hybrid_scoring",
            ), patch(
                "api.services.advanced_ai_service.UnifiedRAGService._rrf_fusion",
                return_value=[],
            ):
                result = await fuse_rerank(state)

        assert result["early_exit"] is True
        assert result["hits"] == []


# ── generate_answer ──


class TestGenerateAnswer:
    @pytest.mark.asyncio
    async def test_generates_answer(self):
        """Answer generation produces raw_answer."""
        from api.services.ai.langgraph.nodes import generate_answer

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch("api.services.ai.langgraph.nodes.async_chat_generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.FEATURE_DSPY_ENABLED = False
            mock_llm.return_value = "The DOI is 10.1234 [csv:0]"

            state = _base_state(context="Context about DOIs", intent="factual")
            result = await generate_answer(state)

        assert result["raw_answer"] == "The DOI is 10.1234 [csv:0]"


# ── validate_citations ──


class TestValidateCitations:
    @pytest.mark.asyncio
    async def test_valid_citations_pass(self):
        """Valid citations should not trigger repair."""
        from api.services.ai.langgraph.nodes import validate_citations

        mock_hit = MagicMock()
        mock_hit.metadata = {"source": "csv"}

        with patch(
            "api.services.advanced_ai_service.extract_citations",
            return_value={"[csv:0]"},
        ):
            state = _base_state(raw_answer="Answer [csv:0]", hits=[mock_hit])
            result = await validate_citations(state)

        assert result["citations_valid"] is True
        assert result["answer"] == "Answer [csv:0]"

    @pytest.mark.asyncio
    async def test_invalid_citations_trigger_repair(self):
        """Invalid citations should trigger repair attempt."""
        from api.services.ai.langgraph.nodes import validate_citations

        mock_hit = MagicMock()
        mock_hit.metadata = {"source": "csv"}

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch(
                "api.services.advanced_ai_service.extract_citations",
                side_effect=[{"[csv:99]"}, {"[csv:0]"}],
            ),
            patch(
                "api.services.ai.langgraph.nodes.async_chat_generate",
                new_callable=AsyncMock,
                return_value="Repaired answer [csv:0]",
            ),
        ):
            mock_settings.FEATURE_DSPY_ENABLED = False

            state = _base_state(raw_answer="Answer [csv:99]", hits=[mock_hit])
            result = await validate_citations(state)

        assert "Repaired" in result["answer"]


# ── hitl_review ──


class TestHITLReview:
    @pytest.mark.asyncio
    async def test_passthrough_when_disabled(self):
        """HITL disabled should pass through."""
        from api.services.ai.langgraph.nodes import hitl_review

        with patch("api.services.ai.langgraph.nodes.settings") as mock_settings:
            mock_settings.FEATURE_HITL_ENABLED = False

            state = _base_state(
                answer="Good answer",
                citations_valid=True,
                hits=[MagicMock(similarity=0.9)],
                top_k=16,
            )
            result = await hitl_review(state)

        assert result["hitl_required"] is False

    @pytest.mark.asyncio
    async def test_passthrough_high_confidence(self):
        """High-confidence answers should pass through even with HITL enabled."""
        from api.services.ai.langgraph.nodes import hitl_review

        mock_hit = MagicMock(similarity=0.95)

        with patch("api.services.ai.langgraph.nodes.settings") as mock_settings:
            mock_settings.FEATURE_HITL_ENABLED = True
            mock_settings.RAG_HITL_CONFIDENCE_THRESHOLD = 0.35

            state = _base_state(
                answer="Good answer",
                citations_valid=True,
                hits=[mock_hit] * 5,
                top_k=5,
            )
            result = await hitl_review(state)

        assert result["hitl_required"] is False


# ── assemble_response ──


class TestAssembleResponse:
    @pytest.mark.asyncio
    async def test_assembles_sources(self):
        """Response assembly extracts sources from hits."""
        from api.services.ai.langgraph.nodes import assemble_response

        mock_hit = MagicMock()
        mock_hit.metadata = {"filename": "test.csv", "group": "articles", "chunk_index": 0}
        mock_hit.document = "Some document text"
        mock_hit.similarity = 0.85

        with (
            patch(
                "api.services.advanced_ai_service.extract_citations",
                return_value={"[csv:0]"},
            ),
            patch(
                "api.services.ai.visualization_service.render_chart_images_from_answer",
                return_value=[],
            ),
        ):
            state = _base_state(
                answer="Answer [csv:0]",
                hits=[mock_hit],
                start_time=1000.0,
            )
            result = await assemble_response(state)

        assert len(result["sources"]) == 1
        assert result["sources"][0]["file"] == "test.csv"
        assert result["citations"] == ["[csv:0]"]
