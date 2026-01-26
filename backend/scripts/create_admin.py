from api.core.database import SessionLocal
from api.models import User
from api.core.security import hash_password

def create_admin():
    db = SessionLocal()
    try:
        # Check if admin already exists
        existing = db.query(User).filter(User.username == "admin").first()
        if existing:
            print("[!] Admin user already exists")
            return
        
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
            is_active=True,
            is_locked=False,
        )
        db.add(admin)
        
        # Create demo user
        demo = User(
            username="demo",
            password_hash=hash_password("demo123"),
            role="user",
            is_active=True,
            is_locked=False,
        )
        db.add(demo)
        
        db.commit()
        print("[+] Admin user created (username: admin, password: admin123)")
        print("[+] Demo user created (username: demo, password: demo123)")
    except Exception as e:
        db.rollback()
        print(f"[-] Error creating users: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()
