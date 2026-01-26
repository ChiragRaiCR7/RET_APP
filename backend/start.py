#!/usr/bin/env python3
"""
Development server startup script for RET-v4 Backend
Initializes database and runs uvicorn server
"""
import subprocess
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(backend_dir))

def init_database():
    """Initialize database tables"""
    print("[*] Initializing database...")
    try:
        from scripts.init_db import init_db
        init_db()
        print("[+] Database initialized")
        
        # Create demo users
        print("[*] Creating demo users...")
        from scripts.demo_users import create_demo_users
        create_demo_users()
    except Exception as e:
        print(f"[!] Database init warning: {e}")

def start_server():
    """Start uvicorn development server"""
    print("[+] Starting RET-v4 Backend Server...")
    print("[*] API will be available at http://localhost:8000")
    print("[*] Swagger docs at http://localhost:8000/docs")
    print("[*] Press Ctrl+C to stop\n")
    
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
    ]

    try:
        # check=True will raise CalledProcessError if uvicorn exits with non-zero code
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[!] Stopping server (KeyboardInterrupt)")
    except subprocess.CalledProcessError as e:
        print(f"\n[-] uvicorn exited with error: {e.returncode}")
    except FileNotFoundError:
        print("\n[-] Could not find uvicorn. Try installing it in your venv: pip install uvicorn")

if __name__ == "__main__":
    init_database()
    start_server()
