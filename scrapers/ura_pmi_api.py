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

INSTALL:
    pip install requests --break-system-packages
"""

import os
import sys
import json
import time
import argparse
import csv
import tempfile
from pathlib import Path

try:
    from scrapers.ura_pmi_playwright import (
        DISTRICT_LABELS,
        PROP_TYPE_MAP,
        artifact_metadata,
        atomic_write_json,
        attempt_manifest_path,
        build_attempt_manifest,
        manifest_sale_types,
        new_attempt,
        normalize_month_scope,
        normalize_prop_types,
        prop_type_slug,
        utc_now,
    )
except ModuleNotFoundError:
    from ura_pmi_playwright import (
        DISTRICT_LABELS,
        PROP_TYPE_MAP,
        artifact_metadata,
        atomic_write_json,
        attempt_manifest_path,
        build_attempt_manifest,
        manifest_sale_types,
        new_attempt,
        normalize_month_scope,
        normalize_prop_types,
        prop_type_slug,
        utc_now,
    )

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
        raise RuntimeError(
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


def transactions_to_csv(records: list, out_path: Path) -> Path:
    """Atomically write one non-empty transaction partition to CSV."""
    if not records:
        raise ValueError("cannot write an empty transaction artifact")

    fieldnames = list(records[0].keys())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{out_path.name}.", suffix=".tmp", dir=out_path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, out_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    print(
        f"  Saved: {out_path.name} "
        f"({len(records)} records, {out_path.stat().st_size // 1024} KB)"
    )
    return out_path


def api_raw_filename(
    district: str,
    prop_type: str,
    year_from: str,
    month_from: str,
    year_to: str,
    month_to: str,
) -> str:
    """Return a method-specific filename that cannot overwrite portal downloads."""
    return (
        f"pmi_api_d{str(district).zfill(2)}_{prop_type_slug(prop_type)}_"
        f"{year_from}{int(month_from):02d}-{year_to}{int(month_to):02d}.csv"
    )


def records_for_partition(
    records: list[dict],
    *,
    district: str,
    prop_type: str,
    coverage_start: str,
    coverage_end: str,
) -> list[dict]:
    district_rows = [
        record
        for record in records
        if str(record.get("postal_district", "")).zfill(2) == str(district).zfill(2)
    ]
    typed_rows = filter_records_by_prop_types(district_rows, [prop_type])
    return [
        record
        for record in typed_rows
        if not str(record.get("sale_month", "")).strip()
        or coverage_start <= str(record["sale_month"]).strip() <= coverage_end
    ]


def _failed_partition_attempts(
    districts: list[str],
    prop_types: list[str],
    *,
    started_at: str,
    error_code: str,
    error_message: str,
) -> list[dict[str, object]]:
    return [
        new_attempt(
            district=district,
            prop_type=prop_type,
            method="api",
            status="failed",
            started_at=started_at,
            completed_at=utc_now(),
            error_code=error_code,
            error_message=error_message,
        )
        for district in districts
        for prop_type in prop_types
    ]


def _api_manifest(
    *,
    started_at: str,
    districts: list[str],
    prop_types: list[str],
    attempts: list[dict[str, object]],
    source_requests: list[dict[str, object]],
    year_from: str,
    month_from: str,
    year_to: str,
    month_to: str,
) -> dict[str, object]:
    return build_attempt_manifest(
        method="api",
        started_at=started_at,
        completed_at=utc_now(),
        districts=districts,
        prop_types=prop_types,
        year_from=year_from,
        month_from=month_from,
        year_to=year_to,
        month_to=month_to,
        sale_types=manifest_sale_types([]),
        attempts=attempts,
        source_requests=source_requests,
    )


def run(args, *, session=None, sleep=time.sleep) -> dict[str, object]:
    """Fetch all four API batches, then publish only reconciled partitions."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = attempt_manifest_path(
        out_dir,
        getattr(args, "attempt_manifest", None),
        method="api",
    )
    started_at = utc_now()
    year_from, month_from, year_to, month_to = normalize_month_scope(
        getattr(args, "year_from", "2021"),
        getattr(args, "month_from", "1"),
        getattr(args, "year_to", "2026"),
        getattr(args, "month_to", "12"),
    )
    coverage_start = f"{int(year_from):04d}-{int(month_from):02d}"
    coverage_end = f"{int(year_to):04d}-{int(month_to):02d}"
    prop_types = (
        normalize_prop_types(args.prop_types)
        if args.prop_types
        else list(sorted(API_PROP_TYPE_MATCHES))
    )
    districts = (
        [str(value).zfill(2) for value in args.districts]
        if args.districts
        else list(sorted(DISTRICT_LABELS))
    )
    invalid = [district for district in districts if district not in DISTRICT_LABELS]
    if invalid:
        attempts = _failed_partition_attempts(
            districts,
            prop_types,
            started_at=started_at,
            error_code="invalid_district",
            error_message=f"Unknown district(s): {invalid}",
        )
        manifest = _api_manifest(
            started_at=started_at,
            districts=districts,
            prop_types=prop_types,
            attempts=attempts,
            source_requests=[],
            year_from=year_from,
            month_from=month_from,
            year_to=year_to,
            month_to=month_to,
        )
        atomic_write_json(manifest_path, manifest)
        return manifest

    source_requests: list[dict[str, object]] = []
    session = session or requests.Session()
    print("Generating URA API token...")
    try:
        access_key = get_access_key()
        token = generate_token(access_key, session)
        print("  Token acquired.")
    except Exception as exc:
        attempts = _failed_partition_attempts(
            districts,
            prop_types,
            started_at=started_at,
            error_code="token_generation_failed",
            error_message=str(exc),
        )
        manifest = _api_manifest(
            started_at=started_at,
            districts=districts,
            prop_types=prop_types,
            attempts=attempts,
            source_requests=source_requests,
            year_from=year_from,
            month_from=month_from,
            year_to=year_to,
            month_to=month_to,
        )
        atomic_write_json(manifest_path, manifest)
        print(f"[ERROR] {exc}", file=sys.stderr)
        return manifest

    all_records: list[dict] = []
    failed_batch: int | None = None
    for batch in API_BATCHES:
        request_started_at = utc_now()
        print(f"  Fetching batch {batch}...", end=" ", flush=True)
        try:
            data = fetch_transactions(access_key, token, batch, session)
            status = data.get("Status", "")
            if status != "Success":
                raise RuntimeError(f"URA API batch {batch} returned Status={status!r}")
            records = flatten_project_transactions(data.get("Result", []))
            all_records.extend(records)
            known_months = sorted(
                str(record.get("sale_month", "")).strip()
                for record in records
                if str(record.get("sale_month", "")).strip()
            )
            source_requests.append(
                {
                    "request_id": f"api-batch-{batch}",
                    "batch": batch,
                    "status": "succeeded",
                    "started_at": request_started_at,
                    "completed_at": utc_now(),
                    "row_count": len(records),
                    "coverage_start": known_months[0] if known_months else None,
                    "coverage_end": known_months[-1] if known_months else None,
                    "error_code": None,
                    "error_message": None,
                }
            )
            print(f"{len(records)} records")
            if batch != API_BATCHES[-1]:
                sleep(1)
        except Exception as exc:
            failed_batch = batch
            source_requests.append(
                {
                    "request_id": f"api-batch-{batch}",
                    "batch": batch,
                    "status": "failed",
                    "started_at": request_started_at,
                    "completed_at": utc_now(),
                    "row_count": None,
                    "coverage_start": None,
                    "coverage_end": None,
                    "error_code": "api_batch_failed",
                    "error_message": str(exc),
                }
            )
            print(f"FAILED: {exc}", file=sys.stderr)
            break

    if failed_batch is not None:
        for batch in API_BATCHES:
            if batch <= failed_batch:
                continue
            source_requests.append(
                {
                    "request_id": f"api-batch-{batch}",
                    "batch": batch,
                    "status": "failed",
                    "started_at": None,
                    "completed_at": None,
                    "row_count": None,
                    "coverage_start": None,
                    "coverage_end": None,
                    "error_code": "not_attempted_after_batch_failure",
                    "error_message": f"Not attempted after API batch {failed_batch} failed",
                }
            )
        attempts = _failed_partition_attempts(
            districts,
            prop_types,
            started_at=started_at,
            error_code="incomplete_api_batches",
            error_message=f"Required API batch {failed_batch} failed",
        )
        manifest = _api_manifest(
            started_at=started_at,
            districts=districts,
            prop_types=prop_types,
            attempts=attempts,
            source_requests=source_requests,
            year_from=year_from,
            month_from=month_from,
            year_to=year_to,
            month_to=month_to,
        )
        atomic_write_json(manifest_path, manifest)
        return manifest

    known_months = sorted(
        str(record.get("sale_month", "")).strip()
        for record in all_records
        if str(record.get("sale_month", "")).strip()
    )
    observed_start = known_months[0] if known_months else None
    observed_end = known_months[-1] if known_months else None
    if (
        observed_start is None
        or observed_end is None
        or coverage_start < observed_start
        or coverage_end > observed_end
    ):
        message = (
            f"Requested API coverage {coverage_start}..{coverage_end} is not "
            f"proven by observed source coverage {observed_start}..{observed_end}"
        )
        attempts = _failed_partition_attempts(
            districts,
            prop_types,
            started_at=started_at,
            error_code="unsupported_api_date_scope",
            error_message=message,
        )
        manifest = _api_manifest(
            started_at=started_at,
            districts=districts,
            prop_types=prop_types,
            attempts=attempts,
            source_requests=source_requests,
            year_from=year_from,
            month_from=month_from,
            year_to=year_to,
            month_to=month_to,
        )
        atomic_write_json(manifest_path, manifest)
        print(f"[ERROR] {message}", file=sys.stderr)
        return manifest

    attempts: list[dict[str, object]] = []
    for district in districts:
        for prop_type in prop_types:
            attempt_started_at = utc_now()
            partition_records = records_for_partition(
                all_records,
                district=district,
                prop_type=prop_type,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
            )
            if not partition_records:
                attempts.append(
                    new_attempt(
                        district=district,
                        prop_type=prop_type,
                        method="api",
                        status="confirmed_empty",
                        started_at=attempt_started_at,
                        completed_at=utc_now(),
                        observations={"row_count": 0},
                    )
                )
                continue

            out_path = out_dir / api_raw_filename(
                district,
                prop_type,
                year_from,
                month_from,
                year_to,
                month_to,
            )
            try:
                transactions_to_csv(partition_records, out_path)
                artifact = artifact_metadata(
                    out_path,
                    relative_to=manifest_path.parent,
                )
                attempts.append(
                    new_attempt(
                        district=district,
                        prop_type=prop_type,
                        method="api",
                        status="succeeded",
                        started_at=attempt_started_at,
                        completed_at=utc_now(),
                        artifact=artifact,
                        observations={"row_count": len(partition_records)},
                    )
                )
            except Exception as exc:
                attempts.append(
                    new_attempt(
                        district=district,
                        prop_type=prop_type,
                        method="api",
                        status="failed",
                        started_at=attempt_started_at,
                        completed_at=utc_now(),
                        error_code="artifact_write_failed",
                        error_message=str(exc),
                    )
                )

    manifest = _api_manifest(
        started_at=started_at,
        districts=districts,
        prop_types=prop_types,
        attempts=attempts,
        source_requests=source_requests,
        year_from=year_from,
        month_from=month_from,
        year_to=year_to,
        month_to=month_to,
    )
    atomic_write_json(manifest_path, manifest)
    print(f"\nAttempt manifest: {manifest_path}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="URA Data Service API client for private residential transactions"
    )
    ap.add_argument("--out_dir", default="data/raw/ura", help="Output directory (default: data/raw/ura)")
    ap.add_argument(
        "--attempt-manifest",
        help="Structured attempt JSON (default: <out_dir>/ura_pmi_api_attempts.json)",
    )
    ap.add_argument("--year_from", default="2021", help="Start year (default: 2021)")
    ap.add_argument("--month_from", default="1", help="Start month 1-12 (default: 1)")
    ap.add_argument("--year_to", default="2026", help="End year (default: 2026)")
    ap.add_argument("--month_to", default="12", help="End month 1-12 (default: 12)")
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
    args = ap.parse_args(argv)
    if args.prop_types:
        try:
            args.prop_types = normalize_prop_types(args.prop_types)
        except ValueError as e:
            ap.error(str(e))
    manifest = run(args)
    return 0 if manifest["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
