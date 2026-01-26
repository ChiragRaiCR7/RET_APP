from typing import Optional, List
from api.workers.celery_app import celery
from api.workers.base_task import JobTask
from api.services.conversion_service import convert_session

@celery.task(bind=True, base=JobTask)
def conversion_task(self, session_id: str, job_id: int, groups: Optional[List[str]] = None):
    return convert_session(session_id, groups)

