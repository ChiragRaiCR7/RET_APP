from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"

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
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AuditLogEntry(BaseModel):
    id: int
    username: Optional[str] = None
    action: Optional[str] = None
    area: Optional[str] = None
    message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class OpsLogEntry(BaseModel):
    id: int
    level: Optional[str] = None
    area: Optional[str] = None
    action: Optional[str] = None
    username: Optional[str] = None
    message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PasswordResetRequestEntry(BaseModel):
    id: int
    username: str
    reason: Optional[str] = None
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class SessionInfo(BaseModel):
    session_id: str
    username: str
    created_at: str
    last_activity: str
    size: Optional[str] = None

class AdminStats(BaseModel):
    totalUsers: int
    admins: int
    regular: int
    activeSessions: int

