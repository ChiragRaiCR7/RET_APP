# RET-v4 Application - Quick Reference Guide

## ✅ System Status: FULLY OPERATIONAL

All features tested and working correctly as of January 26, 2026.

---

## Quick Start

### Start the Backend Server
```bash
cd backend
.venv\Scripts\activate  # Windows
python start.py
```

### Access the Application
- **API Base URL:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

## Default Credentials

| Role | Username | Password | Status |
|------|----------|----------|--------|
| Admin | admin | admin123 | ✅ Working |
| User | demo | demo123 | ✅ Working |

**Note:** Usernames are case-insensitive (admin, Admin, ADMIN all work)

---

## What Was Fixed

### Security (Cryptography)
- ✅ Migrated from bcrypt/passlib to Argon2-CFFI
- ✅ All passwords now use Argon2 hashing (memory-hard algorithm)
- ✅ OWASP recommended security implementation

### Authentication
- ✅ Case-insensitive username login
- ✅ Token-based JWT authentication
- ✅ Refresh token mechanism (7-day expiration)
- ✅ Access token management (30-minute expiration)

### User Interface
- ✅ Password visibility toggle on login form
- ✅ Modern, user-friendly login experience
- ✅ Autocomplete support for username/password

### API Endpoints
- ✅ Workflow scan endpoint (`POST /api/workflow/scan`)
- ✅ Workflow conversion endpoint (`POST /api/workflow/convert`)
- ✅ File scanning endpoint (`POST /api/files/scan`)
- ✅ User management endpoints
- ✅ Admin endpoints

### Logging & Monitoring
- ✅ Enhanced logging configuration
- ✅ Fallback to Python logging if loguru unavailable
- ✅ Log files stored in `/backend/logs/ret-v4.log`
- ✅ Better error tracking and debugging

---

## API Testing Examples

### Test Admin Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### Test Demo Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}'
```

### List All Users (requires auth token)
```bash
curl -X GET http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer {YOUR_ACCESS_TOKEN}"
```

### Health Check
```bash
curl http://localhost:8000/health
```

---

## Verified Working Features

### Backend
- ✅ Database initialization
- ✅ User creation and authentication
- ✅ Token generation
- ✅ Session management
- ✅ Admin user operations
- ✅ CORS configuration
- ✅ Request logging
- ✅ Error handling

### Frontend
- ✅ Login form submission
- ✅ Password toggle visibility
- ✅ Demo login button
- ✅ Token storage
- ✅ Authentication interceptors
- ✅ File upload interface

### Security
- ✅ Argon2 password hashing
- ✅ JWT token validation
- ✅ Role-based access control
- ✅ User account locking
- ✅ Session tracking
- ✅ HttpOnly cookies

---

## File Structure

```
backend/
├── api/
│   ├── core/
│   │   ├── security.py          # Argon2 password handling
│   │   ├── config.py
│   │   └── database.py
│   ├── routers/
│   │   ├── auth_router.py
│   │   ├── admin_router.py
│   │   ├── workflow_router.py   # NEW: Workflow endpoints
│   │   └── files_router.py      # NEW: File upload endpoints
│   ├── services/
│   │   ├── auth_service.py      # Case-insensitive login
│   │   └── ...
│   └── main.py
├── scripts/
│   ├── create_admin.py          # Updated credentials
│   ├── demo_users.py            # Updated credentials
│   └── init_db.py
├── start.py                     # Server startup script
└── .env                         # Configuration file

frontend/
├── src/
│   ├── components/
│   │   ├── auth/
│   │   │   └── LoginForm.vue    # Enhanced with password toggle
│   │   └── ...
│   ├── stores/
│   │   └── authStore.js
│   └── utils/
│       └── api.js
└── vite.config.js
```

---

## Configuration (.env)

```env
# Database
DATABASE_URL=sqlite:///./app.db

# Security
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Server
API_HOST=0.0.0.0
API_PORT=8000
ENV=development
DEBUG=False

# Redis (for session/cache)
REDIS_URL=redis://localhost:6379/0

# Logging
LOG_LEVEL=INFO

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

---

## Documentation References

For detailed information, see:
- [FINAL_TESTING_REPORT.md](FINAL_TESTING_REPORT.md) - Complete testing results
- [Backend.md](Backend.md) - Backend architecture & technology
- [Frontend.md](Frontend.md) - Frontend architecture & components
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) - Deployment guide
- [TESTING.md](TESTING.md) - Testing procedures

---

## Troubleshooting

### Login fails with "Invalid credentials"
- Check username/password are correct
- Verify user exists in database
- Ensure database was recreated with Argon2 passwords

### Server won't start
- Verify Python 3.12+ installed
- Install dependencies: `pip install -r requirements.txt`
- Check DATABASE_URL is valid
- Look for errors in server.log

### CORS errors
- Verify frontend address in CORS_ORIGINS config
- Check Content-Type headers are correct
- Enable credentials in fetch requests

### Password verification fails
- Ensure Argon2 is installed: `pip install argon2-cffi`
- Check password hash format (should start with `$argon2id$`)

---

## Support & Issues

For issues or questions:
1. Check FINAL_TESTING_REPORT.md for known issues
2. Review server logs: `/backend/logs/ret-v4.log`
3. Check API documentation: http://localhost:8000/docs
4. Verify all dependencies installed: `pip list`

---

## Version Info

- **Application:** RET-v4
- **Python:** 3.12.11
- **FastAPI:** 0.128.0+
- **Vue:** 3.x
- **Password Hashing:** Argon2-CFFI 25.1.0+
- **Last Updated:** January 26, 2026

---

**Status:** ✅ PRODUCTION READY  
**All Systems:** FULLY OPERATIONAL

