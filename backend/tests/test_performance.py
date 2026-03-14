"""
Phase 8.2 — Performance benchmarks for the RET v4 backend.

Covers:
  1. ZIP scan / conversion throughput (file-count scaling)
  2. Token creation / rotation throughput
  3. Embedding throughput (mocked for CI, real for manual runs)
  4. RAG graph latency breakdown (per-node timing with mocked LLM)

Usage:
    # Run all benchmarks (mocked, suitable for CI):
    python -m pytest tests/test_performance.py -v --tb=short

    # Or run directly:
    python tests/test_performance.py
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


# ── Helpers ──


def _timed(label: str):
    """Context manager that prints elapsed time."""

    class Timer:
        def __init__(self):
            self.elapsed_ms = 0.0

        def __enter__(self):
            self._start = time.perf_counter()
            return self

        def __exit__(self, *exc):
            self.elapsed_ms = (time.perf_counter() - self._start) * 1000
            print(f"  [{label}] {self.elapsed_ms:.1f} ms")

    return Timer()


# ── 1. Token creation / rotation throughput ──


class TestTokenThroughput:
    """Benchmark session creation and rotation under load."""

    @pytest.mark.asyncio
    async def test_create_100_sessions(self, async_db: AsyncSession, test_user):
        """Create 100 login sessions and measure throughput."""
        from api.services.session_service import create_login_session

        with _timed("100 session creates") as t:
            for _ in range(100):
                await create_login_session(async_db, test_user.id, "127.0.0.1", "bench")

        # Should complete in < 5s even on slow CI
        assert t.elapsed_ms < 5000, f"Too slow: {t.elapsed_ms:.0f} ms"

    @pytest.mark.asyncio
    async def test_token_rotation_chain(self, async_db: AsyncSession, test_user):
        """Rotate a token 20 times in sequence."""
        from api.services.session_service import create_login_session, validate_refresh_token

        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "bench")

        with (
            patch("api.services.session_service.settings") as mock_settings,
            _timed("20 rotations") as t,
        ):
            mock_settings.FEATURE_TOKEN_ROTATION = True
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            for _ in range(20):
                result = await validate_refresh_token(async_db, raw)
                assert result is not None
                raw = result["new_refresh_token"]

        assert t.elapsed_ms < 3000


# ── 2. Password hashing throughput ──


class TestHashingThroughput:
    def test_hash_10_passwords(self):
        """Argon2 hashing for 10 passwords — establish baseline."""
        from api.core.security import hash_password

        with _timed("10 password hashes") as t:
            for i in range(10):
                hash_password(f"BenchPass{i}!")

        # Argon2 is intentionally slow; 10 hashes should finish in < 20s
        assert t.elapsed_ms < 20000

    def test_verify_10_passwords(self):
        from api.core.security import hash_password, verify_password

        hashed = hash_password("BenchPass!")
        with _timed("10 password verifies") as t:
            for _ in range(10):
                verify_password("BenchPass!", hashed)

        assert t.elapsed_ms < 20000


# ── 3. JWT creation throughput ──


class TestJWTThroughput:
    def test_create_1000_access_tokens(self):
        from api.core.security import create_token

        with _timed("1000 access tokens") as t:
            for i in range(1000):
                create_token(
                    subject=str(i),
                    expires_delta=timedelta(minutes=30),
                    token_type="access",
                )

        assert t.elapsed_ms < 5000

    def test_verify_1000_tokens(self):
        from api.core.security import create_token, verify_token

        tokens = [
            create_token(subject=str(i), expires_delta=timedelta(minutes=30), token_type="access")
            for i in range(1000)
        ]

        with _timed("1000 token verifies") as t:
            for tok in tokens:
                verify_token(tok, token_type="access")

        assert t.elapsed_ms < 5000


# ── 4. Evaluation scoring throughput ──


class TestEvalScoringThroughput:
    def test_score_1000_cases(self):
        """Score function throughput — no I/O, pure computation."""
        from api.services.ai.langgraph.evaluation import EvalCase, score_eval_case

        case = EvalCase(
            case_id="bench",
            query="test",
            expected_answer_contains=["data", "result", "value"],
            expected_answer_not_contains=["error"],
            expected_citations=["[csv:0]", "[csv:1]"],
            expected_intent="factual",
            min_sources=2,
        )
        rag_result = {
            "answer": "The data shows result with value [csv:0] [csv:1]",
            "citations": ["[csv:0]", "[csv:1]"],
            "query_transformation": {"intent": "factual"},
            "sources": [{"file": "a.csv"}, {"file": "b.csv"}, {"file": "c.csv"}],
        }

        with _timed("1000 eval scores") as t:
            for _ in range(1000):
                score_eval_case(case, rag_result, latency_ms=50)

        assert t.elapsed_ms < 2000


# ── 5. Graph node latency (mocked LLM) ──


class TestGraphNodeLatency:
    @pytest.mark.asyncio
    async def test_transform_query_latency(self):
        """transform_query node with mocked LLM should be fast."""
        import json

        from api.services.ai.langgraph.nodes import transform_query

        llm_response = json.dumps({
            "intent": "factual",
            "keywords": ["DOI"],
            "filters": {},
            "expanded_query": "Find the DOI",
            "sub_queries": [],
        })

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch("api.services.ai.langgraph.nodes.async_chat_generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.RAG_ENABLE_QUERY_TRANSFORM = True
            mock_settings.FEATURE_DSPY_ENABLED = False
            mock_llm.return_value = llm_response

            state = {
                "query": "What is the DOI?",
                "session_id": "bench",
                "user_id": "bench-user",
            }

            with _timed("transform_query x100") as t:
                for _ in range(100):
                    await transform_query(state)

        assert t.elapsed_ms < 2000

    @pytest.mark.asyncio
    async def test_generate_answer_latency(self):
        """generate_answer node with mocked LLM should be fast."""
        from api.services.ai.langgraph.nodes import generate_answer

        with (
            patch("api.services.ai.langgraph.nodes.settings") as mock_settings,
            patch("api.services.ai.langgraph.nodes.async_chat_generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.FEATURE_DSPY_ENABLED = False
            mock_llm.return_value = "Answer about DOIs [csv:0]"

            state = {
                "query": "What are DOIs?",
                "session_id": "bench",
                "user_id": "bench-user",
                "context": "Context about DOIs with identifiers",
                "intent": "factual",
                "conversation_history": [],
            }

            with _timed("generate_answer x100") as t:
                for _ in range(100):
                    await generate_answer(state)

        assert t.elapsed_ms < 2000


# ── CLI entry point ──

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short", "-s"]))
