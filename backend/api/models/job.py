from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Enum, Index
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

    id = Column(Integer, primary_key=True)
    job_type = Column(Enum(JobType), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    progress = Column(Integer, default=0)  # 0–100
    result = Column(JSON)
    error = Column(String(2048))

    # Owner tracking
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(128), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created", "created_at"),
        Index("ix_jobs_session", "session_id"),
    )
