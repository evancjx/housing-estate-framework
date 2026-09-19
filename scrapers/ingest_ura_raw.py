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

USAGE:
    # Ingest new files from data/raw/ura/ and merge with existing ura_private.csv
    python scrapers/ingest_ura_raw.py \\
        --raw_dir data/raw/ura/ \\
        --out data/inputs/ura_private.csv \\
        --merge   # append to existing, deduplicate

    # Rebuild from scratch (replaces existing ura_private.csv)
    python scrapers/ingest_ura_raw.py --raw_dir data/raw/ura/ --out data/inputs/ura_private.csv

    # Ingest a specific file
    python scrapers/ingest_ura_raw.py --files data/raw/ura/pmi_d15_2021-2026.csv --out data/inputs/ura_private.csv --merge
"""

import argparse
import os
import sys
import re
import tempfile
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
    Project age is unknown: URA PMI downloads carry no completion year.
    Keep the column null rather than inventing a value. The value model
    does not use it as a control.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


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

    # sale_month: never invented. Unparseable dates stay null and the value
    # model excludes those rows; a file with no date column is skipped.
    if "sale_date" in df.columns:
        df["sale_month"] = df["sale_date"].apply(extract_sale_month)
    elif "sale_month" not in df.columns:
        print(f"  [WARN] {path.name}: missing sale_date/sale_month — skipping")
        return pd.DataFrame()

    # project_age_years
    df["project_age_years"] = compute_project_age(df)

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
                "unit_number_status", "unit_number_source"]
    for c in optional:
        if c in df.columns:
            out_cols.append(c)

    df = df[[c for c in out_cols if c in df.columns]]
    print(f"  {path.name}: {len(df)} rows → planning areas: {sorted(df['planning_area'].unique())}")
    return df


SOURCE_COL = "_source_file"


def _occurrence(df: pd.DataFrame, key: list[str]) -> pd.Series:
    """0, 1, 2... for each repeat of key within one source file."""
    source = df[SOURCE_COL].fillna("") if SOURCE_COL in df.columns else pd.Series("", index=df.index)
    return df.groupby([source, *key], dropna=False).cumcount()


def dedupe_transactions(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop transactions repeated across overlapping sources.

    URA PMI rows carry no unit number, so identical rows within one source are
    distinct units sold on identical terms. A transaction's true count is the
    most times it appears in any single source (raw file, or the existing
    output for --merge); rows beyond that count are cross-source repeats.
    """
    dedup_cols = ["planning_area", "transacted_price", "area_sqm", "sale_month", "property_type"]
    # Exact units that happen to share month/price/area are distinct
    # transactions. Include published address/unit context when available.
    for extra in ["project_name", "street_name", "address", "unit_number", "floor_level"]:
        if extra in df.columns:
            dedup_cols.append(extra)
    before = len(df)

    if "type_of_area" not in df.columns:
        df = df.assign(_occurrence=_occurrence(df, dedup_cols))
        df = df.drop_duplicates(subset=dedup_cols + ["_occurrence"], keep="last")
        return df.drop(columns=["_occurrence", SOURCE_COL], errors="ignore"), before - len(df)

    type_key = df["type_of_area"]
    has_type = type_key.notna() & type_key.astype(str).str.strip().ne("")
    typed = df[has_type]
    typed = typed.assign(_occurrence=_occurrence(typed, dedup_cols + ["type_of_area"]))
    typed = typed.drop_duplicates(subset=dedup_cols + ["type_of_area", "_occurrence"], keep="last")
    legacy_blank = df[~has_type]
    legacy_blank = legacy_blank.assign(_occurrence=_occurrence(legacy_blank, dedup_cols))

    if not typed.empty and not legacy_blank.empty:
        # A legacy blank row is the same transaction as a typed row while the
        # typed rows for that key still outnumber its occurrence.
        typed_counts = typed.groupby(dedup_cols, dropna=False).size().rename("_typed_count").reset_index()
        blank_typed_count = legacy_blank[dedup_cols].merge(
            typed_counts,
            on=dedup_cols,
            how="left",
        )["_typed_count"].fillna(0)
        legacy_blank = legacy_blank[
            legacy_blank["_occurrence"].to_numpy() >= blank_typed_count.to_numpy()
        ]

    legacy_blank = legacy_blank.drop_duplicates(subset=dedup_cols + ["_occurrence"], keep="last")
    df = pd.concat([legacy_blank, typed]).sort_index()
    return df.drop(columns=["_occurrence", SOURCE_COL], errors="ignore"), before - len(df)


def coverage_key(df: pd.DataFrame, other: pd.DataFrame) -> list[str]:
    """Finest location x type key both frames can be compared on."""
    location = (
        "postal_district"
        if "postal_district" in df.columns and "postal_district" in other.columns
        else "planning_area"
    )
    return [location, "property_type"]


def missing_coverage(existing: pd.DataFrame, rebuilt: pd.DataFrame) -> list[tuple]:
    """(location, property_type) groups present in existing but absent from rebuilt."""
    key = coverage_key(existing, rebuilt)

    def groups(frame):
        keyed = frame[key].astype("string").apply(lambda col: col.str.strip())
        if "postal_district" in key:
            keyed["postal_district"] = keyed["postal_district"].str.zfill(2)
        return set(keyed.dropna().itertuples(index=False, name=None))

    return sorted(groups(existing) - groups(rebuilt))


def write_csv_atomic(df: pd.DataFrame, out_path: Path) -> None:
    """Write via a sibling temp file so a failed write never truncates out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out_path.name}.", suffix=".tmp", dir=out_path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            df.to_csv(handle, index=False)
        os.replace(tmp_name, out_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


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
        df = ingest_file(p, district, source_quality=args.source_quality)
        if not df.empty:
            frames.append(df.assign(**{SOURCE_COL: str(p)}))

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
        # A rebuild from an incomplete raw_dir would silently drop whole
        # districts from the canonical input. Refuse unless explicitly allowed.
        if out_path.exists() and not args.allow_coverage_loss:
            lost = missing_coverage(pd.read_csv(out_path, low_memory=False), combined)
            if lost:
                preview = ", ".join("/".join(map(str, group)) for group in lost[:10])
                sys.exit(
                    f"ERROR: rebuild would drop {len(lost)} location/property-type group(s) "
                    f"present in {out_path}: {preview}{' ...' if len(lost) > 10 else ''}. "
                    "Use --merge, add the missing raw files, or pass --allow-coverage-loss."
                )

    write_csv_atomic(combined, out_path)
    print(f"\nWritten: {out_path}")
    print("\nRow counts by planning area:")
    for area, count in combined["planning_area"].value_counts().items():
        print(f"  {area}: {count}")

    print("\nNext: re-run value model to pick up new areas:")
    print(f"  python models/value_model.py --scores data/outputs/provision_scores.csv \\")
    print(f"      --hdb data/inputs/hdb_resale.csv --private {out_path} --out data/outputs/value_output_private.csv")


def main():
    ap = argparse.ArgumentParser(description="Ingest URA raw CSVs into ura_private.csv schema")
    ap.add_argument("--raw_dir", default="data/raw/ura", help="Directory of raw PMI CSVs")
    ap.add_argument("--files", nargs="*", help="Specific file(s) to ingest (overrides --raw_dir)")
    ap.add_argument("--out", default="data/inputs/ura_private.csv", help="Output file")
    ap.add_argument("--merge", action="store_true", help="Merge with existing --out file")
    ap.add_argument(
        "--allow-coverage-loss",
        action="store_true",
        help="Allow a non-merge rebuild to drop district/property-type groups present in --out",
    )
    ap.add_argument(
        "--source_quality",
        help="Optional provenance marker applied to all ingested rows, e.g. not_clean",
    )
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
