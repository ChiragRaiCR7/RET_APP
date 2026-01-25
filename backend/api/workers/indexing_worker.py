from api.workers.celery_app import celery
from api.workers.base_task import JobTask
from api.services.ai_service import index_session

@celery.task(bind=True, base=JobTask)
def indexing_task(self, session_id: str, collection: str, job_id: int):
    return {"indexed_chunks": index_session(session_id, collection)}
