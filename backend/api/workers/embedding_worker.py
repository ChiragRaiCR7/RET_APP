"""
Embedding Worker — Fast Background Embedding Service

Handles background embedding tasks with:
- Thread pool for parallel processing
- Batch processing for efficiency
- Progress tracking
- Semantic chunking with optimal strategies  
- Semantic reranking for better retrieval
- Queue-based task management

Only embeds groups configured in admin settings.
"""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from api.core.config import settings

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Embedding task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class EmbeddingTask:
    """Represents a background embedding task"""
    task_id: str
    session_id: str
    user_id: str
    groups: List[str]
    csv_dir: Path
    status: TaskStatus = TaskStatus.PENDING
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
        """Calculate elapsed time"""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "groups": list(self.groups or []),
            "status": self.status.value,
            "progress": self.progress,
            "files_processed": self.files_processed,
            "files_total": self.files_total,
            "docs_embedded": self.docs_embedded,
            "chunks_created": self.chunks_created,
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
        }


class EmbeddingWorker:
    """
    Background worker for fast embedding operations.
    
    Features:
    - Thread pool for parallel file processing
    - Batch embedding for efficiency
    - Progress tracking per task
    - Automatic cleanup of completed tasks
    - Only embeds admin-configured groups
    """
    
    def __init__(
        self,
        max_workers: int = None,
        batch_size: int = getattr(settings, "EMBED_BATCH_SIZE", 16),
    ):
        """
        Initialize embedding worker.
        
        Args:
            max_workers: Maximum parallel workers (default: CPU count * 2)
            batch_size: Batch size for embedding operations
        """
        cpu_count = os.cpu_count() or 4
        default_workers = getattr(settings, "CONVERSION_DEFAULT_WORKERS", cpu_count * 2)
        self.max_workers = max_workers or default_workers
        self.batch_size = batch_size
        
        self._task_queue: Queue = Queue()
        self._tasks: Dict[str, EmbeddingTask] = {}
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        
        logger.info(
            f"EmbeddingWorker initialized: {self.max_workers} workers, "
            f"batch size {self.batch_size}"
        )
    
    def start(self):
        """Start the worker thread"""
        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("Embedding worker already running")
            return
        
        self._stop_flag.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="EmbeddingWorker"
        )
        self._worker_thread.start()
        logger.info("Embedding worker started")
    
    def stop(self, wait: bool = True):
        """Stop the worker thread"""
        self._stop_flag.set()
        
        if self._executor:
            self._executor.shutdown(wait=wait)
        
        if wait and self._worker_thread:
            self._worker_thread.join(timeout=10.0)
        
        logger.info("Embedding worker stopped")
    
    def submit_task(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        groups: List[str],
        csv_dir: Path,
        rag_service: Any,
        admin_config: Optional[Dict[str, Any]] = None,
        enforce_admin_filter: bool = True,
        callback: Optional[Callable[[EmbeddingTask], None]] = None,
    ) -> EmbeddingTask:
        """
        Submit an embedding task to the queue.
        
        Args:
            task_id: Unique task identifier
            session_id: Session ID
            user_id: User ID
            groups: Groups to embed
            csv_dir: Directory containing CSV files
            rag_service: UnifiedRAGService instance
            admin_config: Admin configuration dict
            callback: Optional callback for progress updates
            
        Returns:
            EmbeddingTask object
        """
        # Ensure worker is started before submitting task
        if not self._worker_thread or not self._worker_thread.is_alive():
            logger.info("Starting embedding worker for new task submission")
            self.start()
        
        # Filter groups to only admin-configured ones when enforced
        filtered_groups = list(groups)
        if enforce_admin_filter:
            admin_config = admin_config or {}
            configured_groups = admin_config.get("auto_embedded_groups", [])
            configured_groups = [str(g).strip().upper() for g in configured_groups if g]

            filtered_groups = [
                g for g in groups
                if g.upper() in configured_groups
            ]

            if not filtered_groups:
                logger.warning(
                    f"No eligible groups for task {task_id}. "
                    f"Requested: {groups}, Configured: {configured_groups}"
                )
                # Create a failed task
                task = EmbeddingTask(
                    task_id=task_id,
                    session_id=session_id,
                    user_id=user_id,
                    groups=groups,
                    csv_dir=csv_dir,
                    status=TaskStatus.FAILED,
                    error="No eligible groups (check admin config)",
                )
                with self._lock:
                    self._tasks[task_id] = task
                return task
        
        task = EmbeddingTask(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            groups=filtered_groups,
            csv_dir=csv_dir,
        )
        
        with self._lock:
            self._tasks[task_id] = task
        
        # Add to queue
        self._task_queue.put((task, rag_service, callback))
        
        logger.info(
            f"Submitted embedding task {task_id} for session {session_id}: "
            f"groups={filtered_groups}"
        )
        
        return task
    
    def get_task(self, task_id: str) -> Optional[EmbeddingTask]:
        """Get task status by ID"""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_session_tasks(self, session_id: str) -> List[EmbeddingTask]:
        """Get all tasks for a session"""
        with self._lock:
            return [
                task for task in self._tasks.values()
                if task.session_id == session_id
            ]
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or running task"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.error = "Cancelled by user"
                task.completed_at = time.time()
                return True
        return False
    
    def cleanup_old_tasks(self, max_age_seconds: float = 3600):
        """Remove completed tasks older than max_age_seconds"""
        with self._lock:
            now = time.time()
            to_remove = [
                task_id for task_id, task in self._tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                and (now - task.created_at) > max_age_seconds
            ]
            for task_id in to_remove:
                del self._tasks[task_id]
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old embedding tasks")
    
    def _worker_loop(self):
        """Main worker loop that processes tasks from the queue"""
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="EmbedWorker"
        )
        
        cleanup_counter = 0
        while not self._stop_flag.is_set():
            try:
                # Get task from queue (with longer timeout to reduce CPU usage)
                task, rag_service, callback = self._task_queue.get(timeout=5.0)
                
                # Process task
                self._process_task(task, rag_service, callback)
                
                self._task_queue.task_done()
                
            except Empty:
                # No tasks in queue - only cleanup periodically (every 60 iterations = ~5 minutes)
                cleanup_counter += 1
                if cleanup_counter >= 60:
                    self.cleanup_old_tasks()
                    cleanup_counter = 0
                continue
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
    
    def _process_task(
        self,
        task: EmbeddingTask,
        rag_service: Any,
        callback: Optional[Callable[[EmbeddingTask], None]],
    ):
        """Process a single embedding task"""
        try:
            # Update task status
            with self._lock:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
            
            if callback:
                callback(task)
            
            logger.info(f"Processing embedding task {task.task_id}: groups={task.groups}")
            
            # Collect CSV files for each group
            group_files: Dict[str, List[Path]] = {g: [] for g in task.groups}
            conversion_index: Optional[Dict[str, Any]] = None

            # Try conversion_index.json first for accurate group mapping
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
                        csv_path = Path(info.get("csv_path", "")) if info.get("csv_path") else (task.csv_dir / filename)
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
            
            # Calculate total files
            total_files = sum(len(files) for files in group_files.values())
            task.files_total = total_files
            
            if total_files == 0:
                available = [p.name for p in task.csv_dir.glob("*.csv")]
                raise ValueError(
                    "No CSV files found matching groups. "
                    f"Requested groups={task.groups}, "
                    f"available_files={available[:10]}"
                )
            
            # Use thread pool to embed groups in parallel
            futures = []
            for group in task.groups:
                if self._stop_flag.is_set() or task.status == TaskStatus.CANCELLED:
                    break
                
                future = self._executor.submit(
                    self._embed_group,
                    task,
                    group,
                    rag_service,
                    conversion_index,
                    callback,
                )
                futures.append((group, future))
            
            # Wait for all groups to complete
            for group, future in futures:
                try:
                    result = future.result(timeout=300)  # 5 min timeout per group
                    logger.info(f"Group {group} embedded: {result}")
                except Exception as e:
                    logger.error(f"Failed to embed group {group}: {e}")
            
            # Mark as completed
            with self._lock:
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100.0
                task.completed_at = time.time()
            
            if callback:
                callback(task)
            
            logger.info(
                f"Embedding task {task.task_id} completed: "
                f"{task.docs_embedded} docs, {task.chunks_created} chunks "
                f"in {task.elapsed_seconds:.1f}s"
            )
        
        except Exception as e:
            logger.error(f"Embedding task {task.task_id} failed: {e}", exc_info=True)
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = time.time()
            
            if callback:
                callback(task)
    
    def _embed_group(
        self,
        task: EmbeddingTask,
        group: str,
        rag_service: Any,
        conversion_index: Optional[Dict[str, Any]],
        callback: Optional[Callable[[EmbeddingTask], None]],
    ) -> Dict[str, Any]:
        """Embed a single group (called in thread pool)"""
        try:
            logger.info(f"Embedding group: {group} (task {task.task_id})")
            max_retries = getattr(settings, "EMBED_GROUP_MAX_RETRIES", 2)
            backoff = getattr(settings, "EMBED_GROUP_BACKOFF_SECONDS", 1.5)
            last_exc: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    # Call RAG service to embed this group (resume-aware)
                    result = rag_service.embed_groups(
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
                        group,
                        attempt + 1,
                        max_retries + 1,
                        e,
                        delay,
                    )
                    time.sleep(delay)
            else:
                raise last_exc  # type: ignore[misc]
            
            # Update task progress
            with self._lock:
                task.files_processed += result.indexed_files
                task.docs_embedded += result.indexed_docs
                task.chunks_created += result.indexed_chunks
                
                # Calculate progress
                if task.files_total > 0:
                    task.progress = (task.files_processed / task.files_total) * 100.0
            
            if callback:
                callback(task)
            
            return {
                "group": group,
                "files": result.indexed_files,
                "docs": result.indexed_docs,
                "chunks": result.indexed_chunks,
            }
        
        except Exception as e:
            logger.error(f"Failed to embed group {group}: {e}", exc_info=True)
            raise


# Global worker instance
_worker: Optional[EmbeddingWorker] = None
_worker_lock = threading.Lock()


def get_embedding_worker() -> EmbeddingWorker:
    """Get or create the global embedding worker"""
    global _worker
    
    with _worker_lock:
        if _worker is None:
            _worker = EmbeddingWorker()
            # Start worker lazily only when first task is submitted
            logger.info("Embedding worker created (will start on first task)")
        return _worker


def stop_embedding_worker():
    """Stop the global embedding worker"""
    global _worker
    
    with _worker_lock:
        if _worker:
            _worker.stop()
            _worker = None
