#!/usr/bin/env python3
"""
URA Data Service API Client  (fallback to Playwright scraper)
=============================================================
Calls the URA uraDataService API to retrieve private residential
transaction data.

API docs: https://eservice.ura.gov.sg/maps/api/
Access key: set URA_ACCESS_KEY environment variable (never hardcode)

AUTHENTICATION FLOW:
    1. GET /uraDataService/insertNewToken/v1
       Headers: AccessKey: <access_key>
       → returns {"Result": "<token>", "Status": "Success"}
    2. GET /uraDataService/invokeUraDS/v1?service=PMI_Resi_Transaction&batch=<n>
       Headers: AccessKey: <access_key>, Token: <token>
       → returns JSON with project records and nested transactions

IMPORTANT — L7 WAF:
    The uraDataService endpoint is behind a Layer-7 WAF that blocks raw
    HTTP clients (requests, curl). Chromium-based browsers pass the challenge
    automatically. This client uses the requests library with a browser-like
    User-Agent; if blocked, the caller falls back to ura_pmi_playwright.py.

USAGE:
    export URA_ACCESS_KEY="your-access-key-here"
    python scrapers/ura_pmi_api.py --out_dir data/raw/ura/

    # Keep only landed transaction groups if the API path is usable.
    python scrapers/ura_pmi_api.py --prop_types landed strata_landed --out_dir data/raw/ura/

    # Monthly developer sales (PMI_Resi_Developer_Sales) for a YYYY-MM range.
    # Written outside data/raw/ura/ so ingest_ura_raw.py's *.csv glob skips it.
    python scrapers/ura_pmi_api.py --developer_sales 2025-08 2026-08 --districts 27 \
        --out_dir data/raw/ura/developer_sales

INSTALL:
    pip install requests --break-system-packages
"""

import os
import sys
import json
import time
import argparse
import csv
from pathlib import Path

try:
    from scrapers.ura_pmi_playwright import PROP_TYPE_MAP, normalize_prop_types, prop_type_slug
except ModuleNotFoundError:
    from ura_pmi_playwright import PROP_TYPE_MAP, normalize_prop_types, prop_type_slug

try:
    import requests
except ImportError:
    sys.exit("pip install requests --break-system-packages")

API_ROOT = "https://eservice.ura.gov.sg/uraDataService"
TOKEN_URL = f"{API_ROOT}/insertNewToken/v1"
INVOKE_URL = f"{API_ROOT}/invokeUraDS/v1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://eservice.ura.gov.sg/",
}

API_PROP_TYPE_MATCHES = {
    "1": {
        "landed properties (non-strata)",
        "landed properties (non strata)",
        "detached house",
        "semi-detached house",
        "semi detached house",
        "terrace house",
        "detached",
        "semi-detached",
        "semi detached",
        "semidetached",
        "terrace",
    },
    "2": {
        "strata landed",
        "strata detached house",
        "strata semi-detached house",
        "strata semi detached house",
        "strata semidetached house",
        "strata terrace house",
        "strata detached",
        "strata semi-detached",
        "strata semi detached",
        "strata semidetached",
        "strata terrace",
    },
    "3": {
        "apartments & condominiums",
        "apartment",
        "condominium",
    },
    "4": {
        "executive condominiums",
        "executive condominium",
    },
}

API_BATCHES = (1, 2, 3, 4)

API_PROPERTY_TYPE_CANONICAL = {
    "detached": "Detached House",
    "detached house": "Detached House",
    "semi-detached": "Semi-Detached House",
    "semi detached": "Semi-Detached House",
    "semidetached": "Semi-Detached House",
    "semi-detached house": "Semi-Detached House",
    "semi detached house": "Semi-Detached House",
    "semidetached house": "Semi-Detached House",
    "terrace": "Terrace House",
    "terrace house": "Terrace House",
    "strata detached": "Strata Detached House",
    "strata detached house": "Strata Detached House",
    "strata semi-detached": "Strata Semi-Detached House",
    "strata semi detached": "Strata Semi-Detached House",
    "strata semidetached": "Strata Semi-Detached House",
    "strata semi-detached house": "Strata Semi-Detached House",
    "strata semi detached house": "Strata Semi-Detached House",
    "strata semidetached house": "Strata Semi-Detached House",
    "strata terrace": "Strata Terrace House",
    "strata terrace house": "Strata Terrace House",
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
    r = session.get(TOKEN_URL, headers={**HEADERS, "AccessKey": access_key}, timeout=15)
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
    url = f"{INVOKE_URL}?service=PMI_Resi_Transaction&batch={batch}"
    hdrs = {**HEADERS, "AccessKey": access_key, "Token": token}
    r = session.get(url, headers=hdrs, timeout=30)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type", "")
    if "text/html" in content_type or r.text.strip().startswith("<"):
        raise RuntimeError("L7 WAF challenge on data fetch — switching to Playwright fallback")

    return r.json()


def parse_contract_month(value: str) -> str:
    """Convert URA API contractDate mmyy to YYYY-MM."""
    text = str(value or "").strip()
    if len(text) != 4 or not text.isdigit():
        return ""
    month = int(text[:2])
    year = int(text[2:])
    if not 1 <= month <= 12:
        return ""
    year += 2000 if year < 70 else 1900
    return f"{year:04d}-{month:02d}"


def record_property_type(record: dict) -> str:
    """Return a normalized property type string from a URA API transaction record."""
    for key in ("propertyType", "property_type", "property type", "type"):
        if key in record and record[key] is not None:
            return str(record[key]).strip().lower()
    return ""


def canonical_property_type(value: str) -> str:
    """Normalize URA API property type labels to the portal CSV labels where possible."""
    text = str(value or "").strip()
    return API_PROPERTY_TYPE_CANONICAL.get(text.lower(), text)


def filter_records_by_prop_types(records: list[dict], prop_types: list[str]) -> list[dict]:
    """Filter flat URA API records by the same property groups used in the PMI portal."""
    wanted = {name for code in prop_types for name in API_PROP_TYPE_MATCHES[code]}
    return [record for record in records if record_property_type(record) in wanted]


def flatten_project_transactions(records: list[dict]) -> list[dict]:
    """Flatten URA API project records into rows compatible with ingest_ura_raw.py."""
    rows = []
    for project in records:
        project_name = project.get("project", "")
        street_name = project.get("street", "")
        market_segment = project.get("marketSegment", "")
        for txn in project.get("transaction", []) or []:
            district = str(txn.get("district", "")).strip().zfill(2)
            rows.append({
                "project_name": project_name,
                "street_name": street_name,
                "property_type": canonical_property_type(txn.get("propertyType", "")),
                "postal_district": district,
                "market_segment": market_segment,
                "floor_level": txn.get("floorRange", ""),
                "transacted_price": txn.get("price", ""),
                "area_sqm": txn.get("area", ""),
                "sale_month": parse_contract_month(txn.get("contractDate", "")),
                "tenure": txn.get("tenure", ""),
                "type_of_sale": txn.get("typeOfSale", ""),
                "type_of_area": txn.get("typeOfArea", ""),
                "n_units": txn.get("noOfUnits", ""),
            })
    return rows


def developer_sales_periods(start: str, end: str) -> list[str]:
    """Expand an inclusive YYYY-MM range into URA mmyy refPeriod values."""
    year, month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))
    periods = []
    while (year, month) <= (end_year, end_month):
        periods.append(f"{month:02d}{year % 100:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return periods


def flatten_developer_sales(records: list[dict]) -> list[dict]:
    """Flatten PMI_Resi_Developer_Sales records into one row per project-month.

    Prices are URA's median/lowest/highest $psf for units sold in the month.
    Cumulative fields are kept exactly as reported; sold_to_date can net out
    cancellations, so it is never derived from monthly sales.
    """

    def value(sales: dict, key: str):
        field = sales.get(key)
        return "" if field is None else field

    rows = []
    for project in records:
        for sales in project.get("developerSales", []) or []:
            rows.append({
                "ref_month": parse_contract_month(sales.get("refPeriod", "")),
                "project_name": project.get("project", ""),
                "street_name": project.get("street", ""),
                "postal_district": str(project.get("district", "")).strip().zfill(2),
                "market_segment": project.get("marketSegment", ""),
                "property_type": project.get("propertyType", ""),
                "developer": project.get("developer", ""),
                "units_avail": value(sales, "unitsAvail"),
                "launched_to_date": value(sales, "launchedToDate"),
                "sold_to_date": value(sales, "soldToDate"),
                "launched_in_month": value(sales, "launchedInMonth"),
                "sold_in_month": value(sales, "soldInMonth"),
                "median_psf": value(sales, "medianPrice"),
                "lowest_psf": value(sales, "lowestPrice"),
                "highest_psf": value(sales, "highestPrice"),
            })
    return rows


def fetch_developer_sales(access_key: str, token: str, ref_period: str, session: requests.Session) -> dict:
    """Fetch PMI_Resi_Developer_Sales for one mmyy reference month."""
    url = f"{INVOKE_URL}?service=PMI_Resi_Developer_Sales&refPeriod={ref_period}"
    hdrs = {**HEADERS, "AccessKey": access_key, "Token": token}
    r = session.get(url, headers=hdrs, timeout=60)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type", "")
    if "text/html" in content_type or r.text.strip().startswith("<"):
        raise RuntimeError("L7 WAF challenge on developer-sales fetch")

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

    prop_types = normalize_prop_types(args.prop_types) if args.prop_types else []

    wanted_districts = {d.zfill(2) for d in args.districts} if args.districts else set()

    # The official API exposes exactly four transaction batches.
    all_records = []
    for batch in API_BATCHES:
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

        records = flatten_project_transactions(data.get("Result", []))
        if not records:
            print("empty batch")
            continue

        print(f"{len(records)} records")
        all_records.extend(records)
        time.sleep(1)  # polite delay between batches

    if not all_records:
        print("[ERROR] No records retrieved.", file=sys.stderr)
        sys.exit(1)

    if wanted_districts:
        before = len(all_records)
        all_records = [
            record for record in all_records
            if str(record.get("postal_district", "")).zfill(2) in wanted_districts
        ]
        print(f"\nFiltered to districts {sorted(wanted_districts)}: {len(all_records)} of {before} records")
        if not all_records:
            print("[ERROR] No records matched requested district(s).", file=sys.stderr)
            sys.exit(1)

    if prop_types:
        before = len(all_records)
        all_records = filter_records_by_prop_types(all_records, prop_types)
        labels = ", ".join(PROP_TYPE_MAP[p] for p in prop_types)
        print(f"\nFiltered to {labels}: {len(all_records)} of {before} records")
        if not all_records:
            print("[ERROR] No records matched requested property type(s).", file=sys.stderr)
            sys.exit(1)

    print(f"\nTotal records: {len(all_records)}")
    if not prop_types:
        out_name = "pmi_api_all.csv"
    else:
        out_name = "pmi_api_" + "_".join(prop_type_slug(p) for p in prop_types) + ".csv"
    if wanted_districts:
        out_name = out_name.removesuffix(".csv") + "_d" + "_d".join(sorted(wanted_districts)) + ".csv"
    out_path = out_dir / out_name
    transactions_to_csv(all_records, out_path)
    print(f"\nDone. Output: {out_path}")


def run_developer_sales(args) -> Path:
    """Fetch monthly developer sales for an inclusive YYYY-MM range and write one CSV."""
    access_key = get_access_key()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    token = generate_token(access_key, session)

    start, end = args.developer_sales
    wanted_districts = {d.zfill(2) for d in args.districts} if args.districts else set()
    rows = []
    for ref_period in developer_sales_periods(start, end):
        data = fetch_developer_sales(access_key, token, ref_period, session)
        if data.get("Status") != "Success":
            raise RuntimeError(f"Developer sales {ref_period}: Status={data.get('Status')}")
        month_rows = flatten_developer_sales(data.get("Result", []))
        if wanted_districts:
            month_rows = [row for row in month_rows if row["postal_district"] in wanted_districts]
        print(f"  {ref_period}: {len(month_rows)} project rows")
        rows.extend(month_rows)
        time.sleep(1)  # polite delay between months

    if not rows:
        sys.exit("[ERROR] No developer-sales rows retrieved.")
    out_name = f"pmi_api_developer_sales_{start}_{end}"
    if wanted_districts:
        out_name += "_d" + "_d".join(sorted(wanted_districts))
    out_path = out_dir / f"{out_name}.csv"
    transactions_to_csv(rows, out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="URA Data Service API client for private residential transactions"
    )
    ap.add_argument("--out_dir", default="data/raw/ura", help="Output directory (default: data/raw/ura)")
    ap.add_argument(
        "--prop_types", nargs="+",
        help=(
            "Property type(s) to keep from API results: "
            "1/landed, 2/strata_landed, 3/apt_condo, 4/ec. Default: all residential."
        ),
    )
    ap.add_argument(
        "--districts", nargs="*", metavar="NN",
        help="Optional postal district filter, e.g. --districts 03 07 08",
    )
    ap.add_argument(
        "--developer_sales", nargs=2, metavar=("START", "END"),
        help="Fetch monthly developer sales (PMI_Resi_Developer_Sales) for an inclusive YYYY-MM range instead of transactions",
    )
    args = ap.parse_args()
    if args.developer_sales:
        run_developer_sales(args)
        return
    if args.prop_types:
        try:
            args.prop_types = normalize_prop_types(args.prop_types)
        except ValueError as e:
            ap.error(str(e))
    run(args)


if __name__ == "__main__":
    main()
