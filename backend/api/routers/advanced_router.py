"""
Advanced API Routes — XLSX conversion.

Comparison endpoints have been consolidated into comparison_router.py (/api/comparison).
RAG endpoints have been moved to rag_router.py (/api/v2/ai).
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from fastapi.responses import StreamingResponse
import logging

from api.core.dependencies import get_current_user_id
from api.services.storage_service import get_session_dir, get_session_metadata
from api.services.xlsx_service import get_xlsx_bytes_from_csv
from api.schemas.advanced import (
    XLSXConversionRequest,
    XLSXConversionResponse,
)

router = APIRouter(prefix="/advanced", tags=["Advanced Features"])
logger = logging.getLogger(__name__)


# ============================================================
# XLSX Conversion Endpoints
# ============================================================


@router.post("/xlsx/convert", response_model=XLSXConversionResponse)
async def convert_csv_to_xlsx(
    request: XLSXConversionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Convert CSV file from session to XLSX format."""
    try:
        session_dir = get_session_dir(request.session_id)

        meta = get_session_metadata(request.session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        csv_path = session_dir / "output" / request.csv_filename
        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="CSV file not found")

        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))
        output_filename = request.csv_filename.replace(".csv", ".xlsx")

        return XLSXConversionResponse(
            status="success",
            filename=output_filename,
            size_bytes=len(xlsx_bytes),
            message="Conversion successful",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"XLSX conversion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/xlsx/download/{session_id}/{filename}")
async def download_xlsx(
    session_id: str,
    filename: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Download converted XLSX file."""
    try:
        session_dir = get_session_dir(session_id)

        meta = get_session_metadata(session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        csv_name = filename.replace(".xlsx", ".csv")
        csv_path = session_dir / "output" / csv_name

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="CSV file not found")

        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))

        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"XLSX download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
