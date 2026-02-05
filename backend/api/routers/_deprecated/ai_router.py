from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks, UploadFile, File
from pathlib import Path
import logging
import json
import uuid
from datetime import datetime
from typing import Optional, List

from api.schemas.ai import (
    IndexRequest,
    ChatRequest,
    ChatResponse,
    ZipScanResponse,
    GroupInfo,
    AutoIndexRequest,
    CompareZipsResponse,
    GroupComparisonInfo,
    FileComparisonInfo,
    RAGStatus,
    AdminAIConfig,
    SourceDocument,
    RetrievalInfo,
    # AI Session schemas
    SessionMessage,
    AISessionState,
    CreateSessionRequest,
    CreateSessionResponse,
    UpdateSessionRequest,
)
from api.services.lite_ai_service import (
    get_ai_service,
    clear_ai_service,
)
from api.services.storage_service import (
    get_session_dir,
    get_session_metadata,
    save_session_metadata,
)
from api.core.dependencies import get_current_user
from api.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ============================================================
# Helper Functions
# ============================================================

def load_ai_config() -> dict:
    """Load AI config from data/ai_config.json"""
    config_path = Path(settings.RET_RUNTIME_ROOT).parent / "data" / "ai_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"auto_indexed_groups": [], "default_collection": "documents"}


def save_ai_config(config: dict):
    """Save AI config to data/ai_config.json"""
    config_path = Path(settings.RET_RUNTIME_ROOT).parent / "data" / "ai_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


# ============================================================
# AI Config Endpoint
# ============================================================

@router.get("/config")
def get_ai_config_endpoint(
    current_user_id: str = Depends(get_current_user),
):
    """
    Get AI configuration including auto-indexed groups.
    """
    try:
        config = load_ai_config()
        return {
            "auto_indexed_groups": config.get("auto_indexed_groups", []),
            "default_collection": config.get("default_collection", "documents"),
            "chunk_size": config.get("chunk_size", 10000),
            "retrieval_top_k": config.get("retrieval_top_k", 16),
            "enable_auto_indexing": config.get("enable_auto_indexing", False),
        }
    except Exception as e:
        logger.error(f"Failed to get AI config: {e}")
        return {
            "auto_indexed_groups": [],
            "default_collection": "documents",
            "chunk_size": 10000,
            "retrieval_top_k": 16,
            "enable_auto_indexing": False,
        }


# ============================================================
# AI Session Endpoints
# ============================================================

def get_ai_session_file(user_id: str) -> Path:
    """Get path to user's AI session file"""
    session_dir = Path(settings.RET_RUNTIME_ROOT) / "ai_sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / f"{user_id}_session.json"


def load_ai_session(user_id: str) -> dict:
    """Load user's AI session state"""
    session_file = get_ai_session_file(user_id)
    if session_file.exists():
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_ai_session(user_id: str, session_data: dict):
    """Save user's AI session state"""
    session_file = get_ai_session_file(user_id)
    session_data["updated_at"] = datetime.utcnow().isoformat()
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2)


@router.get("/session", response_model=AISessionState)
def get_session(
    current_user_id: str = Depends(get_current_user),
):
    """
    Get the current user's AI session.
    Returns existing session or 404 if none exists.
    """
    try:
        session_data = load_ai_session(current_user_id)
        
        if not session_data or "session_id" not in session_data:
            raise HTTPException(status_code=404, detail="No AI session found")
        
        return AISessionState(
            session_id=session_data.get("session_id", ""),
            messages=[SessionMessage(**m) for m in session_data.get("messages", [])],
            instructions=session_data.get("instructions", ""),
            created_at=session_data.get("created_at"),
            updated_at=session_data.get("updated_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get AI session: {e}")
        raise HTTPException(status_code=500, detail="Failed to get AI session")


@router.post("/session", response_model=CreateSessionResponse)
def create_session(
    req: CreateSessionRequest = None,
    current_user_id: str = Depends(get_current_user),
):
    """
    Create a new AI session for the current user.
    Clears any existing session and starts fresh.
    """
    try:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        session_data = {
            "session_id": session_id,
            "messages": [],
            "instructions": req.instructions if req else "",
            "created_at": now,
            "updated_at": now,
        }
        
        save_ai_session(current_user_id, session_data)
        
        return CreateSessionResponse(
            session_id=session_id,
            messages=[],
            instructions=session_data["instructions"],
        )
    except Exception as e:
        logger.error(f"Failed to create AI session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create AI session")


@router.put("/session/{session_id}")
def update_session(
    session_id: str,
    req: UpdateSessionRequest,
    current_user_id: str = Depends(get_current_user),
):
    """
    Update an AI session's instructions.
    """
    try:
        session_data = load_ai_session(current_user_id)
        
        if not session_data or session_data.get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data["instructions"] = req.instructions
        save_ai_session(current_user_id, session_data)
        
        return {
            "status": "success",
            "message": "Session updated",
            "session_id": session_id,
            "instructions": req.instructions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update AI session: {e}")
        raise HTTPException(status_code=500, detail="Failed to update AI session")


@router.delete("/session/{session_id}")
def delete_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """
    Delete/clear an AI session.
    """
    try:
        session_file = get_ai_session_file(current_user_id)
        
        if session_file.exists():
            session_data = load_ai_session(current_user_id)
            if session_data.get("session_id") == session_id:
                session_file.unlink()
        
        return {
            "status": "success",
            "message": "Session deleted",
            "session_id": session_id,
        }
    except Exception as e:
        logger.error(f"Failed to delete AI session: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete AI session")


@router.post("/session/message")
def add_session_message(
    role: str = Form(...),
    content: str = Form(...),
    current_user_id: str = Depends(get_current_user),
):
    """
    Add a message to the current AI session.
    """
    try:
        session_data = load_ai_session(current_user_id)
        
        if not session_data or "session_id" not in session_data:
            raise HTTPException(status_code=404, detail="No AI session found. Create one first.")
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if "messages" not in session_data:
            session_data["messages"] = []
        
        session_data["messages"].append(message)
        save_ai_session(current_user_id, session_data)
        
        return {
            "status": "success",
            "message": "Message added",
            "session_id": session_data["session_id"],
            "message_count": len(session_data["messages"]),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add message: {e}")
        raise HTTPException(status_code=500, detail="Failed to add message")


# ============================================================
# ZIP Scanning Endpoints
# ============================================================

@router.post("/scan-zip")
async def scan_zip_file(
    session_id: str = Form(...),
    custom_prefixes: Optional[str] = Form(None),  # Comma-separated
    max_files: int = Form(10000),
    current_user_id: str = Depends(get_current_user),
):
    """
    Scan uploaded ZIP file and extract XML entries.
    Returns detected groups and file statistics.
    """
    from api.services.zip_service import scan_zip_file as do_scan
    from api.services.rag_service import infer_group
    
    try:
        # Verify user owns session
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        
        # Find uploaded ZIP
        zip_files = list(session_dir.glob("*.zip"))
        if not zip_files:
            raise HTTPException(status_code=400, detail="No ZIP file found in session")
        
        zip_path = zip_files[0]
        
        # Parse custom prefixes
        prefixes = set()
        if custom_prefixes:
            prefixes = {p.strip() for p in custom_prefixes.split(",") if p.strip()}
        
        # Scan ZIP
        result = do_scan(
            zip_path,
            session_dir,
            custom_prefixes=prefixes,
            max_files=max_files
        )
        
        # Build group info
        groups = []
        for group_name, count in result.group_counts.items():
            # Calculate approximate size for group
            group_entries = [e for e in result.xml_entries 
                           if infer_group(e.logical_path, e.filename, prefixes) == group_name]
            total_size = sum(e.xml_size for e in group_entries)
            groups.append(GroupInfo(
                name=group_name,
                file_count=count,
                total_size_bytes=total_size
            ))
        
        # Sort by file count
        groups.sort(key=lambda g: -g.file_count)
        
        # Save scan results to session metadata
        metadata = get_session_metadata(session_id)
        metadata["scan_result"] = {
            "xml_count": len(result.xml_entries),
            "groups": [g.dict() for g in groups],
            "total_extracted_bytes": result.total_extracted_bytes,
        }
        save_session_metadata(session_id, metadata)
        
        return ZipScanResponse(
            status="success",
            message=f"Found {len(result.xml_entries)} XML files in {len(groups)} groups",
            xml_count=len(result.xml_entries),
            groups=groups,
            total_extracted_bytes=result.total_extracted_bytes,
            elapsed_seconds=result.elapsed_seconds,
            errors=result.errors[:20]  # Limit errors
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ZIP scan failed: {str(e)}")


@router.get("/detected-groups/{session_id}")
def get_detected_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get detected groups from last ZIP scan"""
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        scan_result = session_metadata.get("scan_result", {})
        return {
            "session_id": session_id,
            "groups": scan_result.get("groups", []),
            "xml_count": scan_result.get("xml_count", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get detected groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to get detected groups")


# ============================================================
# Auto-Index Endpoints
# ============================================================

@router.post("/auto-index")
async def auto_index_groups(
    req: AutoIndexRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user),
):
    """
    Auto-index specified groups using advanced RAG service.
    Triggered after ZIP scan with admin-configured groups.
    """
    from api.services.rag_service import RAGService
    
    try:
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(req.session_id)
        
        # Initialize RAG service
        rag_service = RAGService(
            persist_dir=str(session_dir / "chroma_db"),
            collection_name=f"session_{req.session_id}"
        )
        
        # Get XML entries from temp directory
        xml_dir = session_dir / "temp" / "xml_inputs"
        if not xml_dir.exists():
            raise HTTPException(status_code=400, detail="No scanned XML files. Run scan-zip first.")
        
        # Build XmlEntry objects from files
        from api.services.rag_service import XmlEntry, infer_group
        xml_entries = []
        for xml_file in xml_dir.glob("*.xml"):
            stub = xml_file.stem
            xml_entries.append(XmlEntry(
                logical_path=str(xml_file.relative_to(session_dir)),
                filename=xml_file.name,
                xml_path=str(xml_file),
                xml_size=xml_file.stat().st_size,
                stub=stub
            ))
        
        # Filter by selected groups
        selected_set = set(req.groups)
        filtered_entries = [
            e for e in xml_entries
            if infer_group(e.logical_path, e.filename, set()) in selected_set
        ]
        
        if not filtered_entries:
            raise HTTPException(status_code=400, detail="No XML files match selected groups")
        
        # Index records
        result = rag_service.index_xml_records(filtered_entries, req.groups)
        
        # Update session metadata
        metadata = get_session_metadata(req.session_id)
        metadata["indexed_groups"] = req.groups
        metadata["index_stats"] = result
        save_session_metadata(req.session_id, metadata)
        
        return {
            "status": "success",
            "message": f"Indexed {result.get('total_chunks', 0)} chunks from {len(filtered_entries)} files",
            "groups_indexed": req.groups,
            "stats": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-indexing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Auto-indexing failed: {str(e)}")


@router.get("/auto-index-config")
def get_auto_index_config(
    current_user_id: str = Depends(get_current_user),
):
    """Get admin-configured auto-index groups"""
    config = load_ai_config()
    return AdminAIConfig(**config)


@router.get("/session-groups/{session_id}")
def get_session_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get available groups for a session from conversion index"""
    try:
        from api.services.storage_service import get_session_metadata, get_session_dir
        import json
        
        # Verify user owns this session
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        index_path = session_dir / "conversion_index.json"
        
        groups = []
        if index_path.exists():
            try:
                index_data = json.loads(index_path.read_text())
                groups = list(index_data.get("groups", {}).keys())
            except Exception as e:
                logger.warning(f"Could not parse conversion index: {e}")
        
        return {
            "session_id": session_id,
            "groups": sorted(groups),
            "group_count": len(groups),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session groups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get groups: {str(e)}")


# ============================================================
# Original Index/Chat Endpoints
# ============================================================


@router.post("/index-session")
async def index_session_files(
    session_id: str = Form(...),
    groups: Optional[str] = Form(None),  # Comma-separated group names
    files: Optional[List[UploadFile]] = File(None),  # Optional direct file uploads
    current_user_id: str = Depends(get_current_user),
):
    """
    Index files for AI - supports two modes:
    1. If files are uploaded, index those directly
    2. If no files, use converted CSV files from session's output directory with group filtering
    """
    try:
        # Verify user owns this session
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        csv_files = []
        selected_groups = []
        
        # Mode 1: Direct file uploads
        if files and len(files) > 0 and files[0].filename:
            import tempfile
            temp_dir = session_dir / "temp_index"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            for file in files:
                if file.filename:
                    # Save uploaded file
                    temp_path = temp_dir / file.filename
                    content = await file.read()
                    with open(temp_path, 'wb') as f:
                        f.write(content)
                    
                    if file.filename.endswith('.csv'):
                        csv_files.append(temp_path)
        
        # Mode 2: Use converted files from output directory with group filtering
        if not csv_files:
            from api.services.conversion_service import get_conversion_index
            import json
            
            output_dir = session_dir / "output"
            
            # Parse requested groups
            requested_groups = set()
            if groups:
                requested_groups = {g.strip() for g in groups.split(",") if g.strip()}
            
            # Try to load conversion index
            index_path = session_dir / "conversion_index.json"
            if index_path.exists():
                try:
                    index_data = json.loads(index_path.read_text())
                    
                    # Filter files by group
                    for file_info in index_data.get("files", []):
                        file_group = file_info.get("group", "")
                        
                        # Include file if:
                        # 1. No groups specified (index all), OR
                        # 2. File's group is in requested groups
                        if not requested_groups or file_group in requested_groups:
                            csv_path = output_dir / file_info["filename"]
                            if csv_path.exists():
                                csv_files.append(csv_path)
                                if file_group and file_group not in selected_groups:
                                    selected_groups.append(file_group)
                except Exception as e:
                    logger.warning(f"Could not parse conversion index: {e}")
            
            # Fallback: if no index or no files found, list all CSVs in output directory
            if not csv_files and output_dir.exists():
                csv_files = list(output_dir.glob("*.csv"))
                selected_groups = []  # Group info unknown
        
        if not csv_files:
            raise HTTPException(
                status_code=400, 
                detail="No files to index. Please convert files first or upload CSV files directly."
            )
        
        # Get AI service
        ai_service = get_ai_service(session_id, str(session_dir / "ai_index"))
        
        # Index files
        result = ai_service.index_csv_files(csv_files)
        
        if result["status"] != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "Indexing failed"))
        
        # Update session metadata
        metadata = get_session_metadata(session_id)
        metadata["indexed_groups"] = selected_groups or metadata.get("indexed_groups", [])
        metadata["indexed_file_count"] = len(csv_files)
        save_session_metadata(session_id, metadata)
        
        return {
            "status": "success",
            "message": f"Indexed {len(csv_files)} CSV file(s) successfully",
            "files_indexed": len(csv_files),
            "indexed_groups": metadata.get("indexed_groups", []),
            "stats": {
                "documents_indexed": result.get("documents_indexed", 0),
                "chunks_created": result.get("chunks_created", 0),
                "total_size_mb": result.get("total_size_mb", 0.0),
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session indexing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")



@router.post("/index")
def index_groups(
    req: IndexRequest,
    current_user_id: str = Depends(get_current_user),
):
    """Index selected groups from converted CSV files"""
    try:
        # Verify user owns this session (or session has no owner set)
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            logger.warning(f"Index auth mismatch: stored={stored_user}, current={current_user_id}")
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get session directory
        session_dir = get_session_dir(req.session_id)
        output_dir = session_dir / "output"
        
        if not output_dir.exists():
            raise HTTPException(status_code=400, detail="No converted files in session")
        
        # Collect CSV files
        csv_files = list(output_dir.glob("*.csv"))
        
        if not csv_files:
            raise HTTPException(status_code=400, detail="No CSV files to index")
        
        # Get AI service
        ai_service = get_ai_service(req.session_id, str(session_dir / "ai_index"))
        
        # Index files
        result = ai_service.index_csv_files(csv_files)
        
        if result["status"] != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "Indexing failed"))
        
        # Persist indexed group metadata
        metadata = get_session_metadata(req.session_id)
        metadata["indexed_groups"] = req.groups or metadata.get("indexed_groups", [])
        save_session_metadata(req.session_id, metadata)

        return {
            "status": "success",
            "message": result.get("message", "Indexing complete"),
            "indexed_groups": metadata.get("indexed_groups", []),
            "stats": {
                "documents_indexed": result.get("documents_indexed", 0),
                "chunks_created": result.get("chunks_created", 0),
                "total_size_mb": result.get("total_size_mb", 0.0),
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/indexed-groups/{session_id}")
def get_indexed_groups(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get status of indexed groups for a session"""
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        ai_service = get_ai_service(session_id, str(session_dir / "ai_index"))
        
        return {
            "session_id": session_id,
            "is_indexed": ai_service.collection is not None,
            "status": "indexed" if ai_service.collection else "not_indexed",
            "indexed_groups": session_metadata.get("indexed_groups", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get indexed groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to get indexed groups")


@router.post("/clear-memory/{session_id}")
def clear_ai_memory(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Clear all AI indexing memory for a session"""
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        clear_ai_service(session_id)
        metadata = get_session_metadata(session_id)
        metadata["indexed_groups"] = []
        save_session_metadata(session_id, metadata)
        
        return {
            "status": "success",
            "message": "AI memory cleared successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear memory")


@router.post("/chat")
def chat(
    req: ChatRequest,
    current_user_id: str = Depends(get_current_user),
):
    """Chat with AI about indexed documents"""
    try:
        # Verify user owns this session (or session has no owner set)
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get AI service
        session_dir = get_session_dir(req.session_id)
        ai_service = get_ai_service(req.session_id, str(session_dir / "ai_index"))
        
        # Get the query text from either question or message field
        query_text = req.question or req.message
        
        # Add instructions context if provided
        if query_text and req.instructions:
            query_text = f"Instructions: {req.instructions}\n\nQuestion: {query_text}"
        
        # Query or chat
        if query_text:
            # RAG-based query
            result = ai_service.query(query_text)
            
            # Store in session history
            ai_session = load_ai_session(current_user_id)
            if ai_session and "messages" in ai_session:
                ai_session["messages"].append({
                    "role": "user",
                    "content": req.question or req.message,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                ai_session["messages"].append({
                    "role": "assistant",
                    "content": result["answer"],
                    "timestamp": datetime.utcnow().isoformat(),
                })
                save_ai_session(current_user_id, ai_session)
            
            # Return in format frontend expects
            return {
                "response": result["answer"],
                "answer": result["answer"],  # Also include for compatibility
                "sources": result.get("sources", []),
                "retrieval_info": {
                    "chunks_retrieved": len(result.get("sources", [])),
                    "method": "rag"
                }
            }
        elif req.messages:
            # Regular chat
            response = ai_service.chat(req.messages)
            return {
                "response": response,
                "answer": response,
                "sources": [],
                "retrieval_info": None
            }
        else:
            raise HTTPException(status_code=400, detail="Provide either question, message, or messages")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.post("/chat/message")
def chat_message(
    message: str = Form(...),
    session_id: str = Form(...),
    instructions: Optional[str] = Form(None),
    current_user_id: str = Depends(get_current_user),
):
    """
    Chat endpoint that accepts message via form data.
    Used by the AI Panel component.
    """
    try:
        # Verify user owns this session
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get AI service
        session_dir = get_session_dir(session_id)
        ai_service = get_ai_service(session_id, str(session_dir / "ai_index"))
        
        # Build context with instructions if provided
        query = message
        if instructions:
            query = f"Instructions: {instructions}\n\nQuestion: {message}"
        
        # RAG-based query
        result = ai_service.query(query)
        
        # Add message to AI session history
        ai_session = load_ai_session(current_user_id)
        if ai_session and "messages" in ai_session:
            ai_session["messages"].append({
                "role": "user",
                "content": message,
                "timestamp": datetime.utcnow().isoformat(),
            })
            ai_session["messages"].append({
                "role": "assistant",
                "content": result["answer"],
                "timestamp": datetime.utcnow().isoformat(),
            })
            save_ai_session(current_user_id, ai_session)
        
        return {
            "response": result["answer"],
            "sources": result.get("sources", []),
            "retrieval_info": {
                "chunks_retrieved": len(result.get("sources", [])),
                "method": "rag"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.post("/chat/simple")
def chat_simple(
    prompt: str = Form(...),
    session_id: str = Form(None),
    current_user_id: str = Depends(get_current_user),
):
    """
    Simplified chat endpoint that accepts prompt via form data.
    If session_id not provided, uses user's most recent session.
    """
    from api.services.storage_service import get_user_sessions
    
    try:
        # If no session_id, get user's most recent session
        if not session_id:
            user_sessions = get_user_sessions(current_user_id)
            if user_sessions:
                session_id = user_sessions[0]["session_id"]
            else:
                return {"answer": "No session found. Please upload and scan files first.", "sources": [], "retrievals": []}
        
        # Verify user owns this session
        session_metadata = get_session_metadata(session_id)
        if session_metadata.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get AI service
        session_dir = get_session_dir(session_id)
        ai_service = get_ai_service(session_id, str(session_dir / "ai_index"))
        
        # RAG query
        result = ai_service.query(prompt)
        
        # Format retrievals for frontend
        retrievals = []
        for src in result.get("sources", []):
            retrievals.append({
                "doc": src.get("file", "unknown"),
                "score": "—",
                "snippet": src.get("snippet", "")[:100]
            })
        
        return {
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "retrievals": retrievals,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simple chat failed: {e}", exc_info=True)
        return {"answer": f"Error: {str(e)}", "sources": [], "retrievals": []}


# ============================================================
# Advanced RAG Chat Endpoint
# ============================================================

@router.post("/chat/advanced", response_model=ChatResponse)
def advanced_chat(
    req: ChatRequest,
    current_user_id: str = Depends(get_current_user),
):
    """
    Advanced RAG chat with hybrid retrieval, query planning, and citations.
    Uses the new RAGService for improved results.
    """
    from api.services.rag_service import RAGService
    
    try:
        # Verify user owns session
        session_metadata = get_session_metadata(req.session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(req.session_id)
        
        # Initialize RAG service
        rag_service = RAGService(
            persist_dir=str(session_dir / "chroma_db"),
            collection_name=f"session_{req.session_id}"
        )
        
        if not rag_service.collection:
            raise HTTPException(status_code=400, detail="No indexed data. Run indexing first.")
        
        if req.question:
            # RAG query with hybrid retrieval
            result = rag_service.query(req.question, top_k=req.top_k)
            
            # Format sources
            sources = []
            retrievals = []
            for r in result.get("retrievals", []):
                sources.append(SourceDocument(
                    file=r.get("stub", "unknown"),
                    group=r.get("group"),
                    snippet=r.get("text", "")[:200],
                    score=r.get("final_score"),
                    chunk_index=r.get("chunk_index")
                ))
                retrievals.append(RetrievalInfo(
                    doc=r.get("stub", "unknown"),
                    score=r.get("final_score", 0.0),
                    snippet=r.get("text", "")[:100],
                    method="hybrid"
                ))
            
            return ChatResponse(
                answer=result.get("answer", ""),
                sources=sources,
                retrievals=retrievals,
                query_plan=result.get("query_plan")
            )
        
        elif req.messages:
            # Conversational chat with RAG context
            result = rag_service.chat(req.messages)
            return ChatResponse(
                answer=result.get("answer", ""),
                sources=[],
                retrievals=[]
            )
        
        else:
            raise HTTPException(status_code=400, detail="Provide either question or messages")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Advanced chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Advanced chat failed: {str(e)}")


# ============================================================
# Comparison Endpoints
# ============================================================

@router.post("/compare-zips")
async def compare_zip_files(
    session_id: str = Form(...),
    left_filename: str = Form(...),
    right_filename: str = Form(...),
    selected_groups: Optional[str] = Form(None),  # Comma-separated
    current_user_id: str = Depends(get_current_user),
):
    """
    Compare two ZIP files with detailed delta analysis.
    """
    from api.services.comparison_service import compare_zip_files as do_compare
    
    try:
        # Verify user owns session
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        
        # Find ZIP files
        left_path = session_dir / left_filename
        right_path = session_dir / right_filename
        
        if not left_path.exists():
            raise HTTPException(status_code=404, detail=f"Left ZIP not found: {left_filename}")
        if not right_path.exists():
            raise HTTPException(status_code=404, detail=f"Right ZIP not found: {right_filename}")
        
        # Parse selected groups
        groups = None
        if selected_groups:
            groups = [g.strip() for g in selected_groups.split(",") if g.strip()]
        
        # Run comparison
        result = do_compare(
            left_path,
            right_path,
            session_dir,
            selected_groups=groups
        )
        
        # Format response
        group_comparisons = [
            GroupComparisonInfo(
                group=gs.group,
                files_added=gs.files_added,
                files_removed=gs.files_removed,
                files_modified=gs.files_modified,
                files_unchanged=gs.files_unchanged,
                rows_added=gs.rows_added,
                rows_removed=gs.rows_removed
            )
            for gs in result.group_comparisons.values()
        ]
        
        file_comparisons = [
            FileComparisonInfo(
                filename=fc.filename,
                logical_path=fc.logical_path,
                group=fc.group,
                status=fc.status.value if hasattr(fc.status, 'value') else str(fc.status),
                left_row_count=fc.left_row_count,
                right_row_count=fc.right_row_count,
                rows_added=fc.rows_added,
                rows_removed=fc.rows_removed
            )
            for gs in result.group_comparisons.values()
            for fc in gs.file_comparisons
        ][:100]  # Limit to first 100
        
        return CompareZipsResponse(
            status="success",
            left_zip_name=result.left_zip_name,
            right_zip_name=result.right_zip_name,
            summary=result.summary,
            group_comparisons=group_comparisons,
            file_comparisons=file_comparisons,
            elapsed_seconds=result.elapsed_seconds,
            errors=result.errors[:20]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP comparison failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ZIP comparison failed: {str(e)}")


# ============================================================
# RAG Status Endpoint
# ============================================================

@router.get("/rag-status/{session_id}", response_model=RAGStatus)
def get_rag_status(
    session_id: str,
    current_user_id: str = Depends(get_current_user),
):
    """Get RAG system status for a session"""
    try:
        session_metadata = get_session_metadata(session_id)
        stored_user = session_metadata.get("user_id", "")
        if stored_user and stored_user != current_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_dir = get_session_dir(session_id)
        chroma_dir = session_dir / "chroma_db"
        
        is_indexed = chroma_dir.exists()
        indexed_groups = session_metadata.get("indexed_groups", [])
        index_stats = session_metadata.get("index_stats", {})
        
        return RAGStatus(
            session_id=session_id,
            is_indexed=is_indexed,
            collection_name=f"session_{session_id}" if is_indexed else None,
            document_count=index_stats.get("total_chunks", 0),
            groups_indexed=indexed_groups,
            last_indexed=index_stats.get("timestamp"),
            index_mode=None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get RAG status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get RAG status")

