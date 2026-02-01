"""
Storage Service
Manages session-specific file storage, metadata, and cleanup.
"""
from pathlib import Path
import shutil
import uuid
import json
import logging
from typing import Optional, List

from api.core.config import settings
from api.core.session_cache import get_session_cache

logger = logging.getLogger(__name__)

RUNTIME_ROOT = Path(settings.RET_RUNTIME_ROOT).resolve()
SESSIONS_ROOT = RUNTIME_ROOT / "sessions"
SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)


def create_session_dir(user_id: str = "") -> str:
    sid = uuid.uuid4().hex
    path = SESSIONS_ROOT / sid
    path.mkdir(parents=True)
    (path / "input").mkdir()
    (path / "output").mkdir()
    (path / "extracted").mkdir()
    (path / "ai_index").mkdir()
    metadata = {"session_id": sid, "user_id": user_id}
    (path / "metadata.json").write_text(json.dumps(metadata))
    return sid


def get_session_dir(session_id: str) -> Path:
    path = (SESSIONS_ROOT / session_id).resolve()
    if not str(path).startswith(str(SESSIONS_ROOT)):
        raise ValueError("Invalid session path")
    return path


def save_upload(session_id: str, filename: str, data: bytes) -> Path:
    p = get_session_dir(session_id) / "input" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def cleanup_session(session_id: str):
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
    except Exception:
        logger.exception("Failed to delete session directory %s", session_id)


def get_session_metadata(session_id: str) -> dict:
    p = get_session_dir(session_id) / "metadata.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_session_metadata(session_id: str, metadata: dict):
    p = get_session_dir(session_id) / "metadata.json"
    p.write_text(json.dumps(metadata, indent=2))


def get_user_sessions(user_id: str) -> List[dict]:
    sessions = []
    for sd in SESSIONS_ROOT.iterdir():
        if not sd.is_dir():
            continue
        m = sd / "metadata.json"
        if not m.exists():
            continue
        try:
            meta = json.loads(m.read_text())
            if meta.get("user_id") == user_id:
                created = meta.get("created_at", sd.stat().st_ctime)
                sessions.append({"session_id": sd.name, "created_at": created, **meta})
        except Exception:
            continue
    sessions.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return sessions


def cleanup_user_sessions(user_id: str):
    for s in get_user_sessions(user_id):
        cleanup_session(s["session_id"])
