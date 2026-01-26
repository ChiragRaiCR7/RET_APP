# RET v4 - Frontend & Backend Integration Guide

## Overview

This guide provides step-by-step instructions to run the RET v4 application locally without Docker. The application consists of:
- **Backend**: FastAPI server running on `http://localhost:8000`
- **Frontend**: Vue 3 + Vite app running on `http://localhost:3000`
- **Database**: SQLite (local dev) or PostgreSQL (production)
- **Cache**: Redis (for Celery tasks and rate limiting)

---

## Prerequisites

### System Requirements
- **Windows 10+** with PowerShell 5.1+
- **Python 3.10+** (3.12+ recommended)
- **Node.js 18+** with npm/yarn/pnpm
- **Redis** (Windows version available)

### Installation

#### 1. Python Setup
```powershell
# Check Python version
python --version

# Create virtual environment (in backend folder)
cd d:\WORK\RET_App\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

#### 2. Node.js Setup
```powershell
# Check Node version
node --version

# Install frontend dependencies
cd d:\WORK\RET_App\frontend
npm install
```

#### 3. Redis Setup (Windows)
**Option A: Using Windows Subsystem for Linux (WSL)**
```powershell
wsl
sudo apt-get update
sudo apt-get install redis-server
redis-server
```

**Option B: Using Docker**
```powershell
docker run -d -p 6379:6379 redis:latest
```

**Option C: Windows Binary**
Download from: https://github.com/microsoftarchive/redis/releases/latest

---

## Configuration

### Backend Configuration

1. **Update `.env` file** (already provided):
```
DATABASE_URL=sqlite:///./ret_app.db
JWT_SECRET_KEY=dev-secret-key-12345
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

2. **Initialize Database**:
```powershell
cd d:\WORK\RET_App\backend
python -c "from api.core.database import init_db; init_db()"
```

3. **Create Admin User** (optional):
```powershell
python scripts/create_admin.py
# Username: admin
# Password: (set your own)
```

### Frontend Configuration

1. **Check `.env` file** (already provided):
```
VITE_API_BASE=http://localhost:8000/api
```

---

## Running the Application

### Start Backend (Terminal 1)
```powershell
cd d:\WORK\RET_App\backend

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run FastAPI server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Start Frontend (Terminal 2)
```powershell
cd d:\WORK\RET_App\frontend
npm run dev
```

Expected output:
```
  VITE v7.2.4  ready in 123 ms

  ➜  Local:   http://localhost:3000/
  ➜  press h to show help
```

### Start Redis (Terminal 3) - If needed for Celery
```powershell
# If using Docker
docker run -p 6379:6379 redis:latest

# If using WSL
redis-server
```

### Access Application
Open browser and navigate to: `http://localhost:3000`

---

## Architecture & Integration Points

### Authentication Flow

1. **Login**
   - Frontend: `POST /api/auth/login` with `{username, password}`
   - Backend: Validates credentials, returns `{access_token, refresh_token, user}`
   - Frontend: Stores `access_token` in Pinia store (memory only)
   - Backend: Sets `refresh_token` as HttpOnly cookie

2. **API Requests**
   - Frontend: Axios adds `Authorization: Bearer <access_token>` header
   - Vite dev server proxies `/api/*` to `http://localhost:8000`
   - Backend validates token and processes request

3. **Token Refresh**
   - Frontend: On 401 response, calls `POST /api/auth/refresh`
   - Backend: Reads `refresh_token` from cookie, validates, rotates it
   - Returns new `access_token`

4. **Logout**
   - Frontend: Calls `POST /api/auth/logout`
   - Backend: Invalidates session, clears cookies
   - Frontend: Clears store, redirects to login

### API Endpoints

#### Authentication
- `POST /api/auth/login` - Login with username/password
- `GET /api/auth/me` - Get current user info
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout and clear session
- `POST /api/auth/password-reset/request` - Request password reset
- `POST /api/auth/password-reset/confirm` - Confirm password reset

#### Conversion (File Processing)
- `POST /api/conversion/scan` - Upload and scan ZIP file
- `POST /api/conversion/convert` - Convert XML to CSV
- `GET /api/conversion/download/{session_id}` - Download converted files
- `GET /api/conversion/status/{job_id}` - Check conversion status

#### Comparison
- `POST /api/comparison/compare` - Compare two sessions
- `GET /api/comparison/results/{job_id}` - Get comparison results

#### AI & Indexing
- `POST /api/ai/index` - Index session for AI search
- `POST /api/ai/chat` - Chat with AI about indexed content

#### Admin
- `GET /api/admin/users` - List users
- `POST /api/admin/users` - Create user
- `PUT /api/admin/users/{user_id}` - Update user
- `DELETE /api/admin/users/{user_id}` - Delete user

#### Jobs
- `GET /api/jobs/{job_id}` - Get job status and progress

---

## Troubleshooting

### Issue: CORS Error
**Problem**: Frontend cannot reach backend
**Solution**:
1. Verify backend is running on `http://localhost:8000`
2. Check `CORS_ORIGINS` in `.env`: should include `http://localhost:3000`
3. Restart both frontend and backend

### Issue: 401 Unauthorized
**Problem**: Access token expired or invalid
**Solution**:
1. Backend will automatically call refresh endpoint
2. If still failing, clear cookies and login again
3. Check JWT_SECRET_KEY matches in `.env`

### Issue: Database Not Found
**Problem**: `ret_app.db` doesn't exist
**Solution**:
```powershell
cd d:\WORK\RET_App\backend
python -c "from api.core.database import init_db; init_db()"
```

### Issue: Redis Connection Refused
**Problem**: Celery/Rate limiting fails
**Solution**:
1. Start Redis: `redis-server` or `docker run -p 6379:6379 redis:latest`
2. Verify `REDIS_URL=redis://localhost:6379/0` in `.env`
3. For local dev without Redis, set `REDIS_URL=redis://localhost:6379/1` and comment out rate limit middleware

### Issue: Port Already in Use
**Problem**: Port 8000 or 3000 already in use
**Solution**:
```powershell
# Find process using port 8000
Get-Process | Where-Object { $_.Handles -like "*8000*" }

# Kill process (replace PID)
Stop-Process -Id <PID> -Force

# Or change port in vite.config.js or uvicorn command
```

---

## Code Changes Summary

### Backend Changes
1. **`api/schemas/auth.py`**: Added user info to `TokenResponse`
2. **`api/services/auth_service.py`**: Modified to include user in login response
3. **`api/routers/auth_router.py`**: Added `/auth/me` and `/auth/logout` endpoints
4. **`api/core/config.py`**: Changed CORS_ORIGINS from `["*"]` to specific localhost URLs
5. **`api/services/session_service.py`**: Added `db.commit()` calls
6. **`.env`**: Added database, JWT, Redis, and CORS configuration

### Frontend Changes
1. **`src/stores/authStore.js`**: 
   - Changed from localStorage to memory-only token storage
   - Updated to match new login response format
   - Added `refreshToken()` action
   - Modified logout to call backend endpoint

2. **`src/utils/api.js`**:
   - Added `withCredentials: true` for cookie handling
   - Implemented 401 interceptor with token refresh retry logic
   - Added queue for failed requests during refresh

3. **`vite.config.js`**: Enhanced proxy configuration

4. **`.env`**: Added API base URL configuration

---

## Development Workflow

### Making API Calls from Frontend
```javascript
import api from '@/utils/api'

// GET request
const response = await api.get('/conversion/status/123')

// POST request
const response = await api.post('/conversion/convert', { session_id: '123' })

// Automatic features:
// - Adds Authorization header with access token
// - Sends/receives cookies
// - Retries on 401 with token refresh
// - Handles errors globally
```

### Testing Authentication
```javascript
// In browser console
import { useAuthStore } from '@/stores/authStore'
const auth = useAuthStore()

// Check login
await auth.login('admin', 'password')
console.log(auth.user)

// Check token refresh
await auth.refreshToken()

// Logout
await auth.logout()
```

### Backend Testing
```bash
cd backend
pytest tests/

# Or specific test
pytest tests/test_auth.py -v
```

---

## Production Deployment

For production, you'll need to:

1. **Change secrets**:
   - Generate new `JWT_SECRET_KEY`
   - Use strong database credentials
   - Set `DEBUG=false`

2. **Database**:
   - Use PostgreSQL instead of SQLite
   - Run Alembic migrations: `alembic upgrade head`

3. **Frontend**:
   - Build: `npm run build`
   - Deploy static files to CDN/web server
   - Update `VITE_API_BASE` to production API URL

4. **Backend**:
   - Use Gunicorn: `gunicorn api.main:app -w 4`
   - Set up Nginx reverse proxy
   - Enable HTTPS/SSL

5. **Workers** (Celery):
   - Run in separate process: `celery -A api.workers.celery_app worker`
   - Use task queue for file conversions

6. **Redis**:
   - Use managed Redis (AWS ElastiCache, Azure Cache, etc.)
   - Enable authentication and encryption

---

## Support

For issues or questions:
1. Check logs in both frontend and backend terminals
2. Verify all prerequisites are installed
3. Ensure `.env` files are properly configured
4. Check browser DevTools (F12) for frontend errors
5. Check backend console for API errors

---

## Quick Reference

| Component | Port | URL | Command |
|-----------|------|-----|---------|
| Backend | 8000 | `http://localhost:8000` | `uvicorn api.main:app --reload` |
| Frontend | 3000 | `http://localhost:3000` | `npm run dev` |
| Redis | 6379 | `redis://localhost:6379` | `redis-server` |
| API Docs | 8000 | `http://localhost:8000/docs` | (auto) |

---

**Version**: 4.0.0
**Last Updated**: January 25, 2026
