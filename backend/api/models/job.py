
from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    JSON,
    ForeignKey,
    Enum as SAEnum,
    Index,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.core.database import Base


def _utcnow() -> datetime:
    """Return naive UTC timestamp for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JobStatus(str, enum.Enum):
    """Job status enumeration."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, enum.Enum):
    """Job type enumeration."""
    CONVERSION = "conversion"
    COMPARISON = "comparison"
    INDEXING = "indexing"
    XLSX_EXPORT = "xlsx_export"
    AUTO_INDEX = "auto_index"


class Job(Base):
    __tablename__ = "jobs"

    # -------------------------
    # Core fields
    # -------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    job_type: Mapped[JobType] = mapped_column(SAEnum(JobType), nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus),
        default=JobStatus.PENDING,
        nullable=False,
    )

    # progress: 0–100
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # -------------------------
    # Owner tracking
    # -------------------------
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # -------------------------
    # Timestamps
    # -------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,                 # python-side default
        server_default=func.now(),       # db-side default (extra safety)
        nullable=False,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,                 # python-side default
        onupdate=_utcnow,                # python-side update
        server_default=func.now(),       # db-side default
        nullable=False,
    )

    # -------------------------
    # Indexes / Constraints
    # -------------------------
    __table_args__ = (
        # ✅ Ensure progress is always valid
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_jobs_progress_0_100"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created", "created_at"),
        Index("ix_jobs_session", "session_id"),
    )
