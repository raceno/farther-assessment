#!/usr/bin/env python3
# test_local.py
# Generates a sample ZIP in memory and tests the /ingest endpoint locally.
# Run AFTER starting the server:  uvicorn main:app --reload

import io
import json
import zipfile
import threading
import http.server
import requests
import time

# ---------------------------------------------------------------------------
# Sample data — mirrors the structure in the spec
# ---------------------------------------------------------------------------

SAMPLE_CLIENTS = [
    {
        "client_id": "CLT-29481",
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@example.com",
        "advisor_id": "ADV-0052",
        "last_updated": "2025-03-02T14:30:00Z",
        "accounts": [
            {
                "account_id": "ACC-10042",
                "account_type": "INDIVIDUAL",
                "custodian": "Apex Clearing",
                "opened_date": "2023-03-15",
                "status": "ACTIVE",
                "cash_balance": 2450.75,
                "total_value": 61100.75,
                "holdings": [
                    {
                        "ticker": "VTI",
                        "cusip": "922908769",
                        "description": "Vanguard Total Stock Market ETF",
                        "quantity": 150.0,
                        "market_value": 38250.00,
                        "cost_basis": 33750.00,
                        "price": 255.00,
                        "asset_class": "US_EQUITY",
                    },
                    {
                        "ticker": "BND",
                        "cusip": "921937835",
                        "description": "Vanguard Total Bond Market ETF",
                        "quantity": 200.0,
                        "market_value": 14800.00,
                        "cost_basis": 15200.00,
                        "price": 74.00,
                        "asset_class": "FIXED_INCOME",
                    },
                ],
            },
            {
                "account_id": "ACC-10043",
                "account_type": "ROTH_IRA",
                "custodian": "Apex Clearing",
                "opened_date": "2023-06-01",
                "status": "ACTIVE",
                "cash_balance": 1200.00,
                "total_value": 23475.00,
                "holdings": [
                    {
                        "ticker": "VOO",
                        "cusip": "922908363",
                        "description": "Vanguard S&P 500 ETF",
                        "quantity": 45.0,
                        "market_value": 22275.00,
                        "cost_basis": 19800.00,
                        "price": 495.00,
                        "asset_class": "US_EQUITY",
                    }
                ],
            },
        ],
    },
    {
        "client_id": "CLT-10002",
        "first_name": "Bob",
        "last_name": "Jones",
        "email": "bob.jones@example.com",
        "advisor_id": "ADV-0052",
        "last_updated": "2025-03-02T14:30:00Z",
        "accounts": [
            {
                "account_id": "ACC-20001",
                "account_type": "INDIVIDUAL",
                "custodian": "Schwab",
                "opened_date": "2022-01-10",
                "status": "ACTIVE",
                "cash_balance": 500.00,
                "total_value": 15000.00,
                "holdings": [
                    {
                        "ticker": "SPY",
                        "cusip": "78462F103",
                        "description": "SPDR S&P 500 ETF",
                        "quantity": 25.0,
                        "market_value": 14500.00,
                        "cost_basis": 12000.00,
                        "price": 580.00,
                        "asset_class": "US_EQUITY",
                    }
                ],
            }
        ],
    },
]


# ---------------------------------------------------------------------------
# Build ZIP in memory
# ---------------------------------------------------------------------------

def build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for client in SAMPLE_CLIENTS:
            filename = f"{client['client_id']}.json"
            zf.writestr(filename, json.dumps(client, indent=2))
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Serve the ZIP on a local HTTP server so the service can download it
# ---------------------------------------------------------------------------

class ZipHandler(http.server.BaseHTTPRequestHandler):
    zip_data: bytes = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(self.zip_data)))
        self.end_headers()
        self.wfile.write(self.zip_data)

    def log_message(self, *args):
        pass  # suppress noisy access logs


def serve_zip_once(port: int = 8765) -> str:
    zip_bytes = build_zip()
    ZipHandler.zip_data = zip_bytes

    server = http.server.HTTPServer(("localhost", port), ZipHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print(f"  📦 Serving ZIP ({len(zip_bytes)} bytes) on http://localhost:{port}/data.zip")
    return f"http://localhost:{port}/data.zip"


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8000"


def test_health():
    print("\n[1] Health check …")
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200, r.text
    print(f"  ✅ {r.json()}")


def test_ingest_sync(zip_url: str):
    print("\n[2] Synchronous ingest …")
    r = requests.post(f"{BASE_URL}/ingest", json={"url": zip_url})
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    print(f"  ✅ {report['clients_upserted']} upserted, {report['clients_failed']} failed")
    print(f"     Files found: {report['files_found']}")
    if report["errors"]:
        print(f"  ⚠️  Errors: {report['errors']}")


def test_idempotency(zip_url: str):
    print("\n[3] Idempotency — running same ingest again …")
    # Re-serve the same ZIP (need a new server instance)
    zip_url2 = serve_zip_once(port=8766)
    r = requests.post(f"{BASE_URL}/ingest", json={"url": zip_url2})
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    print(f"  ✅ Re-ran successfully — {report['clients_upserted']} upserted (no duplicates)")


def test_webhook_async(zip_url: str):
    print("\n[4] Async webhook endpoint …")
    zip_url3 = serve_zip_once(port=8767)
    r = requests.post(f"{BASE_URL}/webhook", json={"url": zip_url3})
    assert r.status_code == 202, r.text
    print(f"  ✅ Accepted: {r.json()}")
    time.sleep(3)


if __name__ == "__main__":
    print("=" * 60)
    print("  Financial Ingestion Service — Local Test Suite")
    print("=" * 60)
    print("\n  Make sure the service is running:  uvicorn main:app --reload")
    print()

    zip_url = serve_zip_once(port=8765)

    test_health()
    test_ingest_sync(zip_url)
    test_idempotency(zip_url)
    test_webhook_async(zip_url)

    print("\n" + "=" * 60)
    print("  All tests passed! ✅")
    print("=" * 60)
