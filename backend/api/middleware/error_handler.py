import logging
from fastapi import Request
from fastapi.responses import JSONResponse

try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception):
    corr_id = getattr(request.state, "correlation_id", None)

    if HAS_LOGURU:
        logger.exception(
            f"Unhandled exception at {request.url.path} (correlation_id: {corr_id})"
        )
    else:
        logger.exception(
            f"Unhandled exception at {request.url.path} (correlation_id: {corr_id})"
        )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "correlation_id": corr_id,
        },
    )
