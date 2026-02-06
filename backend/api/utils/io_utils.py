"""
I/O Utilities for safe file operations.

Provides atomic file writes and other safe I/O patterns.
"""
import json
import os
from pathlib import Path
from typing import Any, Union
import logging

try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)


def atomic_write_text(path: Union[str, Path], content: str, encoding: str = "utf-8") -> None:
    """
    Write text content to a file atomically.
    
    Uses a temporary file and os.replace() to ensure the write is atomic.
    This prevents partial writes from corrupting the file on crashes.
    
    Args:
        path: Target file path
        content: Text content to write
        encoding: Text encoding (default: utf-8)
    """
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temporary file
        tmp_path.write_text(content, encoding=encoding)
        
        # Atomic replace
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise


def atomic_write_bytes(path: Union[str, Path], data: bytes) -> None:
    """
    Write binary content to a file atomically.
    
    Uses a temporary file and os.replace() to ensure the write is atomic.
    
    Args:
        path: Target file path
        data: Binary content to write
    """
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temporary file
        tmp_path.write_bytes(data)
        
        # Atomic replace
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
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
    except (json.JSONDecodeError, OSError) as e:
        log_msg = f"Failed to read JSON from {path}: {e}"
        if HAS_LOGURU:
            logger.warning(log_msg)
        else:
            logger.warning(log_msg)
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
        log_msg = f"Failed to delete {path}: {e}"
        if HAS_LOGURU:
            logger.warning(log_msg)
        else:
            logger.warning(log_msg)
        return False
