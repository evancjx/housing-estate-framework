#!/usr/bin/env python3
"""
URA PMI Playwright Scraper
==========================
Downloads private residential transaction data from the URA Property Market
Information portal using Playwright browser automation.

Portal: https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch

USAGE:
    # Download Apartments & Condominiums for districts 03, 04, 05
    python scrapers/ura_pmi_playwright.py --districts 03 04 05 --out_dir data/ura_raw/

    # Download landed transactions: Landed Properties (Non-Strata) + Strata Landed
    python scrapers/ura_pmi_playwright.py --districts 15 16 --prop_types landed strata_landed

    # Full date range, resale only
    python scrapers/ura_pmi_playwright.py --districts 15 16 --year_from 2021 --sale_type 3

    # All districts with private transactions (non-central)
    python scrapers/ura_pmi_playwright.py --districts 03 04 05 07 08 10 14 15 16 18 19 20 21 22 23 24 25 26 27 --out_dir data/ura_raw/

DISTRICT → ESTATE mapping (estates.csv names):
    03 → QUEENSTOWN / DOVER / HOLLAND VILLAGE proxy
    04 → BUKIT MERAH
    05 → CLEMENTI
    07 → KALLANG
    08 → BOON KENG
    10 → BUKIT TIMAH (Ardmore/Holland Rd area) / HOLLAND VILLAGE
    14 → GEYLANG
    15 → MARINE PARADE (Katong/East Coast)
    16 → BEDOK
    18 → TAMPINES / PASIR RIS
    19 → SERANGOON / HOUGANG / PUNGGOL
    20 → BISHAN / ANG MO KIO
    21 → BUKIT TIMAH (Upper Bukit Timah)
    22 → JURONG EAST / JURONG WEST
    23 → BUKIT PANJANG / CHOA CHU KANG
    24 → TENGAH
    25 → WOODLANDS
    26 → LENTOR (AMK area)
    27 → YISHUN / SEMBAWANG / CANBERRA
    28 → SELETAR

OUTPUT:
    CSV files: {out_dir}/pmi_d{district}_{property_type}_{year_from}-{year_to}.csv
    Apartments & Condominiums keep the legacy filename
    {out_dir}/pmi_d{district}_{year_from}-{year_to}.csv.
    Column names match URA REALIS caveat schema (no transformation applied).

INSTALL:
    pip install playwright --break-system-packages
    playwright install chromium
"""

import argparse
import asyncio
import json
import sys
import os
from pathlib import Path

# District value → display label (from URA PMI portal)
DISTRICT_LABELS = {
    "01": "D01 / Raffles Place, Cecil, Marina, People's Park",
    "02": "D02 / Anson, Tanjong Pagar",
    "03": "D03 / Queenstown, Tiong Bahru",
    "04": "D04 / Telok Blangah, Harbourfront",
    "05": "D05 / Pasir Panjang, Hong Leong Garden, Clementi New Town",
    "06": "D06 / High Street, Beach Road (part)",
    "07": "D07 / Middle Road, Golden Mile",
    "08": "D08 / Little India",
    "09": "D09 / Orchard, Cairnhill, River Valley",
    "10": "D10 / Ardmore, Bukit Timah, Holland Road, Tanglin",
    "11": "D11 / Watten Estate, Novena, Thomson",
    "12": "D12 / Balestier, Toa Payoh, Serangoon",
    "13": "D13 / Macpherson, Braddell",
    "14": "D14 / Geylang, Eunos",
    "15": "D15 / Katong, Joo Chiat, Amber Road",
    "16": "D16 / Bedok, Upper East Coast, Eastwood, Kew Drive",
    "17": "D17 / Loyang, Changi",
    "18": "D18 / Tampines, Pasir Ris",
    "19": "D19 / Serangoon Garden, Hougang, Punggol",
    "20": "D20 / Bishan, Ang Mo Kio",
    "21": "D21 / Upper Bukit Timah, Clementi Park, Ulu Pandan",
    "22": "D22 / Jurong",
    "23": "D23 / Hillview, Dairy Farm, Bukit Panjang, Choa Chu Kang",
    "24": "D24 / Lim Chu Kang, Tengah",
    "25": "D25 / Kranji, Woodgrove",
    "26": "D26 / Upper Thomson, Springleaf",
    "27": "D27 / Yishun, Sembawang",
    "28": "D28 / Seletar",
}

PORTAL_URL = "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch"

# Property type values (select#propertyTypeGroupNo)
PROP_TYPE_MAP = {
    "1": "Landed Properties (Non-Strata)",
    "2": "Strata Landed",
    "3": "Apartments & Condominiums",
    "4": "Executive Condominiums",
    "all": "",  # empty = all types (field stays disabled when not postal-district mode)
}

PROP_TYPE_SLUGS = {
    "1": "landed_non_strata",
    "2": "strata_landed",
    "3": "apt_condo",
    "4": "executive_condo",
    "all": "all_residential",
}

PROP_TYPE_ALIASES = {
    "landed": "1",
    "landed_non_strata": "1",
    "landed-non-strata": "1",
    "non_strata_landed": "1",
    "non-strata-landed": "1",
    "strata_landed": "2",
    "strata-landed": "2",
    "apt_condo": "3",
    "apt-condo": "3",
    "apartment": "3",
    "apartments": "3",
    "condo": "3",
    "condos": "3",
    "ec": "4",
    "executive_condo": "4",
    "executive-condo": "4",
}

# Sale type values (multiselect#saleType)
SALE_TYPE_MAP = {
    "1": "New Sale",
    "2": "Sub Sale",
    "3": "Resale",
}


def normalize_prop_type(value: str) -> str:
    """Return the URA property type code for a CLI value or alias."""
    v = str(value).strip().lower()
    v = PROP_TYPE_ALIASES.get(v, v)
    if v not in PROP_TYPE_MAP or v == "all":
        raise ValueError(
            f"Unknown property type '{value}'. Use one of: "
            "1/landed, 2/strata_landed, 3/apt_condo, 4/ec"
        )
    return v


def normalize_prop_types(values: list[str] | None) -> list[str]:
    """Normalize property type values, preserving order and removing duplicates."""
    raw = values or ["3"]
    out = []
    for value in raw:
        code = normalize_prop_type(value)
        if code not in out:
            out.append(code)
    return out


def prop_type_slug(prop_type: str) -> str:
    return PROP_TYPE_SLUGS[normalize_prop_type(prop_type)]


def raw_filename(district: str, year_from: str, year_to: str, prop_type: str) -> str:
    """
    Return the raw CSV filename for a district/property-type download.

    Apartments & Condominiums keep the historical filename so existing data and
    README commands remain valid. Other property groups include a slug to avoid
    overwriting apartment/condo downloads for the same district/date range.
    """
    district = str(district).zfill(2)
    prop_type = normalize_prop_type(prop_type)
    if prop_type == "3":
        return f"pmi_d{district}_{year_from}-{year_to}.csv"
    return f"pmi_d{district}_{prop_type_slug(prop_type)}_{year_from}-{year_to}.csv"


async def download_district(
    page,
    district: str,
    year_from: str,
    month_from: str,
    year_to: str,
    month_to: str,
    prop_type: str,
    sale_types: list,
    out_dir: Path,
    timeout_ms: int = 60000,
) -> Path | None:
    """
    Download CSV for one district. Returns the saved file path, or None on failure.
    """
    label = DISTRICT_LABELS.get(district)
    if not label:
        print(f"  [ERROR] Unknown district '{district}' — skipping", file=sys.stderr)
        return None

    prop_label = PROP_TYPE_MAP.get(prop_type, prop_type)
    print(f"  District {district}: {label[:50]}... / {prop_label}")

    await page.goto(PORTAL_URL, wait_until="commit", timeout=30000)
    await page.wait_for_timeout(5000)

    # 1. Set locationDetails JSON (bypasses modal interaction)
    location_json = json.dumps(["postalDistrict", label])
    await page.evaluate(
        f"""$("input[name=locationDetails]").val({json.dumps(location_json)}).change();"""
    )
    await page.wait_for_timeout(500)

    # 2. Select property type (now enabled after locationDetails.change())
    enabled = await page.evaluate("!document.getElementById('propertyTypeGroupNo').disabled")
    if not enabled:
        print(f"  [WARN] Property type selector still disabled after locationDetails set — attempting force", file=sys.stderr)
        await page.evaluate(
            "document.getElementById('propertyTypeGroupNo').removeAttribute('disabled')"
        )

    if prop_type and prop_type != "all":
        await page.select_option("#propertyTypeGroupNo", prop_type)

    # 3. Set date range
    await page.evaluate(f"""
        document.getElementById('saleYearFrom').value = '{year_from}';
        document.getElementById('saleMonthFrom').value = '{month_from}';
        document.getElementById('saleYearTo').value = '{year_to}';
        document.getElementById('saleMonthTo').value = '{month_to}';
    """)

    # 4. Set sale types (multiselect — set selected on underlying <select>)
    if sale_types:
        sale_vals = json.dumps(sale_types)
        await page.evaluate(f"""
            var sel = document.getElementById('saleType');
            var wanted = {sale_vals};
            for (var i = 0; i < sel.options.length; i++) {{
                sel.options[i].selected = wanted.indexOf(sel.options[i].value) !== -1;
            }}
        """)
    else:
        # Select all
        await page.evaluate("""
            var sel = document.getElementById('saleType');
            for (var i = 0; i < sel.options.length; i++) sel.options[i].selected = true;
        """)

    # 5. Submit search via ajaxSubmit (direct call — skips button visibility checks)
    print("    Submitting search...", end=" ", flush=True)
    await page.evaluate("ajaxSubmit($('#appForm'))")

    # 6. Wait for results to load into #searchResult
    try:
        await page.wait_for_selector("#searchResult form.resultForm", state="attached", timeout=timeout_ms)
        print("results loaded.")
    except Exception:
        print("TIMEOUT — no results loaded")
        html_snippet = await page.evaluate(
            "document.getElementById('searchResult').innerHTML.slice(0, 200)"
        )
        print(f"    searchResult snippet: {html_snippet}", file=sys.stderr)
        return None

    # 7. Check how many results
    result_count_text = await page.evaluate("""
        (function() {
            var h3s = document.querySelectorAll('#searchResult h3, #searchResult .result-count, #searchResult .panel-heading');
            for (var i = 0; i < h3s.length; i++) {
                var t = h3s[i].textContent.trim();
                if (t) return t;
            }
            // fallback: look for download link text
            var csv = document.querySelector('#searchResult a.downloadCSV');
            return csv ? csv.textContent.trim() : 'unknown count';
        })()
    """)
    print(f"    Results: {result_count_text}")

    # 8. Check no-data scenario
    no_data = await page.evaluate("""
        document.querySelector('#searchResult #noDataError') !== null ||
        document.querySelector('#searchResult .no-result') !== null
    """)
    if no_data:
        print(f"    No transactions found for district {district} in this date range.")
        return None

    # 9. Trigger CSV download via the resultForm submit
    out_file = out_dir / raw_filename(district, year_from, year_to, prop_type)

    async with page.expect_download(timeout=60000) as dl_info:
        await page.evaluate("""
            (function() {
                var form = document.querySelector('#searchResult form.resultForm');
                if (!form) return 'no-form';
                var gotoPage = form.querySelector('input[name=gotoPage]');
                var dlType   = form.querySelector('input[name=downloadType]');
                var csvLink  = document.querySelector('#searchResult a.downloadCSV');
                var dlPage   = csvLink ? csvLink.getAttribute('data-page-dlpage') : '1';
                if (gotoPage) gotoPage.value = dlPage;
                if (dlType)   dlType.value   = 'downloadCSV';
                // Some resultForms don't have downloadType — add it
                if (!dlType) {
                    var inp = document.createElement('input');
                    inp.type = 'hidden';
                    inp.name = 'downloadType';
                    inp.value = 'downloadCSV';
                    form.appendChild(inp);
                }
                form.submit();
                return 'submitted';
            })()
        """)

    dl = await dl_info.value
    await dl.save_as(str(out_file))
    print(f"    Saved: {out_file.name} ({out_file.stat().st_size // 1024} KB)")
    return out_file


async def run(args):
    from playwright.async_api import async_playwright

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    districts = [d.zfill(2) for d in args.districts]
    invalid = [d for d in districts if d not in DISTRICT_LABELS]
    if invalid:
        print(f"[ERROR] Unknown district(s): {invalid}. Valid: 01–28", file=sys.stderr)
        sys.exit(1)

    sale_types = args.sale_type if args.sale_type else []
    prop_types = normalize_prop_types(getattr(args, "prop_types", None) or [args.prop_type])

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = await ctx.new_page()

        results = {}
        total = len(districts) * len(prop_types)
        n = 0
        for district in districts:
            for prop_type in prop_types:
                n += 1
                prop_label = PROP_TYPE_MAP[prop_type]
                print(f"\n[{n}/{total}] Downloading district {district} / {prop_label}...")
                try:
                    saved = await download_district(
                        page=page,
                        district=district,
                        year_from=args.year_from,
                        month_from=args.month_from,
                        year_to=args.year_to,
                        month_to=args.month_to,
                        prop_type=prop_type,
                        sale_types=sale_types,
                        out_dir=out_dir,
                        timeout_ms=args.timeout * 1000,
                    )
                    results[(district, prop_type)] = str(saved) if saved else None
                except Exception as e:
                    print(f"  [ERROR] District {district} / {prop_label} failed: {e}", file=sys.stderr)
                    results[(district, prop_type)] = None

                # Brief pause between searches to avoid rate limiting
                if n < total:
                    await asyncio.sleep(3)

        await browser.close()

    print("\n=== SUMMARY ===")
    ok = [k for k, f in results.items() if f]
    fail = [k for k, f in results.items() if not f]
    for district, prop_type in ok:
        print(f"  D{district} / {PROP_TYPE_MAP[prop_type]}: {results[(district, prop_type)]}")
    for district, prop_type in fail:
        print(f"  D{district} / {PROP_TYPE_MAP[prop_type]}: FAILED")
    print(f"\n{len(ok)}/{len(results)} downloads completed successfully.")
    if ok:
        print(f"Files in: {out_dir}")


def main():
    ap = argparse.ArgumentParser(
        description="Download URA PMI private residential transaction CSVs via Playwright"
    )
    ap.add_argument(
        "--districts", nargs="+", required=True, metavar="NN",
        help="Postal district numbers, e.g. --districts 03 04 05 15 16",
    )
    ap.add_argument("--year_from", default="2021", help="Start year (default: 2021)")
    ap.add_argument("--month_from", default="1", help="Start month 1-12 (default: 1)")
    ap.add_argument("--year_to", default="2026", help="End year (default: 2026)")
    ap.add_argument("--month_to", default="12", help="End month 1-12 (default: 12)")
    ap.add_argument(
        "--prop_type", default="3",
        help=(
            "Single property type, kept for backward compatibility: "
            "1/landed, 2/strata_landed, 3/apt_condo (default), 4/ec"
        ),
    )
    ap.add_argument(
        "--prop_types", nargs="+",
        help=(
            "One or more property types. Example for landed coverage: "
            "--prop_types landed strata_landed"
        ),
    )
    ap.add_argument(
        "--sale_type", nargs="*", default=[],
        choices=["1", "2", "3"],
        help="Sale type(s): 1=New Sale, 2=Sub Sale, 3=Resale. Default: all.",
    )
    ap.add_argument("--out_dir", default="data/ura_raw", help="Output directory (default: data/ura_raw)")
    ap.add_argument("--headed", action="store_true", help="Run in headed mode (shows browser window)")
    ap.add_argument("--timeout", type=int, default=60, help="Results load timeout in seconds (default: 60)")
    args = ap.parse_args()
    try:
        args.prop_types = normalize_prop_types(args.prop_types or [args.prop_type])
    except ValueError as e:
        ap.error(str(e))

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
