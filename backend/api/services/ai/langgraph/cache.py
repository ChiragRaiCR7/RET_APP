"""
LangChain LLM Cache — local SQLite-backed response caching.

When ``FEATURE_LLM_CACHE`` is enabled, identical LLM prompts return
cached responses without incurring an API call.  The cache is stored
at ``runtime/cache/llm_cache.db`` and persists across restarts.

Usage (called once at app startup)::

    from api.services.ai.langgraph.cache import configure_llm_cache
    configure_llm_cache()

Disabling:
    Set ``FEATURE_LLM_CACHE=false`` in ``.env`` or the environment.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_cache_configured = False


def configure_llm_cache() -> None:
    """
    Activate LangChain's global LLM cache using SQLite.

    Safe to call multiple times — only the first call has an effect.
    No-op when the feature flag is off or when dependencies are missing.
    """
    global _cache_configured
    if _cache_configured:
        return

    from api.core.config import settings

    if not getattr(settings, "FEATURE_LLM_CACHE", False):
        logger.debug("LLM cache disabled (FEATURE_LLM_CACHE=false)")
        return

    try:
        from langchain_community.cache import SQLiteCache  # type: ignore[import-untyped]
        from langchain.globals import set_llm_cache  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "langchain_community.cache not available; LLM cache disabled"
        )
        return

    try:
        cache_dir = Path(getattr(settings, "RET_RUNTIME_ROOT", "runtime")) / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = cache_dir / "llm_cache.db"

        cache = SQLiteCache(database_path=str(db_path))
        set_llm_cache(cache)

        _cache_configured = True
        logger.info("LLM cache enabled: SQLiteCache at %s", db_path)

    except Exception as exc:
        logger.warning("Failed to configure LLM cache: %s", exc)
