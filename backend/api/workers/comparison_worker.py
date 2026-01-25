from api.workers.celery_app import celery
from api.workers.base_task import JobTask
from api.services.comparison_service import compare_sessions

@celery.task(bind=True, base=JobTask)
def comparison_task(self, left_session_id: str, right_session_id: str, job_id: int):
    return compare_sessions(left_session_id, right_session_id)
