
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, status


class APIException(HTTPException):
    """
    Base class for all application-level HTTP exceptions.

    Provides a consistent error structure with machine-readable error codes
    (surfaced via ``X-Error-Code`` response header) and optional metadata
    alongside the human-readable ``detail`` message.

    Subclasses should set the class-level ``error_code`` to a snake_case
    identifier that the frontend can act on deterministically.
    """

    error_code: str = "internal_error"

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        code = error_code or self.__class__.error_code
        headers: Dict[str, str] = {"X-Error-Code": code}
        if extra_headers:
            headers.update(extra_headers)
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        # Store on instance so middleware / handlers can read it
        self.error_code = code
        self.metadata: Dict[str, Any] = metadata or {}


# ---------------------------------------------------------------------------
# 401 — Authentication
# ---------------------------------------------------------------------------

class Unauthorized(APIException):
    """
    Raised when credentials are entirely absent (no token provided).
    Distinct from ``TokenInvalidError`` (malformed/wrong token) and
    ``TokenExpiredError`` (valid token but past its expiry).
    """
    error_code = "missing_credentials"

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            extra_headers={"WWW-Authenticate": "Bearer"},
        )


class TokenExpiredError(APIException):
    """Raised when a JWT access or refresh token has expired."""
    error_code = "token_expired"

    def __init__(self, detail: str = "Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            extra_headers={"WWW-Authenticate": "Bearer"},
        )


class TokenInvalidError(APIException):
    """Raised when a JWT token is invalid, malformed, or has invalid claims."""
    error_code = "token_invalid"

    def __init__(self, detail: str = "Invalid token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            extra_headers={"WWW-Authenticate": "Bearer"},
        )


class TokenRevokedError(APIException):
    """Raised when a token has been explicitly revoked (logout, password change, account lock)."""
    error_code = "token_revoked"

    def __init__(self, detail: str = "Token has been revoked"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            extra_headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# 403 — Authorisation
# ---------------------------------------------------------------------------

class Forbidden(APIException):
    """Raised when the user is authenticated but lacks the required permission."""
    error_code = "forbidden"

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


# ---------------------------------------------------------------------------
# 404 — Resource not found
# ---------------------------------------------------------------------------

class NotFound(APIException):
    """Raised when a requested resource does not exist."""
    error_code = "not_found"

    def __init__(self, detail: str = "Not found"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class LoginSessionNotFoundError(APIException):
    """Raised when a login-session token doesn't exist or has been cleaned up."""
    error_code = "login_session_not_found"

    def __init__(self, detail: str = "Login session not found or expired"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ProcessingSessionNotFoundError(APIException):
    """Raised when an AI/conversion processing session doesn't exist."""
    error_code = "processing_session_not_found"

    def __init__(self, detail: str = "Processing session not found or expired"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


# Backward-compatible alias — prefer the named variants above in new code.
SessionNotFoundError = LoginSessionNotFoundError


# ---------------------------------------------------------------------------
# 400 / 409 / 422 — Request errors
# ---------------------------------------------------------------------------

class BadRequest(APIException):
    """Raised for malformed or semantically invalid requests."""
    error_code = "bad_request"

    def __init__(self, detail: str = "Bad request"):
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class ConflictError(APIException):
    """Raised when a resource conflict occurs (e.g. duplicate username)."""
    error_code = "conflict"

    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(status.HTTP_409_CONFLICT, detail)


class ValidationError(APIException):
    """Domain-level validation failure (distinct from Pydantic schema errors)."""
    error_code = "validation_error"

    def __init__(
        self,
        detail: str = "Validation failed",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# 429 / 503 — Traffic & availability
# ---------------------------------------------------------------------------

class RateLimitExceeded(APIException):
    """Raised when a client exceeds the configured request rate."""
    error_code = "rate_limit_exceeded"

    def __init__(self, retry_after: int = 60, detail: str = "Rate limit exceeded"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            extra_headers={"Retry-After": str(retry_after)},
        )


class ServiceUnavailableError(APIException):
    """Raised when a downstream service (e.g. Azure OpenAI) is unavailable."""
    error_code = "service_unavailable"

    def __init__(self, detail: str = "Service temporarily unavailable"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            extra_headers={"Retry-After": "30"},
        )


# ---------------------------------------------------------------------------
# Non-HTTP exceptions (raised in service/worker layers)
# ---------------------------------------------------------------------------

class TaskCancelledError(Exception):
    """Raised when a background task is cancelled."""
    def __init__(self, detail: str = "Task was cancelled"):
        self.detail = detail
        super().__init__(detail)


class EmbeddingError(Exception):
    """Raised when an embedding operation fails."""
    def __init__(self, detail: str = "Embedding operation failed", group: str | None = None):
        self.detail = detail
        self.group = group
        super().__init__(detail)
