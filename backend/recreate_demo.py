#!/usr/bin/env python3
from api.core.database import SessionLocal
from api.models.models import User
from api.core.security import hash_password

db = SessionLocal()

# Delete demo user if exists
existing = db.query(User).filter(User.username == "demo").first()
if existing:
    db.delete(existing)
    db.commit()
    print("Deleted existing demo user")

# Create new demo user
demo = User(
    username="demo",
    password_hash=hash_password("demo123"),
    role="user",
    is_active=True,
    is_locked=False,
)
db.add(demo)
db.commit()
print(f"Created demo user with hash: {demo.password_hash}")

# Verify it works
from api.core.security import verify_password
if verify_password("demo123", demo.password_hash):
    print("Verification SUCCESS!")
else:
    print("Verification FAILED!")

db.close()
