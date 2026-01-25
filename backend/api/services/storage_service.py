from pathlib import Path
import shutil
import uuid
from api.core.config import settings

RUNTIME_ROOT = Path(settings.RET_RUNTIME_ROOT).resolve()
SESSIONS_ROOT = RUNTIME_ROOT / "sessions"
SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)

def create_session_dir() -> str:
    sid = uuid.uuid4().hex
    path = SESSIONS_ROOT / sid
    path.mkdir(parents=True)
    (path / "input").mkdir()
    (path / "output").mkdir()
    return sid

def get_session_dir(session_id: str) -> Path:
    path = (SESSIONS_ROOT / session_id).resolve()
    if not str(path).startswith(str(SESSIONS_ROOT)):
        raise ValueError("Invalid session path")
    return path

def save_upload(session_id: str, filename: str, data: bytes) -> Path:
    path = get_session_dir(session_id) / "input" / filename
    with open(path, "wb") as f:
        f.write(data)
    return path

def cleanup_session(session_id: str):
    path = get_session_dir(session_id)
    shutil.rmtree(path, ignore_errors=True)
