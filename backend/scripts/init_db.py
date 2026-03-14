
#!/usr/bin/env python3
"""
Initialize RET-v4 database (Async SQLAlchemy) and optionally seed demo users.

Why this rewrite:
- Your backend DB layer is async-first (init_db / close_db are async).
- The old init_db script only created tables and did not seed users.
- Sign-in failures commonly occur because:
  (a) users don't exist (admin/demo missing), or
  (b) passwords were hashed with a legacy algorithm (bcrypt) and now verification uses Argon2.

Usage:
  python scripts/init_db.py
  python scripts/init_db.py --seed-demo
  python scripts/init_db.py --seed-demo --reset-demo-passwords
"""

import argparse
import asyncio

from sqlalchemy import select

import api.core.database as database
from api.core.security import hash_password

# Import models so Base.metadata knows them (important for create_all in dev/testing)
# Keep your existing imports, but make it robust if module paths differ.
try:
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
    )
    from api.models.job import Job
except Exception:
    # fallback if your project uses api.models.models
    from api.models.models import (  # type: ignore
        User,
        LoginSession,
        PasswordResetToken,
        PasswordResetRequest,
        UserLimit,
        LimitIncreaseRequest,
        AuditLog,
        OpsLog,
        ErrorEvent,
    )
    from api.models.job import Job

DEFAULT_SEED_USERS = [
    # Keep canonical defaults that your docs/frontend likely expect:
    {"username": "admin", "password": "admin123", "role": "admin"},
    {"username": "demo", "password": "demo123", "role": "user"},

    # Optional additional demo accounts:
    {"username": "admin1", "password": "admin123", "role": "admin"},
    {"username": "admin2", "password": "admin234", "role": "admin"},
    {"username": "user1",  "password": "user123",  "role": "user"},
    {"username": "user2",  "password": "user234",  "role": "user"},
    {"username": "user3",  "password": "user345",  "role": "user"},
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Initialize DB and optionally seed demo users.")
    p.add_argument("--seed-demo", action="store_true", help="Create demo users if missing.")
    p.add_argument(
        "--reset-demo-passwords",
        action="store_true",
        help="Force reset passwords for demo users (fixes hash mismatch). Requires --seed-demo.",
    )
    return p.parse_args()


def is_argon2_hash(pw_hash: str | None) -> bool:
    return bool(pw_hash) and pw_hash.startswith("$argon2")


async def seed_demo_users(reset_passwords: bool) -> None:
    if database.SessionLocal is None:
        raise RuntimeError("SessionLocal is None. Database is not initialized.")

    async with database.SessionLocal() as db:
        created = 0
        updated = 0
        skipped = 0

        for u in DEFAULT_SEED_USERS:
            username = u["username"]
            password = u["password"]
            role = u["role"].lower().strip()

            res = await db.execute(select(User).where(User.username == username))
            existing = res.scalar_one_or_none()

            if not existing:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    is_active=True,
                    is_locked=False,
                )
                # Optional fields if your model includes them
                if hasattr(user, "is_deleted"):
                    user.is_deleted = False
                if hasattr(user, "failed_login_attempts"):
                    user.failed_login_attempts = 0
                if hasattr(user, "locked_until"):
                    user.locked_until = None

                db.add(user)
                created += 1
                print(f"[+] Created user '{username}'")
                continue

            # Repair/normalize existing user so sign-in works reliably
            changed = False

            # normalize role casing
            if getattr(existing, "role", None) != role:
                existing.role = role
                changed = True

            # unlock/activate for demo accounts
            if getattr(existing, "is_active", True) is False:
                existing.is_active = True
                changed = True

            if getattr(existing, "is_locked", False) is True:
                existing.is_locked = False
                changed = True

            if hasattr(existing, "is_deleted") and getattr(existing, "is_deleted", False) is True:
                existing.is_deleted = False
                changed = True

            if hasattr(existing, "failed_login_attempts"):
                existing.failed_login_attempts = 0
                changed = True

            if hasattr(existing, "locked_until"):
                existing.locked_until = None
                changed = True

            # fix hash mismatch: ensure Argon2
            current_hash = getattr(existing, "password_hash", None)
            if reset_passwords or not is_argon2_hash(current_hash):
                existing.password_hash = hash_password(password)
                changed = True

            if changed:
                updated += 1
                print(f"[~] Repaired user '{username}' (role/hash/lock state normalized)")
            else:
                skipped += 1
                print(f"[*] User '{username}' already OK — skipping")

        await db.commit()

        print("\n" + "=" * 60)
        print("Seed Summary")
        print("=" * 60)
        print(f"Created: {created}")
        print(f"Updated: {updated}")
        print(f"Skipped: {skipped}")
        print("=" * 60)


async def run(seed_demo: bool, reset_demo_passwords: bool) -> None:
    print("[*] Initializing database...")
    await database.init_db()
    print("[+] Database initialized")

    if seed_demo:
        print("[*] Seeding demo users...")
        await seed_demo_users(reset_passwords=reset_demo_passwords)
        print("[+] Demo users ensured")

    await database.close_db()
    print("[+] Database connection closed")

    print("\n✅ Done.")
    print("➡️ Try login with:")
    print("   - admin / admin123")
    print("   - demo / demo123")
    print("   - admin1 / admin123")


def main() -> int:
    args = parse_args()
    if args.reset_demo_passwords and not args.seed_demo:
        print("❌ --reset-demo-passwords requires --seed-demo")
        return 2

    asyncio.run(run(seed_demo=args.seed_demo, reset_demo_passwords=args.reset_demo_passwords))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

