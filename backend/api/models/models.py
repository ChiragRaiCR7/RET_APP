from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from api.core.database import Base


# =========================
# USERS
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), default="user", nullable=False)
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("LoginSession", back_populates="user")
    reset_tokens = relationship("PasswordResetToken", back_populates="user")


# =========================
# LOGIN SESSIONS
# =========================
class LoginSession(Base):
    __tablename__ = "login_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    refresh_token_hash = Column(String(255), nullable=False)
    ip_address = Column(String(64))
    user_agent = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("ix_login_session_user", "user_id"),
    )


# =========================
# PASSWORD RESET TOKENS
# =========================
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    token_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reset_tokens")


# =========================
# PASSWORD RESET REQUESTS (ADMIN APPROVAL)
# =========================
class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"

    id = Column(Integer, primary_key=True)
    username = Column(String(120), nullable=False)
    reason = Column(Text)
    status = Column(String(32), default="pending")  # pending / approved / rejected

    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime)


# =========================
# USER LIMITS
# =========================
class UserLimit(Base):
    __tablename__ = "user_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    max_sessions = Column(Integer, default=3)
    max_upload_mb = Column(Integer, default=10000)

    created_at = Column(DateTime, default=datetime.utcnow)


# =========================
# LIMIT INCREASE REQUESTS
# =========================
class LimitIncreaseRequest(Base):
    __tablename__ = "limit_increase_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    requested_max_upload_mb = Column(Integer)
    reason = Column(Text)
    status = Column(String(32), default="pending")

    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime)


# =========================
# AUDIT LOGS
# =========================
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    username = Column(String(120))
    action = Column(String(255))
    area = Column(String(64))
    corr_id = Column(String(64))
    message = Column(Text)
    details = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_audit_username", "username"),
        Index("ix_audit_area", "area"),
    )


# =========================
# OPERATIONAL LOGS
# =========================
class OpsLog(Base):
    __tablename__ = "ops_logs"

    id = Column(Integer, primary_key=True)
    level = Column(String(16))
    area = Column(String(64))
    action = Column(String(255))
    username = Column(String(120))
    session_id = Column(String(128))
    corr_id = Column(String(64))
    message = Column(Text)
    details = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)


# =========================
# ERROR EVENTS
# =========================
class ErrorEvent(Base):
    __tablename__ = "error_events"

    id = Column(Integer, primary_key=True)
    username = Column(String(120))
    session_id = Column(String(128))
    phase = Column(String(64))
    path = Column(Text)
    error_type = Column(String(128))
    message = Column(Text)
    corr_id = Column(String(64))

    created_at = Column(DateTime, default=datetime.utcnow)
