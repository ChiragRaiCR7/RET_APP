from datetime import datetime
from api.core.database import SessionLocal
from api.models.models import LoginSession

if __name__ == "__main__":
    db = SessionLocal()
    now = datetime.utcnow()

    deleted = (
        db.query(LoginSession)
        .filter(LoginSession.expires_at < now)
        .delete()
    )

    db.commit()
    print(f"Deleted {deleted} expired sessions")
