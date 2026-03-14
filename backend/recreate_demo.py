#!/usr/bin/env python3
from __future__ import annotations

import asyncio

from sqlalchemy import select

import api.core.database as database
from api.models.models import User
from api.core.security import hash_password, verify_password


async def main() -> int:
    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized (SessionLocal is None)")

    try:
        async with database.SessionLocal() as db:
            # Delete demo user if exists
            existing_res = await db.execute(select(User).where(User.username == "demo"))
            existing = existing_res.scalar_one_or_none()
            if existing is not None:
                await db.delete(existing)
                await db.commit()
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
            await db.commit()
            await db.refresh(demo)
            print(f"Created demo user with hash: {demo.password_hash}")

            # Verify it works
            if verify_password("demo123", demo.password_hash):
                print("Verification SUCCESS!")
            else:
                print("Verification FAILED!")

        return 0
    finally:
        await database.close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
