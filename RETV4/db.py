# db.py
# Database initialization, connection pooling, and utilities
# This module handles all database operations and connection management

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, ContextManager
from contextlib import contextmanager

from sqlalchemy import create_engine, select, text, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from models import Base, User, OpsLog, ErrorEvent, AuditLog

# =========================================================
# Database Engine & Session Factory
# =========================================================
DATABASE_URL = "sqlite:///./ret.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_session() -> ContextManager[Session]:
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =========================================================
# Initialization
# =========================================================
def init_db() -> None:
    """Create all database tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# =========================================================
# Operational Logging (Postgres-backed in production, SQLite in dev)
# =========================================================
def write_ops_log(
    *,
    level: str = "INFO",
    area: str = "MAIN",
    action: str = "event",
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    corr_id: Optional[str] = None,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write to ops_logs table.
    
    Args:
        level: Log level (INFO, WARNING, ERROR, DEBUG)
        area: Area/module name
        action: Action name
        username: Associated username
        session_id: Associated session ID
        corr_id: Correlation ID for tracing
        message: Log message
        details: Additional details dictionary
    """
    try:
        now = int(time.time())
        with get_session() as db:
            log_entry = OpsLog(
                created_at=now,
                level=level or "INFO",
                area=area or "MAIN",
                action=action or "event",
                username=username,
                session_id=session_id,
                corr_id=corr_id,
                message=(message or "")[:2000],
                details=json.dumps(details or {}, ensure_ascii=False)[:50_000],
            )
            db.add(log_entry)
    except Exception:
        pass  # Never break application due to logging failure


def write_error_event(
    *,
    phase: str = "UNKNOWN",
    path: Optional[str] = None,
    error_code: str = "INTERNAL_ERROR",
    message: str = "",
    corr_id: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write to error_events table.
    
    Args:
        phase: Phase where error occurred
        path: File/resource path
        error_code: Error code
        message: Error message
        corr_id: Correlation ID
        username: Associated username
        session_id: Associated session ID
        details: Additional error details
    """
    try:
        now = int(time.time())
        with get_session() as db:
            error_entry = ErrorEvent(
                created_at=now,
                phase=phase or "UNKNOWN",
                path=path,
                error_code=error_code or "INTERNAL_ERROR",
                message=(message or "")[:2000],
                corr_id=corr_id,
                username=username,
                session_id=session_id,
                details=json.dumps(details or {}, ensure_ascii=False)[:50_000],
            )
            db.add(error_entry)
    except Exception:
        pass  # Never break application due to logging failure


# =========================================================
# App Session Management (Session Registry)
# =========================================================
def upsert_app_session(
    session_id: str,
    username: Optional[str] = None,
    temp_dir: Optional[str] = None,
    log_path: Optional[str] = None,
    status: str = "ACTIVE",
) -> None:
    """
    Create or update an app session in the registry.
    
    Args:
        session_id: Session ID (from sid cookie)
        username: Associated username
        temp_dir: Temp directory path
        log_path: Log file path
        status: Session status
    """
    try:
        from models import AppSession
        now = int(time.time())
        
        with get_session() as db:
            existing = db.execute(
                select(AppSession).where(AppSession.session_id == session_id)
            ).scalar()
            
            if existing:
                existing.username = username
                existing.temp_dir = temp_dir
                existing.log_path = log_path
                existing.status = status
                existing.last_seen = now
            else:
                session = AppSession(
                    session_id=session_id,
                    username=username,
                    temp_dir=temp_dir,
                    log_path=log_path,
                    status=status,
                    created_at=now,
                    last_seen=now,
                )
                db.add(session)
    except Exception:
        pass


def touch_app_session(session_id: str) -> None:
    """Update last_seen timestamp for a session."""
    try:
        from models import AppSession
        now = int(time.time())
        
        with get_session() as db:
            session = db.execute(
                select(AppSession).where(AppSession.session_id == session_id)
            ).scalar()
            if session:
                session.last_seen = now
    except Exception:
        pass


def mark_app_session(session_id: str, status: str) -> None:
    """Mark an app session with a status."""
    try:
        from models import AppSession
        now = int(time.time())
        
        with get_session() as db:
            session = db.execute(
                select(AppSession).where(AppSession.session_id == session_id)
            ).scalar()
            if session:
                session.status = status
                session.last_seen = now
    except Exception:
        pass
