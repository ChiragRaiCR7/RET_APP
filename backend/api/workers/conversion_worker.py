# conversion_worker.py
"""
Simple worker wrapper to run conversion as a (Celery) task.
This imports a celery-compatible `celery` object from celery_app above.
When celery is not installed, the mock will run tasks synchronously.
"""
from typing import Optional, List
from api.workers.celery_app import celery
from api.services.conversion_service import convert_session

@celery.task(bind=True)
def conversion_task(self, session_id: str, job_id: str, groups: Optional[List[str]] = None):
    """
    Execute a conversion job for the given session_id.
    Returns conversion result (dict) from convert_session.
    """
    return convert_session(session_id, groups)
