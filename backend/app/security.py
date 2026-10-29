"""Password hashing, cookie sessions, request guards and audit logging."""

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, AuthSession, User, utcnow

log = logging.getLogger("ret.security")

SESSION_COOKIE = "ret_session"
_hasher = PasswordHasher()
# Hash of a random password: verifying against it keeps login timing equal for unknown users.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))
MIN_PASSWORD_LEN = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def password_problem(password: str, username: str) -> str | None:
    """Return a human-readable reason the password is unacceptable, or None."""
    if len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if username and username.lower() in password.lower():
        return "Password must not contain the username."
    return None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, request: Request, response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
            ip=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/api",
    )


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    response.delete_cookie(SESSION_COOKIE, path="/api")


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    if sess is None or sess.expires_at <= utcnow() or not sess.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.")
    request.state.username = sess.user.username
    return sess.user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]


def origin_allowed(request: Request) -> bool:
    """CSRF guard for cookie-authenticated writes: the browser-sent Origin must be trusted.

    SameSite=Strict already blocks cross-site cookies in modern browsers; this check is the
    second layer for older browsers and same-site-but-cross-origin attackers.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    origin = request.headers.get("origin")
    if origin is None:
        # Non-browser clients (curl, tests) send no Origin and carry no ambient cookies risk.
        return request.headers.get("sec-fetch-site") in (None, "same-origin", "none")
    own = f"{request.url.scheme}://{request.url.netloc}"
    return origin == own or origin in get_settings().allowed_origins


def audit(
    db: Session,
    request: Request | None,
    action: str,
    target: str | None = None,
    actor: str | None = None,
    **details: Any,
) -> None:
    """Record a security- or data-relevant event. Caller commits."""
    if actor is None and request is not None:
        actor = getattr(request.state, "username", None)
    rid = getattr(request.state, "request_id", None) if request is not None else None
    db.add(
        AuditEvent(
            actor=actor, action=action, target=target, details=details or None, request_id=rid
        )
    )
    log.info("audit action=%s actor=%s target=%s", action, actor, target)
