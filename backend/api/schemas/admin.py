from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserCreateRequest(BaseModel):
    """Request to create a new user via token-first onboarding"""
    username: str
    password: Optional[str] = None  # Optional for token-first onboarding
    role: Optional[str] = "user"
    tokenTTL: Optional[int] = 60  # Token validity in minutes
    note: Optional[str] = None

class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_locked: Optional[bool] = None

class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool = True
    is_locked: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    token: Optional[str] = None  # Reset token for newly created users

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


class AgentRequest(BaseModel):
    command: str


class AgentResponse(BaseModel):
    result: str
    details: Optional[dict] = None

