from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from typing import cast
from api.core.config import settings

# Type-safe database URL with fallback (explicit cast for type checker)
_database_url: str = cast(str, settings.DATABASE_URL) if settings.DATABASE_URL else "sqlite:///./test.db"

engine = create_engine(
    _database_url,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections every hour
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

class Base(DeclarativeBase):
    pass

def init_db():
    """Initialize database schema"""
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
