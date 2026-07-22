# Interview Prep Guide — Financial Ingestion Service

---

## PART 1: WALKTHROUGH QUESTIONS (They'll ask these first)

### Architecture & Design

**Q: Walk me through your overall architecture.**
> "The service has three clean layers: an HTTP layer (main.py) that handles the webhook and returns immediately, a business logic layer (ingestion.py) that owns the download-parse-upsert pipeline, and a data layer (models.py + database.py). I kept them separated so the ingestion logic can be called from a CLI, a queue worker, or a test — without touching HTTP at all."

**Q: Why FastAPI over Flask/Django?**
> "FastAPI gives me async request handling and BackgroundTasks out of the box, which is exactly what I need for a webhook that should return fast. It also auto-generates a Swagger UI at /docs which is great for demoing. Flask would work but I'd need to wire up background processing myself."

**Q: Why SQLite? Is that production-ready?**
> "SQLite is intentional for local demo — zero setup, file-based, no Docker needed. In production I'd point DATABASE_URL at Postgres. SQLAlchemy abstracts the difference so it's literally a one-line config change. The schema and queries work identically."

**Q: Why three tables instead of a flat structure?**
> "The data is naturally hierarchical: one client → many accounts → many holdings. Normalizing into three tables means I don't repeat client info on every holding row (1,000 clients × 2 accounts × ~5 holdings = 10,000 holding rows — each would duplicate client name, email, etc. if flat). It also makes queries like 'show me all holdings for a client' or 'total AUM per advisor' fast and clean."

---

### Idempotency

**Q: What happens if the webhook fires twice for the same ZIP?**
> "It's safe — fully idempotent. Clients are upserted by client_id (merge if exists, insert if not). Accounts are upserted by account_id. Holdings are fully replaced per account — I delete and re-insert them. So running the same payload 10 times leaves the database in exactly the same state as running it once."

**Q: Why replace holdings instead of upsert?**
> "Holdings don't have a natural stable business key that I can guarantee uniqueness on. A client could sell VTI and buy QQQ between two snapshots. If I upserted I might leave a stale VTI row around. Full replace per account is simpler, more correct, and still fast at this scale — ~5 holdings per account is tiny."

---

### Error Handling

**Q: What happens if one JSON file in the ZIP is malformed?**
> "I wrap each file in a try/except inside the loop. A bad file logs an error, increments the failure counter, appends to the report's error list, and the loop continues to the next file. One bad client doesn't abort the entire batch of 1,000."

**Q: What if the ZIP download fails?**
> "httpx raises an HTTPStatusError on 4xx/5xx, and a TimeoutException if the download takes longer than 30 seconds. Both bubble up from _download_zip() to the caller. In the async webhook path that means the background task logs the failure. In production I'd add retry logic with exponential backoff — probably 3 retries with 1s/2s/4s delays."

**Q: What if the database is down mid-batch?**
> "Each client is committed in its own transaction. If the DB goes down mid-batch, already-committed clients are safe. The failed ones are in the error report. Because the whole thing is idempotent, you can just re-trigger the webhook and it picks up cleanly — already-committed clients get re-upserted (no-op), failed ones succeed this time."

---

### Async / Background Tasks

**Q: Why return 202 instead of processing synchronously?**
> "Webhook deliveries typically have a short timeout — usually 5-30 seconds. Downloading a ZIP of 1,000 JSON files could easily take longer than that, especially on a slow network. If we time out, the partner marks the delivery as failed and retries, which means duplicate processing. Returning 202 immediately acknowledges receipt; the actual work happens async."

**Q: What's the risk of BackgroundTasks vs a real queue?**
> "BackgroundTasks run in the same process. If the server crashes mid-job, the job is lost — no retry. For production I'd use a proper queue like SQS or Redis Queue. The job payload (just the URL) goes on the queue, a worker process picks it up, and the queue handles retries, dead-letter queues, and visibility timeouts automatically."

---

## PART 2: EXTENSION QUESTIONS (Live coding phase)

These are the most common extensions they'll ask you to build. Have a plan for each.

### Extension 1: Add authentication to the webhook

**What they want:** Prevent random people from triggering your webhook.

**Your answer:**
```python
# Add a shared secret header check
import hmac, hashlib, os

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-secret")

@app.post("/webhook")
async def receive_webhook(request: Request, ...):
    signature = request.headers.get("X-Signature")
    body = await request.body()
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid signature")
    ...
```
> "This is HMAC-SHA256 — the partner signs the request body with a shared secret. I use `hmac.compare_digest` instead of `==` to prevent timing attacks."

---

### Extension 2: Add an endpoint to query the data

**What they want:** `GET /clients/{client_id}` or `GET /clients/{client_id}/holdings`

**Your answer:**
```python
@app.get("/clients/{client_id}")
def get_client(client_id: str, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client  # would need a Pydantic response schema

@app.get("/clients/{client_id}/holdings")
def get_holdings(client_id: str, db: Session = Depends(get_db)):
    # Join accounts → holdings for this client
    holdings = (
        db.query(Holding)
        .join(Account)
        .filter(Account.client_id == client_id)
        .all()
    )
    return holdings
```

---

### Extension 3: Track ingest history / audit log

**What they want:** Know when each batch ran, how many succeeded/failed.

**Your answer:** Add an `IngestJob` table:
```python
class IngestJob(Base):
    __tablename__ = "ingest_jobs"
    id               = Column(String, primary_key=True, default=lambda: str(uuid4()))
    url              = Column(String)
    status           = Column(String)  # PENDING / COMPLETED / FAILED
    files_found      = Column(Integer, default=0)
    clients_upserted = Column(Integer, default=0)
    clients_failed   = Column(Integer, default=0)
    error_detail     = Column(Text, nullable=True)
    started_at       = Column(DateTime)
    finished_at      = Column(DateTime, nullable=True)
```
> "This gives us a full audit trail — we can see every batch, when it ran, how many records it touched, and any errors."

---

### Extension 4: Handle large ZIPs efficiently

**What they want:** What if it's 100,000 clients, not 1,000?

**Your answer:**
1. **Stream the download** — don't load the whole ZIP into memory:
   ```python
   with httpx.stream("GET", url) as r:
       with open("/tmp/data.zip", "wb") as f:
           for chunk in r.iter_bytes():
               f.write(chunk)
   ```
2. **Process in batches** — commit every N clients instead of one at a time
3. **Move to a worker pool** — parallel processing with multiple DB connections
4. **Use a queue** — SQS with multiple worker processes consuming in parallel

---

### Extension 5: Data validation

**What they want:** What if `total_value` doesn't match the sum of holdings?

**Your answer:**
```python
def _validate_account(data: dict) -> list[str]:
    warnings = []
    holdings_sum = sum(h.get("market_value", 0) for h in data.get("holdings", []))
    cash = data.get("cash_balance", 0)
    expected = holdings_sum + cash
    actual = data.get("total_value", 0)
    if abs(expected - actual) > 0.01:  # float tolerance
        warnings.append(
            f"Account {data['account_id']}: total_value {actual} != "
            f"holdings {holdings_sum} + cash {cash} = {expected}"
        )
    return warnings
```
> "I'd log these as warnings, not errors — we still ingest the data but flag the discrepancy for the ops team to investigate with the partner."

---

## PART 3: SYSTEM DESIGN QUESTIONS

**Q: How would you scale this to 100 partners sending data simultaneously?**
> "Decouple ingestion from HTTP using a message queue. The webhook handler writes the URL to SQS (fast, ~1ms). Worker processes — autoscaled ECS tasks or Lambda — consume from the queue. Each worker handles one ZIP. No shared state means horizontal scaling is trivial. SQS provides at-least-once delivery with automatic retries."

**Q: How would you handle a partner sending data every 5 minutes?**
> "Idempotency is already handled — re-ingesting the same data is safe. The main concern is DB write throughput. At 1,000 clients × 2 accounts × 5 holdings = 10,000 rows per batch, every 5 minutes is ~33 rows/second — totally fine for Postgres. If it grew 100x I'd look at batch inserts (`INSERT ... VALUES (),(),()`), connection pooling (PgBouncer), and read replicas for queries."

**Q: How would you monitor this in production?**
> "Three layers: (1) Metrics — track ingest job duration, success/failure rate, rows upserted per minute via CloudWatch or Datadog. (2) Alerting — page on-call if failure rate > 5% or if no successful ingests in 30 minutes. (3) Audit log — the IngestJob table gives a queryable history for ops debugging."

**Q: How would you handle schema changes from the partner?**
> "Two cases: additive changes (new fields) — I use `.get()` everywhere so new fields are silently ignored unless I explicitly map them. Breaking changes (renamed/removed fields) — I'd add a schema validation step using Pydantic models to detect missing required fields early and fail fast with a clear error, rather than ingesting partial data silently."

---

## PART 4: QUICK-FIRE ANSWERS

| Question | Answer |
|---|---|
| Why `db.flush()` before deleting accounts? | Flush writes pending inserts to satisfy FK constraints before the delete |
| Why `cascade="all, delete-orphan"`? | Deleting a Client automatically deletes its Accounts (and their Holdings) |
| Why not use `autocommit=True`? | Explicit transactions let me roll back if something fails mid-upsert |
| How do you prevent SQL injection? | SQLAlchemy ORM — never raw string interpolation in queries |
| What's `pool_pre_ping=True`? | Tests DB connection before using it — prevents errors after idle periods |
| Why `follow_redirects=True` in httpx? | ZIP URLs might redirect (CDN, S3 presigned URL chain) |

---

## PART 5: THINGS TO SHOW OFF DURING THE DEMO

1. **Hit /docs** — show the auto-generated Swagger UI
2. **Run test_local.py** — shows end-to-end working + idempotency
3. **Show the logs** — structured logging makes the pipeline visible
4. **Open the SQLite file** with a DB browser or `sqlite3` CLI to show the data
5. **Explain a tradeoff you made** — e.g., "I chose full replace for holdings over diffing because simplicity > micro-optimization at this scale"
6. **Mention what you'd add next** — auth, IngestJob audit table, retry logic
