from datetime import datetime, timezone
import enum
from typing import Optional
from sqlalchemy import Integer, String, DateTime, JSON, ForeignKey, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column
from api.core.database import Base


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0–100
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Owner tracking
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created", "created_at"),
        Index("ix_jobs_session", "session_id"),
    )
