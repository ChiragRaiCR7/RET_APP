
from __future__ import annotations

import logging
from datetime import timedelta, datetime, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, status, Request
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.models import User, PasswordResetToken, PasswordResetRequest
from api.core.security import verify_password, hash_password, create_token
from api.core.config import settings
from api.services.session_service import (
    create_login_session,
    validate_refresh_token,
)

logger = logging.getLogger(__name__)

# Lockout policy
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User:
    # Normalize username to lowercase for case-insensitive matching
    normalized_username = username.lower().strip()

    res = await db.execute(select(User).where(User.username == normalized_username))
    user = res.scalar_one_or_none()

    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.is_active is False or user.is_deleted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # Check lockout
    if user.is_locked:
        if user.locked_until and user.locked_until > _utcnow():
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account locked")
        # Lockout expired — reset
        user.is_locked = False
        user.failed_login_attempts = 0
        user.locked_until = None

    if not verify_password(password, user.password_hash):
        # Increment failed attempts
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= _MAX_FAILED_ATTEMPTS:
            user.is_locked = True
            user.locked_until = _utcnow() + timedelta(minutes=_LOCKOUT_MINUTES)
            logger.warning("Account locked after %d failed attempts: %s", _MAX_FAILED_ATTEMPTS, normalized_username)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Successful login — reset failed attempts
    if user.failed_login_attempts:
        user.failed_login_attempts = 0
        user.locked_until = None

    await db.commit()
    return user


async def issue_tokens(db: AsyncSession, user: User, request: Request) -> Dict[str, Any]:
    access_token = create_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )

    # Refresh token creation delegated to session_service (must be async)
    refresh_token = await create_login_session(
        db=db,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": str(getattr(user.role, "value", user.role)).lower(),
            "is_active": user.is_active,
            "is_locked": user.is_locked,
            "created_at": user.created_at,
        },
    }


async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Dict[str, Any]:
    result = await validate_refresh_token(
        db,
        refresh_token,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    session = result["session"]

    res_user = await db.execute(select(User).where(User.id == session.user_id))
    user = res_user.scalar_one_or_none()

    if user is None or user.is_active is False or user.is_locked is True:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account disabled")

    access_token = create_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )

    resp: Dict[str, Any] = {"access_token": access_token, "token_type": "bearer"}

    # If rotation produced a new refresh token, include it so the router can
    # update the HttpOnly cookie.
    if result.get("new_refresh_token"):
        resp["refresh_token"] = result["new_refresh_token"]

    return resp


async def request_password_reset(db: AsyncSession, username: str, reason: str | None = None) -> bool:
    normalized = username.lower().strip()

    res = await db.execute(select(User).where(User.username == normalized))
    user = res.scalar_one_or_none()

    if user is None:
        return True  # prevent user enumeration

    # Create an admin-visible reset request (token is generated by admin)
    req = PasswordResetRequest(
        username=normalized,
        reason=reason,
        status="pending",
        created_at=_utcnow(),
    )
    db.add(req)
    await db.commit()
    return True


async def confirm_password_reset(db: AsyncSession, token: str, new_password: str) -> Dict[str, Any]:
    res = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.used == False,  # noqa: E712
            PasswordResetToken.expires_at > _utcnow(),
        )
    )
    candidates = res.scalars().all()

    reset = None
    for candidate in candidates:
        if verify_password(token, candidate.token_hash):
            reset = candidate
            break

    if reset is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")

    res_user = await db.execute(select(User).where(User.id == reset.user_id))
    user = res_user.scalar_one_or_none()

    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid user")

    user.password_hash = hash_password(new_password)
    reset.used = True

    await db.commit()
    return {"success": True}