import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.models import (
    AuditEvent,
    AuthSession,
    Dataset,
    PasswordResetRequest,
    PasswordResetToken,
    User,
    Workspace,
    utcnow,
)
from app.schemas import (
    AdminStats,
    AuditEventOut,
    Message,
    ResetRequestOut,
    ResetTokenOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from app.security import DB, AdminUser, audit, hash_password, password_problem, token_digest

router = APIRouter(prefix="/admin", tags=["admin"])


def _dir_bytes() -> int:
    root = get_settings().workspaces_dir
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.exists() else 0


@router.get("/stats", response_model=AdminStats)
def stats(_: AdminUser, db: DB) -> AdminStats:
    return AdminStats(
        users=db.scalar(select(func.count(User.id))) or 0,
        active_sessions=db.scalar(
            select(func.count(AuthSession.id)).where(AuthSession.expires_at > utcnow())
        )
        or 0,
        workspaces=db.scalar(select(func.count(Workspace.id))) or 0,
        datasets=db.scalar(select(func.count(Dataset.id))) or 0,
        disk_bytes=_dir_bytes(),
        llm_configured=get_settings().llm_configured,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DB) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, request: Request, _: AdminUser, db: DB) -> User:
    if db.scalar(select(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists.")
    if problem := password_problem(body.password, body.username):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    audit(db, request, "user.created", target=body.username, role=body.role)
    db.commit()
    return user


def _target(db: DB, admin: User, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own account here.")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdateIn, request: Request, admin: AdminUser, db: DB
) -> User:
    user = _target(db, admin, user_id)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, request, "user.updated", target=user.username, **body.model_dump(exclude_none=True))
    db.commit()
    return user


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: int, request: Request, admin: AdminUser, db: DB) -> User:
    user = _target(db, admin, user_id)
    user.failed_logins, user.locked_until = 0, None
    audit(db, request, "user.unlocked", target=user.username)
    db.commit()
    return user


@router.post("/users/{user_id}/reset-token", response_model=ResetTokenOut)
def issue_reset_token(user_id: int, request: Request, admin: AdminUser, db: DB) -> ResetTokenOut:
    user = _target(db, admin, user_id)
    token = secrets.token_urlsafe(24)
    expires = utcnow() + timedelta(minutes=get_settings().reset_token_ttl_minutes)
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_digest(token), expires_at=expires))
    audit(db, request, "reset.token_issued", target=user.username)
    db.commit()
    # Shown once to the admin, who hands it over out of band. Only the hash is stored.
    return ResetTokenOut(token=token, expires_at=expires)


@router.delete("/users/{user_id}", response_model=Message)
def delete_user(user_id: int, request: Request, admin: AdminUser, db: DB) -> Message:
    from app.services.workspaces import delete_workspace

    user = _target(db, admin, user_id)
    for ws in db.scalars(select(Workspace).where(Workspace.owner_id == user.id)).all():
        delete_workspace(db, ws)
    db.delete(user)
    audit(db, request, "user.deleted", target=user.username)
    db.commit()
    return Message(message=f"Deleted {user.username} and their workspaces.")


@router.get("/reset-requests", response_model=list[ResetRequestOut])
def reset_requests(_: AdminUser, db: DB) -> list[PasswordResetRequest]:
    return list(
        db.scalars(
            select(PasswordResetRequest)
            .where(PasswordResetRequest.status == "pending")
            .order_by(PasswordResetRequest.created_at.desc())
        )
    )


@router.get("/audit", response_model=list[AuditEventOut])
def audit_log(
    _: AdminUser, db: DB, limit: int = Query(200, ge=1, le=2000), action: str | None = None
) -> list[AuditEvent]:
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if action:
        q = q.where(AuditEvent.action.startswith(action))
    return list(db.scalars(q))
