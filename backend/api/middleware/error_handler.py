"""
Global exception handler with proper error differentiation and logging.
"""
import logging
import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette import status

from api.core.exceptions import TokenExpiredError, TokenInvalidError, SessionNotFoundError

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """
    Handle all unhandled exceptions globally.

    - TokenExpiredError: 401 with error_code so frontend can auto-refresh
    - HTTPException: Return its status & detail
    - ValueError: 400 Bad Request
    - Other exceptions: Log full stack trace and return 500
    """
    corr_id = getattr(request.state, "correlation_id", None)

    # --- Token expired: include error_code for frontend refresh logic ---
    if isinstance(exc, TokenExpiredError):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": exc.detail,
                "error_code": "token_expired",
                "correlation_id": corr_id,
            },
            headers=getattr(exc, "headers", None) or {},
        )

    # --- Token invalid ---
    if isinstance(exc, TokenInvalidError):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": exc.detail,
                "error_code": "token_invalid",
                "correlation_id": corr_id,
            },
            headers=getattr(exc, "headers", None) or {},
        )

    # --- HTTP exceptions (client + server errors) ---
    if isinstance(exc, HTTPException):
        detail = getattr(exc, "detail", "Error")
        code = exc.status_code

        log_msg = f"HTTPException {code} at {request.url.path} (cid={corr_id}): {detail}"
        if code >= 500:
            logger.error(log_msg)
        elif code >= 400:
            logger.warning(log_msg)

        resp_headers = {}
        if hasattr(exc, "headers") and exc.headers:
            resp_headers = dict(exc.headers)

        return JSONResponse(
            status_code=code,
            content={
                "success": False,
                "error": detail,
                "correlation_id": corr_id,
            },
            headers=resp_headers,
        )

    # --- ValueError → 400 Bad Request ---
    if isinstance(exc, ValueError):
        logger.warning(f"ValueError at {request.url.path} (cid={corr_id}): {exc}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": str(exc),
                "correlation_id": corr_id,
            },
        )

    # --- Unexpected server error — log full stack trace ---
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.exception(
        f"Unhandled exception at {request.url.path} (cid={corr_id})\n{tb}"
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal server error",
            "correlation_id": corr_id,
        },
    )
