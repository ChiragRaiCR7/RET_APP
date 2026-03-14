
"""
I/O Utilities for safe file operations.

Provides atomic file writes and other safe I/O patterns.

Non-breaking improvements:
- Uses unique temp files to avoid collisions under concurrency
- Best-effort fsync before atomic replace to reduce risk of data loss on abrupt power loss
- Unified logging helper for loguru/stdlib
- Robust temp cleanup on failure
"""

from __future__ import annotations

import json
import os
import uuid
import logging
from pathlib import Path
from typing import Any, Union, Optional

try:
    from loguru import logger as loguru_logger  # type: ignore
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    loguru_logger = None

_std_logger = logging.getLogger(__name__)


def _log(level: str, msg: str, **fields: Any) -> None:
    """
    Unified logging helper for stdlib + loguru.
    """
    if HAS_LOGURU and loguru_logger is not None:
        loguru_logger.bind(**fields).log(level.upper(), msg)
    else:
        extra = {"extra_fields": fields} if fields else None
        getattr(_std_logger, level.lower(), _std_logger.info)(msg, extra=extra)


def _tmp_path_for(path: Path) -> Path:
    """
    Generate a unique temp path in the same directory so os.replace() is atomic.
    """
    # Keep suffix so tools/editors recognize file type; add unique token to avoid collisions
    return path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")


def _fsync_file_descriptor(fd: int) -> None:
    """
    Best-effort flush to disk. Safe no-op if not supported.
    """
    try:
        os.fsync(fd)
    except Exception:
        # Not all environments/filesystems support fsync cleanly; ignore.
        pass


def atomic_write_text(path: Union[str, Path], content: str, encoding: str = "utf-8") -> None:
    """
    Write text content to a file atomically.

    Uses a temporary file in the same directory + os.replace() to ensure atomic write.
    Prevents partial writes from corrupting the file on crashes.

    Args:
        path: Target file path
        content: Text content to write
        encoding: Text encoding (default: utf-8)
    """
    path = Path(path)
    tmp_path = _tmp_path_for(path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Write to temp file, fsync, then replace
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            _fsync_file_descriptor(f.fileno())

        os.replace(tmp_path, path)
    except Exception as e:
        # Clean up temp file on failure
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        _log("warning", "atomic_write_text failed", path=str(path), error=str(e))
        raise


def atomic_write_bytes(path: Union[str, Path], data: bytes) -> None:
    """
    Write binary content to a file atomically.

    Uses a temporary file in the same directory + os.replace() to ensure atomic write.

    Args:
        path: Target file path
        data: Binary content to write
    """
    path = Path(path)
    tmp_path = _tmp_path_for(path)

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            _fsync_file_descriptor(f.fileno())

        os.replace(tmp_path, path)
    except Exception as e:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        _log("warning", "atomic_write_bytes failed", path=str(path), error=str(e))
        raise


def atomic_write_json(path: Union[str, Path], data: Any, indent: int = 2) -> None:
    """
    Write JSON data to a file atomically.

    Args:
        path: Target file path
        data: Data to serialize as JSON
        indent: JSON indentation level (default: 2)
    """
    content = json.dumps(data, indent=indent, ensure_ascii=False, default=str)
    atomic_write_text(path, content)


def safe_read_json(path: Union[str, Path], default: Any = None) -> Any:
    """
    Safely read JSON from a file.

    Returns the default value if the file doesn't exist or can't be parsed.

    Args:
        path: File path to read
        default: Default value if file doesn't exist or is invalid

    Returns:
        Parsed JSON data or default value
    """
    path = Path(path)
    if not path.exists():
        return default

    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content)
    except Exception as e:
        _log("warning", "safe_read_json failed", path=str(path), error=str(e))
        return default


def safe_delete(path: Union[str, Path]) -> bool:
    """
    Safely delete a file or directory.

    Returns True if deleted successfully, False if it didn't exist or failed.

    Args:
        path: File or directory path to delete

    Returns:
        True if deleted, False otherwise
    """
    import shutil

    path = Path(path)
    if not path.exists():
        return False

    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
        return True
    except Exception as e:
        _log("warning", "safe_delete failed", path=str(path), error=str(e))
        return False

