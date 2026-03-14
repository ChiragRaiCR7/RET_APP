
from __future__ import annotations

from datetime import datetime, timezone
import enum

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
    Enum as SAEnum,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from api.core.database import Base


# =========================
# Helpers
# =========================
def _utcnow() -> datetime:
    """Return naive UTC timestamp for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# =========================
# ENUMS
# =========================
class UserRole(str, enum.Enum):
    """User role enumeration."""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    GUEST = "guest"


class RequestStatus(str, enum.Enum):
    """Status for approval requests."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# =========================
# USERS
# =========================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ✅ Non-breaking: keep role as string to avoid schema/type breaking changes.
    # Add a DB-level CHECK constraint below to restrict values to known roles.
    role: Mapped[str] = mapped_column(
        String(32),
        default=UserRole.USER.value,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # soft delete

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    sessions: Mapped[list["LoginSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # ✅ Non-breaking safety: restrict role values at DB-level
        # (Effective on Postgres; SQLite may not enforce depending on configuration)
        CheckConstraint(
            "role IN ('user','admin','super_admin','guest')",
            name="ck_users_role_valid",
        ),
    )


# =========================
# LOGIN SESSIONS
# =========================
class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Store a hash of refresh token (never store raw refresh token)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ✅ Additive security improvement:
    # store refresh token jti for efficient revocation/rotation tracking
    refresh_jti: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Token-family tracking for rotation and reuse detection.
    # All tokens in one rotation chain share the same family ID.
    token_family: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # When a token is rotated, the old row points to the replacement.
    replaced_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Soft-revoke flag (set on reuse-detection to invalidate full family).
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_login_session_user", "user_id"),
        Index("ix_login_session_expires", "expires_at"),
        Index("ix_login_session_refresh_jti", "refresh_jti"),
        Index("ix_login_session_family", "token_family"),
    )


# =========================
# PASSWORD RESET TOKENS
# =========================
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # token_hash should be an Argon2 hash (or similar)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="reset_tokens")

    __table_args__ = (
        Index("ix_reset_token_expires", "expires_at"),
    )


# =========================
# PASSWORD RESET REQUESTS (ADMIN APPROVAL)
# =========================
class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Keep Enum(RequestStatus) storage (works well on Postgres)
    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus),
        default=RequestStatus.PENDING,
        nullable=False,
    )

    action_by: Mapped[str | None] = mapped_column(String(120), nullable=True)  # admin who took action

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# =========================
# USER LIMITS
# =========================
class UserLimit(Base):
    __tablename__ = "user_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    max_sessions: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_upload_mb: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    max_files: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    max_nested_depth: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_limits_user"),
    )


# =========================
# LIMIT INCREASE REQUESTS
# =========================
class LimitIncreaseRequest(Base):
    __tablename__ = "limit_increase_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    requested_max_upload_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_max_files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_max_nested_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus),
        default=RequestStatus.PENDING,
        nullable=False,
    )

    action_by: Mapped[str | None] = mapped_column(String(120), nullable=True)  # admin who took action

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# =========================
# AUDIT LOGS
# =========================
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corr_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_username", "username"),
        Index("ix_audit_area", "area"),
        Index("ix_audit_corr_id", "corr_id"),
    )


# =========================
# OPERATIONAL LOGS
# =========================
class OpsLog(Base):
    __tablename__ = "ops_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(255), nullable=True)

    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    corr_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ops_corr_id", "corr_id"),
        Index("ix_ops_session_id", "session_id"),
        Index("ix_ops_username", "username"),
    )


# =========================
# ERROR EVENTS
# =========================
class ErrorEvent(Base):
    __tablename__ = "error_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    corr_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_error_corr_id", "corr_id"),
        Index("ix_error_type", "error_type"),
        Index("ix_error_session_id", "session_id"),
    )

