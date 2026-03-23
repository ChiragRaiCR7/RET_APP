
from __future__ import annotations

import json
import logging
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

from api.core.config import settings
from api.core.request_context import get_request_context

try:
    from loguru import logger as loguru_logger  # type: ignore
    HAS_LOGURU = True
except ImportError:
    loguru_logger = None
    HAS_LOGURU = False

# Maximum number of per-session loggers to keep open simultaneously.
# Older entries are evicted when this limit is exceeded.
_MAX_SESSION_LOGGERS = 200


# ---------------------------------------------------------------------
# Stdlib → Loguru bridge
# ---------------------------------------------------------------------
class InterceptHandler(logging.Handler):
    """
    Route stdlib logging records through Loguru for unified output.

    Installed on the root stdlib logger and key named loggers so that
    uvicorn, SQLAlchemy, and any other stdlib-based emitters flow
    through the same Loguru sinks (console + file + optional session).
    """

    def emit(self, record: logging.LogRecord) -> None:
        if not HAS_LOGURU or loguru_logger is None:
            return
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# ---------------------------------------------------------------------
# Per-session log file sink
# ---------------------------------------------------------------------
class _SessionSink:
    """
    Dynamic file sink that routes log messages with a ``session_id``
    in ``record["extra"]`` to per-session log files under
    ``{base_dir}/{session_id}/session.log``.

    Manages an LRU cache of open file handles, evicting the oldest
    when ``_MAX_SESSION_LOGGERS`` is exceeded.
    """

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._handles: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()

    def write(self, message: Any) -> None:
        record = message.record
        sid = record["extra"].get("session_id")
        if not sid:
            return
        with self._lock:
            fh = self._get_handle(sid)
            fh.write(str(message))
            fh.flush()

    def _get_handle(self, session_id: str) -> Any:
        if session_id in self._handles:
            self._handles.move_to_end(session_id)
            return self._handles[session_id]
        while len(self._handles) >= _MAX_SESSION_LOGGERS:
            _, old_fh = self._handles.popitem(last=False)
            old_fh.close()
        session_dir = self._base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        fh = open(session_dir / "session.log", "a", encoding="utf-8")
        self._handles[session_id] = fh
        return fh

    def close_session(self, session_id: str) -> None:
        """Close and remove a single session log handle."""
        with self._lock:
            fh = self._handles.pop(session_id, None)
            if fh:
                fh.close()

    def close_all(self) -> None:
        """Close all open session log handles."""
        with self._lock:
            for fh in self._handles.values():
                fh.close()
            self._handles.clear()


_session_sink: Optional[_SessionSink] = None
_session_sink_id: Optional[int] = None  # Loguru sink ID for removal


# ---------------------------------------------------------------------
# Stdlib JSON formatter (fallback + optional structured logging)
# ---------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    """
    Minimal JSON formatter for stdlib logging.
    Injects correlation_id / user_id from RequestContext automatically.
    If your code uses ``extra={"extra_fields": {...}}`` those fields are merged in.
    """

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_request_context()
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": ctx.correlation_id,
        }
        if ctx.user_id:
            payload["user_id"] = ctx.user_id
        if ctx.session_id:
            payload["session_id"] = ctx.session_id

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class ExtraAdapter(logging.LoggerAdapter):
    """
    Allows: ``logger.info("msg", extra={"extra_fields": {...}})`` style.
    Also allows: ``logger.info("msg", foo="bar")`` by mapping kwargs to extra_fields.
    Automatically injects correlation_id, user_id, session_id from RequestContext.
    """

    def process(self, msg, kwargs):
        extra = kwargs.pop("extra", {}) or {}
        fields = dict(kwargs)  # remaining kwargs treated as structured fields
        existing = extra.get("extra_fields", {}) or {}
        existing.update(fields)
        # Auto-inject request context
        ctx = get_request_context()
        if ctx.correlation_id:
            existing.setdefault("correlation_id", ctx.correlation_id)
        if ctx.user_id:
            existing.setdefault("user_id", ctx.user_id)
        if ctx.session_id:
            existing.setdefault("session_id", ctx.session_id)
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

def _make_loguru_sink(*, level: str, fmt: str, log_file: str) -> None:
    """
    Shared helper that adds both the console and file sinks for Loguru,
    ensuring both branches (JSON / text) share identical rotation/retention
    settings without duplicating configuration.
    """
    assert loguru_logger is not None
    loguru_logger.remove()

    is_json = fmt == "json"
    common = {"level": level, "backtrace": False, "diagnose": False}
    if is_json:
        loguru_logger.add(sys.stdout, serialize=True, **common)
        loguru_logger.add(log_file, serialize=True, rotation="500 MB", retention="7 days", **common)
    else:
        text_fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
        loguru_logger.add(sys.stdout, format=text_fmt, colorize=True, **common)
        file_fmt = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}"
        loguru_logger.add(log_file, format=file_fmt, rotation="500 MB", retention="7 days", **common)


def configure_logging() -> None:
    """
    Configure logging for the application.

    Behavior:
    - If Loguru is available: configure Loguru sinks
    - Else: configure stdlib logging

    Both paths install an ``InterceptHandler`` on stdlib root and key
    named loggers (uvicorn, sqlalchemy) so that all output is unified.
    When ``FEATURE_SESSION_LOGGING`` is enabled, a ``_SessionSink`` is
    registered to route messages with ``session_id`` in extras to
    per-session log files.
    """
    global _session_sink, _session_sink_id

    log_level = getattr(settings, "LOG_LEVEL", "INFO")
    log_format = str(getattr(settings, "LOG_FORMAT", "text") or "text").lower()
    log_file = _log_file_path()

    if HAS_LOGURU and loguru_logger is not None:
        _make_loguru_sink(level=log_level, fmt=log_format, log_file=log_file)

        # ── Intercept stdlib loggers ───────────────────────────
        intercept = InterceptHandler()
        logging.basicConfig(handlers=[intercept], level=0, force=True)
        for name in (
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "sqlalchemy",
            "sqlalchemy.engine",
            "sqlalchemy.engine.Engine",
        ):
            _logger = logging.getLogger(name)
            _logger.handlers = [intercept]
            _logger.propagate = False

        # ── Per-session logging ────────────────────────────────
        if getattr(settings, "FEATURE_SESSION_LOGGING", False):
            runtime_root = getattr(settings, "RET_RUNTIME_ROOT", "./runtime") or "./runtime"
            sessions_dir = Path(runtime_root) / "sessions"
            _session_sink = _SessionSink(sessions_dir)
            _session_sink_id = loguru_logger.add(
                _session_sink.write,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
                filter=lambda record: bool(record["extra"].get("session_id")),
                level="DEBUG",
            )

        loguru_logger.info("Logging configured (loguru)", log_file=log_file, format=log_format)
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
    Return a structured logger for *name*.

    Both backends expose ``.info() / .warning() / .error() / .debug()``.
    The stdlib backend is wrapped in ``ExtraAdapter`` so it accepts keyword
    arguments as structured log fields, matching Loguru's calling convention.
    """
    if HAS_LOGURU and loguru_logger is not None:
        return loguru_logger.bind(logger=name)
    return ExtraAdapter(logging.getLogger(name), {})


# ---------------------------------------------------------------------
# Session-scoped logger helpers
# ---------------------------------------------------------------------

def get_session_logger(session_id: str) -> Any:
    """
    Return a logger bound to *session_id*.

    When ``FEATURE_SESSION_LOGGING`` is enabled, messages emitted from
    this logger are also written to
    ``runtime/sessions/{session_id}/session.log``.
    """
    if HAS_LOGURU and loguru_logger is not None:
        return loguru_logger.bind(session_id=session_id)
    return ExtraAdapter(logging.getLogger(f"session.{session_id}"), {})


def close_session_logger(session_id: str) -> None:
    """Close the per-session log file for *session_id*."""
    if _session_sink is not None:
        _session_sink.close_session(session_id)


def close_all_session_loggers() -> None:
    """Close all per-session log files (called during shutdown)."""
    if _session_sink is not None:
        _session_sink.close_all()


# ---------------------------------------------------------------------
# Per-session log files (FEATURE_SESSION_LOGGING)
# ---------------------------------------------------------------------
_session_loggers: Dict[str, Any] = {}  # session_id -> logger


def get_session_logger(session_id: str, user_id: str | None = None) -> Any:
    """
    Return a logger that writes to ``runtime/sessions/{session_id}/session.log``.

    Only active when ``FEATURE_SESSION_LOGGING`` is enabled in settings.
    Falls back to the default module logger otherwise.

    A cap of ``_MAX_SESSION_LOGGERS`` prevents unbounded memory growth;
    the oldest entry is evicted when the limit is hit.
    """
    if not getattr(settings, "FEATURE_SESSION_LOGGING", False):
        return get_logger(f"session.{session_id}")

    if session_id in _session_loggers:
        return _session_loggers[session_id]

    # Evict oldest session logger if cap reached
    if len(_session_loggers) >= _MAX_SESSION_LOGGERS:
        oldest_key = next(iter(_session_loggers))
        _session_loggers.pop(oldest_key, None)

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


def log_chat_message(
    session_id: str,
    role: str,
    content: str,
    *,
    user_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Log an AI chat message (both user queries and assistant replies) to the
    per-session log file so every conversation is auditable.

    Args:
        session_id: The AI processing session identifier.
        role: ``"user"`` or ``"assistant"``.
        content: The full message content.
        user_id: Optional user identifier for filtering.
        metadata: Optional extra structured fields (intent, sources, etc.).
    """
    slogger = get_session_logger(session_id, user_id=user_id)
    fields: dict = {"role": role, "content_length": len(content)}
    if metadata:
        fields.update(metadata)
    # Log a trimmed preview; full content preserved in the session log at DEBUG.
    preview = content[:200] + "..." if len(content) > 200 else content
    slogger.info(f"[CHAT:{role.upper()}] {preview}", **fields)  # type: ignore[call-arg]
