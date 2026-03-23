"""
LangSmith Tracing — configures and provides tracing callbacks.

When ``FEATURE_LANGSMITH_TRACING`` is enabled, this module:

1. Sets the ``LANGCHAIN_TRACING_V2`` environment variable so the
   LangSmith callback is automatically injected into LangChain calls.
2. Provides ``get_tracing_config()`` which returns a config dict suitable
   for passing to ``graph.ainvoke(..., config=config)`` so every trace
   gets tagged with session, user, thread, and environment metadata.

Usage (called once at app startup)::

    from api.services.ai.langgraph.tracing import configure_langsmith
    configure_langsmith()

Per-request::

    from api.services.ai.langgraph.tracing import get_tracing_callbacks
    callbacks = get_tracing_callbacks(session_id, user_id, thread_id)
    # merge into the config dict passed to ainvoke
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)

_tracing_enabled = False


class TracingConfig(TypedDict):
    callbacks: List[Any]
    tags: List[str]
    metadata: Dict[str, Any]


def configure_langsmith() -> None:
    """
    Activate LangSmith tracing by setting environment variables.

    Called once at app startup.  No-op when the feature flag is off
    or the API key is missing.
    """
    global _tracing_enabled

    from api.core.config import settings

    if not getattr(settings, "FEATURE_LANGSMITH_TRACING", False):
        logger.debug("LangSmith tracing disabled (FEATURE_LANGSMITH_TRACING=false)")
        return

    api_key = getattr(settings, "LANGSMITH_API_KEY", None)
    if not api_key:
        logger.warning("LangSmith tracing enabled but LANGSMITH_API_KEY is not set")
        return

    project = getattr(settings, "LANGSMITH_PROJECT", "ret-v4")

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGCHAIN_PROJECT"] = project

    _tracing_enabled = True
    logger.info("LangSmith tracing enabled (project=%s)", project)


def is_tracing_enabled() -> bool:
    """Return whether LangSmith tracing is active."""
    return _tracing_enabled


def get_tracing_callbacks(
    session_id: str = "",
    user_id: str = "",
    thread_id: str = "",
    group_filter: Optional[str] = None,
    extra_tags: Optional[List[str]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """
    Return a list of LangSmith callback handlers with metadata tags.

    When tracing is disabled, returns an empty list (callers can
    always pass the result — an empty list is a no-op for callbacks).
    """
    if not _tracing_enabled:
        return []

    try:
        from langsmith import Client  # type: ignore[import-untyped]
        from langchain_core.tracers import LangChainTracer  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("langsmith or langchain_core.tracers not available")
        return []

    from api.core.config import settings

    tags = [
        f"env:{getattr(settings, 'ENV', 'development')}",
        f"app:{getattr(settings, 'APP_NAME', 'ret-v4')}",
    ]
    if session_id:
        tags.append(f"session:{session_id[:12]}")
    if user_id:
        tags.append(f"user:{user_id[:12]}")
    if group_filter:
        tags.append(f"group:{group_filter}")
    if extra_tags:
        tags.extend(extra_tags)

    metadata: Dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "group_filter": group_filter or "",
        "environment": str(getattr(settings, "ENV", "development")),
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    project = getattr(settings, "LANGSMITH_PROJECT", "ret-v4")

    try:
        tracer = LangChainTracer(
            project_name=project,
            tags=tags,
            client=Client(),
        )
        # Attach metadata via run_name or extra_metadata depending on version
        tracer.metadata = metadata  # type: ignore[attr-defined]
        return [tracer]
    except Exception as exc:
        logger.debug("Failed to create LangSmith tracer: %s", exc)
        return []


def build_tracing_config(
    session_id: str = "",
    user_id: str = "",
    thread_id: str = "",
    group_filter: Optional[str] = None,
) -> Optional[TracingConfig]:
    """
    Build a config dict fragment with tracing callbacks and tags.

    Merge the returned dict into the ``ainvoke`` config::

        base_config = {"configurable": {"thread_id": tid}}
        base_config.update(build_tracing_config(sid, uid, tid))
        await graph.ainvoke(state, config=base_config)

    Returns empty dict when tracing is disabled.
    """
    if not _tracing_enabled:
        return None

    callbacks = get_tracing_callbacks(
        session_id=session_id,
        user_id=user_id,
        thread_id=thread_id,
        group_filter=group_filter,
    )

    if not callbacks:
        return None

    from api.core.config import settings

    return {
        "callbacks": callbacks,
        "tags": [
            f"session:{session_id[:12]}" if session_id else "session:unknown",
            f"env:{getattr(settings, 'ENV', 'development')}",
        ],
        "metadata": {
            "session_id": session_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "group_filter": group_filter or "",
        },
    }
