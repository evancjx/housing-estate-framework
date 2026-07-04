#!/usr/bin/env python3
"""
URA Raw CSV → ura_private.csv Ingestor
========================================
Converts raw URA REALIS / PMI portal CSV files into the schema expected
by value_model.py's --private flag.

INPUT:  Raw CSVs from the URA PMI portal or REALIS caveats.
        Column names vary slightly between the portal download and
        REALIS export. This script normalises both.

OUTPUT: data/ura_private.csv with columns:
    planning_area, transacted_price, area_sqm, property_type,
    tenure, project_age_years, sale_month, plus optional raw context
    columns such as type_of_area and market_segment when present

DISTRICT → PLANNING AREA mapping is used when the raw file doesn't have
a planning_area column (portal downloads only have Postal District).

USAGE:
    # Ingest new files from data/ura_raw/ and merge with existing ura_private.csv
    python scrapers/ingest_ura_raw.py \\
        --raw_dir data/ura_raw/ \\
        --out data/ura_private.csv \\
        --merge   # append to existing, deduplicate

    # Rebuild from scratch (replaces existing ura_private.csv)
    python scrapers/ingest_ura_raw.py --raw_dir data/ura_raw/ --out data/ura_private.csv

    # Ingest a specific file
    python scrapers/ingest_ura_raw.py --files data/ura_raw/pmi_d15_2021-2026.csv --out data/ura_private.csv --merge
"""

import argparse
import sys
import re
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    sys.exit("pip install pandas --break-system-packages")


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


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw column names to internal names (case-insensitive)."""
    rename = {}
    cols_lower = {c.strip().lower(): c for c in df.columns}
    for raw, internal in {**REALIS_COLS, **PORTAL_COLS}.items():
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
    Approximate project age in years = sale_year - completion_year.
    Without completion data, use a floor of 0 (new) based on sale year
    and a rough estimate from tenure commencement if available.
    """
    # We don't have completion data in the portal download.
    # Return a placeholder column; the value model uses it as a control
    # variable so it needs to exist. Set 5 years as a reasonable default.
    return pd.Series([5.0] * len(df), index=df.index)


def ingest_file(path: Path, district: str | None = None) -> pd.DataFrame:
    """Read one raw CSV and return a normalised DataFrame."""
    try:
        df = pd.read_csv(path, thousands=",", encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path, thousands=",", encoding="latin-1")

    if df.empty:
        print(f"  [WARN] {path.name}: empty file")
        return pd.DataFrame()

    df = normalise_columns(df)

    required = ["transacted_price", "area_sqm"]
    missing_req = [c for c in required if c not in df.columns]
    if missing_req:
        print(f"  [WARN] {path.name}: missing columns {missing_req} — skipping")
        return pd.DataFrame()

    # Numeric coercion
    df["transacted_price"] = pd.to_numeric(
        df["transacted_price"].astype(str).str.replace(",", ""), errors="coerce"
    )
    df["area_sqm"] = pd.to_numeric(
        df["area_sqm"].astype(str).str.replace(",", ""), errors="coerce"
    )
    df = df.dropna(subset=["transacted_price", "area_sqm"])
    df = df[(df["transacted_price"] > 0) & (df["area_sqm"] > 0)]

    # planning_area: derive from postal_district or filename
    if "planning_area" not in df.columns:
        if "postal_district" in df.columns:
            df["postal_district"] = df["postal_district"].astype(str).str.zfill(2)
            df["planning_area"] = df["postal_district"].map(DISTRICT_TO_PLANNING_AREA)
        elif district:
            df["planning_area"] = DISTRICT_TO_PLANNING_AREA.get(district.zfill(2), "UNKNOWN")
        else:
            print(f"  [WARN] {path.name}: no planning_area or postal_district — skipping")
            return pd.DataFrame()
        df["planning_area"] = df["planning_area"].fillna("UNKNOWN")

    # Uppercase planning_area to match estate names
    df["planning_area"] = df["planning_area"].str.upper().str.strip()

    # property_type
    if "property_type" not in df.columns:
        df["property_type"] = "Apartment"

    # tenure + project_age_years
    if "tenure" not in df.columns:
        df["tenure"] = "99-year leasehold"

    # sale_month
    if "sale_date" in df.columns:
        df["sale_month"] = df["sale_date"].apply(extract_sale_month)
    elif "sale_month" in df.columns:
        pass  # already present
    else:
        df["sale_month"] = "2024-01"  # fallback

    # project_age_years
    df["project_age_years"] = compute_project_age(df)

    # Keep only the columns value_model.py needs
    out_cols = [
        "planning_area", "transacted_price", "area_sqm",
        "property_type", "tenure", "project_age_years", "sale_month",
    ]
    optional = ["project_name", "street_name", "postal_district", "market_segment",
                "floor_level", "type_of_sale", "type_of_area", "unit_price_psm"]
    for c in optional:
        if c in df.columns:
            out_cols.append(c)

    df = df[[c for c in out_cols if c in df.columns]]
    print(f"  {path.name}: {len(df)} rows → planning areas: {sorted(df['planning_area'].unique())}")
    return df


def dedupe_transactions(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop duplicate raw transactions using the broadest stable key available."""
    dedup_cols = ["planning_area", "transacted_price", "area_sqm", "sale_month", "property_type"]
    for extra in ["project_name", "street_name", "floor_level"]:
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


def run(args):
    out_path = Path(args.out)
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
        df = ingest_file(p, district)
        if not df.empty:
            frames.append(df)

    if not frames:
        sys.exit("No data after ingestion.")

    combined = pd.concat(frames, ignore_index=True)

    if args.merge and out_path.exists():
        existing = pd.read_csv(out_path)
        combined = pd.concat([existing, combined], ignore_index=True)
        combined, dropped = dedupe_transactions(combined)
        print(f"Merged with existing ({len(existing)} rows) → {len(combined)} rows total (deduped {dropped} rows)")
    else:
        combined, dropped = dedupe_transactions(combined)
        print(f"Total: {len(combined)} rows (deduped {dropped} rows)")

    combined.to_csv(out_path, index=False)
    print(f"\nWritten: {out_path}")
    print("\nRow counts by planning area:")
    for area, count in combined["planning_area"].value_counts().items():
        print(f"  {area}: {count}")

    print("\nNext: re-run value model to pick up new areas:")
    print(f"  python models/value_model.py --scores data/provision_scores.csv \\")
    print(f"      --hdb data/hdb_resale.csv --private {out_path} --out data/value_output_private.csv")


def main():
    ap = argparse.ArgumentParser(description="Ingest URA raw CSVs into ura_private.csv schema")
    ap.add_argument("--raw_dir", default="data/ura_raw", help="Directory of raw PMI CSVs")
    ap.add_argument("--files", nargs="*", help="Specific file(s) to ingest (overrides --raw_dir)")
    ap.add_argument("--out", default="data/ura_private.csv", help="Output file")
    ap.add_argument("--merge", action="store_true", help="Merge with existing --out file")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
