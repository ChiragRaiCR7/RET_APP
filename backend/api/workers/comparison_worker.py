

"""
comparison_worker.py

Async background worker for comparison tasks.

Uses the BackgroundTaskManager from celery_app (Celery-compatible interface).
Tasks run as asyncio.Tasks with CPU-bound work offloaded via asyncio.to_thread().

Updates Job state in DB via async base_task helpers:
- RUNNING / SUCCESS / FAILED
- progress 0..100
- result / error
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

from api.workers.celery_app import celery
from api.workers.base_task import mark_running, update_progress, mark_success, mark_failed

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _as_int_job_id(job_id: Union[str, int]) -> int:
    try:
        return int(job_id)
    except Exception:
        raise ValueError(f"Invalid job_id: {job_id!r} (expected int or numeric string)")


def _json_safe(value: Any) -> Any:
    """Ensure result is JSON-serializable for Job.result (JSON column)."""
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except Exception:
        return {"_non_json_": str(value)}


# -------------------------------------------------------------------
# Task: Session-to-session comparison
# -------------------------------------------------------------------
@celery.task(name="comparison_task")
async def comparison_task(
    left_session_id: str,
    right_session_id: str,
    job_id: Union[str, int],
) -> Dict[str, Any]:
    """
    Session-to-session background comparison (async).
    """
    jid = _as_int_job_id(job_id)

    logger.info(
        "Starting session comparison task",
        extra={"job_id": jid, "left": left_session_id, "right": right_session_id},
    )

    await mark_running(jid, progress=5)

    try:
        await update_progress(jid, 20)

        # CPU-bound comparison in thread
        from api.services.comparison_service import compare_sessions
        result = await asyncio.to_thread(compare_sessions, left_session_id, right_session_id)

        if isinstance(result, dict) and result.get("error"):
            err = str(result["error"])
            await mark_failed(jid, err)
            return {"error": err}

        if not isinstance(result, dict):
            err = "Unexpected result type from compare_sessions"
            await mark_failed(jid, err)
            return {"error": err}

        await mark_success(jid, _json_safe(result))
        return result

    except asyncio.CancelledError:
        logger.warning("Session comparison task cancelled (job_id=%s)", jid)
        await mark_failed(jid, "Task cancelled")
        raise

    except Exception as e:
        logger.exception("Session comparison crashed (job_id=%s)", jid)
        await mark_failed(jid, f"Comparison worker failed: {str(e)}")
        return {"error": f"Comparison worker failed: {str(e)}"}


# -------------------------------------------------------------------
# Task: Uploaded-file comparison
# -------------------------------------------------------------------
@celery.task(name="comparison_files_task")
async def comparison_files_task(
    file_a_path: str,
    file_a_name: str,
    file_b_path: str,
    file_b_name: str,
    job_id: Union[str, int],
    *,
    ignore_case: bool = False,
    trim_whitespace: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    ignore_columns: Optional[str] = None,
    cleanup_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Uploaded-file background comparison (async).
    """
    jid = _as_int_job_id(job_id)

    logger.info(
        "Starting file comparison task",
        extra={
            "job_id": jid,
            "file_a": file_a_name,
            "file_b": file_b_name,
        },
    )

    await mark_running(jid, progress=5)

    try:
        a_path = Path(file_a_path)
        b_path = Path(file_b_path)

        if not a_path.exists():
            raise FileNotFoundError(f"File A not found: {file_a_path}")
        if not b_path.exists():
            raise FileNotFoundError(f"File B not found: {file_b_path}")

        await update_progress(jid, 15)

        # Read files in thread to avoid blocking event loop
        a_bytes = await asyncio.to_thread(a_path.read_bytes)
        b_bytes = await asyncio.to_thread(b_path.read_bytes)

        await update_progress(jid, 30)

        # CPU-bound comparison in thread
        from api.services.comparison_service import compare_files
        res = await asyncio.to_thread(
            compare_files,
            a_bytes,
            file_a_name or a_path.name,
            b_bytes,
            file_b_name or b_path.name,
            ignore_case=bool(ignore_case),
            trim_whitespace=bool(trim_whitespace),
            similarity_pairing=bool(similarity_pairing),
            sim_threshold=float(sim_threshold),
            ignore_columns=ignore_columns,
        )

        payload = _json_safe(res.to_dict())
        await mark_success(jid, payload)
        return payload

    except asyncio.CancelledError:
        logger.warning("File comparison task cancelled (job_id=%s)", jid)
        await mark_failed(jid, "Task cancelled")
        raise

    except Exception as e:
        logger.exception("File comparison crashed (job_id=%s)", jid)
        await mark_failed(jid, f"Comparison worker failed: {str(e)}")
        return {"error": f"Comparison worker failed: {str(e)}"}

    finally:
        if cleanup_dir:
            try:
                await asyncio.to_thread(shutil.rmtree, cleanup_dir, True)
            except Exception:
                pass
