from fastapi import APIRouter
from api.schemas.ai import (
    IndexRequest,
    IndexResponse,
    ChatRequest,
    ChatResponse,
)
from api.services.ai_service import index_session, chat_with_collection
from api.services.job_service import create_job
from api.workers.indexing_worker import indexing_task


router = APIRouter(prefix="/api/ai", tags=["ai"])

@router.post("/index")
def index_async(req: IndexRequest, db: Session = Depends(get_db)):
    job = create_job(db, "indexing")
    indexing_task.delay(req.session_id, req.collection, job.id)
    return {"job_id": job.id}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return chat_with_collection(req.collection, req.question)
