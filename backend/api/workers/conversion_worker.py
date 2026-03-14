

"""
conversion_worker.py

Async background worker for conversion tasks.

Uses the BackgroundTaskManager from celery_app (Celery-compatible interface).
Tasks run as asyncio.Tasks with CPU-bound work offloaded via asyncio.to_thread().

Updates Job state in DB via async base_task helpers:
- RUNNING / SUCCESS / FAILED
- progress 0..100
- result / error
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, List, Union

from api.workers.celery_app import celery
from api.workers.base_task import mark_running, update_progress, mark_success, mark_failed
from api.services.ai.session_manager import trigger_auto_embed_after_conversion

logger = logging.getLogger(__name__)


def _as_int_job_id(job_id: Union[str, int]) -> int:
    """Convert job_id to int safely (Job.id is int)."""
    try:
        return int(job_id)
    except Exception:
        raise ValueError(f"Invalid job_id: {job_id!r} (expected int or numeric string)")


@celery.task(bind=True, name="conversion_task")
async def conversion_task(
    self,
    session_id: str,
    job_id: Union[str, int],
    groups: Optional[List[str]] = None,
    output_format: str = "csv",
):
    """
    Execute a conversion job for the given session_id.

    Args:
        session_id: Session identifier
        job_id: DB job id (int or numeric string)
        groups: Optional list of groups to convert
        output_format: Conversion output format (csv/xlsx)

    Returns:
        dict result from convert_session()
    """
    jid = _as_int_job_id(job_id)

    logger.info(
        "Starting conversion task",
        extra={
            "job_id": jid,
            "session_id": session_id,
            "groups": groups,
            "output_format": output_format,
        },
    )

    # Mark job running (DB) — async
    await mark_running(jid, progress=5)

    try:
        await update_progress(jid, 10)

        # Run CPU-bound conversion in a thread to avoid blocking the event loop
        from api.services.conversion_service import convert_session
        result = await asyncio.to_thread(convert_session, session_id, groups, output_format)

        # Conversion done — report progress before auto-embed
        await update_progress(jid, 70)

        # Normalize service errors
        if isinstance(result, dict) and result.get("error"):
            err = str(result["error"])
            await mark_failed(jid, err)
            return {"error": err}

        await update_progress(jid, 75)

        embedding_meta = {
            "status": "not_attempted",
            "attempted": False,
            "triggered": False,
            "eligible_groups": [],
            "message": "Auto-embedding not attempted",
        }
        try:
            from api.services.storage_service import get_session_metadata

            session_meta = get_session_metadata(session_id)
            user_id = str(session_meta.get("user_id", "") or "").strip()
            if user_id:
                embedding_meta = trigger_auto_embed_after_conversion(
                    session_id=session_id,
                    user_id=user_id,
                    conversion_result=result if isinstance(result, dict) else None,
                )
            else:
                embedding_meta["message"] = "Auto-embedding not attempted: missing session owner"
        except Exception as e:
            logger.warning("Failed to run auto-embed trigger for session %s: %s", session_id, e)
            embedding_meta.update(
                {
                    "status": "failed",
                    "attempted": True,
                    "triggered": False,
                    "message": f"Auto-embedding trigger failed: {e}",
                }
            )

        result_payload: Dict[str, Any] = (
            dict(result) if isinstance(result, dict) else {"result": result}
        )
        result_payload["embedding_status"] = str(embedding_meta.get("status", "not_attempted"))
        result_payload["embedding"] = embedding_meta

        await update_progress(jid, 95)
        await mark_success(jid, result_payload)
        return result_payload

    except asyncio.CancelledError:
        logger.warning("Conversion task cancelled (job_id=%s)", jid)
        await mark_failed(jid, "Task cancelled")
        raise

    except Exception as e:
        logger.exception(
            "Conversion task failed",
            extra={"job_id": jid, "session_id": session_id},
        )
        await mark_failed(jid, str(e))
        return {"error": str(e)}