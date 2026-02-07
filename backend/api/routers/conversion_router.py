from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, Query, Response, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pathlib import Path
import zipfile
import io
import logging
from typing import List, Optional, Literal

from api.schemas.conversion import (
    ZipScanResponse, 
    ConversionFilesResponse,
    FilePreviewResponse,
    GroupsListResponse,
    AddRowRequest,
    AddFileRequest,
    SaveEditsRequest,
    UpdateCellsRequest,
)
from api.services.conversion_service import (
    scan_zip_with_groups, 
    convert_session,
    list_converted_files,
    get_file_preview,
    build_download_zip,
    download_single_file,
    get_conversion_index,
    add_row_to_file,
    add_new_file,
    delete_file,
    apply_cell_changes,
    refresh_conversion_index,
)
from api.services.job_service import create_job
from api.core.database import get_db
from api.core.dependencies import get_current_user, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversion", tags=["conversion"])
workflow_router = APIRouter(prefix="/workflow", tags=["workflow"])


def _auto_embed_after_conversion(session_id: str, user_id: str, converted_files: list):
    """Background task to embed converted CSVs into ChromaDB after conversion.
    
    STRICT ADMIN CONFIG ENFORCEMENT:
    Only embeds groups that are BOTH:
      1. Configured by admin in AI embedding config (auto_embedded_groups)  
      2. Present in the converted output
    
    Groups not in the admin config are left for the user to select manually
    in the ASK RET AI section.
    
    Uses the dedicated embedding worker for fast background processing.
    
    IMPORTANT: This runs SILENTLY in the background and NEVER interferes with
    the main conversion workflow. All errors are logged but not raised.
    """
    try:
        from api.services.ai.session_manager import get_session_ai_manager
        from api.services.admin_service import get_ai_indexing_config_data
        from api.services.storage_service import get_session_dir
        from api.workers.embedding_worker import get_embedding_worker
        import uuid

        logger.info(f"[AUTO-EMBED] Evaluating auto-embedding for session {session_id}")

        manager = get_session_ai_manager(session_id, user_id)

        if not manager.is_configured():
            logger.info(f"[AUTO-EMBED] Skipped for session {session_id}: AI not configured")
            return

        # STRICT: Check if auto-embedding is enabled in admin config
        ai_config = get_ai_indexing_config_data()
        if not ai_config.get("enable_auto_indexing", False):
            logger.info(f"[AUTO-EMBED] Skipped for session {session_id}: Auto-embedding disabled in admin config")
            return

        # STRICT: Get configured groups from admin config (ONLY these groups)
        configured_groups = [g.strip().upper() for g in ai_config.get("auto_indexed_groups", []) if g]
        if not configured_groups:
            logger.info(f"[AUTO-EMBED] Skipped for session {session_id}: No groups configured for auto-embedding")
            return

        # Filter converted files to ONLY include admin-configured groups
        available_groups = list(set(cf.get("group", "MISC").upper() for cf in converted_files))
        groups_to_embed = [g for g in available_groups if g in configured_groups]
        
        if not groups_to_embed:
            logger.info(
                f"[AUTO-EMBED] Skipped for session {session_id}: "
                f"No converted groups match configured groups. "
                f"Configured: {configured_groups}, Available: {available_groups}"
            )
            return

        logger.info(f"[AUTO-EMBED] Submitting task for session {session_id}: {groups_to_embed}")
        
        # Submit to embedding worker for fast background processing
        session_dir = get_session_dir(session_id)
        csv_dir = session_dir / "output"
        
        worker = get_embedding_worker()
        task = worker.submit_task(
            task_id=f"auto_embed_{session_id}_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            user_id=user_id,
            groups=groups_to_embed,
            csv_dir=csv_dir,
            rag_service=manager.rag_service,
            admin_config=ai_config,
            callback=None,  # Could add progress callback if needed
        )

        # Track which groups were auto-embedded
        existing_auto_embedded = getattr(manager, '_auto_embedded_groups', [])
        manager._auto_embedded_groups = list(
            set(existing_auto_embedded + groups_to_embed)
        )
        manager._metadata["auto_embedded_groups"] = manager._auto_embedded_groups
        manager._save_metadata()

        logger.info(
            f"[AUTO-EMBED] Task submitted successfully: "
            f"session={session_id}, task_id={task.task_id}, groups={groups_to_embed}"
        )
    except Exception as e:
        # CRITICAL: Never let auto-embed errors crash the conversion workflow
        logger.error(
            f"[AUTO-EMBED] Task submission failed for session {session_id}: {e}. "
            f"Conversion workflow continues normally.",
            exc_info=True
        )


@router.post("/scan", response_model=ZipScanResponse)
async def scan(
    file: UploadFile = File(...),
    # Kept for compatibility - actual grouping is prefix-based in service
    group_mode: Literal["zip", "folder", "hybrid"] = Query("zip"),
    group_prefix_len: Optional[int] = Query(
        None, ge=1, le=10,
        description="Optional: limit group prefix length (2/3/4). Default uses full prefix token."
    ),
    max_depth: int = Query(10, ge=0, le=50, description="Max nested zip recursion depth."),
    max_files: int = Query(20000, ge=100, le=200000, description="Max XML files to collect."),
    max_unzipped_mb: int = Query(
        300, ge=1, le=50000,
        description="Max total bytes copied during scan (MB)."
    ),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Scan a ZIP (recursively, including nested ZIPs) or XML file for content.
    
    Groups are determined by the MODULE PREFIX of business ZIPs:
    - AR_PAYMENT_TERM.zip → group "AR"
    - ATK_KR_TOPIC.zip → group "ATK"
    - CST_COST_BOOK.zip → group "CST"
    
    Root ZIPs (like "Manufacturing and Supply Chain...zip") do NOT become groups.
    Batch ZIPs (like "1_BATCH.zip") inherit group from parent business ZIP.
    Folders are traversed but do NOT affect grouping.
    """
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="No file provided")

    is_zip = filename.lower().endswith(".zip")
    is_xml = filename.lower().endswith(".xml")
    if not is_zip and not is_xml:
        raise HTTPException(status_code=400, detail="File must be ZIP or XML format")

    try:
        data = await file.read()
        result = scan_zip_with_groups(
            file_bytes=data,
            filename=filename,
            user_id=current_user_id,
            group_mode=group_mode,
            group_prefix_len=group_prefix_len,
            max_depth=max_depth,
            max_files=max_files,
            max_unzipped_bytes=max_unzipped_mb * 1024 * 1024,
        )
        return result
    except Exception as e:
        logger.exception("Scan failed")
        raise HTTPException(status_code=400, detail=f"Failed to scan: {str(e)}")


@router.post("/convert")
async def convert_async(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    auto_embed: bool = Form(False),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Start conversion job.
    - session_id: Session ID (required)
    - groups: Optional list of groups to convert
    - output_format: Output format (csv or xlsx)
    - auto_embed: If true, automatically embed converted CSVs into ChromaDB
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    logger.info(f"Conversion request: session={session_id}, groups={groups}, format={output_format}, auto_embed={auto_embed}")

    # Validate session exists
    from api.services.storage_service import get_session_dir, get_session_metadata
    try:
        sess_dir = get_session_dir(session_id)
        if not sess_dir.exists():
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found. Please scan a file first.")
        
        extract_dir = sess_dir / "extracted"
        if not extract_dir.exists():
            raise HTTPException(status_code=400, detail="No extracted files found. Please scan a file first.")
        
        # Check if there are any XML files
        xml_count = len(list(extract_dir.rglob("*.xml")))
        if xml_count == 0:
            raise HTTPException(status_code=400, detail="No XML files found in session. Please scan a valid ZIP/XML file.")
        
        logger.info(f"Session validation passed: {xml_count} XML files found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error during validation: {str(e)}")

    try:
        job = create_job(db, "conversion")
        result = convert_session(session_id, groups, output_format)

        # Check if conversion was successful
        stats = result.get("stats", {})
        if stats.get("success", 0) == 0 and stats.get("failed", 0) > 0:
            error_details = result.get("errors", [])
            error_msg = f"All {stats.get('failed')} files failed to convert. First error: {error_details[0].get('error', 'Unknown')}" if error_details else "All files failed to convert"
            logger.error(error_msg)
            return {
                "success": False, 
                "job_id": job.id, 
                "message": error_msg,
                **result
            }

        # Trigger auto-embedding ONLY if explicitly requested and conversion produced files
        # This is disabled by default to prevent interference with utility workflow
        if auto_embed and result.get("stats", {}).get("success", 0) > 0:
            try:
                background_tasks.add_task(
                    _auto_embed_after_conversion,
                    session_id=session_id,
                    user_id=current_user_id,
                    converted_files=result.get("converted_files", []),
                )
                result["embedding_status"] = "queued"
                logger.info(f"Auto-embedding queued for session {session_id}")
            except Exception as e:
                logger.error(f"Failed to queue auto-embedding: {e}")
                result["embedding_status"] = "failed_to_queue"
                # Don't fail the conversion if embedding fails to queue

        return {"success": True, "job_id": job.id, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Conversion failed")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@router.get("/download/{session_id}")
def download(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Package converted CSVs into a zip and return it"""
    from api.services.storage_service import get_session_dir, get_session_metadata

    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        # Check ownership - allow if user matches or if no user was stored
        if stored_user and stored_user != current_user_id:
            logger.warning(f"Download auth mismatch: stored={stored_user}, current={current_user_id}")
            raise HTTPException(status_code=403, detail="Unauthorized - session belongs to another user")
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.warning(f"Session metadata check failed: {e}")
        # Continue anyway if we can't read metadata but session exists

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"
    
    if not out_dir.exists():
        raise HTTPException(status_code=404, detail="No output directory found. Run conversion first.")
    
    csv_files = list(out_dir.glob("*.csv"))
    xlsx_files = list(out_dir.glob("*.xlsx"))
    all_files = csv_files + xlsx_files
    
    if not all_files:
        raise HTTPException(status_code=404, detail="No converted files found. Run conversion first.")
    
    zip_path = sess_dir / "result.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in all_files:
                z.write(f, f.name)
        
        logger.info(f"Created download zip with {len(all_files)} files for session {session_id}")
        return FileResponse(
            zip_path, 
            filename="converted_output.zip",
            media_type="application/zip"
        )
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/files/{session_id}", response_model=ConversionFilesResponse)
def get_converted_files(
    session_id: str,
    group: Optional[str] = Query(None, description="Filter by group name"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    List all converted files for a session.
    Provides data for file dropdown and group selection.
    """
    try:
        result = list_converted_files(session_id, current_user_id, group)
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list converted files")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/{session_id}/{filename}", response_model=FilePreviewResponse)
def preview_file(
    session_id: str,
    filename: str,
    max_rows: int = Query(100, ge=1, le=1000, description="Max rows to preview"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Get preview data for a converted CSV file.
    Returns headers and rows for table display.
    """
    try:
        result = get_file_preview(session_id, current_user_id, filename, max_rows)
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to preview file")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups/{session_id}", response_model=GroupsListResponse)
def get_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Get list of groups for a session with file counts.
    """
    try:
        index = get_conversion_index(session_id, current_user_id)
        groups_data = index.get("groups", {})
        
        groups = [
            {
                "name": g,
                "file_count": len(files),
                "total_rows": sum(f.get("rows", 0) for f in files),
                "total_size": sum(f.get("size_bytes", 0) for f in files),
            }
            for g, files in groups_data.items()
        ]
        
        return {
            "session_id": session_id,
            "total_groups": len(groups),
            "groups": groups,
        }
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get groups")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-custom/{session_id}")
def download_custom(
    session_id: str,
    output_format: str = Form("csv"),
    groups: Optional[List[str]] = Form(None),
    preserve_structure: bool = Form(False),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Download converted files with custom options.
    - output_format: 'csv' or 'xlsx'
    - groups: Optional list of groups to include
    - preserve_structure: Whether to preserve original folder structure
    """
    try:
        zip_bytes, filename = build_download_zip(
            session_id,
            current_user_id,
            output_format,
            groups,
            preserve_structure,
        )
        
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download-file/{session_id}/{filename}")
def download_single(
    session_id: str,
    filename: str,
    format: str = Query("csv", description="Output format: csv or xlsx"),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Download a single converted file.
    """
    try:
        file_bytes, out_filename, mime_type = download_single_file(
            session_id,
            current_user_id,
            filename,
            format,
        )
        
        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{out_filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e))


# Frontend-compatible endpoints (legacy routes)
@workflow_router.post("/scan", response_model=ZipScanResponse)
async def workflow_scan(
    file: UploadFile = File(...),
    group_mode: Literal["zip", "folder", "hybrid"] = Query("zip"),
    group_prefix_len: Optional[int] = Query(None, ge=1, le=10),
    max_depth: int = Query(10, ge=0, le=50),
    max_files: int = Query(20000, ge=100, le=200000),
    max_unzipped_mb: int = Query(300, ge=1, le=50000),
    current_user_id: str = Depends(get_current_user_id),
):
    return await scan(
        file=file,
        group_mode=group_mode,
        group_prefix_len=group_prefix_len,
        max_depth=max_depth,
        max_files=max_files,
        max_unzipped_mb=max_unzipped_mb,
        current_user_id=current_user_id,
    )


@workflow_router.post("/convert")
async def workflow_convert(
    session_id: str = Form(...),
    groups: Optional[List[str]] = Form(None),
    output_format: str = Form("csv"),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info(f"Workflow conversion request: session={session_id}, groups={groups}, format={output_format}")
    job = create_job(db, "conversion")
    result = convert_session(session_id, groups, output_format)
    return {"success": True, "job_id": job.id, **result}


@workflow_router.get("/download/{session_id}")
def workflow_download(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    return download(session_id, current_user_id)


# ---------------------------------------------------------------------------
# Edit & save helpers (frontend-friendly routes)
# ---------------------------------------------------------------------------

@router.post("/add-row/{session_id}")
def add_row_api(
    session_id: str,
    payload: AddRowRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return add_row_to_file(session_id, current_user_id, payload.filename, payload.row)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Add row failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-file/{session_id}")
def add_file_api(
    session_id: str,
    payload: AddFileRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return add_new_file(session_id, current_user_id, payload.filename, payload.group, payload.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Add file failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-file/{session_id}/{filename}")
def delete_file_api(
    session_id: str,
    filename: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return delete_file(session_id, current_user_id, filename)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Delete file failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-cells/{session_id}")
def update_cells_api(
    session_id: str,
    payload: UpdateCellsRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return apply_cell_changes(session_id, current_user_id, payload.filename, [c.dict() for c in payload.changes])
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Batch cell update failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-edits/{session_id}")
def save_edits_api(
    session_id: str,
    payload: SaveEditsRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Placeholder endpoint to align with frontend workflow.
    Rebuilds conversion index after prior edits and returns a simple receipt.
    """
    try:
        index = refresh_conversion_index(session_id)
        return {"success": True, "changes": len(payload.changes or []), "index": index}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Save edits failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download-modified/{session_id}")
def download_modified(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Alias for download that simply packages the current output (including edits).
    """
    return download(session_id, current_user_id)


@router.post("/update-cell/{session_id}/{filename}")
def update_cell(
    session_id: str,
    filename: str,
    row_index: int = Form(...),
    column: str = Form(...),
    value: str = Form(...),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Update a single cell in a converted CSV file.
    """
    from api.services.storage_service import get_session_dir, get_session_metadata
    import pandas as pd
    
    try:
        # Verify ownership
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
    except HTTPException:
        raise
    except Exception:
        pass  # Continue if metadata not found
    
    sess_dir = get_session_dir(session_id)
    file_path = sess_dir / "output" / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        df = pd.read_csv(file_path)
        if row_index < 0 or row_index >= len(df):
            raise HTTPException(status_code=400, detail="Invalid row index")
        if column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{column}' not found")
        
        df.at[row_index, column] = value
        df.to_csv(file_path, index=False)
        refresh_conversion_index(session_id)
        
        return {"success": True, "message": "Cell updated"}
    except Exception as e:
        logger.exception("Cell update failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-row/{session_id}/{filename}")
def update_row(
    session_id: str,
    filename: str,
    row_index: int = Form(...),
    row_data: str = Form(...),  # JSON string of column:value pairs
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Update an entire row in a converted CSV file.
    """
    from api.services.storage_service import get_session_dir, get_session_metadata
    import pandas as pd
    import json
    
    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
    except HTTPException:
        raise
    except Exception:
        pass
    
    sess_dir = get_session_dir(session_id)
    file_path = sess_dir / "output" / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        df = pd.read_csv(file_path)
        if row_index < 0 or row_index >= len(df):
            raise HTTPException(status_code=400, detail="Invalid row index")
        
        data = json.loads(row_data)
        for col, val in data.items():
            if col in df.columns:
                df.at[row_index, col] = val
        
        df.to_csv(file_path, index=False)
        refresh_conversion_index(session_id)
        return {"success": True, "message": "Row updated"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for row_data")
    except Exception as e:
        logger.exception("Row update failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-row/{session_id}/{filename}")
def add_row(
    session_id: str,
    filename: str,
    row_data: str = Form(...),  # JSON string of column:value pairs
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Add a new row to a converted CSV file.
    """
    from api.services.storage_service import get_session_dir, get_session_metadata
    import pandas as pd
    import json
    
    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
    except HTTPException:
        raise
    except Exception:
        pass
    
    sess_dir = get_session_dir(session_id)
    file_path = sess_dir / "output" / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        df = pd.read_csv(file_path)
        data = json.loads(row_data)
        new_row = {col: data.get(col, '') for col in df.columns}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(file_path, index=False)
        refresh_conversion_index(session_id)
        return {"success": True, "message": "Row added", "new_row_index": len(df) - 1}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for row_data")
    except Exception as e:
        logger.exception("Add row failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-row/{session_id}/{filename}/{row_index}")
def delete_row(
    session_id: str,
    filename: str,
    row_index: int,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Delete a row from a converted CSV file.
    """
    from api.services.storage_service import get_session_dir, get_session_metadata
    import pandas as pd
    
    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
    except HTTPException:
        raise
    except Exception:
        pass
    
    sess_dir = get_session_dir(session_id)
    file_path = sess_dir / "output" / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        df = pd.read_csv(file_path)
        if row_index < 0 or row_index >= len(df):
            raise HTTPException(status_code=400, detail="Invalid row index")
        
        df = df.drop(index=row_index).reset_index(drop=True)
        df.to_csv(file_path, index=False)
        refresh_conversion_index(session_id)
        return {"success": True, "message": "Row deleted"}
    except Exception as e:
        logger.exception("Delete row failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup/{session_id}")
def cleanup_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Clean up extracted and output files from a session"""
    from api.services.storage_service import get_session_dir, get_session_metadata
    from pathlib import Path
    import shutil

    try:
        metadata = get_session_metadata(session_id)
        stored_user = metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized - session belongs to another user")
    except HTTPException:
        raise
    except Exception:
        pass  # Continue if we can't check metadata

    try:
        sess_dir = get_session_dir(session_id)
        extract_dir = sess_dir / "extracted"
        out_dir = sess_dir / "output"

        # Remove directories
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        if out_dir.exists():
            shutil.rmtree(out_dir)

        # Clear conversion index
        index_file = sess_dir / "conversion_index.json"
        if index_file.exists():
            index_file.unlink()

        logger.info(f"Cleaned up session {session_id}")
        return {"success": True, "message": "Session cleaned up successfully"}
    except Exception as e:
        logger.exception("Cleanup failed")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")