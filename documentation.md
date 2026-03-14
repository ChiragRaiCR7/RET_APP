# RET v4 — Complete Application Documentation

## What this document is

This file is the single-source documentation for the RET v4 application in this repository. It covers:

- full application overview
- backend and frontend architecture
- step-by-step setup instructions
- local development workflow
- user guide
- admin guide
- operational commands
- deployment strategies for **10–50** and **100–500** users
- file-by-file utility reference for the main application source code

> **Security note**
>
> This repository contains a real `backend/.env` file. This documentation **does not reproduce any live secrets**. Use placeholders, rotate any existing exposed secrets, and never commit production credentials.

---

## Table of contents

1. [Application summary](#application-summary)
2. [Core capabilities](#core-capabilities)
3. [Technology stack](#technology-stack)
4. [Architecture overview](#architecture-overview)
5. [Repository structure](#repository-structure)
6. [Step-by-step setup guide](#step-by-step-setup-guide)
7. [How to run the application](#how-to-run-the-application)
8. [User guide](#user-guide)
9. [Admin guide](#admin-guide)
10. [API overview](#api-overview)
11. [Operational commands](#operational-commands)
12. [Deployment strategy for 10–50 users](#deployment-strategy-for-1050-users)
13. [Deployment strategy for 100–500 users](#deployment-strategy-for-100500-users)
14. [Scaling constraints in the current codebase](#scaling-constraints-in-the-current-codebase)
15. [Troubleshooting](#troubleshooting)
16. [File utility reference](#file-utility-reference)

---

## Application summary

**RET v4** is a FastAPI + Vue 3 application for:

- scanning uploaded ZIP/XML payloads
- extracting and grouping XML and related files
- converting XML into CSV/XLSX outputs
- comparing converted outputs and uploaded files
- editing session-scoped CSV content before download
- indexing converted data into a RAG workflow
- querying indexed business data using Azure OpenAI-backed chat
- administering users, sessions, logs, and AI configuration

The application is designed around **session-based processing**. Each uploaded job gets a session directory under `backend/runtime/sessions/{session_id}/`, where source files, extracted files, converted outputs, and AI index artifacts are stored.

---

## Core capabilities

### End-user capabilities

- log in with JWT-based authentication
- upload a ZIP or XML file
- recursively scan nested ZIPs
- auto-detect groups based on module prefixes
- convert XML files to CSV or XLSX
- preview generated files
- download all outputs or selected groups
- edit generated CSV files in-session
- compare ZIP/XML/CSV outputs
- embed selected groups into the AI search index
- ask natural-language questions against indexed data
- download AI chat transcripts

### Admin capabilities

- create, update, delete, unlock, and role-manage users
- generate reset tokens and review reset requests
- inspect user sessions and clean up old sessions
- view audit logs and operational logs
- access admin statistics
- use an AI admin agent for guided admin tasks
- configure AI indexing behavior

---

## Technology stack

### Backend

- **Python**: 3.12+
- **Framework**: FastAPI
- **ORM**: SQLAlchemy async
- **Database**: PostgreSQL (preferred), SQLite for dev/testing
- **Validation**: Pydantic v2
- **Auth**: JWT + HttpOnly refresh cookies + Argon2 password hashing
- **AI**: Azure OpenAI
- **Vector storage**: ChromaDB
- **XML parsing**: lxml / ElementTree fallback
- **Excel output**: openpyxl-compatible XML generation + pandas when needed
- **Background jobs**: in-process async task manager with job-tracking records

### Frontend

- **Framework**: Vue 3
- **Bundler**: Vite
- **Routing**: Vue Router
- **State**: Pinia
- **HTTP client**: Axios with refresh-token retry handling
- **Charts**: Chart.js + vue-chartjs
- **UI helpers**: Headless UI, Lucide Vue

---

## Architecture overview

### High-level flow

$$
\text{Browser} \rightarrow \text{Vue SPA} \rightarrow \text{FastAPI API} \rightarrow \text{Services} \rightarrow \text{DB / Filesystem / ChromaDB / Azure OpenAI}
$$

### Backend architecture layers

1. **Routers**
   - expose HTTP endpoints
   - validate requests using Pydantic schemas
   - inject dependencies like current user and DB session

2. **Services**
   - implement business logic
   - own conversion, comparison, storage, auth, and AI workflows

3. **Core infrastructure**
   - configuration
   - database initialization
   - security helpers
   - rate limiting
   - structured logging
   - error handling

4. **Workers**
   - execute long-running jobs asynchronously
   - update job status/progress in the database

5. **Storage model**
   - runtime session data stored locally under `backend/runtime/`
   - metadata stored in JSON files plus database rows
   - AI vector state stored per session

### Frontend architecture layers

1. **Views**
   - `LoginView.vue`
   - `MainView.vue`
   - `AdminView.vue`

2. **Stores**
   - authentication state
   - conversion/session state
   - toast notifications

3. **Components**
   - workflow controls
   - file uploader
   - AI chat panels
   - comparison UI
   - admin tools

4. **API layer**
   - centralized Axios instance with auth injection and refresh retry logic

---

## Repository structure

```text
RET_App/
├─ LICENSE
├─ setup.bat
├─ documentation.md
├─ backend/
│  ├─ .env
│  ├─ pyproject.toml
│  ├─ alembic.ini
│  ├─ start.py
│  ├─ recreate_demo.py
│  ├─ README.md
│  ├─ alembic/
│  ├─ api/
│  │  ├─ main.py
│  │  ├─ core/
│  │  ├─ middleware/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ routers/
│  │  ├─ services/
│  │  ├─ integrations/
│  │  ├─ utils/
│  │  └─ workers/
│  ├─ scripts/
│  ├─ runtime/
│  └─ logs/
├─ frontend/
│  ├─ index.html
│  ├─ package.json
│  ├─ vite.config.js
│  ├─ README.md
│  ├─ public/
│  └─ src/
└─ Examples/
```

### Important runtime folders

- `backend/runtime/sessions/` — per-session input/output/AI artifacts
- `backend/logs/` — application logs
- `Examples/` — sample XML test data used for validation and manual testing

---

## Step-by-step setup guide

## Prerequisites

Install the following first:

### Required

- Python **3.12+**
- Node.js **18+** (Node 20 LTS recommended)
- npm **9+**
- Git

### Optional but recommended

- PostgreSQL 15+ for realistic local or production-like development
- `asyncpg` if your `DATABASE_URL` uses `postgresql+asyncpg://`
- `psycopg[binary]` if your `DATABASE_URL` uses `postgresql+psycopg://`

### Windows recommendation

Use **PowerShell** and run commands from the repository root unless stated otherwise.

---

## Step 1: Clone or open the repository

```powershell
cd D:\WORK\RET_App
```

---

## Step 2: Set up the backend virtual environment

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

---

## Step 3: Install backend dependencies

### Recommended installation

```powershell
pip install -e ".[dev]"
```

This installs the FastAPI application and development tools declared in `backend/pyproject.toml`.

### If you use PostgreSQL with `asyncpg`

Your current `backend/.env` uses an **asyncpg-style DSN**, so make sure the driver is installed:

```powershell
pip install asyncpg
```

### If you use PostgreSQL with `psycopg`

Use this instead:

```powershell
pip install "psycopg[binary]"
```

> **Important**
>
> The current repository is **pyproject-based**, not `requirements.txt`-based. The included `setup.bat` still references `requirements.txt`, so the commands in this document are the recommended source of truth.

---

## Step 4: Configure backend environment variables

Create or update `backend/.env`.

### Safe development example (SQLite)

```env
APP_NAME=RET-v4
ENV=development
DEBUG=true

API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=300
REFRESH_TOKEN_EXPIRE_DAYS=70

DATABASE_URL=sqlite+aiosqlite:///./runtime/test.db
RET_SESSION_DB=./runtime/ret_session.db
RET_RUNTIME_ROOT=./runtime
LOG_LEVEL=INFO

AI_STRATEGY=advanced
AZURE_OPENAI_API_KEY=replace-me
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_MODEL=your-chat-deployment
AZURE_OPENAI_EMBED_MODEL=your-embedding-deployment
```

### PostgreSQL example

```env
DATABASE_URL=postgresql+asyncpg://ret_user:your_password@localhost:5432/ret_db
```

### Current repo note

The checked-in `.env` currently points to PostgreSQL and Azure services. Do **not** reuse those values outside your controlled environment. Rotate them if they were ever shared.

---

## Step 5: Initialize the database

From `backend/` with the virtual environment active:

```powershell
python -m scripts.init_db --seed-demo
```

This initializes the database and seeds common demo accounts.

### Related user-management scripts

```powershell
python -m scripts.create_admin --create-demo
python -m scripts.demo_users
python -m scripts.fix_role_case
python recreate_demo.py
```

---

## Step 5b: Apply database migrations

After initializing the database, apply all schema migrations so the schema matches the current models:

```powershell
python -m alembic upgrade head
```

`alembic` is shipped as a dependency in `pyproject.toml`, so it will be available after `pip install -e ".[dev]"`.

### Why this step is required separately

`init_db.py` uses SQLAlchemy `create_all()` to create tables. `create_all()` only creates **new** tables — it does not add columns to tables that already exist. Alembic migrations handle all subsequent column additions and schema changes. Running `alembic upgrade head` after `init_db.py` ensures all columns are present.

### If you see "DuplicateTable" or "DuplicateColumn" errors

This happens when `create_all()` already applied some columns that a migration also tries to add. Use the following to tell Alembic the database is already at the target revision without re-running migrations:

```powershell
# Find the current highest revision in alembic/versions/
# Typically this matches the latest 0NNN_*.py file, e.g. 0005

python -m alembic stamp 0005
python -m alembic upgrade head
```

After stamping, `upgrade head` only runs revisions that have not been applied yet.

### Alembic command note on Windows

If `alembic` is not on your `PATH` (no `alembic.exe` generated in the venv), use `python -m alembic` as shown above. This always works when the virtual environment is active and alembic is installed.

---

## Step 6: Start the backend API

### Recommended

```powershell
python start.py
```

### Alternative direct command

```powershell
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Expected backend URLs

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`
- Base API prefix: `http://localhost:8000/api/v1`

---

## Step 7: Set up the frontend

Open a new terminal from the repository root:

```powershell
cd frontend
npm install
```

If you want the frontend to use a custom API base URL directly instead of the Vite proxy, create `frontend/.env.local`:

```env
VITE_API_BASE=http://localhost:8000/api/v1
```

---

## Step 8: Start the frontend

```powershell
npm run dev
```

### Expected frontend URL

- App: `http://localhost:5173`

The Vite proxy in `frontend/vite.config.js` forwards `/api` to `http://localhost:8000`.

---

## Step 9: First login

Use a seeded development user, such as:

- `admin / admin123`
- `demo / demo123`
- additional demo users if created by scripts

If login fails, rerun:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.init_db --seed-demo --reset-demo-passwords
```

---

## How to run the application

## Local development

### Terminal 1 — backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python start.py
```

### Terminal 2 — frontend

```powershell
cd frontend
npm run dev
```

---

## Local validation checks

### Backend health

```powershell
curl http://localhost:8000/health
```

### Advanced backend validation

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.validate_advanced
python -m scripts.validate_parallel_conversion
```

### Frontend production build

```powershell
cd frontend
npm run build
npm run preview
```

---

## User guide

## 1. Logging in

1. Open `http://localhost:5173`
2. Enter username and password
3. On success, the frontend stores the access token in state and uses the refresh cookie for renewal
4. If your role is `admin`, you can access `/admin`

---

## 2. Utility workflow: upload, convert, download

The main workspace is centered around the **Utility** tab.

### Step-by-step

1. **Upload** a ZIP or XML source using the uploader
2. **Scan** the uploaded archive
3. Review detected **groups** and file counts
4. Choose output format: `csv` or `xlsx`
5. Run **Bulk Convert ALL**
6. Preview generated files
7. Download:
   - all files
   - a single group ZIP
   - a single file
8. Optionally enable **Edit Mode** and download the modified output ZIP

### What the backend does

- creates a session directory
- extracts allowed files
- groups files by module prefix
- converts XML in parallel
- stores session metadata for later preview/download

---

## 3. Editing converted files

Edit mode is **session-only**.

You can:

- change individual cell values
- add rows
- add new CSV files
- remove files from the session output
- save edits back to the session output folder

This does **not** permanently rewrite source archives unless you explicitly export the modified data.

---

## 4. Comparing two datasets

Use the **Compare (ZIP/XML/CSV)** tab.

### Typical comparison workflow

1. prepare two processed sessions or two upload files
2. start comparison
3. wait for the comparison job to finish
4. review summary statistics:
   - added rows
   - removed rows
   - modified rows
   - changed files/groups
5. open drilldown views for detailed row/cell deltas

---

## 5. Asking RET AI questions

Use the **Ask RET (Advanced RAG)** tab.

### Step-by-step

1. Convert your data first
2. Select one or more groups for embedding
3. Trigger indexing
4. Wait for embedding to finish
5. Ask questions such as:
   - “What are the top 5 entities by count?”
   - “Summarize differences across this group.”
   - “Which rows mention a specific code?”
6. Review the answer, citations, and optional visualizations
7. Download the transcript if needed

### AI response behavior

The AI layer can:

- transform user queries
- retrieve semantic and lexical matches
- build RAG context
- answer with citations
- generate chart/table instructions that the frontend can render

---

## Admin guide

## 1. Admin dashboard access

Admins log in normally and then use the `/admin` route.

### Admin-only areas include

- user management
- reset and approval flows
- session inspection
- audit logs
- ops logs
- AI admin agent

---

## 2. Creating users

### From the UI

An admin can create users with:

- direct password setup
- token-first onboarding flow

### From the command line

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.create_admin --username alice --password "StrongPass123!" --role admin
```

---

## 3. Resetting passwords

The application supports password reset request workflows and token generation.

Admin responsibilities include:

- reviewing pending requests
- approving or rejecting them
- generating reset tokens when needed

---

## 4. Unlocking users

If a user is locked out after repeated failed logins, an admin can unlock the account from the admin UI or by fixing records through backend scripts.

---

## 5. Session cleanup

Admins can inspect active sessions and trigger cleanup of old or idle session data.

Session cleanup removes:

- runtime session folders
- cached entries
- AI artifacts where applicable

---

## 6. Audit and operational logs

Admin users can inspect:

- **audit logs** — admin actions and governance changes
- **ops logs** — application operations and runtime events

These are critical for support, troubleshooting, and compliance reviews.

---

## API overview

The application mounts its main routes under:

```text
/api/v1
```

## Main route groups

### Authentication

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`

### Conversion and workflow

- `POST /api/v1/conversion/scan`
- `POST /api/v1/conversion/convert`
- `GET /api/v1/conversion/files/{session_id}`
- `GET /api/v1/conversion/preview/{session_id}/{filename}`
- download and edit endpoints under the same router

### Comparison

- session-to-session comparison
- upload/file comparison
- drilldown detail endpoints

### AI / RAG

Mounted under:

```text
/api/v1/v2/ai
```

Because `rag_router.py` defines its own `prefix="/v2/ai"` and `main.py` mounts it under `API_PREFIX`.

Practical endpoints include:

- chat
- embedding groups
- status
- transcript download
- cleanup

### Admin

- stats
- user CRUD
- session listing/cleanup
- reset request management
- logs
- AI admin agent

### Jobs

- `GET /api/v1/jobs/{job_id}`

---

## Operational commands

## Backend commands

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

# install
pip install -e ".[dev]"
pip install asyncpg

# initialize DB
python -m scripts.init_db --seed-demo

# run API
python start.py
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# demo/admin users
python -m scripts.create_admin --create-demo
python -m scripts.create_admin --username bob --password "StrongPass123!" --role user
python -m scripts.demo_users
python recreate_demo.py

# maintenance
python -m scripts.cleanup_sessions
python -m scripts.fix_role_case
python -m scripts.add_is_deleted_column
python -m scripts.migrate_all_columns

# validation
python -m scripts.validate_advanced
python -m scripts.validate_parallel_conversion
```

## Frontend commands

```powershell
cd frontend

# install
npm install

# dev
npm run dev

# production build
npm run build
npm run preview

# lint
npm run lint
```

## Database migration commands

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

# Apply all pending migrations (run this after init_db.py on every setup)
python -m alembic upgrade head

# Check current migration revision
python -m alembic current

# Show migration history
python -m alembic history

# Downgrade one revision
python -m alembic downgrade -1

# Stamp the database to a specific revision without running migrations
# Use this when tables were created externally (e.g. via create_all()) and
# alembic_version does not yet exist or is behind.
python -m alembic stamp <revision_id>

# Create a new migration revision (auto-detect model changes)
python -m alembic revision --autogenerate -m "describe your change"
```

### Alembic on Windows — important note

Depending on the Python/pip version, `alembic.exe` may or may not be placed in `.venv\Scripts\`. Always prefer:

```powershell
python -m alembic <command>
```

This works reliably whenever the virtual environment is activated.

---

## Deployment strategy for 10–50 users

This size range is well served by a **single-node deployment** if usage is moderate and not all users are running heavy XML conversions simultaneously.

## Recommended architecture

- **1 application VM** or physical server
- **1 PostgreSQL instance** (same server or managed DB)
- **Nginx** as reverse proxy
- **Gunicorn + Uvicorn workers** for backend
- **built frontend static files** served by Nginx
- **local runtime storage** for session directories
- **local or attached SSD** for ChromaDB and runtime files

## Suggested sizing

- **CPU**: 4–8 vCPU
- **RAM**: 16–32 GB
- **Disk**: 200–500 GB SSD
- **OS**: Ubuntu 22.04 LTS or similar Linux server

## Why this works for 10–50 users

Because the current codebase:

- stores session files on local disk
- uses an in-process background task manager
- uses local runtime metadata patterns
- benefits from avoiding distributed coordination

A single-node deployment keeps this simple and matches the current implementation very well.

## Production backend run command

```bash
cd /opt/ret-app/backend
source .venv/bin/activate
gunicorn api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300
```

## Build frontend

```bash
cd /opt/ret-app/frontend
npm ci
npm run build
```

## Example systemd service

```ini
[Unit]
Description=RET v4 Backend
After=network.target

[Service]
User=ret
Group=ret
WorkingDirectory=/opt/ret-app/backend
Environment="PATH=/opt/ret-app/backend/.venv/bin"
ExecStart=/opt/ret-app/backend/.venv/bin/gunicorn api.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 300
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Example Nginx config

```nginx
server {
    listen 80;
    server_name ret.example.com;

    root /opt/ret-app/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Operational recommendations

- use PostgreSQL instead of SQLite
- place `backend/runtime/` on fast SSD storage
- schedule backups for DB and runtime exports
- enable log rotation
- monitor CPU spikes during conversions and embeddings
- use HTTPS in front of Nginx

---

## Deployment strategy for 100–500 users

At this scale, the **current codebase can still be used**, but the deployment must evolve beyond a single-node local-storage model.

## Recommended architecture

- **2–4 backend API nodes** behind a load balancer
- **1–N dedicated worker nodes** for heavy conversion and embedding jobs
- **managed PostgreSQL**
- **shared object storage** or **shared filesystem** for session runtime artifacts
- **Redis** for distributed cache / rate limiting / job coordination
- **real distributed task queue** (Celery + Redis/RabbitMQ) instead of only in-process tasks
- **persistent vector storage strategy** for ChromaDB or an external vector store
- **centralized logging and metrics**

## Suggested sizing

### API layer

- 2–4 nodes
- 8 vCPU each
- 16–32 GB RAM each

### Worker layer

- 2–4 nodes
- 8–16 vCPU each
- 32–64 GB RAM each

### Database

- managed PostgreSQL with backups, failover, and connection pooling

### Storage

- shared session artifact storage (Azure Blob / S3 / NFS / Azure Files)
- separate persistent volume for vector index data if Chroma remains local-file based

## Why this change is necessary

The current implementation includes several single-node assumptions:

- session files are stored under local `backend/runtime/sessions/`
- background jobs are launched via an in-process async task manager
- session cache and rate-limiting patterns are not fully distributed
- ChromaDB is persisted locally by session

For 100–500 users, especially with simultaneous conversions and embeddings, you need distributed coordination and shared storage.

## Recommended modernization steps

1. move session artifacts to shared/object storage
2. replace or extend the in-process task manager with **real Celery workers**
3. add Redis for queueing and possibly rate-limit state
4. run the frontend as static files behind CDN/Nginx
5. add load balancer + health checks
6. add observability:
   - Prometheus
   - Grafana
   - application log aggregation
   - Sentry or equivalent error monitoring
7. enforce secret management via environment injection or vault

## Example backend startup for containers

```bash
gunicorn api.main:app \
  --workers 6 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 600
```

## Recommended deployment model

- containerize backend and frontend
- use Kubernetes, ECS, App Service, or VM scale sets
- use CI/CD for build/test/deploy
- support rolling deployments and rollback

---

## Scaling constraints in the current codebase

These are important to understand before larger-scale deployment.

## 1. Session storage is local

`backend/api/services/storage_service.py` writes to local runtime directories.

### Impact

- single-node friendly
- multi-node requires shared storage or sticky sessions

## 2. Background jobs are primarily in-process

`backend/api/workers/celery_app.py` provides a Celery-like interface but is actually an async in-process task manager.

### Impact

- fine for single-node development and small-team deployments
- not ideal for distributed horizontal scaling without enhancement

## 3. Session cache is local-process/local-disk oriented

`backend/api/core/session_cache.py` uses in-memory + SQLite persistence patterns.

### Impact

- fast locally
- not distributed by default

## 4. ChromaDB is session-scoped and locally persisted

The AI stack stores vector state per session.

### Impact

- simple and isolated
- larger installations need storage design and cleanup discipline

---

## Troubleshooting

## Backend does not start

### Check environment

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -c "from api.core.config import settings; print(settings.ENVIRONMENT, settings.API_PREFIX)"
```

### Check DB driver mismatch

If your `DATABASE_URL` uses `postgresql+asyncpg://`, install:

```powershell
pip install asyncpg
```

If it uses `sqlite+aiosqlite://`, ensure:

```powershell
pip install aiosqlite
```

---

## Database column not found — `UndefinedColumnError`

### Symptom

```
asyncpg.exceptions.UndefinedColumnError: column login_sessions.token_family does not exist
```

Or similar errors on startup or during login/refresh.

### Cause

The PostgreSQL database was originally created via `SQLAlchemy create_all()`, which only creates tables — it does not add new columns to existing tables. Subsequent columns added in Alembic migration revisions were never applied to the live database.

### Fix

From `backend/` with the virtual environment active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

# 1. Check current alembic state
python -m alembic current

# 2. If alembic_version table does not exist yet, stamp to the last
#    revision that was already effectively applied (tables exist).
#    Typical initial stamp (assumes migrations up to 0003 were implied by create_all):
python -m alembic stamp 0003

# 3. Apply all remaining migrations
python -m alembic upgrade head
```

If `upgrade head` fails with a `DuplicateColumn` error for a column that is already in the table (a column was added by `create_all()` before its migration existed), stamp past that revision:

```powershell
# Find the revision ID of the failing migration, e.g. 0005
python -m alembic stamp 0005
python -m alembic upgrade head
```

After this sequence, `python -m alembic current` should show the latest revision, and the missing-column error will be gone.

---

## Frontend cannot reach backend

1. confirm backend is running on port `8000`
2. confirm frontend is running on port `5173`
3. confirm `API_PREFIX=/api/v1`
4. confirm Vite proxy or `VITE_API_BASE` is correct
5. inspect browser devtools for 401/403/CORS issues

---

## Login fails for demo users

Reset and reseed demo accounts:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.init_db --seed-demo --reset-demo-passwords
```

---

## Health check fails

Check:

```powershell
curl http://localhost:8000/health
```

Then inspect:

- database connectivity
- `.env` values
- missing async DB driver
- invalid JWT or CORS settings

---

## Validation scripts fail

Run them one by one:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.validate_parallel_conversion
python -m scripts.validate_advanced
```

If AI validation fails, verify Azure OpenAI settings first.

---

## File utility reference

This section documents the utility of the main application files. Generated folders such as `node_modules/`, `dist/`, `.venv/`, `logs/`, and the many sample XML data files under `Examples/` are not individually catalogued line by line.

## Top-level files and directories

| Path | Utility |
|---|---|
| `LICENSE` | Repository license file. |
| `setup.bat` | Windows quick-start helper script; useful as a convenience starter, but currently lags behind the pyproject-based backend workflow. |
| `Examples/` | Sample XML and test input data for manual validation, conversions, and comparison experiments. |
| `backend/` | Full backend application, scripts, runtime storage, and deployment configuration. |
| `frontend/` | Vue 3 single-page application for end-user and admin workflows. |

## Backend root files

| Path | Utility |
|---|---|
| `backend/.env` | Environment-specific configuration file for database, auth, runtime, and Azure OpenAI settings. |
| `backend/alembic.ini` | Alembic migration configuration entrypoint. |
| `backend/pyproject.toml` | Python package metadata, dependencies, and tooling configuration for black, ruff, mypy, bandit, and pytest. |
| `backend/README.md` | Legacy backend guide; useful for reference but should be superseded by this document. |
| `backend/start.py` | Development startup helper that initializes the database and starts the FastAPI server. |
| `backend/recreate_demo.py` | Async utility that recreates the `demo` user and verifies its password hash. |
| `backend/test.db` | Local development/testing SQLite database file. |
| `backend/uv.lock` | Python dependency lock file generated by uv tooling. |
| `backend/alembic/` | Database migration environment and revision history. |
| `backend/logs/` | Runtime log output directory. |
| `backend/runtime/` | Runtime session storage root for uploaded files, converted outputs, and AI data. |
| `backend/scripts/` | Administrative, migration, seeding, and validation utilities. |
| `backend/api/` | Main backend application package containing FastAPI code. |

## Alembic files

| Path | Utility |
|---|---|
| `backend/alembic/env.py` | Alembic runtime environment setup for migration execution. |
| `backend/alembic/script.py.mako` | Template used to generate new migration revision files. |
| `backend/alembic/versions/` | Migration revision files for schema changes. |

## Backend API package markers

All `__init__.py` files under `backend/api/`, `backend/api/core/`, `backend/api/middleware/`, `backend/api/models/`, `backend/api/routers/`, `backend/api/schemas/`, `backend/api/services/`, `backend/api/services/ai/`, `backend/api/utils/`, and `backend/api/workers/` act as Python package markers and optional re-export points.

## Backend core files

| Path | Utility |
|---|---|
| `backend/api/core/config.py` | Central application settings model with environment-aware defaults and validation. |
| `backend/api/core/database.py` | Async SQLAlchemy engine/session setup, DB initialization, and health checks. |
| `backend/api/core/dependencies.py` | FastAPI dependency providers for current user resolution and token extraction. |
| `backend/api/core/exceptions.py` | Shared exception classes for authentication, sessions, rate limits, and service failures. |
| `backend/api/core/logging_config.py` | Configures structured logging for stdlib logging and optional loguru. |
| `backend/api/core/prompts.py` | Core LLM prompts for RAG answering, transformation, citation repair, and refusal logic. |
| `backend/api/core/prompts_visualization.py` | Visualization-specific prompting rules for charts, tables, and summaries. |
| `backend/api/core/rbac.py` | Role-based access control helpers used by routers and dependencies. |
| `backend/api/core/security.py` | Password hashing, password verification, and JWT token creation/verification helpers. |
| `backend/api/core/session_cache.py` | Async session cache layer used for rate limiting and persistent cached session metadata. |

## Backend middleware files

| Path | Utility |
|---|---|
| `backend/api/middleware/correlation_id.py` | Adds or propagates a request correlation ID for end-to-end tracing. |
| `backend/api/middleware/error_handler.py` | Converts unhandled exceptions into consistent JSON responses and logs stack traces. |
| `backend/api/middleware/logging_middleware.py` | Logs each request path, response code, and duration. |
| `backend/api/middleware/rate_limit.py` | Applies request rate limiting with exempt paths and cache-backed counters. |
| `backend/api/middleware/security_headers.py` | Attaches HTTP security headers to outgoing responses. |

## Backend model files

| Path | Utility |
|---|---|
| `backend/api/models/models.py` | ORM models for users, login sessions, reset flows, user limits, audit logs, ops logs, and error events. |
| `backend/api/models/job.py` | ORM model and enums for async background job tracking and progress reporting. |

## Backend schema files

| Path | Utility |
|---|---|
| `backend/api/schemas/admin.py` | Pydantic request/response models for admin-facing operations. |
| `backend/api/schemas/advanced.py` | Schemas for XLSX conversion and legacy advanced feature payloads. |
| `backend/api/schemas/ai.py` | Schemas for chat, embedding, transcript, and AI workflow responses. |
| `backend/api/schemas/auth.py` | Schemas for login, token responses, and password-reset flows. |
| `backend/api/schemas/common.py` | Common response wrappers such as `MessageResponse` and `JobCreatedResponse`. |
| `backend/api/schemas/comparison.py` | Schemas for comparison requests, summaries, deltas, and drilldown models. |
| `backend/api/schemas/conversion.py` | Schemas for ZIP scan responses, file previews, conversion listings, and edit operations. |

## Backend router files

| Path | Utility |
|---|---|
| `backend/api/routers/admin_router.py` | Exposes admin endpoints for user management, stats, logs, sessions, and AI admin actions. |
| `backend/api/routers/advanced_router.py` | Exposes advanced endpoints for XLSX generation and related conversion helpers. |
| `backend/api/routers/auth_router.py` | Exposes login, refresh, logout, reset, and current-user endpoints. |
| `backend/api/routers/comparison_router.py` | Exposes comparison endpoints for sessions, uploaded files, and drilldown details. |
| `backend/api/routers/conversion_router.py` | Exposes scan, convert, preview, download, edit, and cleanup endpoints for the main workflow. |
| `backend/api/routers/files_router.py` | Provides file/session helper routes for scan/session retrieval and deletion. |
| `backend/api/routers/job_router.py` | Exposes job-status lookup for async operations. |
| `backend/api/routers/rag_router.py` | Exposes unified v2 AI endpoints for chat, embedding, transcript export, and cleanup. |

## Backend integration and utility files

| Path | Utility |
|---|---|
| `backend/api/integrations/azure_openai.py` | Retry and backoff utilities for Azure OpenAI sync and async calls. |
| `backend/api/utils/io_utils.py` | Atomic JSON/text/bytes write helpers and safe deletion/read utilities. |

## Backend service files

| Path | Utility |
|---|---|
| `backend/api/services/admin_service.py` | Implements admin business rules, logging, stats, and AI indexing configuration persistence. |
| `backend/api/services/advanced_ai_service.py` | Implements the main unified RAG service, retrieval, embedding, conversation history, and citation logic. |
| `backend/api/services/auth_service.py` | Implements user authentication, token issuance, refresh, and password reset logic. |
| `backend/api/services/comparison_service.py` | Implements archive/file comparison, conversion-to-CSV for diffing, similarity scoring, and drilldown generation. |
| `backend/api/services/conversion_service.py` | Implements scan, conversion, exclusion handling, preview, edit operations, and download packaging. |
| `backend/api/services/job_service.py` | Implements job record creation, lookup, status updates, and cleanup. |
| `backend/api/services/parallel_converter.py` | Implements parallel XML conversion with worker clamping, retries, and deterministic output naming. |
| `backend/api/services/session_service.py` | Implements refresh-token session creation, validation, and revocation. |
| `backend/api/services/storage_service.py` | Manages runtime session directories, uploads, metadata, and cleanup. |
| `backend/api/services/xlsx_service.py` | Generates XLSX files from CSV or in-memory row sets, including multi-sheet output. |
| `backend/api/services/xml_processing_service.py` | Scans nested ZIPs, detects supported file types, infers groups, and flattens XML records. |

## Backend AI service subpackage

| Path | Utility |
|---|---|
| `backend/api/services/ai/async_azure_openai_service.py` | Shared async Azure OpenAI wrapper for chat completions and admin-agent prompts. |
| `backend/api/services/ai/auto_embedder.py` | Handles automated embedding workflows and progress tracking for post-conversion AI indexing. |
| `backend/api/services/ai/session_manager.py` | Provides per-session AI manager lifecycle and auto-embed orchestration. |
| `backend/api/services/ai/visualization_service.py` | Parses and renders chart instructions from AI responses into image artifacts. |

## Backend worker files

| Path | Utility |
|---|---|
| `backend/api/workers/base_task.py` | Shared async helpers for marking job progress and final status in the database. |
| `backend/api/workers/celery_app.py` | Provides the in-process background task manager and Celery-like task decorator interface. |
| `backend/api/workers/comparison_worker.py` | Runs comparison jobs asynchronously and writes results back to job records. |
| `backend/api/workers/conversion_worker.py` | Runs conversion jobs asynchronously and triggers auto-embedding after completion. |
| `backend/api/workers/embedding_worker.py` | Runs embedding tasks asynchronously with queue/semaphore coordination. |

## Backend script files

| Path | Utility |
|---|---|
| `backend/scripts/add_is_deleted_column.py` | One-off SQLite migration script to add the `is_deleted` column. |
| `backend/scripts/cleanup_sessions.py` | Async maintenance script to delete expired login sessions. |
| `backend/scripts/create_admin.py` | Async CLI utility for creating admin or demo users. |
| `backend/scripts/demo_users.py` | Async CLI utility for seeding or repairing demo users. |
| `backend/scripts/fix_role_case.py` | Async migration script that normalizes role values to lowercase. |
| `backend/scripts/init_db.py` | Async database bootstrap and demo-user seeding script. |
| `backend/scripts/migrate_all_columns.py` | SQLite migration helper that adds missing user-table columns. |
| `backend/scripts/validate_advanced.py` | Validation script for advanced backend modules, routes, env config, and dependencies. |
| `backend/scripts/validate_parallel_conversion.py` | Validation script for the parallel conversion stack and related configuration. |

## Frontend root files

| Path | Utility |
|---|---|
| `frontend/index.html` | Vite HTML entry page for the SPA shell. |
| `frontend/package.json` | Frontend package metadata, dependencies, and npm scripts. |
| `frontend/README.md` | Minimal template README from Vue/Vite scaffolding. |
| `frontend/vite.config.js` | Vite configuration with Vue plugin, aliasing, dev server port, and backend proxy. |
| `frontend/public/` | Static assets copied directly into the built frontend. |
| `frontend/dist/` | Generated production frontend bundle output. |

## Frontend app entry files

| Path | Utility |
|---|---|
| `frontend/src/main.js` | Bootstraps Vue, Pinia, and Vue Router. |
| `frontend/src/App.vue` | Root component that hosts global layout and route rendering. |
| `frontend/src/router/index.js` | Defines routes and auth/admin navigation guards. |
| `frontend/src/utils/api.js` | Central Axios client with auth header injection and token refresh retry queue. |
| `frontend/src/utils/validators.js` | Shared frontend validation helpers for inputs and forms. |

## Frontend stores and composables

| Path | Utility |
|---|---|
| `frontend/src/stores/authStore.js` | Stores logged-in user state, access token, refresh flow, and logout logic. |
| `frontend/src/stores/conversionStore.js` | Stores session, scan, conversion, file-preview, and download workflow state. |
| `frontend/src/stores/toastStore.js` | Stores and manages toast notifications. |
| `frontend/src/composable/useAuth.js` | Reusable auth helper logic for components. |
| `frontend/src/composable/useTheme.js` | Reusable theme-toggle and theme persistence logic. |

## Frontend views

| Path | Utility |
|---|---|
| `frontend/src/views/LoginView.vue` | Login page for authentication and reset flows. |
| `frontend/src/views/MainView.vue` | Main end-user workspace containing Utility, Compare, and AI tabs. |
| `frontend/src/views/AdminView.vue` | Admin dashboard for management and monitoring workflows. |

## Frontend common components

| Path | Utility |
|---|---|
| `frontend/src/components/common/BrandHeader.vue` | Global top header with branding and navigation helpers. |
| `frontend/src/components/common/DataTable.vue` | Reusable table component for structured data rendering. |
| `frontend/src/components/common/ErrorBoundary.vue` | UI guard for component-level error containment. |
| `frontend/src/components/common/ToastContainer.vue` | Renders global toast notifications from store state. |

## Frontend auth components

| Path | Utility |
|---|---|
| `frontend/src/components/auth/LoginForm.vue` | Login form component used by the login screen. |
| `frontend/src/components/auth/PasswordStrengthMeter.vue` | Displays password strength feedback for reset/create flows. |
| `frontend/src/components/auth/ResetPasswordForm.vue` | Password reset form for token-based reset completion. |

## Frontend admin components

| Path | Utility |
|---|---|
| `frontend/src/components/admin/AIAgentChat.vue` | Admin AI assistant panel for natural-language admin actions. |

## Frontend workspace components

| Path | Utility |
|---|---|
| `frontend/src/components/workspace/AIChatInterface.vue` | Chat UI for asking RAG questions and displaying answers/sources. |
| `frontend/src/components/workspace/AIPanel.vue` | Wrapper panel for AI embedding, status, and transcript actions. |
| `frontend/src/components/workspace/AutoEmbedProgress.vue` | Shows progress state for automatic embedding jobs. |
| `frontend/src/components/workspace/ComparisonPanel.vue` | Comparison UI for archives/files and drilldown results. |
| `frontend/src/components/workspace/ConversionResults.vue` | Displays grouped conversion results, previews, and downloads. |
| `frontend/src/components/workspace/EditModePanel.vue` | Handles edit-mode actions such as adding/updating/removing files and rows. |
| `frontend/src/components/workspace/EditModeToggle.vue` | Enables or disables session edit mode. |
| `frontend/src/components/workspace/FileUploader.vue` | Handles drag/drop or manual upload of ZIP/XML files. |
| `frontend/src/components/workspace/GroupSelector.vue` | Group selection UI for filtered conversion or AI actions. |
| `frontend/src/components/workspace/UtilityPanel.vue` | Utility panel for general workflow helpers and secondary actions. |
| `frontend/src/components/workspace/WorkflowControls.vue` | Shared workflow action controls for scan/convert/download actions. |

## Frontend chart/message components

| Path | Utility |
|---|---|
| `frontend/src/components/workspace/charts/ChartRenderer.vue` | Renders charts returned by AI/visualization workflows. |
| `frontend/src/components/workspace/charts/DataTable.vue` | Renders chart-related or AI-generated tabular data. |
| `frontend/src/components/workspace/charts/MessageRenderer.vue` | Renders AI message content with formatting and visualization blocks. |
| `frontend/src/components/workspace/charts/StatsCardGrid.vue` | Displays summary KPI/stat cards in a grid layout. |

---

## Final recommendations

1. Treat this document as the canonical setup and operational guide.
2. Update or replace `setup.bat` so it matches the current `pyproject.toml`-based backend flow.
3. Move secrets out of the committed `.env` and rotate them.
4. For small deployments, keep the architecture single-node and simple.
5. For larger deployments, plan shared storage and distributed job execution before scaling out.

---

## Quick start recap

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install asyncpg
python -m scripts.init_db --seed-demo
python -m alembic upgrade head
python start.py

# Frontend
cd ..\frontend
npm install
npm run dev
```

Open:

- `http://localhost:5173` for the frontend
- `http://localhost:8000/docs` for the backend docs

Happy building — and may your XML always flatten nicely on the first try.
