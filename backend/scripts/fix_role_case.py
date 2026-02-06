"""
Fix user role column values to use lowercase.

This script updates any existing user records that have uppercase role values
(ADMIN, USER, GUEST) to lowercase (admin, user, guest) to match the updated
UserRole enum values and prevent SQLAlchemy LookupError.

Run this script after upgrading to the new lowercase role schema.

Usage:
    python scripts/fix_role_case.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from api.core.database import get_session
from api.core.config import settings


def fix_role_case():
    """Update all user roles to lowercase."""
    print("=" * 60)
    print("RET v4 - Role Case Migration Script")
    print("=" * 60)
    print()
    
    with get_session() as db:
        # Check for any uppercase roles
        result = db.execute(text("""
            SELECT username, role 
            FROM users 
            WHERE role IN ('ADMIN', 'USER', 'GUEST', 'SUPER_ADMIN')
        """))
        
        uppercase_users = result.fetchall()
        
        if not uppercase_users:
            print("✅ No uppercase roles found. Database is already up to date.")
            return
        
        print(f"Found {len(uppercase_users)} users with uppercase roles:")
        for username, role in uppercase_users:
            print(f"  - {username}: {role}")
        
        print()
        print("Converting to lowercase...")
        print()
        
        # Update to lowercase
        updates = {
            'ADMIN': 'admin',
            'USER': 'user',
            'GUEST': 'guest',
            'SUPER_ADMIN': 'super_admin'
        }
        
        for old_role, new_role in updates.items():
            result = db.execute(
                text("UPDATE users SET role = :new_role WHERE role = :old_role"),
                {"new_role": new_role, "old_role": old_role}
            )
            if result.rowcount > 0:
                print(f"  ✅ Updated {result.rowcount} user(s) from '{old_role}' to '{new_role}'")
        
        db.commit()
        
        # Verify the fix
        print()
        result = db.execute(text("SELECT username, role FROM users"))
        all_users = result.fetchall()
        
        print(f"Final verification - All users ({len(all_users)}):")
        for username, role in all_users:
            print(f"  - {username}: {role}")
        
        print()
        print("=" * 60)
        print("✅ Role case migration completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    try:
        fix_role_case()
    except Exception as e:
        print(f"\n❌ Error during migration: {e}", file=sys.stderr)
        sys.exit(1)
