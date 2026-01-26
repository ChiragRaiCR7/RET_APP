# RET_APP
A SIMPLE XML TO CSV App with AI Features
# RETv4 — FastAPI Backend

This repository contains RETv4 backend (FastAPI). The project is split across phases:
- Phase 1..9: app core, DB, auth, conversion, comparison, AI, admin, workers, middleware
- Phase 10: tests, alembic migration for Jobs, CI, documentation & production checklist

---

## Quick start (development)

1. Copy and edit environment variables:
   ```bash
   cp .env.example .env
   # edit .env to supply DB url, jwt secret, redis url, azure keys (optional)



Nice — thanks. I treated everything you already uploaded as the complete project and I’ve analyzed both frontend and backend. Below I give a clear, actionable **project structure**, short **file-by-file purpose**, the **integration points** (what endpoints the frontend needs and how to call them), **small code changes** you should apply to make frontend ↔ backend work locally **without Docker**, and a step-by-step run guide. I’ll also point out the small, high-impact security changes you should make now.

I **assume** you want to run the app locally (Vite dev server for frontend, Uvicorn for backend) without Docker. I’ve kept instructions practical so you can get to a working local dev environment quickly.

---

# 1 — Project layout (final structure)

This is the recommended logical tree for your repo (combine what you uploaded). Adjust names/paths if your repo differs.

```
/ (repo root)
├─ frontend/
│  ├─ index.html                                  # SPA entry. :contentReference[oaicite:0]{index=0}
│  ├─ package.json                                # npm scripts, deps. :contentReference[oaicite:1]{index=1}
│  ├─ vite.config.js                              # alias @ -> src + dev proxy. :contentReference[oaicite:2]{index=2}
│  ├─ src/
│  │  ├─ main.js / index.js                        # app bootstrap (router/pinia register) — your file loaded from index.html. :contentReference[oaicite:3]{index=3}
│  │  ├─ api/
│  │  │  └─ api.js                                 # axios instance used by store/components. :contentReference[oaicite:4]{index=4}
│  │  ├─ stores/
│  │  │  └─ authStore.js                           # pinia auth store (token, user). :contentReference[oaicite:5]{index=5}
│  │  ├─ composables/
│  │  │  ├─ useAuth.js                             # fetchMe on mount. :contentReference[oaicite:6]{index=6}
│  │  │  └─ useTheme.js                            # theme management. :contentReference[oaicite:7]{index=7}
│  │  ├─ views/ components/ (LoginView, MainView, components)   # your .vue files (UI). (many were uploaded) 
│  │  └─ assets/ styles/                            # tokens.css, base.css, components.css. :contentReference[oaicite:8]{index=8} :contentReference[oaicite:9]{index=9} :contentReference[oaicite:10]{index=10}
└─ backend/
   ├─ api/
   │  ├─ main.py                                    # app create + middleware + router includes. :contentReference[oaicite:11]{index=11}
   │  ├─ core/
   │  │  ├─ config.py                               # settings from env. :contentReference[oaicite:12]{index=12}
   │  │  ├─ database.py                             # SQLAlchemy engine + get_db. :contentReference[oaicite:13]{index=13}
   │  │  ├─ security.py                             # password hashing & JWT helpers. :contentReference[oaicite:14]{index=14}
   │  │  ├─ dependencies.py                         # get_current_user using OAuth2 scheme. :contentReference[oaicite:15]{index=15}
   │  │  ├─ logging_config.py                       # loguru config. :contentReference[oaicite:16]{index=16}
   │  │  └─ rbac.py                                 # role check helper. :contentReference[oaicite:17]{index=17}
   │  ├─ routers/                                   # API surface
   │  │  ├─ auth_router.py                           # /api/auth endpoints (login/refresh/password reset). :contentReference[oaicite:18]{index=18}
   │  │  ├─ conversion_router.py                     # /api/conversion endpoints. :contentReference[oaicite:19]{index=19}
   │  │  ├─ comparison_router.py                     # /api/comparison endpoints. :contentReference[oaicite:20]{index=20}
   │  │  ├─ ai_router.py                             # /api/ai index & chat. :contentReference[oaicite:21]{index=21}
   │  │  ├─ admin_router.py                          # /api/admin endpoints. :contentReference[oaicite:22]{index=22}
   │  │  └─ job_router.py                            # /api/jobs endpoints. :contentReference[oaicite:23]{index=23}
   │  ├─ models/                                    # SQLAlchemy models (users, sessions, job, logs). :contentReference[oaicite:24]{index=24} :contentReference[oaicite:25]{index=25}
   │  ├─ services/                                  # business logic (auth_service, conversion_service...). :contentReference[oaicite:26]{index=26} :contentReference[oaicite:27]{index=27}
   │  ├─ integrations/                              # AzureOpenAI, Chroma wrapper. :contentReference[oaicite:28]{index=28} :contentReference[oaicite:29]{index=29}
   │  ├─ middleware/                                # correlation_id, logging, rate_limit, error_handler. :contentReference[oaicite:30]{index=30} :contentReference[oaicite:31]{index=31} :contentReference[oaicite:32]{index=32} :contentReference[oaicite:33]{index=33}
   │  ├─ utils/                                     # xml_utils, file_utils, csv_utils, vector_utils, diff_utils. :contentReference[oaicite:34]{index=34} :contentReference[oaicite:35]{index=35} :contentReference[oaicite:36]{index=36} :contentReference[oaicite:37]{index=37}
   │  └─ workers/                                   # celery config + worker tasks (conversion, indexing, comparison). :contentReference[oaicite:38]{index=38} :contentReference[oaicite:39]{index=39}
   ├─ runtime/                                      # session data persisted locally (created at runtime). :contentReference[oaicite:40]{index=40}
   └─ requirements.txt / pyproject.toml             # python deps (fastapi, sqlalchemy, chromadb, celery, redis, etc.)
```

---

# 2 — How the system works (end-to-end flow)

### Typical user conversion flow (frontend -> backend -> workers)

1. Frontend sends a ZIP file to `/api/conversion/scan` (UploadFile). Backend `scan_zip()` saves the upload into `runtime/sessions/<session_id>/input` and returns `session_id`.  
2. User clicks convert; frontend calls `/api/conversion/convert` with `{ session_id }`. Backend creates a `Job` record then enqueues a Celery `conversion_task` (worker). `conversion_task` runs `convert_session(session_id)` and writes output CSVs in `runtime/sessions/<session_id>/output`. Job status updated by the worker.   
3. When the worker completes, frontend polls `/api/jobs/{job_id}` to read status and result. When the job is `SUCCESS`, frontend calls `/api/conversion/download/{session_id}` to download zip of CSVs.  

### Typical auth flow (recommended secure flow)

1. Frontend logs in via `/api/auth/login` with username/password. Backend returns an access token (JWT) and sets a **HttpOnly Secure cookie** called `refresh_token` (recommended change). The frontend stores access token **in memory** (or Pinia state) — **do not store refresh token in localStorage**. (I’ll show exact code below.) 
2. Frontend sets axios to include `Authorization: Bearer <access_token>` header for API calls that require auth and `withCredentials: true` so the refresh cookie can be used by the browser for refresh calls. 
3. When access token expires, frontend calls `/api/auth/refresh` (the backend reads refresh_token cookie and rotates it) to get a new access token. The backend rotates the refresh token (issue new raw token cookie and expire old one server-side). 
4. To log out, call `/api/auth/logout` (implement) that deletes login session(s) server-side and clears cookie on client. `admin_service.force_logout_user` already provides server-side forced logout. 

### AI indexing & chat

* Convert outputs can be indexed via `/api/ai/index` which enqueues an indexing job. The `ai_service` reads CSVs in output dir, chunk texts, gets embeddings from Azure, and stores embeddings & docs into Chroma collection. Chat queries call `/api/ai/chat` that uses the collection to find top contexts and then calls Azure chat to produce an answer. Monitor size & costs for embeddings/chat.   

---

# 3 — Integration points (exact endpoints frontend needs)

Use these exact endpoints from frontend (examples):

* Authentication

  * `POST /api/auth/login` — body: `{ username, password }` → returns access_token and sets refresh cookie (recommended). 
  * `POST /api/auth/refresh` — use cookie (no body) → returns new access token. 
  * `POST /api/auth/password-reset/request` — `{ username }`
  * `POST /api/auth/password-reset/confirm` — `{ token, new_password }` 

* Conversion

  * `POST /api/conversion/scan` — multipart file upload (form field `file`) → returns `{ session_id, ... }`. 
  * `POST /api/conversion/convert` — `{ session_id }` → returns job id. 
  * `GET /api/conversion/download/{session_id}` — download zip of CSVs. 

* Jobs

  * `GET /api/jobs/{job_id}` — poll for job progress & status. 

* Comparison

  * `POST /api/comparison/compare` — `{ left_session_id, right_session_id }` → returns job id (async). 

* AI

  * `POST /api/ai/index` — `{ session_id, collection }` → enqueue indexing (async). 
  * `POST /api/ai/chat` — `{ collection, question }` → synchronous chat response. 

* Admin (requires admin role)

  * `POST /api/admin/users` etc. — user management. 

---

# 4 — Minimal code changes to integrate frontend + backend (no Docker)

Below are the **small, targeted code changes** to implement on both sides so the app runs locally and the frontend talks to the backend correctly and securely **without Docker**.

> Summary of the changes:
>
> * Frontend: set axios `baseURL` from env (`VITE_API_BASE`), use `withCredentials: true`, update auth store to keep access token in memory and to call refresh endpoint on 401. 
> * Backend: change login to set refresh cookie, change refresh endpoint to read cookie and rotate refresh token, tighten CORS to real origin(s).  

## 4.1 Frontend — `src/api/api.js` (axios) — patch

Replace your axios instance with this variant:

```js
// src/api/api.js
import axios from 'axios'

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // important: allow cookies to be sent
})

// attach access token from in-memory store (example uses local AuthStore import)
instance.interceptors.request.use((config) => {
  // import the store lazily to avoid circular issues
  const store = JSON.parse(sessionStorage.getItem('retv4_access')) || null
  if (store?.access_token) {
    config.headers.Authorization = `Bearer ${store.access_token}`
  }
  return config
})

// response interceptor to handle 401 -> try refresh once
let isRefreshing = false
let failedQueue = []

function processQueue(err, token = null) {
  failedQueue.forEach(prom => {
    if (err) prom.reject(err)
    else prom.resolve(token)
  })
  failedQueue = []
}

instance.interceptors.response.use(
  res => res,
  async (err) => {
    const originalRequest = err.config
    if (err.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise(function(resolve, reject) {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          originalRequest.headers.Authorization = 'Bearer ' + token
          return instance(originalRequest)
        }).catch(e => Promise.reject(e))
      }

      originalRequest._retry = true
      isRefreshing = true
      try {
        const r = await instance.post('/auth/refresh') // refresh uses cookie
        const token = r.data.access_token
        // save short-lived access in sessionStorage or in-memory store
        sessionStorage.setItem('retv4_access', JSON.stringify({ access_token: token }))
        instance.defaults.headers.Authorization = 'Bearer ' + token
        processQueue(null, token)
        return instance(originalRequest)
      } catch (refreshErr) {
        processQueue(refreshErr, null)
        // optional: clear auth state and redirect to login
        throw refreshErr
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(err)
  }
)

export default instance
```

Notes:

* I used `sessionStorage` for simplicity to store access token only for current tab; you can instead use Pinia state and memory-only storage. Do **not** store refresh tokens in localStorage. 

## 4.2 Frontend — auth store minimal behavior

* On login success, **do not** persist refresh token: backend will set cookie. Save access token in `sessionStorage` or Pinia state. Use `useAuth()` composable to call fetchMe after login. `useAuth()` is already present; ensure it calls `auth.fetchMe()` when a token exists.  

## 4.3 Backend — login endpoint: set HttpOnly cookie (patch)

Replace or adjust `auth_router.login` to set the refresh token as cookie (instead of returning raw token in JSON). Example:

```py
# api/routers/auth_router.py
from fastapi.responses import JSONResponse

@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, req.username, req.password)
    tokens = issue_tokens(db, user, request)
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    resp = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    resp.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,  # secure only in production
        samesite="Lax",
        max_age=7 * 24 * 3600
    )
    return resp
```

(You must also update `issue_tokens()` to keep returning raw refresh_token as it already does.) 

## 4.4 Backend — refresh endpoint: read cookie & rotate (patch)

Change refresh endpoint to read cookie and **rotate** refresh token:

```py
# api/routers/auth_router.py (refresh)
from fastapi.responses import JSONResponse

@router.post("/refresh")
def refresh(request: Request, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "Missing refresh token")

    session = validate_refresh_token(db, refresh_token)
    if not session:
        raise HTTPException(401, "Invalid refresh token")

    user = db.query(User).get(session.user_id)
    if not user or not user.is_active or user.is_locked:
        raise HTTPException(403, "Account disabled")

    # revoke old refresh token
    revoke_refresh_token(db, refresh_token)

    # create a new login session (rotated)
    new_refresh = create_login_session(
        db=db,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    access_token = create_token(subject=str(user.id),
                                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    resp = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    resp.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        max_age=7 * 24 * 3600
    )
    return resp
```

Files involved: `auth_router`, `session_service` (`create_login_session`, `validate_refresh_token`, `revoke_refresh_token`). 

## 4.5 Backend — CORS tightening (patch)

Edit `main.py` to set `CORS_ORIGINS` from env and avoid `"*"`. Example:

```py
# main.py (app.add_middleware(CORSMiddleware, ...))
app.add_middleware(
  CORSMiddleware,
  allow_origins=settings.CORS_ORIGINS,  # e.g., ["http://localhost:5173"]
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
```

Set `VITE_API_BASE` in frontend to `http://localhost:8000` (or full URL including port) and set backend `CORS_ORIGINS` to that origin.  

---

# 5 — Running locally (no Docker) — step-by-step

Below are the minimal steps to run the frontend and backend locally. I assume you will run them on the same machine.

## Prereqs

* Node 18+ and npm/yarn/pnpm. 
* Python 3.10+ and pip.
* Redis installed and running locally at default port (used by celery & rate limiting). If you cannot run Redis, you must remove/replace rate limit middleware and set Celery broker to a filesystem or other broker. (Recommended: install Redis via package manager or run `redis-server` locally.)  
* (Optional) PostgreSQL or use SQLite for quick dev. If using PostgreSQL, create DB and set `DATABASE_URL`. Otherwise set `DATABASE_URL=sqlite:///./dev.db`. 

## Backend steps

1. Create `.env` at repo root (or `backend/.env`) with minimum values:

```
DATABASE_URL=sqlite:///./dev.db
JWT_SECRET_KEY=replace_with_strong_secret
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_VERSION=...
AZURE_OPENAI_CHAT_MODEL=gpt-4o ...
AZURE_OPENAI_EMBED_MODEL=...
REDIS_URL=redis://localhost:6379/0
RET_RUNTIME_ROOT=./runtime
CORS_ORIGINS=http://localhost:5173   # Vite default dev origin
DEBUG=True
```

(Adapt values to your environment.) 

2. Install Python deps:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# if you don't have requirements.txt, install: fastapi uvicorn sqlalchemy alembic argon2-cffi python-jose[cryptography] chromadb openai redis celery loguru defusedxml
```

3. Create DB & tables (quick dev method):

```py
# quick bootstrap script (create_tables.py)
from api.core.database import engine, Base
from api.models import models  # ensure models are imported
Base.metadata.create_all(bind=engine)
```

Run:

```bash
python create_tables.py
```

(Or add Alembic migrations for production.) 

4. Start Redis:

```bash
redis-server
```

5. Start Celery worker (in project root):

```bash
# assumes celery_app.py exists and broker is redis
celery -A api.workers.celery_app.celery_app worker --loglevel=info -Q default
```

(Exact module path may vary — check `celery_app.py` you uploaded.) 

6. Start backend server:

```bash
# from backend/
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` (FastAPI docs) to inspect endpoints.

## Frontend steps

1. Install Node deps:

```bash
cd frontend
npm install
```

2. Set Vite env:

* Create `.env` in `frontend/`:

```
VITE_API_BASE=http://localhost:8000
```

(If you use a port other than 8000, change accordingly.) 

3. Start dev server:

```bash
npm run dev
# default: http://localhost:5173
```

Now the frontend (on `localhost:5173`) can call backend `http://localhost:8000/api/...`. Ensure `CORS_ORIGINS` contains `http://localhost:5173`. 

---

# 6 — Minimal migration-less DB bootstrap script

If you don't want Alembic now, use this quick script `create_tables.py` (place in backend root):

```py
# create_tables.py
from api.core.database import engine
# import models modules to ensure they register with Base
import api.models.models as models
from api.core.database import Base

Base.metadata.create_all(bind=engine)
print("Tables created")
```

Run `python create_tables.py` after setting `DATABASE_URL`.

---

# 7 — Safety & production notes (short)

* **Do not** use `CORS_ORIGINS=["*"]` in production. Set to explicit origins. 
* Use secure secrets manager for keys rather than `.env`. 
* Always enable `secure=True` on cookies in production (HTTPS).
* Use Alembic for DB migrations.
* Add monitoring & alerting (Prometheus/Grafana) and structured logs shipped to a logging system.

---

# 8 — Small optional UX/Dev improvements I recommend now

* In router guards (frontend), if `auth.isAuthenticated` is true but `auth.user` is null, call `fetchMe()` and wait before allowing route navigation — avoids race on page refresh. `useAuth()` already attempts `fetchMe` on mount; ensure route guard awaits initialization.  
* Lazy-load heavy UI components (data table, chat, admin panel) using dynamic `import()` in router to lower initial bundle. 
* Add `prefers-reduced-motion` uses and ensure modals trap focus (a11y). CSS already has focus-visible and reduced-motion rules. 

---

# 9 — Quick checklist to implement now (copy/paste)

1. In backend `.env` set `CORS_ORIGINS` to `http://localhost:5173` and `REDIS_URL` to `redis://localhost:6379/0`. 
2. Update `auth_router.login` to set refresh cookie (code above). 
3. Update `auth_router.refresh` to read cookie and rotate token (code above). 
4. Update frontend `src/api/api.js` to `withCredentials: true` and implement refresh-on-401 logic (code above). 
5. Start services locally: Redis > create DB tables > Celery worker > Uvicorn > Vite dev. (See commands above.) 

---

# 10 — I can do next for you (pick one)

* Provide full patched files (auth_router.py, api.js, main.py) with diffs you can apply.
* Create a `run-local.md` script that automates local setup (virtualenv, pip install, create_tables, start commands).
* Add a small unit test suite to validate auth flow (login → refresh → revoke) using `pytest` and test client.

Tell me which and I’ll produce the exact code/files/patches.

---

If you want me to **now** produce the full patched files I described (backend `auth_router` changes, frontend `api.js` changes, `main.py` CORS tweak, and a `create_tables.py`), say “Please produce the patches” and I’ll output them as ready-to-paste files.
