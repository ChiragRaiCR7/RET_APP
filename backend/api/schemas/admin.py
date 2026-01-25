from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_locked: Optional[bool] = None

class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    is_locked: bool
    created_at: datetime

class AuditLogEntry(BaseModel):
    username: Optional[str]
    action: str
    area: str
    message: str
    created_at: datetime
