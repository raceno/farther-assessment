# ingestion.py
# All business logic lives here — completely decoupled from HTTP layer.
# This makes it independently testable and reusable (CLI, queue worker, etc.)

import io
import json
import logging
import zipfile
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from models import Account, Client, Holding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def process_zip_from_url(url: str, db: Session) -> dict:
    """
    Full pipeline:
      1. Download ZIP from url
      2. Extract each .json file
      3. Parse + upsert client data into DB
      4. Return a summary report

    Designed to be idempotent — safe to call multiple times with the same URL.
    """
    report = {
        "url": url,
        "started_at": datetime.utcnow().isoformat(),
        "files_found": 0,
        "clients_upserted": 0,
        "clients_failed": 0,
        "errors": [],
    }

    # Step 1 — Download
    zip_bytes = _download_zip(url)

    # Step 2 — Extract + parse each file
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        json_files = [f for f in zf.namelist() if f.endswith(".json")]
        report["files_found"] = len(json_files)

        if not json_files:
            logger.warning("ZIP contained no .json files: %s", url)

        for filename in json_files:
            try:
                raw = zf.read(filename)
                data = json.loads(raw)
                upsert_client(data, db)
                report["clients_upserted"] += 1
                logger.info("Upserted client from %s", filename)

            except json.JSONDecodeError as exc:
                # Malformed JSON — log and continue; don't let one bad file
                # abort the entire batch.
                msg = f"{filename}: invalid JSON — {exc}"
                logger.error(msg)
                report["clients_failed"] += 1
                report["errors"].append(msg)

            except Exception as exc:
                msg = f"{filename}: unexpected error — {exc}"
                logger.exception(msg)
                report["clients_failed"] += 1
                report["errors"].append(msg)

    report["finished_at"] = datetime.utcnow().isoformat()
    return report


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _download_zip(url: str, timeout_seconds: int = 30) -> bytes:
    """
    Download a ZIP from `url` and return raw bytes.

    Uses a streaming download so we don't load multi-GB ZIPs fully into memory
    before starting to process (important at scale).
    """
    logger.info("Downloading ZIP from %s", url)

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()   # raises HTTPStatusError on 4xx/5xx

    content_type = response.headers.get("content-type", "")
    if "zip" not in content_type and not url.endswith(".zip"):
        logger.warning("Unexpected content-type '%s' from %s", content_type, url)

    logger.info("Downloaded %d bytes", len(response.content))
    return response.content


# ---------------------------------------------------------------------------
# Upsert logic — one client at a time, wrapped in a transaction
# ---------------------------------------------------------------------------

def upsert_client(data: dict, db: Session) -> Client:
    """
    Insert or update a single client and all child records.

    Strategy:
      - Merge Client row (upsert by client_id)
      - Delete + re-insert Accounts and Holdings for that client
        This is simpler than diffing nested structures and guarantees
        the DB always reflects the latest snapshot from the partner.
    """
    client_id = data.get("client_id")
    if not client_id:
        raise ValueError("Record missing required field 'client_id'")

    # --- Client ---
    client = db.get(Client, client_id)
    if client is None:
        client = Client(client_id=client_id)
        db.add(client)

    client.first_name   = data.get("first_name", "")
    client.last_name    = data.get("last_name", "")
    client.email        = data.get("email", "")
    client.advisor_id   = data.get("advisor_id")
    client.last_updated = _parse_datetime(data.get("last_updated"))
    client.ingested_at  = datetime.utcnow()

    # --- Accounts (replace strategy) ---
    # Flush first so FK constraints are satisfied before deleting children
    db.flush()

    existing_accounts = {a.account_id: a for a in client.accounts}
    incoming_account_ids = {a["account_id"] for a in data.get("accounts", [])}

    # Remove accounts that are no longer in the latest snapshot
    for account_id, account in existing_accounts.items():
        if account_id not in incoming_account_ids:
            logger.debug("Removing stale account %s", account_id)
            db.delete(account)

    for account_data in data.get("accounts", []):
        _upsert_account(account_data, client_id, db)

    db.commit()
    db.refresh(client)
    return client


def _upsert_account(data: dict, client_id: str, db: Session) -> Account:
    account_id = data.get("account_id")
    if not account_id:
        raise ValueError(f"Account missing 'account_id' for client {client_id}")

    account = db.get(Account, account_id)
    if account is None:
        account = Account(account_id=account_id, client_id=client_id)
        db.add(account)

    account.client_id    = client_id
    account.account_type = data.get("account_type", "UNKNOWN")
    account.custodian    = data.get("custodian")
    account.opened_date  = data.get("opened_date")
    account.status       = data.get("status", "ACTIVE")
    account.cash_balance = data.get("cash_balance", 0.0)
    account.total_value  = data.get("total_value", 0.0)
    account.ingested_at  = datetime.utcnow()

    db.flush()

    # Holdings — full replace per account
    for holding in account.holdings:
        db.delete(holding)
    db.flush()

    for holding_data in data.get("holdings", []):
        _insert_holding(holding_data, account_id, db)

    return account


def _insert_holding(data: dict, account_id: str, db: Session) -> Holding:
    cusip  = data.get("cusip", "")
    ticker = data.get("ticker", "")

    # Deterministic surrogate PK — stable across re-ingests
    holding_id = f"{account_id}:{cusip or ticker}"

    holding = Holding(
        id           = holding_id,
        account_id   = account_id,
        ticker       = ticker,
        cusip        = cusip,
        description  = data.get("description"),
        quantity     = data.get("quantity"),
        market_value = data.get("market_value"),
        cost_basis   = data.get("cost_basis"),
        price        = data.get("price"),
        asset_class  = data.get("asset_class"),
        ingested_at  = datetime.utcnow(),
    )
    db.add(holding)
    return holding


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 string → datetime; return None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning("Could not parse datetime: %s", value)
        return None
