# RET v5

RET is a workbench for Oracle E-Business Suite and Oracle Fusion configuration extracts. Upload
an export (nested ZIPs, XML, XML.GZ, CSV or XLSX) and RET:

- unpacks it and groups files by Oracle module (`AR`, `FUN`, `INV`, …);
- converts record-oriented XML into tables you can browse, search, edit and export (CSV or XLSX);
- builds the **Business Structure** (business group → ledger → legal entity → operating unit →
  inventory organization) from the converted data;
- **compares** two extracts dataset by dataset, down to the changed cells;
- answers questions about the data with **citations that open the exact source row**, using Azure
  OpenAI when configured, or a retrieval-only mode when not.

Architecture: open [`docs/architecture.html`](docs/architecture.html) in a browser for the interactive
diagram (source: [`docs/architecture.json`](docs/architecture.json)).

| Layer | Choice |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, lxml, openpyxl, Argon2 |
| Database | SQLite (WAL) for users, sessions, jobs, datasets, chat and the FTS5 search index |
| Files | `DATA_DIR/workspaces/<id>/{sources,datasets}` — addressed only through database ids |
| Frontend | Vue 3 + TypeScript (strict), Vite, Vue Router; API types generated from OpenAPI |
| AI | SQLite FTS5 (BM25) retrieval + Azure OpenAI chat completions (streamed) |

## Run it locally

Prerequisites: Python 3.12+, Node 20.19+ or 22.12+. Python packages always go into the project
virtual environment.

**Backend** (terminal 1):

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.lock   # pinned versions (same as CI)
.venv/bin/pip install --no-deps -e .              # Windows: .venv\Scripts\pip …
cp .env.example .env                       # optional
.venv/bin/uvicorn app.main:app --reload --port 8000
```

On first start with an empty database, RET applies migrations and creates an `admin` account.
In development the password is printed once to the console; set `BOOTSTRAP_ADMIN_PASSWORD` to
choose it.

**Frontend** (terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards `/api` to the backend, so the browser sees one origin.

## Deploy

```bash
cd frontend && npm ci && npm run build      # writes frontend/dist
cd ../backend && ENV=production BOOTSTRAP_ADMIN_PASSWORD='…' \
  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

When `frontend/dist` exists the API serves the app itself, so there is no CORS and the session
cookie stays first-party. Put it behind a TLS-terminating reverse proxy (production cookies are
`Secure`) and set an upload limit there too (e.g. nginx `client_max_body_size`).

Run **one** API process: background jobs run in-process and SQLite allows one writer. Jobs left
running by a restart are marked failed on the next start, and the user can retry. Back up
`DATA_DIR` (it holds both the database and the files). For many concurrent writers or several API
instances, move to PostgreSQL and an external job queue.

Health checks: `GET /api/health` (liveness) and `GET /api/ready` (database reachable). Every
response carries an `X-Request-ID`, which also appears in every log line and in 500 error
messages.

## Tests

```bash
cd backend
.venv/bin/pytest                          # unit + API integration tests on a real SQLite database
.venv/bin/ruff check app tests alembic && .venv/bin/ruff format --check app tests alembic
.venv/bin/mypy app                        # strict

cd ../frontend
npm run typecheck
npm run build
npx playwright install chromium          # once
# End-to-end: start the backend serving the build, then
BASE_URL=http://127.0.0.1:8000 RET_PASSWORD='<admin password>' npm run e2e
```

The end-to-end script drives ten journeys through the real UI on desktop, dark and 390 px mobile, and fails on console errors,
failed requests or horizontal overflow. After an API change, run `npm run gen:api` to regenerate
the TypeScript types. A stale contract then fails `npm run typecheck`.

GitHub Actions (`.github/workflows/ci.yml`) runs all of this on every pull request and push to
`main`:
- backend lint, format, `mypy --strict` and tests on Python 3.12 and 3.13;
- frontend type check, build and `npm audit`;
- the end-to-end journeys against the built app;
- a check that the committed API types match the backend.

Backend dependencies are pinned in `backend/requirements-dev.lock`. After changing
`pyproject.toml`, regenerate it with
`uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements-dev.lock`.

## Security model

- **Sessions:** a random token in an `HttpOnly`, `SameSite=Strict` cookie scoped to `/api`. Only
  its SHA-256 is stored, so a session can be revoked instantly. Passwords use Argon2. Accounts
  lock for 15 minutes after 5 failures. Unknown and wrong-password logins take the same time and
  return the same error.
- **CSRF:** cookie-authenticated writes must carry a trusted `Origin` (the server's own origin or
  `ALLOWED_ORIGINS`).
- **Access:** workspaces, datasets, jobs, comparisons and conversations are visible only to their
  owner. Any other user gets 404, not 403. Admins manage accounts but cannot read other users'
  data.
- **Password resets:** an admin issues a single-use code that expires after 60 minutes. Users can
  file a request, and the response is the same whether or not the account exists.
- **Uploads:** the size limit applies while the body streams in. The nested ZIP scan has budgets
  for total bytes, file count, nesting depth and compression ratio. Member paths are normalised,
  and files on disk get server-generated names.
- **XML:** parsed with entity resolution, DTD loading and network access all disabled.
- **Exports:** XLSX cells are always written as text, so a value like `=HYPERLINK(…)` never runs
  as a formula.
- **AI:** retrieval only searches the requesting workspace. Retrieved rows go to the model marked
  as untrusted data, and the answer is sanitised (DOMPurify) before it is rendered.
- **Headers:** strict CSP (`script-src 'self'`), `nosniff`, frame denial, `no-store` on API
  responses, and HSTS in production. Every security-relevant action goes to the audit log
  (Admin → Audit log).

## What changed from v4

v5 is a rewrite. It keeps v4's behaviour where it was correct and deliberately changes it where
v4 was wrong.

**Kept**
- Module grouping rules (2–3 letter prefix; batch and root-container ZIPs never become groups).
- The record-detection and flattening conventions (`Parent.Child`, `[2]` for repeated siblings,
  `@attr`).
- Upper-case output names with a deterministic `__SHA8` suffix on collisions.
- The strict joins of the Business Structure.
- Ignoring WHO/audit columns when comparing.
- The Oracle module catalogue.

**Fixed**
- **Security:**
  - Comparison drilldown accepted server file paths from the client, so any user could read any
    file.
  - File names in edit, delete and preview could escape the session folder.
  - Sessions without an owner were readable by anyone.
  - XML parsing allowed entity expansion.
- **Data loss:**
  - Columns that first appeared after row 10,000 of a large XML were silently dropped.
  - Every value was truncated to 300 characters (the limit is now Excel's 32,767).
  - Attributes on the record element were ignored.
- **Grouping:** files outside any business ZIP were grouped as `ROO`. They are now grouped by
  folder or filename.
- **Comparison:**
  - Columns were aligned by position, so reordered columns read as all-modified. They are now
    aligned by name.
  - Rows are now matched regardless of order.

**Removed**
- Celery/Redis, LangGraph, LangChain, ChromaDB, DSPy, pandas, matplotlib and Mermaid.
- The admin "AI agent". Letting a model choose admin actions is an authorisation risk.
- Legacy `.xls` (BIFF) input: convert those files to XLSX or CSV first.
- v4's PostgreSQL data is **not migrated**. Re-upload extracts into v5, and recreate users in
  Admin.

## Project layout

```
backend/app/
  main.py          app factory: middleware (request id, CSRF, headers), routers, SPA serving
  security.py      passwords, sessions, guards, audit
  models.py        ORM models (schema changes go through alembic/versions)
  routers/         auth, admin, workspaces (+datasets, AI), comparisons
  services/        scanning, flatten, workspaces, datasets, comparison, structure, search,
                   assistant, jobs, oracle_catalog
backend/tests/     pytest suite
frontend/src/
  api/             client.ts (typed fetch, upload, SSE) and generated schema.d.ts
  views/           pages; views/ws/ holds the workspace tabs
  components/      DataGrid, GroupTabs, DiffTable, StructureTree, dialogs, …
  styles/app.css   design tokens (light/dark) and base components
frontend/e2e/      end-to-end journey and fixtures
docs/              architecture diagram (source JSON + rendered HTML)
```

## License

MIT (see `LICENSE`).
