"""
Evaluation Framework for RET v4 RAG Pipeline.

Provides:
1. ``EvalCase`` — dataclass for a single evaluation example
2. ``EvalDataset`` — collection of eval cases with serialisation
3. ``evaluate_rag()`` — run eval cases against the RAG pipeline and score
4. LangSmith trace integration for logging eval results

Usage::

    from api.services.ai.langgraph.evaluation import (
        EvalCase, EvalDataset, evaluate_rag,
    )

    dataset = EvalDataset.load("backend/eval/rag_cases.json")
    results = await evaluate_rag(dataset)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ===================================================================
# Data structures
# ===================================================================


@dataclass
class EvalCase:
    """A single evaluation example for the RAG pipeline."""

    # Unique identifier
    case_id: str

    # Input
    query: str
    group_filter: Optional[str] = None
    intent: Optional[str] = None  # Expected intent (if testing query transform)

    # Expected output
    expected_answer_contains: List[str] = field(default_factory=list)
    expected_answer_not_contains: List[str] = field(default_factory=list)
    expected_citations: List[str] = field(default_factory=list)  # e.g. ["[csv:0]"]
    expected_intent: Optional[str] = None
    min_sources: int = 0

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Scored result for a single evaluation case."""

    case_id: str
    passed: bool
    score: float  # 0.0 - 1.0

    # Sub-scores
    answer_contains_score: float = 0.0
    answer_not_contains_score: float = 0.0
    citation_score: float = 0.0
    intent_score: float = 0.0
    source_count_score: float = 0.0
    latency_ms: int = 0

    # Actual outputs for inspection
    actual_answer: str = ""
    actual_citations: List[str] = field(default_factory=list)
    actual_intent: Optional[str] = None
    actual_source_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalDataset:
    """Collection of evaluation cases."""

    name: str
    cases: List[EvalCase] = field(default_factory=list)
    version: str = "1.0"
    description: str = ""

    def save(self, path: str | Path) -> None:
        """Serialise to JSON."""
        data = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "cases": [asdict(c) for c in self.cases],
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "EvalDataset":
        """Load from JSON."""
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        cases = [EvalCase(**c) for c in raw.get("cases", [])]
        return cls(
            name=raw.get("name", p.stem),
            version=raw.get("version", "1.0"),
            description=raw.get("description", ""),
            cases=cases,
        )


# ===================================================================
# Scoring functions
# ===================================================================


def _score_contains(answer: str, expected: List[str]) -> float:
    """Score: what fraction of expected substrings are in the answer."""
    if not expected:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for e in expected if e.lower() in answer_lower)
    return hits / len(expected)


def _score_not_contains(answer: str, forbidden: List[str]) -> float:
    """Score: 1.0 if none of the forbidden substrings appear."""
    if not forbidden:
        return 1.0
    answer_lower = answer.lower()
    violations = sum(1 for f in forbidden if f.lower() in answer_lower)
    return max(0.0, 1.0 - violations / len(forbidden))


def _score_citations(actual: List[str], expected: List[str]) -> float:
    """Score: fraction of expected citations that appear in actual."""
    if not expected:
        return 1.0
    actual_set = set(actual)
    hits = sum(1 for c in expected if c in actual_set)
    return hits / len(expected)


def _score_intent(actual: Optional[str], expected: Optional[str]) -> float:
    """Score: 1.0 if intents match, 0.0 otherwise."""
    if not expected:
        return 1.0
    if not actual:
        return 0.0
    # Treat "compare" and "comparison" as equivalent
    normalise = {"comparison": "compare"}
    a = normalise.get(actual.lower(), actual.lower())
    e = normalise.get(expected.lower(), expected.lower())
    return 1.0 if a == e else 0.0


def _score_source_count(actual_count: int, min_expected: int) -> float:
    """Score: 1.0 if actual >= expected, scaled down otherwise."""
    if min_expected <= 0:
        return 1.0
    if actual_count >= min_expected:
        return 1.0
    return actual_count / min_expected


def score_eval_case(case: EvalCase, rag_result: Dict[str, Any], latency_ms: int) -> EvalResult:
    """Score a single RAG result against an eval case."""
    answer = rag_result.get("answer", "")
    citations = rag_result.get("citations", [])
    transform = rag_result.get("query_transformation") or {}
    actual_intent = transform.get("intent") if isinstance(transform, dict) else None
    sources = rag_result.get("sources", [])

    s_contains = _score_contains(answer, case.expected_answer_contains)
    s_not_contains = _score_not_contains(answer, case.expected_answer_not_contains)
    s_citations = _score_citations(citations, case.expected_citations)
    s_intent = _score_intent(actual_intent, case.expected_intent)
    s_sources = _score_source_count(len(sources), case.min_sources)

    # Weighted overall score
    weights = {
        "contains": 0.30,
        "not_contains": 0.10,
        "citations": 0.25,
        "intent": 0.15,
        "sources": 0.20,
    }
    overall = (
        s_contains * weights["contains"]
        + s_not_contains * weights["not_contains"]
        + s_citations * weights["citations"]
        + s_intent * weights["intent"]
        + s_sources * weights["sources"]
    )

    return EvalResult(
        case_id=case.case_id,
        passed=overall >= 0.7,
        score=round(overall, 4),
        answer_contains_score=round(s_contains, 4),
        answer_not_contains_score=round(s_not_contains, 4),
        citation_score=round(s_citations, 4),
        intent_score=round(s_intent, 4),
        source_count_score=round(s_sources, 4),
        latency_ms=latency_ms,
        actual_answer=answer[:1000],
        actual_citations=citations,
        actual_intent=actual_intent,
        actual_source_count=len(sources),
    )


# ===================================================================
# Runner
# ===================================================================


async def evaluate_rag(
    dataset: EvalDataset,
    *,
    session_id: str = "eval",
    user_id: str = "eval",
) -> List[EvalResult]:
    """
    Run all eval cases through the RAG pipeline and return scored results.

    Requires that test documents are indexed in the given session.
    """
    from api.services.ai.langgraph.graph import run_rag_graph

    results: List[EvalResult] = []

    for case in dataset.cases:
        t0 = time.time()
        try:
            rag_result = await run_rag_graph(
                query=case.query,
                session_id=session_id,
                user_id=user_id,
                group_filter=case.group_filter,
                thread_id=f"eval:{case.case_id}",
            )
            latency = int((time.time() - t0) * 1000)
            result = score_eval_case(case, rag_result, latency)
        except Exception as exc:
            latency = int((time.time() - t0) * 1000)
            result = EvalResult(
                case_id=case.case_id,
                passed=False,
                score=0.0,
                latency_ms=latency,
                error=str(exc),
            )
        results.append(result)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    avg_score = sum(r.score for r in results) / total if total else 0.0
    logger.info(
        "Evaluation complete: %d/%d passed (avg score: %.3f)",
        passed, total, avg_score,
    )

    return results


def save_eval_results(results: List[EvalResult], path: str | Path) -> None:
    """Save evaluation results to JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": time.time(),
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "avg_score": round(sum(r.score for r in results) / len(results), 4) if results else 0.0,
        "results": [r.to_dict() for r in results],
    }
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
