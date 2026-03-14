
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from api.core.config import settings

try:
    from loguru import logger as loguru_logger  # type: ignore
    HAS_LOGURU = True
except ImportError:
    loguru_logger = None
    HAS_LOGURU = False


# ---------------------------------------------------------------------
# Stdlib JSON formatter (fallback + optional structured logging)
# ---------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    """
    Minimal JSON formatter for stdlib logging.
    If your code uses `extra={"extra_fields": {...}}`, those fields are included.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class ExtraAdapter(logging.LoggerAdapter):
    """
    Allows: logger.info("msg", extra={"extra_fields": {...}}) style.
    Also allows: logger.info("msg", foo="bar") by mapping kwargs to extra_fields.
    """

    def process(self, msg, kwargs):
        extra = kwargs.pop("extra", {}) or {}
        fields = dict(kwargs)  # remaining kwargs treated as structured fields
        existing = extra.get("extra_fields", {}) or {}
        existing.update(fields)
        extra["extra_fields"] = existing
        return msg, {"extra": extra}


def _log_dir() -> Path:
    """
    Prefer settings.LOG_FILE if provided, otherwise use settings.RET_RUNTIME_ROOT/logs.
    """
    # If LOG_FILE is configured, ensure its parent exists
    lf = getattr(settings, "LOG_FILE", None)
    if lf:
        p = Path(lf).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p.parent

    runtime_root = getattr(settings, "RET_RUNTIME_ROOT", "./runtime") or "./runtime"
    log_dir = Path(runtime_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _log_file_path() -> str:
    lf = getattr(settings, "LOG_FILE", None)
    if lf:
        return str(Path(lf).expanduser().resolve())
    return str(_log_dir() / "ret-v4.log")


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def configure_logging() -> None:
    """
    Configure logging for the application.

    Behavior:
    - If Loguru is available: configure Loguru sinks
    - Else: configure stdlib logging

    Improvements:
    - Log path uses settings.RET_RUNTIME_ROOT/logs or settings.LOG_FILE
    - JSON output supported via settings.LOG_FORMAT == "json"
    """
    log_level = getattr(settings, "LOG_LEVEL", "INFO")
    log_format = str(getattr(settings, "LOG_FORMAT", "text") or "text").lower()
    log_file = _log_file_path()

    if HAS_LOGURU and loguru_logger is not None:
        # -------------------------
        # Loguru configuration
        # -------------------------
        loguru_logger.remove()

        # Console sink
        if log_format == "json":
            # Loguru JSON serialize: use serialize=True
            loguru_logger.add(
                sys.stdout,
                level=log_level,
                serialize=True,
                backtrace=False,
                diagnose=False,
            )
        else:
            loguru_logger.add(
                sys.stdout,
                level=log_level,
                format=(
                    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                    "<level>{level:<8}</level> | "
                    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                    "<level>{message}</level>"
                ),
                colorize=True,
                backtrace=False,
                diagnose=False,
            )

        # File sink
        if log_format == "json":
            loguru_logger.add(
                log_file,
                level=log_level,
                serialize=True,
                rotation="500 MB",
                retention="7 days",
                backtrace=False,
                diagnose=False,
            )
        else:
            loguru_logger.add(
                log_file,
                level=log_level,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
                rotation="500 MB",
                retention="7 days",
                backtrace=False,
                diagnose=False,
            )

        # Optional: ensure stdlib logs get routed too (if some libs use logging)
        # This doesn't change your existing behavior but helps unify logs.
        logging.getLogger().handlers = []
        logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))

        loguru_logger.info("Logging configured (loguru)", extra={"log_file": log_file, "format": log_format})
        return

    # -------------------------
    # Stdlib fallback
    # -------------------------
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Clear any existing handlers to avoid duplicate logs
    for h in list(root.handlers):
        root.removeHandler(h)

    stream_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")

    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    root.info("Logging configured (stdlib)", extra={"extra_fields": {"log_file": log_file, "format": log_format}})


def get_logger(name: str) -> Any:
    """
    Optional helper to get a logger that supports structured fields.

    - With loguru: returns loguru logger bound with module name
    - With stdlib: returns LoggerAdapter that accepts logger.info("msg", foo="bar")
    """
    if HAS_LOGURU and loguru_logger is not None:
        return loguru_logger.bind(logger=name)

    return ExtraAdapter(logging.getLogger(name), {})


# ---------------------------------------------------------------------
# Per-session log files (FEATURE_SESSION_LOGGING)
# ---------------------------------------------------------------------
_session_loggers: Dict[str, Any] = {}


def get_session_logger(session_id: str, user_id: str | None = None) -> Any:
    """
    Return a logger that writes to ``runtime/sessions/{session_id}/session.log``.

    Only active when ``FEATURE_SESSION_LOGGING`` is enabled.
    Falls back to the default module logger otherwise.
    """
    if not getattr(settings, "FEATURE_SESSION_LOGGING", False):
        return get_logger(f"session.{session_id}")

    if session_id in _session_loggers:
        return _session_loggers[session_id]

    runtime_root = getattr(settings, "RET_RUNTIME_ROOT", "./runtime") or "./runtime"
    log_path = Path(runtime_root) / "sessions" / session_id / "session.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if HAS_LOGURU and loguru_logger is not None:
        sink_id = loguru_logger.add(
            str(log_path),
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
            rotation="50 MB",
            retention="3 days",
            filter=lambda record: record["extra"].get("session_id") == session_id,
            backtrace=False,
            diagnose=False,
        )
        bound = loguru_logger.bind(session_id=session_id, user_id=user_id)
        _session_loggers[session_id] = bound
        return bound

    # stdlib fallback
    slogger = logging.getLogger(f"session.{session_id}")
    slogger.setLevel(logging.DEBUG)
    if not slogger.handlers:
        handler = logging.FileHandler(str(log_path), encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        slogger.addHandler(handler)
        slogger.propagate = False
    adapter = ExtraAdapter(slogger, {"session_id": session_id, "user_id": user_id})
    _session_loggers[session_id] = adapter
    return adapter


def cleanup_session_logger(session_id: str) -> None:
    """Remove session logger from cache (called on session cleanup)."""
    _session_loggers.pop(session_id, None)
