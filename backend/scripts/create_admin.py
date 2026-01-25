from api.core.database import SessionLocal
from api.services.admin_service import create_user

if __name__ == "__main__":
    db = SessionLocal()
    create_user(
        db,
        username="admin",
        password="admin123",
        role="admin",
    )
    db.commit()
    print("Admin user created")
