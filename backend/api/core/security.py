from datetime import datetime, timedelta
from jose import jwt
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
    except (VerifyMismatchError, InvalidHash, Exception):
        return False

def create_token(subject: str, expires_delta: timedelta) -> str:
    if not settings.JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not configured")
    
    payload = {
        "sub": subject,
        "exp": datetime.utcnow() + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
