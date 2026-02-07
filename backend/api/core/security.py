from datetime import datetime, timedelta, timezone
import secrets
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from api.core.config import settings

# Initialize Argon2 password hasher
hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2"""
    return hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its Argon2 hash"""
    try:
        hasher.verify(hashed, password)  # verify(hash, password) - order matters!
        return True
    except (VerifyMismatchError, InvalidHash):
        return False
    except Exception:
        # Log unexpected errors but still return False
        return False


def create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str = "access",
    additional_claims: dict | None = None,
) -> str:
    """
    Create a JWT token with proper claims.
    
    Args:
        subject: The user ID or identifier
        expires_delta: Token expiration time
        token_type: 'access' or 'refresh'
        additional_claims: Optional extra claims to include
    
    Returns:
        Encoded JWT token
    """
    if not settings.JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not configured")
    
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,  # Issued at
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,  # Issuer
        "aud": settings.JWT_AUDIENCE,  # Audience
        "jti": secrets.token_hex(16),  # JWT ID for revocation tracking
        "type": token_type,
    }
    
    if additional_claims:
        payload.update(additional_claims)
    
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(subject: str, additional_claims: dict | None = None) -> str:
    """Create an access token with standard expiration."""
    return create_token(
        subject=subject,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
        additional_claims=additional_claims,
    )


def create_refresh_token(subject: str) -> str:
    """Create a refresh token with longer expiration."""
    return create_token(
        subject=subject,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


def verify_token(token: str, token_type: str = "access") -> dict:
    """
    Verify and decode a JWT token.
    
    Args:
        token: The JWT token to verify
        token_type: Expected token type ('access' or 'refresh')
    
    Returns:
        Decoded token payload
    
    Raises:
        ValueError: If token is invalid or verification fails
    """
    if not settings.JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not configured")
    
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
        
        # Verify token type
        if payload.get("type") != token_type:
            raise ValueError(f"Expected {token_type} token, got {payload.get('type')}")
        
        return payload
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTClaimsError as e:
        raise ValueError(f"Invalid token claims: {e}")
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
