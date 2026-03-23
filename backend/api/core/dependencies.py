
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.database import get_db
from api.core.exceptions import TokenExpiredError, TokenInvalidError
from api.core.request_context import get_request_context
from api.core.security import verify_token
from api.models.models import User

logger = logging.getLogger(__name__)


# ✅ tokenUrl mismatch fix + optional auth support
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login",
    auto_error=False,  # ✅ required for get_optional_user to work correctly
)


def _extract_access_token(request: Request, bearer_token: Optional[str]) -> Optional[str]:
    """
    Extract access token in priority order:

    1. HttpOnly access cookie (if ``ACCESS_COOKIE_NAME`` is configured).
    2. ``Authorization: Bearer <token>`` header (OAuth2 standard fallback).

    If a cookie is present but empty/whitespace, a debug log is emitted and
    the bearer token is tried instead, making auth debugging easier.
    """
    cookie_name = getattr(settings, "ACCESS_COOKIE_NAME", None)

    if cookie_name:
        cookie_token = request.cookies.get(cookie_name)
        if cookie_token and cookie_token.strip():
            return cookie_token
        if cookie_token is not None:
            logger.debug(
                "Empty access cookie ignored, falling back to bearer token",
                extra={"extra_fields": {"cookie_name": cookie_name}},
            )

    return bearer_token


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from JWT token.

    - Returns a full User object to reduce repeated DB lookups.
    - Validates JWT claims including issuer and audience.
    - Accepts token from HttpOnly access cookie (if enabled) or Bearer header.
    """
    if not settings.JWT_SECRET_KEY:
        raise TokenInvalidError(detail="JWT configuration error")

    actual_token = _extract_access_token(request, token)
    if not actual_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = verify_token(actual_token, token_type="access")

        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise TokenInvalidError(detail="Token missing subject claim")

    except ValueError as exc:
        msg = str(exc)
        if "expired" in msg.lower():
            raise TokenExpiredError()
        raise TokenInvalidError(detail=msg)

    # ✅ Async-friendly lookup
    try:
        uid = int(user_id)
    except Exception:
        raise TokenInvalidError(detail="Invalid subject claim")

    res = await db.execute(select(User).where(User.id == uid))
    user = res.scalar_one_or_none()

    if user is None:
        raise TokenInvalidError(detail="User not found")

    if not user.is_active or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is locked",
        )

    # Expose user_id on request.state (for rate-limit keying, middleware logging, etc.)
    request.state.user_id = user.id

    # Mirror into RequestContext so service-layer code can read it without
    # receiving the Request object directly.
    ctx = get_request_context()
    ctx.user_id = str(user.id)

    return user


async def get_current_user_id(
    current_user: User = Depends(get_current_user),
) -> str:
    """
    Return the current user ID as a string.

    Kept for backward compatibility with code that declared a ``str`` user ID
    dependency.  In new code prefer ``current_user.id`` directly from
    ``get_current_user`` to avoid the extra dependency hop.
    """
    return str(current_user.id)


async def get_optional_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get the current user if authenticated, or None if not.

    Uses OAuth2PasswordBearer(auto_error=False) so missing tokens don't raise.
    """
    actual_token = _extract_access_token(request, token)
    if not actual_token:
        return None

    try:
        return await get_current_user(request, token, db)
    except HTTPException:
        return None
