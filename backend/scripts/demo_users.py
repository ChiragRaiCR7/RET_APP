"""
Create demo users for RET-v4
- Admin user
- Normal user
"""

from sqlalchemy.orm import Session

from api.core.database import SessionLocal
from api.models.models import User
from api.core.security import hash_password


DEMO_USERS = [
    {
        "username": "admin",
        "password": "admin123",
        "role": "admin",
        "is_active": True,
        "is_locked": False,
    },
    {
        "username": "demo",
        "password": "demo123",
        "role": "user",
        "is_active": True,
        "is_locked": False,
    },
]


def create_demo_users():
    db: Session = SessionLocal()

    try:
        for data in DEMO_USERS:
            existing = (
                db.query(User)
                .filter(User.username == data["username"])
                .first()
            )

            if existing:
                print(f"[!] User '{data['username']}' already exists — skipping")
                continue

            user = User(
                username=data["username"],
                password_hash=hash_password(data["password"]),
                role=data["role"],
                is_active=data["is_active"],
                is_locked=data["is_locked"],
            )

            db.add(user)
            db.commit()

            print(f"[+] Created user '{data['username']}'")

    finally:
        db.close()


if __name__ == "__main__":
    create_demo_users()
