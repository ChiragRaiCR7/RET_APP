from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
import json
from pathlib import Path
import logging
from typing import Any, Dict, Optional, List

from sqlalchemy import delete, desc, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.models import (
    User,
    AuditLog,
    OpsLog,
    LoginSession,
    PasswordResetToken,
    PasswordResetRequest,
    RequestStatus,
)
from api.core.security import hash_password
from api.core.exceptions import NotFound, Forbidden

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
AI_CONFIG_FILE = DATA_DIR / "ai_config.json"

# Centralized role policy — extend here if roles evolve
_ALLOWED_ROLES = {"user", "admin", "super_admin", "guest"}


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return naive UTC timestamp for DB timestamp columns (SQL-friendly)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_data_dir() -> None:
    """Ensure `data/` directory exists for AI config persistence."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_role(role: Optional[str]) -> str:
    """Normalize role input to a valid, lower-cased role with a safe default."""
    if not role:
        return "user"
    r = role.strip().lower()
    return r if r in _ALLOWED_ROLES else "user"


def _normalize_group_list(values: Any) -> List[str]:
    """Normalize incoming list-like group values to uppercase, unique, sorted list."""
    if not isinstance(values, list):
        return []
    cleaned = {
        str(v).strip().upper()
        for v in values
        if str(v).strip()
    }
    return sorted(cleaned)


def _status_value(name: str, fallback: str) -> Any:
    """
    Safely resolve a RequestStatus attr if enum is used; fall back to raw string.

    e.g. _status_value("PENDING", "pending")
    """
    try:
        return getattr(RequestStatus, name)
    except Exception:
        return fallback


def _normalize_ai_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize AI indexing config:
    - Keep canonical flag `auto_embed_enabled`
    - Maintain legacy alias `enable_auto_embedding`
    - Clean list fields and preserve defaults
    """
    defaults = {
        "auto_embedded_groups": [],
        # legacy compatibility only (not used for eligibility policy)
        "excluded_groups": [],
        "default_collection": "documents",
        "chunk_size": 10000,
        "retrieval_top_k": 16,
        "hybrid_alpha": 0.70,
        "hybrid_beta": 0.30,
        "max_zip_size_mb": 10000,
        "max_nested_depth": 50,
        # canonical flag
        "auto_embed_enabled": False,
        # legacy alias maintained for older clients
        "enable_auto_embedding": False,
    }

    cfg = {**defaults, **(raw or {})}

    # Harmonize old/new flag names.
    source = raw or {}
    if "auto_embed_enabled" in source:
        enabled = bool(source.get("auto_embed_enabled"))
    elif "enable_auto_embedding" in source:
        enabled = bool(source.get("enable_auto_embedding"))
    else:
        enabled = bool(cfg.get("auto_embed_enabled") or cfg.get("enable_auto_embedding"))

    cfg["auto_embed_enabled"] = enabled
    cfg["enable_auto_embedding"] = enabled

    cfg["auto_embedded_groups"] = _normalize_group_list(cfg.get("auto_embedded_groups"))
    # Keep excluded_groups for backward-compatible payload roundtrips only.
    cfg["excluded_groups"] = _normalize_group_list(cfg.get("excluded_groups"))

    # A group cannot be both auto-embedded and excluded.
    if cfg["excluded_groups"]:
        excluded = set(cfg["excluded_groups"])
        cfg["auto_embedded_groups"] = [g for g in cfg["auto_embedded_groups"] if g not in excluded]

    return cfg


# ---------------------------------------------------------------------------
# Audit / Ops logs
# ---------------------------------------------------------------------------

def write_audit_log(
    db: AsyncSession,
    username: Optional[str],
    action: str,
    area: str,
    message: str,
) -> None:
    """Write an entry to the audit log (deferred commit)."""
    try:
        log = AuditLog(
            username=username,
            action=action,
            area=area,
            message=message,
            created_at=_utcnow(),
        )
        db.add(log)
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)


def write_ops_log(
    db: AsyncSession,
    username: Optional[str],
    action: str,
    area: str,
    message: str,
) -> None:
    """Write an entry to the ops log (deferred commit)."""
    try:
        log = OpsLog(
            username=username,
            action=action,
            area=area,
            message=message,
            created_at=_utcnow(),
        )
        db.add(log)
    except Exception as e:
        logger.error("Failed to write ops log: %s", e)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

async def create_user(
    db: AsyncSession,
    username: str,
    password: Optional[str] = None,
    role: str = "user",
    admin_username: Optional[str] = None,
    token_ttl_minutes: int = 60,
):
    """
    Create a new user.
    - If password is None, creates a placeholder password and issues a reset token
      (token-first onboarding).
    - Returns (user, token) where token is only provided for token-first onboarding.
    """
    # Uniqueness check
    res = await db.execute(select(User).where(User.username == username))
    if res.scalar_one_or_none():
        raise Forbidden("User already exists")

    norm_role = _normalize_role(role)

    # Compute password hash (placeholder if token-first)
    if password:
        password_hash = hash_password(password)
    else:
        password_hash = hash_password(secrets.token_urlsafe(32))

    user = User(
        username=username,
        password_hash=password_hash,
        role=norm_role,
    )
    db.add(user)

    try:
        await db.flush()  # allocate user.id

        token: Optional[str] = None
        if not password:
            # Token-first onboarding: generate token and persist its hash
            token = secrets.token_urlsafe(32)
            token_hash = hash_password(token)
            expires_at = _utcnow() + timedelta(minutes=token_ttl_minutes)
            db.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                )
            )

        write_audit_log(
            db,
            username=admin_username,
            action="CREATE_USER",
            area="AUTH",
            message=f"Created user {user.username} with role {norm_role}" + (" (token-first)" if not password else ""),
        )

        await db.commit()
        await db.refresh(user)
        return user, token
    except Exception:
        await db.rollback()
        logger.exception("Failed to create user '%s'", username)
        raise


async def update_user(
    db: AsyncSession,
    user_id: int,
    updates: dict,
    admin_username: Optional[str] = None
):
    """
    Update user attributes (only existing attributes will be applied).
    """
    user = await db.get(User, user_id)
    if not user:
        raise NotFound("User not found")

    try:
        # Normalize role via policy if included
        if "role" in updates and updates["role"] is not None:
            updates["role"] = _normalize_role(updates["role"])

        for k, v in updates.items():
            if v is not None and hasattr(user, k):
                setattr(user, k, v)

        write_audit_log(
            db,
            username=admin_username,
            action="UPDATE_USER",
            area="AUTH",
            message=f"Updated user {user.username}: {updates}",
        )

        await db.commit()
        await db.refresh(user)
        return user
    except Exception:
        await db.rollback()
        logger.exception("Failed to update user_id=%s", user_id)
        raise


async def get_user(db: AsyncSession, user_id: int):
    """Get user by ID or raise NotFound."""
    user = await db.get(User, user_id)
    if not user:
        raise NotFound("User not found")
    return user


async def delete_user(
    db: AsyncSession,
    user_id: int,
    admin_username: Optional[str] = None
) -> None:
    """
    Delete a user and associated sessions/tokens.
    """
    user = await db.get(User, user_id)
    if not user:
        raise NotFound("User not found")

    username = user.username

    try:
        # Delete sessions first
        await db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
        # Delete reset tokens
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
        # Delete user
        await db.delete(user)

        write_audit_log(
            db,
            username=admin_username,
            action="DELETE_USER",
            area="AUTH",
            message=f"Deleted user {username}",
        )

        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete user_id=%s", user_id)
        raise


async def list_users(db: AsyncSession) -> List[User]:
    """List all users ordered by creation timestamp (descending)."""
    res = await db.execute(select(User).order_by(desc(User.created_at)))
    return list(res.scalars().all())


async def get_admin_stats(db: AsyncSession) -> Dict[str, int]:
    """Return aggregate admin dashboard statistics."""
    total_users = int((await db.execute(select(func.count()).select_from(User))).scalar_one() or 0)
    admins = int(
        (await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin")
        )).scalar_one() or 0
    )
    regular = int(
        (await db.execute(
            select(func.count()).select_from(User).where(User.role == "user")
        )).scalar_one() or 0
    )
    active_sessions = int(
        (await db.execute(select(func.count()).select_from(LoginSession))).scalar_one() or 0
    )

    return {
        "totalUsers": total_users,
        "admins": admins,
        "regular": regular,
        "activeSessions": active_sessions,
    }


async def update_user_role(
    db: AsyncSession,
    user_id: int,
    new_role: str,
    admin_username: Optional[str] = None
):
    """Update only the role of a user; validates against allowed set."""
    user = await get_user(db, user_id)
    old_role = user.role
    norm_role = _normalize_role(new_role)
    if norm_role not in _ALLOWED_ROLES:
        raise ValueError(f"Invalid role: {new_role}")

    try:
        user.role = norm_role
        write_audit_log(
            db,
            username=admin_username,
            action="UPDATE_ROLE",
            area="AUTH",
            message=f"Changed role for {user.username} from {old_role} to {norm_role}",
        )
        await db.commit()
        await db.refresh(user)
        return user
    except Exception:
        await db.rollback()
        logger.exception("Failed to update role for user_id=%s", user_id)
        raise


async def unlock_user_account(
    db: AsyncSession,
    user_id: int,
    admin_username: Optional[str] = None
):
    """Unlock a user account after failed login attempts."""
    user = await get_user(db, user_id)

    try:
        user.is_locked = False
        write_audit_log(
            db,
            username=admin_username,
            action="UNLOCK_ACCOUNT",
            area="AUTH",
            message=f"Unlocked account for {user.username}",
        )
        await db.commit()
        await db.refresh(user)
        return user
    except Exception:
        await db.rollback()
        logger.exception("Failed to unlock account for user_id=%s", user_id)
        raise


async def generate_reset_token(
    db: AsyncSession,
    user_id: int,
    admin_username: Optional[str] = None
) -> str:
    """
    Generate a password reset token (valid for 24 hours), remove old unused ones,
    and approve latest pending reset request if it exists.
    """
    user = await get_user(db, user_id)

    try:
        # Delete old unused tokens
        await db.execute(
            delete(PasswordResetToken).where(
                and_(
                    PasswordResetToken.user_id == user_id,
                    PasswordResetToken.used.is_(False),
                )
            )
        )

        # Create new token (valid for 24 hours)
        token = secrets.token_urlsafe(32)
        token_hash = hash_password(token)
        expires_at = _utcnow() + timedelta(hours=24)

        db.add(
            PasswordResetToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )

        # Approve latest pending reset request (if any)
        pending_status = _status_value("PENDING", "pending")
        res = await db.execute(
            select(PasswordResetRequest)
            .where(
                and_(
                    PasswordResetRequest.username == user.username,
                    PasswordResetRequest.status == pending_status,
                )
            )
            .order_by(desc(PasswordResetRequest.created_at))
            .limit(1)
        )
        pending_req = res.scalar_one_or_none()
        if pending_req:
            approved = _status_value("APPROVED", "approved")
            pending_req.status = approved
            pending_req.decided_at = _utcnow()

        write_audit_log(
            db,
            username=admin_username,
            action="GENERATE_RESET_TOKEN",
            area="AUTH",
            message=f"Generated reset token for {user.username}",
        )

        await db.commit()
        # Return the unhashed token (only shown once)
        return token
    except Exception:
        await db.rollback()
        logger.exception("Failed to generate reset token for user_id=%s", user_id)
        raise


async def list_reset_requests(db: AsyncSession) -> List[PasswordResetRequest]:
    """List latest password reset requests (up to 100)."""
    res = await db.execute(
        select(PasswordResetRequest)
        .order_by(desc(PasswordResetRequest.created_at))
        .limit(100)
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

async def list_sessions(db: AsyncSession) -> List[Dict[str, str]]:
    """List all active sessions with user info (latest 200)."""
    res = await db.execute(
        select(LoginSession)
        .join(User)
        .options(selectinload(LoginSession.user))
        .order_by(desc(LoginSession.created_at))
        .limit(200)
    )
    sessions = list(res.scalars().all())

    result: List[Dict[str, str]] = []
    for session in sessions:
        result.append({
            "session_id": str(session.id),
            "username": session.user.username if session.user else "",
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "last_activity": session.last_used_at.isoformat() if session.last_used_at else "",
            "size": "—"  # Placeholder: hook for future metrics
        })
    return result


async def count_old_sessions(db: AsyncSession, hours: int = 24) -> int:
    """
    Count sessions older than the specified hours (dry run helper).
    Non-breaking addition to support 'dry-run' UX in the agent/UI.
    """
    cutoff = _utcnow() - timedelta(hours=hours)
    # SQLAlchemy Core count across a filtered selectable:
    res = await db.execute(
        select(func.count()).select_from(LoginSession).where(LoginSession.last_used_at < cutoff)
    )
    return int(res.scalar_one() or 0)


async def cleanup_old_sessions(
    db: AsyncSession,
    hours: int = 24,
    admin_username: Optional[str] = None
) -> int:
    """Delete sessions older than the specified hours. Returns number deleted."""
    cutoff = _utcnow() - timedelta(hours=hours)

    try:
        deleted_res = await db.execute(
            delete(LoginSession).where(LoginSession.last_used_at < cutoff)
        )
        # rowcount may not be present in stubs; guard defensively
        deleted = int(getattr(deleted_res, "rowcount", 0) or 0)

        if deleted > 0 and admin_username:
            write_audit_log(
                db,
                username=admin_username,
                action="CLEANUP_SESSIONS",
                area="CLEANUP",
                message=f"Cleaned up {deleted} old sessions (>{hours}h)",
            )

        await db.commit()
        return deleted
    except Exception:
        await db.rollback()
        logger.exception("Failed to cleanup old sessions (>%sh)", hours)
        raise


async def force_logout_user(
    db: AsyncSession,
    user_id: int,
    admin_username: Optional[str] = None
) -> None:
    """Force logout a specific user by deleting all their sessions."""
    try:
        await db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
        write_audit_log(
            db,
            username=admin_username,
            action="FORCE_LOGOUT",
            area="AUTH",
            message=f"Forced logout for user_id {user_id}",
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to force logout for user_id=%s", user_id)
        raise


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

async def list_audit_logs(db: AsyncSession, limit: int = 200) -> List[AuditLog]:
    """List latest audit logs."""
    res = await db.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit))
    return list(res.scalars().all())


async def list_ops_logs(db: AsyncSession, limit: int = 200) -> List[OpsLog]:
    """List latest operational logs."""
    res = await db.execute(select(OpsLog).order_by(desc(OpsLog.created_at)).limit(limit))
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# AI CONFIG PERSISTENCE
# ---------------------------------------------------------------------------

def get_ai_indexing_config_data() -> dict:
    """Load AI indexing configuration (normalized)."""
    if AI_CONFIG_FILE.exists():
        try:
            with open(AI_CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                return _normalize_ai_config(loaded)
        except Exception as e:
            logger.error("Failed to load AI config: %s", e)
            return _normalize_ai_config({})
    return _normalize_ai_config({})


def save_ai_indexing_config_data(config: dict) -> bool:
    """
    Save AI indexing configuration with alias preservation rules.
    - Merges incoming payload into current file
    - Maintains both canonical and legacy flags consistently
    """
    ensure_data_dir()
    try:
        incoming = config or {}
        current = get_ai_indexing_config_data()
        current.update(incoming)

        # Preserve backward-compatible updates when only one flag alias is sent.
        if "auto_embed_enabled" not in incoming and "enable_auto_embedding" in incoming:
            current.pop("auto_embed_enabled", None)
        if "enable_auto_embedding" not in incoming and "auto_embed_enabled" in incoming:
            current.pop("enable_auto_embedding", None)

        current = _normalize_ai_config(current)
        with open(AI_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save AI config: %s", e)
        return False


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Get user by username (exact match), or None."""
    res = await db.execute(select(User).where(User.username == username))
    return res.scalar_one_or_none()