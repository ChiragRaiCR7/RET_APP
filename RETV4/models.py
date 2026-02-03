# models.py
# -----------------------------------------------------------------------------
# PURPOSE
#   SQLAlchemy ORM models for RETv4:
#     - Authentication (users, login sessions)
#     - Password reset flows (tokens + requests)
#     - Governance (limits + limit requests)
#     - Audit logging (admin actions)
#     - Operational logging (ops logs)
#     - Error events (structured errors stored in DB)
#     - App session registry (central session tracking for cleanup/monitoring)
#
# NOTES
#   - This file defines the schema used by db.py:init_db() via Base.metadata.create_all()
#   - Where possible, we keep schema stable to avoid forcing migrations.
#   - Indexes are intentionally added for admin querying and cleanup operations.
# -----------------------------------------------------------------------------

from __future__ import annotations

import time
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    CheckConstraint,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, synonym

Base = declarative_base()


def now_epoch() -> int:
    """Epoch seconds helper for created_at fields."""
    return int(time.time())


# =========================================================
# Core Auth Models
# =========================================================
class User(Base):
    """
    users
    - Primary identity store for RETv4.
    - Token-first onboarding supported: password_hash may be NULL.
    - Lockout fields support basic brute-force protection.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    # Username is unique and indexed for fast auth lookups.
    username = Column(String, unique=True, nullable=False, index=True)

    # Token-first onboarding: allow NULL password hash until reset token used.
    password_hash = Column(Text, nullable=True)

    # admin/user/guest
    role = Column(String, nullable=False, index=True)

    # lockout tracking
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(BigInteger, default=0, nullable=False)

    # must_reset means user must reset password on next login attempt
    must_reset = Column(Boolean, default=True, nullable=False)
    password_changed_at = Column(BigInteger, nullable=True)

    created_at = Column(BigInteger, default=now_epoch, nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('admin','user','guest')", name="ck_users_role"),
        Index("idx_users_role", "role"),
    )


class ResetToken(Base):
    """
    reset_tokens
    - Stores password reset token hash only (never plaintext).
    - Primary key is username (one active token row per user).
    - used_at marks token used; expires_at enforces TTL.
    """
    __tablename__ = "reset_tokens"

    username = Column(
        String,
        ForeignKey("users.username", ondelete="CASCADE"),
        primary_key=True,
    )
    token_hash = Column(Text, nullable=False)

    expires_at = Column(BigInteger, nullable=False, index=True)
    created_at = Column(BigInteger, default=now_epoch, nullable=False)
    used_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint("username", name="uq_tokens_username"),
        Index("idx_reset_tokens_expires_at", "expires_at"),
    )


class ResetRequest(Base):
    """
    reset_requests
    - User-initiated workflow (user requests reset; admin approves/rejects).
    - status: pending/approved/rejected
    """
    __tablename__ = "reset_requests"

    id = Column(Integer, primary_key=True)

    username = Column(
        String,
        ForeignKey("users.username", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(String, default="pending", nullable=False, index=True)
    note = Column(Text, nullable=True)

    requested_at = Column(BigInteger, default=now_epoch, nullable=False)
    actioned_at = Column(BigInteger, nullable=True)
    action_by = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_rr_status"),
        Index("idx_reset_requests_status", "status"),
        Index("idx_reset_requests_requested_at", "requested_at"),
    )


class UserLimit(Base):
    """
    user_limits
    - Per-user limits overrides (optional).
    - Admin role can override limits via auth logic even if no row exists.
    """
    __tablename__ = "user_limits"

    username = Column(
        String,
        ForeignKey("users.username", ondelete="CASCADE"),
        primary_key=True,
    )

    zip_upload_mb = Column(Integer, default=1000, nullable=False)
    depth_limit = Column(Integer, default=50, nullable=False)
    max_files = Column(Integer, default=10_000, nullable=False)
    max_total_mb = Column(Integer, default=10_000, nullable=False)
    max_per_file_mb = Column(Integer, default=10, nullable=False)

    updated_at = Column(BigInteger, default=now_epoch, nullable=False)

    __table_args__ = (
        Index("idx_user_limits_updated_at", "updated_at"),
    )


class LimitRequest(Base):
    """
    limit_requests
    - User-initiated workflow for increasing resource limits.
    - Admin approves/rejects; approval typically creates/updates user_limits.
    """
    __tablename__ = "limit_requests"

    id = Column(Integer, primary_key=True)

    username = Column(
        String,
        ForeignKey("users.username", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    requested_zip_upload_mb = Column(Integer, nullable=True)
    requested_depth_limit = Column(Integer, nullable=True)
    requested_max_files = Column(Integer, nullable=True)
    requested_max_total_mb = Column(Integer, nullable=True)
    requested_max_per_file_mb = Column(Integer, nullable=True)

    status = Column(String, default="pending", nullable=False, index=True)
    note = Column(Text, nullable=True)

    requested_at = Column(BigInteger, default=now_epoch, nullable=False)
    actioned_at = Column(BigInteger, nullable=True)
    action_by = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_lr_status"),
        Index("idx_limit_requests_status", "status"),
        Index("idx_limit_requests_requested_at", "requested_at"),
    )


class AuditLog(Base):
    """
    audit_logs
    - Records admin actions (create user, delete user, approve requests, etc.)
    - Stored separately from ops_logs to keep audit trail consistent.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    admin_username = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    target_username = Column(String, nullable=True, index=True)

    # JSON string payload, bounded at write time.
    details = Column(Text, nullable=True)

    created_at = Column(BigInteger, default=now_epoch, nullable=False, index=True)

    __table_args__ = (
        Index("idx_audit_logs_created_at", "created_at"),
    )


class LoginSession(Base):
    """
    login_sessions
    - Persistent login sessions (cookie token stored client-side; hash stored server-side).
    - token_hash is the primary key.
    - token synonym exists for backward compatibility (older code referencing token).
    """
    __tablename__ = "login_sessions"

    # Store hash (e.g., HMAC-SHA256 hex) in DB; plaintext stays only in cookie.
    token_hash = Column(String, primary_key=True)

    # Backward-compatible alias (older code may reference LoginSession.token)
    token = synonym("token_hash")

    username = Column(
        String,
        ForeignKey("users.username", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(BigInteger, default=now_epoch, nullable=False)
    expires_at = Column(BigInteger, nullable=False, index=True)

    __table_args__ = (
        Index("idx_login_sessions_expires_at", "expires_at"),
        Index("idx_login_sessions_username", "username"),
    )


# =========================================================
# Postgres-backed Session Registry & Operational Logs
# =========================================================
class AppSession(Base):
    """
    app_sessions
    - Central registry of active sessions identified by sid cookie.
    - Admin console can view/cleanup idle sessions based on last_seen.
    - temp_dir/log_path are stored for convenience; admin cleanup must allowlist paths.
    """
    __tablename__ = "app_sessions"

    session_id = Column(String, primary_key=True)  # sid cookie
    username = Column(String, ForeignKey("users.username", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(BigInteger, default=now_epoch, nullable=False, index=True)
    last_seen = Column(BigInteger, default=now_epoch, nullable=False, index=True)

    # ACTIVE / CLEANED_IDLE / FORCE_CLEANED_IDLE / LOGOUT / ERROR / etc.
    status = Column(String, default="ACTIVE", nullable=False, index=True)

    # Optional filesystem pointers:
    # - temp_dir: session runtime folder (contains extracted XMLs, CSV outputs, chroma)
    # - log_path: session log file path
    temp_dir = Column(Text, nullable=True)
    log_path = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_app_sessions_status_last_seen", "status", "last_seen"),
        Index("idx_app_sessions_user_last_seen", "username", "last_seen"),
    )


class OpsLog(Base):
    """
    ops_logs
    - Structured operational logs (system events, admin agent actions, conversion stats).
    - Avoid storing secrets; db.py and auth.py sanitize payloads.
    """
    __tablename__ = "ops_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(BigInteger, default=now_epoch, nullable=False, index=True)

    level = Column(String, default="INFO", nullable=False, index=True)  # INFO/WARN/ERROR
    area = Column(String, nullable=False, index=True)  # AUTH / ADMIN / MAIN / AI / CLEANUP / APP
    action = Column(String, nullable=False, index=True)  # e.g. "cleanup_idle_sessions"

    username = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    corr_id = Column(String, nullable=True, index=True)

    message = Column(Text, nullable=True)

    # JSON string payload (bounded at write time)
    details_json = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_ops_logs_area_created", "area", "created_at"),
        Index("idx_ops_logs_user_created", "username", "created_at"),
        Index("idx_ops_logs_session_created", "session_id", "created_at"),
    )


class ErrorEvent(Base):
    """
    error_events
    - Structured error tracking stored in Postgres (in addition to per-session file logs).
    - Useful for admin diagnostics at scale.
    """
    __tablename__ = "error_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(BigInteger, default=now_epoch, nullable=False, index=True)

    username = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)

    phase = Column(String, nullable=True, index=True)  # e.g. SCAN/CONVERT/AI_CHAT
    path = Column(Text, nullable=True)

    error_type = Column(String, nullable=True)
    message = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_error_events_phase_created", "phase", "created_at"),
        Index("idx_error_events_user_created", "username", "created_at"),
    )
