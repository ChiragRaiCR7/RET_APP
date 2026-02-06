"""
Migration script to add is_deleted column to users table
Run this if you need to preserve existing data instead of recreating the database
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

    # Check if column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]

    if "is_deleted" in columns:
        print("[!] Column 'is_deleted' already exists in users table")
    else:
        # Add the column
        cursor.execute("ALTER TABLE users ADD COLUMN is_deleted BOOLEAN DEFAULT 0")
        conn.commit()
        print("[+] Successfully added is_deleted column to users table")

    conn.close()

except Exception as e:
    print(f"[-] Error: {e}")
    sys.exit(1)
