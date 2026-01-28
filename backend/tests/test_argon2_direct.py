#!/usr/bin/env python3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

hasher = PasswordHasher()

# Test direct argon2 verification
test_hash = "$argon2id$v=19$m=65536,t=3,p=4$Usr8WOOmjEHDtMT+k7JdsA$tetiYyTm+tffs/6qRJxmsdL2UXvonnECW98ysBdNERs"
password = "demo123"

print(f"Hash: {test_hash}")
print(f"Password: {password}")

try:
    hasher.verify(test_hash, password)
    print("Verify result: True")
except (VerifyMismatchError, InvalidHash) as e:
    print(f"Verify failed: {e}")
except Exception as e:
    print(f"Unknown error: {type(e).__name__}: {e}")
