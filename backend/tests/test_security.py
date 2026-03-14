"""Tests for security module: password hashing and JWT tokens."""

from __future__ import annotations

import time

import pytest

from api.core.security import (
    create_access_token,
    create_refresh_token,
    create_token,
    hash_password,
    verify_password,
    verify_token,
)


# ── Password hashing ──


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "Str0ngP@ssword!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("Correct1!")
        assert verify_password("Wrong1!", hashed) is False

    def test_hash_is_unique(self):
        h1 = hash_password("Same1!")
        h2 = hash_password("Same1!")
        # Argon2 uses random salt, so hashes differ
        assert h1 != h2

    def test_empty_password_rejected(self):
        # Empty password should still hash, but shouldn't match non-empty
        hashed = hash_password("something")
        assert verify_password("", hashed) is False


# ── JWT Tokens ──


class TestJWTTokens:
    def test_create_and_verify_access_token(self):
        token = create_access_token("42")
        payload = verify_token(token, token_type="access")
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_create_and_verify_refresh_token(self):
        token = create_refresh_token("42")
        payload = verify_token(token, token_type="refresh")
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"

    def test_access_token_rejected_as_refresh(self):
        token = create_access_token("42")
        with pytest.raises(ValueError, match="Expected"):
            verify_token(token, token_type="refresh")

    def test_refresh_token_rejected_as_access(self):
        token = create_refresh_token("42")
        with pytest.raises(ValueError, match="Expected"):
            verify_token(token, token_type="access")

    def test_expired_token(self):
        from datetime import timedelta
        token = create_token("42", expires_delta=timedelta(seconds=-1))
        with pytest.raises(ValueError, match="[Ee]xpir"):
            verify_token(token)

    def test_invalid_token(self):
        with pytest.raises(ValueError):
            verify_token("not.a.valid.token")

    def test_additional_claims(self):
        token = create_access_token("42", additional_claims={"role": "admin"})
        payload = verify_token(token)
        assert payload["role"] == "admin"

    def test_token_has_jti(self):
        token = create_access_token("42")
        payload = verify_token(token)
        assert "jti" in payload
