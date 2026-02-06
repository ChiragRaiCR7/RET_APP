# RET v4 Backend - Complete Setup & Usage Guide

## 📋 Table of Contents
1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Installation & Setup](#installation--setup)
4. [Database Configuration](#database-configuration)
5. [User Management](#user-management)
6. [Running the Application](#running-the-application)
7. [API Documentation](#api-documentation)
8. [Architecture](#architecture)
9. [Troubleshooting](#troubleshooting)
10. [Development Workflow](#development-workflow)

---

## 📱 Overview

**RET v4** (Resource Extraction Tool v4) is a professional enterprise web application that provides:

### Core Features
- **XML to CSV/XLSX Conversion Pipeline**: Process bulk ZIP archives with nested XML files
- **Multi-tenant User Management**: Role-based access control (RBAC) with 3 user roles
- **Azure OpenAI Integration**: AI-powered RAG (Retrieval-Augmented Generation) chat
- **Secure Authentication**: JWT-based with refresh tokens and HttpOnly cookies
- **Comprehensive Audit Logging**: Track all user actions and system events
- **Session Management**: Secure session handling with automatic cleanup

### Technology Stack
```
Backend: FastAPI (Python 3.12+)
Database: PostgreSQL (production) / SQLite (development)
ORM: SQLAlchemy 2.0+
Authentication: JWT, bcrypt, Argon2
Vector Database: ChromaDB
LLM: Azure OpenAI (GPT-4, embeddings)
```

---

## 🖥️ System Requirements

### Prerequisites
- **Python**: 3.12 or higher
- **pip**: Latest version
- **Virtual Environment**: venv (recommended)
- **Database**: SQLite for dev, PostgreSQL for production
- **Azure Credentials** (optional for AI features):
  - Azure OpenAI API key
  - Azure OpenAI endpoint
  - Deployment names for chat and embedding models

### Development Machine
- **OS**: Windows, macOS, or Linux
- **Disk Space**: 2GB minimum
- **RAM**: 4GB minimum (8GB recommended)
- **Port Access**: 8000 (backend API)

---

## 🚀 Installation & Setup

### Step 1: Clone & Navigate

```powershell
# Navigate to backend directory
cd d:\WORK\RET_App\backend
```

### Step 2: Create Virtual Environment

```powershell
# On Windows
python -m venv .venv
.venv\Scripts\Activate.ps1

# On macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```powershell
# Install in development mode with all extras
pip install -e ".[dev]"

# Or just base dependencies
pip install -e .
```

**Key dependencies** (auto-installed):
- `fastapi>=0.104.0` - Web framework
- `uvicorn>=0.24.0` - ASGI server
- `sqlalchemy>=2.0.0` - ORM
- `psycopg2-binary` - PostgreSQL adapter
- `pydantic>=2.0.0` - Data validation
- `python-jose>=3.3.0` - JWT handling
- `passlib[bcrypt]>=1.7.4` - Password hashing
- `chromadb>=0.4.0` - Vector database
- `openai>=1.0.0` - Azure OpenAI client
- `pandas>=2.0.0` - Data processing
- `openpyxl>=3.1.0` - Excel support
- `lxml>=4.9.0` - XML parsing

### Step 4: Configure Environment Variables

Create `.env` file in backend directory:

```bash
# ===== DATABASE =====
DATABASE_URL=sqlite:///./ret.db
# For production PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost:5432/retdb

# ===== SECURITY =====
SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_SECONDS=3600
REFRESH_TOKEN_EXPIRE_SECONDS=604800

# ===== AZURE OPENAI =====
AZURE_OPENAI_API_KEY=your-azure-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# ===== APPLICATION =====
APP_ENV=development
DEBUG=True
LOG_LEVEL=INFO

# ===== STORAGE =====
RUNTIME_ROOT=./runtime

# ===== CORS =====
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## 🗄️ Database Configuration

### SQLite (Development - Default)

SQLite is automatically configured for development:
```python
# Automatic: DATABASE_URL=sqlite:///./ret.db
Database file: backend/ret.db
```

### PostgreSQL (Production)

For production, configure PostgreSQL:

```bash
# 1. Create database and user
createdb retdb
createuser ret_user -P  # Enter password when prompted

# 2. Grant privileges
psql -d retdb
GRANT ALL PRIVILEGES ON DATABASE retdb TO ret_user;
\q

# 3. Update .env
DATABASE_URL=postgresql://ret_user:password@localhost:5432/retdb
```

### Initialize Database

The database is automatically initialized on first run (see `scripts/init_db.py`):

```powershell
# Manual initialization (if needed)
python scripts/init_db.py
```

**Tables created**:
- `users` - User accounts
- `login_sessions` - Active JWT sessions
- `password_reset_tokens` - Password reset workflows
- `password_reset_requests` - Admin approval workflow
- `audit_logs` - Immutable audit trail
- `ops_logs` - Operational logging
- `error_events` - Error tracking

---

## 👥 User Management

### User Roles & Permissions

| Role | Access Level | Permissions |
|------|-------------|-------------|
| **ADMIN** | Full system | Create users, approve resets, view logs, access main app |
| **USER** | Standard | Upload files, convert XML, chat with AI, download exports |
| **GUEST** | Limited | Read-only access (future feature) |

### Creating Demo Users

Demo users are automatically created on first run:

```
username: admin
password: admin123
role: ADMIN

username: demo
password: demo123
role: USER
```

Located in `scripts/demo_users.py`

### Create User via Script

```powershell
python scripts/create_admin.py --username newadmin --password SecurePass123! --role ADMIN
```

### Create User Programmatically

```python
from api.core.database import SessionLocal
from api.models.models import User
from api.core.security import hash_password

db = SessionLocal()

new_user = User(
    username="john.doe",
    password_hash=hash_password("SecurePassword123!"),
    role="USER",
    is_active=True,
    is_locked=False,
)

db.add(new_user)
db.commit()
print(f"Created user: {new_user.username}")
db.close()
```

### Password Requirements

- Minimum 8 characters
- At least 1 uppercase letter (A-Z)
- At least 1 lowercase letter (a-z)
- At least 1 digit (0-9)
- At least 1 special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

### User Lockout Policy

- **Failed Attempts**: 5 consecutive failed logins
- **Lockout Duration**: 15 minutes
- **Reset**: Automatically after lockout expires
- **Admin Override**: Admins can manually unlock users

---

## ▶️ Running the Application

### Quick Start (Development)

```powershell
# From backend directory with venv activated
python start.py

# Output:
# [*] Initializing database...
# [+] Database initialized
# [*] Creating demo users...
# [+] Created user 'admin'
# [+] Created user 'demo'
# [+] Starting RET-v4 Backend Server...
# [*] API will be available at http://localhost:8000
# [*] Swagger docs at http://localhost:8000/docs
# [*] Press Ctrl+C to stop
```

### Manual Server Start

```powershell
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Flags explained:
# --reload: Restart on code changes (development only)
# --host 0.0.0.0: Listen on all interfaces
# --port 8000: Use port 8000
```

### Production Deployment

```powershell
# Without reload (production)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# With gunicorn (recommended)
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker api.main:app --bind 0.0.0.0:8000
```

---

## 📚 API Documentation

### Interactive Docs

Once running, access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Authentication Flow

#### 1. Login & Get Tokens

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

**Response**:
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "ADMIN",
    "is_active": true
  }
}
```

#### 2. Use Access Token

```bash
curl -X GET "http://localhost:8000/api/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 3. Refresh Access Token

```bash
# Refresh token is HttpOnly cookie (auto-sent)
curl -X POST "http://localhost:8000/api/auth/refresh" \
  -H "Cookie: refresh_token=YOUR_REFRESH_TOKEN"
```

### Main API Endpoints

#### Authentication (`/api/auth`)
- `POST /login` - Login and get JWT
- `GET /me` - Get current user info
- `POST /logout` - Logout and revoke tokens
- `POST /refresh` - Refresh access token
- `POST /password-reset/request` - Request password reset
- `POST /password-reset/confirm` - Confirm with reset token

#### Conversion (`/api/conversion`)
- `POST /scan` - Scan ZIP file for XML structure
- `POST /convert` - Convert XML files to CSV/XLSX
- `GET /download/{session_id}` - Download converted files
- `GET /groups/{session_id}` - List available groups

#### AI & RAG (`/api/v2/ai`)
- `POST /chat` - Chat with RAG engine
- `POST /index/groups` - Index documents for search
- `GET /index/groups` - Get indexable groups
- `GET /sessions` - List AI sessions
- `POST /transcript/download` - Export chat history

#### Admin (`/api/admin`)
- `GET /users` - List all users
- `POST /users` - Create new user
- `PUT /users/{user_id}` - Update user
- `DELETE /users/{user_id}` - Delete user
- `POST /users/{user_id}/unlock` - Unlock account
- `GET /audit-logs` - View audit trail
- `GET /ops-logs` - View operational logs

---

## 🏗️ Architecture

### Directory Structure

```
backend/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app initialization
│   ├── core/
│   │   ├── config.py           # Settings & configuration
│   │   ├── database.py         # SQLAlchemy setup
│   │   ├── security.py         # JWT & password functions
│   │   ├── dependencies.py     # DI container
│   │   ├── exceptions.py       # Custom exceptions
│   │   ├── rbac.py             # Role-based access control
│   │   └── session_cache.py    # Redis/memory cache
│   ├── models/
│   │   └── models.py           # SQLAlchemy ORM models
│   ├── schemas/
│   │   ├── auth.py             # Auth request/response models
│   │   ├── conversion.py       # Conversion schemas
│   │   ├── ai.py               # AI/RAG schemas
│   │   ├── admin.py            # Admin schemas
│   │   └── common.py           # Shared models
│   ├── routers/
│   │   ├── auth_router.py      # Auth endpoints
│   │   ├── conversion_router.py  # File conversion endpoints
│   │   ├── ai_router.py        # AI/chat endpoints
│   │   ├── admin_router.py     # Admin endpoints
│   │   └── job_router.py       # Job status tracking
│   ├── services/
│   │   ├── auth_service.py     # Auth logic
│   │   ├── user_service.py     # User CRUD
│   │   ├── conversion_service.py # XML→CSV conversion
│   │   ├── ai_indexing_service.py # Vector indexing
│   │   ├── rag_service.py      # RAG/chat engine
│   │   └── storage_service.py  # File operations
│   ├── utils/
│   │   ├── xml_utils.py        # XML parsing helpers
│   │   ├── csv_utils.py        # CSV generation
│   │   ├── file_utils.py       # File operations
│   │   └── vector_utils.py     # Vector operations
│   ├── middleware/
│   │   ├── correlation_id.py   # Request tracing
│   │   ├── error_handler.py    # Error handling
│   │   ├── logging_middleware.py # Request logging
│   │   └── security_headers.py # Security headers
│   ├── workers/
│   │   ├── base_task.py        # Base task class
│   │   ├── conversion_worker.py # Async conversion
│   │   └── comparison_worker.py # File comparison
│   └── integrations/
│       ├── azure_openai.py     # Azure OpenAI client
│       └── chroma_client.py    # ChromaDB wrapper
├── scripts/
│   ├── init_db.py              # Database initialization
│   ├── demo_users.py           # Demo user creation
│   ├── create_admin.py         # Admin creation script
│   └── cleanup_sessions.py     # Session cleanup
├── tests/
│   ├── test_auth.py            # Auth tests
│   ├── test_workflow.py        # Workflow tests
│   ├── integration_test.py     # Integration tests
│   └── e2e/                    # End-to-end tests
├── runtime/
│   ├── sessions/               # User session data
│   └── ai_sessions/            # AI chat sessions
├── logs/                       # Application logs
├── .env                        # Environment variables
├── .env.example                # Example env
├── pyproject.toml              # Dependencies & metadata
├── alembic.ini                 # Database migrations
└── start.py                    # Development server launcher
```

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────┐
│  Frontend (Vue 3 / Browser)                         │
└────────────┬─────────────────────────────────────────┘
             │ HTTP/JSON
             ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI Application (api/main.py)                  │
├──────────────────────────────────────────────────────┤
│ Middleware Stack:                                   │
│ ├─ Correlation ID tracking                         │
│ ├─ Security headers                                │
│ ├─ CORS configuration                              │
│ ├─ Request logging                                 │
│ └─ Error handling                                  │
└────────────┬─────────────────────────────────────────┘
             │
     ┌───────┼────────┐
     ▼       ▼        ▼
   Auth     Conversion AI/RAG
  routers   routers   routers
     │       │        │
     └───────┴────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│  Services Layer (api/services/)                     │
├──────────────────────────────────────────────────────┤
│ ├─ AuthService (JWT, passwords)                    │
│ ├─ UserService (CRUD)                              │
│ ├─ ConversionService (XML→CSV)                     │
│ ├─ AIService (RAG, embeddings)                     │
│ └─ StorageService (files)                          │
└────────────┬─────────────────────────────────────────┘
             │
     ┌───────┼───────────────┐
     ▼       ▼               ▼
 Database  File Storage  Vector Store
 (PostgreSQL (Sessions)  (ChromaDB)
  /SQLite)     │
     │         ▼
     │    runtime/
     │    sessions/
     │    {session_id}/
     │    ├── uploads/
     │    ├── extracted/
     │    ├── output/
     │    └── ai_index/
     │
     ▼
┌──────────────────────────────────────────────────────┐
│  Database Schema                                   │
├──────────────────────────────────────────────────────┤
│ ├─ users (id, username, role, password_hash)      │
│ ├─ login_sessions (token_hash, user_id)           │
│ ├─ password_reset_tokens (token_hash, user_id)    │
│ ├─ audit_logs (action, username, timestamp)       │
│ ├─ ops_logs (action, area, message)               │
│ └─ error_events (phase, error_type, message)      │
└──────────────────────────────────────────────────────┘
```

### Authentication Flow

```
┌─────────┐
│ Browser │
└────┬────┘
     │ 1. POST /api/auth/login
     │    {username, password}
     ▼
┌──────────────────────┐
│ auth_router.login()  │
│ authenticate_user()  │ ◄── Hash check
└────┬────────────────┘
     │ 2. Issue JWT tokens
     ▼
┌──────────────────────┐
│ issue_tokens()       │ ◄── Returns access_token
│                      │      + refresh_token (cookie)
└────┬────────────────┘
     │ 3. Response: TokenResponse
     ▼
┌─────────────────────────┐
│ Browser stores:         │
│ - access_token (memory) │
│ - refresh_token (cookie)│ ◄── HttpOnly, Secure
└─────────────────────────┘

4. Subsequent requests:
   Authorization: Bearer {access_token}
   Cookie: refresh_token={refresh_token}

5. When access_token expires:
   POST /api/auth/refresh ◄── refresh_tokens()
   Returns new access_token
```

---

## 🔐 Security Features

### Authentication
- ✅ **JWT Tokens**: Stateless, time-limited
- ✅ **Refresh Tokens**: Long-lived, HttpOnly cookies
- ✅ **bcrypt Password Hashing**: Industry-standard with salt
- ✅ **Token Expiry**: Access (1 hour), Refresh (7 days)

### Authorization
- ✅ **Role-Based Access Control (RBAC)**: 3 roles (ADMIN, USER, GUEST)
- ✅ **Dependency Injection**: `get_current_user` enforces auth
- ✅ **Route Protection**: All sensitive endpoints require auth

### Input Validation
- ✅ **Pydantic Models**: Automatic request validation
- ✅ **SQL Injection Prevention**: SQLAlchemy parameterized queries
- ✅ **Path Traversal Prevention**: Validated file paths
- ✅ **ZIP Bomb Prevention**: Compression ratio limits (200:1)

### Audit & Compliance
- ✅ **Immutable Audit Logs**: All admin actions tracked
- ✅ **Operational Logs**: System events and errors
- ✅ **Correlation IDs**: Request tracing across services
- ✅ **Data Retention**: Configurable log retention

### HTTP Security
- ✅ **CORS**: Configured allow-list
- ✅ **CSRF**: SameSite cookies
- ✅ **XSS**: Content Security Policy headers
- ✅ **Secure Cookies**: HttpOnly, Secure flags

---

## 🛠️ Troubleshooting

### Issue: "Connection Refused" on Port 8000

**Solution**:
```powershell
# Check if port is in use
netstat -ano | findstr :8000

# Kill process if needed
taskkill /PID {PID} /F

# Try different port
uvicorn api.main:app --port 8001
```

### Issue: Database Lock (SQLite)

**Solution**:
```powershell
# Remove lock file
rm ret.db-journal

# Restart server
python start.py
```

### Issue: ModuleNotFoundError

**Solution**:
```powershell
# Ensure venv is activated
.venv\Scripts\Activate.ps1

# Reinstall dependencies
pip install -e .
```

### Issue: "User 'user' is not among defined enum values"

**Solution**: This has been fixed in latest code. The enum now uses uppercase:
```python
# Before (wrong)
role: "user", "admin"

# After (correct)
role: "USER", "ADMIN"
```

If you have old data:
```powershell
# Option 1: Delete database and restart
del ret.db
python start.py

# Option 2: Update existing records
python -c "
from api.core.database import SessionLocal
from api.models.models import User
db = SessionLocal()
for user in db.query(User).all():
    if user.role == 'user': user.role = 'USER'
    elif user.role == 'admin': user.role = 'ADMIN'
db.commit()
"
```

### Issue: Import Errors in IDE

**Solution**: Configure Python path in VS Code:
```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true
  }
}
```

---

## 📚 Development Workflow

### Running Tests

```powershell
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_auth.py -v

# Run with coverage
pytest --cov=api tests/ -v

# Run integration tests
pytest tests/integration_test.py -v
```

### Adding New Endpoints

```python
# 1. Define schema (api/schemas/your_feature.py)
from pydantic import BaseModel

class YourRequest(BaseModel):
    field: str

class YourResponse(BaseModel):
    result: str

# 2. Add service logic (api/services/your_service.py)
def your_function(db: Session, param: str):
    # Business logic here
    return result

# 3. Create router (api/routers/your_router.py)
from fastapi import APIRouter, Depends
from api.core.database import get_db

router = APIRouter(prefix="/api/your-feature", tags=["your-feature"])

@router.post("/endpoint", response_model=YourResponse)
def endpoint(
    req: YourRequest,
    db: Session = Depends(get_db),
):
    result = your_function(db, req.field)
    return YourResponse(result=result)

# 4. Include router (api/main.py)
from api.routers.your_router import router as your_router
app.include_router(your_router)
```

### Database Migrations (Alembic)

```powershell
# Create migration
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Code Style & Linting

```powershell
# Format code
black api/

# Check linting
flake8 api/ --max-line-length=100

# Type checking
mypy api/

# All at once
pip install pre-commit
pre-commit run --all-files
```

---

## 📞 Support & Documentation

### Key Files Reference

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app setup & route registration |
| `api/core/config.py` | All application settings |
| `api/models/models.py` | Database schema definitions |
| `api/core/security.py` | Password hashing & JWT functions |
| `scripts/init_db.py` | Database initialization |
| `start.py` | Development server launcher |

### Environment Variables Reference

```bash
# Security
SECRET_KEY                              # JWT signing key
JWT_ALGORITHM                           # Algorithm (default: HS256)
JWT_EXPIRE_SECONDS                      # Access token lifespan
REFRESH_TOKEN_EXPIRE_SECONDS            # Refresh token lifespan

# Database
DATABASE_URL                            # Connection string

# Azure OpenAI
AZURE_OPENAI_API_KEY                   # API key
AZURE_OPENAI_ENDPOINT                  # Resource endpoint
AZURE_OPENAI_CHAT_DEPLOYMENT           # Chat model name
AZURE_OPENAI_EMBEDDING_DEPLOYMENT      # Embedding model name

# Application
APP_ENV                                 # development/production
DEBUG                                   # Enable debug mode
LOG_LEVEL                               # INFO/DEBUG/WARNING/ERROR
RUNTIME_ROOT                            # Session storage path
ALLOWED_ORIGINS                         # CORS allow-list
```

### Quick Command Reference

```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Start development server
python start.py

# Run tests
pytest tests/ -v

# Create admin user
python scripts/create_admin.py --username admin --password Admin123!

# Initialize database
python scripts/init_db.py

# Create demo users
python scripts/demo_users.py

# Access API docs
# http://localhost:8000/docs

# Access ReDoc
# http://localhost:8000/redoc
```

---

## 📊 Default Credentials

```
┌──────────────┬──────────────┬─────────────┐
│ Username     │ Password     │ Role        │
├──────────────┼──────────────┼─────────────┤
│ admin        │ admin123     │ ADMIN       │
│ demo         │ demo123      │ USER        │
└──────────────┴──────────────┴─────────────┘
```

**⚠️ IMPORTANT**: Change these credentials in production!

---

## 🎓 Complete Workflow Example

### 1. Initialize & Run Server

```powershell
cd d:\WORK\RET_App\backend
.venv\Scripts\Activate.ps1
python start.py
```

### 2. Login

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' \
  -c cookies.txt
```

### 3. Upload & Convert Files

```bash
# Scan ZIP
curl -X POST "http://localhost:8000/api/conversion/scan" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@mydata.zip"

# Convert XML to CSV
curl -X POST "http://localhost:8000/api/conversion/convert" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "groups": ["articles"]}'

# Download results
curl -X GET "http://localhost:8000/api/conversion/download/SESSION_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -o results.zip
```

### 4. Use AI Chat

```bash
# Index documents
curl -X POST "http://localhost:8000/api/v2/ai/index/groups" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "groups": ["articles"]}'

# Chat
curl -X POST "http://localhost:8000/api/v2/ai/chat" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "...",
    "message": "What are the top articles?",
    "group_filter": "articles"
  }'
```

---

## ✅ Verification Checklist

- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -e .`)
- [ ] `.env` file configured
- [ ] Database initialized (auto on first run)
- [ ] Demo users created (auto on first run)
- [ ] Server running on http://localhost:8000
- [ ] Swagger docs accessible at http://localhost:8000/docs
- [ ] Can login with admin/admin123
- [ ] Can perform file upload and conversion
- [ ] Can use AI chat (if Azure OpenAI configured)

---

## 📝 License & Credits

**RET v4 Backend** - Enterprise XML-to-CSV Conversion & AI Tool
- Framework: FastAPI
- Database: PostgreSQL/SQLite
- Language: Python 3.12+

---

## 🚀 Next Steps

1. **[Configure Azure OpenAI](#database-configuration)** for AI features
2. **[Create additional users](#user-management)** as needed
3. **[Run test suite](#development-workflow)** to verify setup
4. **[Deploy to production](#production-deployment)** when ready
5. **[Review security checklist](#security-features)** before going live

