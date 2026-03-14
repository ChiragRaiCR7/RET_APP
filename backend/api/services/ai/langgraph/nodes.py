"""
LangGraph RAG Nodes — Async node functions for the RAG pipeline.

Each node is an async function that receives ``RAGState`` and returns a
partial state dict with the keys it owns.  LangGraph merges the return
value back into the running state automatically.

Nodes reuse existing primitives from ``advanced_ai_service`` (retrieval,
scoring, context building, citation extraction) and the shared async
client layer for LLM calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from api.core.config import settings
from api.core.prompts import (
    QUERY_TRANSFORM_SYSTEM_PROMPT,
    REFUSE_INSUFFICIENT_CONTEXT,
    REFUSE_INVALID_CITATIONS,
    REFUSE_NO_SOURCES,
    build_user_prompt,
    get_citation_repair_messages,
)
from api.services.ai.langgraph.client import async_chat_generate, async_embed_texts
from api.services.ai.langgraph.state import RAGState

logger = logging.getLogger(__name__)

# Re-use config constants from advanced_ai_service to stay in sync
_RETRIEVAL_TOP_K = int(getattr(settings, "RAG_TOP_K_VECTOR", 20))
_RETRIEVAL_TOP_K_SUMMARY = int(getattr(settings, "RAG_TOP_K_SUMMARY", 5))
_MAX_CONTEXT_CHARS = int(getattr(settings, "RAG_MAX_CONTEXT_CHARS", 40_000))
_MAX_CONTEXT_CHUNKS = int(getattr(settings, "RAG_MAX_CHUNKS", 15))
_AI_TEMPERATURE = float(getattr(settings, "RET_AI_TEMPERATURE", 0.65))
_AI_MAX_TOKENS = int(getattr(settings, "AI_MAX_TOKENS", 4000))
_HYBRID_ALPHA = float(getattr(settings, "RAG_VECTOR_WEIGHT", 0.70))
_HYBRID_BETA = float(getattr(settings, "RAG_LEXICAL_WEIGHT", 0.30))
_ENABLE_CITATION_REPAIR = bool(getattr(settings, "RAG_ENABLE_CITATION_REPAIR", True))
_CITATION_REPAIR_TEMP = float(getattr(settings, "RAG_CITATION_REPAIR_TEMPERATURE", 0.0))

# ---------------------------------------------------------------------------
# Helpers — thin wrappers around advanced_ai_service utilities
# ---------------------------------------------------------------------------

def _get_rag_service(session_id: str, user_id: str):
    """Lazily obtain the per-session UnifiedRAGService."""
    from api.services.advanced_ai_service import get_rag_service
    from api.services.storage_service import get_session_dir
    session_dir = get_session_dir(session_id)
    return get_rag_service(session_dir, session_id, user_id)


# ===================================================================
# NODE: transform_query
# ===================================================================

async def transform_query(state: RAGState) -> Dict[str, Any]:
    """LLM-based query analysis: intent, keywords, sub-queries, filters."""
    query = state["query"]

    if not getattr(settings, "RAG_ENABLE_QUERY_TRANSFORM", True):
        return {
            "query_transform": None,
            "search_query": query,
            "intent": "factual",
            "extra_queries": [],
        }

    # ── DSPy path ──
    if getattr(settings, "FEATURE_DSPY_ENABLED", False):
        return await _transform_query_dspy(state, query)

    # ── Raw LLM path ──
    try:
        messages = [
            {"role": "system", "content": QUERY_TRANSFORM_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        raw = await async_chat_generate(messages, temperature=0.1, max_tokens=500)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        parsed = json.loads(raw)

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
        extra_queries: List[str] = list(sub_queries)
        if keywords:
            extra_queries.append(" ".join(keywords[:8]))

        transform = {
            "transformed_query": parsed.get("expanded_query", query),
            "intent": intent,
            "sub_queries": sub_queries,
            "keywords": keywords,
            "filters": parsed.get("filters", {}),
        }

        # Apply inferred group filter if caller didn't specify one
        group_filter = state.get("group_filter")
        if not group_filter and transform.get("filters"):
            inferred = transform["filters"].get("group")
            if isinstance(inferred, str) and inferred.strip():
                group_filter = inferred

        return {
            "query_transform": transform,
            "search_query": transform["transformed_query"],
            "intent": intent,
            "extra_queries": extra_queries,
            "group_filter": group_filter,
        }

    except Exception as exc:
        logger.debug("Query transformation failed: %s", exc)
        return {
            "query_transform": None,
            "search_query": query,
            "intent": "factual",
            "extra_queries": [],
        }


async def _transform_query_dspy(state: RAGState, query: str) -> Dict[str, Any]:
    """DSPy-based query transformation (runs sync module in thread)."""
    try:
        from api.services.ai.langgraph.dspy_modules import get_query_transform_module

        mod = get_query_transform_module()
        parsed = await asyncio.to_thread(mod.forward, query)

        intent = parsed.get("intent", "factual")
        sub_queries = parsed.get("sub_queries", [])
        keywords = parsed.get("keywords", [])
        extra_queries: List[str] = list(sub_queries)
        if keywords:
            extra_queries.append(" ".join(keywords[:8]))

        transform = {
            "transformed_query": parsed.get("transformed_query", query),
            "intent": intent,
            "sub_queries": sub_queries,
            "keywords": keywords,
            "filters": parsed.get("filters", {}),
        }

        group_filter = state.get("group_filter")
        if not group_filter and transform.get("filters"):
            inferred = transform["filters"].get("group")
            if isinstance(inferred, str) and inferred.strip():
                group_filter = inferred

        return {
            "query_transform": transform,
            "search_query": transform["transformed_query"],
            "intent": intent,
            "extra_queries": extra_queries,
            "group_filter": group_filter,
        }
    except Exception as exc:
        logger.debug("DSPy query transformation failed: %s", exc)
        return {
            "query_transform": None,
            "search_query": query,
            "intent": "factual",
            "extra_queries": [],
        }


# ===================================================================
# NODE: embed_and_tokenize  (parallel: embedding API + CPU tokenization)
# ===================================================================

async def embed_and_tokenize(state: RAGState) -> Dict[str, Any]:
    """Embed query texts and extract lexical tokens in parallel."""
    from api.services.advanced_ai_service import extract_query_tokens

    search_query = state.get("search_query") or state["query"]
    extra_queries = state.get("extra_queries") or []

    query_texts = [search_query] + extra_queries

    # Run embedding (async I/O) and tokenization (CPU) concurrently
    embed_task = asyncio.create_task(async_embed_texts(query_texts))
    tokens = extract_query_tokens(search_query)
    embeddings = await embed_task

    return {
        "query_embeddings": embeddings,
        "query_tokens": tokens,
    }


# ===================================================================
# NODE: retrieve  (parallel vector searches via thread pool)
# ===================================================================

async def retrieve(state: RAGState) -> Dict[str, Any]:
    """
    Run all vector searches in parallel via asyncio.to_thread.

    Searches: main query, sub-queries, and summary collection.
    Produces ranked lists + weights for RRF fusion.
    """
    from api.services.advanced_ai_service import UnifiedRAGService

    session_id = state["session_id"]
    user_id = state["user_id"]
    svc = _get_rag_service(session_id, user_id)

    embeddings = state.get("query_embeddings", [])
    group_filter = state.get("group_filter")
    intent = state.get("intent", "factual")
    top_k = state.get("top_k", _RETRIEVAL_TOP_K)

    fetch_k = top_k
    if intent in ("summary", "exploratory", "statistical"):
        fetch_k = max(top_k, int(top_k * 1.5))

    # Build tasks — each ChromaDB query runs in a thread
    async def _vector_search(embedding, doc_type="chunk", k=fetch_k):
        where = svc._build_where(group_filter, doc_type=doc_type)
        return await asyncio.to_thread(svc.vector_store.query, embedding, top_k=k, where=where)

    search_tasks = []
    search_weights = []

    # Main query
    search_tasks.append(_vector_search(embeddings[0]))
    search_weights.append(_HYBRID_ALPHA)

    # Sub-query searches (embeddings[1:])
    for idx, emb in enumerate(embeddings[1:], start=1):
        search_tasks.append(_vector_search(emb))
        search_weights.append(max(0.15, _HYBRID_ALPHA * 0.5))

    # Summary search
    if getattr(settings, "RAG_ENABLE_SUMMARIES", True):
        search_tasks.append(
            _vector_search(embeddings[0], doc_type="summary", k=_RETRIEVAL_TOP_K_SUMMARY)
        )
        search_weights.append(float(getattr(settings, "RAG_SUMMARY_WEIGHT", 0.1)))

    results = await asyncio.gather(*search_tasks)

    return {
        "ranked_lists": list(results),
        "ranked_weights": search_weights,
    }


# ===================================================================
# NODE: fuse_rerank
# ===================================================================

async def fuse_rerank(state: RAGState) -> Dict[str, Any]:
    """Apply hybrid scoring, RRF fusion, and MMR re-ranking."""
    from api.services.advanced_ai_service import (
        UnifiedRAGService,
        extract_query_tokens,
    )

    ranked_lists = state.get("ranked_lists", [])
    weights = state.get("ranked_weights", [])
    query_tokens = state.get("query_tokens", [])
    embeddings = state.get("query_embeddings", [])
    intent = state.get("intent", "factual")
    top_k = state.get("top_k", _RETRIEVAL_TOP_K)
    session_id = state["session_id"]
    user_id = state["user_id"]

    svc = _get_rag_service(session_id, user_id)

    # Hybrid scoring in-place
    for hits in ranked_lists:
        UnifiedRAGService._apply_hybrid_scoring(hits, query_tokens)
        hits.sort(key=lambda h: h.similarity, reverse=True)

    # RRF fusion
    fused = UnifiedRAGService._rrf_fusion(ranked_lists, weights)

    # MMR diversification
    mmr_diversity = 0.25 if intent in ("analytical", "compare", "comparison") else 0.15
    if len(fused) > top_k and embeddings:
        fused = svc.vector_store.mmr_rerank(
            fused, embeddings[0], top_k=top_k, diversity=mmr_diversity,
        )

    hits = fused[:top_k]

    # Early exit if no hits
    if not hits:
        return {
            "hits": [],
            "early_exit": True,
            "early_exit_answer": REFUSE_NO_SOURCES,
        }

    return {"hits": hits, "early_exit": False, "early_exit_answer": ""}


# ===================================================================
# NODE: build_context
# ===================================================================

async def build_context(state: RAGState) -> Dict[str, Any]:
    """Assemble context string from retrieval hits."""
    from api.services.advanced_ai_service import build_context_from_hits

    hits = state.get("hits", [])
    context = build_context_from_hits(hits, max_chunks=_MAX_CONTEXT_CHUNKS)

    sufficient = len(context.strip()) >= 50 and context.strip() != "(empty)"

    if not sufficient:
        return {
            "context": context,
            "context_sufficient": False,
            "early_exit": True,
            "early_exit_answer": REFUSE_INSUFFICIENT_CONTEXT,
        }

    return {
        "context": context,
        "context_sufficient": True,
    }


# ===================================================================
# NODE: generate_answer
# ===================================================================

async def generate_answer(state: RAGState) -> Dict[str, Any]:
    """Generate an LLM answer using the assembled context."""
    query = state["query"]
    context = state.get("context", "")
    intent = state.get("intent", "factual")
    history = state.get("conversation_history", [])

    # ── DSPy path ──
    if getattr(settings, "FEATURE_DSPY_ENABLED", False):
        return await _generate_answer_dspy(query, context, intent, history)

    # ── Raw LLM path ──
    from api.core.prompts import ADVANCED_SYSTEM_PROMPT

    messages: list = [{"role": "system", "content": ADVANCED_SYSTEM_PROMPT}]

    # Append recent conversation history for continuity
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    user_content = build_user_prompt(query, context, intent=intent)
    messages.append({"role": "user", "content": user_content})

    answer = await async_chat_generate(
        messages, temperature=_AI_TEMPERATURE, max_tokens=_AI_MAX_TOKENS,
    )

    return {"raw_answer": answer}


async def _generate_answer_dspy(
    query: str,
    context: str,
    intent: str,
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """DSPy-based answer generation (runs sync module in thread)."""
    try:
        from api.services.ai.langgraph.dspy_modules import get_answer_generation_module

        mod = get_answer_generation_module()
        answer = await asyncio.to_thread(
            mod.forward, context, query, intent, history,
        )
        return {"raw_answer": answer}
    except Exception as exc:
        logger.warning("DSPy answer generation failed, falling back to raw LLM: %s", exc)
        # Fallback to raw LLM path
        from api.core.prompts import ADVANCED_SYSTEM_PROMPT

        messages: list = [{"role": "system", "content": ADVANCED_SYSTEM_PROMPT}]
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        user_content = build_user_prompt(query, context, intent=intent)
        messages.append({"role": "user", "content": user_content})
        answer = await async_chat_generate(
            messages, temperature=_AI_TEMPERATURE, max_tokens=_AI_MAX_TOKENS,
        )
        return {"raw_answer": answer}


# ===================================================================
# NODE: validate_citations
# ===================================================================

async def validate_citations(state: RAGState) -> Dict[str, Any]:
    """Validate and optionally repair citations in the generated answer."""
    from api.services.advanced_ai_service import extract_citations

    answer = state.get("raw_answer", "")
    hits = state.get("hits", [])

    citations_found = extract_citations(answer)
    allowed_citations = {
        f"[{hit.metadata.get('source', 'csv')}:{i}]"
        for i, hit in enumerate(hits)
    }

    invalid = citations_found - allowed_citations

    if invalid and citations_found and _ENABLE_CITATION_REPAIR:
        try:
            if getattr(settings, "FEATURE_DSPY_ENABLED", False):
                answer = await _citation_repair_dspy(answer, sorted(allowed_citations))
                citations_found = extract_citations(answer)
            else:
                repair_msgs = get_citation_repair_messages(answer, sorted(allowed_citations))
                repair_messages = [repair_msgs["system"], repair_msgs["user"]]
                repaired = await async_chat_generate(
                    repair_messages, temperature=_CITATION_REPAIR_TEMP, max_tokens=_AI_MAX_TOKENS,
                )
                if repaired and len(repaired) > 20:
                    answer = repaired
                    citations_found = extract_citations(answer)
        except Exception as exc:
            logger.warning("Citation repair failed: %s", exc)

    # Still no valid citations after repair?
    if citations_found and not (citations_found & allowed_citations):
        answer = REFUSE_INVALID_CITATIONS

    return {
        "answer": answer,
        "citations_valid": bool(not invalid or (citations_found & allowed_citations)),
    }


async def _citation_repair_dspy(answer: str, allowed_citations: list) -> str:
    """DSPy-based citation repair (runs sync module in thread)."""
    from api.services.ai.langgraph.dspy_modules import get_citation_repair_module

    mod = get_citation_repair_module()
    repaired = await asyncio.to_thread(mod.forward, answer, allowed_citations)
    if repaired and len(repaired) > 20:
        return repaired
    return answer


# ===================================================================
# NODE: hitl_review
# ===================================================================

# Confidence thresholds for HITL gating
_HITL_LOW_CONFIDENCE_THRESHOLD = float(
    getattr(settings, "RAG_HITL_CONFIDENCE_THRESHOLD", 0.35)
)


def _compute_confidence(state: RAGState) -> float:
    """
    Heuristic confidence score (0.0–1.0) based on retrieval quality
    and citation validity.
    """
    hits = state.get("hits", [])
    if not hits:
        return 0.0

    # Average similarity of top hits (capped at top-5 for stability)
    top = hits[: min(5, len(hits))]
    avg_sim = sum(getattr(h, "similarity", 0.0) for h in top) / len(top) if top else 0.0

    # Penalty for failed citation validation
    cit_penalty = 0.0 if state.get("citations_valid", True) else 0.20

    # Penalty for very few hits relative to request
    coverage = min(len(hits) / max(state.get("top_k", 16), 1), 1.0)
    coverage_penalty = max(0.0, 0.15 * (1.0 - coverage))

    score = max(0.0, min(1.0, avg_sim - cit_penalty - coverage_penalty))
    return round(score, 4)


async def hitl_review(state: RAGState) -> Dict[str, Any]:
    """
    Decide whether human-in-the-loop review is needed.

    When ``FEATURE_HITL_ENABLED`` is true and the confidence score is
    below the threshold (or citations are invalid), the node calls
    ``interrupt()`` to pause the graph.  The caller must resume with a
    ``Command(resume={"decision": "approve"|"reject"|"edit", ...})``.

    If HITL is not required the node is a pass-through.
    """
    confidence = _compute_confidence(state)
    citations_valid = state.get("citations_valid", True)

    needs_review = (
        confidence < _HITL_LOW_CONFIDENCE_THRESHOLD
        or not citations_valid
    )

    if not needs_review or not getattr(settings, "FEATURE_HITL_ENABLED", False):
        return {
            "hitl_required": False,
            "hitl_reason": "",
            "hitl_decision": "",
            "hitl_edited_answer": "",
            "confidence_score": confidence,
        }

    # Build reason string
    reasons: list[str] = []
    if confidence < _HITL_LOW_CONFIDENCE_THRESHOLD:
        reasons.append(f"low confidence ({confidence:.2f} < {_HITL_LOW_CONFIDENCE_THRESHOLD})")
    if not citations_valid:
        reasons.append("invalid or conflicting citations")

    reason = "; ".join(reasons)
    logger.info("HITL review required: %s (thread=%s)", reason, state.get("thread_id"))

    # Pause for human review — graph state is checkpointed here
    from langgraph.types import interrupt  # type: ignore[import-untyped]

    human_input = interrupt({
        "reason": reason,
        "confidence": confidence,
        "answer_preview": (state.get("answer") or "")[:500],
        "citations_valid": citations_valid,
    })

    # Resumed — extract the decision
    decision = human_input.get("decision", "approve") if isinstance(human_input, dict) else "approve"
    edited_answer = human_input.get("edited_answer", "") if isinstance(human_input, dict) else ""

    result: Dict[str, Any] = {
        "hitl_required": True,
        "hitl_reason": reason,
        "hitl_decision": decision,
        "confidence_score": confidence,
        "hitl_edited_answer": "",
    }

    if decision == "edit" and edited_answer:
        result["answer"] = edited_answer
        result["hitl_edited_answer"] = edited_answer
    elif decision == "reject":
        result["answer"] = "Response rejected by reviewer."
        result["hitl_edited_answer"] = ""

    return result


# ===================================================================
# NODE: assemble_response
# ===================================================================

async def assemble_response(state: RAGState) -> Dict[str, Any]:
    """Build the final response dict with sources, citations, and visualizations."""
    from api.services.advanced_ai_service import extract_citations, SourceDocument
    from api.services.ai.visualization_service import render_chart_images_from_answer

    answer = state.get("answer") or state.get("early_exit_answer", "")
    hits = state.get("hits", [])
    start_time = state.get("start_time", time.time())

    # Build sources
    sources = []
    for i, hit in enumerate(hits):
        meta = hit.metadata or {}
        sources.append(asdict(SourceDocument(
            file=meta.get("filename", "unknown"),
            group=meta.get("group"),
            snippet=hit.document[:300],
            chunk_index=meta.get("chunk_index"),
            score=round(hit.similarity, 4),
        )))

    citations = list(extract_citations(answer))

    # Visualization rendering (offloaded to thread)
    visualizations: list = []
    try:
        visualizations = await asyncio.to_thread(render_chart_images_from_answer, answer)
    except Exception as exc:
        logger.debug("Chart rendering skipped: %s", exc)

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "sources": sources,
        "citations": citations,
        "visualizations": visualizations,
        "query_time_ms": elapsed_ms,
        "response_type": state.get("intent", "factual"),
    }
