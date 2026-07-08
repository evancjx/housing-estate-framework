#!/usr/bin/env python3
"""
URA Transaction Download Orchestrator
======================================
Tries Playwright scraper first; falls back to the API client if it fails.

TYPICAL USAGE:
    # Download missing districts for the estate framework (15, 16 = Marine Parade/Bedok private)
    python scrapers/run_download.py --districts 15 16 --out_dir data/raw/ura/

    # Download landed transactions (Landed Properties (Non-Strata) + Strata Landed)
    python scrapers/run_download.py --landed --districts 15 16 --out_dir data/raw/ura/

    # Download all non-central districts (Apts & Condos only, all years)
    python scrapers/run_download.py --mode all --out_dir data/raw/ura/

    # API mode only (faster but requires token + WAF clearance)
    python scrapers/run_download.py --mode api --out_dir data/raw/ura/

After download, ingest the raw CSVs into the pipeline:
    python scrapers/ingest_ura_raw.py --raw_dir data/raw/ura/ --out data/inputs/ura_private.csv

Then re-run the value model:
    python models/value_model.py --scores data/outputs/provision_scores.csv \\
        --hdb data/inputs/hdb_resale.csv --private data/inputs/ura_private.csv \\
        --out data/outputs/value_output.csv
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

try:
    from scrapers.ura_pmi_playwright import (
        PROP_TYPE_MAP,
        normalize_prop_types,
        raw_filename,
    )
except ModuleNotFoundError:
    from ura_pmi_playwright import PROP_TYPE_MAP, normalize_prop_types, raw_filename

# Districts with meaningful private residential transactions
# (excludes D01/02/06/09/11/17/28 — central, industrial, or minimal residential)
RESIDENTIAL_DISTRICTS = [
    "03", "04", "05", "07", "08",         # Queenstown/Bukit Merah/Clementi/Kallang/Boon Keng
    "10", "12", "13", "14",               # Bukit Timah/Toa Payoh area/Geylang
    "15", "16",                            # Marine Parade/East Coast/Bedok  ← still missing
    "18", "19", "20",                      # Tampines+PasirRis/Serangoon+Hougang/Bishan+AMK
    "21", "22", "23",                      # Upper Bukit Timah/Jurong/Bukit Panjang+CCK
    "25", "26", "27",                      # Woodlands/Lentor/Yishun+Sembawang+Canberra
]

# Districts where we ALREADY have data (from prior sessions)
ALREADY_DOWNLOADED = {"03", "04", "05", "07", "08", "21", "27"}


async def run_playwright(
    districts: list,
    year_from: str,
    year_to: str,
    out_dir: Path,
    prop_types: list[str],
) -> dict:
    """Run the Playwright scraper for given districts. Returns {district: path_or_None}."""
    from scrapers.ura_pmi_playwright import run as pw_run
    import types

    args = types.SimpleNamespace(
        districts=districts,
        year_from=year_from,
        month_from="1",
        year_to=year_to,
        month_to="12",
        prop_type=prop_types[0],
        prop_types=prop_types,
        sale_type=[],
        out_dir=str(out_dir),
        headed=False,
        timeout=60,
    )

    # Redirect to pw_run which handles browser setup + returns nothing (prints results)
    # For orchestration, we just call subprocess to capture exit code
    return {}


def run_playwright_subprocess(
    districts: list,
    year_from: str,
    year_to: str,
    out_dir: Path,
    prop_types: list[str],
) -> bool:
    """Run Playwright scraper as subprocess. Returns True on success."""
    script = Path(__file__).parent / "ura_pmi_playwright.py"
    cmd = [
        sys.executable, str(script),
        "--districts", *districts,
        "--year_from", year_from,
        "--year_to", year_to,
        "--prop_types", *prop_types,
        "--out_dir", str(out_dir),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def run_api_subprocess(
    out_dir: Path,
    prop_types: list[str],
    districts: list[str] | None = None,
) -> bool:
    """Run API client as subprocess. Returns True on success."""
    script = Path(__file__).parent / "ura_pmi_api.py"
    cmd = [sys.executable, str(script), "--out_dir", str(out_dir)]
    if districts:
        cmd.extend(["--districts", *districts])
    if prop_types:
        cmd.extend(["--prop_types", *prop_types])
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    ap = argparse.ArgumentParser(description="URA PMI download orchestrator")
    ap.add_argument(
        "--districts", nargs="*", metavar="NN",
        help="Districts to download (default: residential_districts minus already-downloaded)",
    )
    ap.add_argument(
        "--mode", default="playwright",
        choices=["playwright", "api", "both", "all"],
        help=(
            "playwright = web scraper only (default); "
            "api = API client only; "
            "both = playwright first, api fallback; "
            "all = playwright for all residential districts"
        ),
    )
    ap.add_argument("--year_from", default="2021", help="Start year (default: 2021)")
    ap.add_argument("--year_to", default="2026", help="End year (default: 2026)")
    ap.add_argument("--out_dir", default="data/raw/ura", help="Output directory")
    ap.add_argument(
        "--prop_types", nargs="+", default=["3"],
        help=(
            "Property type(s): 1/landed, 2/strata_landed, 3/apt_condo, 4/ec. "
            "Default: 3 (Apartments & Condominiums)."
        ),
    )
    ap.add_argument(
        "--landed", action="store_true",
        help="Shortcut for --prop_types landed strata_landed",
    )
    ap.add_argument(
        "--include_existing", action="store_true",
        help="Re-download districts already in data/inputs/ura_private.csv",
    )
    args = ap.parse_args()
    try:
        prop_types = normalize_prop_types(["landed", "strata_landed"] if args.landed else args.prop_types)
    except ValueError as e:
        ap.error(str(e))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "all":
        districts = RESIDENTIAL_DISTRICTS
    elif args.districts:
        districts = [d.zfill(2) for d in args.districts]
    else:
        # Default: only missing districts
        districts = [d for d in RESIDENTIAL_DISTRICTS if d not in ALREADY_DOWNLOADED]

    if not args.include_existing:
        # Check which district/type files already exist. This must be property-type
        # aware; a condo CSV must not cause landed downloads to be skipped.
        to_skip = {
            district
            for district in districts
            if all(
                (out_dir / raw_filename(district, args.year_from, args.year_to, prop_type)).exists()
                for prop_type in prop_types
            )
        }
        if to_skip:
            print(f"Skipping {sorted(to_skip)} (files exist). Use --include_existing to re-download.")
            districts = [d for d in districts if d not in to_skip]

    if not districts:
        print("Nothing to download.")
        return

    print(f"Districts to download: {districts}")
    print("Property types: " + ", ".join(PROP_TYPE_MAP[p] for p in prop_types))
    print(f"Output: {out_dir}")
    print()

    if args.mode in ("playwright", "both", "all"):
        ok = run_playwright_subprocess(districts, args.year_from, args.year_to, out_dir, prop_types)
        if ok or args.mode != "both":
            return

        # Playwright failed — fall through to API
        print("\nPlaywright scraper failed. Trying API fallback...")

    if args.mode in ("api", "both"):
        run_api_subprocess(out_dir, prop_types, districts)


if __name__ == "__main__":
    main()
