
#!/usr/bin/env python3
"""
Create or update users for RET-v4 (Async SQLAlchemy).

Improvements over legacy version:
  1. Interactive password prompt via getpass (no plaintext on CLI)
  2. Role validation against UserRole enum (admin/user/guest/super_admin)
  3. Structured logging (logging module)
  4. Environment awareness — blocks production use without --force
  5. Atomic transactions via async with db.begin()

Usage:
  # Fully interactive
  python scripts/create_admin.py

  # Username supplied, password prompted securely
  python scripts/create_admin.py --username admin

  # Fully non-interactive (CI/CD pipelines)
  python scripts/create_admin.py --username admin --password "Admin123!" --role admin

  # Override production guard
  python scripts/create_admin.py --username admin --force
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from sqlalchemy import select

import api.core.database as database
from api.core.security import hash_password

try:
    from api.models import User
    from api.models.models import UserRole
except Exception:
    from api.models.models import User, UserRole  # fallback

# ------------------------------------------------
# Logging
# ------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("create_admin")

# ------------------------------------------------
# Constants
# ------------------------------------------------

VALID_ROLES: set[str] = {role.value for role in UserRole}


# ------------------------------------------------
# CLI
# ------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create or ensure a RET-v4 user.")
    p.add_argument("--username", type=str, default=None, help="Username to create.")
    p.add_argument(
        "--password", type=str, default=None,
        help="Password (omit to be prompted securely via getpass).",
    )
    p.add_argument(
        "--role", type=str, default=None,
        help=f"User role. One of: {sorted(VALID_ROLES)}. Default: admin.",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Bypass the production environment guard.",
    )
    return p.parse_args()


# ------------------------------------------------
# 4. Environment awareness
# ------------------------------------------------

def _check_environment(force: bool) -> None:
    """Warn or block if running against a production environment."""
    try:
        from api.core.config import settings
        env_value = getattr(settings.ENV, "value", str(settings.ENV)).lower()
    except Exception:
        env_value = os.getenv("ENV", "development").lower()

    if env_value == "production":
        if force:
            logger.warning(
                "Running in PRODUCTION (--force supplied). "
                "Proceeding — ensure this is intentional."
            )
        else:
            logger.error(
                "Refusing to run create_admin.py in PRODUCTION without --force. "
                "Use your provisioning or deployment pipeline instead."
            )
            raise SystemExit(1)
    elif env_value == "staging":
        logger.warning("Running against STAGING environment.")
    else:
        logger.info(f"Environment: {env_value}")


# ------------------------------------------------
# 2. Role validation
# ------------------------------------------------

def _validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in VALID_ROLES:
        logger.error(f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}")
        raise SystemExit(1)
    return normalized


# ------------------------------------------------
# Interactive prompts
# ------------------------------------------------

def _prompt_username() -> str:
    username = input("Username: ").strip()
    if not username:
        logger.error("Username cannot be empty.")
        raise SystemExit(1)
    return username


def _prompt_password(username: str) -> str:
    """Prompt for password with confirmation. Enforces minimum length."""
    while True:
        pw = getpass.getpass(f"Password for '{username}': ")
        if len(pw) < 8:
            print("  Password must be at least 8 characters. Try again.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            print("  Passwords do not match. Try again.")
            continue
        return pw


def _prompt_role() -> str:
    role_input = (
        input(f"Role [{'/'.join(sorted(VALID_ROLES))}] (default: admin): ").strip()
        or "admin"
    )
    return _validate_role(role_input)


# ------------------------------------------------
# 5. Atomic user creation
# ------------------------------------------------

async def _ensure_user(db, username: str, password: str, role: str) -> bool:
    """
    Create a user inside an atomic transaction.
    Returns True if created, False if username already existed.
    Uses async with db.begin() to guarantee atomicity (auto-commits on clean exit).
    """
    async with db.begin():
        res = await db.execute(select(User).where(User.username == username))
        existing = res.scalar_one_or_none()
        if existing:
            logger.info(f"User '{username}' already exists — skipping")
            return False

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            is_locked=False,
        )
        db.add(user)
        # db.begin() context manager auto-commits here

    logger.info(f"Created user '{username}' with role '{role}'")
    return True


# ------------------------------------------------
# Main async entry point
# ------------------------------------------------

async def create_admin_async(args: argparse.Namespace) -> int:
    # 4. Environment guard
    _check_environment(force=args.force)

    # Gather inputs — interactive if not provided via CLI
    username = args.username or _prompt_username()
    role_raw = args.role or _prompt_role()
    role = _validate_role(role_raw)
    password = args.password or _prompt_password(username)

    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized (SessionLocal is None)")

    try:
        async with database.SessionLocal() as db:
            created = await _ensure_user(db, username, password, role)
            if created:
                logger.info(f"User '{username}' ({role}) is ready.")
            return 0
    finally:
        await database.close_db()


def main() -> int:
    args = _parse_args()
    return asyncio.run(create_admin_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
