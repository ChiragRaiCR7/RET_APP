from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import json
from pathlib import Path
import logging

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

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
AI_CONFIG_FILE = DATA_DIR / "ai_config.json"

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def write_audit_log(
    db: Session,
    username: str | None,
    action: str,
    area: str,
    message: str,
):
    """Write an entry to the audit log"""
    try:
        log = AuditLog(
            username=username,
            action=action,
            area=area,
            message=message,
            created_at=datetime.utcnow(),
        )
        db.add(log)
        # We don't commit here to allow the caller to commit in transaction
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

def write_ops_log(
    db: Session,
    username: str | None,
    action: str,
    area: str,
    message: str,
):
    """Write an entry to the ops log"""
    try:
        log = OpsLog(
            username=username,
            action=action,
            area=area,
            message=message,
            created_at=datetime.utcnow(),
        )
        db.add(log)
    except Exception as e:
        logger.error(f"Failed to write ops log: {e}")

def create_user(
    db: Session, 
    username: str, 
    password: str = None, 
    role: str = "user", 
    admin_username: str = None,
    token_ttl_minutes: int = 60,
):
    """
    Create new user with given credentials.
    Supports token-first onboarding when password is None.
    Returns (user, token) tuple where token is only provided for token-first onboarding.
    """
    if db.query(User).filter(User.username == username).first():
        raise Forbidden("User already exists")

    # For token-first onboarding, create user with placeholder password hash
    # User will set password via reset token
    if password:
        password_hash = hash_password(password)
    else:
        # Create a random placeholder that can't be used to log in
        password_hash = hash_password(secrets.token_urlsafe(32))

    user = User(
        username=username,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    db.flush()  # Get the user ID
    
    # For token-first onboarding, generate a reset token
    token = None
    if not password:
        token = secrets.token_urlsafe(32)
        token_hash = hash_password(token)
        expires_at = datetime.utcnow() + timedelta(minutes=token_ttl_minutes)
        
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(reset_token)
    
    write_audit_log(
        db, 
        username=admin_username, 
        action="CREATE_USER", 
        area="AUTH", 
        message=f"Created user {username} with role {role}" + (" (token-first)" if not password else "")
    )
    
    db.commit()
    db.refresh(user)
    return user, token


def update_user(db: Session, user_id: int, updates: dict, admin_username: str = None):
    """Update user fields"""
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")

    for k, v in updates.items():
        if v is not None and hasattr(user, k):
            setattr(user, k, v)

    write_audit_log(
        db, 
        username=admin_username, 
        action="UPDATE_USER", 
        area="AUTH", 
        message=f"Updated user {user.username}: {updates}"
    )

    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int):
    """Get user by ID"""
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")
    return user


def delete_user(db: Session, user_id: int, admin_username: str = None):
    """Delete user and all associated data"""
    user = db.query(User).get(user_id)
    if not user:
        raise NotFound("User not found")
    
    username = user.username
    
    # Delete sessions
    db.query(LoginSession).filter(LoginSession.user_id == user_id).delete()
    # Delete reset tokens
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    # Delete user
    db.delete(user)
    
    write_audit_log(
        db, 
        username=admin_username, 
        action="DELETE_USER", 
        area="AUTH", 
        message=f"Deleted user {username}"
    )
    
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


def update_user_role(db: Session, user_id: int, new_role: str, admin_username: str = None):
    """Update user role"""
    user = get_user(db, user_id)
    old_role = user.role
    user.role = new_role
    
    write_audit_log(
        db, 
        username=admin_username, 
        action="UPDATE_ROLE", 
        area="AUTH", 
        message=f"Changed role for {user.username} from {old_role} to {new_role}"
    )
    
    db.commit()
    db.refresh(user)
    return user


def unlock_user_account(db: Session, user_id: int, admin_username: str = None):
    """Unlock user account after failed login attempts"""
    user = get_user(db, user_id)
    user.is_locked = False
    
    write_audit_log(
        db, 
        username=admin_username, 
        action="UNLOCK_ACCOUNT", 
        area="AUTH", 
        message=f"Unlocked account for {user.username}"
    )
    
    db.commit()
    db.refresh(user)
    return user


def generate_reset_token(db: Session, user_id: int, admin_username: str = None):
    """Generate password reset token for user"""
    user = get_user(db, user_id)
    
    # Delete old unused tokens
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        ~PasswordResetToken.used
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

    # Mark latest pending reset request (if any) as approved
    pending_req = (
        db.query(PasswordResetRequest)
        .filter(
            PasswordResetRequest.username == user.username,
            PasswordResetRequest.status == "pending",
        )
        .order_by(PasswordResetRequest.created_at.desc())
        .first()
    )
    if pending_req:
        pending_req.status = "approved"
        pending_req.decided_at = datetime.utcnow()
    
    write_audit_log(
        db, 
        username=admin_username, 
        action="GENERATE_RESET_TOKEN", 
        area="AUTH", 
        message=f"Generated reset token for {user.username}"
    )
    
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


def cleanup_old_sessions(db: Session, hours: int = 24, admin_username: str = None):
    """Delete sessions older than specified hours"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    deleted = db.query(LoginSession).filter(
        LoginSession.last_used_at < cutoff
    ).delete()
    
    if deleted > 0 and admin_username:
        write_audit_log(
            db, 
            username=admin_username, 
            action="CLEANUP_SESSIONS", 
            area="CLEANUP", 
            message=f"Cleaned up {deleted} old sessions"
        )
    
    db.commit()
    return deleted


def force_logout_user(db: Session, user_id: int, admin_username: str = None):
    db.query(LoginSession).filter(LoginSession.user_id == user_id).delete()
    
    write_audit_log(
        db, 
        username=admin_username, 
        action="FORCE_LOGOUT", 
        area="AUTH", 
        message=f"Forced logout for user_id {user_id}"
    )
    
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

# ==========================================
# AI CONFIG PERSISTENCE
# ==========================================
def get_ai_indexing_config_data() -> dict:
    """Get AI indexing configuration"""
    defaults = {
        "auto_indexed_groups": [],
        "default_collection": "documents",
        "chunk_size": 10000,
        "retrieval_top_k": 16,
        "hybrid_alpha": 0.70,
        "hybrid_beta": 0.30,
        "max_zip_size_mb": 10000,
        "max_nested_depth": 50,
        "enable_auto_indexing": False,
    }
    
    if AI_CONFIG_FILE.exists():
        try:
            with open(AI_CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                # Merge with defaults to ensure new keys are present
                return {**defaults, **loaded}
        except Exception as e:
            logger.error(f"Failed to load AI config: {e}")
            return defaults
    return defaults

def save_ai_indexing_config_data(config: dict):
    """Save AI indexing configuration"""
    ensure_data_dir()
    try:
        current = get_ai_indexing_config_data()
        current.update(config)
        with open(AI_CONFIG_FILE, "w") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save AI config: {e}")
        return False

def get_user_by_username(db: Session, username: str):
    """Get user by username"""
    return db.query(User).filter(User.username == username).first()


