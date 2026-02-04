# RET v4 Copilot Instructions

## Architecture Overview

RET v4 is a **FastAPI + Vue 3** application for XML-to-CSV conversion with AI-powered RAG chat.

```
backend/api/         # FastAPI backend (Python 3.12+)
├── routers/         # API endpoints (/api/{domain})
├── services/        # Business logic (conversion, AI, storage)
├── services/ai/     # AI strategy factory (lite, langchain, advanced)
├── schemas/         # Pydantic request/response models
├── core/            # Config, security, dependencies
└── models/          # SQLAlchemy ORM models

frontend/src/        # Vue 3 SPA (Composition API)
├── views/           # Page-level components (MainView, AdminView)
├── components/      # Reusable UI components
├── stores/          # Pinia state management
└── utils/api.js     # Axios instance with auth interceptor
```

## Critical Patterns

### Backend Router Conventions
- All routers prefix with `/api/{domain}` (e.g., `/api/conversion`, `/api/auth`)
- New features use `/api/v2/{domain}` versioning (see `backend/api/routers/rag_router.py`)
- Use `Depends(get_current_user)` for authenticated endpoints
- Return Pydantic models in `response_model=` parameter

### Schema Flexibility Pattern
Schemas support multiple field names for frontend compatibility:
```python
class RAGChatRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None  # Alias for frontend compatibility
```

### AI Service Factory
Select AI strategy via `settings.AI_STRATEGY` ("lite", "langchain", "advanced"):
```python
from api.services.ai import AIServiceFactory
service = AIServiceFactory.create(session_id, strategy=settings.AI_STRATEGY)
```

### Session-Based Storage
Files stored in `runtime/sessions/{session_id}/`:
- `input/` - Uploaded files
- `output/` - Converted CSVs
- `extracted/` - Extracted XML files
- `ai_index/` - ChromaDB vector storage

Use `get_session_dir(session_id)` from `storage_service.py` - never construct paths manually.

### Frontend State Pattern
Vue components use Pinia stores for global state:
```javascript
import { useAuthStore } from '@/stores/authStore'
const auth = useAuthStore()
```
API calls go through `@/utils/api.js` which handles JWT refresh automatically.

## Developer Commands

```bash
# Backend
cd backend
pip install -e ".[dev]"
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev  # Vite dev server on :5173

# Tests
cd backend
pytest tests/ -v
```

## Environment Variables

Required in `backend/.env`:
```
JWT_SECRET_KEY=<secret>
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_CHAT_MODEL=gpt-4o
AZURE_OPENAI_EMBED_MODEL=text-embedding-3-small
```

## Key Workflows

### XML Conversion Flow
1. Upload ZIP → `POST /api/conversion/scan` → returns `session_id` and detected groups
2. Convert → `POST /api/workflow/convert` with selected groups
3. Download → `GET /api/conversion/download/{session_id}`

### AI Chat Flow
1. After conversion, get available groups → `GET /api/v2/ai/index/groups?session_id=xxx`
2. Index selected groups → `POST /api/v2/ai/index/groups`
3. Chat with RAG → `POST /api/v2/ai/chat`
4. Download transcript → `POST /api/v2/ai/transcript/download`

### Advanced RAG Implementation
The RAG engine (`backend/api/services/ai/rag_engine.py`) implements Microsoft's Advanced RAG patterns:

**Query Transformation:**
- User queries are rewritten using LLM to improve retrieval
- Original query preserved for final LLM prompt
- Transformed query used only for embedding/vector search

**Hybrid Retrieval:**
- Vector search (70% weight) via ChromaDB embeddings
- Lexical search (30% weight) via keyword matching
- Results reranked using hybrid scoring

**ChromaDB Filter Syntax:**
```python
# Single condition
{"session_id": {"$eq": "xxx"}}

# Multiple conditions (use $and operator)
{"$and": [
    {"session_id": {"$eq": "xxx"}},
    {"group": {"$eq": "articles"}}
]}
```

**RAG Settings (configurable in config.py):**
- `chunk_size=1500` - Document chunk size
- `top_k=16` - Number of chunks to retrieve
- `max_context_chars=40000` - Max context for LLM
- `vector_weight=0.7` - Weight for vector similarity
- `lexical_weight=0.3` - Weight for keyword matching

## Testing Patterns

Integration tests in `backend/tests/` follow pattern:
```python
def test_workflow():
    data = create_test_zip()
    result = scan_zip_with_groups(data, "test.zip", user_id="test")
    assert "session_id" in result
```

## Important Files

| Purpose | Location |
|---------|----------|
| App config | `backend/api/core/config.py` |
| Auth flow | `backend/api/routers/auth_router.py` |
| Conversion logic | `backend/api/services/conversion_service.py` |
| RAG engine | `backend/api/services/ai/rag_engine.py` |
| Main UI | `frontend/src/views/MainView.vue` |
| API client | `frontend/src/utils/api.js` |




# RET v4 - Complete Application Working Documentation

## 📋 Table of Contents
1. [Application Overview](#application-overview)
2. [Architecture & Technology Stack](#architecture--technology-stack)
3. [Core Components](#core-components)
4. [Data Flow & Workflows](#data-flow--workflows)
5. [Database Schema](#database-schema)
6. [Security Implementation](#security-implementation)
7. [File Processing Pipeline](#file-processing-pipeline)
8. [User Roles & Permissions](#user-roles--permissions)

---

## 🎯 Application Overview

**RET v4** (Resource Extraction Tool v4) is an enterprise-grade web application built with Streamlit that provides:

### Primary Functions
- **ZIP to XML to CSV/XLSX Conversion**: Bulk processing of nested ZIP archives containing XML files
- **Multi-tenant User Management**: Role-based access control with admin/user roles
- **AI-Powered Assistant**: Azure OpenAI integration for intelligent data querying
- **Session Management**: Secure, persistent login sessions with cookie-based authentication
- **Audit & Compliance**: Comprehensive logging and audit trails

### Key Features
- Token-first user onboarding (passwordless initial setup)
- Password reset workflows with admin approval
- Resource limit governance per user
- Session registry with automatic cleanup
- ChromaDB vector embeddings for AI-powered search
- Professional enterprise UI with dark/light mode support

---

## 🏗️ Architecture & Technology Stack

### Frontend
- **Framework**: Streamlit Replace with VUE & FastAPI
- **UI Components**: Custom CSS with professional enterprise design system
- **Styling**: Verdana Pro Black font, FFC000 brand color (#FFC000)
- **State Management**: Streamlit session state replace with FastAPI + Vue 3 + Pinia
- **Cookies**: streamlit-cookies-controller for persistent sessions replace with FastAPI + Vue 3 + Pinia

### Backend
- **Language**: Python 3.x
- **Web Framework**: Streamlit replace with FastAPI + Vue 3 + Pinia
- **Database**: 
  - PostgreSQL (production) / SQLite (development)
  - SQLAlchemy ORM
- **Authentication**: bcrypt for password hashing
- **Session Tokens**: HMAC-SHA256 with server-side pepper

### AI & Embeddings
- **LLM**: Azure OpenAI (GPT-4)
- **Vector Database**: ChromaDB
- **Embedding Model**: Azure OpenAI embeddings

### Data Processing
- **XML Parsing**: lxml with safe iterparse
- **CSV/Excel**: pandas, openpyxl
- **ZIP Handling**: zipfile with security limits
- **Concurrency**: concurrent.futures, threading, multiprocessing

### Infrastructure
- **Logging**: RotatingFileHandler with secret redaction
- **Session Storage**: File-based (ret_runtime/sessions/)
- **Configuration**: Environment variables + pydantic settings

---

## 🔧 Core Components

### 1. **main.py** (5,578 lines)
**Purpose**: Primary application interface for authenticated users

#### Key Responsibilities
- ZIP file upload and extraction with security limits
- XML to CSV/XLSX conversion pipeline
- AI chat interface with ChromaDB RAG
- File comparison (zipcmp) functionality
- Session lifecycle management
- Real-time progress tracking

#### Major Classes & Functions
```python
# Configuration
class RETSettings(BaseSettings):
    - session_timeout_minutes: 60
    - max_upload_size_mb: 10000
    - ai_temperature: 0.65
    - chunk_size_mb: 10
    # ... 30+ configurable parameters

# Data Models
@dataclass
class XmlEntry:
    logical_path, filename, xml_path, xml_size, stub

@dataclass
class CsvArtifactDC:
    logical_path, filename, group, stub, csv_path
    rows, cols, tag_used, status, err_msg
    vec, vec_norm  # AI embeddings

# Database
class SQLiteConnectionPool:
    - Thread-safe connection pooling
    - Context manager for transactions

# Core Functions
- plan_zip_work(): Security-hardened ZIP scanning
- extract_zip_safe(): Controlled extraction with limits
- convert_xml_to_csv(): XML parsing and CSV generation
- build_ai_index(): ChromaDB vector indexing
- ai_chat(): RAG-powered Q&A
```

#### Security Features
- **ZIP Bomb Protection**: Compression ratio limits (200:1)
- **Path Traversal Prevention**: Allowlisted extraction paths
- **Resource Limits**: Max files (10k), max size (10GB), depth limits (50)
- **XML Entity Expansion**: Disabled network access in lxml
- **Correlation IDs**: Full request tracing

---

### 2. **login.py** (1,011 lines)
**Purpose**: Authentication landing page

#### Key Features
- **Login Form**: Username/password authentication
- **Persistent Login**: Cookie-based session tokens
- **Password Reset**: User-initiated reset requests
- **Modern UI**: SaaS-style design with glassmorphism

#### UI Components
```css
/* Design Tokens */
--brand-primary: #FFC000
--font-display: "Verdana Pro Black"
--radius-lg: 22px
--shadow-md: 0 22px 56px rgba(2, 6, 23, .12)

/* Components */
.auth-shell: Glass-morphic container
.brand-title: Gradient accent text
.auth-card: Elevated surface with shadow
.ret-meter: Password strength indicator
```

#### Authentication Flow
1. Check for existing cookie token → `AUTH.get_login_session()`
2. If valid → restore session → redirect to main/admin
3. If invalid → show login form
4. On successful login → `AUTH.verify_user()` → `AUTH.create_login_session()`
5. Set cookie → redirect based on role

---

### 3. **admin.py** (2,537 lines)
**Purpose**: Enterprise admin console

#### Admin Capabilities
1. **User Management**
   - Create users (token-first or with password)
   - Delete users (with last-admin protection)
   - Update roles (admin/user/guest)
   - Unlock locked accounts
   - Force password resets

2. **Governance**
   - Approve/reject password reset requests
   - Approve/reject resource limit increase requests
   - Set per-user resource limits

3. **Monitoring**
   - Session registry (active/idle sessions)
   - Cleanup idle sessions (manual + auto)
   - View audit logs
   - View operational logs
   - Download session logs

4. **AI Admin Agent**
   - Azure OpenAI-powered assistant
   - Tool calling for admin operations
   - Natural language queries

#### Professional UI
```css
/* Enterprise Design System */
--brand-primary: #FFC000
--surface-elevated: #ffffff (light) / #1c2128 (dark)
--shadow-brand: 0 10px 30px -5px var(--brand-glow)

/* Components */
.admin-header: Gradient top border
.enterprise-card: Elevated cards with hover effects
.user-avatar: Gradient circular avatar
.status-badge: Semantic color-coded badges
```

#### Admin Agent Tools
```python
tools = [
    "list_users", "create_user", "delete_user",
    "list_reset_requests", "approve_reset_request",
    "list_limit_requests", "approve_limit_request",
    "list_sessions", "cleanup_idle_sessions",
    "get_system_stats"
]
```

---

### 4. **auth.py** (1,364 lines)
**Purpose**: Authentication & authorization logic

#### Core Functions

##### User Management
```python
def create_user(username, role, password, admin_username)
    - Validates username format (3-64 chars, a-z0-9._-)
    - Validates password policy (8+ chars, upper/lower/digit/special)
    - Supports token-first onboarding (password=None)
    - Logs admin action

def verify_user(username, password) -> Tuple[id, username, role]
    - Checks lockout status
    - Validates bcrypt hash
    - Implements failed attempt tracking (5 attempts → 15min lockout)
    - Returns None on any failure (prevents user enumeration)

def delete_user(username, admin_username)
    - Prevents self-deletion
    - Prevents last admin deletion
    - Cascades to related records
```

##### Session Management
```python
def create_login_session(username, ttl_seconds=86400) -> str
    - Generates secure token (secrets.token_urlsafe(32))
    - Stores HMAC-SHA256 hash in DB (never plaintext)
    - Returns plaintext token for cookie

def get_login_session(token) -> Tuple[id, username, role]
    - Hashes incoming token
    - Validates expiry
    - Returns user tuple or None

def logout_cleanup(cookie_token, session_id, username, temp_dir, ...)
    - Revokes login session
    - Marks app_session status
    - Deletes temp directories (allowlisted paths only)
    - Deletes ChromaDB collections
```

##### Password Reset
```python
def generate_reset_token(username, admin_username) -> str
    - Creates secure token
    - Stores hash in reset_tokens table
    - Returns plaintext for email/display

def use_reset_token(token, new_password)
    - Validates token hash
    - Checks expiry
    - Validates new password policy
    - Updates password_hash
    - Marks token as used
```

##### Logging
```python
def ops(level, action, username, session_id, corr_id, message, details)
    - Sanitizes message (removes CR/LF, caps at 1000 chars)
    - Redacts sensitive keys (token, password, api_key, etc.)
    - Writes to ops_logs table

def log_admin_action(db, admin_username, action, target_username, details)
    - Records to audit_logs table
    - Immutable audit trail
```

---

### 5. **db.py** (225 lines)
**Purpose**: Database connection and utilities

#### Key Components
```python
# Engine Configuration
DATABASE_URL = "sqlite:///./ret.db"  # or PostgreSQL in prod
engine = create_engine(DATABASE_URL, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_session() -> Session:
    # Auto-commit/rollback context manager

def init_db():
    Base.metadata.create_all(bind=engine)

# Logging Functions
def write_ops_log(level, area, action, username, session_id, corr_id, message, details)
def write_error_event(phase, path, error_code, message, corr_id, username, session_id, details)

# Session Registry
def upsert_app_session(session_id, username, temp_dir, log_path, status)
def touch_app_session(session_id)  # Update last_seen
def mark_app_session(session_id, status)  # Update status
```

---

### 6. **models.py** (346 lines)
**Purpose**: SQLAlchemy ORM models

#### Database Tables

##### Authentication
```python
class User(Base):
    id: Integer (PK)
    username: String (unique, indexed)
    password_hash: Text (nullable for token-first)
    role: String (admin/user/guest)
    failed_attempts: Integer
    locked_until: BigInteger (epoch)
    must_reset: Boolean
    password_changed_at: BigInteger
    created_at: BigInteger

class LoginSession(Base):
    token_hash: String (PK)  # HMAC-SHA256 hash
    username: String (FK → users.username)
    created_at: BigInteger
    expires_at: BigInteger (indexed)
```

##### Password Reset
```python
class ResetToken(Base):
    username: String (PK, FK)
    token_hash: Text
    expires_at: BigInteger (indexed)
    created_at: BigInteger
    used_at: BigInteger (nullable)

class ResetRequest(Base):
    id: Integer (PK)
    username: String (FK)
    status: String (pending/approved/rejected)
    note: Text
    requested_at: BigInteger
    actioned_at: BigInteger
    action_by: String
```

##### Governance
```python
class UserLimit(Base):
    username: String (PK, FK)
    zip_upload_mb: Integer (default 1000)
    depth_limit: Integer (default 50)
    max_files: Integer (default 10000)
    max_total_mb: Integer (default 10000)
    max_per_file_mb: Integer (default 10)
    updated_at: BigInteger

class LimitRequest(Base):
    id: Integer (PK)
    username: String (FK)
    requested_zip_upload_mb: Integer
    requested_depth_limit: Integer
    requested_max_files: Integer
    requested_max_total_mb: Integer
    requested_max_per_file_mb: Integer
    status: String (pending/approved/rejected)
    note: Text
    requested_at: BigInteger
    actioned_at: BigInteger
    action_by: String
```

##### Monitoring
```python
class AppSession(Base):
    session_id: String (PK)  # sid cookie
    username: String (FK, nullable)
    created_at: BigInteger (indexed)
    last_seen: BigInteger (indexed)
    status: String (ACTIVE/LOGOUT/CLEANED_IDLE/etc.)
    temp_dir: Text (nullable)
    log_path: Text (nullable)

class OpsLog(Base):
    id: BigInteger (PK)
    created_at: BigInteger (indexed)
    level: String (INFO/WARN/ERROR)
    area: String (AUTH/ADMIN/MAIN/AI/CLEANUP)
    action: String
    username: String (indexed)
    session_id: String (indexed)
    corr_id: String (indexed)
    message: Text
    details_json: Text

class ErrorEvent(Base):
    id: BigInteger (PK)
    created_at: BigInteger (indexed)
    username: String (indexed)
    session_id: String (indexed)
    phase: String (SCAN/CONVERT/AI_CHAT)
    path: Text
    error_type: String
    message: Text

class AuditLog(Base):
    id: Integer (PK)
    admin_username: String (indexed)
    action: String
    target_username: String (indexed)
    details: Text (JSON)
    created_at: BigInteger (indexed)
```

---

## 🔄 Data Flow & Workflows

### 1. User Login Flow
```
┌─────────────┐
│ login.py    │
└──────┬──────┘
       │
       ├─ Check cookie token
       │  └─ AUTH.get_login_session(token)
       │     └─ Hash token → Query login_sessions → Return user tuple
       │
       ├─ If no valid session:
       │  └─ Show login form
       │     └─ User submits credentials
       │        └─ AUTH.verify_user(username, password)
       │           ├─ Check lockout status
       │           ├─ Validate bcrypt hash
       │           ├─ Update failed_attempts
       │           └─ Return (id, username, role) or None
       │
       └─ On success:
          └─ AUTH.create_login_session(username)
             ├─ Generate token (secrets.token_urlsafe(32))
             ├─ Store hash in login_sessions
             └─ Return plaintext token
          └─ Set cookie
          └─ Redirect to main.py or admin.py based on role
```

### 2. File Processing Pipeline
```
┌──────────────────────────────────────────────────────────────┐
│ main.py: File Upload & Processing                           │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 1. ZIP Upload                                                │
│    - User uploads ZIP via st.file_uploader                   │
│    - Check size against user limits                          │
│    - Save to temp directory                                  │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 2. ZIP Scanning (plan_zip_work)                             │
│    - Recursively scan nested ZIPs (up to depth limit)       │
│    - Check compression ratios (anti-zip-bomb)               │
│    - Build extraction plan                                   │
│    - Validate total uncompressed size                        │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 3. ZIP Extraction (extract_zip_safe)                        │
│    - Extract to allowlisted temp directory                  │
│    - Sanitize filenames (prevent path traversal)            │
│    - Track extracted file count                             │
│    - Log extraction events                                   │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 4. XML Discovery                                            │
│    - Scan extracted files for .xml extensions               │
│    - Build XmlEntry inventory                                │
│    - Store in session state                                  │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 5. XML to CSV Conversion                                    │
│    - Parallel processing (ThreadPoolExecutor)               │
│    - For each XML:                                           │
│      ├─ Parse with lxml.iterparse (streaming)               │
│      ├─ Extract target tag data                             │
│      ├─ Convert to pandas DataFrame                         │
│      ├─ Write to CSV                                         │
│      └─ Store metadata in SQLite (files table)              │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 6. AI Indexing (Optional)                                   │
│    - Load CSVs into pandas                                   │
│    - Generate text representations                           │
│    - Create embeddings via Azure OpenAI                      │
│    - Store in ChromaDB collection                            │
│    - Mark group as indexed in DB                             │
└────────────────────────────────────────────────────────────┬─┘
                                                             │
┌────────────────────────────────────────────────────────────▼─┐
│ 7. Download & Export                                        │
│    - User selects files/groups                              │
│    - Create ZIP archive of CSVs/XLSXs                        │
│    - Stream download via st.download_button                  │
└──────────────────────────────────────────────────────────────┘
```

### 3. AI Chat Flow
```
┌─────────────────────────────────────────────────────────────┐
│ User Query: "What are the top 5 customers by revenue?"     │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 1. Query Embedding                                          │
│    - Azure OpenAI embeddings API                            │
│    - Convert query to vector                                │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 2. Vector Search (ChromaDB)                                 │
│    - Query collection with embedding                        │
│    - Retrieve top-k similar documents (k=16)                │
│    - Return CSV metadata + content snippets                 │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 3. Context Assembly                                         │
│    - Load full CSV content for top matches                  │
│    - Truncate to max_context_chars (40k)                    │
│    - Format as markdown tables                              │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 4. LLM Completion (Azure OpenAI GPT-4)                      │
│    - System prompt: "You are a data analyst..."            │
│    - User query + context                                   │
│    - Temperature: 0.65                                      │
│    - Max tokens: 4000                                       │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 5. Response Display                                         │
│    - Stream response via st.chat_message                    │
│    - Store in chat history                                  │
│    - Log interaction to ops_logs                            │
└─────────────────────────────────────────────────────────────┘
```

### 4. Admin User Creation Flow
```
┌─────────────────────────────────────────────────────────────┐
│ admin.py: User Management Tab                              │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 1. Admin fills form:                                        │
│    - Username (validated: 3-64 chars, a-z0-9._-)           │
│    - Role (admin/user/guest)                                │
│    - Onboarding method:                                     │
│      ├─ Token-first (no password)                          │
│      └─ Password (validated: 8+ chars, complexity)         │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 2. AUTH.create_user(username, role, password, admin_user)  │
│    ├─ Validate username format                             │
│    ├─ Check for existing user                              │
│    ├─ Hash password with bcrypt (if provided)              │
│    ├─ Insert into users table (must_reset=True)            │
│    └─ Log to audit_logs                                     │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 3. If token-first:                                          │
│    └─ AUTH.generate_reset_token(username, admin_user)      │
│       ├─ Generate secure token (secrets.token_urlsafe(32)) │
│       ├─ Store hash in reset_tokens (expires in 7 days)    │
│       └─ Display token to admin (copy to clipboard)        │
└──────────────────────────────────────────────────────────┬──┘
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│ 4. Admin shares token with user                            │
│    └─ User visits login page                               │
│       └─ Clicks "Reset Password" tab                       │
│          └─ Enters token + new password                    │
│             └─ AUTH.use_reset_token(token, new_password)   │
│                ├─ Validate token hash                      │
│                ├─ Check expiry                             │
│                ├─ Validate password policy                 │
│                ├─ Update password_hash                     │
│                ├─ Set must_reset=False                     │
│                └─ Mark token as used                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔐 Security Implementation

### 1. Authentication Security
- **Password Hashing**: bcrypt with auto-generated salt
- **Session Tokens**: HMAC-SHA256 hash stored in DB (plaintext never stored)
- **Token Pepper**: Server-side secret (TOKEN_PEPPER env var)
- **Lockout Policy**: 5 failed attempts → 15 minute lockout
- **Token Expiry**: 24 hours (configurable)

### 2. Authorization
- **Role-Based Access Control (RBAC)**:
  - `admin`: Full access to admin console + main app
  - `user`: Access to main app only
  - `guest`: Limited access (if implemented)
- **Last Admin Protection**: Cannot delete or demote last admin
- **Self-Deletion Prevention**: Admins cannot delete their own account

### 3. Input Validation
```python
# Username
USERNAME_RE = re.compile(r'^[a-z0-9._-]{3,64}$')

# Password Policy
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 digit
- At least 1 special character (!@#$%^&*(),.?":{}|<>)

# Path Sanitization
def _is_under(child: Path, parent: Path) -> bool:
    # Ensures child is under parent (prevents path traversal)
```

### 4. ZIP Security
```python
# Anti-Zip-Bomb Measures
MAX_COMPRESSION_RATIO = 200  # 200:1
MAX_DEPTH = 50  # Nested ZIP depth
MAX_FILES = 10_000
MAX_TOTAL_MB = 10_000
MAX_PER_FILE_MB = 1_000

# Path Traversal Prevention
def _sanitize_zip_name(name: str) -> str:
    # Remove leading slashes, .., etc.
    # Ensure extraction stays in temp directory
```

### 5. XML Security
```python
# lxml safe parsing
def safe_iterparse(source, *, events=("end",), tag=None, **opts):
    opts.setdefault("no_network", True)  # Disable XXE
    return LET.iterparse(source, events=events, tag=tag, **opts)
```

### 6. Logging Security
```python
# Secret Redaction
SECRET_PATTERNS = [
    r"(?i)(api[-_ ]?key)\s*[:=]\s*([^\s]+)",
    r"(?i)(authorization)\s*[:=]\s*bearer\s+([^\s]+)",
    r"\b(sk-[A-Za-z0-9]{20,})\b",  # OpenAI keys
    r"\b(eyJ[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+)\b",  # JWT
]

# Log Sanitization
def _sanitize_log_str(s, max_len=2000):
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    return s[:max_len]
```

### 7. Session Security
- **Cookie Attributes**:
  - `httponly=True` (prevent XSS)
  - `secure=True` (HTTPS only in production)
  - `samesite="Lax"` (CSRF protection)
- **Session Fixation Prevention**: New session ID on login
- **Idle Timeout**: 60 minutes (configurable)
- **Automatic Cleanup**: Background thread removes idle sessions

---

## 📊 Database Schema

### Entity Relationship Diagram
```
┌──────────────┐
│    users     │
│──────────────│
│ id (PK)      │◄─────────┐
│ username (U) │          │
│ password_hash│          │
│ role         │          │
│ failed_...   │          │
│ locked_until │          │
│ must_reset   │          │
└──────────────┘          │
       │                  │
       │ 1                │
       │                  │
       │ N                │
┌──────▼──────────┐       │
│ login_sessions  │       │
│─────────────────│       │
│ token_hash (PK) │       │
│ username (FK)   │───────┘
│ created_at      │
│ expires_at      │
└─────────────────┘

┌──────────────┐
│ reset_tokens │
│──────────────│
│ username(PK,FK)│─────┐
│ token_hash   │      │
│ expires_at   │      │
│ used_at      │      │
└──────────────┘      │
                      │
┌─────────────────┐   │
│ reset_requests  │   │
│─────────────────│   │
│ id (PK)         │   │
│ username (FK)   │───┘
│ status          │
│ requested_at    │
│ actioned_at     │
│ action_by       │
└─────────────────┘

┌──────────────┐
│ user_limits  │
│──────────────│
│ username(PK,FK)│─────┐
│ zip_upload_mb│      │
│ depth_limit  │      │
│ max_files    │      │
│ max_total_mb │      │
└──────────────┘      │
                      │
┌─────────────────┐   │
│ limit_requests  │   │
│─────────────────│   │
│ id (PK)         │   │
│ username (FK)   │───┘
│ requested_*     │
│ status          │
│ requested_at    │
└─────────────────┘

┌──────────────┐
│ app_sessions │
│──────────────│
│ session_id(PK)│
│ username (FK) │
│ created_at    │
│ last_seen     │
│ status        │
│ temp_dir      │
│ log_path      │
└──────────────┘

┌──────────────┐
│  ops_logs    │
│──────────────│
│ id (PK)      │
│ created_at   │
│ level        │
│ area         │
│ action       │
│ username     │
│ session_id   │
│ corr_id      │
│ message      │
│ details_json │
└──────────────┘

┌──────────────┐
│ error_events │
│──────────────│
│ id (PK)      │
│ created_at   │
│ username     │
│ session_id   │
│ phase        │
│ path         │
│ error_type   │
│ message      │
└──────────────┘

┌──────────────┐
│ audit_logs   │
│──────────────│
│ id (PK)      │
│ admin_username│
│ action       │
│ target_username│
│ details      │
│ created_at   │
└──────────────┘
```

---

## 👥 User Roles & Permissions

### Admin Role
**Access**: Full system access

**Capabilities**:
- ✅ Create/delete/modify users
- ✅ Approve password reset requests
- ✅ Approve resource limit requests
- ✅ View all sessions
- ✅ Force cleanup sessions
- ✅ View audit logs
- ✅ View operational logs
- ✅ Download session logs
- ✅ Use AI admin agent
- ✅ Access main application (file processing)

**Resource Limits** (overrides):
```python
ADMIN_ZIP_UPLOAD_MB = 10_000
ADMIN_DEPTH_LIMIT = 50
ADMIN_MAX_FILES = 10_000
ADMIN_MAX_TOTAL_MB = 10_000
ADMIN_MAX_PER_FILE_MB = 1_000
```

### User Role
**Access**: Main application only

**Capabilities**:
- ✅ Upload ZIP files (within limits)
- ✅ Convert XML to CSV/XLSX
- ✅ Use AI chat assistant
- ✅ Download converted files
- ✅ Request password reset (requires admin approval)
- ✅ Request limit increases (requires admin approval)
- ❌ Cannot access admin console
- ❌ Cannot view other users' data

**Default Resource Limits**:
```python
DEFAULT_LIMITS = {
    "zip_upload_mb": 1_000,
    "depth_limit": 50,
    "max_files": 10_000,
    "max_total_mb": 10_000,
    "max_per_file_mb": 10,
}
```

### Guest Role
**Access**: Limited (if implemented)

**Capabilities**:
- ⚠️ Read-only access (implementation-dependent)
- ❌ Cannot upload files
- ❌ Cannot use AI features

---

## 🔄 Session Lifecycle

### 1. Session Creation
```python
# On login
session_id = secrets.token_hex(16)[:16]  # sid cookie
cookie_token = AUTH.create_login_session(username)  # ret_session cookie

# Session registry
AUTH.register_or_touch_session(
    session_id=session_id,
    username=username,
    temp_dir=str(temp_dir),
    log_path=str(log_path),
    status="ACTIVE"
)
```

### 2. Session Maintenance
```python
# Periodic heartbeat (every request)
AUTH.touch_session(session_id)  # Updates last_seen timestamp

# Temp directory structure
ret_runtime/
├── sessions/
│   └── {session_id}/
│       ├── uploads/
│       ├── extracted/
│       ├── output/
│       └── chroma/
└── logs/
    └── {session_id}/
        └── session_{session_id}.log
```

### 3. Session Cleanup
```python
# Manual logout
AUTH.logout_cleanup(
    cookie_token=cookie_token,
    session_id=session_id,
    username=username,
    temp_dir=temp_dir,
    chroma_collection_name=collection_name,
    chroma_parent_dir=chroma_dir,
    reason="LOGOUT"
)

# Automatic idle cleanup (admin console)
idle_threshold = now - IDLE_CLEANUP_SECONDS  # default 3600s
idle_sessions = [s for s in sessions if s.last_seen < idle_threshold]
for session in idle_sessions:
    _safe_delete_dir(session.temp_dir)  # Allowlisted deletion
    mark_session(session.session_id, "CLEANED_IDLE")
```

---

## 📝 Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/retdb  # or sqlite:///./ret.db

# Security
TOKEN_PEPPER=your-secret-pepper-string
RET_FORCE_COOKIE_SECURE=1  # Force HTTPS cookies

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002

# Application
RET_ENV=prod  # or dev
RET_DEBUG=0
RET_RUNTIME_ROOT=/path/to/ret_runtime
RET_IDLE_CLEANUP_SECONDS=3600
RET_CONSOLE_LOG=0  # Enable console logging

# Limits (optional overrides)
RET_MAX_UPLOAD_SIZE_MB=10000
RET_MAX_EXTRACT_SIZE_MB=10000
RET_CHUNK_SIZE_MB=10
```

### Settings (pydantic)
```python
class RETSettings(BaseSettings):
    # Session
    session_timeout_minutes: int = 60
    cookie_secure: bool = True
    cookie_httponly: bool = True
    cookie_samesite: str = "Lax"
    
    # Performance
    max_threads: int = 32
    max_workers_per_cpu: int = 2
    chunk_size_mb: int = 10
    cache_max_size: int = 128
    
    # AI
    ai_temperature: float = 0.65
    ai_max_tokens: int = 4000
    embedding_batch_size: int = 16
    retrieval_top_k: int = 16
    max_context_chars: int = 40000
    
    # Security
    zip_depth_limit: int = 50
    max_files: int = 10000
    max_per_file_mb: int = 1000
    max_compression_ratio: int = 200
    
    # Logging
    console_log: bool = False
    max_log_chars: int = 2200
    log_rotation_mb: int = 2
    log_backup_count: int = 5
```

---

## 🚀 Deployment Checklist

### Production Readiness
- [ ] Set `RET_ENV=prod`
- [ ] Configure PostgreSQL (not SQLite)
- [ ] Set strong `TOKEN_PEPPER`
- [ ] Enable HTTPS (`RET_FORCE_COOKIE_SECURE=1`)
- [ ] Configure Azure OpenAI credentials
- [ ] Set up log rotation
- [ ] Configure backup strategy for database
- [ ] Set up monitoring (ops_logs, error_events)
- [ ] Review resource limits per user role
- [ ] Test session cleanup automation
- [ ] Verify audit log retention policy

### Security Hardening
- [ ] Disable debug mode (`RET_DEBUG=0`)
- [ ] Disable console logging (`RET_CONSOLE_LOG=0`)
- [ ] Review secret redaction patterns
- [ ] Test path traversal prevention
- [ ] Validate ZIP bomb protection
- [ ] Test lockout policy
- [ ] Verify CSRF protection (SameSite cookies)
- [ ] Test XSS prevention (httponly cookies)
- [ ] Review admin last-admin protection
- [ ] Test session fixation prevention

---

## 📚 Key Dependencies

```
streamlit>=1.30.0
streamlit-cookies-controller
pandas
openpyxl
lxml
bcrypt
sqlalchemy
psycopg2-binary  # PostgreSQL
chromadb
openai  # Azure OpenAI
pydantic-settings
python-dotenv
```

---

## 🎨 UI/UX Design Principles

### Brand Identity
- **Primary Color**: #FFC000 (golden yellow)
- **Typography**: Verdana Pro Black
- **Design Language**: Professional enterprise with modern SaaS aesthetics

### Accessibility
- High contrast ratios (WCAG AA compliant)
- Focus-visible rings (3px solid)
- Reduced motion support
- Semantic HTML
- ARIA labels

### Responsive Design
- Desktop-first (1520px max width)
- Tablet support (900px breakpoint)
- Mobile-friendly forms

---

## 📞 Support & Troubleshooting

### Common Issues

**Issue**: User cannot log in (account locked)
**Solution**: Admin unlocks via admin console → User Management → Unlock User

**Issue**: Password reset token expired
**Solution**: Admin generates new token → User Management → Generate Reset Token

**Issue**: Session cleanup not working
**Solution**: Check `IDLE_CLEANUP_SECONDS` env var, verify allowlisted paths

**Issue**: AI chat not responding
**Solution**: Verify Azure OpenAI credentials, check ChromaDB indexing status

**Issue**: ZIP upload fails
**Solution**: Check user limits, verify ZIP is not corrupted, check compression ratio

---

## 📄 License & Credits

**Application**: RET v4 (Resource Extraction Tool)
**Architecture**: Modular Python with Streamlit replace with FastAPI + Vue 3 + Pinia
**Database**: SQLAlchemy ORM (SQLite)
**AI**: Azure OpenAI + ChromaDB

