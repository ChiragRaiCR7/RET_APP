from datetime import timedelta, datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request

from api.models.models import User, PasswordResetToken
from api.core.security import verify_password, hash_password, create_token
from api.core.config import settings
from api.services.session_service import (
    create_login_session,
    validate_refresh_token,
)

import secrets
import hashlib


def authenticate_user(db: Session, username: str, password: str) -> User:
    # Normalize username to lowercase for case-insensitive matching
    normalized_username = username.lower().strip()
    user = db.query(User).filter(User.username == normalized_username).first()

    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.is_locked is True or user.is_active is False:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account locked")

    if not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    return user


def issue_tokens(
    db: Session,
    user: User,
    request: Request,
):
    access_token = create_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    refresh_token = create_login_session(
        db=db,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active,
            "is_locked": user.is_locked,
            "created_at": user.created_at,
        },
    }


def refresh_tokens(db: Session, refresh_token: str):
    session = validate_refresh_token(db, refresh_token)

    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    user = db.get(User, session.user_id)
    if user is None or user.is_active is False or user.is_locked is True:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    access_token = create_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {"access_token": access_token, "token_type": "bearer"}


def request_password_reset(db: Session, username: str):
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return

    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )

    db.add(reset)
    db.commit()

    return raw_token


def confirm_password_reset(db: Session, token: str, new_password: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    reset = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
        )
        .first()
    )

    if reset is None or reset.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reset token")

    user = db.get(User, reset.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid user")

    user.password_hash = hash_password(new_password)
    reset.used = True

    db.commit()
    return {"success": True}
