#!/usr/bin/env python3
"""
RET-v4 Backend — Startup Script

Improvements over legacy version:
  1. .env loading via python-dotenv before any imports
  2. Pre-flight checks (JWT_SECRET_KEY required; DATABASE_URL defaults to SQLite)
  3. Migration subprocess with configurable timeout
  4. In-process uvicorn.run() — no nested subprocess
  5. Colored structured logging via loguru
  6. Post-startup health check (background thread, non-blocking)
  7. Structured log output suitable for production pipelines
"""

import os
import sys
import signal
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from argparse import ArgumentParser

# ------------------------------------------------
# Path setup (must happen before local imports)
# ------------------------------------------------

BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))

# ------------------------------------------------
# 1. .env loading
# ------------------------------------------------

from dotenv import load_dotenv  # noqa: E402  (python-dotenv is a hard dep)

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# ------------------------------------------------
# 5. Colored structured logging via loguru
#    Early sinks: stderr + main log file so that
#    preflight / migration output is persisted.
# ------------------------------------------------

import logging as _logging  # noqa: E402
from loguru import logger   # noqa: E402  (loguru is a hard dep)


def _early_log_file() -> str:
    """Compute log file path from env vars — mirrors logging_config._log_file_path()."""
    log_file = os.getenv("LOG_FILE")
    if log_file:
        p = Path(log_file).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)
    runtime_root = os.getenv("RET_RUNTIME_ROOT", "./runtime")
    log_dir = Path(runtime_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / "ret-v4.log")


logger.remove()
_EARLY_LOG = _early_log_file()

# Console sink (coloured)
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{message}</cyan>"
    ),
    colorize=True,
    level="INFO",
)

# File sink — same path that configure_logging() will use later.
# Early output (preflight, migrations) is written here before the
# app's logging bootstrap overwrites the sinks.
logger.add(
    _EARLY_LOG,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | startup - {message}",
    rotation="500 MB",
    retention="7 days",
    level="INFO",
)


# Route stdlib logging through Loguru so uvicorn / alembic output is
# captured by the same sinks during early startup.
class _BootInterceptHandler(_logging.Handler):
    def emit(self, record: _logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = _logging.currentframe(), 2
        while frame and frame.f_code.co_filename == _logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


_logging.basicConfig(handlers=[_BootInterceptHandler()], level=0, force=True)

# ------------------------------------------------
# CLI Arguments
# ------------------------------------------------

parser = ArgumentParser(description="Start RET-v4 backend server")
parser.add_argument("--no-migrate", action="store_true", help="Skip Alembic migrations")
parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload (dev only)")
parser.add_argument("--workers", type=int, default=1, help="Number of uvicorn worker processes")
parser.add_argument("--host", default=os.getenv("API_HOST", "0.0.0.0"))
parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")))
parser.add_argument("--no-health-check", action="store_true", help="Skip post-startup health check")
parser.add_argument("--migration-timeout", type=int,
                    default=int(os.getenv("MIGRATION_TIMEOUT", "120")),
                    help="Seconds before migration is aborted (default: 120)")

args = parser.parse_args()

# ------------------------------------------------
# 2. Pre-flight checks
# ------------------------------------------------

def preflight_checks() -> None:
    """Validate required environment configuration before starting."""
    errors: list[str] = []

    if not os.getenv("JWT_SECRET_KEY"):
        errors.append("JWT_SECRET_KEY is not set")

    # Optional but recommended
    if not os.getenv("AZURE_OPENAI_API_KEY"):
        logger.warning("AZURE_OPENAI_API_KEY not set — AI features will be unavailable")

    if errors:
        for err in errors:
            logger.error(f"Pre-flight check FAILED: {err}")
        raise SystemExit(1)

    logger.info("Pre-flight checks passed")

# ------------------------------------------------
# 3. Migration Runner (with timeout)
# ------------------------------------------------

def run_migrations() -> bool:
    timeout = args.migration_timeout
    logger.info(f"Applying database migrations (alembic upgrade head, timeout={timeout}s)")

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            logger.error(f"Migration timed out after {timeout}s — aborting")
            return False

        for line in stdout.splitlines():
            if line.strip():
                logger.info(f"[alembic] {line.strip()}")

        if process.returncode != 0:
            logger.error(f"Migration failed (exit code {process.returncode})")
            return False

        logger.success("Migrations applied successfully")
        return True

    except FileNotFoundError:
        logger.error("alembic not found — run: pip install alembic")
        return False
    except Exception as exc:
        logger.error(f"Migration error: {exc}")
        return False


def init_database() -> None:
    if args.no_migrate:
        logger.info("Skipping migrations (--no-migrate)")
        return

    if not run_migrations():
        raise SystemExit("Database migrations failed — aborting startup")

# ------------------------------------------------
# 6. Post-startup health check (background thread)
# ------------------------------------------------

_HEALTH_TIMEOUT = 30   # seconds to wait for the server to come up
_HEALTH_INTERVAL = 1   # seconds between retries


def _health_check_worker(host: str, port: int) -> None:
    check_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{check_host}:{port}/health"
    deadline = time.monotonic() + _HEALTH_TIMEOUT

    logger.info(f"Health check: polling {url} (up to {_HEALTH_TIMEOUT}s)")

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    logger.success(f"Health check passed — server is ready at {url}")
                    return
        except Exception:
            time.sleep(_HEALTH_INTERVAL)

    logger.warning(
        f"Health check did not receive 200 within {_HEALTH_TIMEOUT}s — "
        "server may still be initialising"
    )


def _start_health_check_thread(host: str, port: int) -> None:
    t = threading.Thread(
        target=_health_check_worker,
        args=(host, port),
        daemon=True,
        name="health-check",
    )
    t.start()

# ------------------------------------------------
# 4. Server Launcher (in-process uvicorn.run)
# ------------------------------------------------

def start_server() -> None:
    import uvicorn  # imported here so pre-flight errors surface first

    host = args.host
    port = args.port

    logger.info("=" * 60)
    logger.info("RET-v4 Backend Server")
    logger.info(f"  API:     http://{host}:{port}")
    logger.info(f"  Docs:    http://{host}:{port}/docs")
    logger.info(f"  Reload:  {args.reload}")
    logger.info(f"  Workers: {1 if args.reload else args.workers}")
    logger.info("=" * 60)
    logger.info("Press Ctrl+C to stop")

    if not args.no_health_check:
        _start_health_check_thread(host, port)

    # --reload and multiple workers are mutually exclusive in uvicorn
    workers = 1 if args.reload else args.workers

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=args.reload,
        workers=workers,
        log_config=None,       # our Loguru pipeline handles all logging
        access_log=False,      # request logging handled by LoggingMiddleware
    )

# ------------------------------------------------
# Signal handling
# ------------------------------------------------

def _handle_signal(sig, frame):
    logger.info(f"Received signal {sig} — shutting down")
    sys.exit(0)


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ------------------------------------------------
# Main
# ------------------------------------------------

if __name__ == "__main__":
    if _env_file.exists():
        logger.info(f"Loaded environment from {_env_file}")
    else:
        logger.warning(f".env file not found at {_env_file} — relying on environment variables")

    preflight_checks()
    init_database()
    start_server()