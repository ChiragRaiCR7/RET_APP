
#!/usr/bin/env python3
"""
Fix user role column values to lowercase.

Why this rewrite:
- Your DB layer is async-first.
- The previous script imported get_session (not present in your async database.py).
- ORM-based reads can crash if role values don't match Enum; raw SQL avoids that.

Usage:
  python scripts/fix_role_case.py
"""

import asyncio
import sys

from sqlalchemy import text

import api.core.database as database


UPPER_TO_LOWER = {
    "ADMIN": "admin",
    "USER": "user",
    "GUEST": "guest",
    "SUPER_ADMIN": "super_admin",
}


async def fix_role_case_async() -> int:
    print("=" * 60)
    print("RET v4 - Role Case Migration Script (Async)")
    print("=" * 60)
    print()

    await database.init_db()

    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized (SessionLocal is None)")

    try:
        async with database.SessionLocal() as db:
            # Find uppercase roles safely (raw SQL)
            res = await db.execute(
                text(
                    """
                    SELECT username, role
                    FROM users
                    WHERE role IN ('ADMIN', 'USER', 'GUEST', 'SUPER_ADMIN')
                    """
                )
            )
            uppercase_users = res.fetchall()

            if not uppercase_users:
                print("✅ No uppercase roles found. Database is already up to date.")
                return 0

            print(f"Found {len(uppercase_users)} users with uppercase roles:")
            for username, role in uppercase_users:
                print(f"  - {username}: {role}")

            print("\nConverting to lowercase...\n")

            total_updated = 0
            for old_role, new_role in UPPER_TO_LOWER.items():
                upd = await db.execute(
                    text("UPDATE users SET role = :new_role WHERE role = :old_role"),
                    {"new_role": new_role, "old_role": old_role},
                )
                rowcount = getattr(upd, "rowcount", None)
                updated = int(rowcount) if isinstance(rowcount, int) else 0
                if updated > 0:
                    total_updated += updated
                    print(f"  ✅ Updated {updated} user(s) from '{old_role}' to '{new_role}'")

            await db.commit()

            print("\nFinal verification - All users:")
            res2 = await db.execute(text("SELECT username, role FROM users ORDER BY username"))
            for username, role in res2.fetchall():
                print(f"  - {username}: {role}")

            print("\n" + "=" * 60)
            print(f"✅ Role case migration completed successfully! Updated: {total_updated}")
            print("=" * 60)
            return 0

    finally:
        await database.close_db()


def main() -> int:
    try:
        return asyncio.run(fix_role_case_async())
    except Exception as e:
        print(f"\n❌ Error during migration: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
