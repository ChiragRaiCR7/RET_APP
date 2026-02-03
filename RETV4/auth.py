# auth.py
# ----------------------------------------------------------------------------- (same header)
from __future__ import annotations

import os
import re
import json
import time
import secrets
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, cast

import bcrypt
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

# Import from modular architecture
from db import (
    engine,
    get_session,
    init_db as _db_init,
    write_ops_log,
    write_error_event,
)
from models import (
    User,
    ResetToken,
    ResetRequest,
    UserLimit,
    LimitRequest,
    AuditLog,
    LoginSession,
)
from constants import (
    RET_ENV,
    TOKEN_EXPIRY_SECONDS,
    MAX_FAILED_ATTEMPTS,
    LOCKOUT_SECONDS,
    ALLOWED_ROLES,
    TOKEN_PEPPER,
    ADMIN_ZIP_UPLOAD_MB,
    ADMIN_DEPTH_LIMIT,
    ADMIN_MAX_FILES,
    ADMIN_MAX_TOTAL_MB,
    ADMIN_MAX_PER_FILE_MB,
    DEFAULT_LIMITS,
    USERNAME_RE,
    RET_RUNTIME_ROOT,
    RET_SESS_ROOT,
)
from utils import (
    normalize_username as _normalize_username,
    hash_session_token as _hash_session_token,
    now_epoch as _now,
)
from security import (
    is_under as _is_under,
    safe_delete_dir_allowlisted as _safe_delete_dir,
    sanitize_log_str as _sanitize_log_str,
    sanitize_details as _sanitize_details,
)
from session_management import (
    register_session,
    touch_session,
    mark_session_status,
)

# ---------------------------------------------------------------------
# Configuration is now imported from constants.py

_USERNAME_RE = USERNAME_RE  # Alias for backwards compatibility


# ---------------------------------------------------------------------
# Safe filesystem allowlist for deletions (prevents arbitrary delete)
# ---------------------------------------------------------------------
RET_RUNTIME_ROOT = Path(os.environ.get("RET_RUNTIME_ROOT", str(Path.cwd() / "ret_runtime"))).resolve()
RET_SESS_ROOT = (RET_RUNTIME_ROOT / "sessions").resolve()


def _is_under(child: Path, parent: Path) -> bool:
    """True if 'child' resolves under 'parent' directory."""
    try:
        child = child.resolve()
        parent = parent.resolve()
        return str(child).startswith(str(parent) + os.sep)
    except Exception:
        return False


# ---------------------------------------------------------------------
# Logging sanitization helpers (prevents log injection + sensitive leakage)
# ---------------------------------------------------------------------
_SENSITIVE_KEYS = {"token", "authorization", "api_key", "password", "secret", "cookie", "session", "bearer"}


def _sanitize_log_str(s: Optional[str], max_len: int = 2000) -> Optional[str]:
    """Neutralize CR/LF and cap length."""
    if s is None:
        return None
    s2 = str(s).replace("\r", "\\r").replace("\n", "\\n")
    return s2[:max_len]


def _sanitize_details(details: Optional[Dict[str, Any]], max_items: int = 80) -> Optional[Dict[str, Any]]:
    """Redact sensitive keys and cap values to keep payload bounded."""
    if not isinstance(details, dict):
        return None
    out: Dict[str, Any] = {}
    for i, (k, v) in enumerate(details.items()):
        if i >= max_items:
            out["_truncated"] = True
            break
        key = str(k)
        if key.lower() in _SENSITIVE_KEYS:
            out[key] = "[REDACTED]"
        else:
            out[key] = _sanitize_log_str(str(v), 500)
    return out


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def _now() -> int:
    return int(time.time())


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_username(username: str) -> bool:
    return bool(_USERNAME_RE.match(_normalize_username(username)))


def validate_password(password: str) -> bool:
    """
    Password policy:
      - >= 8 chars
      - 1 uppercase, 1 lowercase, 1 digit, 1 special char
    """
    if len(password or "") < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    # keep the special chars set as you had (unescaped in real source)
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True


def _hash_session_token(token: str) -> str:
    """
    Hash a login session token using HMAC-SHA256 + server-side pepper.
    Stored in LoginSession.token_hash.
    """
    tok = (token or "").strip()
    pepper = TOKEN_PEPPER or "default-pepper"
    return hmac.new(pepper.encode("utf-8"), tok.encode("utf-8"), hashlib.sha256).hexdigest()


def _safe_delete_dir(p: Optional[str]) -> bool:
    """
    ✅ Allowlisted deletion: only delete under RET_SESS_ROOT.
    Prevents arbitrary directory deletion if path in DB is wrong/malicious.
    """
    try:
        if not p:
            return True
        target = Path(p).resolve()

        # Allowlist enforcement
        if not _is_under(target, RET_SESS_ROOT):
            return False

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return True
    except Exception:
        return False


def _require_admin(db: Session, admin_username: str) -> str:
    """Ensure caller is admin."""
    admin_uname = _normalize_username(admin_username)
    admin_obj = db.execute(select(User).where(User.username == admin_uname)).scalar_one_or_none()
    if not admin_obj or str(cast(Any, admin_obj).role).lower() != "admin":
        raise ValueError("Admin privileges required.")
    return admin_uname


# ---------------------------------------------------------------------
# Initialization & housekeeping
# ---------------------------------------------------------------------
def init_db() -> None:
    """
    Create all tables and (DEV-ONLY) apply minimal compatibility adjustments.

    ✅ Fix: runtime DDL “migrations-lite” are disabled in production.
    For prod, use Alembic or pre-migrated DB.
    """
    _db_init()

    # PROD: skip runtime DDL modifications
    if RET_ENV in ("prod", "production"):
        prune_expired_tokens()
        return
    # DEV-only compatibility adjustments
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL"))
        except Exception:
            pass

        try:
            conn.execute(text("ALTER TABLE user_limits ADD COLUMN IF NOT EXISTS zip_upload_mb INTEGER DEFAULT 1000"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE limit_requests ADD COLUMN IF NOT EXISTS requested_zip_upload_mb INTEGER"))
        except Exception:
            pass

        try:
            conn.execute(text("ALTER TABLE login_sessions RENAME COLUMN token TO token_hash"))
        except Exception:
            pass

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_reset_tokens_expires_at ON reset_tokens(expires_at)"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_login_sessions_expires_at ON login_sessions(expires_at)"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_reset_requests_status ON reset_requests(status)"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_limit_requests_status ON limit_requests(status)"))
        except Exception:
            pass

    prune_expired_tokens()


def prune_expired_tokens() -> None:
    """Remove expired reset tokens and expired login sessions."""
    now = _now()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM reset_tokens WHERE expires_at < :now"), {"now": now})
        conn.execute(text("DELETE FROM login_sessions WHERE expires_at < :now"), {"now": now})


# ---------------------------------------------------------------------
# Operational logs + Audit logs
# ---------------------------------------------------------------------
def ops(
    *,

    level: str = "INFO",
    action: str = "event",
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    corr_id: Optional[str] = None,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    area: str = "AUTH",
) -> None:
    """
    Convenience wrapper for Postgres-backed operational logging.

    ✅ Fix: sanitize message/details (avoid CR/LF injection, cap size, redact secrets).
    """
    try:
        write_ops_log(
            level=(level or "INFO"),
            area=(area or "AUTH"),
            action=(action or "event"),
            username=_normalize_username(username) if username else None,
            session_id=session_id,
            corr_id=corr_id,
            message=_sanitize_log_str(message, 1000),
            details=_sanitize_details(details),
        )
    except Exception:
        # Never break auth flow due to logging failures
        pass


def log_admin_action(
    db: Session,
    admin_username: str,
    action: str,
    target_username: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Admin audit trail record."""
    entry = AuditLog(
        admin_username=_normalize_username(admin_username or "admin"),
        action=action,
        target_username=_normalize_username(target_username) if target_username else None,
        details=json.dumps(details or {}, ensure_ascii=False)[:50_000],
        created_at=_now(),
    )
    db.add(entry)


def list_audit_logs(limit: int = 5000) -> List[Dict]:
    with get_session() as db:
        rows = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars().all()
        out = []
        for r in rows:
            r = cast(Any, r)
            out.append(
                {
                    "id": r.id,
                    "admin_username": r.admin_username,
                    "action": r.action,
                    "target_username": r.target_username,
                    "details": r.details,
                    "created_at": r.created_at,
                }
            )
        return out


def list_ops_logs(limit: int = 500, area: Optional[str] = None) -> List[Dict]:
    """Admin page uses this to show operational logs."""
    from models import OpsLog  # local import to avoid cycles

    with get_session() as db:
        stmt = select(OpsLog)
        if area:
            stmt = stmt.where(OpsLog.area == area)
        rows = db.execute(stmt.order_by(OpsLog.created_at.desc()).limit(limit)).scalars().all()
        out = []
        for r in rows:
            r = cast(Any, r)
            out.append(
                {
                    "id": int(r.id),
                    "created_at": int(r.created_at),
                    "level": r.level,
                    "area": r.area,
                    "action": r.action,
                    "username": r.username,
                    "session_id": r.session_id,
                    "corr_id": r.corr_id,
                    "message": r.message,
                    "details_json": r.details_json,
                }
            )
        return out


# ---------------------------------------------------------------------
# Session registry (Postgres app_sessions)
# ---------------------------------------------------------------------
def register_or_touch_session(
    *,
    session_id: str,
    username: Optional[str],
    temp_dir: Optional[str] = None,
    log_path: Optional[str] = None,
    status: str = "ACTIVE",
) -> None:
    """Insert/Update app_sessions record."""
    try:
        upsert_app_session(
            session_id=session_id,
            username=_normalize_username(username) if username else None,
            temp_dir=temp_dir,
            log_path=log_path,
            status=status,
        )
    except Exception:
        pass


def touch_session(session_id: str) -> None:
    try:
        touch_app_session(session_id=session_id)
    except Exception:
        pass


def mark_session(session_id: str, status: str) -> None:
    try:
        mark_app_session(session_id=session_id, status=status)
    except Exception:
        pass


# ---------------------------------------------------------------------
# Persistent login sessions (token in cookie; hash in DB)
# ---------------------------------------------------------------------
def create_login_session(username: str, ttl_seconds: int = TOKEN_EXPIRY_SECONDS) -> str:
    uname = _normalize_username(username)
    with get_session() as db:
        u = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not u:
            raise ValueError("User not found")

        u = cast(Any, u)

        token_plain = secrets.token_urlsafe(32)
        token_db = _hash_session_token(token_plain)
        exp = _now() + int(ttl_seconds)

        db.add(LoginSession(token_hash=token_db, username=uname, created_at=_now(), expires_at=exp))
        db.commit()

        ops(action="create_login_session", username=uname, message="Login session created", details={"ttl": int(ttl_seconds)})
        return token_plain


def get_login_session(token: str) -> Optional[Tuple[int, str, str]]:
    """Validate cookie token -> user tuple (id, username, role)."""
    if not token:
        return None
    token_db = _hash_session_token(token)

    with get_session() as db:
        ls = db.execute(select(LoginSession).where(LoginSession.token_hash == token_db)).scalar_one_or_none()
        if not ls or int(cast(Any, ls).expires_at) <= _now():
            return None

        ls = cast(Any, ls)

        u = db.execute(select(User).where(User.username == ls.username)).scalar_one_or_none()
        if not u:
            return None
        u = cast(Any, u)

        return (int(u.id), str(u.username), str(u.role))


def clear_login_session(token: str) -> None:
    """Remove LoginSession row matching token hash."""
    if not token:
        return
    token_db = _hash_session_token(token)
    with get_session() as db:
        ls = db.execute(select(LoginSession).where(LoginSession.token_hash == token_db)).scalar_one_or_none()
        if ls:
            ls = cast(Any, ls)
            db.delete(ls)
            db.commit()
            ops(action="clear_login_session", username=ls.username, message="Login session cleared")
# ---------------------------------------------------------------------
# Logout cleanup (centralized)
# ---------------------------------------------------------------------
def logout_cleanup(
    *,
    cookie_token: Optional[str],
    session_id: Optional[str],
    username: Optional[str],
    temp_dir: Optional[str] = None,
    reason: str = "LOGOUT",
    chroma_collection_name: Optional[str] = None,
    chroma_parent_dir: Optional[str] = None,
) -> None:
    """
    Central cleanup called by UI pages on logout.
    ✅ Uses allowlisted deletion (_safe_delete_dir).
    """
    uname = _normalize_username(username) if username else None
    sid = (session_id or "").strip() or None

    try:
        if cookie_token:
            clear_login_session(cookie_token)
    except Exception as e:
        ops(level="WARN", action="logout_revoke_failed", username=uname, session_id=sid, message=str(e))

    try:
        if sid:
            mark_session(sid, reason)
    except Exception as e:
        ops(level="WARN", action="logout_mark_session_failed", username=uname, session_id=sid, message=str(e))

    deleted_temp = False
    try:
        if temp_dir:
            deleted_temp = _safe_delete_dir(temp_dir)
    except Exception:
        deleted_temp = False

    deleted_chroma = False
    try:
        if chroma_parent_dir:
            deleted_chroma = _safe_delete_dir(chroma_parent_dir)
    except Exception:
        deleted_chroma = False

    ops(
        action="logout_cleanup",
        username=uname,
        session_id=sid,
        message="Logout cleanup completed",
        details={
            "reason": reason,
            "temp_dir_deleted": bool(deleted_temp),
            "chroma_dir_deleted": bool(deleted_chroma),
            "chroma_collection_name": chroma_collection_name,
        },
    )


# ---------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------
def get_user(username: str, include_password_hash: bool = False) -> Optional[Dict]:
    uname = _normalize_username(username)
    with get_session() as db:
        obj = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not obj:
            return None

        obj = cast(Any, obj)

        data = {
            "id": int(obj.id),
            "username": str(obj.username),
            "role": str(obj.role),
            "failed_attempts": int(obj.failed_attempts or 0),
            "locked_until": int(obj.locked_until or 0),
            "must_reset": 1 if bool(obj.must_reset) else 0,
            "password_changed_at": int(obj.password_changed_at) if getattr(obj, "password_changed_at", None) is not None else None,
            "created_at": int(obj.created_at),
        }
        if include_password_hash:
            data["password_hash"] = obj.password_hash
        return data


def list_users() -> List[Dict]:
    with get_session() as db:
        rows = db.execute(select(User).order_by(User.username)).scalars().all()
        out: List[Dict] = []
        for r in rows:
            r = cast(Any, r)
            out.append(
                {
                    "id": int(r.id),
                    "username": str(r.username),
                    "role": str(r.role),
                    "created_at": int(r.created_at),
                    "failed_attempts": int(r.failed_attempts or 0),
                    "locked_until": int(r.locked_until or 0),
                    "must_reset": 1 if bool(r.must_reset) else 0,
                    "password_changed_at": int(r.password_changed_at) if getattr(r, "password_changed_at", None) is not None else None,
                    "has_password": 1 if (getattr(r, "password_hash", None) is not None and str(getattr(r, "password_hash", "")).strip() != "") else 0,
                }
            )
        return out


def count_admins() -> int:
    with get_session() as db:
        return db.execute(select(func.count()).select_from(User).where(User.role == "admin")).scalar_one()


def requires_password_reset(username: str) -> bool:
    u = get_user(username)
    return bool(u and u.get("must_reset") == 1)


def set_must_reset(username: str, flag: bool = True, admin_username: Optional[str] = None) -> bool:
    uname = _normalize_username(username)
    with get_session() as db:
        if admin_username:
            _require_admin(db, admin_username)

        obj = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not obj:
            return False

        db_obj = cast(Any, obj)
        db_obj.must_reset = bool(flag)
        db.add(db_obj)

        if admin_username:
            log_admin_action(db, admin_username, "set_must_reset", uname, {"must_reset": bool(flag)})

        db.commit()
        return True


# ---------------------------------------------------------------------
# Auth (login verification)
# ---------------------------------------------------------------------
def verify_user(username: str, password: str) -> Optional[Tuple[int, str, str]]:
    """
    Validate username/password with lockout policy.
    ✅ Fix: reduce user enumeration by avoiding distinct raised messages
            for "no password" / "locked" states.
    Return:
      - (id, username, role) on success
      - None on any failure
    """
    uname = _normalize_username(username)

    with get_session() as db:
        obj = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not obj:
            # Do not reveal whether user exists (caller should show generic error)
            ops(level="WARN", action="login_failed_unknown_user", username=uname, message="Login failed")
            return None

        obj = cast(Any, obj)

        # If password not set, do not raise detailed user-facing error
        if not bool(getattr(obj, "password_hash", None)):
            ops(level="WARN", action="login_blocked_no_password", username=uname, message="Password not set")
            return None

        current_time = _now()

        # auto-unlock if lock expired
        if int(getattr(obj, "locked_until", 0) or 0) > 0 and int(getattr(obj, "locked_until", 0)) <= current_time:
            obj.failed_attempts = 0
            obj.locked_until = 0
            db.add(obj)
            db.commit()

        # locked
        if int(getattr(obj, "locked_until", 0) or 0) > current_time:
            ops(level="WARN", action="login_blocked_locked", username=uname, message="Account locked")
            return None

        ok = False
        try:
            ok = bcrypt.checkpw(password.encode("utf-8"), str(getattr(obj, "password_hash", "")).encode("utf-8"))
        except Exception:
            ok = False

        if ok:
            obj.failed_attempts = 0
            obj.locked_until = 0
            db.add(obj)
            db.commit()
            ops(action="login_success", username=uname, message="User login succeeded")
            return (int(obj.id), str(obj.username), str(obj.role))

        # wrong password
        obj.failed_attempts = int(getattr(obj, "failed_attempts", 0) or 0) + 1
        if int(getattr(obj, "failed_attempts", 0)) >= MAX_FAILED_ATTEMPTS:
            obj.locked_until = current_time + LOCKOUT_SECONDS
        db.add(obj)
        db.commit()

        ops(
            level="WARN",
            action="login_failed",
            username=uname,
            message="Invalid password",
            details={"failed_attempts": int(getattr(obj, "failed_attempts", 0)), "locked_until": int(getattr(obj, "locked_until", 0) or 0)},
        )
        return None

# ---------------------------------------------------------------------
# Admin user management
# ---------------------------------------------------------------------
def create_user(
    username: str,
    role: str = "user",
    password: Optional[str] = None,
    admin_username: Optional[str] = None,
) -> int:
    uname = _normalize_username(username)
    role_norm = (role or "").strip().lower()

    if not validate_username(uname):
        raise ValueError("Invalid username format. Use 3–64 chars: a-z, 0-9, ., _, -")
    if role_norm not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role '{role}'.")

    with get_session() as db:
        if admin_username:
            _require_admin(db, admin_username)

        exists = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if exists:
            raise ValueError(f"User '{uname}' already exists")

        if password is None:
            obj = User(username=uname, password_hash=None, role=role_norm, must_reset=True, created_at=_now())
        else:
            if not validate_password(password):
                raise ValueError("Password does not meet security requirements")
            pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            obj = User(username=uname, password_hash=pw_hash, role=role_norm, must_reset=True, created_at=_now())

        db.add(obj)
        if admin_username:
            log_admin_action(db, admin_username, "create_user", uname, {"role": role_norm, "token_first": password is None})
        db.commit()

        ops(action="create_user", username=uname, message="User created", details={"role": role_norm, "token_first": password is None})
        return int(cast(Any, obj).id)


def delete_user(username: str, admin_username: Optional[str] = None) -> bool:
    uname = _normalize_username(username)
    with get_session() as db:
        if admin_username:
            admin_uname = _require_admin(db, admin_username)
            if uname == admin_uname:
                raise ValueError("You cannot delete your own account.")

        obj = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not obj:
            return False

        obj = cast(Any, obj)

        if str(obj.role).lower() == "admin":
            num_admins = db.execute(select(func.count()).select_from(User).where(User.role == "admin")).scalar_one()
            if int(num_admins) <= 1:
                raise ValueError("Cannot delete the last remaining admin.")

        db.delete(obj)
        if admin_username:
            log_admin_action(db, admin_username, "delete_user", uname)
        db.commit()

        ops(action="delete_user", username=uname, message="User deleted")
        return True


def update_user_role(username: str, new_role: str, admin_username: Optional[str] = None) -> bool:
    uname = _normalize_username(username)
    role_norm = (new_role or "").strip().lower()
    if role_norm not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role '{new_role}'.")

    with get_session() as db:
        if not admin_username:
            raise ValueError("Admin username required")
        _require_admin(db, admin_username)

        obj = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not obj:
            return False

        obj = cast(Any, obj)

        is_admin = str(obj.role).lower() == "admin"
        if is_admin and role_norm != "admin":
            num_admins = db.execute(select(func.count()).select_from(User).where(User.role == "admin")).scalar_one()
            if int(num_admins) <= 1:
                raise ValueError("Cannot demote the last remaining admin.")

        obj.role = role_norm
        db.add(obj)

        log_admin_action(db, admin_username, "update_role", uname, {"new_role": role_norm})
        db.commit()

        ops(action="update_user_role", username=uname, message="Role updated", details={"new_role": role_norm})
        return True


def unlock_user(username: str, admin_username: Optional[str] = None) -> bool:
    uname = _normalize_username(username)
    with get_session() as db:
        if admin_username:
            _require_admin(db, admin_username)

        obj = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not obj:
            return False

        obj = cast(Any, obj)
        obj.failed_attempts = 0
        obj.locked_until = 0
        db.add(obj)

        if admin_username:
            log_admin_action(db, admin_username, "unlock_user", uname)
        db.commit()

        ops(action="unlock_user", username=uname, message="User unlocked")
        return True


# ---------------------------------------------------------------------
# Reset tokens (HASH-ONLY; no plaintext stored)
# ---------------------------------------------------------------------
def _insert_token_row(db: Session, uname: str, token_plain: str, ttl: Optional[int] = None) -> None:
    old = db.execute(select(ResetToken).where(ResetToken.username == uname)).scalar_one_or_none()
    if old:
        db.delete(old)

    token_hash = bcrypt.hashpw(token_plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expires_at = _now() + (int(ttl) if ttl is not None else TOKEN_EXPIRY_SECONDS)

    db.add(
        ResetToken(
            username=uname,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=_now(),
            used_at=None,
        )
    )


def generate_reset_token(username: str, ttl: Optional[int] = None) -> Optional[str]:
    uname = _normalize_username(username)
    with get_session() as db:
        u = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not u:
            return None
        tok = secrets.token_urlsafe(32)
        _insert_token_row(db, uname, tok, ttl=ttl)
        db.commit()
        ops(action="generate_reset_token", username=uname, message="Reset token generated (self)")
        return tok


def admin_generate_reset_token_for_user(
    username: str,
    admin_username: str,
    ttl_seconds: int = TOKEN_EXPIRY_SECONDS,
    note: str = "",
) -> Optional[str]:
    uname = _normalize_username(username)
    with get_session() as db:
        admin_uname = _require_admin(db, admin_username)

        u = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not u:
            return None
        u = cast(Any, u)

        tok = secrets.token_urlsafe(32)
        _insert_token_row(db, uname, tok, ttl=int(ttl_seconds))

        u.must_reset = True
        db.add(u)

        log_admin_action(
            db,
            admin_uname,
            "admin_generate_reset_token_for_user",
            uname,
            {"ttl_seconds": int(ttl_seconds), "note": (note or "")[:500]},
        )
        db.commit()

        ops(action="admin_generate_reset_token_for_user", username=uname, message="Admin issued reset token", details={"ttl": int(ttl_seconds)})
        return tok

def verify_reset_token(username: str, token: str) -> bool:
    uname = _normalize_username(username)
    token = (token or "").strip()
    if not token:
        return False
    with get_session() as db:
        rt = db.execute(select(ResetToken).where(ResetToken.username == uname)).scalar_one_or_none()
        if not rt:
            return False
        rt = cast(Any, rt)
        if int(getattr(rt, "expires_at", 0)) <= _now():
            return False
        if getattr(rt, "used_at", None):
            return False
        return bcrypt.checkpw(token.encode("utf-8"), str(getattr(rt, "token_hash", "")).encode("utf-8"))


def reset_password(username: str, new_password: str, token: str) -> bool:
    ok, _ = reset_password_verbose(username, new_password, token)
    return ok


def reset_password_verbose(username: str, new_password: str, token: str) -> tuple[bool, str]:
    uname = _normalize_username(username)
    token = (token or "").strip()
    if not validate_password(new_password):
        return False, "policy"
    if not token:
        return False, "token_missing"

    with get_session() as db:
        rt = db.execute(select(ResetToken).where(ResetToken.username == uname)).scalar_one_or_none()
        if not rt:
            return False, "no_token_row"
        rt = cast(Any, rt)
        if int(getattr(rt, "expires_at", 0)) <= _now():
            return False, "expired"
        if getattr(rt, "used_at", None):
            return False, "used"
        if not bcrypt.checkpw(token.encode("utf-8"), str(getattr(rt, "token_hash", "")).encode("utf-8")):
            return False, "token_mismatch"

        u = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not u:
            return False, "user_missing"
        u = cast(Any, u)

        pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        u.password_hash = pw_hash
        u.must_reset = False
        u.password_changed_at = _now()
        u.failed_attempts = 0
        u.locked_until = 0
        db.add(u)

        rt.used_at = _now()
        db.add(rt)

        db.commit()

        ops(action="reset_password", username=uname, message="Password reset completed")
        return True, "ok"


def check_reset_token_status(username: str) -> Dict[str, Any]:
    uname = _normalize_username(username)
    with get_session() as db:
        rt = db.execute(select(ResetToken).where(ResetToken.username == uname)).scalar_one_or_none()
        if not rt:
            return {"exists": False, "status": "missing"}
        rt = cast(Any, rt)
        now = _now()
        remaining = max(0, int(getattr(rt, "expires_at", 0) or 0) - now)
        return {
            "exists": True,
            "expired": int(getattr(rt, "expires_at", 0) or 0) <= now,
            "used": bool(getattr(rt, "used_at", None)),
            "remaining_secs": remaining,
            "plaintext_available": False,
        }


# ---------------------------------------------------------------------
# Reset Requests workflow
# ---------------------------------------------------------------------
def create_reset_request(username: str, note: str = "") -> int:
    uname = _normalize_username(username)
    with get_session() as db:
        user = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not user:
            raise ValueError("User not found")
        req = ResetRequest(username=uname, note=note or "", status="pending", requested_at=_now())
        db.add(req)
        db.commit()
        ops(action="create_reset_request", username=uname, message="Reset request created")
        return int(cast(Any, req).id)


def list_reset_requests(status: Optional[str] = None) -> List[Dict]:
    with get_session() as db:
        stmt = select(ResetRequest)
        if status:
            stmt = stmt.where(ResetRequest.status == status)
        rows = db.execute(stmt.order_by(ResetRequest.requested_at.desc())).scalars().all()
        out: List[Dict] = []
        for r in rows:
            r = cast(Any, r)
            out.append(
                {
                    "id": int(r.id),
                    "username": str(r.username),
                    "status": str(r.status),
                    "note": r.note,
                    "requested_at": int(r.requested_at),
                    "actioned_at": int(r.actioned_at) if getattr(r, "actioned_at", None) else None,
                    "action_by": r.action_by,
                }
            )
        return out


def set_reset_request_status(request_id: int, status: str, admin_username: str, note: str = "") -> bool:
    status_norm = (status or "").strip().lower()
    if status_norm not in {"pending", "approved", "rejected"}:
        raise ValueError("Invalid status")

    with get_session() as db:
        admin_uname = _require_admin(db, admin_username)
        r = db.get(ResetRequest, request_id)
        if not r:
            return False

        r = cast(Any, r)
        r.status = status_norm
        r.actioned_at = _now()
        r.action_by = admin_uname
        if note:
            r.note = note

        db.add(r)
        log_admin_action(db, admin_uname, "set_reset_request_status", r.username, {"status": status_norm, "request_id": request_id})
        db.commit()

        ops(action="set_reset_request_status", username=r.username, message="Reset request status updated",
            details={"request_id": request_id, "status": status_norm})
        return True


def admin_generate_token_for_request(request_id: int, admin_username: str, ttl: Optional[int] = None) -> Optional[str]:
    with get_session() as db:
        admin_uname = _require_admin(db, admin_username)
        r = db.get(ResetRequest, request_id)
        if not r or str(cast(Any, r).status).lower() != "pending":
            return None

        r = cast(Any, r)
        uname = _normalize_username(r.username)
        u = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not u:
            return None
        u = cast(Any, u)

        tok = secrets.token_urlsafe(32)
        _insert_token_row(db, uname, tok, ttl=ttl)

        r.status = "approved"
        r.actioned_at = _now()
        r.action_by = admin_uname
        db.add(r)

        u.must_reset = True
        db.add(u)

        log_admin_action(db, admin_uname, "admin_generate_token_for_request", uname, {"request_id": request_id})
        db.commit()

        ops(action="admin_generate_token_for_request", username=uname, message="Token generated for reset request",
            details={"request_id": request_id})
        return tok


# ---------------------------------------------------------------------
# Limits + Effective limits
# ---------------------------------------------------------------------
def get_user_limits(username: str) -> Optional[Dict]:
    uname = _normalize_username(username)
    with get_session() as db:
        row = db.execute(select(UserLimit).where(UserLimit.username == uname)).scalar_one_or_none()
        if not row:
            return None
        row = cast(Any, row)
        return {
            "username": uname,
            "zip_upload_mb": int(getattr(row, "zip_upload_mb", 1000) or 1000),
            "depth_limit": int(getattr(row, "depth_limit", DEFAULT_LIMITS["depth_limit"])),
            "max_files": int(getattr(row, "max_files", DEFAULT_LIMITS["max_files"])),
            "max_total_mb": int(getattr(row, "max_total_mb", DEFAULT_LIMITS["max_total_mb"])),
            "max_per_file_mb": int(getattr(row, "max_per_file_mb", DEFAULT_LIMITS["max_per_file_mb"])),
            "updated_at": int(getattr(row, "updated_at", _now())),
        }


def get_effective_user_limits(username: str) -> Dict:
    uname = _normalize_username(username)
    with get_session() as db:
        u = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not u:
            return {}
        u = cast(Any, u)
        if str(u.role).lower() == "admin":
            return {
                "username": uname,
                "zip_upload_mb": ADMIN_ZIP_UPLOAD_MB,
                "depth_limit": ADMIN_DEPTH_LIMIT,
                "max_files": ADMIN_MAX_FILES,
                "max_total_mb": ADMIN_MAX_TOTAL_MB,
                "max_per_file_mb": ADMIN_MAX_PER_FILE_MB,
                "updated_at": _now(),
                "source": "role_override_admin",
            }

    stored = get_user_limits(uname)
    if stored:
        stored["source"] = "user_override"
        return stored

    return {"username": uname, **DEFAULT_LIMITS, "updated_at": _now(), "source": "defaults"}

def set_user_limits(
    username: str,
    zip_upload_mb: int,
    depth_limit: int,
    max_files: int,
    max_total_mb: int,
    max_per_file_mb: int,
    admin_username: Optional[str] = None,
    ) -> bool:
    uname = _normalize_username(username)
    with get_session() as db:
        if not admin_username:
            raise ValueError("Admin username required to set limits.")
        admin_uname = _require_admin(db, admin_username)

        existing = db.execute(select(UserLimit).where(UserLimit.username == uname)).scalar_one_or_none()
        if existing:
            existing = cast(Any, existing)
            existing.zip_upload_mb = int(zip_upload_mb)
            existing.depth_limit = int(depth_limit)
            existing.max_files = int(max_files)
            existing.max_total_mb = int(max_total_mb)
            existing.max_per_file_mb = int(max_per_file_mb)
            existing.updated_at = _now()
            db.add(existing)
        else:
            db.add(
                UserLimit(
                    username=uname,
                    zip_upload_mb=int(zip_upload_mb),
                    depth_limit=int(depth_limit),
                    max_files=int(max_files),
                    max_total_mb=int(max_total_mb),
                    max_per_file_mb=int(max_per_file_mb),
                    updated_at=_now(),
                )
            )

        log_admin_action(
            db,
            admin_uname,
            "set_user_limits",
            uname,
            {
                "zip_upload_mb": int(zip_upload_mb),
                "depth_limit": int(depth_limit),
                "max_files": int(max_files),
                "max_total_mb": int(max_total_mb),
                "max_per_file_mb": int(max_per_file_mb),
            },
        )
        db.commit()

        ops(action="set_user_limits", username=uname, message="User limits updated")
        return True


# ---------------------------------------------------------------------
# Limit Requests
# ---------------------------------------------------------------------
def create_limit_request(username: str, *args, note: str = "") -> int:
    """
    Backward compatible:
      old: create_limit_request(username, depth, max_files, max_total_mb, max_per_file_mb)
      new: create_limit_request(username, zip_upload_mb, depth, max_files, max_total_mb, max_per_file_mb)
    """
    uname = _normalize_username(username)

    if len(args) == 4:
        requested_zip_upload_mb = None
        requested_depth_limit, requested_max_files, requested_max_total_mb, requested_max_per_file_mb = args
    elif len(args) == 5:
        requested_zip_upload_mb, requested_depth_limit, requested_max_files, requested_max_total_mb, requested_max_per_file_mb = args
    else:
        raise ValueError("Invalid arguments for create_limit_request()")

    with get_session() as db:
        user = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        req = LimitRequest(
            username=uname,
            requested_zip_upload_mb=int(requested_zip_upload_mb) if requested_zip_upload_mb is not None else None,
            requested_depth_limit=int(requested_depth_limit),
            requested_max_files=int(requested_max_files),
            requested_max_total_mb=int(requested_max_total_mb),
            requested_max_per_file_mb=int(requested_max_per_file_mb),
            note=note or "",
            status="pending",
            requested_at=_now(),
        )
        db.add(req)
        db.commit()

        ops(action="create_limit_request", username=uname, message="Limit request created")
        return int(cast(Any, req).id)


def list_limit_requests(status: Optional[str] = None) -> List[Dict]:
    with get_session() as db:
        stmt = select(LimitRequest)
        if status:
            stmt = stmt.where(LimitRequest.status == status)
        rows = db.execute(stmt.order_by(LimitRequest.requested_at.desc())).scalars().all()
        out: List[Dict] = []
        for r in rows:
            r = cast(Any, r)
            out.append(
                {
                    "id": int(r.id),
                    "username": str(r.username),
                    "requested_zip_upload_mb": int(r.requested_zip_upload_mb) if getattr(r, "requested_zip_upload_mb", None) is not None else None,
                    "requested_depth_limit": int(r.requested_depth_limit) if getattr(r, "requested_depth_limit", None) is not None else None,
                    "requested_max_files": int(r.requested_max_files) if getattr(r, "requested_max_files", None) is not None else None,
                    "requested_max_total_mb": int(r.requested_max_total_mb) if getattr(r, "requested_max_total_mb", None) is not None else None,
                    "requested_max_per_file_mb": int(r.requested_max_per_file_mb) if getattr(r, "requested_max_per_file_mb", None) is not None else None,
                    "status": str(r.status),
                    "note": r.note,
                    "requested_at": int(r.requested_at),
                    "actioned_at": int(r.actioned_at) if getattr(r, "actioned_at", None) else None,
                    "action_by": r.action_by,
                }
            )
        return out


def approve_limit_request(request_id: int, admin_username: str) -> bool:
    with get_session() as db:
        admin_uname = _require_admin(db, admin_username)

        row = db.get(LimitRequest, request_id)
        if not row or str(cast(Any, row).status).lower() != "pending":
            return False

        row = cast(Any, row)
        uname = _normalize_username(row.username)

        existing = db.execute(select(UserLimit).where(UserLimit.username == uname)).scalar_one_or_none()
        existing = cast(Any, existing) if existing else None
        current_zip = int(getattr(existing, "zip_upload_mb", DEFAULT_LIMITS["zip_upload_mb"]) or DEFAULT_LIMITS["zip_upload_mb"]) if existing else DEFAULT_LIMITS["zip_upload_mb"]
        zip_cap = int(row.requested_zip_upload_mb) if row.requested_zip_upload_mb is not None else current_zip

        ok = set_user_limits(
            uname,
            zip_cap,
            int(row.requested_depth_limit) if row.requested_depth_limit is not None else DEFAULT_LIMITS["depth_limit"],
            int(row.requested_max_files) if row.requested_max_files is not None else DEFAULT_LIMITS["max_files"],
            int(row.requested_max_total_mb) if row.requested_max_total_mb is not None else DEFAULT_LIMITS["max_total_mb"],
            int(row.requested_max_per_file_mb) if row.requested_max_per_file_mb is not None else DEFAULT_LIMITS["max_per_file_mb"],
            admin_username=admin_uname,
        )
        if not ok:
            return False

        row.status = "approved"
        row.actioned_at = _now()
        row.action_by = admin_uname
        db.add(row)

        log_admin_action(db, admin_uname, "approve_limit_request", uname, {"request_id": request_id})
        db.commit()

        ops(action="approve_limit_request", username=uname, message="Limit request approved", details={"request_id": request_id})
        return True


def reject_limit_request(request_id: int, admin_username: str, note: str = "") -> bool:
    """
    ✅ Fix: now returns True after logging.
    """
    with get_session() as db:
        admin_uname = _require_admin(db, admin_username)

        row = db.get(LimitRequest, request_id)
        if not row:
            return False

        row = cast(Any, row)
        row.status = "rejected"
        row.actioned_at = _now()
        row.action_by = admin_uname
        if note:
            row.note = note
        db.add(row)

        log_admin_action(db, admin_uname, "reject_limit_request", row.username, {"request_id": request_id, "note": (note or "")[:500]})
        db.commit()

        ops(
            action="reject_limit_request",
            username=_normalize_username(row.username),
            message="Limit request rejected",
            details={"request_id": request_id, "note": (note or "")[:500]},
        )
        return True


# =========================================================================
# Demo Users + Session Verification
# =========================================================================
def _create_if_missing(username: str, password: str, role: str) -> None:
    """Create a demo user if they don't already exist."""
    uname = _normalize_username(username)
    with get_session() as db:
        # Check if user exists
        existing = db.execute(
            select(User).where(User.username == uname)
        ).scalar_one_or_none()
        if existing:
            return

        # Validate password meets security requirements
        if not validate_password(password):
            raise ValueError(f"Demo password for {username} does not meet security requirements")

        # Hash and create the user
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        new_user = User(
            username=uname,
            password_hash=pw_hash,
            role=role.strip().lower(),
            must_reset=True,
            created_at=_now()
        )
        db.add(new_user)
        db.commit()
        
        ops(
            action="create_demo_user",
            username=uname,
            message=f"Demo user created with role {role}",
        )


def create_demo_users() -> None:
    """Create default demo users for testing/development."""
    init_db()
    _create_if_missing("admin_user", "Admin@123!", "admin")
    _create_if_missing("user", "User@123!", "user")
    _create_if_missing("guest_user", "Guest@123!", "guest")


def verify_session_owner(session_id: str, username: str) -> bool:
    """
    Verify that a session is owned by the given username.
    Used to detect and prevent session fixation attacks.
    
    Returns True if the session is validly owned by the user, False otherwise.
    """
    if not session_id or not username:
        return False
    
    uname = _normalize_username(username)
    
    try:
        with get_session() as db:
            # Check app_sessions registry
            from models import AppSession
            session_rec = db.execute(
                select(AppSession).where(
                    (AppSession.session_id == session_id) &
                    (AppSession.username == uname)
                )
            ).scalar_one_or_none()
            
            if session_rec and str(cast(Any, session_rec).status) == "ACTIVE":
                return True
    except Exception:
        pass
    
    return False
