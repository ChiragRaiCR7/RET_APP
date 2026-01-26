from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets

from api.models.models import (
    User,
    AuditLog,
    OpsLog,
    LoginSession,
    PasswordResetToken,
    PasswordResetRequest,
)
from api.core.security import hash_password
from api.core.exceptions import NotFound, Forbidden


def create_user(db: Session, username: str, password: str, role: str = "user"):
    """Create new user with given credentials"""
    if db.query(User).filter(User.username == username).first():
        raise Forbidden("User already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, **updates):
    """Update user fields"""
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")

    for k, v in updates.items():
        if v is not None and hasattr(user, k):
            setattr(user, k, v)

    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int):
    """Get user by ID"""
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")
    return user


def delete_user(db: Session, user_id: int):
    """Delete user and all associated data"""
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")
    
    # Delete sessions
    db.query(LoginSession).filter(LoginSession.user_id == user_id).delete()
    # Delete reset tokens
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    # Delete user
    db.delete(user)
    db.commit()


def list_users(db: Session):
    """List all users ordered by creation"""
    return db.query(User).order_by(User.created_at.desc()).all()


def get_admin_stats(db: Session):
    """Get admin dashboard statistics"""
    total_users = db.query(User).count()
    admins = db.query(User).filter(User.role == "admin").count()
    regular = db.query(User).filter(User.role == "user").count()
    active_sessions = db.query(LoginSession).count()
    
    return {
        "totalUsers": total_users,
        "admins": admins,
        "regular": regular,
        "activeSessions": active_sessions,
    }


def update_user_role(db: Session, user_id: int, new_role: str):
    """Update user role"""
    user = get_user(db, user_id)
    user.role = new_role
    db.commit()
    db.refresh(user)
    return user


def unlock_user_account(db: Session, user_id: int):
    """Unlock user account after failed login attempts"""
    user = get_user(db, user_id)
    user.is_locked = False
    db.commit()
    db.refresh(user)
    return user


def generate_reset_token(db: Session, user_id: int):
    """Generate password reset token for user"""
    user = get_user(db, user_id)
    
    # Delete old unused tokens
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used == False
    ).delete()
    
    # Create new token (valid for 24 hours)
    token = secrets.token_urlsafe(32)
    token_hash = hash_password(token)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    reset_token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()
    
    # Return the unhashed token (only shown once)
    return token


def list_reset_requests(db: Session):
    """List password reset requests"""
    return (
        db.query(PasswordResetRequest)
        .order_by(PasswordResetRequest.created_at.desc())
        .limit(100)
        .all()
    )


def list_sessions(db: Session):
    """List all active sessions with user info"""
    sessions = (
        db.query(LoginSession)
        .join(User)
        .order_by(LoginSession.created_at.desc())
        .limit(200)
        .all()
    )
    
    result = []
    for session in sessions:
        result.append({
            "session_id": str(session.id),
            "username": session.user.username,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_used_at.isoformat(),
            "size": "—"  # Could be enhanced to track session size
        })
    
    return result


def cleanup_old_sessions(db: Session, hours: int = 24):
    """Delete sessions older than specified hours"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    deleted = db.query(LoginSession).filter(
        LoginSession.last_used_at < cutoff
    ).delete()
    db.commit()
    return deleted


def force_logout_user(db: Session, user_id: int):
    db.query(LoginSession).filter(LoginSession.user_id == user_id).delete()
    db.commit()


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
    db.commit()


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


def list_ops_logs(db: Session, limit: int = 200):
    return (
        db.query(OpsLog)
        .order_by(OpsLog.created_at.desc())
        .limit(limit)
        .all()
    )
