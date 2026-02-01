from sqlalchemy.orm import Session
from typing import Optional
from api.models.job import Job

def create_job(db: Session, job_type: str) -> Job:
    job = Job(job_type=job_type)
    db.add(job)
    db.flush()
    return job

def get_job(db: Session, job_id: int) -> Optional[Job]:
    return db.query(Job).get(job_id)
