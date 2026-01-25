from pydantic import BaseModel
from typing import List, Dict, Optional

class IndexRequest(BaseModel):
    session_id: str
    collection: str

class IndexResponse(BaseModel):
    collection: str
    indexed_chunks: int

class ChatRequest(BaseModel):
    collection: str
    question: str

class RetrievalChunk(BaseModel):
    content: str
    metadata: Dict
    score: float

class ChatResponse(BaseModel):
    answer: str
    citations: List[RetrievalChunk]
