"""
DSPy Modules for RET v4 RAG Pipeline.

Wraps the three LLM-calling nodes (query transformation, answer generation,
citation repair) in DSPy ``Module`` / ``Signature`` abstractions.  When
``FEATURE_DSPY_ENABLED`` is True the graph nodes delegate to these modules
instead of making raw OpenAI calls, unlocking prompt optimisation via DSPy
teleprompters (BootstrapFewShot, MIPRO, etc.).

The modules are drop-in replacements for their raw-call counterparts in
``nodes.py``.  Each module mirrors the exact input/output contract of the
node it replaces so the graph state merging continues to work unchanged.

Requires:
    pip install dspy-ai
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy DSPy import — only loaded when FEATURE_DSPY_ENABLED is True
# ---------------------------------------------------------------------------

_dspy = None


def _ensure_dspy():
    """Import dspy lazily to avoid hard dependency when disabled."""
    global _dspy
    if _dspy is not None:
        return _dspy
    try:
        import dspy  # type: ignore[import-untyped]
        _dspy = dspy
        return _dspy
    except ImportError as exc:
        raise RuntimeError(
            "dspy-ai package is required when FEATURE_DSPY_ENABLED=True. "
            "Install it with: pip install dspy-ai"
        ) from exc


# ===================================================================
# DSPy LM Configuration
# ===================================================================

_configured = False


def configure_dspy_lm() -> None:
    """
    Configure DSPy to use the Azure OpenAI backend from RET settings.

    Must be called once at startup (guarded by ``_configured`` flag).
    """
    global _configured
    if _configured:
        return

    dspy = _ensure_dspy()
    from api.core.config import settings

    api_key = settings.AZURE_OPENAI_API_KEY or ""
    endpoint = str(settings.AZURE_OPENAI_ENDPOINT or "")
    model = settings.AZURE_OPENAI_CHAT_MODEL or "gpt-4o"
    api_version = settings.AZURE_OPENAI_API_VERSION or "2024-10-21"

    # DSPy uses "azure/<deployment>" format for Azure OpenAI
    lm = dspy.LM(
        model=f"azure/{model}",
        api_key=api_key,
        api_base=endpoint,
        api_version=api_version,
    )
    dspy.configure(lm=lm)
    _configured = True
    logger.info("DSPy configured with Azure OpenAI model: %s", model)


def reset_dspy_config() -> None:
    """Reset the configuration flag (for testing)."""
    global _configured
    _configured = False


# ===================================================================
# Signature: QueryTransform
# ===================================================================


def _get_query_transform_signature():
    """Build the QueryTransform Signature class lazily."""
    dspy = _ensure_dspy()

    class QueryTransformSignature(dspy.Signature):
        """Analyse a user query for a RAG data-analysis system.

        Given the user query, produce a JSON object with: intent, keywords,
        filters, expanded_query, and sub_queries.

        Intents: factual, analytical, summary, exploratory, specific,
        compare, statistical, trend, lookup.

        Keywords: 3-8 key search terms from the query.

        Filters: inferred group= or file= constraints (empty if none).

        expanded_query: a rephrased version adding synonyms and context.

        sub_queries: up to 3 decomposed sub-questions for complex queries."""

        query: str = dspy.InputField(desc="The user's natural-language question")
        analysis_json: str = dspy.OutputField(
            desc=(
                "A JSON object with keys: intent, keywords, filters, "
                "expanded_query, sub_queries"
            )
        )

    return QueryTransformSignature


class QueryTransformModule:
    """
    DSPy module wrapping query transformation.

    Replaces the raw LLM call in ``transform_query`` node.
    """

    def __init__(self) -> None:
        dspy = _ensure_dspy()
        sig = _get_query_transform_signature()
        self._predict = dspy.Predict(sig)

    def forward(self, query: str) -> Dict[str, Any]:
        """Execute query transformation and parse the JSON result."""
        result = self._predict(query=query)
        raw = result.analysis_json

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("DSPy QueryTransform returned non-JSON: %s", raw[:200])
            return {
                "transformed_query": query,
                "intent": "factual",
                "sub_queries": [],
                "keywords": [],
                "filters": {},
            }

        valid_intents = {
            "factual", "analytical", "summary", "exploratory",
            "specific", "compare", "comparison", "statistical", "trend", "lookup",
        }
        intent = parsed.get("intent", "factual").lower()
        if intent not in valid_intents:
            intent = "factual"

        sub_queries = parsed.get("sub_queries", [])
        if not isinstance(sub_queries, list):
            sub_queries = []
        sub_queries = [q for q in sub_queries if isinstance(q, str) and q.strip()][:3]

        keywords = parsed.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

        return {
            "transformed_query": parsed.get("expanded_query", query),
            "intent": intent,
            "sub_queries": sub_queries,
            "keywords": keywords,
            "filters": parsed.get("filters", {}),
        }


# ===================================================================
# Signature: AnswerGeneration
# ===================================================================


def _get_answer_generation_signature():
    """Build the AnswerGeneration Signature class lazily."""
    dspy = _ensure_dspy()

    class AnswerGenerationSignature(dspy.Signature):
        """Generate a comprehensive analytical answer using retrieved context.

        You are an enterprise data analyst assistant. Use ONLY the provided
        context to answer the question. Cite sources as [csv:N] or [xml:N].

        Use ```table``` blocks for structured data, ```stats``` for KPIs,
        ```chart``` for visualisations of 3+ items, and Mermaid for flows.

        Bold key numbers and statistics. If the data is insufficient, say so
        rather than guessing."""

        context: str = dspy.InputField(desc="Retrieved context blocks with [source:N] labels")
        question: str = dspy.InputField(desc="The user's question")
        intent: str = dspy.InputField(
            desc="Query intent: factual|analytical|summary|exploratory|compare|statistical|trend|lookup"
        )
        conversation_history: str = dspy.InputField(
            desc="Recent conversation turns for continuity (may be empty)"
        )
        answer: str = dspy.OutputField(
            desc=(
                "Analytical answer with citations [csv:N]/[xml:N], "
                "tables, stats blocks, and chart blocks as appropriate"
            )
        )

    return AnswerGenerationSignature


class AnswerGenerationModule:
    """
    DSPy module wrapping answer generation.

    Replaces the raw LLM call in ``generate_answer`` node.
    """

    def __init__(self) -> None:
        dspy = _ensure_dspy()
        sig = _get_answer_generation_signature()
        self._predict = dspy.ChainOfThought(sig)

    def forward(
        self,
        context: str,
        question: str,
        intent: str = "factual",
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate an answer and return the text."""
        history_text = ""
        if conversation_history:
            parts = []
            for msg in conversation_history[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                parts.append(f"{role}: {content}")
            history_text = "\n".join(parts)

        result = self._predict(
            context=context,
            question=question,
            intent=intent,
            conversation_history=history_text,
        )
        return result.answer


# ===================================================================
# Signature: CitationRepair
# ===================================================================


def _get_citation_repair_signature():
    """Build the CitationRepair Signature class lazily."""
    dspy = _ensure_dspy()

    class CitationRepairSignature(dspy.Signature):
        """Repair invalid citations in an AI-generated answer.

        Given the original answer and a set of allowed citation tags,
        replace or remove any citation that is not in the allowed set.
        Keep the answer text intact otherwise. Only modify citation markers."""

        answer_to_repair: str = dspy.InputField(desc="The answer text with possibly invalid citations")
        allowed_citations: str = dspy.InputField(desc="Comma-separated list of valid citation tags")
        repaired_answer: str = dspy.OutputField(desc="The answer with only valid citations")

    return CitationRepairSignature


class CitationRepairModule:
    """
    DSPy module wrapping citation repair.

    Replaces the raw LLM call in ``validate_citations`` node.
    """

    def __init__(self) -> None:
        dspy = _ensure_dspy()
        sig = _get_citation_repair_signature()
        self._predict = dspy.Predict(sig)

    def forward(self, answer: str, allowed_citations: List[str]) -> str:
        """Repair citations and return the corrected answer."""
        result = self._predict(
            answer_to_repair=answer,
            allowed_citations=", ".join(sorted(allowed_citations)),
        )
        return result.repaired_answer


# ===================================================================
# Module singletons — lazily created per-process
# ===================================================================

_query_transform_mod: Optional[QueryTransformModule] = None
_answer_gen_mod: Optional[AnswerGenerationModule] = None
_citation_repair_mod: Optional[CitationRepairModule] = None


def get_query_transform_module() -> QueryTransformModule:
    """Return (and lazily create) the QueryTransform DSPy module."""
    global _query_transform_mod
    configure_dspy_lm()
    if _query_transform_mod is None:
        _query_transform_mod = QueryTransformModule()
    return _query_transform_mod


def get_answer_generation_module() -> AnswerGenerationModule:
    """Return (and lazily create) the AnswerGeneration DSPy module."""
    global _answer_gen_mod
    configure_dspy_lm()
    if _answer_gen_mod is None:
        _answer_gen_mod = AnswerGenerationModule()
    return _answer_gen_mod


def get_citation_repair_module() -> CitationRepairModule:
    """Return (and lazily create) the CitationRepair DSPy module."""
    global _citation_repair_mod
    configure_dspy_lm()
    if _citation_repair_mod is None:
        _citation_repair_mod = CitationRepairModule()
    return _citation_repair_mod


def reset_modules() -> None:
    """Reset all module singletons (for testing or config changes)."""
    global _query_transform_mod, _answer_gen_mod, _citation_repair_mod
    _query_transform_mod = None
    _answer_gen_mod = None
    _citation_repair_mod = None
    reset_dspy_config()
