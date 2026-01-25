from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from api.core.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(64), nullable=False)   # conversion | comparison | indexing
    status = Column(String(32), default="PENDING")  # PENDING/RUNNING/SUCCESS/FAILED
    progress = Column(Integer, default=0)           # 0–100
    result = Column(JSON)
    error = Column(String(1024))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
