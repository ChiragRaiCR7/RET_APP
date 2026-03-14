
"""
Background Task Manager — Async Local Worker / Task Queue Module

Production-grade in-process background task system:
- No Redis/RabbitMQ required
- Runs tasks using asyncio.create_task() for I/O-bound work
- Uses asyncio.to_thread() for CPU-bound work
- Preserves a Celery-like interface:
    - task_manager.task(...) decorator
    - returned task object has .delay(...) and .apply_async(...)

Also includes an optional JobQueue that stores job state in runtime/jobs/*.json
(In your project you already store jobs in DB; this file store is optional and
can be used for debugging or non-DB tasks.)

Non-breaking improvements:
- Adds shutdown() for graceful shutdown with timeout
- Atomic file writes for JobQueue to prevent corruption
- asyncio.Semaphore-based concurrency control
- Comprehensive logging and error handling
- Task cancellation support
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Optional: Lightweight file-based job queue
# -------------------------------------------------------------------
class JobQueue:
    """
    Simple file-based job store (runtime/jobs/<job_id>.json)
    Useful for local development or non-DB task tracking.
    """

    def __init__(self, runtime_root: str = "./runtime"):
        self.runtime_root = Path(runtime_root)
        self.jobs_dir = self.runtime_root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    async def _atomic_write_json(self, path: Path, data: dict) -> None:
        """
        Atomic write: write to temp then os.replace().
        Prevents partial writes/corrupt files if process dies mid-write.
        """
        tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
        payload = json.dumps(data, ensure_ascii=False)
        await asyncio.to_thread(tmp.write_text, payload, "utf-8")
        await asyncio.to_thread(os.replace, tmp, path)

    async def create_job(self, session_id: str, job_id: str, task_name: str) -> dict:
        """Create and persist a new job record."""
        job_id = str(job_id)
        job = {
            "job_id": job_id,
            "session_id": session_id,
            "task_name": task_name,
            "status": "PENDING",
            "result": None,
            "error": None,
        }
        await self.update_job(job_id, status="PENDING", result=None, error=None, extra=job)
        return job

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Read job status from file."""
        job_id = str(job_id)
        job_file = self._job_file(job_id)

        if not job_file.exists():
            return None
        try:
            content = await asyncio.to_thread(job_file.read_text, "utf-8")
            return json.loads(content)
        except Exception:
            logger.exception("Failed reading job file %s", job_file)
            return None

    async def update_job(
        self,
        job_id: str,
        status: str,
        result: Any = None,
        error: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Update job state atomically."""
        job_id = str(job_id)
        job_file = self._job_file(job_id)

        async with self._lock:
            existing = await self.get_job(job_id) or {"job_id": job_id}
            if extra:
                existing.update(extra)
            existing.update({"status": status, "result": result, "error": error})
            try:
                await self._atomic_write_json(job_file, existing)
            except Exception:
                logger.exception("Failed writing job file %s", job_file)


_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """
    Lazy global JobQueue. Uses settings.RET_RUNTIME_ROOT if available.
    """
    global _job_queue
    if _job_queue is not None:
        return _job_queue

    runtime_root = "./runtime"
    try:
        from api.core.config import settings
        runtime_root = getattr(settings, "RET_RUNTIME_ROOT", runtime_root) or runtime_root
    except Exception:
        pass

    _job_queue = JobQueue(runtime_root=runtime_root)
    return _job_queue


# -------------------------------------------------------------------
# Async task result wrapper
# -------------------------------------------------------------------
class AsyncTaskResult:
    """
    Minimal Celery-like async result wrapper backed by asyncio.Task.
    """

    def __init__(self, task: asyncio.Task, task_id: str):
        self._task = task
        self.id = task_id

    async def get(self, timeout: Optional[float] = None) -> Any:
        """Await the task result with optional timeout."""
        if timeout is not None:
            return await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
        return await self._task

    @property
    def status(self) -> str:
        if self._task.cancelled():
            return "CANCELLED"
        if self._task.done():
            exc = self._task.exception()
            return "FAILED" if exc else "SUCCESS"
        return "RUNNING"

    def cancel(self) -> bool:
        """Cancel the underlying asyncio task."""
        return self._task.cancel()

    @property
    def done(self) -> bool:
        return self._task.done()


# -------------------------------------------------------------------
# Background task definition
# -------------------------------------------------------------------
class BackgroundTask:
    """
    A Celery-like task object supporting delay/apply_async.

    The wrapped function can be either sync or async:
    - async def → scheduled directly as asyncio.Task
    - sync def → wrapped in asyncio.to_thread() automatically
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        name: str,
        bind: bool = False,
        manager: "BackgroundTaskManager | None" = None,
    ):
        self.fn = fn
        self.name = name
        self.bind = bind
        self._manager = manager
        self._is_coroutine = asyncio.iscoroutinefunction(fn)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Direct call (for testing or sync contexts)."""
        return self.fn(*args, **kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> AsyncTaskResult:
        """Schedule the task for background execution."""
        return self.apply_async(args=args, kwargs=kwargs)

    def apply_async(
        self,
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        **options: Any,
    ) -> AsyncTaskResult:
        """
        Schedule the task on the event loop's background task manager.
        Must be called from within a running event loop.
        """
        args = args or ()
        kwargs = kwargs or {}
        task_id = str(uuid.uuid4())

        # Optional hook: if job_id present, mirror status to file-based JobQueue
        job_id = kwargs.get("job_id")

        async def _run() -> Any:
            jq: Optional[JobQueue] = None
            if job_id is not None:
                try:
                    jq = get_job_queue()
                    await jq.update_job(str(job_id), status="RUNNING")
                except Exception:
                    jq = None

            logger.info("BackgroundTask start name=%s task_id=%s", self.name, task_id)
            try:
                if self.bind:
                    class _Self:
                        request = type("req", (), {"id": task_id})()

                    if self._is_coroutine:
                        result = await self.fn(_Self(), *args, **kwargs)
                    else:
                        result = await asyncio.to_thread(self.fn, _Self(), *args, **kwargs)
                else:
                    if self._is_coroutine:
                        result = await self.fn(*args, **kwargs)
                    else:
                        result = await asyncio.to_thread(self.fn, *args, **kwargs)

                if jq and job_id is not None:
                    try:
                        await jq.update_job(str(job_id), status="SUCCESS", result=result)
                    except Exception:
                        pass

                logger.info("BackgroundTask completed name=%s task_id=%s", self.name, task_id)
                return result

            except asyncio.CancelledError:
                logger.warning("BackgroundTask cancelled name=%s task_id=%s", self.name, task_id)
                if jq and job_id is not None:
                    try:
                        await jq.update_job(str(job_id), status="CANCELLED")
                    except Exception:
                        pass
                raise

            except Exception as e:
                logger.exception("BackgroundTask failed name=%s task_id=%s", self.name, task_id)
                if jq and job_id is not None:
                    try:
                        await jq.update_job(str(job_id), status="FAILED", error=str(e))
                    except Exception:
                        pass
                raise

        manager = self._manager or _default_manager
        if manager is not None:
            return manager.schedule(task_id, _run())
        else:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_run(), name=f"bg-{self.name}-{task_id[:8]}")
            return AsyncTaskResult(task=task, task_id=task_id)


# -------------------------------------------------------------------
# Background Task Manager (replaces LocalCelery)
# -------------------------------------------------------------------
class _Conf:
    """Dummy conf object for Celery API compat."""
    def update(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class BackgroundTaskManager:
    """
    Production-grade async background task manager.

    - Schedules tasks as asyncio.Tasks
    - Uses asyncio.Semaphore for concurrency control
    - Supports graceful shutdown with cancellation
    - Tracks active tasks for monitoring
    - Celery-compatible decorator API
    """

    conf = _Conf()

    def __init__(self, max_concurrent: int = 8):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._active: Dict[str, asyncio.Task] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._max_concurrent = max_concurrent

    def _ensure_semaphore(self) -> asyncio.Semaphore:
        """Lazy init semaphore (must be created inside event loop)."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    def task(self, *dargs: Any, **dkwargs: Any):
        """
        Decorator mimicking @celery.task(bind=True, name="...").

        Supports:
          - bind (bool): pass a minimal self object as first arg
          - name (str): task name override
          - Ignores base=... for Celery compatibility
        """
        bind = bool(dkwargs.get("bind", False))
        name = dkwargs.get("name")

        def decorator(fn: Callable[..., Any]) -> BackgroundTask:
            task_name = name or fn.__name__
            t = BackgroundTask(fn=fn, name=task_name, bind=bind, manager=self)
            self._tasks[task_name] = t
            return t

        return decorator

    def schedule(self, task_id: str, coro: Coroutine) -> AsyncTaskResult:
        """
        Schedule a coroutine as a managed background task with concurrency control.
        """
        sem = self._ensure_semaphore()

        async def _guarded():
            async with sem:
                return await coro

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "BackgroundTaskManager.schedule() must be called "
                "from within a running event loop"
            )

        asyncio_task = loop.create_task(_guarded(), name=f"bg-task-{task_id[:8]}")
        self._active[task_id] = asyncio_task

        def _on_done(t: asyncio.Task):
            self._active.pop(task_id, None)

        asyncio_task.add_done_callback(_on_done)

        return AsyncTaskResult(task=asyncio_task, task_id=task_id)

    def get_active_tasks(self) -> Dict[str, str]:
        """Return a snapshot of active tasks and their statuses for monitoring."""
        result = {}
        for tid, t in list(self._active.items()):
            if t.cancelled():
                result[tid] = "CANCELLED"
            elif t.done():
                try:
                    exc = t.exception()
                except asyncio.CancelledError:
                    exc = None
                result[tid] = "FAILED" if exc else "SUCCESS"
            else:
                result[tid] = "RUNNING"
        return result

    @property
    def active_count(self) -> int:
        """Number of currently active tasks."""
        return len(self._active)

    async def shutdown(self, timeout: float = 30.0, cancel: bool = True) -> None:
        """
        Gracefully shutdown the task manager.

        Args:
            timeout: Maximum seconds to wait for tasks to complete
            cancel: Whether to cancel remaining tasks after timeout
        """
        active = list(self._active.values())
        if not active:
            logger.info("BackgroundTaskManager: no active tasks, shutdown immediate")
            return

        logger.info(
            "BackgroundTaskManager: shutting down with %d active tasks (timeout=%.1fs)",
            len(active),
            timeout,
        )

        done, pending = await asyncio.wait(active, timeout=timeout)

        if pending and cancel:
            logger.warning(
                "BackgroundTaskManager: cancelling %d tasks that didn't finish in %.1fs",
                len(pending),
                timeout,
            )
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.wait(pending, timeout=5.0)

        self._active.clear()
        logger.info("BackgroundTaskManager: shutdown complete")


# -------------------------------------------------------------------
# Default manager instance
# -------------------------------------------------------------------
def _get_max_workers() -> int:
    """Determine max concurrent tasks from config or environment."""
    try:
        val = int(os.environ.get("RET_LOCAL_WORKERS", "0"))
        if val > 0:
            return val
    except (ValueError, TypeError):
        pass
    try:
        from api.core.config import settings
        return getattr(settings, "TASK_EXECUTOR_MAX_WORKERS", 8)
    except Exception:
        return 8


_default_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """Get the global BackgroundTaskManager singleton."""
    global _default_manager
    if _default_manager is None:
        _default_manager = BackgroundTaskManager(max_concurrent=_get_max_workers())
    return _default_manager


async def shutdown_task_manager(timeout: float = 30.0) -> None:
    """Shutdown the global task manager gracefully."""
    global _default_manager
    if _default_manager is not None:
        await _default_manager.shutdown(timeout=timeout)
        _default_manager = None


# -------------------------------------------------------------------
# Backward-compatible aliases
# -------------------------------------------------------------------
# celery is kept as an alias so existing `from api.workers.celery_app import celery`
# and `@celery.task(...)` work unchanged.
celery = get_task_manager()


async def shutdown_executor(wait: bool = True) -> None:
    """Backward-compatible async shutdown."""
    await shutdown_task_manager(timeout=30.0 if wait else 5.0)


# Legacy sync-compat aliases for any code that imported these names
get_active_tasks = celery.get_active_tasks

