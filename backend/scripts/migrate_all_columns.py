"""
Comprehensive migration script to add all missing columns to users table
"""
import sqlite3
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.absolute()
db_path = backend_dir / "test.db"

if not db_path.exists():
    print(f"[!] Database not found at {db_path}")
    sys.exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get current columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {info[1] for info in cursor.fetchall()}

    print(f"[*] Current columns: {existing_columns}")

    # Define all required columns with their types and defaults
    required_columns = {
        "is_deleted": ("BOOLEAN", "0"),
        "failed_login_attempts": ("INTEGER", "0"),
        "locked_until": ("DATETIME", "NULL"),
    }

    # Add missing columns
    added = []
    for col_name, (col_type, default_val) in required_columns.items():
        if col_name not in existing_columns:
            if default_val == "NULL":
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            else:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type} DEFAULT {default_val}")
            added.append(col_name)
            print(f"[+] Added column: {col_name}")

    if added:
        conn.commit()
        print(f"[+] Successfully added {len(added)} column(s): {', '.join(added)}")
    else:
        print("[*] All required columns already exist")

    conn.close()

except Exception as e:
    print(f"[-] Error: {e}")
    sys.exit(1)
