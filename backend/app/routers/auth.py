from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update

from app.config import get_settings
from app.models import AuthSession, PasswordResetRequest, PasswordResetToken, User, utcnow
from app.schemas import (
    ChangePasswordIn,
    LoginIn,
    Message,
    ResetConfirmIn,
    ResetRequestIn,
    UserOut,
)
from app.security import (
    DB,
    CurrentUser,
    audit,
    dummy_verify,
    end_session,
    hash_password,
    password_problem,
    start_session,
    token_digest,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
BAD_CREDENTIALS = "Incorrect username or password."


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: DB) -> User:
    settings = get_settings()
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    now = utcnow()
    if user is None:
        dummy_verify(body.password)
        audit(db, request, "login.failed", actor=body.username[:64], reason="unknown user")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    if user.locked_until and user.locked_until > now:
        audit(db, request, "login.locked", actor=user.username)
        db.commit()
        raise HTTPException(
            status.HTTP_423_LOCKED,
            "Account temporarily locked after repeated failures. Try again later.",
        )
    if not verify_password(user.password_hash, body.password) or not user.is_active:
        user.failed_logins += 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        audit(db, request, "login.failed", actor=user.username)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)

    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    start_session(db, user, request, response)
    audit(db, request, "login", actor=user.username)
    db.commit()
    return user


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: DB) -> Message:
    end_session(db, request, response)
    db.commit()
    return Message(message="Signed out.")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.post("/password", response_model=Message)
def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, db: DB) -> Message:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if problem := password_problem(body.new_password, user.username):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user.password_hash = hash_password(body.new_password)
    # Sign out every other session; keep the one making this request.
    current = token_digest(request.cookies.get("ret_session", ""))
    db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token_hash != current)
    )
    audit(db, request, "password.changed", target=user.username)
    db.commit()
    return Message(message="Password changed.")


@router.post("/reset-requests", response_model=Message, status_code=202)
def request_reset(body: ResetRequestIn, request: Request, db: DB) -> Message:
    """Anyone may ask an admin for a reset. Response is identical whether or not the user
    exists, so this cannot be used to enumerate accounts."""
    pending = db.scalar(
        select(PasswordResetRequest).where(
            PasswordResetRequest.username == body.username, PasswordResetRequest.status == "pending"
        )
    )
    if pending is None:
        db.add(PasswordResetRequest(username=body.username, reason=body.reason))
        audit(db, request, "reset.requested", actor=body.username)
        db.commit()
    return Message(message="Request sent. An administrator will give you a reset code.")


@router.post("/reset", response_model=Message)
def confirm_reset(body: ResetConfirmIn, request: Request, db: DB) -> Message:
    token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(body.token))
    )
    if token is None or token.used_at is not None or token.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset code is invalid or expired.")
    user = db.get(User, token.user_id)
    assert user is not None
    if problem := password_problem(body.new_password, user.username):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user.password_hash = hash_password(body.new_password)
    user.failed_logins, user.locked_until = 0, None
    token.used_at = utcnow()
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(
        update(PasswordResetRequest)
        .where(PasswordResetRequest.username == user.username)
        .values(status="resolved")
    )
    audit(db, request, "reset.completed", actor=user.username)
    db.commit()
    return Message(message="Password updated. Sign in with your new password.")
