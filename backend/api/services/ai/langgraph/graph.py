"""
LangGraph RAG Graph — Compiled StateGraph for the RAG pipeline.

Builds and compiles the graph once; callers invoke it via ``run_rag_graph``.
The graph uses conditional edges for early-exit paths (no hits, thin context).

Graph topology::

    START
      │
      ▼
    transform_query
      │
      ▼
    embed_and_tokenize
      │
      ▼
    retrieve
      │
      ▼
    fuse_rerank ──── (early_exit?) ───► assemble_response ──► END
      │
      ▼
    build_context ── (early_exit?) ───► assemble_response ──► END
      │
      ▼
    generate_answer
      │
      ▼
    validate_citations
      │
      ▼
    hitl_review  (may interrupt if FEATURE_HITL_ENABLED + low confidence)
      │
      ▼
    assemble_response
      │
      ▼
    END
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from langgraph.graph import END
from langgraph.graph.state import StateGraph  # type: ignore[import-untyped]

from api.services.ai.langgraph.state import RAGState
from api.services.ai.langgraph.tracing import build_tracing_config
from api.services.ai.langgraph.nodes import (
    transform_query,
    embed_and_tokenize,
    retrieve,
    fuse_rerank,
    build_context,
    generate_answer,
    validate_citations,
    hitl_review,
    assemble_response,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

# ---------------------------------------------------------------------------
# Conditional edge helpers
# ---------------------------------------------------------------------------


def _after_fuse_rerank(state: RAGState) -> str:
    """Route after fusion: skip generation if no relevant hits."""
    if state.get("early_exit"):
        return "assemble_response"
    return "build_context"


def _after_build_context(state: RAGState) -> str:
    """Route after context assembly: skip generation if context insufficient."""
    if state.get("early_exit"):
        return "assemble_response"
    return "generate_answer"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph():
    """Construct the RAG StateGraph (not yet compiled)."""
    graph = StateGraph(RAGState)  # type: ignore[arg-type]

    graph.add_node("transform_query", transform_query)
    graph.add_node("embed_and_tokenize", embed_and_tokenize)
    graph.add_node("retrieve", retrieve)
    graph.add_node("fuse_rerank", fuse_rerank)
    graph.add_node("build_context", build_context)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("validate_citations", validate_citations)
    graph.add_node("hitl_review", hitl_review)
    graph.add_node("assemble_response", assemble_response)

    # Linear edges
    graph.set_entry_point("transform_query")
    graph.add_edge("transform_query", "embed_and_tokenize")
    graph.add_edge("embed_and_tokenize", "retrieve")
    graph.add_edge("retrieve", "fuse_rerank")

    # Conditional: fuse_rerank → build_context | assemble_response (early exit)
    graph.add_conditional_edges("fuse_rerank", _after_fuse_rerank)

    # Conditional: build_context → generate_answer | assemble_response (early exit)
    graph.add_conditional_edges("build_context", _after_build_context)

    # Linear: generation → citation repair → HITL review → response
    graph.add_edge("generate_answer", "validate_citations")
    graph.add_edge("validate_citations", "hitl_review")
    graph.add_edge("hitl_review", "assemble_response")
    graph.add_edge("assemble_response", END)

    return graph


# Singleton compiled graph (thread-safe after compilation)
_compiled_graph = None
_checkpointer = None


def _get_checkpointer():
    """
    Return a LangGraph checkpointer based on ``FEATURE_CHECKPOINT_BACKEND``.

    - ``"memory"``  → ``MemorySaver`` (dev/test — volatile)
    - ``"postgres"`` → ``PostgresSaver`` (requires ``langgraph-checkpoint-postgres``)
    - ``""`` or ``"none"`` → ``None`` (no checkpointing)
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    from api.core.config import settings

    backend = getattr(settings, "FEATURE_CHECKPOINT_BACKEND", "memory").lower()

    if backend in ("", "none"):
        return None

    if backend == "memory":
        try:
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import-untyped]
            _checkpointer = MemorySaver()
            logger.info("LangGraph checkpointer: MemorySaver (volatile)")
        except ImportError:
            logger.warning("langgraph checkpoint memory not available; checkpointing disabled")
            return None

    elif backend == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import-untyped]
            _checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
            logger.info("LangGraph checkpointer: AsyncPostgresSaver")
        except (ImportError, Exception) as exc:
            logger.warning("Postgres checkpointer not available (%s); falling back to memory", exc)
            try:
                from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import-untyped]
                _checkpointer = MemorySaver()
            except ImportError:
                return None

    return _checkpointer


def get_compiled_graph():
    """Return the compiled LangGraph RAG graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        checkpointer = _get_checkpointer()
        _compiled_graph = _build_graph().compile(checkpointer=checkpointer)
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_rag_graph(
    *,
    query: str,
    session_id: str,
    user_id: str,
    group_filter: Optional[str] = None,
    top_k: int = 20,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    thread_id: str = "",
) -> Dict[str, Any]:
    """
    Execute the RAG graph end-to-end and return the final state as a response dict.

    This is the primary entry-point used by the router and session manager.

    Returns:
        Dict matching the existing ``UnifiedRAGService.chat()`` response shape::

            {
                "answer": str,
                "sources": List[SourceDoc],
                "citations": List[str],
                "query_time_ms": int,
                "error": bool,
                "query_transformation": Optional[QueryTransform],
                "response_type": str,
                "visualizations": list,
            }
    """
    graph = get_compiled_graph()

    initial_state: RAGState = {
        "query": query,
        "session_id": session_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "group_filter": group_filter,
        "top_k": top_k,
        "conversation_history": conversation_history or [],
        "start_time": time.time(),
        "early_exit": False,
        "early_exit_answer": "",
    }

    try:
        # Build invocation config — thread_id enables checkpointer keying
        config: Dict[str, Any] = {}
        effective_thread = thread_id or f"{session_id}:{user_id}"
        if _get_checkpointer() is not None:
            config["configurable"] = {"thread_id": effective_thread}

        # Merge LangSmith tracing callbacks/tags when enabled
        tracing_cfg = build_tracing_config(
            session_id=session_id,
            user_id=user_id,
            thread_id=effective_thread,
            group_filter=group_filter,
        )
        if tracing_cfg:
            callbacks = config.setdefault("callbacks", [])
            if isinstance(callbacks, list):
                callbacks.extend(tracing_cfg["callbacks"])
            else:
                config["callbacks"] = list(tracing_cfg["callbacks"])

            tags = config.setdefault("tags", [])
            if isinstance(tags, list):
                tags.extend(tracing_cfg["tags"])
            else:
                config["tags"] = list(tracing_cfg["tags"])

            metadata = config.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.update(tracing_cfg["metadata"])
            else:
                config["metadata"] = dict(tracing_cfg["metadata"])

        invoke_config = cast(Optional["RunnableConfig"], config or None)
        final_state = cast(Dict[str, Any], await graph.ainvoke(initial_state, config=invoke_config))

        answer = final_state.get("answer") or final_state.get("early_exit_answer", "")

        return {
            "answer": answer,
            "sources": final_state.get("sources", []),
            "citations": final_state.get("citations", []),
            "query_time_ms": final_state.get("query_time_ms", 0),
            "error": False,
            "query_transformation": final_state.get("query_transform"),
            "response_type": final_state.get("response_type", "factual"),
            "visualizations": final_state.get("visualizations", []),
        }

    except Exception as exc:
        logger.error("RAG graph execution failed: %s", exc, exc_info=True)
        elapsed = int((time.time() - initial_state["start_time"]) * 1000)
        return {
            "answer": f"An error occurred: {exc}",
            "sources": [],
            "citations": [],
            "query_time_ms": elapsed,
            "error": True,
            "query_transformation": None,
            "response_type": "error",
            "visualizations": [],
        }


async def resume_rag_graph(
    *,
    thread_id: str,
    decision: str = "approve",
    edited_answer: str = "",
) -> Dict[str, Any]:
    """
    Resume a HITL-interrupted graph execution.

    Args:
        thread_id: The thread that was interrupted (used as checkpoint key).
        decision: ``"approve"`` | ``"reject"`` | ``"edit"``
        edited_answer: Replacement answer text when ``decision == "edit"``.

    Returns:
        Same response shape as ``run_rag_graph()``.
    """
    from langgraph.types import Command  # type: ignore[import-untyped]

    graph = get_compiled_graph()
    checkpointer = _get_checkpointer()

    if checkpointer is None:
        return {
            "answer": "Cannot resume: checkpointing is disabled.",
            "sources": [],
            "citations": [],
            "query_time_ms": 0,
            "error": True,
            "query_transformation": None,
            "response_type": "error",
            "visualizations": [],
        }

    config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    # Merge LangSmith tracing callbacks/tags when enabled
    tracing_cfg = build_tracing_config(thread_id=thread_id)
    if tracing_cfg:
        callbacks = config.setdefault("callbacks", [])
        if isinstance(callbacks, list):
            callbacks.extend(tracing_cfg["callbacks"])
        else:
            config["callbacks"] = list(tracing_cfg["callbacks"])

        tags = config.setdefault("tags", [])
        if isinstance(tags, list):
            tags.extend(tracing_cfg["tags"])
        else:
            config["tags"] = list(tracing_cfg["tags"])

        metadata = config.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.update(tracing_cfg["metadata"])
        else:
            config["metadata"] = dict(tracing_cfg["metadata"])

    resume_value = {"decision": decision, "edited_answer": edited_answer}

    try:
        invoke_config = cast(Optional["RunnableConfig"], config)
        final_state = cast(Dict[str, Any], await graph.ainvoke(
            Command(resume=resume_value),
            config=invoke_config,
        ))

        answer = final_state.get("answer") or final_state.get("early_exit_answer", "")

        return {
            "answer": answer,
            "sources": final_state.get("sources", []),
            "citations": final_state.get("citations", []),
            "query_time_ms": final_state.get("query_time_ms", 0),
            "error": False,
            "query_transformation": final_state.get("query_transform"),
            "response_type": final_state.get("response_type", "factual"),
            "visualizations": final_state.get("visualizations", []),
            "hitl_decision": decision,
        }

    except Exception as exc:
        logger.error("HITL resume failed: %s", exc, exc_info=True)
        return {
            "answer": f"Resume failed: {exc}",
            "sources": [],
            "citations": [],
            "query_time_ms": 0,
            "error": True,
            "query_transformation": None,
            "response_type": "error",
            "visualizations": [],
        }


async def stream_rag_graph(
    *,
    query: str,
    session_id: str,
    user_id: str,
    group_filter: Optional[str] = None,
    top_k: int = 20,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    thread_id: str = "",
):
    """
    Async generator that yields SSE-formatted events for the RAG pipeline.

    Event types emitted (all ``data:`` payloads are JSON):
        * ``node_start``  — ``{"node": "<name>"}``
        * ``node_end``    — ``{"node": "<name>"}``
        * ``token``       — ``{"content": "<delta>"}``
        * ``sources``     — list of SourceDoc dicts
        * ``citations``   — list of citation strings
        * ``metadata``    — timing/query_transform/response_type
        * ``done``        — final signal with full answer
        * ``error``       — ``{"detail": "…"}``

    The pre-generation pipeline (transform, embed, retrieve, fuse,
    build_context) runs via ``ainvoke``.  If the graph does NOT early-exit
    we stream tokens from the LLM directly and then run citation validation
    manually so that token deltas arrive as soon as they are produced.
    """
    import json as _json
    from api.services.ai.langgraph.client import async_chat_generate_stream
    from api.services.ai.langgraph.nodes import (
        validate_citations as _validate_citations,
        assemble_response as _assemble_response,
        hitl_review as _hitl_review,
    )
    from api.core.prompts import ADVANCED_SYSTEM_PROMPT, build_user_prompt

    start = time.time()

    initial_state: Dict[str, Any] = {
        "query": query,
        "session_id": session_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "group_filter": group_filter,
        "top_k": top_k,
        "conversation_history": conversation_history or [],
        "start_time": start,
        "early_exit": False,
        "early_exit_answer": "",
    }

    def _sse(event: str, data: Any) -> str:
        payload = _json.dumps(data, default=str) if not isinstance(data, str) else data
        return f"event: {event}\ndata: {payload}\n\n"

    try:
        # ── Phase 1: run the retrieval pipeline (all nodes up to generate_answer) ──
        # We use the full graph's ainvoke — the graph will run through all nodes
        # including generate_answer.  For streaming, we separately invoke
        # the pre-generation portion then manually stream the LLM.
        #
        # Build a "retrieval-only" sub-graph state by running transform →
        # embed → retrieve → fuse → build_context manually through the
        # existing node functions.
        from api.services.ai.langgraph.nodes import (
            transform_query as _transform_query,
            embed_and_tokenize as _embed_and_tokenize,
            retrieve as _retrieve,
            fuse_rerank as _fuse_rerank,
            build_context as _build_context,
        )

        state: Dict[str, Any] = dict(initial_state)

        for node_name, node_fn in [
            ("transform_query", _transform_query),
            ("embed_and_tokenize", _embed_and_tokenize),
            ("retrieve", _retrieve),
            ("fuse_rerank", _fuse_rerank),
            ("build_context", _build_context),
        ]:
            yield _sse("node_start", {"node": node_name})
            result = await node_fn(state)  # type: ignore[arg-type]
            state.update(result)
            yield _sse("node_end", {"node": node_name})

            # Check early exit after fuse_rerank or build_context
            if state.get("early_exit"):
                answer = state.get("early_exit_answer", "No relevant results found.")
                yield _sse("token", {"content": answer})
                elapsed = int((time.time() - start) * 1000)
                yield _sse("done", {
                    "answer": answer, "sources": [], "citations": [],
                    "query_time_ms": elapsed,
                })
                return

        # ── Phase 2: stream LLM tokens ──
        yield _sse("node_start", {"node": "generate_answer"})

        context = state.get("context", "")
        intent = state.get("intent", "factual")
        history = state.get("conversation_history", [])

        messages: list = [{"role": "system", "content": ADVANCED_SYSTEM_PROMPT}]
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        user_content = build_user_prompt(query, context, intent=intent)
        messages.append({"role": "user", "content": user_content})

        full_answer_parts: list = []
        async for delta in async_chat_generate_stream(messages):
            full_answer_parts.append(delta)
            yield _sse("token", {"content": delta})

        raw_answer = "".join(full_answer_parts)
        state["raw_answer"] = raw_answer
        yield _sse("node_end", {"node": "generate_answer"})

        # ── Phase 3: citation validation + HITL review + response assembly ──
        yield _sse("node_start", {"node": "validate_citations"})
        cit_result = await _validate_citations(state)  # type: ignore[arg-type]
        state.update(cit_result)
        yield _sse("node_end", {"node": "validate_citations"})

        # HITL check — compute confidence without calling interrupt() since
        # streaming runs nodes outside the compiled graph's checkpoint context.
        # Instead emit an ``hitl_required`` event when review is needed; the
        # frontend should call POST /chat/resume to provide the decision.
        from api.services.ai.langgraph.nodes import _compute_confidence
        from api.core.config import settings as _settings

        confidence = _compute_confidence(state)  # type: ignore[arg-type]
        state["confidence_score"] = confidence
        citations_valid = state.get("citations_valid", True)
        needs_review = (
            confidence < float(getattr(_settings, "RAG_HITL_CONFIDENCE_THRESHOLD", 0.35))
            and getattr(_settings, "FEATURE_HITL_ENABLED", False)
        ) or (
            not citations_valid
            and getattr(_settings, "FEATURE_HITL_ENABLED", False)
        )

        if needs_review:
            reasons: list = []
            if confidence < float(getattr(_settings, "RAG_HITL_CONFIDENCE_THRESHOLD", 0.35)):
                reasons.append(f"low confidence ({confidence:.2f})")
            if not citations_valid:
                reasons.append("invalid citations")

            yield _sse("hitl_required", {
                "reason": "; ".join(reasons),
                "confidence": confidence,
                "answer_preview": (state.get("answer") or raw_answer)[:500],
                "citations_valid": citations_valid,
                "thread_id": thread_id or f"{session_id}:{user_id}",
            })
            # Stop here — caller must resume via POST /chat/resume
            return

        yield _sse("node_start", {"node": "assemble_response"})
        resp_result = await _assemble_response(state)  # type: ignore[arg-type]
        state.update(resp_result)
        yield _sse("node_end", {"node": "assemble_response"})

        final_answer = state.get("answer", raw_answer)
        sources = state.get("sources", [])
        citations = state.get("citations", [])
        elapsed = int((time.time() - start) * 1000)

        yield _sse("sources", sources)
        yield _sse("citations", citations)
        yield _sse("metadata", {
            "query_time_ms": elapsed,
            "query_transformation": state.get("query_transform"),
            "response_type": state.get("response_type", "factual"),
            "visualizations": state.get("visualizations", []),
        })
        yield _sse("done", {
            "answer": final_answer,
            "sources": sources,
            "citations": citations,
            "query_time_ms": elapsed,
        })

    except Exception as exc:
        logger.error("Streaming RAG graph failed: %s", exc, exc_info=True)
        elapsed = int((time.time() - start) * 1000)
        yield _sse("error", {"detail": str(exc), "query_time_ms": elapsed})
