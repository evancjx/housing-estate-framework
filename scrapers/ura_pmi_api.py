#!/usr/bin/env python3
"""
URA Data Service API Client  (fallback to Playwright scraper)
=============================================================
Calls the URA uraDataService API to retrieve private residential
transaction data.

API docs: https://eservice.ura.gov.sg/maps/api/
Access key: set URA_ACCESS_KEY environment variable (never hardcode)

AUTHENTICATION FLOW:
    1. GET /uraDataService/invokeUraDS?service=generateToken&user-agent=...&Token=<access_key>
       → returns {"Result": "<token>", "Status": "Success"}
    2. GET /uraDataService/invokeUraDS?service=PMI_Resi_Transaction&batch=<n>
       Headers: AccessKey: <access_key>, Token: <token>
       → returns JSON with transactions (past 5 years, batches of ~1000)

IMPORTANT — L7 WAF:
    The uraDataService endpoint is behind a Layer-7 WAF that blocks raw
    HTTP clients (requests, curl). Chromium-based browsers pass the challenge
    automatically. This client uses the requests library with a browser-like
    User-Agent; if blocked, the caller falls back to ura_pmi_playwright.py.

USAGE:
    export URA_ACCESS_KEY="your-access-key-here"
    python scrapers/ura_pmi_api.py --out_dir data/ura_raw/

INSTALL:
    pip install requests --break-system-packages
"""

import os
import sys
import json
import time
import argparse
import csv
from io import StringIO
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests --break-system-packages")

API_BASE = "https://www.ura.gov.sg/uraDataService/invokeUraDS"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://eservice.ura.gov.sg/",
}


def get_access_key() -> str:
    key = os.environ.get("URA_ACCESS_KEY", "").strip()
    if not key:
        sys.exit(
            "ERROR: URA_ACCESS_KEY environment variable not set.\n"
            "Set it with: export URA_ACCESS_KEY='your-key-here'"
        )
    return key


def generate_token(access_key: str, session: requests.Session) -> str:
    """
    Generate a URA API session token.

    Note: if this call returns HTML instead of JSON, the L7 WAF is
    challenging the request. Use ura_pmi_playwright.py instead.
    """
    url = f"{API_BASE}?service=generateToken&user-agent=ura-scraper&Token={access_key}"
    r = session.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type", "")
    if "text/html" in content_type or r.text.strip().startswith("<"):
        raise RuntimeError(
            "L7 WAF challenge received (got HTML instead of JSON).\n"
            "The URA API is blocking non-browser HTTP clients.\n"
            "Use ura_pmi_playwright.py instead (it uses a real Chromium browser)."
        )

    data = r.json()
    if data.get("Status") != "Success":
        raise RuntimeError(f"Token generation failed: {data}")
    return data["Result"]


def fetch_transactions(access_key: str, token: str, batch: int, session: requests.Session) -> dict:
    """Fetch one batch of PMI_Resi_Transaction (past 5 years)."""
    url = f"{API_BASE}?service=PMI_Resi_Transaction&batch={batch}"
    hdrs = {**HEADERS, "AccessKey": access_key, "Token": token}
    r = session.get(url, headers=hdrs, timeout=30)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type", "")
    if "text/html" in content_type or r.text.strip().startswith("<"):
        raise RuntimeError("L7 WAF challenge on data fetch — switching to Playwright fallback")

    return r.json()


def transactions_to_csv(records: list, out_path: Path):
    """Write transaction records to CSV."""
    if not records:
        print("  No records to write.")
        return

    # The API returns records as dicts; extract all keys from the first record
    fieldnames = list(records[0].keys())

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"  Saved: {out_path.name} ({len(records)} records, {out_path.stat().st_size // 1024} KB)")


def run(args):
    access_key = get_access_key()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    print("Generating URA API token...")
    try:
        token = generate_token(access_key, session)
        print(f"  Token: {token[:8]}...")
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        print("\nFalling back to Playwright scraper is recommended.", file=sys.stderr)
        sys.exit(1)

    # The API returns all residential transactions from the past 5 years
    # in batches. Fetch until we get an empty batch.
    all_records = []
    batch = 1
    while True:
        print(f"  Fetching batch {batch}...", end=" ", flush=True)
        try:
            data = fetch_transactions(access_key, token, batch, session)
        except RuntimeError as e:
            print(f"\n[ERROR] {e}", file=sys.stderr)
            break

        status = data.get("Status", "")
        if status != "Success":
            print(f"Status={status} — stopping")
            break

        records = data.get("Result", [])
        if not records:
            print("empty batch — done")
            break

        print(f"{len(records)} records")
        all_records.extend(records)
        batch += 1
        time.sleep(1)  # polite delay between batches

    if not all_records:
        print("[ERROR] No records retrieved.", file=sys.stderr)
        sys.exit(1)

    print(f"\nTotal records: {len(all_records)}")
    out_path = out_dir / "pmi_api_all.csv"
    transactions_to_csv(all_records, out_path)
    print(f"\nDone. Output: {out_path}")


def main():
    ap = argparse.ArgumentParser(
        description="URA Data Service API client for private residential transactions"
    )
    ap.add_argument("--out_dir", default="data/ura_raw", help="Output directory (default: data/ura_raw)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
