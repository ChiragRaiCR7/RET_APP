from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import secrets
import hashlib

from api.models.models import LoginSession
from api.core.config import settings


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_session(
    db: Session,
    user_id: int,
    ip_address: str | None,
    user_agent: str | None,
) -> str:
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)

    expires = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session = LoginSession(
        user_id=user_id,
        refresh_token_hash=token_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires,
    )

    db.add(session)
    db.commit()

    return raw_token


def validate_refresh_token(db: Session, token: str) -> LoginSession | None:
    token_hash = _hash_token(token)

    session = (
        db.query(LoginSession)
        .filter(LoginSession.refresh_token_hash == token_hash)
        .first()
    )

    if not session:
        return None

    if session.expires_at < datetime.utcnow():
        db.delete(session)
        db.commit()
        return None

    session.last_used_at = datetime.utcnow()
    db.commit()
    return session


def revoke_refresh_token(db: Session, token: str) -> None:
    token_hash = _hash_token(token)
    db.query(LoginSession).filter(
        LoginSession.refresh_token_hash == token_hash
    ).delete()
    db.commit()

