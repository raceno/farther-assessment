# Financial Data Ingestion Service

A webhook-driven service that ingests client account data from ZIP files and persists it to a relational database.

## Architecture

```
POST /webhook  ──►  Download ZIP  ──►  Parse JSON files  ──►  Upsert to DB
     │                                                              │
     └── Returns 202 immediately        Clients ──► Accounts ──► Holdings
         (processes in background)
```

## Stack

| Layer     | Choice       | Why                                              |
|-----------|-------------|--------------------------------------------------|
| Framework | FastAPI      | Async, typed, auto docs at /docs                |
| Database  | SQLite       | Zero setup locally; swap `DATABASE_URL` for Postgres in prod |
| ORM       | SQLAlchemy   | Battle-tested, supports upserts cleanly         |
| HTTP      | httpx        | Async-friendly, timeout support                 |

## Setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoints

| Method | Path                      | Description                            |
|--------|---------------------------|----------------------------------------|
| GET    | /health                   | Liveness probe                         |
| GET    | /clients/{client_id}      | Nested client + accounts + holdings (JSON) |
| POST   | /webhook                  | Async — returns 202, processes in background |
| POST   | /ingest                   | Sync — blocks and returns full report  |
| GET    | /docs                     | Auto-generated Swagger UI              |

## CORS (local frontend)

By default, `http://localhost:5173` is allowed for browser requests from Vite. Override with a comma-separated list:

```bash
set CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## Test

```bash
# With server running in another terminal:
python test_local.py
```

## Example webhook call

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/data.zip"}'
```

## Database Schema

```
clients
  client_id (PK), first_name, last_name, email, advisor_id, last_updated, ingested_at

accounts
  account_id (PK), client_id (FK), account_type, custodian, opened_date,
  status, cash_balance, total_value, ingested_at

holdings
  id (PK = account_id:cusip), account_id (FK), ticker, cusip, description,
  quantity, market_value, cost_basis, price, asset_class, ingested_at
```

## Key Design Decisions

**Idempotency** — Re-delivering the same webhook is safe. Clients are upserted
by `client_id`, and holdings are fully replaced per account on each ingest.

**Fault isolation** — One bad JSON file doesn't abort the batch. Each file is
wrapped in a try/except; errors are logged and reported without stopping the job.

**Background processing** — `/webhook` returns 202 immediately so the partner's
HTTP client doesn't time out waiting for us to finish downloading and parsing.

**Replace vs diff for holdings** — Holdings are deleted and re-inserted on each
ingest. Simpler than diffing nested arrays and guarantees the DB always matches
the latest snapshot.
