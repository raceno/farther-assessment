# main.py
# FastAPI application — thin HTTP layer only.
# All business logic lives in ingestion.py.

import logging
import os
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import SessionLocal, get_db, init_db
from ingestion import process_zip_from_url
from models import Account, Client

# ---------------------------------------------------------------------------
# Logging — structured output makes production debugging much easier
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB migrations (create tables) on startup."""
    logger.info("Starting up — initialising database …")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Financial Data Ingestion Service",
    description="Receives webhooks, downloads ZIPs, and persists client account data.",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class WebhookPayload(BaseModel):
    """Payload sent by the external partner webhook."""
    url: HttpUrl   # Pydantic validates this is a well-formed URL

    model_config = {"json_schema_extra": {"example": {"url": "https://example.com/data.zip"}}}


class WebhookResponse(BaseModel):
    status: str
    message: str


class IngestResponse(BaseModel):
    status: str
    report: dict


class HoldingResponse(BaseModel):
    """Holding row — mirrors partner JSON (no internal surrogate id)."""

    ticker: str | None = None
    cusip: str | None = None
    description: str | None = None
    quantity: float | None = None
    market_value: float | None = None
    cost_basis: float | None = None
    price: float | None = None
    asset_class: str | None = None


class AccountResponse(BaseModel):
    account_id: str
    account_type: str
    custodian: str | None = None
    opened_date: str | None = None
    status: str
    holdings: list[HoldingResponse]
    cash_balance: float | None = None
    total_value: float | None = None


class ClientPortfolioResponse(BaseModel):
    """Nested client snapshot aligned with ingested partner files."""

    client_id: str
    first_name: str
    last_name: str
    email: str
    accounts: list[AccountResponse]
    advisor_id: str | None = None
    last_updated: str | None = None


def _client_to_portfolio_response(client: Client) -> ClientPortfolioResponse:
    accounts_orm = sorted(client.accounts, key=lambda a: a.account_id)
    accounts_out: list[AccountResponse] = []
    for acc in accounts_orm:
        holdings_orm = sorted(
            acc.holdings,
            key=lambda h: ((h.ticker or ""), (h.cusip or "")),
        )
        holdings_out = [
            HoldingResponse(
                ticker=h.ticker,
                cusip=h.cusip,
                description=h.description,
                quantity=h.quantity,
                market_value=h.market_value,
                cost_basis=h.cost_basis,
                price=h.price,
                asset_class=h.asset_class,
            )
            for h in holdings_orm
        ]
        accounts_out.append(
            AccountResponse(
                account_id=acc.account_id,
                account_type=acc.account_type,
                custodian=acc.custodian,
                opened_date=acc.opened_date,
                status=acc.status,
                holdings=holdings_out,
                cash_balance=acc.cash_balance,
                total_value=acc.total_value,
            )
        )
    last_updated: str | None = None
    if client.last_updated is not None:
        last_updated = client.last_updated.isoformat()
    return ClientPortfolioResponse(
        client_id=client.client_id,
        first_name=client.first_name,
        last_name=client.last_name,
        email=client.email,
        accounts=accounts_out,
        advisor_id=client.advisor_id,
        last_updated=last_updated,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    """Simple liveness probe — useful for load balancers and k8s."""
    return {"status": "ok"}


@app.get("/clients/{client_id}", response_model=ClientPortfolioResponse)
def get_client_portfolio(client_id: str, db: Session = Depends(get_db)):
    """
    Return a single client's nested portfolio (accounts and holdings).
    Shape matches the partner JSON file for UI consumption.
    """
    stmt = (
        select(Client)
        .where(Client.client_id == client_id)
        .options(selectinload(Client.accounts).selectinload(Account.holdings))
    )
    client = db.execute(stmt).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return _client_to_portfolio_response(client)


@app.post("/webhook", response_model=WebhookResponse, status_code=202)
async def receive_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
):
    """
    Webhook entry point.

    Returns 202 Accepted immediately — processing happens in the background
    so the partner's webhook delivery doesn't time out waiting for us.

    Design note: In production you'd push the URL onto a message queue
    (SQS, RabbitMQ) and have dedicated worker processes consume it.
    Background tasks are fine for a local demo / low-volume service.
    """
    url = str(payload.url)
    logger.info("Webhook received — queuing job for %s", url)

    background_tasks.add_task(_run_ingestion, url)

    return WebhookResponse(
        status="accepted",
        message=f"Job queued for {url}",
    )


@app.post("/ingest", response_model=IngestResponse)
def ingest_sync(
    payload: WebhookPayload,
    db: Session = Depends(get_db),
):
    """
    Synchronous ingest endpoint — useful for testing and manual triggers.
    Blocks until ingestion completes and returns a detailed report.
    """
    url = str(payload.url)
    logger.info("Synchronous ingest triggered for %s", url)

    try:
        report = process_zip_from_url(url, db)
        return IngestResponse(status="completed", report=report)
    except Exception as exc:
        logger.exception("Ingest failed for %s", url)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------

def _run_ingestion(url: str):
    """
    Wrapper so exceptions in the background task are logged rather than
    silently swallowed by FastAPI's task runner.

    Opens a dedicated DB session — never reuse the request-scoped session,
    which is closed before this task runs.
    """
    db = SessionLocal()
    try:
        report = process_zip_from_url(url, db)
        logger.info(
            "Ingestion complete — %d upserted, %d failed. URL: %s",
            report["clients_upserted"],
            report["clients_failed"],
            url,
        )
    except Exception:
        logger.exception("Background ingestion failed for %s", url)
    finally:
        db.close()
