from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

async def global_exception_handler(request: Request, exc: Exception):
    corr_id = getattr(request.state, "correlation_id", None)

    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        corr_id=corr_id,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "correlation_id": corr_id,
        },
    )
