"""
Azure OpenAI Integration — Retry Utility

Provides exponential-backoff retry for transient Azure OpenAI errors
(429 rate-limit, 5xx server errors, timeouts).

Used by UnifiedRAGService's EmbeddingService and ChatService.
"""

import logging
import time
from typing import Optional

try:
    from openai import APIError, RateLimitError, APITimeoutError
    OPENAI_AVAILABLE = True
except ImportError:
    APIError = Exception  # type: ignore[assignment, misc]
    RateLimitError = Exception  # type: ignore[assignment, misc]
    APITimeoutError = Exception  # type: ignore[assignment, misc]
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
_RETRYABLE = (RateLimitError, APITimeoutError)
_MAX_RETRIES = 4
_BASE_DELAY = 1.0  # seconds


def _retry_with_backoff(fn, *, max_retries: int = _MAX_RETRIES, base_delay: float = _BASE_DELAY):
    """
    Execute *fn()* with exponential backoff on transient OpenAI errors.

    Retries on 429 (rate-limit) and timeout errors. Re-raises all others.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Azure OpenAI transient error (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, max_retries, exc, delay,
            )
            time.sleep(delay)
        except APIError as exc:
            # Retry on 5xx server errors
            if getattr(exc, "status_code", 0) >= 500:  # type: ignore[attr-defined]
                last_exc = exc
                if attempt == max_retries:
                    break
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Azure OpenAI server error %s (attempt %d/%d) — retrying in %.1fs",
                    exc.status_code, attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]
