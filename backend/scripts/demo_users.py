
#!/usr/bin/env python3
"""
Create demo users for RET-v4
- 2 Admin users
- 3 Normal users

Fixes:
- Ensures users are verifiable with current Argon2 password verification.
- Repairs existing users with legacy hashes (e.g., bcrypt) by re-hashing with Argon2.
- Normalizes role casing to lowercase.
- Resets lockout state fields if present.

Usage:
  python scripts/demo_users.py
  python scripts/demo_users.py --reset-passwords
"""

import argparse
import asyncio
from typing import Dict, Any

from sqlalchemy import select

import api.core.database as database
from api.models.models import User
from api.core.security import hash_password


DEMO_USERS = [
    {"username": "admin",  "password": "admin123", "role": "admin", "is_active": True, "is_locked": False},
    {"username": "demo",   "password": "demo123",  "role": "user",  "is_active": True, "is_locked": False},
    {"username": "admin1", "password": "admin123", "role": "admin", "is_active": True, "is_locked": False},
    {"username": "admin2", "password": "admin234", "role": "admin", "is_active": True, "is_locked": False},
    {"username": "user1",  "password": "user123",  "role": "user",  "is_active": True, "is_locked": False},
    {"username": "user2",  "password": "user234",  "role": "user",  "is_active": True, "is_locked": False},
    {"username": "user3",  "password": "user345",  "role": "user",  "is_active": True, "is_locked": False},
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create/repair RET-v4 demo users.")
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="Force reset passwords even if existing hashes are already Argon2.",
    )
    return parser.parse_args()


def _is_argon2_hash(pw_hash: str | None) -> bool:
    """
    Argon2 hashes typically start with '$argon2id$' or '$argon2i$' etc.
    """
    if not pw_hash:
        return False
    return pw_hash.startswith("$argon2")


def _safe_set(user: User, field: str, value: Any) -> bool:
    """
    Set attribute only if it exists on the model.
    Returns True if set, else False.
    """
    if hasattr(user, field):
        setattr(user, field, value)
        return True
    return False


async def _create_or_repair_user(db, data: Dict[str, Any], force_reset_passwords: bool) -> str:
    """
    Create missing user or repair existing user to ensure login verification works.

    Returns a status string for reporting.
    """
    username = data["username"]
    desired_role = str(data.get("role", "user")).lower().strip()
    desired_active = bool(data.get("is_active", True))
    desired_locked = bool(data.get("is_locked", False))
    desired_password = data["password"]

    res = await db.execute(select(User).where(User.username == username))
    user = res.scalar_one_or_none()

    if user is None:
        # Create user fresh
        user = User(
            username=username,
            password_hash=hash_password(desired_password),
            role=desired_role,
            is_active=desired_active,
            is_locked=desired_locked,
        )

        # Optional fields (only if model has them)
        _safe_set(user, "is_deleted", False)
        _safe_set(user, "failed_login_attempts", 0)
        _safe_set(user, "locked_until", None)

        db.add(user)
        return "CREATED"

    # Repair path for existing user
    changed = False

    # Normalize critical flags (prevents "user cannot login" due to inactive/locked/deleted)
    if getattr(user, "role", None) != desired_role:
        user.role = desired_role
        changed = True

    if getattr(user, "is_active", None) != desired_active:
        user.is_active = desired_active
        changed = True

    if getattr(user, "is_locked", None) != desired_locked:
        user.is_locked = desired_locked
        changed = True

    # Ensure not deleted (if field exists)
    if _safe_set(user, "is_deleted", False):
        changed = True

    # Reset lockout counters if present
    if _safe_set(user, "failed_login_attempts", 0):
        changed = True
    if _safe_set(user, "locked_until", None):
        changed = True

    # Ensure password hash is Argon2 (or force reset)
    current_hash = getattr(user, "password_hash", None)
    if force_reset_passwords or not _is_argon2_hash(current_hash):
        user.password_hash = hash_password(desired_password)
        changed = True

    return "REPAIRED" if changed else "UNCHANGED"


async def create_demo_users_async(force_reset_passwords: bool = False) -> int:
    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized")

    created = repaired = unchanged = 0

    try:
        async with database.SessionLocal() as db:
            # Do all operations, then commit once for consistency/performance
            for data in DEMO_USERS:
                status = await _create_or_repair_user(db, data, force_reset_passwords)
                if status == "CREATED":
                    created += 1
                    print(f"[+] Created user '{data['username']}'")
                elif status == "REPAIRED":
                    repaired += 1
                    print(f"[~] Repaired user '{data['username']}' (now verifiable)")
                else:
                    unchanged += 1
                    print(f"[*] User '{data['username']}' unchanged")

            await db.commit()

    except Exception:
        # rollback on any failure
        try:
            async with database.SessionLocal() as db:
                await db.rollback()
        except Exception:
            pass
        raise
    finally:
        await database.close_db()

    print("\n" + "=" * 60)
    print("Demo Users Summary")
    print("=" * 60)
    print(f"Created:   {created}")
    print(f"Repaired:  {repaired}")
    print(f"Unchanged: {unchanged}")
    print("=" * 60)

    return 0


def create_demo_users(force_reset_passwords: bool | None = None) -> int:
    if force_reset_passwords is None:
        args = _parse_args()
        force_reset_passwords = args.reset_passwords
    assert force_reset_passwords is not None
    return asyncio.run(create_demo_users_async(force_reset_passwords=force_reset_passwords))


if __name__ == "__main__":
    raise SystemExit(create_demo_users(force_reset_passwords=None))
