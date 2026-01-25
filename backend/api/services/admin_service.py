from sqlalchemy.orm import Session
from datetime import datetime

from api.models.models import (
    User,
    AuditLog,
    OpsLog,
    LoginSession,
)
from api.core.security import hash_password
from api.core.exceptions import NotFound, Forbidden


def create_user(db: Session, username: str, password: str, role: str):
    if db.query(User).filter(User.username == username).first():
        raise Forbidden("User already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def update_user(db: Session, user_id: int, **updates):
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")

    for k, v in updates.items():
        if v is not None:
            setattr(user, k, v)

    return user


def delete_user(db: Session, user_id: int):
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")
    db.delete(user)


def list_users(db: Session):
    return db.query(User).order_by(User.created_at.desc()).all()


def force_logout_user(db: Session, user_id: int):
    db.query(LoginSession).filter(LoginSession.user_id == user_id).delete()


def write_audit_log(
    db: Session,
    username: str | None,
    action: str,
    area: str,
    message: str,
):
    log = AuditLog(
        username=username,
        action=action,
        area=area,
        message=message,
        created_at=datetime.utcnow(),
    )
    db.add(log)


def list_audit_logs(db: Session, limit: int = 200):
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


def list_ops_logs(db: Session, limit: int = 200):
    return (
        db.query(OpsLog)
        .order_by(OpsLog.created_at.desc())
        .limit(limit)
        .all()
    )
