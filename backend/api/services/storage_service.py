"""
Storage Service
Manages session-specific file storage, metadata, and cleanup.

Uses atomic writes to prevent corruption from crashes or concurrent access.
"""
from pathlib import Path
from datetime import datetime, timezone
import shutil
import uuid
import logging
from typing import Optional, List

from api.core.config import settings
from api.core.session_cache import get_session_cache
from api.utils.io_utils import atomic_write_json, safe_read_json, safe_delete

logger = logging.getLogger(__name__)

RUNTIME_ROOT = Path(settings.RET_RUNTIME_ROOT).resolve()
SESSIONS_ROOT = RUNTIME_ROOT / "sessions"
SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)


def create_session_dir(user_id: str = "") -> str:
    """
    Create a new session directory with standard subdirectories.
    
    Args:
        user_id: Owner user ID
        
    Returns:
        New session ID
    """
    sid = uuid.uuid4().hex
    path = SESSIONS_ROOT / sid
    path.mkdir(parents=True)
    (path / "input").mkdir()
    (path / "output").mkdir()
    (path / "extracted").mkdir()
    (path / "ai_index").mkdir()
    
    # Create metadata with timestamps
    metadata = {
        "session_id": sid,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_modified": datetime.now(timezone.utc).isoformat(),
    }
    
    # Use atomic write for safety
    atomic_write_json(path / "metadata.json", metadata)
    
    return sid


def get_session_dir(session_id: str) -> Path:
    """
    Get the session directory path with safety checks.
    
    Prevents directory traversal attacks.
    """
    path = (SESSIONS_ROOT / session_id).resolve()
    if not str(path).startswith(str(SESSIONS_ROOT)):
        raise ValueError("Invalid session path")
    return path


def save_upload(session_id: str, filename: str, data: bytes) -> Path:
    """Save an uploaded file to the session's input directory."""
    p = get_session_dir(session_id) / "input" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    
    # Update session last_modified timestamp
    _touch_session(session_id)
    
    return p


def cleanup_session(session_id: str) -> None:
    """
    Clean up a session and all its resources.
    
    Cleans up:
    - AI indexer resources
    - Cache entries
    - Session directory
    """
    logger.info("Cleaning up session: %s", session_id)
    
    try:
        from api.services.ai_indexing_service import clear_session_indexer
        clear_session_indexer(session_id)
    except Exception:
        logger.debug("No AI index cleanup or failed (continuing)")

    try:
        cache = get_session_cache()
        cache.clear_pattern(f"session:{session_id}:")
    except Exception:
        logger.debug("Cache cleanup failed (continuing)")

    try:
        p = get_session_dir(session_id)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            logger.info("Deleted session directory: %s", p)
    except ValueError:
        logger.debug("Session directory not found: %s", session_id)
    except Exception:
        logger.exception("Failed to delete session directory %s", session_id)


def get_session_metadata(session_id: str) -> dict:
    """Get session metadata, returning empty dict if not found."""
    try:
        p = get_session_dir(session_id) / "metadata.json"
        return safe_read_json(p, default={})
    except ValueError:
        return {}


def save_session_metadata(session_id: str, metadata: dict) -> None:
    """
    Save session metadata atomically.
    
    Updates the last_modified timestamp automatically.
    """
    metadata["last_modified"] = datetime.now(timezone.utc).isoformat()
    p = get_session_dir(session_id) / "metadata.json"
    atomic_write_json(p, metadata)


def update_session_metadata(session_id: str, updates: dict) -> dict:
    """
    Update specific fields in session metadata.
    
    Args:
        session_id: Session ID
        updates: Dictionary of fields to update
        
    Returns:
        Updated metadata
    """
    meta = get_session_metadata(session_id)
    meta.update(updates)
    save_session_metadata(session_id, meta)
    return meta


def _touch_session(session_id: str) -> None:
    """Update the last_modified timestamp for a session."""
    try:
        meta = get_session_metadata(session_id)
        meta["last_modified"] = datetime.now(timezone.utc).isoformat()
        p = get_session_dir(session_id) / "metadata.json"
        atomic_write_json(p, meta)
    except Exception:
        pass  # Non-critical operation


def get_user_sessions(user_id: str) -> List[dict]:
    """
    Get all sessions for a user.
    
    Returns sessions sorted by creation date (newest first).
    """
    sessions = []
    for sd in SESSIONS_ROOT.iterdir():
        if not sd.is_dir():
            continue
        m = sd / "metadata.json"
        if not m.exists():
            continue
        try:
            meta = safe_read_json(m, default={})
            if meta.get("user_id") == user_id:
                created = meta.get("created_at", sd.stat().st_ctime)
                sessions.append({"session_id": sd.name, "created_at": created, **meta})
        except Exception:
            continue
    sessions.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return sessions


def cleanup_user_sessions(user_id: str) -> int:
    """
    Clean up all sessions for a user.
    
    Returns the number of sessions cleaned up.
    """
    count = 0
    for s in get_user_sessions(user_id):
        cleanup_session(s["session_id"])
        count += 1
    return count


def session_exists(session_id: str) -> bool:
    """Check if a session directory exists."""
    try:
        p = get_session_dir(session_id)
        return p.exists() and p.is_dir()
    except ValueError:
        return False
