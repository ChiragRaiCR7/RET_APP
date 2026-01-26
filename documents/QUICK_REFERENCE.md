# RET-v4 Quick Reference Guide

## 🚀 Quick Start (< 5 Minutes)

### Prerequisites
```bash
python --version       # Python 3.12+
node --version        # Node.js 18+
npm --version         # npm 9+
```

### Backend Startup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/create_admin.py
python start.py                # Starts on http://localhost:8000
```

### Frontend Startup
```bash
cd frontend
npm install
npm run dev              # Starts on http://localhost:5173
```

### Login
- **Admin**: `admin` / `admin123`
- **User**: `demo` / `password`

---

## 🔧 Common Commands

### Terminal 3: Redis (Optional)
```powershell
redis-server
# or
docker run -p 6379:6379 redis:latest
```

## Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:3000 | Main application |
| Backend API | http://localhost:8000 | API endpoints |
| API Docs | http://localhost:8000/docs | Swagger UI |
| API ReDoc | http://localhost:8000/redoc | ReDoc UI |

## Default Credentials

Create admin user first:
```powershell
cd backend
python scripts/create_admin.py
```

Then login with created credentials.

## Key Files Modified

### Backend
- `api/schemas/auth.py` - Response format
- `api/services/auth_service.py` - Token generation
- `api/routers/auth_router.py` - New endpoints (/me, /logout)
- `api/core/config.py` - CORS configuration
- `.env` - Local configuration

### Frontend
- `src/stores/authStore.js` - Token management
- `src/utils/api.js` - Axios with 401 handling
- `vite.config.js` - Proxy setup
- `.env` - API endpoint

## API Endpoints

### Authentication
```bash
POST   /api/auth/login                    # Login
GET    /api/auth/me                       # Current user
POST   /api/auth/refresh                  # Refresh token
POST   /api/auth/logout                   # Logout
POST   /api/auth/password-reset/request   # Request reset
POST   /api/auth/password-reset/confirm   # Confirm reset
```

### Conversion
```bash
POST   /api/conversion/scan               # Upload & scan
POST   /api/conversion/convert            # Start conversion
GET    /api/conversion/status/{job_id}    # Job status
GET    /api/conversion/download/{sid}     # Download results
```

### Comparison
```bash
POST   /api/comparison/compare            # Compare sessions
GET    /api/comparison/results/{job_id}   # Results
```

### AI
```bash
POST   /api/ai/index                      # Index session
POST   /api/ai/chat                       # Chat query
```

### Admin
```bash
GET    /api/admin/users                   # List users
POST   /api/admin/users                   # Create user
PUT    /api/admin/users/{id}              # Update user
DELETE /api/admin/users/{id}              # Delete user
```

## Common Commands

```powershell
# Initialize database
python -c "from api.core.database import init_db; init_db()"

# Create admin user
python scripts/create_admin.py

# Run migrations
alembic upgrade head

# Check logs
Get-Content .\api\logs\*.log

# Kill port 8000
Get-Process | Where-Object {$_.Handles -like "*8000*"} | Stop-Process -Force
```

## Testing

```bash
# Backend tests
cd backend
pytest tests/

# Frontend build
cd frontend
npm run build

# Frontend preview
npm run preview
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Logout & login again |
| CORS error | Check CORS_ORIGINS in .env |
| Connection refused | Start backend with uvicorn |
| Module not found | `pip install -r requirements.txt` |
| Port in use | Kill process or change port |
| Redis error | Start Redis or skip for SQLite jobs |

## Environment Variables

### Backend `.env`
```env
DATABASE_URL=sqlite:///./ret_app.db
JWT_SECRET_KEY=dev-secret-key-12345
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

### Frontend `.env`
```env
VITE_API_BASE=http://localhost:8000/api
```

## Architecture

```
Frontend (Vue 3 + Vite) :3000
    ↓ (Vite proxy)
    ↓ /api → http://localhost:8000
    ↓
Backend (FastAPI) :8000
    ↓
    ├─ SQLite Database (./ret_app.db)
    ├─ Redis Cache (localhost:6379)
    └─ Celery Workers
```

## Token Lifecycle

```
1. Login → /api/auth/login
   ↓
2. Receive: access_token + refresh_token
   ↓
3. Store: access_token in memory
   ↓
4. Store: refresh_token in HttpOnly cookie (automatic)
   ↓
5. API calls: Send access_token in Authorization header
   ↓
6. On 401: Auto-refresh via /api/auth/refresh
   ↓
7. Logout: POST /api/auth/logout → Clear tokens
```

## Browser DevTools Debugging

### Network Tab
- Filter by "/api"
- Check request headers (Authorization)
- Check response status (200, 401, 403)
- Look at cookies (refresh_token)

### Console
- `import { useAuthStore } from '@/stores/authStore'`
- `const auth = useAuthStore(); console.log(auth.user)`
- Check for JavaScript errors (red text)

### Storage (Application Tab)
- Cookies: look for `refresh_token`
- LocalStorage: should be empty (no tokens here!)
- SessionStorage: check for temporary data

## Git Workflow

```bash
# Check status
git status

# Stage changes
git add .

# Commit
git commit -m "feat: integrate frontend and backend"

# Push
git push origin main
```

## Performance Tips

1. **Frontend**: 
   - Use Vue DevTools extension
   - Monitor Network tab
   - Check bundle size: `npm run build`

2. **Backend**:
   - Enable DEBUG mode locally
   - Check slow queries with logging
   - Monitor Redis with `redis-cli monitor`

3. **Database**:
   - Use SQLite for dev, PostgreSQL for prod
   - Run migrations: `alembic upgrade head`

## Production Checklist

Before deploying:
- [ ] Change JWT_SECRET_KEY
- [ ] Use PostgreSQL instead of SQLite
- [ ] Enable HTTPS/SSL
- [ ] Update CORS_ORIGINS
- [ ] Set DEBUG=false
- [ ] Use strong database password
- [ ] Set up Redis Cluster
- [ ] Enable logging & monitoring
- [ ] Backup database regularly
- [ ] Update dependencies

## Support & Documentation

- **Setup Guide**: `./SETUP.md`
- **Testing Guide**: `./TESTING.md`
- **Integration Changes**: `./INTEGRATION_CHANGES.md`
- **Backend README**: `./backend/README.md`
- **Frontend README**: `./frontend/README.md`

## Version Info

- **RET App**: v4.0.0
- **FastAPI**: 0.128.0
- **Vue**: 3.5.24
- **Python**: 3.10+
- **Node**: 18+

---

**Last Updated**: January 25, 2026
**Status**: Ready for Local Development Testing
