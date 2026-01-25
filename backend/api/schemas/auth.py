from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# -------- Requests --------

class LoginRequest(BaseModel):
    username: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class PasswordResetRequest(BaseModel):
    username: str
    reason: Optional[str] = None

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

# -------- Responses --------

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserInfo"

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    is_locked: bool
    created_at: datetime

    class Config:
        from_attributes = True
