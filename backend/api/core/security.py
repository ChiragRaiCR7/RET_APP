
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Optional, Dict
from pydantic import SecretStr

from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

from api.core.config import settings

# ---------------------------------------------------------------------------
# Argon2id parameters — explicit hardening for GPU-resistance.
# ~300 ms per hash on modern hardware is the recommended target.
# ---------------------------------------------------------------------------
hasher = PasswordHasher(
    time_cost=2,        # number of iterations
    memory_cost=65536,  # 64 MiB — raises GPU attack cost significantly
    parallelism=2,
)

# ---------------------------------------------------------------------------
# In-memory token revocation set
# Stores revoked JWT IDs (jti) for the lifetime of the process.
# NOTE: In multi-instance or post-restart scenarios, persist to Redis / DB.
# ---------------------------------------------------------------------------
_revoked_jtis: set[str] = set()


def _utcnow() -> datetime:
    """Return current time in UTC."""
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify *password* against its Argon2 *hashed* value."""
    try:
        hasher.verify(hashed, password)  # verify(hash, password) — order matters
        return True
    except (VerifyMismatchError, InvalidHash):
        return False
    except Exception:
        return False


def verify_and_check_rehash(password: str, hashed: str) -> tuple[bool, bool]:
    """
    Verify *password* and report whether the stored hash needs upgrading.

    Returns:
        (password_valid, needs_rehash) — if ``password_valid`` is True and
        ``needs_rehash`` is True the caller should transparently rehash and
        persist the new hash so the account automatically migrates to the
        current Argon2 parameters on next login.
    """
    try:
        hasher.verify(hashed, password)
        return True, hasher.check_needs_rehash(hashed)
    except (VerifyMismatchError, InvalidHash):
        return False, False
    except Exception:
        return False, False


def revoke_token(jti: str) -> None:
    """Add a token JTI to the in-memory revocation set."""
    _revoked_jtis.add(jti)


def is_token_revoked(jti: str) -> bool:
    """Return True if the JTI has been explicitly revoked."""
    return jti in _revoked_jtis


def _get_jwt_secret_key() -> str:
    """Return JWT secret as plain string (handles SecretStr safely)."""
    key = settings.JWT_SECRET_KEY
    if key is None:
        raise ValueError("JWT_SECRET_KEY is not configured")

    secret = key.get_secret_value() if isinstance(key, SecretStr) else str(key)
    if not secret:
        raise ValueError("JWT_SECRET_KEY is not configured")
    return secret


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str = "access",
    additional_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Internal helper — create a signed JWT with standard claims.

    Callers outside this module should use ``create_access_token`` or
    ``create_refresh_token`` rather than calling this directly.
    """
    key = _get_jwt_secret_key()

    now = _utcnow()
    payload: Dict[str, Any] = {
        "sub": subject,
        # python-jose handles timezone-aware datetimes correctly.
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": secrets.token_hex(16),  # unique ID for per-token revocation
        "type": token_type,
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, key, algorithm=settings.JWT_ALGORITHM)


# Backward-compatible alias — prefer the named helpers below in new code.
create_token = _create_token


def create_access_token(subject: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a short-lived access token for *subject*."""
    return _create_token(
        subject=subject,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
        additional_claims=additional_claims,
    )


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token for *subject*."""
    return _create_token(
        subject=subject,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


def create_token_pair(subject: str) -> tuple[str, str]:
    """
    Create a matched (access_token, refresh_token) pair in one call.

    Use this when issuing initial credentials or rotating refresh tokens so
    both tokens share the same ``subject`` and are created atomically.
    """
    return create_access_token(subject), create_refresh_token(subject)


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    Verify and decode a JWT token.

    Raises:
        ValueError: with a descriptive message on any failure so callers can
                    map to the appropriate HTTP exception.
    """
    key = _get_jwt_secret_key()

    try:
        payload: Dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        if payload.get("type") != token_type:
            raise ValueError(f"Expected {token_type} token, got {payload.get('type')}")

        # Check revocation list
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            raise ValueError("Token has been revoked")

        return payload

    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTClaimsError as e:
        raise ValueError(f"Invalid token claims: {e}")
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")

