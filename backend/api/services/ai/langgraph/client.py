"""
Shared async Azure OpenAI client layer.

All LangGraph nodes (and future LangChain model instances) share a single
AsyncAzureOpenAI client per process, avoiding per-call connection overhead.

Usage::

    from api.services.ai.langgraph.client import get_async_chat_client, get_async_embed_client

    chat_client = get_async_chat_client()
    embed_client = get_async_embed_client()
"""

from __future__ import annotations

import logging
from typing import Optional

from api.core.config import settings
from api.integrations.azure_openai import _retry_with_backoff_async

logger = logging.getLogger(__name__)

# Lazy singletons — created on first access.  Typed as Any to avoid
# narrowing issues when the openai package isn't installed.
from typing import Any as _Any
_chat_client: Optional[_Any] = None
_embed_client: Optional[_Any] = None


def _get_api_key() -> str:
    return settings.AZURE_OPENAI_API_KEY or ""


def _get_endpoint() -> str:
    return str(settings.AZURE_OPENAI_ENDPOINT or "")


def _get_api_version() -> str:
    return settings.AZURE_OPENAI_API_VERSION or "2024-10-21"


def _get_timeout() -> int:
    return int(getattr(settings, "AZURE_OPENAI_TIMEOUT_SECONDS", None) or 60)


def get_async_chat_client():
    """Return a shared AsyncAzureOpenAI instance for chat completions."""
    global _chat_client
    if _chat_client is not None:
        return _chat_client

    try:
        from openai import AsyncAzureOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required") from exc

    _chat_client = AsyncAzureOpenAI(
        api_key=_get_api_key(),
        azure_endpoint=_get_endpoint(),
        api_version=_get_api_version(),
        timeout=_get_timeout(),
    )
    return _chat_client


def get_async_embed_client():
    """Return a shared AsyncAzureOpenAI instance for embeddings."""
    global _embed_client
    if _embed_client is not None:
        return _embed_client

    try:
        from openai import AsyncAzureOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required") from exc

    _embed_client = AsyncAzureOpenAI(
        api_key=_get_api_key(),
        azure_endpoint=_get_endpoint(),
        api_version=_get_api_version(),
        timeout=_get_timeout(),
    )
    return _embed_client


async def async_chat_generate(
    messages: list,
    *,
    temperature: float = 0.65,
    max_tokens: int = 4000,
) -> str:
    """Generate a chat completion using the shared async client with retry."""
    client = get_async_chat_client()
    deploy = settings.AZURE_OPENAI_CHAT_MODEL or "gpt-4o"
    timeout = _get_timeout()

    async def _call():
        return await client.chat.completions.create(
            model=deploy,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    response = await _retry_with_backoff_async(_call, name="langgraph_chat")
    return (response.choices[0].message.content or "").strip()


async def async_embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using the shared async client with retry."""
    client = get_async_embed_client()
    deploy = settings.AZURE_OPENAI_EMBED_MODEL or "text-embedding-3-small"
    timeout = _get_timeout()

    async def _call():
        return await client.embeddings.create(
            model=deploy,
            input=texts,
            timeout=timeout,
        )

    response = await _retry_with_backoff_async(_call, name="langgraph_embed")
    return [item.embedding for item in response.data]


async def async_chat_generate_stream(
    messages: list,
    *,
    temperature: float = 0.65,
    max_tokens: int = 4000,
):
    """Yield token deltas from a streaming chat completion.

    This is an async generator that yields ``str`` chunks as they
    arrive from the Azure OpenAI API.
    """
    client = get_async_chat_client()
    deploy = settings.AZURE_OPENAI_CHAT_MODEL or "gpt-4o"
    timeout = _get_timeout()

    response = await client.chat.completions.create(
        model=deploy,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        stream=True,
    )

    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def reset_clients() -> None:
    """Reset singleton clients (for testing or config changes)."""
    global _chat_client, _embed_client
    _chat_client = None
    _embed_client = None
