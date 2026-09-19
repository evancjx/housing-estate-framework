#!/usr/bin/env python3
"""
URA Raw CSV → ura_private.csv Ingestor
========================================
Converts raw URA REALIS / PMI portal CSV files into the schema expected
by value_model.py's --private flag.

INPUT:  Raw CSVs from the URA PMI portal or REALIS caveats.
        Column names vary slightly between the portal download and
        REALIS export. This script normalises both.

OUTPUT: data/inputs/ura_private.csv with columns:
    planning_area, transacted_price, area_sqm, property_type,
    tenure, project_age_years, sale_month, plus optional raw context
    columns such as type_of_area, market_segment, source, source_quality,
    and exact EdgeProp unit provenance when present

DISTRICT → PLANNING AREA mapping is used when the raw file doesn't have
a planning_area column (portal downloads only have Postal District).

NETWORKED USAGE:
    Downloaders first write run-scoped raw artifacts plus an attempt manifest.
    This ingestor reconciles that evidence into a staged CSV/receipt/acquisition
    manifest bundle. Canonical publication is a separate, explicit review step::

        python scrapers/ingest_ura_raw.py \\
            --attempt-manifest data/runs/ura-acquisitions/RUN/attempts.json \\
            --out data/runs/ura-acquisitions/RUN/ura_private.csv

        # After reviewing the staged CSV and both sidecars:
        python scrapers/ingest_ura_raw.py \\
            --promote-run data/runs/ura-acquisitions/RUN/ura_private.csv \\
            --out data/inputs/ura_private.csv

    Direct network writes to data/inputs/ura_private.csv are rejected. Legacy
    --raw_dir/--files ingestion remains available only for noncanonical outputs
    and marks acquisition validation as not run.
"""

import argparse
from collections import Counter
import json
import os
import shutil
import sys
import re
from pathlib import Path
import tempfile
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    sys.exit("pip install pandas --break-system-packages")

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sg_estate.contracts import ContractError
from sg_estate.scrape_generation import (
    finalize_generation,
    load_generation,
    pending_partition_ids,
)
from sg_estate.source_receipts import (
    build_source_receipt,
    receipt_path_for,
    sha256_file,
    write_source_receipt,
)
from sg_estate.ura_acquisition import (
    acquisition_path_for,
    promote_acquisition_bundle,
    read_acquisition_manifest,
    write_acquisition_manifest,
)
from scrapers.run_download import (
    GENERATION_SOURCE,
    attempt_manifest_from_generation,
    generation_scope,
)


CANONICAL_OUTPUT = Path(_ROOT) / "data" / "inputs" / "ura_private.csv"
CANONICAL_DISTRICTS = tuple(f"{district:02d}" for district in range(1, 29))
CANONICAL_PROPERTY_TYPES = ("1", "2", "3", "4")
URA_PORTAL_URL = (
    "https://eservice.ura.gov.sg/property-market-information/"
    "pmiResidentialTransactionSearch"
)


# ------------------------------------------------------------------
# District → planning area mapping
# The URA PMI portal doesn't include planning_area — we derive it
# from the postal district in the filename OR from the file content.
# ------------------------------------------------------------------
DISTRICT_TO_PLANNING_AREA = {
    "01": "CENTRAL AREA",        # X — excluded from scoring
    "02": "CENTRAL AREA",
    "03": "QUEENSTOWN",
    "04": "BUKIT MERAH",
    "05": "CLEMENTI",
    "06": "CENTRAL AREA",
    "07": "KALLANG",
    "08": "BOON KENG",
    "09": "RIVER VALLEY",        # part of CENTRAL AREA
    "10": "BUKIT TIMAH",         # Ardmore/Holland Rd/Tanglin (D10 = luxury belt)
    "11": "NOVENA",
    "12": "TOA PAYOH",
    "13": "MACPHERSON",
    "14": "GEYLANG",
    "15": "MARINE PARADE",       # Katong/Joo Chiat/Amber
    "16": "BEDOK",               # Bedok/Upper East Coast
    "17": "CHANGI",
    "18": "TAMPINES",            # Tampines + Pasir Ris
    "19": "SERANGOON",           # Serangoon Garden + Hougang + Punggol
    "20": "BISHAN",              # Bishan + Ang Mo Kio
    "21": "BUKIT TIMAH",         # Upper Bukit Timah (D21 condo projects)
    "22": "JURONG EAST",         # Jurong East + Jurong West
    "23": "CHOA CHU KANG",       # Hillview/Dairy Farm/Bukit Panjang/CCK
    "24": "TENGAH",
    "25": "WOODLANDS",
    "26": "ANG MO KIO",          # Upper Thomson/Springleaf = Lentor area (AMK town)
    "27": "SEMBAWANG",           # Yishun + Sembawang + Canberra (Sembawang town)
    "28": "SELETAR",
}

# Columns from URA REALIS / CAVEATS format
REALIS_COLS = {
    "project name":          "project_name",
    "transacted price ($)":  "transacted_price",
    "area (sqft)":           "area_sqft",
    "unit price ($ psf)":    "unit_price_psf",
    "sale date":             "sale_date",
    "street name":           "street_name",
    "type of sale":          "type_of_sale",
    "type of area":          "type_of_area",
    "area (sqm)":            "area_sqm",
    "unit price ($ psm)":    "unit_price_psm",
    "nett price ($)":        "nett_price",
    "property type":         "property_type",
    "number of units":       "n_units",
    "tenure":                "tenure",
    "postal district":       "postal_district",
    "market segment":        "market_segment",
    "floor level":           "floor_level",
}

# Columns from URA PMI portal download (different header names)
PORTAL_COLS = {
    "project":                "project_name",
    "street":                 "street_name",
    "type":                   "property_type",
    "postal district":        "postal_district",
    "market segment":         "market_segment",
    "floor":                  "floor_level",
    "unit price ($psf)":      "unit_price_psf",
    "price ($)":              "transacted_price",
    "area (sqft)":            "area_sqft",
    "date of sale":           "sale_date",
    "tenure":                 "tenure",
    "sale type":              "type_of_sale",
    "area (sqm)":             "area_sqm",
    "unit price ($psm)":      "unit_price_psm",
    "no. of units":           "n_units",
}

# Columns commonly seen in EdgeProp sales tables.
EDGEPROP_COLS = {
    "date":                   "sale_date",
    "date of sale":           "sale_date",
    "address":                "address",
    "street":                 "street_name",
    "price (s$ psf)":         "unit_price_psf",
    "unit price ($psf)":      "unit_price_psf",
    "price (s$)":             "transacted_price",
    "price ($)":              "transacted_price",
    "property type":          "property_type",
    "type":                   "property_type",
    "type of sale":           "type_of_sale",
    "sale type":              "type_of_sale",
    "area (sqft)":            "area_sqft",
    "area (sqm)":             "area_sqm",
    "type of area":           "type_of_area",
    "purchaser address":      "purchaser_address",
    "source":                 "source",
    "planning_area":          "planning_area",
    "postal district":        "postal_district",
    "project":                "project_name",
    "project name":           "project_name",
    "unit number":            "unit_number",
    "unit floor":             "unit_floor",
    "unit stack":             "unit_stack",
    "unit number status":     "unit_number_status",
    "unit number source":     "unit_number_source",
}


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw column names to internal names (case-insensitive)."""
    rename = {}
    cols_lower = {c.strip().lower(): c for c in df.columns}
    for raw, internal in {**REALIS_COLS, **PORTAL_COLS, **EDGEPROP_COLS}.items():
        if raw.lower() in cols_lower:
            rename[cols_lower[raw.lower()]] = internal
    return df.rename(columns=rename)


def parse_tenure_years(tenure_str: str, sale_year: int) -> float | None:
    """
    Convert tenure string to approx remaining lease.
    '99-year leasehold from 2010' → ~88 years remaining from 2026
    'freehold' → 999 (sentinel)
    """
    if not isinstance(tenure_str, str):
        return None
    t = tenure_str.strip().lower()
    if "freehold" in t:
        return 999.0
    m = re.search(r"(\d{3,4})-year", t)
    if m:
        total = int(m.group(1))
        m2 = re.search(r"from\s+(\d{4})", t)
        start = int(m2.group(1)) if m2 else sale_year
        return max(0.0, float(total - (sale_year - start)))
    return None


def extract_sale_month(date_str: str) -> str | None:
    """
    Normalise sale date to YYYY-MM for the value model's month control.
    Handles:
      - 'Jan-2025' or 'January-2025'  (%b-%Y / %B-%Y)
      - 'Dec-23'                        (%b-%y  — URA portal 2-digit year)
      - '2025-01'                        (%Y-%m)
      - '01/2025'                        (%m/%Y)
      - '1 Jan 2025' or 'Jan 2025'      (%d %b %Y / %b %Y)
    """
    if not isinstance(date_str, str):
        return None
    date_str = date_str.strip()
    for fmt in ("%b-%Y", "%B-%Y", "%b-%y", "%B-%y", "%Y-%m", "%m/%Y", "%d %b %Y", "%b %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    # Try pandas as last resort
    try:
        dt = pd.to_datetime(date_str, dayfirst=True)
        return dt.strftime("%Y-%m")
    except Exception:
        return None


def compute_project_age(df: pd.DataFrame) -> pd.Series:
    """
    Return evidence-backed project age in years where completion evidence exists.

    PMI transaction downloads do not normally include a completion year. In
    that case age remains nullable; this function never invents a default.
    """
    if "completion_year" not in df.columns or "sale_month" not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")
    completion_year = pd.to_numeric(df["completion_year"], errors="coerce")
    sale_year = pd.to_numeric(
        df["sale_month"].astype("string").str.slice(0, 4), errors="coerce"
    )
    age = (sale_year - completion_year).where(
        completion_year.notna() & sale_year.notna() & (sale_year >= completion_year)
    )
    return age.astype("Float64")


def classify_property_type_group(
    property_type: object,
    type_of_area: object = None,
) -> str | None:
    """Map a normalized URA property label to its requested PMI group code."""

    def _text(value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        return " ".join(str(value).strip().lower().split())

    text = _text(property_type)
    area = _text(type_of_area)
    if not text or text in {"<na>", "nan", "none"}:
        return None
    if "executive condominium" in text:
        return "4"
    if "strata" in text or area == "strata" and any(
        label in text
        for label in ("detached", "semi-detached", "semi detached", "terrace")
    ):
        return "2"
    if any(label in text for label in ("apartment", "condominium")):
        return "3"
    if any(label in text for label in ("detached", "semi-detached", "semi detached", "terrace")):
        return "1"
    return None


def ingest_file(
    path: Path,
    district: str | None = None,
    source_quality: str | None = None,
) -> pd.DataFrame:
    """Read one raw CSV and return a normalised DataFrame."""
    try:
        df = pd.read_csv(path, thousands=",", encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path, thousands=",", encoding="latin-1")

    if df.empty:
        print(f"  [WARN] {path.name}: empty file")
        return pd.DataFrame()

    df = normalise_columns(df)

    required = ["transacted_price"]
    missing_req = [c for c in required if c not in df.columns]
    if missing_req:
        print(f"  [WARN] {path.name}: missing columns {missing_req} — skipping")
        return pd.DataFrame()

    # Numeric coercion
    df["transacted_price"] = pd.to_numeric(
        df["transacted_price"].astype(str).str.replace(",", ""), errors="coerce"
    )
    if "area_sqm" in df.columns:
        df["area_sqm"] = pd.to_numeric(
            df["area_sqm"].astype(str).str.replace(",", ""), errors="coerce"
        )
    elif "area_sqft" in df.columns:
        area_sqft = pd.to_numeric(
            df["area_sqft"].astype(str).str.replace(",", ""), errors="coerce"
        )
        df["area_sqm"] = area_sqft * 0.09290304
    else:
        print(f"  [WARN] {path.name}: missing area_sqm/area_sqft — skipping")
        return pd.DataFrame()
    df = df.dropna(subset=["transacted_price", "area_sqm"])
    df = df[(df["transacted_price"] > 0) & (df["area_sqm"] > 0)]

    # planning_area: derive from postal_district or filename
    if "planning_area" not in df.columns:
        if "postal_district" in df.columns:
            df["postal_district"] = df["postal_district"].astype(str).str.zfill(2)
            df["planning_area"] = df["postal_district"].map(DISTRICT_TO_PLANNING_AREA)
        elif district:
            df["planning_area"] = DISTRICT_TO_PLANNING_AREA.get(district.zfill(2))
        else:
            print(f"  [WARN] {path.name}: no planning_area or postal_district — skipping")
            return pd.DataFrame()

    # Uppercase planning_area to match estate names
    df["planning_area"] = df["planning_area"].astype("string").str.upper().str.strip()
    df["planning_area_status"] = df["planning_area"].notna().map(
        {True: "mapped", False: "unknown"}
    )

    # property_type
    if "property_type" not in df.columns:
        df["property_type"] = pd.Series(pd.NA, index=df.index, dtype="string")

    # tenure + project_age_years
    if "tenure" not in df.columns:
        df["tenure"] = pd.Series(pd.NA, index=df.index, dtype="string")

    # sale_month
    if "sale_date" in df.columns:
        df["sale_month"] = df["sale_date"].apply(extract_sale_month)
    elif "sale_month" in df.columns:
        df["sale_month"] = df["sale_month"].apply(extract_sale_month)
    else:
        df["sale_month"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df["sale_month"] = df["sale_month"].astype("string")
    df["sale_month_status"] = df["sale_month"].notna().map(
        {True: "observed", False: "unknown"}
    )

    # project_age_years
    df["project_age_years"] = compute_project_age(df)
    df["project_age_status"] = df["project_age_years"].notna().map(
        {True: "observed", False: "unknown_no_completion_evidence"}
    )

    if "postal_district" not in df.columns and district:
        df["postal_district"] = district.zfill(2)
    if "postal_district" in df.columns:
        df["postal_district"] = (
            df["postal_district"].astype("string").str.replace(r"\.0$", "", regex=True).str.zfill(2)
        )
    df["property_type_group"] = [
        classify_property_type_group(property_type, type_of_area)
        for property_type, type_of_area in zip(
            df["property_type"],
            df.get("type_of_area", pd.Series(pd.NA, index=df.index)),
        )
    ]

    if source_quality:
        df["source_quality"] = source_quality

    # Keep only the columns value_model.py needs
    out_cols = [
        "planning_area", "transacted_price", "area_sqm",
        "property_type", "tenure", "project_age_years", "sale_month",
    ]
    optional = ["project_name", "street_name", "postal_district", "market_segment",
                "floor_level", "type_of_sale", "type_of_area", "unit_price_psf",
                "unit_price_psm", "purchaser_address", "source", "source_quality",
                "address", "unit_number", "unit_floor", "unit_stack",
                "unit_number_status", "unit_number_source", "property_type_group",
                "sale_month_status", "project_age_status", "planning_area_status"]
    for c in optional:
        if c in df.columns:
            out_cols.append(c)

    df = df[[c for c in out_cols if c in df.columns]]
    print(f"  {path.name}: {len(df)} rows → planning areas: {sorted(df['planning_area'].unique())}")
    return df


def dedupe_transactions(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop duplicate raw transactions using the broadest stable key available."""
    dedup_cols = ["planning_area", "transacted_price", "area_sqm", "sale_month", "property_type"]
    # Exact units that happen to share month/price/area are distinct
    # transactions. Include published address/unit context when available.
    for extra in ["project_name", "street_name", "address", "unit_number", "floor_level"]:
        if extra in df.columns:
            dedup_cols.append(extra)
    before = len(df)

    if "type_of_area" not in df.columns:
        df = df.drop_duplicates(subset=dedup_cols, keep="last")
        return df, before - len(df)

    type_key = df["type_of_area"]
    has_type = type_key.notna() & type_key.astype(str).str.strip().ne("")
    typed = df[has_type].drop_duplicates(subset=dedup_cols + ["type_of_area"], keep="last")
    legacy_blank = df[~has_type]

    if not typed.empty and not legacy_blank.empty:
        typed_keys = typed[dedup_cols].drop_duplicates().assign(_has_typed_area=True)
        blank_key_matches = legacy_blank[dedup_cols].merge(
            typed_keys,
            on=dedup_cols,
            how="left",
        )["_has_typed_area"].fillna(False)
        legacy_blank = legacy_blank[~blank_key_matches.to_numpy()]

    legacy_blank = legacy_blank.drop_duplicates(subset=dedup_cols, keep="last")
    df = pd.concat([legacy_blank, typed]).sort_index()
    return df, before - len(df)


def _load_attempt_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load URA attempt manifest {path}: {exc}") from exc
    required = {
        "schema_version",
        "source",
        "method",
        "status",
        "started_at",
        "completed_at",
        "requested_scope",
        "source_requests",
        "attempts",
        "summary",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ContractError("URA attempt manifest has an unexpected schema")
    if manifest["schema_version"] != 1 or manifest["source"] != "URA PMI":
        raise ContractError("URA attempt manifest version/source is unsupported")
    if manifest["method"] not in {"playwright", "api"}:
        raise ContractError("URA attempt manifest method is unsupported")
    if manifest["status"] != "succeeded":
        raise ContractError("URA attempt manifest is incomplete or failed")
    scope = manifest["requested_scope"]
    scope_fields = {
        "districts",
        "property_types",
        "sale_types",
        "year_from",
        "month_from",
        "year_to",
        "month_to",
    }
    if not isinstance(scope, dict) or set(scope) != scope_fields:
        raise ContractError("URA attempt manifest requested_scope has an unexpected schema")
    districts = scope["districts"]
    property_types = scope["property_types"]
    if (
        not isinstance(districts, list)
        or not districts
        or len(districts) != len(set(districts))
        or any(not re.fullmatch(r"(?:0[1-9]|1\d|2[0-8])", value) for value in districts)
    ):
        raise ContractError("URA attempt manifest districts are invalid")
    if (
        not isinstance(property_types, list)
        or not property_types
        or len(property_types) != len(set(property_types))
        or any(value not in {"1", "2", "3", "4"} for value in property_types)
    ):
        raise ContractError("URA attempt manifest property types are invalid")
    attempts = manifest["attempts"]
    if not isinstance(attempts, list):
        raise ContractError("URA attempt manifest attempts must be a list")
    expected = {
        (district, property_type)
        for district in districts
        for property_type in property_types
    }
    observed: set[tuple[str, str]] = set()
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ContractError("URA attempt must be an object")
        key = (attempt.get("district"), attempt.get("property_type"))
        if key in observed:
            raise ContractError(f"URA attempt manifest repeats partition {key}")
        observed.add(key)
        if attempt.get("status") not in {"succeeded", "confirmed_empty"}:
            raise ContractError(f"URA partition {key} did not complete")
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        raise ContractError(
            "URA attempt partitions do not match requested scope: "
            f"missing={missing}, unexpected={unexpected}"
        )
    return manifest


def _requested_months(scope: dict) -> list[str]:
    values = (
        scope["year_from"],
        scope["month_from"],
        scope["year_to"],
        scope["month_to"],
    )
    if any(value is None for value in values):
        raise ContractError(
            "URA acquisition has no exact month range and cannot prove completeness"
        )
    try:
        start_year, start_month, end_year, end_month = map(int, values)
        start = pd.Period(year=start_year, month=start_month, freq="M")
        end = pd.Period(year=end_year, month=end_month, freq="M")
    except (TypeError, ValueError) as exc:
        raise ContractError("URA attempt month range is invalid") from exc
    if start > end:
        raise ContractError("URA attempt month range is reversed")
    return [str(period) for period in pd.period_range(start, end, freq="M")]


def _safe_artifact_path(manifest_path: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ContractError("Successful URA attempt has no artifact path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ContractError(f"Unsafe URA artifact path: {relative}")
    resolved = (manifest_path.parent / candidate).resolve()
    try:
        resolved.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise ContractError(f"URA artifact escapes its run directory: {relative}") from exc
    if not resolved.is_file():
        raise ContractError(f"URA artifact is missing: {relative}")
    return resolved


def _read_raw_rows(path: Path) -> int:
    try:
        return len(pd.read_csv(path, encoding="utf-8"))
    except UnicodeDecodeError:
        return len(pd.read_csv(path, encoding="latin-1"))


def build_complete_candidate(
    attempt_manifest_path: str | Path,
    *,
    source_quality: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Normalize and reconcile one complete downloader generation."""

    manifest_path = Path(attempt_manifest_path)
    manifest = _load_attempt_manifest(manifest_path)
    scope = manifest["requested_scope"]
    months = _requested_months(scope)
    expected_months = set(months)
    frames: list[pd.DataFrame] = []
    raw_rows = 0
    invalid_reasons: Counter[str] = Counter()
    final_partitions = []
    source_urls = []
    retrieved_values: list[str] = []

    for index, attempt in enumerate(manifest["attempts"]):
        district = attempt["district"]
        property_type = attempt["property_type"]
        attempt_id = str(attempt.get("partition_id") or f"d{district}-p{property_type}")
        status = attempt["status"]
        artifact = attempt.get("artifact")
        attempt_method = attempt.get("method") or manifest["method"]
        converted_attempt = {
            "attempt_id": f"{attempt_id}-{attempt_method}-1",
            "method": attempt_method,
            "status": status,
            "started_at": attempt.get("started_at") or manifest["started_at"],
            "completed_at": attempt.get("completed_at") or manifest["completed_at"],
            "retrieved_at": (
                attempt.get("completed_at")
                if status in {"succeeded", "confirmed_empty"}
                else None
            ),
            "source_url": URA_PORTAL_URL,
            "artifact": None,
            "sha256": None,
            "source_reported_row_count": None,
            "artifact_row_count": None,
            "error_code": attempt.get("error_code"),
            "error_message": attempt.get("error_message"),
            # Private staging-only handle used to validate/copy raw evidence;
            # removed before the public acquisition manifest is serialized.
            "_artifact_path": None,
        }
        if status == "succeeded":
            if not isinstance(artifact, dict):
                raise ContractError(f"URA partition {(district, property_type)} has no artifact")
            artifact_path = _safe_artifact_path(
                manifest_path, artifact.get("relative_path")
            )
            digest = sha256_file(artifact_path)
            if artifact.get("sha256") != digest:
                raise ContractError(f"URA artifact hash mismatch: {artifact_path.name}")
            raw_count = _read_raw_rows(artifact_path)
            if raw_count <= 0:
                raise ContractError(
                    f"URA artifact {artifact_path.name} is empty but was not confirmed empty"
                )
            if artifact.get("byte_count") != artifact_path.stat().st_size:
                raise ContractError(f"URA artifact byte-count mismatch: {artifact_path.name}")
            if artifact.get("row_count") != raw_count:
                raise ContractError(f"URA artifact row-count mismatch: {artifact_path.name}")
            observed_count = (attempt.get("observations") or {}).get("row_count")
            if observed_count is not None and observed_count != raw_count:
                raise ContractError(
                    f"URA source-reported row count differs for {artifact_path.name}"
                )
            normalized = ingest_file(
                artifact_path,
                district,
                source_quality=source_quality,
            )
            raw_rows += raw_count
            if len(normalized) != raw_count:
                invalid_reasons["invalid_price_or_area_or_schema"] += (
                    raw_count - len(normalized)
                )
            district_mismatch = normalized["postal_district"].ne(district)
            group_mismatch = normalized["property_type_group"].ne(property_type)
            unknown_group = normalized["property_type_group"].isna()
            known_month = normalized["sale_month"].notna()
            month_mismatch = known_month & ~normalized["sale_month"].isin(expected_months)
            unknown_area = normalized["planning_area"].isna()
            checks = {
                "district_mismatch": district_mismatch,
                "property_type_mismatch": group_mismatch & ~unknown_group,
                "unknown_property_type": unknown_group,
                "out_of_range_month": month_mismatch,
                "unknown_planning_area": unknown_area,
            }
            invalid_mask = pd.Series(False, index=normalized.index)
            for reason, mask in checks.items():
                count = int(mask.sum())
                if count:
                    invalid_reasons[reason] += count
                invalid_mask |= mask
            if invalid_mask.any():
                normalized = normalized.loc[~invalid_mask].copy()
            frames.append(normalized)
            converted_attempt.update(
                {
                    "artifact": artifact["relative_path"],
                    "_artifact_path": artifact_path,
                    "sha256": digest,
                    "source_reported_row_count": observed_count,
                    "artifact_row_count": raw_count,
                }
            )
            if isinstance(converted_attempt["retrieved_at"], str):
                retrieved_values.append(converted_attempt["retrieved_at"])
        elif artifact is not None:
            raise ContractError("Confirmed-empty URA attempt must not publish an artifact")
        final_partitions.append(
            {
                "district": district,
                "property_type": property_type,
                "selected_attempt_id": converted_attempt["attempt_id"],
                "attempts": [converted_attempt],
            }
        )

    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=[
                "planning_area",
                "transacted_price",
                "area_sqm",
                "property_type",
                "tenure",
                "project_age_years",
                "sale_month",
                "postal_district",
                "property_type_group",
                "sale_month_status",
                "project_age_status",
            ]
        )
    )
    valid_rows = len(combined)
    combined, duplicate_rows = dedupe_transactions(combined)
    if invalid_reasons:
        details = ", ".join(
            f"{reason}={count}" for reason, count in sorted(invalid_reasons.items()) if count
        )
        raise ContractError(f"URA acquisition contains invalid rows: {details}")
    if duplicate_rows:
        raise ContractError(
            f"URA acquisition contains {duplicate_rows} duplicate transaction rows"
        )

    district_counts = {
        district: int(combined["postal_district"].eq(district).sum())
        for district in scope["districts"]
    }
    property_type_counts = {
        property_type: int(combined["property_type_group"].eq(property_type).sum())
        for property_type in scope["property_types"]
    }
    month_counts = {
        month: int(combined["sale_month"].eq(month).sum()) for month in months
    }
    reconciliation = {
        "status": "passed",
        "expected_partitions": len(final_partitions),
        "selected_partitions": len(final_partitions),
        "raw_rows": raw_rows,
        "valid_rows": valid_rows,
        "invalid_rows": 0,
        "duplicate_rows": duplicate_rows,
        "published_rows": len(combined),
        "missing_sale_month_rows": int(combined["sale_month"].isna().sum()),
        "missing_project_age_rows": int(combined["project_age_years"].isna().sum()),
        "district_counts": district_counts,
        "property_type_counts": property_type_counts,
        "month_counts": month_counts,
        "invalid_reasons": {},
        "failures": [],
    }
    metadata = {
        "download": manifest,
        "request": {
            "districts": scope["districts"],
            "property_types": scope["property_types"],
            "sale_types": scope["sale_types"],
            "coverage_start": months[0],
            "coverage_end": months[-1],
        },
        "partitions": final_partitions,
        "reconciliation": reconciliation,
        "retrieved_at": max(retrieved_values) if retrieved_values else None,
        "source_urls": source_urls,
    }
    return combined, metadata


def _run_legacy(args):
    out_path = Path(args.out)
    merged_existing = bool(args.merge and out_path.exists())
    frames = []

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        raw_dir = Path(args.raw_dir)
        if not raw_dir.exists():
            sys.exit(f"ERROR: --raw_dir {raw_dir} does not exist")
        paths = sorted(raw_dir.glob("pmi_d*.csv")) + sorted(raw_dir.glob("*.csv"))
        paths = list(dict.fromkeys(paths))  # dedup, preserve order

    if not paths:
        sys.exit("No CSV files found.")

    print(f"Ingesting {len(paths)} file(s)...")
    for p in paths:
        # Try to extract district from filename: pmi_d03_2021-2026.csv → "03"
        m = re.search(r"pmi_d(\d{2})", p.stem)
        district = m.group(1) if m else None
        df = ingest_file(p, district, source_quality=args.source_quality)
        if not df.empty:
            frames.append(df)

    if not frames:
        sys.exit("No data after ingestion.")

    combined = pd.concat(frames, ignore_index=True)

    if merged_existing:
        existing = pd.read_csv(out_path)
        combined = pd.concat([existing, combined], ignore_index=True)
        combined, dropped = dedupe_transactions(combined)
        print(f"Merged with existing ({len(existing)} rows) → {len(combined)} rows total (deduped {dropped} rows)")
    else:
        combined, dropped = dedupe_transactions(combined)
        print(f"Total: {len(combined)} rows (deduped {dropped} rows)")

    combined.to_csv(out_path, index=False)
    sale_months = sorted(
        str(value).strip()
        for value in combined.get("sale_month", pd.Series(dtype=str)).dropna()
        if re.fullmatch(r"\d{4}-\d{2}", str(value).strip())
    )
    input_identities = ", ".join(path.name for path in paths)
    receipt = build_source_receipt(
        out_path,
        dataset_id="ura_private.csv",
        authority="URA PMI",
        source_url=None,
        source_urls=None,
        source_identity=(
            "local normalized/deduplicated inputs; acquisition completeness "
            f"not asserted:{input_identities}"
            + (" + existing ura_private.csv" if merged_existing else "")
        ),
        retrieved_at=None,
        coverage_start=sale_months[0] if sale_months else None,
        coverage_end=sale_months[-1] if sale_months else None,
        row_count=len(combined),
        cache_state="derived",
        fallback_state="not_used",
        validation_status="not_run",
    )
    write_source_receipt(out_path, receipt)
    print(f"\nWritten: {out_path}")
    print("\nRow counts by planning area:")
    for area, count in combined["planning_area"].value_counts().items():
        print(f"  {area}: {count}")

    print("\nNext: re-run value model to pick up new areas:")
    print(f"  python models/value_model.py --scores data/outputs/provision_scores.csv \\")
    print(f"      --hdb data/inputs/hdb_resale.csv --private {out_path} --out data/outputs/value_output_private.csv")


def _stage_complete_acquisition(args) -> Path:
    out_path = Path(args.out)
    if out_path.resolve() == CANONICAL_OUTPUT.resolve():
        raise ContractError(
            "A networked URA acquisition must be staged outside data/inputs; "
            "use --promote-run only after manual review"
        )
    if getattr(args, "merge", False):
        raise ContractError(
            "--merge is not allowed for a completeness-checked acquisition; "
            "download the complete requested scope into one staged generation"
        )
    generation_path_value = getattr(args, "generation_manifest", None)
    generation_path: Path | None = None
    generation: dict[str, object] | None = None
    if generation_path_value:
        generation_path = Path(generation_path_value)
        attempt_manifest_path = Path(args.attempt_manifest)
        download_manifest = _load_attempt_manifest(attempt_manifest_path)
        request = download_manifest["requested_scope"]
        expected_scope = generation_scope(
            request["districts"],
            request["property_types"],
            year_from=request["year_from"],
            month_from=request["month_from"],
            year_to=request["year_to"],
            month_to=request["month_to"],
            sale_types=request["sale_types"],
        )
        generation = load_generation(
            generation_path,
            expected_source=GENERATION_SOURCE,
            expected_scope=expected_scope,
        )
        remaining = pending_partition_ids(
            generation,
            manifest_path=generation_path,
        )
        if remaining:
            raise ContractError(
                "URA generation still has pending partitions: "
                + ", ".join(sorted(remaining))
            )
        expected_attempt_manifest = attempt_manifest_from_generation(
            generation_path,
        )
        if expected_attempt_manifest != download_manifest:
            raise ContractError(
                "URA attempt manifest does not match the selected generation evidence"
            )
        try:
            out_path.resolve().relative_to(generation_path.resolve().parent)
        except ValueError as exc:
            raise ContractError(
                "Staged URA output must stay inside its generic generation root"
            ) from exc
    combined, metadata = build_complete_candidate(
        args.attempt_manifest,
        source_quality=getattr(args, "source_quality", None),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=f".{out_path.name}.stage.", dir=out_path.parent)
    )
    temporary_output = temporary_dir / out_path.name
    try:
        combined.to_csv(temporary_output, index=False)
        for partition in metadata["partitions"]:
            for attempt in partition["attempts"]:
                artifact_path = attempt.pop("_artifact_path", None)
                if artifact_path is None:
                    continue
                evidence_dir = temporary_dir / "raw"
                evidence_dir.mkdir(exist_ok=True)
                digest = attempt["sha256"]
                evidence_name = f"{digest}-{Path(artifact_path).name}"
                evidence_path = evidence_dir / evidence_name
                evidence_path.write_bytes(Path(artifact_path).read_bytes())
                if sha256_file(evidence_path) != digest:
                    raise ContractError(
                        f"Copied URA evidence hash mismatch: {evidence_name}"
                    )
                attempt["artifact"] = f"raw/{evidence_name}"
        acquisition_id = getattr(args, "acquisition_id", None) or (
            f"{metadata['download']['method']}-"
            + re.sub(r"[^0-9A-Za-z]+", "", metadata["download"]["started_at"])
        )
        receipt = build_source_receipt(
            temporary_output,
            dataset_id="ura_private.csv",
            authority="URA PMI",
            source_url=URA_PORTAL_URL,
            source_identity=f"ura-acquisition:{acquisition_id}",
            retrieved_at=metadata["retrieved_at"],
            coverage_start=metadata["request"]["coverage_start"],
            coverage_end=metadata["request"]["coverage_end"],
            row_count=len(combined),
            cache_state="fresh",
            fallback_state="not_used",
            validation_status="passed",
        )
        write_source_receipt(temporary_output, receipt)
        acquisition_manifest = {
            "schema_version": 1,
            "dataset_id": "ura_private.csv",
            "acquisition_id": acquisition_id,
            "status": "awaiting_review",
            "started_at": metadata["download"]["started_at"],
            "completed_at": metadata["download"]["completed_at"],
            "request": metadata["request"],
            "partitions": metadata["partitions"],
            "reconciliation": metadata["reconciliation"],
            "output": {
                "path": temporary_output.name,
                "sha256": sha256_file(temporary_output),
                "row_count": len(combined),
            },
        }
        write_acquisition_manifest(
            temporary_output,
            acquisition_manifest,
            allowed_statuses=("awaiting_review",),
            validate_selected_artifacts=True,
        )
        # Publish immutable run-scoped evidence before the staged commit marker.
        # A crash may leave an unreferenced content-addressed raw file, but can
        # never leave a manifest that refers to missing evidence.
        staged_evidence = out_path.parent / "raw"
        staged_evidence.mkdir(exist_ok=True)
        for evidence_path in (temporary_dir / "raw").iterdir():
            destination = staged_evidence / evidence_path.name
            if destination.exists():
                if sha256_file(destination) != sha256_file(evidence_path):
                    raise ContractError(
                        f"URA evidence destination already differs: {destination}"
                    )
                continue
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=staged_evidence,
            )
            temporary_destination = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(evidence_path.read_bytes())
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary_destination.replace(destination)
            except Exception:
                temporary_destination.unlink(missing_ok=True)
                raise
        promote_acquisition_bundle(
            temporary_output,
            out_path,
            allowed_statuses=("awaiting_review",),
        )
        if generation_path is not None:
            # DATA-103 promotion moves the reviewed staged CSV to its canonical
            # destination. Bind the generic generation to a durable exact copy
            # so later manual promotion cannot invalidate completed evidence.
            reconciled_output = generation_path.with_name(
                f"{generation_path.stem}.reconciled.csv"
            )
            candidate_digest = sha256_file(out_path)
            if generation is not None and generation["status"] == "complete":
                output_record = generation["output"]
                assert isinstance(output_record, dict)
                if output_record["sha256"] != candidate_digest:
                    raise ContractError(
                        "Complete generic URA generation is bound to different output bytes"
                    )
            else:
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{reconciled_output.name}.",
                    suffix=".tmp",
                    dir=reconciled_output.parent,
                )
                temporary_reconciled = Path(temporary_name)
                try:
                    with out_path.open("rb") as source, os.fdopen(
                        descriptor, "wb"
                    ) as target:
                        shutil.copyfileobj(source, target)
                        target.flush()
                        os.fsync(target.fileno())
                    os.replace(temporary_reconciled, reconciled_output)
                except Exception:
                    temporary_reconciled.unlink(missing_ok=True)
                    raise
                if sha256_file(reconciled_output) != candidate_digest:
                    raise ContractError(
                        "Durable generic URA output differs from the reconciled candidate"
                    )
            finalize_generation(generation_path, reconciled_output)
    finally:
        if temporary_dir.exists():
            for child in temporary_dir.iterdir():
                if child.is_dir():
                    for nested in child.iterdir():
                        nested.unlink(missing_ok=True)
                    child.rmdir()
                else:
                    child.unlink(missing_ok=True)
            temporary_dir.rmdir()
    print(
        f"Staged complete URA acquisition {acquisition_id}: {len(combined)} rows\n"
        f"  CSV: {out_path}\n"
        f"  Receipt: {receipt_path_for(out_path)}\n"
        f"  Manifest: {acquisition_path_for(out_path)}\n"
        "Review the staged evidence, then use --promote-run explicitly."
    )
    return out_path


def _promote_reviewed_acquisition(args) -> Path:
    staged_output = Path(args.promote_run)
    canonical_output = Path(args.out)
    manifest_path = acquisition_path_for(staged_output)
    manifest = read_acquisition_manifest(
        manifest_path,
        output_path=staged_output,
        allowed_statuses=("awaiting_review",),
    )
    request = manifest["request"]
    if canonical_output.resolve() == CANONICAL_OUTPUT.resolve() and (
        set(request["districts"]) != set(CANONICAL_DISTRICTS)
        or set(request["property_types"]) != set(CANONICAL_PROPERTY_TYPES)
    ):
        raise ContractError(
            "Canonical URA promotion requires the complete district 01-28 and "
            "property-type 1-4 scope; a partial acquisition remains staged"
        )
    manifest["status"] = "complete"
    write_acquisition_manifest(
        staged_output,
        manifest,
        allowed_statuses=("complete",),
    )
    try:
        promoted = promote_acquisition_bundle(staged_output, canonical_output)
    except Exception:
        # Keep a failed promotion reviewable/retryable when the staged manifest
        # itself is still present. A rollback may already have restored it.
        if staged_output.is_file():
            manifest["status"] = "awaiting_review"
            write_acquisition_manifest(
                staged_output,
                manifest,
                allowed_statuses=("awaiting_review",),
            )
        raise
    print(f"Promoted reviewed URA acquisition to {canonical_output}")
    return promoted


def run(args):
    """Run legacy noncanonical ingestion or strict acquisition staging."""

    if getattr(args, "generation_manifest", None) and not getattr(
        args, "attempt_manifest", None
    ):
        raise ContractError("--generation-manifest requires --attempt-manifest")
    if getattr(args, "promote_run", None):
        return _promote_reviewed_acquisition(args)
    if getattr(args, "attempt_manifest", None):
        return _stage_complete_acquisition(args)
    out_path = Path(args.out)
    if out_path.resolve() == CANONICAL_OUTPUT.resolve():
        raise ContractError(
            "Direct canonical URA writes are disabled. Supply --attempt-manifest "
            "to stage a complete generation, then --promote-run after review."
        )
    return _run_legacy(args)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest URA raw CSVs into ura_private.csv schema")
    ap.add_argument("--raw_dir", default="data/raw/ura", help="Directory of raw PMI CSVs")
    ap.add_argument("--files", nargs="*", help="Specific file(s) to ingest (overrides --raw_dir)")
    ap.add_argument("--out", default="data/inputs/ura_private.csv", help="Output file")
    ap.add_argument("--merge", action="store_true", help="Merge with existing --out file")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--attempt-manifest",
        help="Downloader attempt manifest to reconcile into a staged bundle",
    )
    mode.add_argument(
        "--promote-run",
        metavar="STAGED_CSV",
        help="Explicitly promote a manually reviewed staged acquisition bundle",
    )
    ap.add_argument(
        "--generation-manifest",
        help=(
            "Generic append-only generation sidecar to verify and finalize only "
            "after the staged DATA-103 candidate reconciles"
        ),
    )
    ap.add_argument(
        "--acquisition-id",
        help="Stable identifier for a staged acquisition (derived when omitted)",
    )
    ap.add_argument(
        "--source_quality",
        help="Optional provenance marker applied to all ingested rows, e.g. not_clean",
    )
    args = ap.parse_args(argv)
    try:
        run(args)
    except (ContractError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
