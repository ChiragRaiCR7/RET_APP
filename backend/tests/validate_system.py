#!/usr/bin/env python3
"""
RET-v4 System Validation & Diagnostic Tool
Checks database, environment, dependencies, and configuration
"""
import sys
from pathlib import Path

def check_python_version():
    """Verify Python 3.12+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 12):
        print(f"❌ Python {version.major}.{version.minor} detected. Requires Python 3.12+")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_environment():
    """Check environment variables"""
    import os
    from dotenv import load_dotenv
    
    backend_dir = Path(__file__).parent
    env_file = backend_dir / ".env"
    
    if not env_file.exists():
        print(f"⚠️  .env file not found at {env_file}")
        return False
    
    load_dotenv(env_file)
    
    required_vars = [
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "RET_SESSION_DB",
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        return False
    
    print("✅ Environment variables configured")
    return True

def check_database():
    """Test database connection"""
    try:
        from api.core.config import settings
        from api.core.database import engine
        
        with engine.connect() as conn:
            print("✅ Database connection successful")
            return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def check_session_cache():
    """Test session cache initialization"""
    try:
        from api.core.session_cache import get_session_cache
        
        cache = get_session_cache()
        # Test basic operations
        cache.set("test_key", "test_value", ttl_seconds=60)
        result = cache.get("test_key")
        
        if result == "test_value":
            print("✅ Session cache initialized successfully")
            return True
        else:
            print("❌ Session cache test failed")
            return False
    except Exception as e:
        print(f"❌ Session cache error: {e}")
        return False

def check_models():
    """Verify database models"""
    try:
        from api.models import (
            User, LoginSession, PasswordResetToken, PasswordResetRequest,
            UserLimit, LimitIncreaseRequest, AuditLog, OpsLog, ErrorEvent, Job
        )
        print("✅ All database models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Model import error: {e}")
        return False

def check_routers():
    """Verify API routers"""
    try:
        from api.routers import (
            auth_router, conversion_router, comparison_router,
            ai_router, admin_router, job_router
        )
        print("✅ All routers imported successfully")
        return True
    except Exception as e:
        print(f"❌ Router import error: {e}")
        return False

def check_services():
    """Verify services"""
    try:
        from api.services import (
            auth_service, admin_service, conversion_service,
            comparison_service, ai_service, job_service
        )
        print("✅ All services imported successfully")
        return True
    except Exception as e:
        print(f"❌ Service import error: {e}")
        return False

def check_app():
    """Test FastAPI app creation"""
    try:
        from api.main import app
        print("✅ FastAPI application initialized successfully")
        return True
    except Exception as e:
        print(f"❌ FastAPI initialization error: {e}")
        return False

def check_tables():
    """Verify database tables exist"""
    try:
        from api.core.database import engine, Base
        from api.models import User
        
        # Try to query users table
        with engine.connect() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            if result.fetchone():
                print("✅ Database tables exist")
                return True
            else:
                print("⚠️  Database tables not initialized")
                print("    Run: python scripts/init_db.py")
                return False
    except Exception as e:
        print(f"⚠️  Table check error: {e}")
        return False

def main():
    """Run all checks"""
    print("\n" + "="*60)
    print("RET-v4 System Validation")
    print("="*60 + "\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("Environment", check_environment),
        ("Database", check_database),
        ("Session Cache", check_session_cache),
        ("Models", check_models),
        ("Routers", check_routers),
        ("Services", check_services),
        ("FastAPI App", check_app),
        ("Database Tables", check_tables),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n🔍 Checking {name}...")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} check failed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All checks passed! System is ready.")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please fix issues before deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
