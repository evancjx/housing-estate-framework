#!/usr/bin/env python3
"""
EdgeProp condo/apartment transaction scraper and saved-table parser.

By default, Playwright only reads rows visible in an unauthenticated browser
session. EdgeProp masks unit numbers there and gates full unit-number access
behind login/Pro access. An authorised Playwright storage state may be supplied
with --storage-state, or a table the user is authorised to view may be parsed
from saved HTML/text with parse-transactions.

Unit numbers are never inferred. The unit_number field is populated only when
the rendered/saved address contains one unmasked #floor-stack token.
Masked, absent, and unparseable values remain blank and are distinguished by
unit_number_status.

Commands:
    python3 scrapers/edgeprop_condo_apartment_playwright.py discover
    python3 scrapers/edgeprop_condo_apartment_playwright.py scrape --resume
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import html
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError
    async_playwright = None

try:
    from scrapers.edgeprop_landed import DEFAULT_USER_AGENT, SQFT_TO_SQM, text_from_html
except ModuleNotFoundError:
    from edgeprop_landed import DEFAULT_USER_AGENT, SQFT_TO_SQM, text_from_html


BASE_URL = "https://www.edgeprop.sg"
DEFAULT_INDEX_URL = f"{BASE_URL}/condo-apartment/all"
DEFAULT_PROJECTS = "data/raw/edgeprop/edgeprop_condo_apartment_projects.csv"
DEFAULT_OUTPUT = "data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"

DATE_RE = re.compile(r"^\d{1,2}\s+[A-Z]{3}\s+\d{4}$", re.I)
MONEY_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
DETAIL_PATH_RE = re.compile(r"^/condo-apartment/[^/?#]+$")
UNIT_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9])#(?P<floor>[A-Z0-9X*?]{1,4})-(?P<stack>[A-Z0-9X*?]{1,6})(?![A-Z0-9])",
    re.I,
)
SALES_COUNT_RE = re.compile(r"ALL SALES TRANSACTIONS?\s*\((\d+)\)", re.I)

FIELDS = [
    "Project", "planning_area", "Postal District", "Date of Sale", "Address", "Street",
    "Bedrooms", "Unit Price ($psf)", "Price ($)", "Type", "Tenure", "Sale Type",
    "Area (sqft)", "Area (sqm)", "Type of Area", "Purchaser Address", "Source",
    "source_quality", "source_url", "source_slug",
]

UNIT_PROVENANCE_FIELDS = [
    "unit_number", "unit_floor", "unit_stack", "unit_number_status",
    "unit_number_source",
]

# Dedicated unit-level output schema. Keep the provenance fields next to the
# published address while retaining all transaction columns used downstream.
UNIT_FIELDS = FIELDS[:6] + UNIT_PROVENANCE_FIELDS + FIELDS[6:]

ATTEMPT_FIELDS = [
    "source_url", "source_slug", "name", "row_count", "pages_scraped",
    "oldest_date", "status", "error",
]


@dataclass(frozen=True)
class ProjectLink:
    name: str
    url: str
    slug: str


@dataclass
class ScrapeResult:
    rows: list[dict[str, Any]]
    pages_scraped: int = 0
    oldest_date: str = ""


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        href = attr_map.get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = " ".join(" ".join(self._text).split())
            self.links.append((self._href, text))
            self._href = None
            self._text = []


def clean_line(line: str) -> str:
    line = html.unescape(line).replace("\xa0", " ")
    return " ".join(line.split()).strip()


def extract_unit_number(address: str) -> dict[str, str]:
    """
    Extract an exact EdgeProp unit token without guessing masked values.

    Status values are stable and intentionally small:
      exact        one unmasked #floor-stack token was published
      masked       the published token contains X, * or ?
      not_present  the address has no # unit fragment
      unparseable  a # fragment exists but is ambiguous/malformed
    """
    published = clean_line(address)
    matches = list(UNIT_TOKEN_RE.finditer(published))
    source = "edgeprop_address" if "#" in published else ""
    empty = {
        "unit_number": "",
        "unit_floor": "",
        "unit_stack": "",
        "unit_number_source": source,
    }
    if not matches:
        return {
            **empty,
            "unit_number_status": "unparseable" if "#" in published else "not_present",
        }
    if len(matches) != 1:
        return {**empty, "unit_number_status": "unparseable"}

    match = matches[0]
    floor = match.group("floor")
    stack = match.group("stack")
    if any(marker in floor.upper() + stack.upper() for marker in ("X", "*", "?")):
        return {**empty, "unit_number_status": "masked"}
    return {
        "unit_number": match.group(0),
        "unit_floor": floor,
        "unit_stack": stack,
        "unit_number_status": "exact",
        "unit_number_source": "edgeprop_address",
    }


def street_without_unit(address: str) -> str:
    """Remove one recognised trailing unit token while preserving source text."""
    published = clean_line(address)
    match = UNIT_TOKEN_RE.search(published)
    if match and match.end() == len(published) and len(list(UNIT_TOKEN_RE.finditer(published))) == 1:
        return published[:match.start()].strip()
    return published


def parse_number(value: str) -> float | None:
    text = clean_line(value).replace(",", "")
    if not MONEY_RE.match(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_sale_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(clean_line(value).title(), "%d %b %Y")
    except ValueError:
        return None


def title_date(value: str) -> str:
    parsed = parse_sale_date(value)
    if parsed is None:
        return clean_line(value)
    return f"{parsed.day} {parsed.strftime('%b')} {parsed.year}"


def detail_value(text: str, label: str) -> str:
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line and line != ":"]
    for idx, line in enumerate(lines):
        if line.lower() != label.lower():
            continue
        for value in lines[idx + 1: idx + 7]:
            if value and value != ":":
                return value
    return ""


def project_context(text: str, fallback_name: str = "") -> tuple[str, str, str, str, str]:
    project_name = detail_value(text, "Project Name") or fallback_name
    property_type = detail_value(text, "Property Type") or "Condominium/Apartment"
    tenure = detail_value(text, "Tenure")
    district_area = detail_value(text, "District/Planning Area")
    district = ""
    planning_area = ""
    match = re.search(r"D\s*(\d{1,2})\s*/\s*(.+)", district_area, flags=re.I)
    if match:
        district = match.group(1).zfill(2)
        planning_area = match.group(2).strip().upper()
    return project_name, planning_area, district, property_type, tenure


def advertised_sales_count(text: str) -> int | None:
    match = SALES_COUNT_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def fetch_text(url: str, timeout: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> str:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def discover_project_links(html_text: str, base_url: str = BASE_URL) -> list[ProjectLink]:
    parser = LinkTextParser()
    parser.feed(html_text)

    seen: set[str] = set()
    projects: list[ProjectLink] = []
    for href, text in parser.links:
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != urlparse(base_url).netloc:
            continue
        if not DETAIL_PATH_RE.match(parsed.path):
            continue
        slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        if slug in {"all", ""} or url in seen:
            continue
        seen.add(url)
        projects.append(ProjectLink(name=text.strip() or slug.replace("-", " ").title(), url=url, slug=slug))
    return projects


def parse_transaction_text(
    text: str,
    project_name: str = "",
    planning_area: str = "",
    postal_district: str = "",
    property_type: str = "",
    tenure: str = "",
) -> list[dict[str, Any]]:
    """Parse the rendered EdgeProp condo/apartment sales-transaction table."""
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if not DATE_RE.match(lines[i]):
            i += 1
            continue
        if i + 8 >= len(lines):
            break

        sale_date = lines[i]
        area_sqft = parse_number(lines[i + 1])
        bedrooms = lines[i + 2]
        unit_price_psf = parse_number(lines[i + 3])
        price = parse_number(lines[i + 4])
        sale_type = lines[i + 5]
        address = lines[i + 6]
        type_of_area = lines[i + 7]
        purchaser_address = lines[i + 8]
        source_idx = i + 9

        combined = re.match(r"^(Land|Strata)\s+(.+)$", type_of_area, flags=re.I)
        if combined and purchaser_address.upper() in {"URA", "EDGEPROP", "REALIS"}:
            type_of_area = combined.group(1)
            purchaser_address = combined.group(2).strip()
            source_idx = i + 8

        if source_idx >= len(lines):
            break
        source = lines[source_idx]
        parsed_date = parse_sale_date(sale_date)
        valid = (
            parsed_date is not None
            and area_sqft is not None
            and unit_price_psf is not None
            and price is not None
            and source.upper() in {"URA", "EDGEPROP", "REALIS"}
        )
        if not valid:
            i += 1
            continue

        unit = extract_unit_number(address)
        rows.append({
            "Project": project_name,
            "planning_area": planning_area.upper().strip(),
            "Postal District": str(postal_district).zfill(2) if postal_district else "",
            "Date of Sale": title_date(sale_date),
            "Address": address,
            "Street": street_without_unit(address),
            **unit,
            "Bedrooms": bedrooms,
            "Unit Price ($psf)": int(unit_price_psf) if unit_price_psf.is_integer() else unit_price_psf,
            "Price ($)": int(price) if price.is_integer() else price,
            "Type": property_type,
            "Tenure": tenure,
            "Sale Type": sale_type,
            "Area (sqft)": int(area_sqft) if area_sqft.is_integer() else area_sqft,
            "Area (sqm)": round(area_sqft * SQFT_TO_SQM, 3),
            "Type of Area": type_of_area,
            "Purchaser Address": purchaser_address,
            "Source": source,
        })
        i = source_idx + 1
    return rows


def read_project_links(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"name", "url", "slug"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"ERROR: {path} missing columns: {sorted(missing)}")
        return [row for row in reader if row.get("url")]


def read_completed_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "source_url" not in (reader.fieldnames or []):
            return set()
        return {row["source_url"] for row in reader if row.get("source_url")}


def append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def write_unit_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the complete unit-level schema, including unavailable-unit rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNIT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in UNIT_FIELDS})


def append_unit_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Append unit rows, refusing to mix this schema with a legacy CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    if not write_header:
        with path.open(newline="", encoding="utf-8") as handle:
            existing_fields = next(csv.reader(handle), [])
        if existing_fields != UNIT_FIELDS:
            raise SystemExit(
                f"ERROR: {path} does not use the EdgeProp unit schema; "
                "choose a new --unit-out path"
            )
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNIT_FIELDS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in UNIT_FIELDS})


def unit_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in ("exact", "masked", "not_present", "unparseable")}
    for row in rows:
        status = str(row.get("unit_number_status", "unparseable"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def append_attempt(
    path: Path,
    project: dict[str, str],
    result: ScrapeResult,
    status: str,
    error: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ATTEMPT_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "source_url": project.get("url", ""),
            "source_slug": project.get("slug", ""),
            "name": project.get("name", ""),
            "row_count": len(result.rows),
            "pages_scraped": result.pages_scraped,
            "oldest_date": result.oldest_date,
            "status": status,
            "error": error[:500],
        })


def row_date(row: dict[str, Any]) -> datetime | None:
    return parse_sale_date(str(row.get("Date of Sale", "")))


def first_row_key(rows: list[dict[str, Any]]) -> tuple[Any, ...] | None:
    if not rows:
        return None
    row = rows[0]
    return (
        row.get("Date of Sale"),
        row.get("Address"),
        row.get("Unit Price ($psf)"),
        row.get("Price ($)"),
        row.get("Area (sqft)"),
        row.get("Bedrooms"),
    )


async def wait_for_table_change(
    page,
    old_key: tuple[Any, ...] | None,
    project_name: str,
    planning_area: str,
    district: str,
    property_type: str,
    tenure: str,
) -> bool:
    if old_key is None:
        await page.wait_for_timeout(1000)
        return True
    for _ in range(24):
        await page.wait_for_timeout(250)
        try:
            text = await page.locator("body").inner_text(timeout=5_000)
        except Exception:
            continue
        rows = parse_transaction_text(
            text,
            project_name=project_name,
            planning_area=planning_area,
            postal_district=district,
            property_type=property_type,
            tenure=tenure,
        )
        if rows and first_row_key(rows) != old_key:
            return True
    return False


async def scrape_project(
    page,
    project: dict[str, str],
    wait_ms: int,
    max_pages: int,
    timeout_ms: int,
    from_year: int,
) -> ScrapeResult:
    url = project["url"]
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.get_by_text("Sales Transaction of", exact=False).first.wait_for(timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    if wait_ms:
        await page.wait_for_timeout(wait_ms)

    # The sales table (and its "ALL SALES TRANSACTIONS (n)" counter) lazy-loads
    # only once #SalesTransaction scrolls into view; without this, the counter
    # reads (0) and the retry loop below bails with zero rows.
    section = page.locator("#SalesTransaction")
    if await section.count():
        try:
            await section.first.scroll_into_view_if_needed(timeout=10_000)
        except Exception:
            pass
        await page.wait_for_timeout(1_000)

    text = await page.locator("body").inner_text(timeout=15_000)
    project_name, planning_area, district, property_type, tenure = project_context(text, project.get("name", ""))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    oldest: datetime | None = None
    pages_scraped = 0

    while pages_scraped < max_pages:
        text = ""
        page_rows: list[dict[str, Any]] = []
        for attempt in range(20):
            text = await page.locator("body").inner_text(timeout=15_000)
            page_rows = parse_transaction_text(
                text,
                project_name=project_name,
                planning_area=planning_area,
                postal_district=district,
                property_type=property_type,
                tenure=tenure,
            )
            if page_rows:
                break
            # Only trust an advertised (0) once the lazy-loaded counter has had
            # time to settle after the scroll above (~3s in).
            if advertised_sales_count(text) == 0 and attempt >= 6:
                break
            if attempt % 4 == 3 and await section.count():
                try:
                    await section.first.scroll_into_view_if_needed(timeout=5_000)
                except Exception:
                    pass
            await page.wait_for_timeout(500)
        pages_scraped += 1
        if not page_rows:
            break

        page_dates = [date for date in (row_date(row) for row in page_rows) if date is not None]
        if page_dates:
            page_oldest = min(page_dates)
            oldest = page_oldest if oldest is None else min(oldest, page_oldest)

        for row in page_rows:
            parsed = row_date(row)
            if parsed is None or parsed.year < from_year:
                continue
            key = (
                row.get("Date of Sale"),
                row.get("Address"),
                row.get("Unit Price ($psf)"),
                row.get("Price ($)"),
                row.get("Area (sqft)"),
                row.get("Bedrooms"),
            )
            if key in seen:
                continue
            seen.add(key)
            row["source_quality"] = "not_clean"
            row["source_url"] = url
            row["source_slug"] = project.get("slug", "")
            rows.append(row)

        if page_dates and max(date.year for date in page_dates) < from_year:
            break

        next_button = page.locator(
            "#SalesTransaction .ant-pagination-next:not(.ant-pagination-disabled) button"
        )
        if await next_button.count() == 0:
            break
        old_key = first_row_key(page_rows)
        advanced = False
        for _ in range(3):
            try:
                await page.locator(
                    "#SalesTransaction .ant-pagination-next:not(.ant-pagination-disabled) button"
                ).first.click(timeout=5_000)
                advanced = await wait_for_table_change(
                    page,
                    old_key,
                    project_name,
                    planning_area,
                    district,
                    property_type,
                    tenure,
                )
                if advanced:
                    break
            except Exception:
                await page.wait_for_timeout(1000)
        if not advanced:
            break

    oldest_date = oldest.strftime("%Y-%m-%d") if oldest else ""
    return ScrapeResult(rows=rows, pages_scraped=pages_scraped, oldest_date=oldest_date)


async def scrape(args: argparse.Namespace) -> None:
    if async_playwright is None:
        raise SystemExit("pip install playwright --break-system-packages")
    projects = read_project_links(Path(args.input))
    if args.match:
        needle = args.match.lower()
        projects = [
            project for project in projects
            if needle in project.get("name", "").lower() or needle in project.get("slug", "").lower()
        ]
    if args.start:
        projects = projects[args.start:]
    if args.limit:
        projects = projects[: args.limit]

    out = Path(args.out)
    unit_out = Path(args.unit_out) if args.unit_out else None
    log_path = Path(args.log) if args.log else out.with_name(f"{out.stem}_attempts.csv")
    completed = read_completed_urls(out) if args.resume else set()
    completed |= read_completed_urls(log_path) if args.resume_attempts else set()
    if completed:
        projects = [project for project in projects if project["url"] not in completed]

    if not projects:
        print("Nothing to scrape.")
        return

    storage_state = None
    if args.storage_state:
        storage_path = Path(args.storage_state)
        if not storage_path.is_file():
            raise SystemExit(f"ERROR: --storage-state does not exist: {storage_path}")
        storage_state = str(storage_path)

    total_rows = 0
    all_status_counts = unit_status_counts([])
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1600},
            user_agent=DEFAULT_USER_AGENT,
            storage_state=storage_state,
        )
        page = await context.new_page()
        for idx, project in enumerate(projects, 1):
            error = ""
            status = "ok"
            result = ScrapeResult(rows=[])
            try:
                result = await scrape_project(
                    page,
                    project,
                    wait_ms=args.wait_ms,
                    max_pages=args.max_pages,
                    timeout_ms=args.timeout_ms,
                    from_year=args.from_year,
                )
            except Exception as exc:
                error = str(exc)
                status = "error"
                print(f"[{idx}/{len(projects)}] ERROR {project['url']}: {exc}", file=sys.stderr, flush=True)
            if result.rows:
                append_rows(out, result.rows)
                if unit_out:
                    append_unit_rows(unit_out, result.rows)
                total_rows += len(result.rows)
                project_counts = unit_status_counts(result.rows)
                for status, count in project_counts.items():
                    all_status_counts[status] += count
            append_attempt(log_path, project, result, status, error)
            print(
                f"[{idx}/{len(projects)}] {project.get('name', '')}: "
                f"{len(result.rows)} rows, {result.pages_scraped} pages",
                flush=True,
            )
            if args.delay:
                await page.wait_for_timeout(int(args.delay * 1000))
        await browser.close()

    print(f"Wrote {total_rows} transaction rows to {out}", flush=True)
    if unit_out:
        summary = ", ".join(f"{status}={count}" for status, count in all_status_counts.items())
        print(f"Wrote unit provenance rows to {unit_out} ({summary})", flush=True)


def write_project_csv(path: Path, projects: list[ProjectLink]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "url", "slug"])
        writer.writeheader()
        for project in projects:
            writer.writerow(project.__dict__)


def discover(args: argparse.Namespace) -> None:
    html_text = fetch_text(args.index_url, timeout=args.timeout)
    projects = discover_project_links(html_text)
    if args.match:
        needle = args.match.lower()
        projects = [
            project for project in projects
            if needle in project.name.lower() or needle in project.slug.lower()
        ]
    write_project_csv(Path(args.out), projects)
    print(f"Wrote {len(projects)} condo/apartment project links to {args.out}")


def parse_saved_transactions(args: argparse.Namespace) -> None:
    """Parse saved/copied EdgeProp tables without requiring a live browser."""
    sources: list[str] = []
    for path_text in args.html_file or []:
        path = Path(path_text)
        sources.append(text_from_html(path.read_text(encoding="utf-8", errors="replace")))
    for path_text in args.text_file or []:
        path = Path(path_text)
        sources.append(path.read_text(encoding="utf-8", errors="replace"))
    if not sources:
        raise SystemExit("ERROR: provide --html-file or --text-file")

    rows: list[dict[str, Any]] = []
    for text in sources:
        context = project_context(text, args.project_name)
        project_name = context[0] or args.project_name
        planning_area = context[1] or args.planning_area
        district = context[2] or args.postal_district
        property_type = detail_value(text, "Property Type") or args.property_type
        tenure = context[4] or args.tenure
        parsed = parse_transaction_text(
            text,
            project_name=project_name,
            planning_area=planning_area,
            postal_district=district,
            property_type=property_type,
            tenure=tenure,
        )
        for row in parsed:
            row["source_quality"] = "not_clean"
            row["source_url"] = args.source_url
            row["source_slug"] = args.source_slug
            # Local paths are deliberately not written into the output. They
            # may reveal workstation details and are not source provenance.
        rows.extend(parsed)

    write_unit_rows(Path(args.out), rows)
    counts = unit_status_counts(rows)
    summary = ", ".join(f"{status}={count}" for status, count in counts.items())
    print(f"Wrote {len(rows)} unit provenance rows to {args.out} ({summary})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract EdgeProp condo/apartment transactions with source-safe unit provenance",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    discover_parser = sub.add_parser("discover", help="Discover project links from /condo-apartment/all")
    discover_parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    discover_parser.add_argument("--out", default=DEFAULT_PROJECTS)
    discover_parser.add_argument("--match", help="Filter discovered links by name/slug substring")
    discover_parser.add_argument("--timeout", type=int, default=30)
    discover_parser.set_defaults(func=discover)

    scrape_parser = sub.add_parser("scrape", help="Scrape discovered project transaction rows")
    scrape_parser.add_argument("--input", default=DEFAULT_PROJECTS, help="CSV with name,url,slug columns")
    scrape_parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Output CSV")
    scrape_parser.add_argument(
        "--unit-out",
        help=(
            "Optional dedicated unit-level CSV. Exact unit_number values are "
            "written only when published; all rows retain unit_number_status."
        ),
    )
    scrape_parser.add_argument(
        "--storage-state",
        help=(
            "Playwright storage-state JSON for an EdgeProp session you are "
            "authorised to use; keep credentials outside the repository"
        ),
    )
    scrape_parser.add_argument("--from-year", type=int, default=2019, help="Keep transactions from this year onward")
    scrape_parser.add_argument("--limit", type=int, help="Maximum project pages to scrape")
    scrape_parser.add_argument("--start", type=int, default=0, help="Zero-based project offset")
    scrape_parser.add_argument("--match", help="Filter project name/slug substring")
    scrape_parser.add_argument("--resume", action="store_true", help="Skip source_url values already in --out")
    scrape_parser.add_argument(
        "--resume-attempts",
        action="store_true",
        help="Also skip source_url values already recorded in --log",
    )
    scrape_parser.add_argument("--log", help="Project attempt log CSV")
    scrape_parser.add_argument("--wait-ms", type=int, default=1200, help="Post-render wait per page")
    scrape_parser.add_argument("--timeout-ms", type=int, default=30_000, help="Navigation timeout per page")
    scrape_parser.add_argument("--max-pages", type=int, default=250, help="Maximum Sales-table pages per project")
    scrape_parser.add_argument("--delay", type=float, default=0.10, help="Delay between projects in seconds")
    scrape_parser.add_argument("--headed", action="store_true")
    scrape_parser.set_defaults(func=lambda args: asyncio.run(scrape(args)))

    parse_parser = sub.add_parser(
        "parse-transactions",
        help="Parse authorised saved HTML/copied transaction tables with unit provenance",
    )
    parse_parser.add_argument("--html-file", nargs="*", help="Saved EdgeProp project HTML page(s)")
    parse_parser.add_argument("--text-file", nargs="*", help="Copied EdgeProp sales-table text file(s)")
    parse_parser.add_argument("--project-name", default="")
    parse_parser.add_argument("--planning-area", default="")
    parse_parser.add_argument("--postal-district", default="")
    parse_parser.add_argument("--property-type", default="Condominium/Apartment")
    parse_parser.add_argument("--tenure", default="")
    parse_parser.add_argument("--source-url", default="")
    parse_parser.add_argument("--source-slug", default="")
    parse_parser.add_argument("--out", required=True, help="Unit-level CSV output")
    parse_parser.set_defaults(func=parse_saved_transactions)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
