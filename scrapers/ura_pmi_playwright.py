#!/usr/bin/env python3
"""
URA PMI Playwright Scraper
==========================
Downloads private residential transaction data from the URA Property Market
Information portal using Playwright browser automation.

Portal: https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch

USAGE:
    # Download Apartments & Condominiums for districts 03, 04, 05
    python scrapers/ura_pmi_playwright.py --districts 03 04 05 --out_dir data/raw/ura/

    # Download landed transactions: Landed Properties (Non-Strata) + Strata Landed
    python scrapers/ura_pmi_playwright.py --districts 15 16 --prop_types landed strata_landed

    # Full date range, resale only
    python scrapers/ura_pmi_playwright.py --districts 15 16 --year_from 2021 --sale_type 3

    # All districts with private transactions (non-central)
    python scrapers/ura_pmi_playwright.py --districts 03 04 05 07 08 10 14 15 16 18 19 20 21 22 23 24 25 26 27 --out_dir data/raw/ura/

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
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
import sys
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

ATTEMPT_MANIFEST_SCHEMA_VERSION = 1
ATTEMPT_STATUSES = {"succeeded", "confirmed_empty", "failed"}


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp for acquisition evidence."""
    return datetime.now(timezone.utc).isoformat()


def partition_id(district: str, prop_type: str) -> str:
    """Return the stable identifier for one district/property-type request."""
    return f"d{str(district).zfill(2)}-p{normalize_prop_type(prop_type)}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_metadata(path: Path, *, relative_to: Path) -> dict[str, object]:
    """Describe exact downloaded CSV bytes without exposing an absolute path."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("downloaded CSV has no header")
        row_count = sum(1 for _row in reader)
    relative_path = Path(os.path.relpath(path, relative_to))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("artifact path escapes the attempt-manifest generation")
    return {
        "relative_path": relative_path.as_posix(),
        "sha256": sha256_file(path),
        "byte_count": path.stat().st_size,
        "row_count": row_count,
    }


def atomic_write_json(path: Path, payload: dict[str, object]) -> Path:
    """Write one attempt manifest without exposing partially serialized JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def attempt_manifest_path(
    out_dir: Path,
    requested: str | None,
    *,
    method: str,
) -> Path:
    path = Path(requested) if requested else out_dir / f"ura_pmi_{method}_attempts.json"
    try:
        out_dir.resolve().relative_to(path.parent.resolve())
    except ValueError as exc:
        raise ValueError(
            "--out_dir must be the attempt manifest directory or one of its "
            "descendants so artifact paths cannot escape the generation"
        ) from exc
    return path


def normalize_month_scope(
    year_from: object,
    month_from: object,
    year_to: object,
    month_to: object,
) -> tuple[str, str, str, str]:
    """Validate and normalize an inclusive year/month acquisition scope."""
    try:
        start_year = int(str(year_from))
        start_month = int(str(month_from))
        end_year = int(str(year_to))
        end_month = int(str(month_to))
    except (TypeError, ValueError) as exc:
        raise ValueError("URA date scope must contain numeric years and months") from exc
    if not 1 <= start_month <= 12 or not 1 <= end_month <= 12:
        raise ValueError("URA date-scope months must be between 1 and 12")
    if (start_year, start_month) > (end_year, end_month):
        raise ValueError("URA date scope must not be reversed")
    return (
        str(start_year),
        str(start_month),
        str(end_year),
        str(end_month),
    )


def manifest_sale_types(sale_types: list[str]) -> list[str]:
    """Represent an empty portal selection as its explicit all-types scope."""
    return list(sale_types) if sale_types else list(sorted(SALE_TYPE_MAP))


def new_attempt(
    *,
    district: str,
    prop_type: str,
    method: str,
    status: str,
    started_at: str,
    completed_at: str,
    artifact: dict[str, object] | None = None,
    observations: dict[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, object]:
    if status not in ATTEMPT_STATUSES:
        raise ValueError(f"invalid attempt status: {status}")
    prop_type = normalize_prop_type(prop_type)
    return {
        "partition_id": partition_id(district, prop_type),
        "district": str(district).zfill(2),
        "property_type": prop_type,
        "property_type_label": PROP_TYPE_MAP[prop_type],
        "method": method,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "artifact": artifact,
        "observations": observations,
        "error_code": error_code,
        "error_message": error_message,
    }


def build_attempt_manifest(
    *,
    method: str,
    started_at: str,
    completed_at: str,
    districts: list[str],
    prop_types: list[str],
    year_from: str | None,
    month_from: str | None,
    year_to: str | None,
    month_to: str | None,
    sale_types: list[str],
    attempts: list[dict[str, object]],
    source_requests: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    failed = [attempt for attempt in attempts if attempt["status"] == "failed"]
    return {
        "schema_version": ATTEMPT_MANIFEST_SCHEMA_VERSION,
        "source": "URA PMI",
        "method": method,
        "status": "failed" if failed else "succeeded",
        "started_at": started_at,
        "completed_at": completed_at,
        "requested_scope": {
            "districts": [str(value).zfill(2) for value in districts],
            "property_types": [normalize_prop_type(value) for value in prop_types],
            "sale_types": list(sale_types),
            "year_from": year_from,
            "month_from": month_from,
            "year_to": year_to,
            "month_to": month_to,
        },
        "source_requests": source_requests or [],
        "attempts": attempts,
        "summary": {
            "requested": len(attempts),
            "succeeded": sum(a["status"] == "succeeded" for a in attempts),
            "confirmed_empty": sum(
                a["status"] == "confirmed_empty" for a in attempts
            ),
            "failed": len(failed),
        },
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


def scoped_raw_filename(
    district: str,
    year_from: str,
    month_from: str,
    year_to: str,
    month_to: str,
    prop_type: str,
    sale_types: list[str],
) -> str:
    """Keep the legacy name only for a full-year, all-sale-types request."""
    name = raw_filename(district, year_from, year_to, prop_type)
    suffixes: list[str] = []
    if int(month_from) != 1 or int(month_to) != 12:
        suffixes.append(f"m{int(month_from):02d}-{int(month_to):02d}")
    normalized_sale_types = sorted(set(sale_types))
    if normalized_sale_types and normalized_sale_types != sorted(SALE_TYPE_MAP):
        suffixes.append("sale-" + "-".join(normalized_sale_types))
    if not suffixes:
        return name
    return name.removesuffix(".csv") + "_" + "_".join(suffixes) + ".csv"


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
    artifact_root: Path | None = None,
    timeout_ms: int = 60000,
) -> dict[str, object]:
    """
    Download CSV for one partition and return a structured terminal attempt.

    Only a portal-confirmed no-data response is ``confirmed_empty``. Timeouts,
    malformed/empty downloads, and browser errors remain failed and cannot be
    mistaken for completed work by callers.
    """
    started_at = utc_now()
    label = DISTRICT_LABELS.get(district)
    if not label:
        print(f"  [ERROR] Unknown district '{district}' — skipping", file=sys.stderr)
        return new_attempt(
            district=district,
            prop_type=prop_type,
            method="playwright",
            status="failed",
            started_at=started_at,
            completed_at=utc_now(),
            error_code="invalid_district",
            error_message=f"Unknown district {district}",
        )

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
        await page.wait_for_selector(
            "#searchResult form.resultForm, #searchResult #noDataError, "
            "#searchResult .no-result",
            state="attached",
            timeout=timeout_ms,
        )
        print("results loaded.")
    except Exception:
        print("TIMEOUT — no results loaded")
        try:
            html_snippet = await page.evaluate(
                "document.getElementById('searchResult').innerHTML.slice(0, 200)"
            )
        except Exception:
            html_snippet = "unavailable"
        print(f"    searchResult snippet: {html_snippet}", file=sys.stderr)
        return new_attempt(
            district=district,
            prop_type=prop_type,
            method="playwright",
            status="failed",
            started_at=started_at,
            completed_at=utc_now(),
            error_code="results_timeout",
            error_message="Search results did not load before the configured timeout",
        )

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
        return new_attempt(
            district=district,
            prop_type=prop_type,
            method="playwright",
            status="confirmed_empty",
            started_at=started_at,
            completed_at=utc_now(),
            observations={"row_count": 0},
        )

    # 9. Trigger CSV download via the resultForm submit
    out_file = out_dir / scoped_raw_filename(
        district,
        year_from,
        month_from,
        year_to,
        month_to,
        prop_type,
        sale_types,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{out_file.name}.", suffix=".download", dir=out_dir
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        async with page.expect_download(timeout=60000) as dl_info:
            submit_result = await page.evaluate("""
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
            if submit_result != "submitted":
                raise RuntimeError("download form was not present")

        dl = await dl_info.value
        await dl.save_as(str(temporary))
        metadata = artifact_metadata(temporary, relative_to=artifact_root or out_dir)
        if metadata["byte_count"] <= 0 or metadata["row_count"] <= 0:
            raise ValueError("downloaded CSV did not contain any transaction rows")
        os.replace(temporary, out_file)
        metadata = artifact_metadata(out_file, relative_to=artifact_root or out_dir)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    print(f"    Saved: {out_file.name} ({out_file.stat().st_size // 1024} KB)")
    return new_attempt(
        district=district,
        prop_type=prop_type,
        method="playwright",
        status="succeeded",
        started_at=started_at,
        completed_at=utc_now(),
        artifact=metadata,
        observations={"row_count": metadata["row_count"]},
    )


async def run(args, *, playwright_factory=None) -> dict[str, object]:
    if playwright_factory is None:
        from playwright.async_api import async_playwright

        playwright_factory = async_playwright

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = attempt_manifest_path(
        out_dir,
        getattr(args, "attempt_manifest", None),
        method="playwright",
    )
    started_at = utc_now()

    districts = [d.zfill(2) for d in args.districts]
    sale_types = args.sale_type if args.sale_type else []
    prop_types = normalize_prop_types(getattr(args, "prop_types", None) or [args.prop_type])
    year_from, month_from, year_to, month_to = normalize_month_scope(
        args.year_from,
        args.month_from,
        args.year_to,
        args.month_to,
    )

    attempts: list[dict[str, object]] = []
    total = len(districts) * len(prop_types)
    browser_error: Exception | None = None
    try:
        async with playwright_factory() as pw:
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

            n = 0
            for district in districts:
                for prop_type in prop_types:
                    n += 1
                    prop_label = PROP_TYPE_MAP[prop_type]
                    print(f"\n[{n}/{total}] Downloading district {district} / {prop_label}...")
                    attempt_started_at = utc_now()
                    try:
                        attempt = await download_district(
                            page=page,
                            district=district,
                            year_from=year_from,
                            month_from=month_from,
                            year_to=year_to,
                            month_to=month_to,
                            prop_type=prop_type,
                            sale_types=sale_types,
                            out_dir=out_dir,
                            artifact_root=manifest_path.parent,
                            timeout_ms=args.timeout * 1000,
                        )
                    except Exception as exc:
                        print(
                            f"  [ERROR] District {district} / {prop_label} failed: {exc}",
                            file=sys.stderr,
                        )
                        attempt = new_attempt(
                            district=district,
                            prop_type=prop_type,
                            method="playwright",
                            status="failed",
                            started_at=attempt_started_at,
                            completed_at=utc_now(),
                            error_code="browser_or_download_error",
                            error_message=str(exc),
                        )
                    attempts.append(attempt)

                    if n < total:
                        await asyncio.sleep(3)

            await browser.close()
    except Exception as exc:
        browser_error = exc
        print(f"[ERROR] Playwright setup failed: {exc}", file=sys.stderr)

    completed_partitions = {str(attempt["partition_id"]) for attempt in attempts}
    for district in districts:
        for prop_type in prop_types:
            if partition_id(district, prop_type) in completed_partitions:
                continue
            attempts.append(
                new_attempt(
                    district=district,
                    prop_type=prop_type,
                    method="playwright",
                    status="failed",
                    started_at=started_at,
                    completed_at=utc_now(),
                    error_code="browser_setup_error",
                    error_message=str(browser_error or "partition was not attempted"),
                )
            )

    manifest = build_attempt_manifest(
        method="playwright",
        started_at=started_at,
        completed_at=utc_now(),
        districts=districts,
        prop_types=prop_types,
        year_from=year_from,
        month_from=month_from,
        year_to=year_to,
        month_to=month_to,
        sale_types=manifest_sale_types(sale_types),
        attempts=attempts,
    )
    atomic_write_json(manifest_path, manifest)

    print("\n=== SUMMARY ===")
    ok = [attempt for attempt in attempts if attempt["status"] == "succeeded"]
    empty = [attempt for attempt in attempts if attempt["status"] == "confirmed_empty"]
    fail = [attempt for attempt in attempts if attempt["status"] == "failed"]
    for attempt in attempts:
        print(
            f"  D{attempt['district']} / {attempt['property_type_label']}: "
            f"{str(attempt['status']).upper()}"
        )
    print(
        f"\n{len(ok)} downloaded, {len(empty)} confirmed empty, "
        f"{len(fail)} failed of {len(attempts)} requested partitions."
    )
    print(f"Attempt manifest: {manifest_path}")
    if ok:
        print(f"Files in: {out_dir}")
    return manifest


def main(argv: list[str] | None = None) -> int:
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
    ap.add_argument("--out_dir", default="data/raw/ura", help="Output directory (default: data/raw/ura)")
    ap.add_argument(
        "--attempt-manifest",
        help="Structured attempt JSON (default: <out_dir>/ura_pmi_playwright_attempts.json)",
    )
    ap.add_argument("--headed", action="store_true", help="Run in headed mode (shows browser window)")
    ap.add_argument("--timeout", type=int, default=60, help="Results load timeout in seconds (default: 60)")
    args = ap.parse_args(argv)
    try:
        args.prop_types = normalize_prop_types(args.prop_types or [args.prop_type])
    except ValueError as e:
        ap.error(str(e))

    manifest = asyncio.run(run(args))
    return 0 if manifest["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
