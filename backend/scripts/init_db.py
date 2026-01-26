from api.core.database import engine, Base

# IMPORTANT: import all models so Base knows them
from api.models import (
    User,
    LoginSession,
    PasswordResetToken,
    PasswordResetRequest,
    UserLimit,
    LimitIncreaseRequest,
    AuditLog,
    OpsLog,
    ErrorEvent,
    Job,
)

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("✅ Database tables created successfully")
