# Financial Data Ingestion & Portfolio Viewer

A full-stack take-home: a webhook-driven service that ingests client account data
from ZIP files into a relational database, plus a UI for inspecting the nested
**client → accounts → holdings** data it produces.

## Structure

| Folder                     | What it is                                                                 |
|----------------------------|----------------------------------------------------------------------------|
| [`backend/`](backend/)     | FastAPI service — webhook ingestion, SQLite persistence, JSON read API      |
| [`frontend/`](frontend/)   | Vite + React + TypeScript UI for browsing a client's portfolio              |

Each folder has its own README with full details:
[backend/README.md](backend/README.md) · [frontend/README.md](frontend/README.md)

## How it fits together

```
Partner ──POST /webhook──► Backend ──► Download ZIP ──► Parse ──► SQLite
                              │                                     │
Browser ◄──── React UI ──GET /clients/{id}──────────────────────────┘
```

## Quick start

Run the two services in separate terminals.

**Backend** (from [`backend/`](backend/)):

```bash
pip install -r requirements.txt
uvicorn main:app --reload          # http://localhost:8000  (docs at /docs)
python test_local.py               # ingest sample data (server must be running)
```

**Frontend** (from [`frontend/`](frontend/)):

```bash
npm install
copy .env.example .env             # set VITE_API_BASE_URL=http://localhost:8000
npm run dev                        # http://localhost:5173
```

Then enable **Fetch from API** in the UI and load a client id that exists in the
database (e.g. `CLT-29481`). Without a `.env`, the frontend falls back to bundled
sample data so it works offline.

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite (swap `DATABASE_URL` for Postgres in prod), httpx
- **Frontend:** React 19, TypeScript, Vite, React Router
