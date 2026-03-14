
#!/usr/bin/env python3
"""
Create admin and demo users for RET-v4 (Async SQLAlchemy compatible).

Why this rewrite:
- Your database layer is async-first (AsyncSession via async_sessionmaker).
- The previous script used sync SessionLocal + .query(), which breaks.

Usage:
  # Default behavior: create admin + demo if they don't exist
  python scripts/create_admin.py

  # Create a specific user
  python scripts/create_admin.py --username admin --password "Admin123!" --role admin

  # Create admin + demo explicitly
  python scripts/create_admin.py --create-demo
"""

import argparse
import asyncio

from sqlalchemy import select

import api.core.database as database
from api.core.security import hash_password

# Prefer importing User from api.models if that is your canonical export.
# If your project uses api.models.models, adjust accordingly.
try:
    from api.models import User
except Exception:
    from api.models.models import User  # fallback


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create RET-v4 users (admin/demo).")
    parser.add_argument("--username", type=str, default=None, help="Username to create")
    parser.add_argument("--password", type=str, default=None, help="Password to set")
    parser.add_argument(
        "--role",
        type=str,
        default=None,
        help="Role to set (admin/user/guest/super_admin). Stored as lowercase.",
    )
    parser.add_argument(
        "--create-demo",
        action="store_true",
        help="Create default admin + demo users if not present.",
    )
    return parser.parse_args()


async def _ensure_user(db, username: str, password: str, role: str) -> bool:
    """
    Ensure a user exists. Returns True if created, False if already existed.
    """
    role = (role or "user").strip().lower()

    res = await db.execute(select(User).where(User.username == username))
    existing = res.scalar_one_or_none()
    if existing:
        print(f"[!] User '{username}' already exists — skipping")
        return False

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,  # lowercase canonical
        is_active=True,
        is_locked=False,
    )
    db.add(user)
    await db.commit()
    print(f"[+] Created user '{username}' with role '{role}'")
    return True


async def create_admin_async(args: argparse.Namespace) -> int:
    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized (SessionLocal is None)")

    try:
        async with database.SessionLocal() as db:
            # If user provided username/password/role, create that specific user.
            if args.username and args.password:
                await _ensure_user(
                    db,
                    username=args.username,
                    password=args.password,
                    role=args.role or "admin",
                )
                return 0

            # Default behavior: create admin + demo if --create-demo is set or no args supplied.
            if args.create_demo or (not args.username and not args.password and not args.role):
                await _ensure_user(db, "admin", "admin123", "admin")
                await _ensure_user(db, "demo", "demo123", "user")
                print("[i] Default users ensured (admin/demo).")
                return 0

            print("[!] No action taken. Provide --username and --password, or use --create-demo.")
            return 1

    finally:
        await database.close_db()


def create_admin() -> int:
    args = _parse_args()
    return asyncio.run(create_admin_async(args))


if __name__ == "__main__":
    raise SystemExit(create_admin())
