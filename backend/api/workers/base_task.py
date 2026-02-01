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
    class JobTaskBase(Task):
        abstract = True

        def before_start(self, task_id, args, kwargs):
            db: Session = SessionLocal()
            try:
                job = db.query(Job).get(kwargs.get("job_id"))
                if job:
                    job.status = "RUNNING"
                    db.commit()
            finally:
                db.close()

        def on_success(self, retval, task_id, args, kwargs):
            db = SessionLocal()
            try:
                job = db.query(Job).get(kwargs.get("job_id"))
                if job:
                    job.status = "SUCCESS"
                    job.progress = 100
                    job.result = retval
                    db.commit()
            finally:
                db.close()

        def on_failure(self, exc, task_id, args, kwargs, einfo):
            db = SessionLocal()
            try:
                job = db.query(Job).get(kwargs.get("job_id"))
                if job:
                    job.status = "FAILED"
                    job.error = str(exc)
                    db.commit()
            finally:
                db.close()
else:
    # Mock JobTaskBase for development without Celery
    class JobTaskBase:
        abstract = True
