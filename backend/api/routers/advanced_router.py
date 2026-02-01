"""
Advanced API Routes

Handles XLSX conversion, file comparison, and advanced RAG endpoints.
Integrates with:
- xlsx_conversion_service
- comparison_service
- advanced_ai_service
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse
import logging
import io
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict
import tempfile
from api.core.dependencies import get_current_user
from api.services.storage_service import get_session_dir, get_session_metadata
from api.services.xlsx_conversion_service import get_xlsx_bytes_from_csv
from api.services.comparison_service import compare_files, DiffResult, compare_sessions
from api.services.advanced_ai_service import (
    get_rag_service,
    clear_rag_service,
    list_rag_services,
)
from api.schemas.advanced import (
    XLSXConversionRequest,
    XLSXConversionResponse,
    ComparisonChange,
    ComparisonRequest,
    ComparisonResponse,
    RAGIndexRequest,
    RAGIndexResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGClearRequest,
    RAGClearResponse,
)

router = APIRouter(prefix="/api/advanced", tags=["Advanced Features"])
logger = logging.getLogger(__name__)

# ============================================================
# XLSX Conversion Endpoints
# ============================================================


@router.post("/xlsx/convert", response_model=XLSXConversionResponse)
async def convert_csv_to_xlsx(
    request: XLSXConversionRequest,
    current_user_id: str = Depends(get_current_user),
):
    """
    Convert CSV file from session to XLSX format.
    
    Returns XLSX file as bytes.
    """
    try:
        session_dir = get_session_dir(request.session_id)

        # Validate session ownership
        meta = get_session_metadata(request.session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Find CSV file in session output
        csv_path = session_dir / "output" / request.csv_filename
        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="CSV file not found")

        # Convert to XLSX
        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))

        # Return as downloadable file
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
    current_user_id: str = Depends(get_current_user),
):
    """Download converted XLSX file."""
    try:
        session_dir = get_session_dir(session_id)

        # Validate session ownership
        meta = get_session_metadata(session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Find and convert CSV
        csv_name = filename.replace(".xlsx", ".csv")
        csv_path = session_dir / "output" / csv_name

        if not csv_path.exists():
            raise HTTPException(status_code=404, detail="CSV file not found")

        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))

        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"XLSX download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# File Comparison Endpoints
# ============================================================


@router.post("/comparison/compare", response_model=ComparisonResponse)
async def compare_csv_files(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    ignore_case: bool = Query(False),
    trim_whitespace: bool = Query(True),
    similarity_pairing: bool = Query(True),
    similarity_threshold: float = Query(0.65),
    current_user_id: str = Depends(get_current_user),
):
    """
    Compare two CSV files for differences.
    
    Parameters:
    - ignore_case: Ignore case when comparing
    - trim_whitespace: Trim whitespace from values
    - similarity_pairing: Use fuzzy matching for row pairing
    - similarity_threshold: Minimum similarity score (0.0-1.0)
    
    Returns detailed comparison with change tracking.
    """
    try:
        # Read uploaded files
        file_a_bytes = await file_a.read()
        file_b_bytes = await file_b.read()

        # Perform comparison
        result = compare_files(
            file_a_bytes,
            file_a.filename or "file_a",
            file_b_bytes,
            file_b.filename or "file_b",
        )

        # Convert result.changes to ComparisonChange objects if they're dicts
        changes_list = []
        for change in result.changes:
            if isinstance(change, dict):
                changes_list.append(ComparisonChange(**change))
            else:
                changes_list.append(change)

        return ComparisonResponse(
            status="success",
            message=f"Comparison complete: {result.similarity:.1f}% similarity",
            similarity=result.similarity,
            added=result.added,
            removed=result.removed,
            modified=result.modified,
            same=result.same,
            total_changes=len(result.changes),
            changes=changes_list,
        )

    except Exception as e:
        logger.error(f"Comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comparison/sessions/{session_a}/{session_b}")
async def compare_sessions_endpoint(
    session_a: str,
    session_b: str,
    current_user_id: str = Depends(get_current_user),
):
    """
    Compare output files from two sessions.
    """
    try:
        # Validate session ownership
        meta_a = get_session_metadata(session_a)
        meta_b = get_session_metadata(session_b)

        if meta_a.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized for session A")
        if meta_b.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized for session B")

        # Compare sessions
        result = compare_sessions(session_a, session_b)

        return {
            "status": "success",
            "message": "Session comparison complete",
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Advanced RAG Endpoints
# ============================================================


@router.post("/rag/index", response_model=RAGIndexResponse)
async def index_documents(
    request: RAGIndexRequest,
    current_user_id: str = Depends(get_current_user),
):
    """
    Index documents from session for RAG queries.
    
    Scans session output directory for CSV files and indexes them
    into the vector store.
    """
    try:
        session_dir = get_session_dir(request.session_id)

        # Validate session ownership
        meta = get_session_metadata(request.session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Get RAG service
        rag_service = get_rag_service(session_dir, request.session_id, current_user_id)

        if not rag_service.is_ready():
            raise HTTPException(status_code=503, detail="RAG service not available")

        # Find CSV files in output
        output_dir = session_dir / "output"
        if not output_dir.exists():
            raise HTTPException(status_code=404, detail="No output directory found")

        csv_files = list(output_dir.glob("*.csv"))

        if not csv_files:
            raise HTTPException(status_code=404, detail="No CSV files found in output")

        # Index files
        csv_paths = [str(f) for f in csv_files]
        stats = rag_service.index_csv_files(csv_paths, group_filter=request.groups)

        return RAGIndexResponse(
            status="success" if not stats.errors else "partial",
            indexed_files=stats.indexed_files,
            indexed_docs=stats.indexed_docs,
            indexed_chunks=stats.indexed_chunks,
            errors=stats.errors,
            message=f"Indexed {stats.indexed_files} files, {stats.indexed_docs} documents",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG indexing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/query", response_model=RAGQueryResponse)
async def query_rag(
    request: RAGQueryRequest,
    current_user_id: str = Depends(get_current_user),
):
    """
    Query indexed documents using RAG.
    
    Performs semantic + lexical hybrid retrieval and generates
    contextualized answers with citations.
    """
    try:
        session_dir = get_session_dir(request.session_id)

        # Validate session ownership
        meta = get_session_metadata(request.session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Get RAG service
        rag_service = get_rag_service(session_dir, request.session_id, current_user_id)

        if not rag_service.is_ready():
            raise HTTPException(status_code=503, detail="RAG service not available")

        # Query
        result = rag_service.query(
            query=request.query,
            group_filter=request.group_filter,
            file_filter=request.file_filter,
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result.get("answer"))

        return RAGQueryResponse(
            status="success",
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            message="Query successful",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/status/{session_id}")
async def get_rag_status(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get RAG indexing status for session."""
    try:
        # Validate session ownership
        meta = get_session_metadata(session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        session_dir = get_session_dir(session_id)

        # Get or create service
        try:
            rag_service = get_rag_service(session_dir, session_id, current_user_id)
            is_ready = rag_service.is_ready()
        except:
            is_ready = False

        return {
            "status": "ready" if is_ready else "not_ready",
            "session_id": session_id,
            "message": "RAG service is ready" if is_ready else "RAG service not initialized",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/clear", response_model=RAGClearResponse)
async def clear_rag(
    request: RAGClearRequest,
    current_user_id: str = Depends(get_current_user),
):
    """Clear RAG index and conversation history."""
    try:
        # Validate session ownership
        meta = get_session_metadata(request.session_id)
        if meta.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Clear service
        clear_rag_service(request.session_id, current_user_id)

        return RAGClearResponse(
            status="success",
            message="RAG service cleared for session",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/services")
async def list_services(
    current_user_id: str = Depends(get_current_user),
):
    """List all active RAG services (admin only)."""
    try:
        services = list_rag_services()
        # Filter to user's services only
        user_services = [s for s in services if s.startswith(f"{current_user_id}::")]

        return {
            "status": "success",
            "total_services": len(user_services),
            "services": user_services,
        }

    except Exception as e:
        logger.error(f"List services error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
