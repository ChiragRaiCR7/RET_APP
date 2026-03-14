"""
Shared async Azure OpenAI chat service.

Used by multiple routers/services that need non-blocking LLM calls
(e.g., Admin Assistant and RET AI compatibility paths).
"""

from __future__ import annotations

import functools
import logging
import threading
from typing import Any, Dict, List, Optional, cast

from api.core.config import settings
from api.integrations.azure_openai import _retry_with_backoff_async

try:
    from openai import AsyncAzureOpenAI
except ImportError:  # pragma: no cover - handled at runtime
    AsyncAzureOpenAI = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class AsyncAzureChatService:
    """Async Azure OpenAI chat completion wrapper with retry."""

    def __init__(self):
        if AsyncAzureOpenAI is None:
            raise RuntimeError(
                "openai package with AsyncAzureOpenAI is not installed. "
                "Install/upgrade with: pip install -U openai"
            )

        api_key = settings.AZURE_OPENAI_API_KEY or ""
        endpoint = str(settings.AZURE_OPENAI_ENDPOINT or "")
        api_version = settings.AZURE_OPENAI_API_VERSION or "2024-10-21"
        self.deploy_name = settings.AZURE_OPENAI_CHAT_MODEL or ""
        self._timeout = getattr(settings, "AZURE_OPENAI_TIMEOUT_SECONDS", None) or 60

        if not all([api_key, endpoint, self.deploy_name]):
            raise RuntimeError(
                "Azure OpenAI chat config incomplete. "
                "Set AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_CHAT_MODEL."
            )

        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            timeout=self._timeout,
            max_retries=0,  # we handle retries ourselves
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> str:
        """Generate an async chat completion with retry/backoff."""

        async def _call():
            return await self.client.chat.completions.create(
                model=self.deploy_name,
                messages=cast(Any, messages),
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._timeout,
            )

        response = await _retry_with_backoff_async(_call, name="azure_chat_async")
        return (response.choices[0].message.content or "").strip()

    async def close(self):
        """Clean up the async HTTP client."""
        try:
            await self.client.close()
        except Exception:
            pass


_chat_service: Optional[AsyncAzureChatService] = None
_chat_service_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def is_async_azure_chat_configured() -> bool:
    """Check whether Azure OpenAI chat is configured (cached)."""
    return bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT)


def get_async_azure_chat_service() -> AsyncAzureChatService:
    """Get or create shared async Azure chat service singleton."""
    global _chat_service

    with _chat_service_lock:
        if _chat_service is None:
            _chat_service = AsyncAzureChatService()
        return _chat_service


async def shutdown_async_chat_service() -> None:
    """Shutdown the async chat service (call during app shutdown)."""
    global _chat_service
    with _chat_service_lock:
        if _chat_service is not None:
            await _chat_service.close()
            _chat_service = None
            logger.info("Async Azure chat service shut down")


async def generate_admin_agent_reply(command: str, admin_username: str) -> str:
    """Generate Admin Assistant response via async Azure OpenAI chat."""
    service = get_async_azure_chat_service()

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are an enterprise admin assistant for the RET system. "
                "Be concise, practical, and safe. "
                "Do not claim that actions were executed unless explicitly confirmed by backend tools. "
                "If asked to perform unsupported backend actions, explain limitations and suggest the exact admin command format. "
                "Prefer bullet points for multi-step guidance."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Admin user: {admin_username}\n"
                f"Request: {command}\n\n"
                "Provide helpful guidance or interpretation for this request."
            ),
        },
    ]

    return await service.generate(messages=messages, temperature=0.2, max_tokens=1000)
