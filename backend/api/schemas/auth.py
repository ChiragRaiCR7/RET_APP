

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# -------- Requests --------

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    """
    Backward-compatible request model.
    Refresh is cookie-based; body token is not required by current backend.
    """
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
        if hasattr(v, "value"):
            return v.value.lower()
        return str(v).lower() if v else v

    # Pydantic v2-friendly (keeps behavior similar to Config.from_attributes)
    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Token response - refresh_token is delivered via HttpOnly cookie, not in body."""
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

