from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from api.core.config import settings
from api.core.database import get_db
from api.core.exceptions import TokenExpiredError, TokenInvalidError
from api.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from JWT token.

    Returns a full User object (not just ID) to reduce repeated DB lookups.
    Validates JWT claims including issuer and audience.
    """
    if not settings.JWT_SECRET_KEY:
        raise TokenInvalidError(detail="JWT configuration error")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")

        if user_id is None:
            raise TokenInvalidError(detail="Token missing subject claim")

        # Only accept access tokens (not refresh tokens)
        if token_type != "access":
            raise TokenInvalidError(detail="Invalid token type")

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.JWTClaimsError:
        raise TokenInvalidError(detail="Invalid token claims")
    except JWTError:
        raise TokenInvalidError(detail="Could not validate credentials")

    user = db.get(User, int(user_id))

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

    return user


def get_current_user_id(
    current_user: User = Depends(get_current_user),
) -> str:
    """
    Get just the user ID as a string.

    For backward compatibility with code that expects a string user ID.
    """
    return str(current_user.id)


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get the current user if authenticated, or None if not.

    Use this for endpoints that work both authenticated and unauthenticated.
    """
    if not token:
        return None

    try:
        return get_current_user(token, db)
    except HTTPException:
        return None
