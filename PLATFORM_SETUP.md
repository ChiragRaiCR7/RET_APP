# RET v4 Platform Setup Guide

Complete guide for setting up and configuring the RET v4 platform from scratch.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Installation](#initial-installation)
3. [Database Setup](#database-setup)
4. [Environment Configuration](#environment-configuration)
5. [Creating Super Admin](#creating-super-admin)
6. [Azure OpenAI Integration](#azure-openai-integration)
7. [ChromaDB Configuration](#chromadb-configuration)
8. [User Role Management](#user-role-management)
9. [Running the Application](#running-the-application)
10. [Admin Panel Guide](#admin-panel-guide)
11. [Troubleshooting](#troubleshooting)

---

## 🔧 Prerequisites

### System Requirements
- **OS**: Windows 10/11, Linux, macOS
- **Python**: 3.12 or higher
- **Node.js**: 18.x or higher
- **RAM**: Minimum 8GB (16GB recommended for large file processing)
- **Disk Space**: 50GB+ for session storage

### Required Accounts
- **Azure OpenAI**: For AI-powered chat and embeddings
  - GPT-4 deployment (chat model)
  - text-embedding-3-small deployment (embeddings)

---

## 🚀 Initial Installation

### 1. Clone Repository
```bash
cd d:\WORK
git clone <your-repo-url> RET_App
cd RET_App
```

### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 3. Frontend Setup
```bash
cd ../frontend

# Install Node.js dependencies
npm install
```

---

## 💾 Database Setup

### SQLite (Development)

RET v4 uses SQLite by default for development.

```bash
cd backend

# Initialize database with tables
python scripts/init_db.py
```

This creates `backend/ret.db` with all required tables:
- users
- login_sessions
- reset_tokens
- reset_requests
- user_limits
- limit_requests
- app_sessions
- ops_logs
- error_events
- audit_logs

### PostgreSQL (Production)

For production deployments, configure PostgreSQL:

1. Install PostgreSQL 14+
2. Create database:
```sql
CREATE DATABASE retv4;
CREATE USER retadmin WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE retv4 TO retadmin;
```

3. Update `.env` file (see next section)

---

## ⚙️ Environment Configuration

### Backend Configuration

Create `backend/.env`:

```bash
# =============================================================================
# RET v4 Backend Configuration
# =============================================================================

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------
# SQLite (Development)
DATABASE_URL=sqlite:///./ret.db

# PostgreSQL (Production)
# DATABASE_URL=postgresql://retadmin:password@localhost:5432/retv4

# -----------------------------------------------------------------------------
# Security & Authentication
# -----------------------------------------------------------------------------
# JWT Secret (Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET_KEY=your-generated-secret-key-here

# Token pepper for additional security
TOKEN_PEPPER=your-pepper-secret-here

# Session timeout (minutes)
SESSION_TIMEOUT_MINUTES=60

# Force HTTPS cookies (set to 1 in production)
RET_FORCE_COOKIE_SECURE=0

# -----------------------------------------------------------------------------
# Azure OpenAI Configuration
# -----------------------------------------------------------------------------
# Azure OpenAI resource endpoint
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/

# Azure OpenAI API key
AZURE_OPENAI_API_KEY=your-azure-openai-api-key

# Deployment names (must match your Azure deployments)
AZURE_OPENAI_CHAT_MODEL=gpt-4o
AZURE_OPENAI_EMBED_MODEL=text-embedding-3-small

# API version
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# -----------------------------------------------------------------------------
# AI & RAG Configuration
# -----------------------------------------------------------------------------
# AI strategy: "lite", "langchain", or "advanced"
AI_STRATEGY=advanced

# Temperature for chat responses (0.0 - 1.0)
AI_TEMPERATURE=0.65

# Maximum tokens in responses
AI_MAX_TOKENS=4000

# RAG retrieval settings
RAG_TOP_K_VECTOR=20
RAG_TOP_K_LEXICAL=15
RAG_TOP_K_SUMMARY=5
RAG_MAX_CHUNKS=15
RAG_MAX_CONTEXT_CHARS=40000

# RAG feature flags
RAG_ENABLE_QUERY_TRANSFORM=true
RAG_ENABLE_SUMMARIES=true
RAG_USE_ADVANCED=true

# Fusion weights (must sum to 1.0)
RAG_VECTOR_WEIGHT=0.6
RAG_LEXICAL_WEIGHT=0.3
RAG_SUMMARY_WEIGHT=0.1

# -----------------------------------------------------------------------------
# File Processing Limits
# -----------------------------------------------------------------------------
# Maximum upload size (MB)
MAX_UPLOAD_SIZE_MB=10000

# Maximum extraction size (MB)
MAX_EXTRACT_SIZE_MB=10000

# Maximum files per ZIP
MAX_FILES=10000

# Maximum depth for nested ZIPs
ZIP_DEPTH_LIMIT=50

# Maximum file size per extracted file (MB)
MAX_PER_FILE_MB=1000

# Compression ratio limit (anti-zip-bomb)
MAX_COMPRESSION_RATIO=200

# Chunk size for processing (MB)
CHUNK_SIZE_MB=10

# -----------------------------------------------------------------------------
# Performance Settings
# -----------------------------------------------------------------------------
# Maximum threads for parallel processing
MAX_THREADS=32

# Workers per CPU core
MAX_WORKERS_PER_CPU=2

# Cache settings
CACHE_MAX_SIZE=128
EMBEDDING_BATCH_SIZE=16

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
# Environment (dev/prod)
RET_ENV=dev

# Debug mode (0/1)
RET_DEBUG=1

# Console logging (0/1)
RET_CONSOLE_LOG=1

# Maximum log message length
MAX_LOG_CHARS=2200

# Log rotation
LOG_ROTATION_MB=2
LOG_BACKUP_COUNT=5

# -----------------------------------------------------------------------------
# Session Management
# -----------------------------------------------------------------------------
# Idle session cleanup threshold (seconds)
RET_IDLE_CLEANUP_SECONDS=3600

# Runtime directory
RET_RUNTIME_ROOT=./runtime

# -----------------------------------------------------------------------------
# CORS Settings (Frontend)
# -----------------------------------------------------------------------------
# Allowed origins (comma-separated)
CORS_ORIGINS=http://localhost:5173,http://localhost:8000

# Allowed methods
CORS_METHODS=GET,POST,PUT,DELETE,OPTIONS

# Allow credentials
CORS_CREDENTIALS=true
```

### Generate Secure Keys

```bash
# JWT Secret Key
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Token Pepper
python -c "import secrets; print('TOKEN_PEPPER=' + secrets.token_urlsafe(32))"
```

### Frontend Configuration

Create `frontend/.env`:

```bash
# Backend API URL
VITE_API_BASE_URL=http://localhost:8000

# Environment
VITE_ENV=development
```

---

## 👤 Creating Super Admin

### Method 1: Using create_admin.py Script

```bash
cd backend
python scripts/create_admin.py
```

This creates:
- **Super Admin**: `superadmin` / `SuperAdmin123!`
- **Regular Admin**: `admin` / `Admin123!`
- **User**: `testuser` / `User123!`

### Method 2: Manual Creation

```bash
cd backend
python
```

```python
from api.core.database import get_session
from api.services.admin_service import create_user

with get_session() as db:
    user_id = create_user(
        db=db,
        username="superadmin",
        role="super_admin",  # Note: lowercase
        password="YourSecurePassword123!",
        admin_username="system"
    )
    print(f"Created super admin with ID: {user_id}")
```

### Role Hierarchy

| Role | Access Level | Capabilities |
|------|-------------|--------------|
| **super_admin** | Full system access | All admin capabilities + system configuration |
| **admin** | Admin console + main app | User management, audit logs, session monitoring |
| **user** | Main app only | File conversion, AI chat, downloads |
| **guest** | Read-only (future) | View-only access |

---

## 🤖 Azure OpenAI Integration

### 1. Create Azure OpenAI Resource

1. Go to [Azure Portal](https://portal.azure.com)
2. Create Resource → AI + Machine Learning → Azure OpenAI
3. Choose region (e.g., East US, West Europe)
4. Select pricing tier (Standard S0)

### 2. Deploy Models

Navigate to Azure OpenAI Studio:

#### Chat Model (GPT-4)
```
Model: gpt-4o
Deployment Name: gpt-4o
Version: Latest
Capacity: 30K TPM (adjust based on usage)
```

#### Embedding Model
```
Model: text-embedding-3-small
Deployment Name: text-embedding-3-small
Version: Latest
Capacity: 120K TPM
```

### 3. Get Credentials

1. Resource → Keys and Endpoint
2. Copy:
   - Endpoint: `https://YOUR-RESOURCE.openai.azure.com/`
   - Key 1 (or Key 2): Your API key

3. Update `.env`:
```bash
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_CHAT_MODEL=gpt-4o
AZURE_OPENAI_EMBED_MODEL=text-embedding-3-small
```

### 4. Test Connection

```bash
cd backend
python -c "
from api.core.config import settings
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key=settings.azure_openai_api_key,
    api_version=settings.azure_openai_api_version,
    azure_endpoint=settings.azure_openai_endpoint
)

response = client.chat.completions.create(
    model=settings.azure_openai_chat_model,
    messages=[{'role': 'user', 'content': 'Hello!'}],
    max_tokens=50
)
print('✅ Azure OpenAI connection successful!')
print(response.choices[0].message.content)
"
```

---

## 🗄️ ChromaDB Configuration

ChromaDB is used for vector embeddings and semantic search in the AI chat feature.

### Default Configuration

ChromaDB stores data in session-specific directories:
```
backend/runtime/sessions/{session_id}/ai_index/chroma/
```

### Settings

In `.env`:
```bash
# Collection naming (auto-generated per session)
# Format: session_{session_id}_rag

# Embedding settings
EMBEDDING_BATCH_SIZE=16
RAG_TOP_K_VECTOR=20

# Storage path (relative to backend/)
RET_RUNTIME_ROOT=./runtime
```

### Manual Cleanup

```bash
# Remove all ChromaDB data
rm -rf backend/runtime/sessions/*/ai_index/

# Remove specific session
rm -rf backend/runtime/sessions/{session_id}/ai_index/
```

### Verify ChromaDB

```bash
cd backend
python -c "
import chromadb
from pathlib import Path

# Create test client
path = Path('./runtime/test_chroma')
path.mkdir(parents=True, exist_ok=True)

client = chromadb.PersistentClient(path=str(path))
collection = client.create_collection('test')

print('✅ ChromaDB initialized successfully')
print(f'Version: {chromadb.__version__}')

# Cleanup
import shutil
shutil.rmtree(path)
"
```

---

## 👥 User Role Management

### Creating Users (Admin Panel)

1. Log in as admin/super_admin
2. Navigate to Admin Panel → User Management
3. Click "Create User"
4. Fill form:
   - **Username**: 3-64 chars, lowercase a-z0-9._-
   - **Role**: user / admin / super_admin
   - **Onboarding**:
     - **Token-first**: User sets password via token
     - **Password**: Set initial password (must meet policy)

### Password Policy

```
Minimum 8 characters
At least 1 uppercase letter (A-Z)
At least 1 lowercase letter (a-z)
At least 1 digit (0-9)
At least 1 special character (!@#$%^&*(),.?":{}|<>)
```

### Token-First Onboarding

1. Admin creates user without password
2. System generates secure token (32 bytes, URL-safe)
3. Admin shares token with user
4. User visits login page → "Reset Password" tab
5. User enters token + new password
6. Account activated

### Resource Limits

Each user has configurable limits:

```python
DEFAULT_LIMITS = {
    "zip_upload_mb": 1000,      # 1 GB
    "depth_limit": 50,           # Nested ZIP depth
    "max_files": 10000,          # Files per upload
    "max_total_mb": 10000,       # 10 GB total extraction
    "max_per_file_mb": 10,       # Individual file size
}
```

**Admins/Super Admins** inherit max limits from settings.

---

## 🏃 Running the Application

### Development Mode

#### Terminal 1: Backend
```bash
cd backend
venv\Scripts\activate  # or source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

Backend runs at: `http://localhost:8000`
API docs: `http://localhost:8000/docs`

#### Terminal 2: Frontend
```bash
cd frontend
npm run dev
```

Frontend runs at: `http://localhost:5173`

### Production Mode

#### Backend (with Gunicorn)
```bash
cd backend
gunicorn api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log
```

#### Frontend (Build)
```bash
cd frontend
npm run build

# Serve with nginx or similar
# Build output in: frontend/dist/
```

### Docker Deployment (Future)

```dockerfile
# Dockerfile example
FROM python:3.12-slim

WORKDIR /app
COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/

RUN cd backend && pip install -e .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🔐 Admin Panel Guide

### Accessing Admin Panel

1. Log in with admin or super_admin account
2. Navigate to `/admin` or use navigation menu

### Key Features

#### 1. User Management
- **Create User**: Token-first or password onboarding
- **Update Role**: Change user roles (user ↔ admin)
- **Delete User**: Remove users (protected for last admin)
- **Unlock Account**: Clear failed login lockouts
- **Force Password Reset**: Require password change on next login

#### 2. Password Reset Approval
- View pending reset requests
- Approve/reject requests
- View request history

#### 3. Resource Limit Management
- View user limits
- Approve limit increase requests
- Set custom limits per user

#### 4. Session Monitoring
- View active sessions
- Monitor idle sessions
- Force cleanup idle sessions (> 60 min inactive)
- View session details (temp_dir, log_path, status)

#### 5. Audit Logs
- View all admin actions
- Filter by admin, target user, action type
- Immutable audit trail

#### 6. Operational Logs
- View system logs (AUTH, ADMIN, MAIN, AI)
- Filter by level (INFO, WARN, ERROR)
- Download logs for analysis

#### 7. AI Admin Agent
- Natural language queries
- Tool calling for admin operations
- Examples:
  - "List all users"
  - "Create user named john with admin role"
  - "Show me pending reset requests"
  - "Cleanup idle sessions"

---

## 🔧 Troubleshooting

### Issue: 500 Error on Admin Panel

**Symptom**: Admin panel returns 500 errors, logs show:
```
LookupError: 'admin' is not among the defined enum values
```

**Cause**: Database has lowercase roles, but enum expects uppercase (before fix).

**Solution**:
```bash
cd backend
python scripts/fix_role_case.py
```

---

### Issue: Azure OpenAI Connection Failed

**Symptom**: AI chat returns connection errors.

**Checklist**:
1. Verify `.env` credentials:
   ```bash
   python -c "from api.core.config import settings; print(settings.azure_openai_endpoint)"
   ```
2. Check Azure OpenAI deployment names match `.env`
3. Verify API key is valid (not copied with extra spaces)
4. Test with curl:
   ```bash
   curl https://YOUR-RESOURCE.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview \
     -H "Content-Type: application/json" \
     -H "api-key: YOUR-API-KEY" \
     -d '{"messages":[{"role":"user","content":"Hello"}]}'
   ```

---

### Issue: ChromaDB Collection Not Found

**Symptom**: AI chat fails with "Collection not found".

**Solution**:
1. Index groups before chat:
   - Main View → AI Chat tab
   - Select groups
   - Click "Index Selected Groups"
2. Wait for indexing to complete
3. Try chat again

---

### Issue: User Locked Out

**Symptom**: User cannot log in after 5 failed attempts.

**Solution** (Admin):
1. Admin Panel → User Management
2. Find user
3. Click "Unlock Account"
4. User lockout cleared (can log in immediately)

---

### Issue: Session Files Accumulating

**Symptom**: `runtime/sessions/` directory growing large.

**Solution**:
1. **Manual cleanup**:
   ```bash
   cd backend
   python scripts/cleanup_sessions.py
   ```
2. **Admin console**:
   - Session Monitoring tab
   - Click "Cleanup Idle Sessions"
3. **Automatic** (if configured):
   - Idle sessions auto-cleaned after `IDLE_CLEANUP_SECONDS` (default 3600s)

---

### Issue: Database Migration Needed

**Symptom**: After code updates, database schema mismatch errors.

**Solution**:
```bash
cd backend

# Create migration
alembic revision --autogenerate -m "Description of changes"

# Review migration in alembic/versions/

# Apply migration
alembic upgrade head
```

---

### Database Reset (Development Only)

**⚠️ WARNING: This deletes all data!**

```bash
cd backend

# Stop backend server first

# Delete database
rm ret.db

# Recreate tables
python scripts/init_db.py

# Create admin users
python scripts/create_admin.py
```

---

## 📊 System Health Checks

### Backend Health
```bash
curl http://localhost:8000/api/health
# Expected: {"status":"ok","version":"4.0.0"}
```

### Database Connection
```bash
cd backend
python -c "from api.core.database import get_session; print('✅ DB connection OK' if next(get_session()) else '❌ DB error')"
```

### Azure OpenAI
```bash
cd backend
python scripts/validate_advanced.py
# Validates full RAG pipeline
```

---

## 📚 Additional Resources

- **API Reference**: [backend/API_REFERENCE.md](backend/API_REFERENCE.md)
- **Troubleshooting Guide**: [backend/TROUBLESHOOTING.md](backend/TROUBLESHOOTING.md)
- **Frontend README**: [frontend/README.md](frontend/README.md)
- **Copilot Instructions**: [.github/copilot-instructions.md](.github/copilot-instructions.md)

---

## 🔄 Regular Maintenance

### Daily
- Monitor `backend/logs/` for errors
- Check disk space in `runtime/sessions/`

### Weekly
- Review audit logs for suspicious activity
- Cleanup idle sessions
- Backup database (`ret.db` or PostgreSQL dump)

### Monthly
- Rotate logs
- Review user resource limits
- Update dependencies
  ```bash
  cd backend && pip install --upgrade -e ".[dev]"
  cd ../frontend && npm update
  ```

---

## 🚨 Security Checklist

- [ ] Change default admin passwords
- [ ] Set strong JWT_SECRET_KEY and TOKEN_PEPPER
- [ ] Enable HTTPS in production (RET_FORCE_COOKIE_SECURE=1)
- [ ] Configure firewall rules (expose only 8000/443)
- [ ] Enable database backups
- [ ] Review CORS_ORIGINS (restrict to known domains)
- [ ] Set up log monitoring/alerts
- [ ] Regularly update dependencies
- [ ] Review audit logs for unauthorized access
- [ ] Test password reset flow

---

## 📞 Support

For issues or questions:
1. Check [TROUBLESHOOTING.md](backend/TROUBLESHOOTING.md)
2. Review logs in `backend/logs/`
3. Check GitHub issues
4. Contact platform admin

---

**Last Updated**: 2024
**Version**: RET v4.0
**Platform**: FastAPI + Vue 3 + SQLAlchemy + ChromaDB + Azure OpenAI
