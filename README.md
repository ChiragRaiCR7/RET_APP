# RET v4

RET v4 is a **FastAPI + Vue 3** application for XML/ZIP scanning, XML-to-CSV/XLSX conversion, comparison workflows, and Azure OpenAI-powered RAG chat.

## Start here

- Full documentation: [`documentation.md`](./documentation.md)
- Backend details: [`backend/README.md`](./backend/README.md)
- Frontend details: [`frontend/README.md`](./frontend/README.md)

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