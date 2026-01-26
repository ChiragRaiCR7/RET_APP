Backend Architecture Analysis: RET-v4 FastAPI Application
System Overview
RET-v4 is a FastAPI-based backend application for data processing, comparison, and indexing with role-based access control, job management, and Azure OpenAI integration.

Architecture Layers
1. Core Layer (api/core/)
Foundation components providing cross-cutting concerns:

Configuration (config.py)

Pydantic-based settings management
Environment variable injection
JWT, database, Redis, Azure OpenAI configuration


Database (database.py)

SQLAlchemy engine with connection pooling
Session management with automatic commit/rollback
Declarative base for ORM models


Security (security.py)

Argon2 password hashing
JWT token generation with expiration
Password verification utilities


Authentication (dependencies.py)

OAuth2 password bearer scheme
JWT token validation dependency
User extraction from tokens


Authorization (rbac.py)

Role-based access control decorator
Dynamic role requirement enforcement
Database-driven user validation


Logging (logging_config.py)

Loguru-based structured logging
Configurable log levels
Formatted output to stdout


Exception Handling (exceptions.py)

Custom HTTP exceptions (Unauthorized, Forbidden, NotFound, BadRequest)
Standardized error responses




2. Middleware Layer (api/middleware/)
Request/response pipeline processing:

Correlation ID (correlation_id.py)

Distributed tracing support
UUID generation for request tracking
Header propagation


Logging (logging_middleware.py)

Request/response logging
Duration measurement
Correlation ID attachment


Rate Limiting (rate_limit.py)

Redis-based IP rate limiting
100 requests per 60 seconds per IP
Automatic key expiration


Error Handling (error_handler.py)

Global exception catching
Structured error responses
Correlation ID in error context




3. Data Layer (api/models/)
User Management

User: Core authentication entity with roles (user/admin)
LoginSession: Refresh token management with device tracking
PasswordResetToken: Secure password reset workflow
PasswordResetRequest: Admin-approved password resets

Resource Management

UserLimit: Per-user quotas (sessions, upload size)
LimitIncreaseRequest: User-requested quota increases

Job Processing

Job: Async job tracking (conversion/comparison/indexing)

Status: PENDING → RUNNING → SUCCESS/FAILED
Progress tracking (0-100%)
JSON result storage



Observability

AuditLog: User action tracking with correlation IDs
OpsLog: Operational events logging
ErrorEvent: Error tracking with phase/path context


4. Service Layer (api/services/)
External Integrations

Azure OpenAI Client (azure_openai.py)

Text embedding generation
Chat completion API
Temperature-controlled responses


ChromaDB Client (chroma_client.py)

Vector database management
Collection lifecycle operations
Local persistence



Utility Services (api/utils/)

CSV Processing (csv_utils.py): Structured data export
Diff Computation (diff_utils.py): Row-level change detection
File Handling (file_utils.py): Secure ZIP extraction with path traversal prevention
Vector Operations (vector_utils.py): SHA256-based hashing, cosine similarity
XML Parsing (xml_utils.py): Flattened record extraction


Data Flow Architecture
Client Request
    ↓
[Correlation ID Middleware] → Assigns tracking ID
    ↓
[Rate Limit Middleware] → Redis-based throttling
    ↓
[Logging Middleware] → Request logging
    ↓
[Route Handler]
    ↓
[Authentication Dependency] → JWT validation
    ↓
[Authorization Dependency] → Role checking
    ↓
[Business Logic]
    ├→ Database Operations (SQLAlchemy)
    ├→ Vector Search (ChromaDB)
    ├→ AI Processing (Azure OpenAI)
    └→ Job Queue (Async tasks)
    ↓
[Response]
    ↓
[Error Handler] → Catches unhandled exceptions
    ↓
Client Response + Correlation ID Header

Security Architecture
Authentication Flow

User credentials → Password verification (argon2)
Access token generation (JWT, 30-min expiry)
Refresh token stored in LoginSession (7-day expiry)
Token validation on protected routes

Authorization Model

Role-based access (user/admin)
Dependency injection for role requirements
Database-backed permission checks

Data Protection

Password hashing (argon2)
Secure token storage (hashed refresh tokens)
Rate limiting per IP
Safe file extraction (path traversal prevention)


Scalability Considerations
Database

Connection pooling (pool_pre_ping=True)
Indexed columns (username, audit logs)
Relationship lazy loading

Caching/State

Redis for rate limiting
ChromaDB for vector persistence
Session-based state management

Async Processing

Job model for long-running tasks
Progress tracking (0-100%)
Result storage in JSON column


Key Design Patterns

Dependency Injection: FastAPI's dependency system for auth, DB, services
Repository Pattern: SQLAlchemy ORM with session management
Middleware Chain: Onion architecture for cross-cutting concerns
Service Layer: Business logic isolation from routes
Settings Management: Centralized config with environment overrides


Technology Stack
LayerTechnologiesFrameworkFastAPI, StarletteORMSQLAlchemy 2.x (DeclarativeBase)Authenticationpython-jose (JWT), passlib (bcrypt)DatabasePostgreSQL/MySQL (configurable via DATABASE_URL)CacheRedisVector DBChromaDBAIAzure OpenAI (chat + embeddings)LoggingLoguruValidationPydantic

Operational Features

Correlation ID Tracing: End-to-end request tracking
Structured Logging: JSON-compatible log format
Audit Trail: User actions, operational events, errors
Rate Limiting: IP-based throttling
Session Management: Multi-device support with limits
Admin Workflows: Password reset approvals, limit increases


This architecture supports a multi-tenant, audit-compliant data processing platform with AI capabilities, suitable for enterprise document management and analysis workflows.


Complete Backend Architecture: RET-v4 FastAPI Application
Full System Architecture
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│                   (Web/Mobile/API Consumer)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    MIDDLEWARE PIPELINE                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Correlation ID → 2. Rate Limit → 3. Logging          │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      ROUTE HANDLERS                              │
│     /api/auth  │  /api/admin  │  /api/jobs  │  /api/ai          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                  DEPENDENCY INJECTION                            │
│   OAuth2 Auth → RBAC → Database Session → Validation            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     SERVICE LAYER                                │
│  ┌────────────┬────────────┬────────────┬────────────────────┐ │
│  │   Auth     │   Admin    │  Storage   │  Comparison/Conv   │ │
│  │  Service   │  Service   │  Service   │      Services      │ │
│  └────────────┴────────────┴────────────┴────────────────────┘ │
│  ┌────────────┬────────────┬────────────────────────────────┐  │
│  │    AI      │  Session   │        Job Service             │  │
│  │  Service   │  Service   │                                 │  │
│  └────────────┴────────────┴────────────────────────────────┘  │
└──────────────┬───────────────────────┬──────────────────────────┘
               │                       │
               │                       │ (Async Jobs)
               ▼                       ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│   DATA LAYER         │    │    WORKER LAYER (Celery)         │
│                      │    │  ┌────────────────────────────┐  │
│  ┌────────────────┐ │    │  │  Conversion Worker         │  │
│  │  PostgreSQL/   │ │    │  │  Comparison Worker         │  │
│  │  MySQL         │ │    │  │  Indexing Worker           │  │
│  │  (SQLAlchemy)  │ │    │  └────────────────────────────┘  │
│  └────────────────┘ │    │  Base Task: JobTask (lifecycle)  │
│                      │    └──────────────────────────────────┘
│  ┌────────────────┐ │                    │
│  │  Redis         │◄───────────────────────┘
│  │  (Queue+Cache) │ │    (Broker + Backend)
│  └────────────────┘ │
│                      │
│  ┌────────────────┐ │
│  │  ChromaDB      │ │
│  │  (Vectors)     │ │
│  └────────────────┘ │
│                      │
│  ┌────────────────┐ │
│  │  File System   │ │
│  │  (Sessions)    │ │
│  └────────────────┘ │
└──────────────────────┘
         │
         ▼
┌──────────────────────┐
│  EXTERNAL SERVICES   │
│  ┌────────────────┐ │
│  │ Azure OpenAI   │ │
│  │ - Embeddings   │ │
│  │ - Chat         │ │
│  └────────────────┘ │
└──────────────────────┘

Layer-by-Layer Architecture
1. API Layer (api/routers/)
Route Modules (Inferred from schemas):

/api/auth: Authentication & authorization endpoints

POST /login → LoginRequest → TokenResponse
POST /refresh → RefreshRequest → RefreshTokenResponse
POST /password-reset/request → PasswordResetRequest
POST /password-reset/confirm → PasswordResetConfirm


/api/admin: User & audit management (admin-only)

POST /users → UserCreateRequest → UserInfo
PUT /users/{id} → UserUpdateRequest → UserInfo
DELETE /users/{id}
GET /users → List[UserInfo]
GET /audit-logs → List[AuditLogEntry]
POST /users/{id}/force-logout


/api/conversion: XML to CSV conversion

POST /scan → File upload → ZipScanResponse
POST /convert → ConversionRequest → Job creation (async)


/api/comparison: Session comparison

POST /compare → ComparisonRequest → Job creation (async)


/api/ai: Vector indexing & RAG

POST /index → IndexRequest → Job creation (async)
POST /chat → ChatRequest → ChatResponse


/api/jobs: Job status tracking

GET /jobs/{id} → Job status/progress/result




2. Schema Layer (api/schemas/)
Request/Response DTOs (Pydantic models):
Auth Module (auth.py)

LoginRequest: username, password
RefreshRequest: refresh_token
TokenResponse: access_token, refresh_token, user info
PasswordResetRequest, PasswordResetConfirm

Admin Module (admin.py)

UserCreateRequest: username, password, role
UserUpdateRequest: role, is_active, is_locked (all optional)
UserInfo: Complete user representation
AuditLogEntry: Audit log structure

Conversion Module (conversion.py)

ZipScanResponse: session_id, xml_count, files[]
ConversionRequest: session_id
ConversionResponse: session_id, stats{total, success, failed}

Comparison Module (comparison.py)

ComparisonRequest: left_session_id, right_session_id
ComparisonResponse: summary + results[]
FileComparisonResult: filename, similarity, deltas[]
DeltaRow: row_id, change_type (added/removed/modified), before, after

AI Module (ai.py)

IndexRequest: session_id, collection
ChatRequest: collection, question
ChatResponse: answer + citations[]
RetrievalChunk: content, metadata, score

Common Module (common.py)

SuccessResponse[T]: Generic success wrapper
ErrorResponse: Standardized error format
HealthCheck: Service health status


3. Service Layer (api/services/)
Authentication Service (auth_service.py)
Responsibilities: User authentication, token lifecycle

authenticate_user(): Validate credentials, check account status
issue_tokens(): Generate access + refresh tokens with device tracking
refresh_tokens(): Validate refresh token, issue new access token
request_password_reset(): Generate secure reset token (SHA256 hashed)
confirm_password_reset(): Validate token, update password, mark token as used

Security Features:

Silent failure on non-existent users (prevent enumeration)
Token expiration enforcement
Hashed token storage
Account lock/active status checks

Admin Service (admin_service.py)
Responsibilities: User management, audit logging

create_user(): Create with hashed password, duplicate check
update_user(): Partial update with validation
delete_user(): Hard delete from database
list_users(): Ordered by creation date
force_logout_user(): Revoke all user sessions
write_audit_log(): Structured logging with correlation
list_audit_logs(), list_ops_logs(): Paginated log retrieval

Session Service (session_service.py)
Responsibilities: Refresh token lifecycle management

create_login_session(): Generate 48-byte token, hash with SHA256
validate_refresh_token(): Hash validation, expiration check, last_used update
revoke_refresh_token(): Immediate session termination
_hash_token(): SHA256 token hashing utility

Token Security:

48-byte URL-safe tokens (secrets.token_urlsafe)
SHA256 hashing before storage
7-day default expiration
Automatic cleanup on expiration

Storage Service (storage_service.py)
Responsibilities: File system session management

create_session_dir(): UUID-based session isolation
get_session_dir(): Path traversal protection
save_upload(): Secure file persistence
cleanup_session(): Safe directory removal

Directory Structure:
./runtime/sessions/
  ├── {session_uuid}/
  │   ├── input/       # Uploaded files
  │   ├── output/      # Processed CSVs
  │   └── extracted/   # Unzipped XMLs
Conversion Service (conversion_service.py)
Responsibilities: XML → CSV batch conversion

scan_zip(): Extract, validate, inventory XML files
convert_session(): Batch convert XMLs using flatten_xml()
Error tracking per file (success/failed counts)

Workflow:

Upload ZIP → Create session
Safe extraction (path traversal check)
XML discovery (recursive glob)
Return file inventory for preview
Async conversion via Celery

Comparison Service (comparison_service.py)
Responsibilities: Multi-file session diff analysis

compare_sessions(): Cross-session CSV comparison
File-level cosine similarity (SHA256 vector hashing)
Row-level diff computation (added/removed/modified)
Aggregate statistics (average similarity)

Output Structure:
json{
  "summary": {
    "total_files": 10,
    "matched_files": 8,
    "average_similarity": 0.8523
  },
  "results": [
    {
      "filename": "data.csv",
      "similarity": 0.92,
      "deltas": [...]
    }
  ]
}
AI Service (ai_service.py)
Responsibilities: RAG (Retrieval-Augmented Generation)

index_session(): Chunk CSV files, embed via Azure OpenAI, store in ChromaDB
chat_with_collection(): Vector search + LLM answering with citations
_chunk_text(): 800-character sliding window chunking

RAG Pipeline:

Indexing: CSV → chunks → embeddings → ChromaDB
Query: Question → embed → vector search (top 5)
Generation: Contexts + system prompt → Azure OpenAI
Response: Answer + cited chunks with similarity scores

Metadata Tracking:

Session ID per chunk
Document source
Similarity scores for provenance

Job Service (job_service.py)
Responsibilities: Job record management

create_job(): Initialize with PENDING status
get_job(): Status/progress retrieval


4. Worker Layer (api/workers/)
Celery Configuration (celery_app.py)
python- Broker: Redis (task queue)
- Backend: Redis (result storage)
- Serialization: JSON
- Task time limit: 60 minutes
- Task tracking: Enabled (start events)
Base Task (base_task.py)
JobTask Abstract Class - Lifecycle hooks:

before_start(): Set job status → RUNNING
on_success(): Set status → SUCCESS, progress=100%, store result
on_failure(): Set status → FAILED, log error message

Database Integration: Direct SessionLocal access (not FastAPI dependency)
Worker Tasks
Conversion Worker (conversion_worker.py)
python@celery.task(bind=True, base=JobTask)
def conversion_task(self, session_id: str, job_id: int):
    return convert_session(session_id)

Bound task (access to self)
Inherits JobTask lifecycle
Returns stats: {total_files, success, failed}

Comparison Worker (comparison_worker.py)
python@celery.task(bind=True, base=JobTask)
def comparison_task(self, left_session_id: str, right_session_id: str, job_id: int):
    return compare_sessions(left_session_id, right_session_id)

Two-session comparison
Returns summary + file-level deltas

Indexing Worker (indexing_worker.py)
python@celery.task(bind=True, base=JobTask)
def indexing_task(self, session_id: str, collection: str, job_id: int):
    return {"indexed_chunks": index_session(session_id, collection)}
```
- Vector embedding generation
- ChromaDB persistence
- Returns chunk count

---

### **5. Data Layer**

#### **ORM Models** (`api/models/`)

**User Management**:
```
User
├── id (PK)
├── username (unique, indexed)
├── password_hash
├── role (user/admin)
├── is_active, is_locked
├── relationships:
│   ├── sessions: LoginSession[]
│   └── reset_tokens: PasswordResetToken[]

LoginSession
├── id (PK)
├── user_id (FK → users)
├── refresh_token_hash (SHA256)
├── ip_address, user_agent
├── expires_at, last_used_at

PasswordResetToken
├── id (PK)
├── user_id (FK → users)
├── token_hash (SHA256)
├── expires_at, used (boolean)

PasswordResetRequest (Admin approval workflow)
├── username, reason
├── status (pending/approved/rejected)
├── decided_at
```

**Resource Management**:
```
UserLimit
├── user_id (FK)
├── max_sessions (default: 3)
├── max_upload_mb (default: 10000)

LimitIncreaseRequest
├── user_id, requested_max_upload_mb
├── reason, status (pending/approved/rejected)
├── decided_at
```

**Job Tracking**:
```
Job
├── id (PK)
├── job_type (conversion|comparison|indexing)
├── status (PENDING → RUNNING → SUCCESS|FAILED)
├── progress (0-100)
├── result (JSON)
├── error (text)
├── created_at, updated_at
```

**Observability**:
```
AuditLog (User actions)
├── username, action, area
├── corr_id, message, details (JSON)
├── created_at
├── indexes: username, area

OpsLog (System events)
├── level, area, action
├── username, session_id, corr_id
├── message, details (JSON)

ErrorEvent (Error tracking)
├── username, session_id, phase
├── path, error_type, message
├── corr_id, created_at

6. Integration Layer (api/integrations/)
Azure OpenAI Client (azure_openai.py)
pythonclass AzureOpenAIClient:
    - embed_texts(texts: list[str]) → list[list[float]]
    - chat(system: str, user: str) → str
Configuration: API key, endpoint, version from settings
Models: Separate chat and embedding models
Temperature: 0.2 (deterministic responses)
ChromaDB Client (chroma_client.py)
pythonclass ChromaClient:
    - get_or_create(name: str) → Collection
    - delete(name: str)
```
**Persistence**: `./runtime/chroma/` directory
**Collections**: Named vector stores per index

---

### **7. Utility Layer** (`api/utils/`)

| Module | Functions | Purpose |
|--------|-----------|---------|
| `csv_utils.py` | `write_csv()` | DictWriter-based CSV export |
| `diff_utils.py` | `compute_row_diff()` | Row-level change detection (added/removed/modified) |
| `file_utils.py` | `safe_extract_zip()` | Path traversal protection via resolve() check |
| `vector_utils.py` | `hash_vector()`, `cosine_similarity()` | SHA256-based 32D vectors, similarity scoring |
| `xml_utils.py` | `flatten_xml()` | ElementTree-based XML → dict[] conversion |

---

## **Complete Request Flow Examples**

### **Example 1: User Login**
```
1. POST /api/auth/login {username, password}
   ↓
2. [Correlation ID Middleware] → Assign UUID
   ↓
3. [Rate Limit Middleware] → Check Redis (100/min per IP)
   ↓
4. [Route Handler] → Validate LoginRequest schema
   ↓
5. auth_service.authenticate_user()
   ├→ Query User from DB
   ├→ Check is_locked, is_active
   └→ verify_password() with bcrypt
   ↓
6. auth_service.issue_tokens()
   ├→ create_token() → JWT access token (30min)
   ├→ session_service.create_login_session()
   │  ├→ Generate 48-byte token
   │  ├→ SHA256 hash
   │  └→ Store LoginSession with device info
   └→ Return {access_token, refresh_token, user}
   ↓
7. [Response] → TokenResponse + X-Correlation-ID header
```

### **Example 2: XML to CSV Conversion (Async Job)**
```
1. POST /api/conversion/scan + ZIP file
   ↓
2. [File Upload Handler]
   ├→ storage_service.create_session_dir() → UUID session
   ├→ storage_service.save_upload() → ./runtime/sessions/{uuid}/input/
   ├→ safe_extract_zip() → ./runtime/sessions/{uuid}/extracted/
   └→ Glob *.xml files → Return inventory
   ↓
3. POST /api/conversion/convert {session_id}
   ↓
4. [Route Handler with Auth]
   ├→ OAuth2 dependency → Validate JWT
   ├→ get_current_user() → Extract user_id
   └→ Validate ConversionRequest schema
   ↓
5. job_service.create_job(db, "conversion")
   ├→ Insert Job record (PENDING)
   └→ Return job.id
   ↓
6. celery.send_task("conversion_task", kwargs={session_id, job_id})
   ↓
7. [Response] → {job_id} immediately (async)
   ↓
8. [Celery Worker - Background]
   ├→ JobTask.before_start() → Update status=RUNNING
   ├→ conversion_service.convert_session()
   │  ├→ Glob extracted/*.xml
   │  ├→ For each: flatten_xml() → write_csv()
   │  └→ Count success/failed
   ├→ JobTask.on_success() → status=SUCCESS, result=stats
   └→ Store in Redis backend
   ↓
9. GET /api/jobs/{job_id}
   ↓
10. [Response] → {status, progress, result}
```

### **Example 3: RAG Query with Citations**
```
1. POST /api/ai/chat {collection, question}
   ↓
2. [Auth + Validation]
   ↓
3. ai_service.chat_with_collection()
   ├→ openai_client.embed_texts([question]) → query_embedding
   ├→ chroma.get_or_create(collection).query()
   │  └→ Vector search → top 5 chunks + distances + metadata
   ├→ Concatenate contexts
   ├→ openai_client.chat(system_prompt, context + question)
   └→ Build citations with scores
   ↓
4. [Response] → ChatResponse {answer, citations[]}

Security Architecture
Authentication Layers

Password Security: Bcrypt hashing (configurable rounds)
Token Security:

Access: JWT with 30-min expiry
Refresh: SHA256-hashed 48-byte tokens, 7-day expiry


Session Tracking: Device fingerprinting (IP + User-Agent)
Account Protection: Lock/active status, force logout

Authorization Model
python@router.post("/admin/users")
async def create_user(
    user: User = Depends(require_role("admin")),  # RBAC enforcement
    db: Session = Depends(get_db),
):
    ...
```

### **Data Protection**
- Path traversal prevention (ZIP extraction)
- Session isolation (UUID directories)
- Correlation ID for tracing
- Structured audit logging

### **Rate Limiting**
- IP-based: 100 requests/60s (Redis sliding window)
- Configurable via middleware
- 429 status on limit exceeded

---

## **Observability Stack**

### **Logging Strategy**
| Log Type | Storage | Purpose |
|----------|---------|---------|
| **Application** | Stdout (Loguru) | Request/response, duration |
| **Audit** | Database (AuditLog) | User actions, compliance |
| **Operational** | Database (OpsLog) | System events |
| **Errors** | Database (ErrorEvent) | Exception tracking |

### **Tracing**
- Correlation IDs in all logs
- Request → Service → Worker chain tracking
- Header propagation (X-Correlation-ID)

### **Metrics** (Inferred)
- Request duration (LoggingMiddleware)
- Job status distribution (Job table)
- Rate limit hits (Redis counters)

---

## **Scalability Patterns**

### **Async Job Processing**
```
API (FastAPI) ──┬─→ Quick response (job_id)
                │
                └─→ Redis Queue ──→ Celery Workers (N instances)
                                    ├─→ Worker 1 (conversion)
                                    ├─→ Worker 2 (comparison)
                                    └─→ Worker 3 (indexing)
```

### **Database Optimizations**
- Indexed columns: username, audit logs (username, area)
- Relationship lazy loading
- Connection pooling with pre-ping

### **Caching Strategy**
- Redis: Rate limit counters, Celery results
- ChromaDB: Vector persistence

### **Horizontal Scaling**
- Stateless API servers (JWT validation)
- Distributed workers (Celery)
- Shared Redis/DB/ChromaDB backend

---

## **Technology Stack Summary**

| Component | Technology | Version/Config |
|-----------|------------|----------------|
| **Web Framework** | FastAPI | ASGI server |
| **ORM** | SQLAlchemy | 2.x (DeclarativeBase) |
| **Database** | PostgreSQL/MySQL | Configurable via DATABASE_URL |
| **Task Queue** | Celery | Redis broker + backend |
| **Cache** | Redis | Queue + rate limiting |
| **Vector DB** | ChromaDB | Local persistence |
| **AI** | Azure OpenAI | Chat + embeddings |
| **Auth** | python-jose | JWT (HS256) |
| **Password** | passlib | Bcrypt |
| **Validation** | Pydantic | Settings + schemas |
| **Logging** | Loguru | Structured JSON-compatible |

---

## **Deployment Architecture**
```
┌─────────────────────────────────────────────────────┐
│                  Load Balancer                       │
└─────────────┬──────────────────┬────────────────────┘
              │                  │
    ┌─────────▼─────────┐  ┌─────▼──────────┐
    │  FastAPI (N)      │  │  FastAPI (N)   │  (Horizontal scaling)
    └─────────┬─────────┘  └─────┬──────────┘
              │                  │
              └─────────┬────────┘
                        │
         ┌──────────────┼──────────────┬──────────────┐
         │              │              │              │
    ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐   ┌─────▼─────┐
    │  DB     │   │  Redis    │  │ Chroma  │   │  Azure    │
    │ Primary │   │           │  │   DB    │   │  OpenAI   │
    └─────────┘   └─────┬─────┘  └─────────┘   └───────────┘
                        │
              ┌─────────┼──────────┐
              │         │          │
         ┌────▼────┐ ┌──▼───┐ ┌───▼────┐
         │ Celery  │ │Celery│ │ Celery │  (Worker pool)
         │ Worker  │ │Worker│ │ Worker │
         └─────────┘ └──────┘ └────────┘
```

---

## **File System Structure**
```
RET-v4/
├── api/
│   ├── core/                    # Foundation
│   │   ├── config.py           # Settings management
│   │   ├── database.py         # SQLAlchemy setup
│   │   ├── dependencies.py     # JWT auth dependency
│   │   ├── rbac.py             # Role-based access
│   │   ├── security.py         # Hashing, token gen
│   │   ├── exceptions.py       # Custom HTTP exceptions
│   │   └── logging_config.py   # Loguru setup
│   │
│   ├── middleware/              # Request pipeline
│   │   ├── correlation_id.py   # UUID tracking
│   │   ├── rate_limit.py       # Redis-based throttling
│   │   ├── logging_middleware.py # Request logging
│   │   └── error_handler.py    # Global exception handler
│   │
│   ├── models/                  # ORM models
│   │   ├── models.py           # User, Session, Audit, etc.
│   │   └── job.py              # Job tracking
│   │
│   ├── schemas/                 # Pydantic DTOs
│   │   ├── auth.py             # Login, token schemas
│   │   ├── admin.py            # User management
│   │   ├── conversion.py       # Conversion requests
│   │   ├── comparison.py       # Comparison schemas
│   │   ├── ai.py               # RAG schemas
│   │   └── common.py           # Generic responses
│   │
│   ├── services/                # Business logic
│   │   ├── auth_service.py     # Authentication
│   │   ├── session_service.py  # Refresh tokens
│   │   ├── admin_service.py    # User CRUD
│   │   ├── storage_service.py  # File management
│   │   ├── conversion_service.py # XML → CSV
│   │   ├── comparison_service.py # Session diff
│   │   ├── ai_service.py       # RAG pipeline
│   │   └── job_service.py      # Job CRUD
│   │
│   ├── workers/                 # Celery tasks
│   │   ├── celery_app.py       # Celery config
│   │   ├── base_task.py        # JobTask lifecycle
│   │   ├── conversion_worker.py
│   │   ├── comparison_worker.py
│   │   └── indexing_worker.py
│   │
│   ├── integrations/            # External clients
│   │   ├── azure_openai.py     # Azure OpenAI SDK
│   │   └── chroma_client.py    # ChromaDB wrapper
│   │
│   ├── utils/                   # Shared utilities
│   │   ├── csv_utils.py
│   │   ├── diff_utils.py
│   │   ├── file_utils.py
│   │   ├── vector_utils.py
│   │   └── xml_utils.py
│   │
│   └── routers/                 # API endpoints (inferred)
│       ├── auth.py
│       ├── admin.py
│       ├── conversion.py
│       ├── comparison.py
│       ├── ai.py
│       └── jobs.py
│
├── runtime/                     # Persistent data
│   ├── sessions/               # User sessions
│   │   └── {uuid}/
│   │       ├── input/          # Uploads
│   │       ├── extracted/      # Unzipped
│   │       └── output/         # CSVs
│   └── chroma/                 # Vector DB
│
├── .env                         # Environment config
├── main.py                      # FastAPI app entry
└── celery_worker.py            # Worker process entry

Environment Configuration
env# Application
APP_NAME=RET-v4
ENV=production
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=postgresql://user:pass@localhost/retv4

# Security
JWT_SECRET_KEY=<secure-random-key>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Redis
REDIS_URL=redis://localhost:6379/0

# Storage
RET_RUNTIME_ROOT=./runtime

# Logging
LOG_LEVEL=INFO

# CORS
CORS_ORIGINS=["http://localhost:3000"]

# Azure OpenAI
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_CHAT_MODEL=gpt-4
AZURE_OPENAI_EMBED_MODEL=text-embedding-3-small

Key Architectural Decisions

Async Job Processing: Long-running tasks (conversion, comparison, indexing) delegated to Celery workers
JWT + Refresh Token Pattern: Stateless API with secure session management
Session Isolation: UUID-based filesystem directories for multi-tenant data safety
Vector RAG: ChromaDB + Azure OpenAI for document Q&A with citations
Comprehensive Observability: Correlation IDs, structured logging, audit trails
Role-Based Access: Admin vs. user roles with dependency-injected enforcement
Defensive Security: Path traversal checks, token hashing, rate limiting, account locking


This architecture supports a production-grade, multi-tenant data processing platform with AI capabilities, suitable for enterprise document conversion, comparison, and intelligent search workflows.


COMPREHENSIVE ARCHITECTURE ANALYSIS + IMPROVEMENT RECOMMENDATIONS
Complete Application Structure
RET-v4/
├── api/
│   ├── core/                    # ✅ Foundation layer
│   │   ├── config.py           # Settings management
│   │   ├── database.py         # SQLAlchemy setup
│   │   ├── dependencies.py     # JWT auth dependency
│   │   ├── rbac.py             # Role-based access
│   │   ├── security.py         # Hashing, tokens
│   │   ├── exceptions.py       # Custom exceptions
│   │   └── logging_config.py   # Loguru configuration
│   │
│   ├── middleware/              # ✅ Request pipeline
│   │   ├── correlation_id.py   # UUID tracking
│   │   ├── rate_limit.py       # Redis throttling
│   │   ├── logging_middleware.py
│   │   └── error_handler.py    # Global exceptions
│   │
│   ├── models/                  # ✅ ORM models
│   │   ├── models.py           # User, Session, Audit
│   │   └── job.py              # Job tracking
│   │
│   ├── schemas/                 # ✅ Pydantic DTOs
│   │   ├── auth.py
│   │   ├── admin.py
│   │   ├── conversion.py
│   │   ├── comparison.py
│   │   ├── ai.py
│   │   └── common.py
│   │
│   ├── services/                # ✅ Business logic
│   │   ├── auth_service.py
│   │   ├── session_service.py
│   │   ├── admin_service.py
│   │   ├── storage_service.py
│   │   ├── conversion_service.py
│   │   ├── comparison_service.py
│   │   ├── ai_service.py
│   │   └── job_service.py
│   │
│   ├── workers/                 # ✅ Celery tasks
│   │   ├── celery_app.py
│   │   ├── base_task.py
│   │   ├── conversion_worker.py
│   │   ├── comparison_worker.py
│   │   └── indexing_worker.py
│   │
│   ├── integrations/            # ✅ External clients
│   │   ├── azure_openai.py
│   │   └── chroma_client.py
│   │
│   ├── utils/                   # ✅ Utilities
│   │   ├── csv_utils.py
│   │   ├── diff_utils.py
│   │   ├── file_utils.py
│   │   ├── vector_utils.py
│   │   └── xml_utils.py
│   │
│   └── routers/                 # ✅ API endpoints
│       ├── auth_router.py       # Authentication
│       ├── admin_router.py      # User management
│       ├── conversion_router.py # XML→CSV
│       ├── comparison_router.py # Session diff
│       ├── ai_router.py         # RAG
│       └── job_router.py        # Job status
│
├── main.py                      # ✅ Application entry
├── celery_worker.py            # Worker entry (implied)
├── .env                         # Environment config
├── requirements.txt            # Dependencies
└── runtime/                     # Persistent data
    ├── sessions/
    └── chroma/

🔴 CRITICAL ISSUES IDENTIFIED
1. Missing Imports in Routers
ai_router.py:
python# ❌ MISSING
from fastapi import Depends
from sqlalchemy.orm import Session
from api.core.database import get_db
comparison_router.py:
python# ❌ MISSING
from fastapi import Depends
from sqlalchemy.orm import Session
from api.core.database import get_db
conversion_router.py:
python# ❌ MISSING
from fastapi import Depends
from sqlalchemy.orm import Session
from api.core.database import get_db
2. Incorrect Middleware Order
python# ❌ CURRENT (main.py)
app.add_middleware(CorrelationIdMiddleware)      # Should be FIRST
app.add_middleware(LoggingMiddleware)            # Should be SECOND
app.add_middleware(RateLimitMiddleware)          # Should be THIRD

# ✅ CORRECT ORDER (outer → inner)
app.add_middleware(RateLimitMiddleware)          # 3. Executes LAST
app.add_middleware(LoggingMiddleware)            # 2. Executes SECOND
app.add_middleware(CorrelationIdMiddleware)      # 1. Executes FIRST
Middleware executes in REVERSE order of registration!
3. Missing Authentication on Critical Endpoints
python# ❌ NO AUTH
@router.post("/scan")  # conversion_router.py
@router.get("/download/{session_id}")  # conversion_router.py
@router.post("/chat")  # ai_router.py

# ❌ Unauthenticated users can:
# - Upload files
# - Download any session
# - Query AI collections
4. Missing File Validation
python# ❌ conversion_router.py
async def scan(file: UploadFile = File(...)):
    # No size validation!
    # No MIME type validation beyond filename!
    data = await file.read()  # Could be 10GB
5. No Response Models on Several Endpoints
python# ❌ admin_router.py
@router.put("/users/{user_id}")  # No response_model
@router.delete("/users/{user_id}")  # Returns raw dict

# ❌ conversion_router.py
@router.post("/convert")  # No response_model
6. Insecure Session Access
python# ❌ conversion_router.py
@router.get("/download/{session_id}")
def download(session_id: str):
    # ANY user can download ANY session!
    # No ownership verification
7. No Pagination on List Endpoints
python# ❌ admin_router.py
@router.get("/users")  # Could return 100,000 users
@router.get("/audit-logs")  # Hardcoded limit=200 in service

🟡 ARCHITECTURAL IMPROVEMENTS
1. Add API Versioning
python# ✅ RECOMMENDED
# Instead of: /api/auth/login
# Use: /api/v1/auth/login

# config.py
class Settings(BaseSettings):
    API_VERSION: str = "v1"
    API_PREFIX: str = f"/api/{API_VERSION}"

# routers
router = APIRouter(prefix=f"{settings.API_PREFIX}/auth")
2. Implement Request Context
python# ✅ NEW FILE: api/core/context.py
from contextvars import ContextVar
from typing import Optional

request_context: ContextVar[dict] = ContextVar('request_context', default={})

def get_correlation_id() -> Optional[str]:
    return request_context.get().get('correlation_id')

def get_current_user_id() -> Optional[str]:
    return request_context.get().get('user_id')
3. Add Service Layer Abstractions
python# ✅ NEW FILE: api/services/base_service.py
from abc import ABC
from sqlalchemy.orm import Session

class BaseService(ABC):
    def __init__(self, db: Session):
        self.db = db
    
    def commit(self):
        self.db.commit()
    
    def rollback(self):
        self.db.rollback()
4. Implement Proper Error Handling
python# ✅ IMPROVED: api/core/exceptions.py
class AppException(HTTPException):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)
        
class ResourceNotFound(AppException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            detail=f"{resource} with id '{identifier}' not found",
            status_code=404
        )

class InsufficientPermissions(AppException):
    def __init__(self, action: str):
        super().__init__(
            detail=f"Insufficient permissions for action: {action}",
            status_code=403
        )
5. Add Job Ownership Tracking
python# ✅ IMPROVED: api/models/job.py
class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # ✅ ADD THIS
    job_type = Column(String(64), nullable=False)
    # ... rest of fields
6. Implement Pagination
python# ✅ NEW FILE: api/schemas/pagination.py
from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar("T")

class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20
    
class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
7. Add File Upload Validation
python# ✅ NEW FILE: api/core/validators.py
from fastapi import UploadFile, HTTPException

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_MIME_TYPES = ["application/zip"]

async def validate_file_upload(file: UploadFile) -> bytes:
    # Check MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Invalid file type: {file.content_type}")
    
    # Read with size limit
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Max: {MAX_FILE_SIZE} bytes")
    
    return contents

🟢 SECURITY ENHANCEMENTS
1. Session Ownership Verification
python# ✅ NEW FILE: api/core/permissions.py
from api.services.storage_service import get_session_dir
from fastapi import HTTPException

def verify_session_ownership(session_id: str, user_id: int, db: Session):
    """Verify user owns the session"""
    # Implementation depends on session-user mapping
    # Option 1: Add user_id to session directory metadata
    # Option 2: Track in database table
    pass
2. Enhanced RBAC
python# ✅ IMPROVED: api/core/rbac.py
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"

class Permission(str, Enum):
    USER_CREATE = "user:create"
    USER_DELETE = "user:delete"
    JOB_CREATE = "job:create"
    JOB_VIEW_ALL = "job:view_all"

ROLE_PERMISSIONS = {
    Role.ADMIN: [Permission.USER_CREATE, Permission.USER_DELETE, Permission.JOB_VIEW_ALL],
    Role.USER: [Permission.JOB_CREATE],
    Role.READONLY: []
}

def require_permission(permission: Permission):
    def checker(user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
        user = db.query(User).get(int(user_id))
        if permission not in ROLE_PERMISSIONS.get(user.role, []):
            raise HTTPException(403, f"Missing permission: {permission}")
        return user
    return checker
3. Rate Limiting per User
python# ✅ IMPROVED: api/middleware/rate_limit.py
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get user from JWT if present
        auth_header = request.headers.get("Authorization")
        if auth_header:
            # Extract user_id from token
            key = f"rate:user:{user_id}"
        else:
            # Fall back to IP
            key = f"rate:ip:{request.client.host}"
        
        # Rest of implementation...
4. Audit Logging Middleware
python# ✅ NEW FILE: api/middleware/audit_middleware.py
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract user context
        # Log request details
        # Continue processing
        response = await call_next(request)
        
        # Log response status
        if request.method in ["POST", "PUT", "DELETE"]:
            # Write to AuditLog
            pass
        
        return response

🔵 PERFORMANCE OPTIMIZATIONS
1. Database Query Optimization
python# ✅ IMPROVED: api/services/admin_service.py
from sqlalchemy.orm import selectinload

def list_users_with_stats(db: Session):
    return (
        db.query(User)
        .options(selectinload(User.sessions))  # Eager load
        .order_by(User.created_at.desc())
        .all()
    )
2. Caching Layer
python# ✅ NEW FILE: api/core/cache.py
import redis
import json
from functools import wraps

redis_client = redis.Redis.from_url(settings.REDIS_URL)

def cache_result(key_prefix: str, ttl: int = 300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix}:{args}:{kwargs}"
            cached = redis_client.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            result = func(*args, **kwargs)
            redis_client.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

# Usage
@cache_result("user", ttl=300)
def get_user_by_id(db: Session, user_id: int):
    return db.query(User).get(user_id)
3. Background Task Queue
python# ✅ Add task prioritization
# celery_app.py
celery.conf.update(
    task_routes={
        'api.workers.indexing_worker.indexing_task': {'queue': 'high_priority'},
        'api.workers.conversion_worker.conversion_task': {'queue': 'normal'},
        'api.workers.comparison_worker.comparison_task': {'queue': 'low_priority'},
    }
)
4. Streaming Large Responses
python# ✅ IMPROVED: conversion_router.py
from fastapi.responses import StreamingResponse

@router.get("/download/{session_id}")
def download_stream(session_id: str):
    def generate_zip():
        # Stream ZIP creation
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            for f in out_dir.glob("*.csv"):
                z.write(f, f.name)
        buffer.seek(0)
        yield buffer.read()
    
    return StreamingResponse(
        generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=result.zip"}
    )

🟣 CODE QUALITY IMPROVEMENTS
1. Type Hints Everywhere
python# ✅ IMPROVED: api/services/auth_service.py
from typing import Dict, Optional

def issue_tokens(
    db: Session,
    user: User,
    request: Request,
) -> Dict[str, any]:  # ✅ Add return type
    ...
2. Constants Management
python# ✅ NEW FILE: api/core/constants.py
class JobStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class JobType:
    CONVERSION = "conversion"
    COMPARISON = "comparison"
    INDEXING = "indexing"

class UserRole:
    ADMIN = "admin"
    USER = "user"
3. Dependency Injection Patterns
python# ✅ IMPROVED: Common dependencies
# api/core/dependencies.py

def get_current_active_user(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    user = db.query(User).get(int(user_id))
    if not user or not user.is_active:
        raise HTTPException(403, "Account disabled")
    return user

def get_current_admin_user(
    user: User = Depends(get_current_active_user)
) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin required")
    return user
4. Configuration Validation
python# ✅ IMPROVED: config.py
from pydantic import validator

class Settings(BaseSettings):
    # ... existing fields
    
    @validator('DATABASE_URL')
    def validate_database_url(cls, v):
        if not v.startswith(('postgresql://', 'mysql://')):
            raise ValueError('Invalid database URL')
        return v
    
    @validator('JWT_SECRET_KEY')
    def validate_jwt_secret(cls, v):
        if len(v) < 32:
            raise ValueError('JWT secret must be at least 32 characters')
        return v

🟠 TESTING INFRASTRUCTURE
Recommended Test Structure
pythontests/
├── conftest.py              # Pytest fixtures
├── unit/
│   ├── test_auth_service.py
│   ├── test_conversion_service.py
│   └── test_ai_service.py
├── integration/
│   ├── test_auth_flow.py
│   ├── test_conversion_flow.py
│   └── test_comparison_flow.py
└── e2e/
    └── test_complete_workflow.py
Example Test Fixture
python# ✅ conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()

@pytest.fixture
def test_client(test_db):
    def override_get_db():
        yield test_db
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

📊 MONITORING & OBSERVABILITY
1. Health Check Enhancement
python# ✅ IMPROVED: main.py
@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    try:
        # Check database
        db.execute("SELECT 1")
        
        # Check Redis
        redis_client.ping()
        
        # Check ChromaDB
        chroma.client.heartbeat()
        
        return {
            "status": "healthy",
            "services": {
                "database": "up",
                "redis": "up",
                "chroma": "up"
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )
2. Metrics Endpoint
python# ✅ NEW: Prometheus metrics
from prometheus_client import Counter, Histogram, generate_latest

request_count = Counter('http_requests_total', 'Total HTTP requests')
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
3. Structured Logging
python# ✅ IMPROVED: logging_config.py
def configure_logging():
    logger.remove()
    
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | {message}",
        serialize=True if settings.ENV == "production" else False
    )
    
    if settings.ENV == "production":
        logger.add(
            "./logs/app.log",
            rotation="500 MB",
            retention="10 days",
            compression="zip"
        )

🎯 FINAL RECOMMENDATIONS SUMMARY
CRITICAL (Fix Immediately)

✅ Add missing imports to ai_router, comparison_router, conversion_router
✅ Fix middleware order in main.py
✅ Add authentication to all sensitive endpoints
✅ Implement file size validation
✅ Add session ownership verification

HIGH PRIORITY (Fix Soon)

✅ Add API versioning (/api/v1/...)
✅ Implement pagination on list endpoints
✅ Add response models to all endpoints
✅ Implement proper error handling with custom exceptions
✅ Add job ownership tracking (user_id in Job model)

MEDIUM PRIORITY (Improvements)

✅ Add caching layer for frequently accessed data
✅ Implement permission-based access control
✅ Add audit middleware for automatic logging
✅ Enhance health check with dependency checks
✅ Add comprehensive type hints

LOW PRIORITY (Nice to Have)

✅ Add metrics/observability (Prometheus)
✅ Implement request context using ContextVars
✅ Add service layer abstractions
✅ Implement background task prioritization
✅ Add comprehensive test suite