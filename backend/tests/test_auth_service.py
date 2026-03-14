"""Tests for auth_service — authenticate, lockout, token refresh."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.models import User
from api.services.auth_service import authenticate_user, refresh_tokens


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── authenticate_user ──


class TestAuthenticateUser:
    @pytest.mark.asyncio
    async def test_success(self, async_db: AsyncSession, test_user):
        user = await authenticate_user(async_db, "testuser", "TestPass1!")
        assert user.id == test_user.id
        assert user.failed_login_attempts == 0

    @pytest.mark.asyncio
    async def test_wrong_password_increments_failed(self, async_db: AsyncSession, test_user):
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_user(async_db, "testuser", "WrongPassword1!")
        assert exc_info.value.status_code == 401

        await async_db.refresh(test_user)
        assert test_user.failed_login_attempts == 1

    @pytest.mark.asyncio
    async def test_nonexistent_user(self, async_db: AsyncSession):
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_user(async_db, "nonexistent", "pass")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_lockout_after_max_attempts(self, async_db: AsyncSession, test_user):
        """Account locks after 5 consecutive failures."""
        for i in range(5):
            with pytest.raises(HTTPException):
                await authenticate_user(async_db, "testuser", "WrongPassword1!")

        await async_db.refresh(test_user)
        assert test_user.is_locked is True
        assert test_user.locked_until is not None
        assert test_user.failed_login_attempts == 5

        # Even correct password now fails with 403
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_user(async_db, "testuser", "TestPass1!")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_lockout_expires(self, async_db: AsyncSession, test_user):
        """After lockout period, account unlocks automatically."""
        # Lock the account
        test_user.is_locked = True
        test_user.failed_login_attempts = 5
        test_user.locked_until = _utcnow() - timedelta(minutes=1)  # expired
        await async_db.commit()

        # Should succeed now
        user = await authenticate_user(async_db, "testuser", "TestPass1!")
        assert user.is_locked is False
        assert user.failed_login_attempts == 0

    @pytest.mark.asyncio
    async def test_successful_login_resets_attempts(self, async_db: AsyncSession, test_user):
        """A successful login after a few failures resets the counter."""
        # Fail twice
        for _ in range(2):
            with pytest.raises(HTTPException):
                await authenticate_user(async_db, "testuser", "WrongPassword1!")

        await async_db.refresh(test_user)
        assert test_user.failed_login_attempts == 2

        # Succeed
        user = await authenticate_user(async_db, "testuser", "TestPass1!")
        assert user.failed_login_attempts == 0

    @pytest.mark.asyncio
    async def test_inactive_user(self, async_db: AsyncSession, test_user):
        """Inactive user cannot authenticate."""
        test_user.is_active = False
        await async_db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await authenticate_user(async_db, "testuser", "TestPass1!")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_deleted_user(self, async_db: AsyncSession, test_user):
        """Soft-deleted user cannot authenticate."""
        test_user.is_deleted = True
        await async_db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await authenticate_user(async_db, "testuser", "TestPass1!")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_case_insensitive_username(self, async_db: AsyncSession, test_user):
        """Username matching should be case-insensitive."""
        user = await authenticate_user(async_db, "TESTUSER", "TestPass1!")
        assert user.id == test_user.id


# ── refresh_tokens ──


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_valid_refresh(self, async_db: AsyncSession, test_user):
        """Valid refresh token returns new access token."""
        from api.services.session_service import create_login_session

        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "pytest")

        with patch("api.services.auth_service.settings") as mock_settings:
            mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
            mock_settings.FEATURE_TOKEN_ROTATION = False
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            # Patch validate_refresh_token's settings too
            with patch("api.services.session_service.settings") as mock_sess_settings:
                mock_sess_settings.FEATURE_TOKEN_ROTATION = False
                mock_sess_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

                result = await refresh_tokens(async_db, raw)

        assert "access_token" in result
        assert result["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_invalid_refresh_raises(self, async_db: AsyncSession):
        """Invalid refresh token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await refresh_tokens(async_db, "invalid-token")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_rotation_returns_new_refresh(self, async_db: AsyncSession, test_user):
        """With rotation enabled, response includes new refresh token."""
        from api.services.session_service import create_login_session

        raw = await create_login_session(async_db, test_user.id, "127.0.0.1", "pytest")

        with patch("api.services.auth_service.settings") as mock_settings:
            mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30

            with patch("api.services.session_service.settings") as mock_sess_settings:
                mock_sess_settings.FEATURE_TOKEN_ROTATION = True
                mock_sess_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

                result = await refresh_tokens(async_db, raw)

        assert "access_token" in result
        assert "refresh_token" in result
        assert len(result["refresh_token"]) > 30

    @pytest.mark.asyncio
    async def test_refresh_for_locked_user_raises(self, async_db: AsyncSession, test_user):
        """Locked user cannot refresh tokens."""
        from api.services.session_service import create_login_session

        raw = await create_login_session(async_db, test_user.id, None, None)

        # Lock the user
        test_user.is_locked = True
        await async_db.commit()

        with patch("api.services.session_service.settings") as mock_sess_settings:
            mock_sess_settings.FEATURE_TOKEN_ROTATION = False
            mock_sess_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

            with pytest.raises(HTTPException) as exc_info:
                await refresh_tokens(async_db, raw)

        assert exc_info.value.status_code == 403
