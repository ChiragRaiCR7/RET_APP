"""Tests for the evaluation framework scoring functions."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from api.services.ai.langgraph.evaluation import (
    EvalCase,
    EvalDataset,
    EvalResult,
    score_eval_case,
    _score_contains,
    _score_not_contains,
    _score_citations,
    _score_intent,
    _score_source_count,
)


# ── Atomic scoring ──


class TestScoreContains:
    def test_all_found(self):
        assert _score_contains("The quick brown fox", ["quick", "fox"]) == 1.0

    def test_partial_found(self):
        assert _score_contains("The quick brown fox", ["quick", "cat"]) == 0.5

    def test_none_found(self):
        assert _score_contains("The quick brown fox", ["cat", "dog"]) == 0.0

    def test_empty_expected(self):
        assert _score_contains("Anything", []) == 1.0

    def test_case_insensitive(self):
        assert _score_contains("DOI 10.1234", ["doi", "10."]) == 1.0


class TestScoreNotContains:
    def test_none_forbidden(self):
        assert _score_not_contains("Clean answer", ["bad", "wrong"]) == 1.0

    def test_one_violation(self):
        assert _score_not_contains("This is bad", ["bad", "wrong"]) == 0.5

    def test_all_violations(self):
        assert _score_not_contains("bad and wrong", ["bad", "wrong"]) == 0.0

    def test_empty_forbidden(self):
        assert _score_not_contains("Anything", []) == 1.0


class TestScoreCitations:
    def test_all_citations_present(self):
        assert _score_citations(["[csv:0]", "[csv:1]"], ["[csv:0]", "[csv:1]"]) == 1.0

    def test_partial_citations(self):
        assert _score_citations(["[csv:0]"], ["[csv:0]", "[csv:1]"]) == 0.5

    def test_no_citations(self):
        assert _score_citations([], ["[csv:0]"]) == 0.0

    def test_empty_expected(self):
        assert _score_citations([], []) == 1.0


class TestScoreIntent:
    def test_matching(self):
        assert _score_intent("factual", "factual") == 1.0

    def test_not_matching(self):
        assert _score_intent("factual", "analytical") == 0.0

    def test_compare_comparison_equivalent(self):
        assert _score_intent("comparison", "compare") == 1.0
        assert _score_intent("compare", "comparison") == 1.0

    def test_no_expected(self):
        assert _score_intent("anything", None) == 1.0

    def test_no_actual(self):
        assert _score_intent(None, "factual") == 0.0


class TestScoreSourceCount:
    def test_above_min(self):
        assert _score_source_count(5, 3) == 1.0

    def test_exact_min(self):
        assert _score_source_count(3, 3) == 1.0

    def test_below_min(self):
        assert _score_source_count(1, 4) == 0.25

    def test_zero_min(self):
        assert _score_source_count(0, 0) == 1.0


# ── Full case scoring ──


class TestScoreEvalCase:
    def test_perfect_score(self):
        case = EvalCase(
            case_id="test",
            query="What is the DOI?",
            expected_answer_contains=["DOI", "10."],
            expected_intent="factual",
            min_sources=1,
        )
        rag_result = {
            "answer": "The DOI is 10.1234/test",
            "citations": ["[csv:0]"],
            "query_transformation": {"intent": "factual"},
            "sources": [{"file": "test.csv"}],
        }
        result = score_eval_case(case, rag_result, latency_ms=100)
        assert result.passed is True
        assert result.score > 0.8

    def test_empty_answer(self):
        case = EvalCase(
            case_id="test",
            query="Something",
            expected_answer_contains=["data"],
            min_sources=1,
        )
        rag_result = {
            "answer": "",
            "citations": [],
            "query_transformation": None,
            "sources": [],
        }
        result = score_eval_case(case, rag_result, latency_ms=50)
        assert result.passed is False
        assert result.score <= 0.5


# ── Dataset serialisation ──


class TestEvalDataset:
    def test_save_and_load(self, tmp_path):
        dataset = EvalDataset(
            name="test-dataset",
            cases=[
                EvalCase(case_id="c1", query="Q1", expected_answer_contains=["a"]),
                EvalCase(case_id="c2", query="Q2", min_sources=2),
            ],
            description="Test dataset",
        )
        path = tmp_path / "cases.json"
        dataset.save(path)

        loaded = EvalDataset.load(path)
        assert loaded.name == "test-dataset"
        assert len(loaded.cases) == 2
        assert loaded.cases[0].case_id == "c1"
        assert loaded.cases[1].min_sources == 2

    def test_load_seed_dataset(self):
        """Validate the seed eval dataset can be loaded."""
        path = Path(__file__).parents[1] / "eval" / "rag_cases.json"
        if not path.exists():
            pytest.skip("Seed dataset not found")
        dataset = EvalDataset.load(path)
        assert len(dataset.cases) > 0
        assert all(c.case_id for c in dataset.cases)
