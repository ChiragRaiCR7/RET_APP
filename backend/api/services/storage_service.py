from pathlib import Path
import shutil
import uuid
import json
from api.core.config import settings

RUNTIME_ROOT = Path(settings.RET_RUNTIME_ROOT).resolve()
SESSIONS_ROOT = RUNTIME_ROOT / "sessions"
SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)

def create_session_dir(user_id: str = "") -> str:
    """Create a new session directory for a user"""
    sid = uuid.uuid4().hex
    path = SESSIONS_ROOT / sid
    path.mkdir(parents=True)
    (path / "input").mkdir()
    (path / "output").mkdir()
    (path / "extracted").mkdir()
    
    # Create metadata file
    metadata = {
        "session_id": sid,
        "user_id": user_id,
    }
    metadata_path = path / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f)
    
    return sid

def get_session_dir(session_id: str) -> Path:
    """Get session directory with path traversal protection"""
    path = (SESSIONS_ROOT / session_id).resolve()
    if not str(path).startswith(str(SESSIONS_ROOT)):
        raise ValueError("Invalid session path")
    return path

def save_upload(session_id: str, filename: str, data: bytes) -> Path:
    """Save uploaded file to session input directory"""
    path = get_session_dir(session_id) / "input" / filename
    with open(path, "wb") as f:
        f.write(data)
    return path

def cleanup_session(session_id: str):
    """Clean up session directory and all associated data"""
    # Clear AI indexer if exists
    try:
        from api.services.ai_indexing_service import clear_session_indexer
        clear_session_indexer(session_id)
    except Exception as e:
        pass  # Continue even if indexer cleanup fails
    
    path = get_session_dir(session_id)
    shutil.rmtree(path, ignore_errors=True)

def get_session_metadata(session_id: str) -> dict:
    """Load session metadata"""
    path = get_session_dir(session_id) / "metadata.json"
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_session_metadata(session_id: str, metadata: dict):
    """Save session metadata"""
    path = get_session_dir(session_id) / "metadata.json"
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)

def get_user_sessions(user_id: str) -> list[str]:
    """Get all sessions for a user"""
    sessions = []
    if SESSIONS_ROOT.exists():
        for session_dir in SESSIONS_ROOT.iterdir():
            if session_dir.is_dir():
                metadata_path = session_dir / "metadata.json"
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r") as f:
                            metadata = json.load(f)
                            if metadata.get("user_id") == user_id:
                                sessions.append(session_dir.name)
                    except:
                        pass
    return sessions

def cleanup_user_sessions(user_id: str):
    """Clean up all sessions for a user"""
    sessions = get_user_sessions(user_id)
    for session_id in sessions:
        cleanup_session(session_id)

