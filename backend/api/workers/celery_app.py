"""
Task Queue Module
Provides synchronous task execution with session storage
Replaces Redis Celery with in-process job queue
Inspired by Streamlit's session-based background task pattern
"""

try:
    from celery import Celery, Task as CeleryTask
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Celery = None
    CeleryTask = None

import logging
from typing import Optional, Any, Callable
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class JobQueue:
    """
    In-process job queue using SQLite backend
    Stores job status for tracking in sessions
    """
    
    def __init__(self, runtime_root: str = "./runtime"):
        self.runtime_root = Path(runtime_root)
        self.jobs_dir = self.runtime_root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
    
    def create_job(self, session_id: str, job_id: str, task_name: str) -> dict:
        """Create a new job record"""
        job = {
            "job_id": job_id,
            "session_id": session_id,
            "task_name": task_name,
            "status": "pending",
            "result": None,
            "error": None,
        }
        return job
    
    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job status"""
        job_file = self.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            with open(job_file, "r") as f:
                return json.load(f)
        return None
    
    def update_job(self, job_id: str, status: str, result: Any = None, error: str = None):
        """Update job status"""
        job_file = self.jobs_dir / f"{job_id}.json"
        job = self.get_job(job_id) or {"job_id": job_id}
        
        job.update({
            "status": status,
            "result": result,
            "error": error,
        })
        
        with open(job_file, "w") as f:
            json.dump(job, f)


# Global job queue instance
_job_queue = None


def get_job_queue() -> JobQueue:
    """Get or create global job queue"""
    global _job_queue
    if _job_queue is None:
        from api.core.config import settings
        _job_queue = JobQueue(runtime_root=settings.RET_RUNTIME_ROOT)
    return _job_queue


# Celery app setup
if CELERY_AVAILABLE and Celery:
    from api.core.config import settings
    
    celery = Celery(
        "retv4",
        # Use memory-based task broker (tasks run synchronously)
        broker="memory://",
        backend="cache+memory://",
    )
    
    celery.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_time_limit=60 * 60,  # 1 hour
        task_always_eager=True,  # Execute tasks synchronously
        task_eager_propagates=True,  # Propagate exceptions
    )
else:
    # Fallback mock Celery for development
    class MockTask:
        def __init__(self, func: Callable):
            self.func = func
        
        def __call__(self, *args, **kwargs):
            return self.func(*args, **kwargs)
        
        def apply_async(self, args=None, kwargs=None, **options):
            """Mock apply_async - execute immediately"""
            args = args or ()
            kwargs = kwargs or {}
            try:
                result = self.func(*args, **kwargs)
                return MockAsyncResult(result, status="success")
            except Exception as e:
                logger.error(f"Task error: {e}")
                return MockAsyncResult(None, status="failure", error=str(e))
    
    class MockAsyncResult:
        def __init__(self, result=None, status="pending", error=None):
            self.result = result
            self.status = status
            self.error = error
            self.id = None
        
        def get(self, timeout=None):
            if self.status == "failure":
                raise Exception(self.error)
            return self.result
    
    class MockCelery:
        """Mock Celery for when celery is not installed"""
        
        def task(self, *args, **kwargs):
            def decorator(func):
                return MockTask(func)
            return decorator
        
        conf = type('obj', (object,), {'update': lambda x: None})()
    
    celery = MockCelery()

