"""
Embedding Worker — Async Background Embedding Service

Fully async embedding worker using asyncio primitives:
- asyncio.Semaphore for concurrency control
- asyncio.Queue for task dispatch
- asyncio.create_task for background processing
- asyncio.Event for graceful shutdown
- asyncio.Lock for task dict synchronization

CPU-bound / blocking work (RAG embed_groups, file I/O) is
offloaded via asyncio.to_thread() to keep the event loop free.

Only embeds groups configured in admin settings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from api.core.config import settings

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Data Types
# -------------------------------------------------------------------
class TaskStatus(str):
    """Embedding task status constants (str-compatible)."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class EmbeddingTask:
    """Represents a background embedding task."""

    task_id: str
    session_id: str
    user_id: str
    groups: List[str]
    csv_dir: Path
    status: str = TaskStatus.PENDING
    progress: float = 0.0
    files_processed: int = 0
    files_total: int = 0
    docs_embedded: int = 0
    chunks_created: int = 0
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "groups": list(self.groups or []),
            "status": self.status,
            "progress": self.progress,
            "files_processed": self.files_processed,
            "files_total": self.files_total,
            "docs_embedded": self.docs_embedded,
            "chunks_created": self.chunks_created,
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
        }


# Type alias for async/sync callbacks
EmbeddingCallback = Optional[Callable[[EmbeddingTask], Any]]


# -------------------------------------------------------------------
# Async Embedding Worker
# -------------------------------------------------------------------
class EmbeddingWorker:
    """
    Fully-async background worker for embedding operations.

    Features:
    - asyncio.Semaphore-based concurrency control (replaces ThreadPoolExecutor)
    - asyncio.Queue-based task dispatch (replaces threading.Queue)
    - Per-group timeout via asyncio.wait_for
    - Exponential backoff with asyncio.sleep
    - Progress tracking per task
    - Automatic cleanup of completed tasks
    - Only embeds admin-configured groups
    """

    def __init__(
        self,
        max_workers: int | None = None,
        batch_size: int = getattr(settings, "EMBED_BATCH_SIZE", 16),
    ):
        embed_default = getattr(settings, "EMBED_MAX_WORKERS", 2)
        self.max_workers: int = max_workers if max_workers is not None else embed_default
        self.batch_size = batch_size

        self._queue: asyncio.Queue[
            tuple[EmbeddingTask, Any, EmbeddingCallback]
        ] = asyncio.Queue()
        self._tasks: Dict[str, EmbeddingTask] = {}
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(self.max_workers)
        self._consumer_task: Optional[asyncio.Task[None]] = None

        logger.info(
            "EmbeddingWorker initialized (async): max_workers=%d, batch_size=%d",
            self.max_workers,
            self.batch_size,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the async consumer loop as a background task."""
        if self._consumer_task and not self._consumer_task.done():
            logger.warning("Embedding worker already running")
            return

        self._stop_event.clear()
        self._consumer_task = asyncio.get_event_loop().create_task(
            self._consumer_loop(), name="EmbeddingWorker-consumer"
        )
        logger.info("Embedding worker started (async)")

    async def stop(self, wait: bool = True) -> None:
        """Signal and optionally await the consumer loop."""
        self._stop_event.set()
        # Put a sentinel to unblock the queue.get()
        try:
            self._queue.put_nowait(None)  # type: ignore[arg-type]
        except asyncio.QueueFull:
            pass
        if wait and self._consumer_task and not self._consumer_task.done():
            try:
                await asyncio.wait_for(self._consumer_task, timeout=15.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._consumer_task.cancel()
        logger.info("Embedding worker stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def submit_task(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        groups: List[str],
        csv_dir: Path,
        rag_service: Any,
        admin_config: Optional[Dict[str, Any]] = None,
        enforce_admin_filter: bool = True,
        callback: EmbeddingCallback = None,
    ) -> EmbeddingTask:
        """Submit an embedding task to the async queue."""
        # Ensure consumer is running
        if self._consumer_task is None or self._consumer_task.done():
            self.start()

        # Filter groups to only admin-configured ones
        filtered_groups = list(groups)
        if enforce_admin_filter:
            admin_config = admin_config or {}
            configured_groups = admin_config.get("auto_embedded_groups", [])
            configured_groups = [str(g).strip().upper() for g in configured_groups if g]
            filtered_groups = [g for g in groups if g.upper() in configured_groups]

            if not filtered_groups:
                logger.warning(
                    "No eligible groups for task %s. Requested: %s, Configured: %s",
                    task_id, groups, configured_groups,
                )
                task = EmbeddingTask(
                    task_id=task_id,
                    session_id=session_id,
                    user_id=user_id,
                    groups=groups,
                    csv_dir=csv_dir,
                    status=TaskStatus.FAILED,
                    error="No eligible groups (check admin config)",
                )
                async with self._lock:
                    self._tasks[task_id] = task
                return task

        task = EmbeddingTask(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            groups=filtered_groups,
            csv_dir=csv_dir,
        )

        async with self._lock:
            self._tasks[task_id] = task

        await self._queue.put((task, rag_service, callback))

        logger.info(
            "Submitted embedding task %s for session %s: groups=%s",
            task_id, session_id, filtered_groups,
        )
        return task

    async def get_task(self, task_id: str) -> Optional[EmbeddingTask]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def get_session_tasks(self, session_id: str) -> List[EmbeddingTask]:
        async with self._lock:
            return [t for t in self._tasks.values() if t.session_id == session_id]

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.error = "Cancelled by user"
                task.completed_at = time.time()
                return True
        return False

    async def cleanup_old_tasks(self, max_age_seconds: float = 3600) -> None:
        async with self._lock:
            now = time.time()
            to_remove = [
                tid for tid, t in self._tasks.items()
                if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                and (now - t.created_at) > max_age_seconds
            ]
            for tid in to_remove:
                del self._tasks[tid]
            if to_remove:
                logger.info("Cleaned up %d old embedding tasks", len(to_remove))

    # ------------------------------------------------------------------
    # Consumer loop (runs as asyncio.Task)
    # ------------------------------------------------------------------
    async def _consumer_loop(self) -> None:
        """Pull items from the queue and dispatch them."""
        cleanup_counter = 0
        while not self._stop_event.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                cleanup_counter += 1
                if cleanup_counter >= 60:
                    await self.cleanup_old_tasks()
                    cleanup_counter = 0
                continue

            if item is None:
                # Sentinel → shutdown
                break

            task, rag_service, callback = item
            # Fire-and-forget but track for shutdown
            asyncio.get_event_loop().create_task(
                self._process_task(task, rag_service, callback),
                name=f"embed-{task.task_id}",
            )

    # ------------------------------------------------------------------
    # Process a single task
    # ------------------------------------------------------------------
    async def _process_task(
        self,
        task: EmbeddingTask,
        rag_service: Any,
        callback: EmbeddingCallback,
    ) -> None:
        try:
            async with self._lock:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()

            await self._invoke_callback(callback, task)

            logger.info("Processing embedding task %s: groups=%s", task.task_id, task.groups)

            # --- collect CSV files per group (blocking I/O in thread) ---
            group_files, conversion_index = await asyncio.to_thread(
                self._collect_group_files, task
            )

            total_files = sum(len(f) for f in group_files.values())
            task.files_total = total_files

            if total_files == 0:
                available = await asyncio.to_thread(
                    lambda: [p.name for p in task.csv_dir.glob("*.csv")][:10]
                )
                raise ValueError(
                    f"No CSV files found matching groups. "
                    f"Requested groups={task.groups}, available_files={available}"
                )

            # --- pre-compute size-aware timeouts ---
            group_timeouts, group_sizes_mb = await asyncio.to_thread(
                self._compute_timeouts, task, group_files
            )

            # --- embed groups concurrently (semaphore-limited) ---
            had_error = False
            embed_coros = []
            for group in task.groups:
                if self._stop_event.is_set() or task.status == TaskStatus.CANCELLED:
                    break

                num_files = len(group_files.get(group, []))
                timeout = group_timeouts.get(group, 300)
                logger.info(
                    "Submitting embed job group=%s (files=%d, size=%.1fMB, timeout=%ds) task=%s",
                    group, num_files, group_sizes_mb.get(group, 0.0), timeout, task.task_id,
                )
                embed_coros.append(
                    self._embed_group_guarded(task, group, rag_service, conversion_index, callback, timeout)
                )

            results = await asyncio.gather(*embed_coros, return_exceptions=True)

            for group, res in zip(task.groups, results):
                if isinstance(res, BaseException):
                    had_error = True
                    err_msg = f"Group {group} error: {res}"
                    logger.error("Embed group %s failed: %s", group, res, exc_info=res)
                    async with self._lock:
                        prev = task.error or ""
                        task.error = (prev + " " + err_msg).strip()
                else:
                    logger.info("Group %s embedded: %s", group, res)

            # Finalize
            async with self._lock:
                if had_error:
                    task.status = TaskStatus.FAILED
                elif task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100.0
                task.completed_at = time.time()

            await self._invoke_callback(callback, task)

            logger.info(
                "Embedding task %s completed: %d docs, %d chunks in %.1fs",
                task.task_id, task.docs_embedded, task.chunks_created, task.elapsed_seconds,
            )

        except Exception as e:
            logger.error("Embedding task %s failed: %s", task.task_id, e, exc_info=True)
            async with self._lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = time.time()
            await self._invoke_callback(callback, task)

    # ------------------------------------------------------------------
    # Embed one group (semaphore-guarded, with timeout)
    # ------------------------------------------------------------------
    async def _embed_group_guarded(
        self,
        task: EmbeddingTask,
        group: str,
        rag_service: Any,
        conversion_index: Optional[Dict[str, Any]],
        callback: EmbeddingCallback,
        timeout: int,
    ) -> Dict[str, Any]:
        """Acquire semaphore, run with per-group timeout."""
        async with self._semaphore:
            return await asyncio.wait_for(
                self._embed_group(task, group, rag_service, conversion_index, callback),
                timeout=timeout,
            )

    async def _embed_group(
        self,
        task: EmbeddingTask,
        group: str,
        rag_service: Any,
        conversion_index: Optional[Dict[str, Any]],
        callback: EmbeddingCallback,
    ) -> Dict[str, Any]:
        """Embed a single group with retry + exponential backoff."""
        logger.info("Embedding group: %s (task %s)", group, task.task_id)
        max_retries = getattr(settings, "EMBED_GROUP_MAX_RETRIES", 2)
        backoff = getattr(settings, "EMBED_GROUP_BACKOFF_SECONDS", 1.5)
        last_exc: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                # CPU-bound / blocking RAG call → offload to thread
                result = await asyncio.to_thread(
                    rag_service.embed_groups,
                    groups=[group],
                    csv_dir=task.csv_dir,
                    conversion_index=conversion_index,
                )
                break
            except Exception as e:
                last_exc = e
                if attempt >= max_retries:
                    raise
                delay = backoff * (2 ** attempt)
                logger.warning(
                    "Embed group %s failed (attempt %d/%d): %s — retrying in %.1fs",
                    group, attempt + 1, max_retries + 1, e, delay,
                )
                await asyncio.sleep(delay)
        else:
            raise last_exc  # type: ignore[misc]

        # Update progress
        async with self._lock:
            task.files_processed += result.indexed_files
            task.docs_embedded += result.indexed_docs
            task.chunks_created += result.indexed_chunks
            if task.files_total > 0:
                task.progress = (task.files_processed / task.files_total) * 100.0

        await self._invoke_callback(callback, task)

        return {
            "group": group,
            "files": result.indexed_files,
            "docs": result.indexed_docs,
            "chunks": result.indexed_chunks,
        }

    # ------------------------------------------------------------------
    # Helpers (sync, run in thread via to_thread)
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_group_files(
        task: EmbeddingTask,
    ) -> tuple[Dict[str, List[Path]], Optional[Dict[str, Any]]]:
        """Collect CSV files per group (blocking I/O — called via to_thread)."""
        group_files: Dict[str, List[Path]] = {g: [] for g in task.groups}
        conversion_index: Optional[Dict[str, Any]] = None

        try:
            session_dir = task.csv_dir.parent
            index_path = session_dir / "conversion_index.json"
            if index_path.exists():
                conversion_index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to read conversion_index.json: %s", e)

        requested_upper = {g.upper(): g for g in task.groups}

        if conversion_index and isinstance(conversion_index, dict):
            files_list = conversion_index.get("files", [])
            if isinstance(files_list, list):
                for info in files_list:
                    if not isinstance(info, dict):
                        continue
                    group = str(info.get("group", "MISC")).upper()
                    if group not in requested_upper:
                        continue
                    filename = info.get("filename")
                    if not filename:
                        continue
                    csv_path = (
                        Path(info["csv_path"]) if info.get("csv_path")
                        else (task.csv_dir / filename)
                    )
                    if csv_path.exists():
                        group_files[requested_upper[group]].append(csv_path)

        # Fallback: match CSV filenames by group prefix
        if not any(group_files.values()):
            for csv_path in task.csv_dir.glob("*.csv"):
                fname = csv_path.stem.upper()
                for g_upper, g_original in requested_upper.items():
                    if fname.startswith(g_upper + "_") or fname == g_upper:
                        group_files[g_original].append(csv_path)
                        break

        return group_files, conversion_index

    @staticmethod
    def _compute_timeouts(
        task: EmbeddingTask,
        group_files: Dict[str, List[Path]],
    ) -> tuple[Dict[str, int], Dict[str, float]]:
        """Compute per-group timeouts based on file sizes (blocking — called via to_thread)."""
        base_timeout = getattr(settings, "EMBED_GROUP_TIMEOUT", 300)
        per_mb_timeout = float(getattr(settings, "EMBED_GROUP_TIMEOUT_PER_MB", 0.0) or 0.0)
        group_timeouts: Dict[str, int] = {}
        group_sizes_mb: Dict[str, float] = {}

        for group in task.groups:
            total_bytes = 0
            for p in group_files.get(group, []):
                try:
                    total_bytes += int(p.stat().st_size)
                except Exception:
                    pass
            size_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
            group_sizes_mb[group] = size_mb
            timeout = max(int(base_timeout), int(base_timeout + per_mb_timeout * size_mb))
            group_timeouts[group] = timeout

        return group_timeouts, group_sizes_mb

    @staticmethod
    async def _invoke_callback(callback: EmbeddingCallback, task: EmbeddingTask) -> None:
        """Safely invoke callback (supports both sync and async callbacks)."""
        if callback is None:
            return
        try:
            result = callback(task)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result
        except Exception:
            logger.debug("Embedding callback error", exc_info=True)


# -------------------------------------------------------------------
# Global worker singleton (async-safe)
# -------------------------------------------------------------------
_worker: Optional[EmbeddingWorker] = None
_worker_lock = asyncio.Lock()


async def get_embedding_worker() -> EmbeddingWorker:
    """Get or create the global async embedding worker."""
    global _worker
    async with _worker_lock:
        if _worker is None:
            _worker = EmbeddingWorker()
            logger.info("Embedding worker created (will start on first task)")
        return _worker


async def stop_embedding_worker() -> None:
    """Stop the global embedding worker."""
    global _worker
    async with _worker_lock:
        if _worker:
            await _worker.stop()
            _worker = None
