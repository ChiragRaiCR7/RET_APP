from pydantic import BaseModel
from typing import Generic, TypeVar, Optional, List

T = TypeVar("T")

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: str

class HealthCheck(BaseModel):
    status: str
