# RET v4

RET v4 is a **FastAPI + Vue 3** application for XML/ZIP scanning, XML-to-CSV/XLSX conversion, comparison workflows, and Azure OpenAI-powered RAG chat.

## Start here

- Full documentation: [`documentation.md`](./documentation.md)
- Backend details: [`backend/README.md`](./backend/README.md)
- Frontend details: [`frontend/README.md`](./frontend/README.md)

## Documentation map

- [`documentation.md`](./documentation.md) is the canonical application guide, user guide, admin guide, and file-by-file code atlas.
- [`backend/README.md`](./backend/README.md) focuses on backend setup, API surfaces, runtime storage, and service-layer responsibilities.
- [`frontend/README.md`](./frontend/README.md) focuses on the Vue SPA structure, tab workflow, and component responsibilities.
- No editable PDF user-guide source is currently tracked in this repository; the maintained source of truth is the Markdown documentation above.

## Quick setup

From the repository root:

```powershell
cd D:\WORK\RET_App
```

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pip install asyncpg
python -m scripts.init_db --seed-demo
python -m alembic upgrade head
python start.py
```

### Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

## Local URLs

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

## Default development users

- `admin / admin123`
- `demo / demo123`

## Notes

- The backend uses `pyproject.toml`, so setup should use `pip install -e ".[dev]"` rather than `requirements.txt`.
- The complete setup, user guide, deployment guidance, and file-by-file utility reference are in [`documentation.md`](./documentation.md).

## Updated workflow highlights

- **Utility tab** handles upload, scan, async conversion, preview, and download workflows.
- **Business Structure tab** now renders a 5-layer graph from converted CSV contents, not from scanned ZIP paths.
- **Compare tab** supports session/file comparison and drilldown review.
- **AI tab** supports post-conversion indexing, retrieval, chat, and transcript export.

## Recently updated code paths

- `backend/api/schemas/business_structure.py` — response models for the Business Structure hierarchy.
- `backend/api/services/business_structure_service.py` — builds the hierarchy from converted CSV files in the session `output/` folder.
- `backend/api/routers/conversion_router.py` — exposes the Business Structure API endpoint.
- `frontend/src/views/MainView.vue` — fetches Business Structure data after conversion and passes it into the tab.
- `frontend/src/components/workspace/BusinessStructurePanel.vue` — renders the searchable 5-layer Mermaid graph with pan/zoom controls.