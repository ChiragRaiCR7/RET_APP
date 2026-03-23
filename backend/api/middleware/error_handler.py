"""
Global exception handler with proper error differentiation and logging.

Improvements:
- Handles LoginSessionNotFoundError / SessionNotFoundError explicitly.
- Uses a consistent _error_response() helper — all branches return the same schema:
    {success, error, error_code, correlation_id, [debug]}.
- error_code is present on every branch (no silent omissions).
- Sensitive data (tokens, passwords, keys) is redacted before logging / returning.
- When settings.DEBUG is True the sanitised traceback is included under "debug".
- method and client IP are included in all log messages for easier investigation.
"""

from __future__ import annotations

import re
import traceback

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette import status

from api.core.exceptions import (
    LoginSessionNotFoundError,
    SessionNotFoundError,  # backward-compat alias
    TokenExpiredError,
    TokenInvalidError,
)
from api.core.logging_config import get_logger

logger = get_logger(__name__)

# Redact patterns for sensitive data before logging / returning messages.
_REDACT_PATTERNS = [
    re.compile(r"(?i)(token|password|secret|api[-_]?key|authorization)[^\s]*\s*[:=]\s*\S+"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\b"),   # JWT-like strings
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),     # OpenAI-style keys
]


def _sanitize(text: str) -> str:
    """Redact known sensitive patterns from a string."""
    for pat in _REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _error_response(
    *,
    status_code: int,
    error: str,
    error_code: str,
    corr_id: str | None,
    headers: dict | None = None,
    debug_detail: str | None = None,
) -> JSONResponse:
    """Return a consistent error response body used by every exception branch."""
    body: dict = {
        "success": False,
        "error": error,
        "error_code": error_code,
        "correlation_id": corr_id,
    }
    if debug_detail is not None:
        body["debug"] = debug_detail
    return JSONResponse(status_code=status_code, content=body, headers=headers or {})


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all unhandled exceptions globally.

    Dispatch order:
    - TokenExpiredError / TokenInvalidError            → 401 with specific error_code
    - LoginSessionNotFoundError / SessionNotFoundError → status_code from exception
    - HTTPException                                    → pass-through, standardised body
    - ValueError                                       → 400 Bad Request
    - Anything else                                    → 500 (sanitised; trace in DEBUG)
    """
    corr_id: str | None = getattr(request.state, "correlation_id", None)
    client_ip: str = request.client.host if request.client else "unknown"
    method: str = request.method
    path: str = request.url.path

    # --- Token expired ---
    if isinstance(exc, TokenExpiredError):
        return _error_response(
            status_code=401,
            error=exc.detail,
            error_code="token_expired",
            corr_id=corr_id,
            headers=getattr(exc, "headers", None) or {},
        )

    # --- Token invalid ---
    if isinstance(exc, TokenInvalidError):
        return _error_response(
            status_code=401,
            error=exc.detail,
            error_code="token_invalid",
            corr_id=corr_id,
            headers=getattr(exc, "headers", None) or {},
        )

    # --- Session not found (login or processing session) ---
    if isinstance(exc, (LoginSessionNotFoundError, SessionNotFoundError)):
        return _error_response(
            status_code=exc.status_code,
            error=exc.detail,
            error_code=getattr(exc, "error_code", "session_not_found"),
            corr_id=corr_id,
            headers=getattr(exc, "headers", None) or {},
        )

    # --- Generic HTTP exceptions ---
    if isinstance(exc, HTTPException):
        detail = _sanitize(str(getattr(exc, "detail", "Error")))
        code = exc.status_code
        error_code = getattr(exc, "error_code", f"http_{code}")

        log_msg = "%s %s \u2192 %d (cid=%s ip=%s)"
        if code >= 500:
            logger.error(log_msg, method, path, code, corr_id, client_ip)
        else:
            logger.warning(log_msg, method, path, code, corr_id, client_ip)

        resp_headers = dict(exc.headers) if getattr(exc, "headers", None) else {}
        return _error_response(
            status_code=code,
            error=detail,
            error_code=error_code,
            corr_id=corr_id,
            headers=resp_headers,
        )

    # --- ValueError → 400 Bad Request ---
    if isinstance(exc, ValueError):
        sanitized = _sanitize(str(exc))
        logger.warning(
            "ValueError %s %s (cid=%s ip=%s): %s",
            method, path, corr_id, client_ip, sanitized,
        )
        return _error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=sanitized,
            error_code="bad_request",
            corr_id=corr_id,
        )

    # --- Unexpected server error ---
    tb_text = _sanitize(
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    )
    logger.error(
        "Unhandled exception %s %s (cid=%s ip=%s): %s",
        method, path, corr_id, client_ip, tb_text,
    )

    from api.core.config import settings  # late import — avoids circular at module level
    debug_detail = tb_text if getattr(settings, "DEBUG", False) else None

    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal server error",
        error_code="internal_server_error",
        corr_id=corr_id,
        debug_detail=debug_detail,
    )
