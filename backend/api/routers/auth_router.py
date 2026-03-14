

"""
Authentication Router — /api/v1/auth

Handles user authentication lifecycle:
  - Login with username/password (issues JWT access + HttpOnly refresh tokens)
  - Token refresh via HttpOnly cookie
  - Logout with full session/AI/cache cleanup
  - Password reset request and confirmation
  - Current user info retrieval

Final async rewrite:
- Uses AsyncSession from get_db()
- Endpoints are async def
- Cookie path uses settings.API_PREFIX (fixes /api vs /api/v1 drift)
- max_age uses seconds (not days)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.core.session_cache import clear_cache_pattern
from api.models.models import User
from api.schemas.auth import (
    LoginRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    TokenResponse,
    RefreshTokenResponse,
    UserInfo,
)
from api.schemas.common import MessageResponse
from api.services.auth_service import (
    authenticate_user,
    issue_tokens,
    refresh_tokens,
    request_password_reset,
    confirm_password_reset,
)
from api.services.session_service import revoke_refresh_token
from api.services.admin_service import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _refresh_cookie_name() -> str:
    return getattr(settings, "REFRESH_COOKIE_NAME", "refresh_token")


def _refresh_cookie_path() -> str:
    # ✅ Fix prefix mismatch: /api/v1/auth/refresh (not /api/auth/refresh)
    return f"{settings.API_PREFIX}/auth/refresh"


def _cookie_secure() -> bool:
    # Prefer explicit cookie setting if present, else fall back to is_production
    return bool(getattr(settings, "COOKIE_SECURE", settings.is_production))


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    value = str(getattr(settings, "COOKIE_SAMESITE", "lax") or "lax").lower()
    if value in ("lax", "strict", "none"):
        return value  # type: ignore
    return "lax"


def _cookie_domain():
    return getattr(settings, "COOKIE_DOMAIN", None)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and issue JWT access token + HttpOnly refresh cookie.

    Returns:
        TokenResponse with access_token + user info.
        Refresh token is set as HttpOnly cookie, not returned in body.
    """
    user = await authenticate_user(db, req.username, req.password)
    tokens = await issue_tokens(db, user, request)

    # Audit: successful login
    write_audit_log(db, user.username, "LOGIN", "AUTH", f"Login from {request.client.host if request.client else 'unknown'}")

    # ✅ Set refresh token cookie with proper attributes
    response.set_cookie(
        key=_refresh_cookie_name(),
        value=tokens["refresh_token"],
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path=_refresh_cookie_path(),
        domain=_cookie_domain(),
        # ✅ max_age must be seconds
        max_age=int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        token_type=tokens["token_type"],
        user=tokens["user"],
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Logout endpoint with comprehensive cleanup.

    Cleans up:
    - Database refresh session records (best effort)
    - Session directories (XML, CSV, extracted files)
    - ChromaDB vector indices (Advanced RAG)
    - AI session managers
    - Cache entries
    """
    from api.services.storage_service import cleanup_user_sessions, get_user_sessions
    from api.services.ai.session_manager import cleanup_session_ai

    user_id = str(current_user.id)
    logger.info("User logout initiated: %s (id=%s)", current_user.username, user_id)

    # Revoke refresh token in DB (best effort)
    try:
        refresh_token = request.cookies.get(_refresh_cookie_name())
        if refresh_token:
            await revoke_refresh_token(db, refresh_token)
            logger.debug("Revoked refresh token for user: %s", user_id)
    except Exception as e:
        logger.error("Failed to revoke refresh token: %s", e)

    # AI cleanup
    try:
        user_sessions = get_user_sessions(user_id)
        for session_info in user_sessions:
            session_id = session_info.get("session_id", "")
            if session_id:
                try:
                    cleanup_session_ai(session_id, user_id)
                    logger.debug("Cleaned up AI resources for session: %s", session_id)
                except Exception as e:
                    logger.warning("Failed to cleanup AI for session %s: %s", session_id, e)
        logger.info("Cleaned up AI sessions for user: %s", user_id)
    except Exception as e:
        logger.error("Failed to cleanup AI sessions: %s", e)

    # Storage cleanup
    try:
        await cleanup_user_sessions(user_id)
        logger.info("Cleaned up all sessions for user: %s", user_id)
    except Exception as e:
        logger.error("Failed to cleanup sessions: %s", e)

    # Cache cleanup
    try:
        cleared = await clear_cache_pattern(f"user:{user_id}:")
        logger.debug("Cleared %s cache entries for user: %s", cleared, user_id)
    except Exception as e:
        logger.debug("Cache cleanup failed: %s", e)

    # Delete refresh token cookie with same attributes as set
    response.delete_cookie(
        key=_refresh_cookie_name(),
        path=_refresh_cookie_path(),
        domain=_cookie_domain(),
        secure=_cookie_secure(),
    )

    # Audit: logout
    write_audit_log(db, current_user.username, "LOGOUT", "AUTH", "User logged out")
    await db.commit()

    logger.info("User logout completed: %s", current_user.username)
    return {"success": True, "message": "Logged out successfully"}


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Issue a new access token using the HttpOnly refresh cookie.

    Raises:
        401 if cookie missing/invalid
    """
    refresh_token = request.cookies.get(_refresh_cookie_name())
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    tokens = await refresh_tokens(
        db,
        refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # If refresh rotation returns a new refresh token, update cookie.
    if "refresh_token" in tokens and tokens["refresh_token"]:
        response.set_cookie(
            key=_refresh_cookie_name(),
            value=tokens["refresh_token"],
            httponly=True,
            secure=_cookie_secure(),
            samesite=_cookie_samesite(),
            path=_refresh_cookie_path(),
            domain=_cookie_domain(),
            max_age=int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
        )

    return RefreshTokenResponse(
        access_token=tokens["access_token"],
        token_type=tokens["token_type"],
    )


@router.post("/password-reset/request", response_model=MessageResponse)
async def password_reset_request_endpoint(req: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """
    Submit password reset request for admin approval.
    Always returns success to prevent user enumeration.
    """
    await request_password_reset(db, req.username, req.reason)
    return {"success": True, "message": "If account exists, reset email will be sent"}


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def password_reset_confirm_endpoint(req: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    """Confirm password reset using one-time token."""
    await confirm_password_reset(db, req.token, req.new_password)
    return {"success": True, "message": "Password reset successful"}
