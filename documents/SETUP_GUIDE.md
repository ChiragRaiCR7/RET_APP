# RET-v4 Application - Setup & Deployment Guide

## Quick Start (Development)

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL (or SQLite for dev)
- Redis (for Celery task queue)

### Backend Setup

```bash
cd backend

# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
# or with uv:
uv pip install -r requirements.txt

# 3. Initialize database
python scripts/init_db.py

# 4. Create demo users
python scripts/create_admin.py

# 5. Start development server
python start.py
# Or manually:
uvicorn api.main:app --reload --port 8000
```

**API will be available at:** http://localhost:8000
**Swagger docs:** http://localhost:8000/docs

### Frontend Setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Start development server
npm run dev

# Or with vite directly:
npx vite
```

**Frontend will be available at:** http://localhost:5173

### Environment Configuration

Backend (.env):
```dotenv
APP_NAME=RET-v4
ENV=development
DEBUG=true
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=sqlite:///./ret_app.db
JWT_SECRET_KEY=your-secret-key
REDIS_URL=redis://localhost:6379/0
```

Frontend (.env):
```dotenv
VITE_API_BASE=http://localhost:8000/api
```

## Demo Credentials

After running setup scripts:
- **Admin:** `admin` / `admin123`
- **User:** `demo` / `password`

## Architecture Overview

### Backend (FastAPI)
- **Framework:** FastAPI with SQLAlchemy ORM
- **Database:** PostgreSQL (production) / SQLite (development)
- **Authentication:** JWT with HttpOnly cookies for refresh tokens
- **Workers:** Celery with Redis broker for async tasks
- **AI Integration:** Azure OpenAI for embeddings and chat
- **Vector DB:** ChromaDB for RAG (Retrieval-Augmented Generation)

### Frontend (Vue 3 + Vite)
- **Framework:** Vue 3 with Composition API
- **State Management:** Pinia
- **Routing:** Vue Router
- **HTTP Client:** Axios with interceptors
- **UI System:** Custom CSS design system
- **Accessibility:** WCAG 2.1 compliant

## Key Features

1. **Authentication**
   - Secure login with JWT tokens
   - Refresh token rotation via HttpOnly cookies
   - Password reset workflow
   - Multi-device session management

2. **File Processing**
   - ZIP file upload and scanning
   - XML to CSV/XLSX conversion
   - Batch processing with job tracking
   - Rate limiting and quota management

3. **Comparison Engine**
   - Session-to-session file comparison
   - Similarity scoring with cosine distance
   - Row-level diff detection
   - Change tracking and audit logs

4. **AI Features**
   - Vector embedding generation
   - Semantic search with RAG
   - Natural language chat interface
   - Citation tracking

5. **Admin Dashboard**
   - User management
   - Audit log viewing
   - System metrics
   - Permission management

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user
- `POST /api/auth/refresh` - Refresh token (uses HttpOnly cookie)
- `POST /api/auth/logout` - Logout
- `POST /api/auth/password-reset/request` - Request password reset
- `POST /api/auth/password-reset/confirm` - Confirm password reset

### File Operations
- `POST /api/conversion/scan` - Scan ZIP file
- `POST /api/conversion/convert` - Convert to CSV/XLSX
- `GET /api/conversion/download/{session_id}` - Download results

### Comparison
- `POST /api/comparison/compare` - Compare two sessions

### AI/Search
- `POST /api/ai/index` - Index session for search
- `POST /api/ai/chat` - Chat with indexed data

### Jobs
- `GET /api/jobs/{job_id}` - Get job status and progress

### Admin (requires admin role)
- `POST /api/admin/users` - Create user
- `GET /api/admin/users` - List users
- `PUT /api/admin/users/{id}` - Update user
- `DELETE /api/admin/users/{id}` - Delete user
- `GET /api/admin/audit-logs` - View audit logs
- `GET /api/admin/ops-logs` - View operational logs

## Deployment (Production)

### Database
```bash
# Use PostgreSQL
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/retdb

# Run migrations
alembic upgrade head
```

### Environment Variables
- Set `ENV=production`
- Set `DEBUG=false`
- Use strong `JWT_SECRET_KEY`
- Configure proper CORS_ORIGINS
- Set up external PostgreSQL and Redis

### Backend Deployment
```bash
# With Gunicorn
gunicorn api.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Or with Docker
docker build -t retv4-backend .
docker run -p 8000:8000 retv4-backend
```

### Frontend Deployment
```bash
# Build
npm run build

# Deploy dist/ folder to static host (Vercel, Netlify, S3, etc.)
```

### Celery Workers
```bash
celery -A api.workers.celery_app worker -l info
celery -A api.workers.celery_app beat -l info  # For scheduled tasks
```

## Troubleshooting

### Database Connection Issues
```bash
# Check if SQLite exists
ls -la backend/*.db

# Reset database
rm backend/ret_app.db
python scripts/init_db.py
```

### Redis Connection
```bash
# Check Redis
redis-cli ping  # Should return PONG

# Start Redis (macOS with homebrew)
brew services start redis

# Or Docker
docker run -d -p 6379:6379 redis:latest
```

### Port Already in Use
```bash
# Change port in vite.config.js or use environment:
PORT=3001 npm run dev
```

### CORS Issues
Check `CORS_ORIGINS` in backend .env matches frontend URL

## Development Best Practices

1. **Code Style**
   - Backend: Follow PEP 8
   - Frontend: ESLint configuration provided
   - Use type hints in Python and JSDoc in JS

2. **Testing**
   - Write unit tests for services
   - Integration tests for routers
   - E2E tests for critical flows

3. **Logging**
   - Backend: Using Loguru with structured logging
   - Frontend: Console logging with components
   - Use correlation IDs for request tracing

4. **Security**
   - Never commit .env files
   - Use strong passwords
   - Validate all inputs
   - Use HTTPS in production
   - Keep dependencies updated

## Support

For issues and questions, refer to:
- Backend docs: `backend/README.md`
- Frontend docs: `frontend/README.md`
- Architecture: `Backend.md` and `Frontend.md`
