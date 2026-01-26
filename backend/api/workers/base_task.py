try:
    from celery import Task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Task = object

from sqlalchemy.orm import Session
from api.core.database import SessionLocal
from api.models.job import Job

if CELERY_AVAILABLE:
    class JobTask(Task):
        abstract = True

        def before_start(self, task_id, args, kwargs):
            db: Session = SessionLocal()
            job = db.query(Job).get(kwargs["job_id"])
            job.status = "RUNNING"
            db.commit()
            db.close()

        def on_success(self, retval, task_id, args, kwargs):
            db = SessionLocal()
            job = db.query(Job).get(kwargs["job_id"])
            job.status = "SUCCESS"
            job.progress = 100
            job.result = retval
            db.commit()
            db.close()

        def on_failure(self, exc, task_id, args, kwargs, einfo):
            db = SessionLocal()
            job = db.query(Job).get(kwargs["job_id"])
            job.status = "FAILED"
            job.error = str(exc)
            db.commit()
            db.close()
else:
    # Mock JobTask for development without Celery
    class JobTask:
        abstract = True
