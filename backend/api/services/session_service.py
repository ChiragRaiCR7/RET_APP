
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import secrets
import hashlib
from typing import Optional, Dict, Any

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.models import LoginSession
from api.core.config import settings

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(token: str) -> str:
    """
    Hash the raw refresh token before storing/looking up in DB.
    Keeps your original approach (sha256(token)).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_naive_utc(dt: datetime) -> datetime:
    """Normalize datetime to naive UTC for DB comparisons."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _new_family_id() -> str:
    """Generate a unique token-family identifier."""
    return secrets.token_hex(16)


async def create_login_session(
    db: AsyncSession,
    user_id: int,
    ip_address: str | None,
    user_agent: str | None,
) -> str:
    """
    Create a login session and return the *raw* refresh token.

    - refresh token is an opaque random string
    - DB stores only sha256 hash
    - expiry is now + REFRESH_TOKEN_EXPIRE_DAYS
    - assigns a new token_family for rotation tracking
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires = _utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session = LoginSession(
        user_id=user_id,
        refresh_token_hash=token_hash,
        token_family=_new_family_id(),
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=_utcnow(),
        last_used_at=_utcnow(),
        expires_at=expires,
    )

    db.add(session)
    await db.commit()
    return raw_token


async def validate_refresh_token(
    db: AsyncSession,
    token: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Validate refresh token.  Returns a dict with session info and,
    when rotation is enabled, a new raw refresh token.

    Return shape:
        {
            "session": LoginSession,
            "new_refresh_token": str | None,   # present only when rotated
        }

    Reuse detection:
        When FEATURE_TOKEN_ROTATION is enabled and a *revoked* token is
        presented, the entire token family is invalidated (all sessions
        with the same ``token_family`` are deleted) and ``None`` is
        returned, forcing the user to re-authenticate.
    """
    token_hash = _hash_token(token)

    res = await db.execute(
        select(LoginSession).where(LoginSession.refresh_token_hash == token_hash)
    )
    session = res.scalar_one_or_none()

    if not session:
        return None

    # ── Reuse detection ──────────────────────────────────────────
    if session.revoked:
        # A revoked token was presented → compromise suspected.
        # Invalidate the entire family.
        family = session.token_family
        if family:
            logger.warning(
                "Refresh-token reuse detected for user_id=%s family=%s — revoking family",
                session.user_id,
                family,
            )
            await db.execute(
                delete(LoginSession).where(LoginSession.token_family == family)
            )
            await db.commit()
        return None

    # ── Expiry check ─────────────────────────────────────────────
    expires_at = _ensure_naive_utc(session.expires_at)
    now = _utcnow()

    if expires_at < now:
        await db.execute(delete(LoginSession).where(LoginSession.id == session.id))
        await db.commit()
        return None

    # ── Token rotation (when feature flag is on) ─────────────────
    new_raw_token: str | None = None
    if getattr(settings, "FEATURE_TOKEN_ROTATION", False):
        # Mark current token as revoked (consumed).
        session.revoked = True

        # Issue replacement in the same family.
        new_raw_token = secrets.token_urlsafe(48)
        new_hash = _hash_token(new_raw_token)
        new_expires = _utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_session = LoginSession(
            user_id=session.user_id,
            refresh_token_hash=new_hash,
            token_family=session.token_family,
            ip_address=ip_address or session.ip_address,
            user_agent=user_agent or session.user_agent,
            created_at=_utcnow(),
            last_used_at=_utcnow(),
            expires_at=new_expires,
        )
        db.add(new_session)
        await db.flush()

        session.replaced_by_id = new_session.id
        await db.commit()
    else:
        # No rotation — just update last_used_at
        session.last_used_at = now
        await db.commit()

    return {
        "session": session,
        "new_refresh_token": new_raw_token,
    }


async def revoke_refresh_token(db: AsyncSession, token: str) -> None:
    """
    Revoke refresh token by deleting its session row.
    """
    token_hash = _hash_token(token)
    await db.execute(
        delete(LoginSession).where(LoginSession.refresh_token_hash == token_hash)
    )
    await db.commit()


async def revoke_all_user_sessions(db: AsyncSession, user_id: int) -> int:
    """
    Delete every refresh session for the given user.
    Returns count of deleted rows.
    """
    res = await db.execute(
        select(LoginSession).where(LoginSession.user_id == user_id)
    )
    sessions = res.scalars().all()
    count = len(sessions)
    if count:
        await db.execute(
            delete(LoginSession).where(LoginSession.user_id == user_id)
        )
        await db.commit()
        logger.info("Revoked %d sessions for user_id=%s", count, user_id)
    return count