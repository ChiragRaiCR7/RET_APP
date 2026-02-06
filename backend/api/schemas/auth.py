from pydantic import BaseModel, Field, field_validator
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

class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    is_locked: bool
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        if hasattr(v, 'value'):
            return v.value.lower()
        return str(v).lower() if v else v

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    """Token response - refresh_token is delivered via HttpOnly cookie, not in body."""
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
    # Note: refresh_token is set as HttpOnly cookie, not returned in response body

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
