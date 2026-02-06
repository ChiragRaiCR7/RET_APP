from pydantic import BaseModel
from typing import Generic, TypeVar, Optional, List

T = TypeVar("T")

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None

class MessageResponse(BaseModel):
    """Simple success/message response for endpoints that don't return data."""
    success: bool = True
    message: str = ""

class JobCreatedResponse(BaseModel):
    """Response for async job creation."""
    job_id: int

class ErrorResponse(BaseModel):
    success: bool = False
    error: str

class HealthCheck(BaseModel):
    status: str
