"""Tests for session_service — token creation, rotation, reuse detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.models import LoginSession
from api.services.session_service import (
    _hash_token,
    create_login_session,
    revoke_all_user_sessions,
    revoke_refresh_token,
    validate_refresh_token,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── create_login_session ──


class TestCreateLoginSession:
    @pytest.mark.asyncio
    async def test_creates_session_returns_raw_token(self, async_db: AsyncSession, test_user):
        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "pytest")

        assert isinstance(raw, str)
        assert len(raw) > 30  # token_urlsafe(48) produces ~64 chars

        # Verify row exists in DB with hashed value
        h = _hash_token(raw)
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.refresh_token_hash == h)
        )
        session = res.scalar_one_or_none()
        assert session is not None
        assert session.user_id == test_user.id
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "pytest"
        assert session.revoked is False
        assert session.token_family is not None

    @pytest.mark.asyncio
    async def test_multiple_sessions_different_families(self, async_db: AsyncSession, test_user):
        t1 = await create_login_session(async_db, test_user.id, None, None)
        t2 = await create_login_session(async_db, test_user.id, None, None)

        h1 = _hash_token(t1)
        h2 = _hash_token(t2)

        r1 = await async_db.execute(select(LoginSession).where(LoginSession.refresh_token_hash == h1))
        r2 = await async_db.execute(select(LoginSession).where(LoginSession.refresh_token_hash == h2))

        s1 = r1.scalar_one()
        s2 = r2.scalar_one()

        # Different sessions should have different families
        assert s1.token_family != s2.token_family


# ── validate_refresh_token ──


class TestValidateRefreshToken:
    @pytest.mark.asyncio
    async def test_valid_token_no_rotation(self, async_db: AsyncSession, test_user):
        """Without rotation flag, token is valid and no new token issued."""
        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "pytest")

        with patch("api.services.session_service.settings") as mock_settings:
            mock_settings.FEATURE_TOKEN_ROTATION = False
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            result = await validate_refresh_token(async_db, raw)

        assert result is not None
        assert result["session"].user_id == test_user.id
        assert result["new_refresh_token"] is None

    @pytest.mark.asyncio
    async def test_valid_token_with_rotation(self, async_db: AsyncSession, test_user):
        """With rotation flag, old token is revoked and new one issued."""
        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "pytest")

        with patch("api.services.session_service.settings") as mock_settings:
            mock_settings.FEATURE_TOKEN_ROTATION = True
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            result = await validate_refresh_token(async_db, raw, ip_address="127.0.0.1")

        assert result is not None
        assert result["new_refresh_token"] is not None
        assert isinstance(result["new_refresh_token"], str)

        # Old token should be revoked
        old_hash = _hash_token(raw)
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.refresh_token_hash == old_hash)
        )
        old_session = res.scalar_one()
        assert old_session.revoked is True
        assert old_session.replaced_by_id is not None

    @pytest.mark.asyncio
    async def test_reuse_detection_deletes_family(self, async_db: AsyncSession, test_user):
        """Presenting a revoked token wipes the entire family."""
        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "pytest")

        # First rotation: consume original token
        with patch("api.services.session_service.settings") as mock_settings:
            mock_settings.FEATURE_TOKEN_ROTATION = True
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            result = await validate_refresh_token(async_db, raw)

        assert result is not None
        new_token = result["new_refresh_token"]
        assert new_token is not None

        # Get the family id for later verification
        old_hash = _hash_token(raw)
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.refresh_token_hash == old_hash)
        )
        old_session = res.scalar_one()
        family = old_session.token_family

        # Reuse: present the *original* (now-revoked) token again
        with patch("api.services.session_service.settings") as mock_settings:
            mock_settings.FEATURE_TOKEN_ROTATION = True
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            result2 = await validate_refresh_token(async_db, raw)

        # Reuse detected → None returned
        assert result2 is None

        # Entire family should be gone
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.token_family == family)
        )
        assert res.scalars().all() == []

    @pytest.mark.asyncio
    async def test_nonexistent_token_returns_none(self, async_db: AsyncSession):
        result = await validate_refresh_token(async_db, "does-not-exist-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_token_returns_none(self, async_db: AsyncSession, test_user):
        """An expired session should be cleaned up and return None."""
        raw = await create_login_session(async_db, test_user.id, None, None)

        # Manually set expiry to the past
        h = _hash_token(raw)
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.refresh_token_hash == h)
        )
        session = res.scalar_one()
        session.expires_at = _utcnow() - timedelta(hours=1)
        await async_db.commit()

        with patch("api.services.session_service.settings") as mock_settings:
            mock_settings.FEATURE_TOKEN_ROTATION = False
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            result = await validate_refresh_token(async_db, raw)

        assert result is None

        # Session row should have been deleted
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.refresh_token_hash == h)
        )
        assert res.scalar_one_or_none() is None


# ── revoke_refresh_token ──


class TestRevokeRefreshToken:
    @pytest.mark.asyncio
    async def test_revoke_deletes_session(self, async_db: AsyncSession, test_user):
        raw = await create_login_session(async_db, test_user.id, None, None)
        await revoke_refresh_token(async_db, raw)

        h = _hash_token(raw)
        res = await async_db.execute(
            select(LoginSession).where(LoginSession.refresh_token_hash == h)
        )
        assert res.scalar_one_or_none() is None


# ── revoke_all_user_sessions ──


class TestRevokeAllUserSessions:
    @pytest.mark.asyncio
    async def test_revokes_all(self, async_db: AsyncSession, test_user):
        # Create 3 sessions
        for _ in range(3):
            await create_login_session(async_db, test_user.id, None, None)

        count = await revoke_all_user_sessions(async_db, test_user.id)
        assert count == 3

        res = await async_db.execute(
            select(LoginSession).where(LoginSession.user_id == test_user.id)
        )
        assert res.scalars().all() == []

    @pytest.mark.asyncio
    async def test_revoke_zero_sessions(self, async_db: AsyncSession, test_user):
        count = await revoke_all_user_sessions(async_db, test_user.id)
        assert count == 0
