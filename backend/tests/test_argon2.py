#!/usr/bin/env python3
from api.core.security import hash_password, verify_password

# Test hashing and verification
hash1 = hash_password('demo123')
print(f'Hash: {hash1}')
result = verify_password('demo123', hash1)
print(f'Verify correct password: {result}')
result2 = verify_password('wrong', hash1)
print(f'Verify wrong password: {result2}')

# Check what's in database
from api.core.database import SessionLocal
from api.models.models import User

db = SessionLocal()
demo = db.query(User).filter(User.username == "demo").first()
if demo:
    print(f'\nDemo user hash: {demo.password_hash}')
    print(f'Verify stored hash: {verify_password("demo123", demo.password_hash)}')
else:
    print("Demo user not found!")
db.close()
