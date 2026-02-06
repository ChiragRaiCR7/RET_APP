from fastapi import HTTPException, status


class Unauthorized(HTTPException):
    def __init__(self, detail="Unauthorized"):
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


class TokenExpiredError(HTTPException):
    """Raised when a JWT token has expired."""
    def __init__(self, detail="Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer", "X-Error-Code": "token_expired"},
        )


class TokenInvalidError(HTTPException):
    """Raised when a JWT token is invalid or malformed."""
    def __init__(self, detail="Invalid token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer", "X-Error-Code": "token_invalid"},
        )


class Forbidden(HTTPException):
    def __init__(self, detail="Forbidden"):
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class NotFound(HTTPException):
    def __init__(self, detail="Not found"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class BadRequest(HTTPException):
    def __init__(self, detail="Bad request"):
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class SessionNotFoundError(HTTPException):
    """Raised when a session ID doesn't exist or has been cleaned up."""
    def __init__(self, detail="Session not found or expired"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class RateLimitExceeded(HTTPException):
    """Raised when rate limit is exceeded."""
    def __init__(self, retry_after: int = 60, detail="Rate limit exceeded"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )
