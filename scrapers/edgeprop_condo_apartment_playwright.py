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
    python3 scrapers/edgeprop_condo_apartment_playwright.py scrape \
        --generation-manifest data/runs/edgeprop-condo/run.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import html
import inspect
import io
import os
import re
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

# Direct script execution exposes ``scrapers/`` but not necessarily the
# repository root. Bootstrap it before importing the shared generation API.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sg_estate import scrape_generation
from sg_estate.contracts import ContractError

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
DEFAULT_GENERATION_OUTPUT = "edgeprop_condo_apartment_transactions.csv"
GENERATION_SOURCE = "edgeprop_condo_apartment"
ARTIFACT_SCHEMA = "edgeprop-condo-unit.v1"

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
    completion_reason: str = ""
    source_advertised_count: int | None = None


@dataclass(frozen=True)
class GenerationRun:
    manifest_path: Path
    root: Path
    scope: dict[str, object]
    projects: tuple[dict[str, str], ...]
    output_path: Path
    unit_output_path: Path | None


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
        return [
            {
                "name": clean_line(row.get("name", "")),
                "url": clean_line(row.get("url", "")),
                "slug": clean_line(row.get("slug", "")),
            }
            for row in reader
            if row.get("url")
        ]


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
    write_csv_atomic(path, UNIT_FIELDS, rows)


def write_csv_atomic(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """Replace one CSV atomically after rendering its complete contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def read_csv_exact(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    """Read one CSV only when its header is exactly the requested schema."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_fields:
            raise ContractError(
                f"{path} has unexpected CSV header; expected {expected_fields!r}, "
                f"got {reader.fieldnames!r}"
            )
        return list(reader)


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
    source_advertised_count = advertised_sales_count(text)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    oldest: datetime | None = None
    pages_scraped = 0
    completion_reason = ""

    while pages_scraped < max_pages:
        text = ""
        page_rows: list[dict[str, Any]] = []
        for attempt in range(20):
            text = await page.locator("body").inner_text(timeout=15_000)
            advertised_count = advertised_sales_count(text)
            if advertised_count is not None:
                source_advertised_count = advertised_count
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
            completion_reason = "zero_rows" if not rows else "pagination_rows_missing"
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

        if page_dates and min(date.year for date in page_dates) < from_year:
            completion_reason = "from_year_boundary"
            break

        next_button = page.locator(
            "#SalesTransaction .ant-pagination-next:not(.ant-pagination-disabled) button"
        )
        if await next_button.count() == 0:
            completion_reason = "terminal_pagination"
            break
        if pages_scraped >= max_pages:
            completion_reason = "max_pages_exhausted"
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
            completion_reason = "pagination_click_failure"
            break

    oldest_date = oldest.strftime("%Y-%m-%d") if oldest else ""
    if not completion_reason:
        completion_reason = "max_pages_exhausted"
    return ScrapeResult(
        rows=rows,
        pages_scraped=pages_scraped,
        oldest_date=oldest_date,
        completion_reason=completion_reason,
        source_advertised_count=source_advertised_count,
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def partition_id_for_url(source_url: str) -> str:
    """Return a stable identifier-safe partition key without altering evidence."""
    return f"url-{sha256_bytes(source_url.encode('utf-8'))}"


def read_project_catalog(path: Path) -> tuple[list[dict[str, str]], str]:
    """Read project rows and hash the exact catalog bytes used for the batch."""
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"ERROR: cannot read project catalog {path}: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    required = {"name", "url", "slug"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"ERROR: {path} missing columns: {sorted(missing)}")
    projects = [
        {
            "name": clean_line(row.get("name", "")),
            "url": clean_line(row.get("url", "")),
            "slug": clean_line(row.get("slug", "")),
        }
        for row in reader
        if row.get("url")
    ]
    return projects, sha256_bytes(raw)


def select_project_batch(
    projects: list[dict[str, str]], args: argparse.Namespace
) -> list[dict[str, str]]:
    selected = projects
    if args.match:
        needle = args.match.lower()
        selected = [
            project
            for project in selected
            if needle in project.get("name", "").lower()
            or needle in project.get("slug", "").lower()
        ]
    if args.start:
        selected = selected[args.start :]
    if args.limit:
        selected = selected[: args.limit]
    return [
        {**project, "partition_id": partition_id_for_url(project["url"])}
        for project in selected
    ]


def requested_scope(
    *,
    catalog_path: Path,
    catalog_sha256: str,
    projects: list[dict[str, str]],
    from_year: int,
    max_pages: int,
    access_mode: str,
) -> dict[str, object]:
    return {
        "project_catalog": {
            "name": catalog_path.name,
            "sha256": catalog_sha256,
        },
        "partitions": [
            {
                "partition_id": project["partition_id"],
                "name": project["name"],
                "source_url": project["url"],
                "source_slug": project["slug"],
            }
            for project in projects
        ],
        "parameters": {
            "access_mode": access_mode,
            "artifact_schema": ARTIFACT_SCHEMA,
            "from_year": from_year,
            "max_pages": max_pages,
        },
    }


def generation_local_path(root: Path, value: str, *, option: str) -> Path:
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else root / supplied
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(
            f"ERROR: {option} must resolve inside the generation root {root}"
        ) from exc
    return resolved


def prepare_generation(args: argparse.Namespace) -> GenerationRun:
    if getattr(args, "resume_attempts", False):
        raise SystemExit(
            "ERROR: --resume-attempts is unsupported: legacy attempt CSVs are "
            "diagnostics only and are never resume evidence"
        )
    if args.start < 0:
        raise SystemExit("ERROR: --start must be non-negative")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("ERROR: --limit must be positive")
    if args.max_pages <= 0:
        raise SystemExit("ERROR: --max-pages must be positive")
    if args.from_year <= 0:
        raise SystemExit("ERROR: --from-year must be positive")

    storage_state = None
    if args.storage_state:
        storage_path = Path(args.storage_state)
        if not storage_path.is_file():
            raise SystemExit(f"ERROR: --storage-state does not exist: {storage_path}")
        storage_state = str(storage_path.resolve())
    args.storage_state = storage_state

    catalog_path = Path(args.input)
    projects, catalog_sha256 = read_project_catalog(catalog_path)
    projects = select_project_batch(projects, args)
    if not projects:
        raise SystemExit("ERROR: the post-filter project batch is empty")
    scope = requested_scope(
        catalog_path=catalog_path,
        catalog_sha256=catalog_sha256,
        projects=projects,
        from_year=args.from_year,
        max_pages=args.max_pages,
        access_mode="authorized" if storage_state else "public",
    )

    manifest_path = Path(args.generation_manifest).resolve()
    root = manifest_path.parent
    root.mkdir(parents=True, exist_ok=True)
    output_path = generation_local_path(root, args.out, option="--out")
    unit_output_path = (
        generation_local_path(root, args.unit_out, option="--unit-out")
        if args.unit_out
        else None
    )
    reserved = {manifest_path}
    if output_path in reserved:
        raise SystemExit("ERROR: --out must not be the generation manifest")
    if unit_output_path in reserved or unit_output_path == output_path:
        raise SystemExit("ERROR: --unit-out must be distinct from the manifest and --out")
    artifacts_root = (root / "artifacts").resolve()
    try:
        artifacts_root.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(
            "ERROR: reserved artifacts/ directory resolves outside the generation root"
        ) from exc
    for label, candidate in (("--out", output_path), ("--unit-out", unit_output_path)):
        if candidate is None:
            continue
        try:
            candidate.relative_to(artifacts_root)
        except ValueError:
            pass
        else:
            raise SystemExit(f"ERROR: {label} must not use the reserved artifacts/ directory")

    if args.log:
        log_path = Path(args.log).resolve()
        if log_path in {manifest_path, output_path, unit_output_path}:
            raise SystemExit(
                "ERROR: --log must not overwrite generation evidence or a candidate"
            )
        try:
            log_path.relative_to(artifacts_root)
        except ValueError:
            pass
        else:
            raise SystemExit("ERROR: --log must not use the reserved artifacts/ directory")
        args.log = str(log_path)

    if manifest_path.exists():
        manifest = scrape_generation.load_generation(
            manifest_path,
            expected_source=GENERATION_SOURCE,
            expected_scope=scope,
            expected_generation_id=args.generation_id,
        )
    else:
        manifest = scrape_generation.new_generation(
            GENERATION_SOURCE,
            scope,
            generation_id=args.generation_id,
            now=utc_now(),
        )
        scrape_generation.write_generation(manifest_path, manifest)

    normalized_projects = {
        project["partition_id"]: project for project in projects
    }
    ordered_projects = tuple(
        normalized_projects[str(partition["partition_id"])]
        for partition in manifest["requested_scope"]["partitions"]
    )
    return GenerationRun(
        manifest_path=manifest_path,
        root=root,
        scope=scope,
        projects=ordered_projects,
        output_path=output_path,
        unit_output_path=unit_output_path,
    )


def validate_unit_rows(
    rows: list[dict[str, Any]], project: dict[str, str], *, source: str
) -> None:
    if not rows:
        raise ContractError(f"{source} has no transaction rows")
    for index, row in enumerate(rows):
        if row.get("source_url") != project["url"]:
            raise ContractError(
                f"{source} row {index} source_url does not match {project['url']!r}"
            )
        if row.get("source_slug") != project["slug"]:
            raise ContractError(
                f"{source} row {index} source_slug does not match exact source slug "
                f"{project['slug']!r}"
            )


def validate_unit_artifact(
    path: Path,
    project: dict[str, str],
    *,
    expected_count: int | None = None,
) -> list[dict[str, str]]:
    rows = read_csv_exact(path, UNIT_FIELDS)
    validate_unit_rows(rows, project, source=str(path))
    if expected_count is not None and len(rows) != expected_count:
        raise ContractError(
            f"{path} row count mismatch: expected {expected_count}, got {len(rows)}"
        )
    return rows


def attempt_observations(result: ScrapeResult) -> dict[str, object]:
    return {
        "completion_reason": result.completion_reason,
        "oldest_date": result.oldest_date or None,
        "pages_scraped": result.pages_scraped,
        "parsed_row_count": len(result.rows),
        "source_advertised_count": result.source_advertised_count,
    }


def append_diagnostic_attempt(
    path_text: str | None,
    project: dict[str, str],
    result: ScrapeResult,
    status: str,
    error: str,
) -> None:
    if not path_text:
        return
    try:
        append_attempt(Path(path_text), project, result, status, error)
    except OSError as exc:
        print(f"WARNING: could not append diagnostic log {path_text}: {exc}", file=sys.stderr)


def new_attempt_id() -> str:
    return f"attempt-{uuid.uuid4().hex}"


async def invoke_scrape_project(
    scrape_project_fn: Callable[..., Any],
    page: Any,
    project: dict[str, str],
    args: argparse.Namespace,
) -> ScrapeResult:
    result = scrape_project_fn(
        page,
        project,
        wait_ms=args.wait_ms,
        max_pages=args.max_pages,
        timeout_ms=args.timeout_ms,
        from_year=args.from_year,
    )
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, ScrapeResult):
        raise TypeError("scrape_project must return ScrapeResult")
    return result


def record_failed_attempt(
    run: GenerationRun,
    project: dict[str, str],
    result: ScrapeResult,
    *,
    started_at: datetime,
    retrieved_at: datetime | None,
    error_code: str,
    error_message: str,
) -> None:
    completed_at = utc_now()
    scrape_generation.record_attempt(
        run.manifest_path,
        project["partition_id"],
        method="playwright",
        status="failed",
        started_at=started_at,
        retrieved_at=retrieved_at,
        completed_at=completed_at,
        source_reported_row_count=result.source_advertised_count,
        error_code=error_code,
        error_message=error_message or error_code,
        observations=attempt_observations(result),
        attempt_id=new_attempt_id(),
        now=completed_at,
    )


async def scrape_pending_projects(
    run: GenerationRun,
    args: argparse.Namespace,
    page: Any,
    *,
    scrape_project_fn: Callable[..., Any] = scrape_project,
) -> None:
    successful = scrape_generation.successful_partition_ids(run.manifest_path)
    pending_projects = [
        project for project in run.projects if project["partition_id"] not in successful
    ]
    for idx, project in enumerate(pending_projects, 1):
        started_at = utc_now()
        result = ScrapeResult(rows=[])
        retrieved_at: datetime | None = None
        try:
            result = await invoke_scrape_project(scrape_project_fn, page, project, args)
            retrieved_at = utc_now()
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            record_failed_attempt(
                run,
                project,
                result,
                started_at=started_at,
                retrieved_at=None,
                error_code="scrape_exception",
                error_message=message,
            )
            append_diagnostic_attempt(args.log, project, result, "failed", message)
            print(
                f"[{idx}/{len(pending_projects)}] ERROR {project['url']}: {message}",
                file=sys.stderr,
                flush=True,
            )
            continue

        if not result.rows:
            reason = "zero_rows"
            message = (
                "project returned no rows; EdgeProp empty results cannot be "
                "selected as complete"
            )
            record_failed_attempt(
                run,
                project,
                result,
                started_at=started_at,
                retrieved_at=retrieved_at,
                error_code=reason,
                error_message=message,
            )
            append_diagnostic_attempt(args.log, project, result, "failed", message)
            print(
                f"[{idx}/{len(pending_projects)}] {project['name']}: 0 rows (pending)",
                flush=True,
            )
            continue

        if result.completion_reason not in {"terminal_pagination", "from_year_boundary"}:
            reason = result.completion_reason or "completion_unproven"
            message = (
                f"partial rows were not selected because completion was {reason!r}"
            )
            record_failed_attempt(
                run,
                project,
                result,
                started_at=started_at,
                retrieved_at=retrieved_at,
                error_code=reason,
                error_message=message,
            )
            append_diagnostic_attempt(args.log, project, result, "failed", message)
            print(
                f"[{idx}/{len(pending_projects)}] {project['name']}: "
                f"{len(result.rows)} partial rows ({reason}; pending)",
                flush=True,
            )
            continue

        attempt_id = new_attempt_id()
        artifact_path = (
            run.root / "artifacts" / project["partition_id"] / f"{attempt_id}.csv"
        )
        try:
            if artifact_path.exists():
                raise ContractError(f"refusing to overwrite attempt artifact {artifact_path}")
            validate_unit_rows(result.rows, project, source="scraped project rows")
            write_csv_atomic(artifact_path, UNIT_FIELDS, result.rows)
            validate_unit_artifact(
                artifact_path, project, expected_count=len(result.rows)
            )
        except Exception as exc:
            artifact_path.unlink(missing_ok=True)
            message = str(exc) or type(exc).__name__
            record_failed_attempt(
                run,
                project,
                result,
                started_at=started_at,
                retrieved_at=retrieved_at,
                error_code="artifact_validation_failed",
                error_message=message,
            )
            append_diagnostic_attempt(args.log, project, result, "failed", message)
            print(
                f"[{idx}/{len(pending_projects)}] ERROR {project['url']}: {message}",
                file=sys.stderr,
                flush=True,
            )
            continue

        completed_at = utc_now()
        reported_count = (
            result.source_advertised_count
            if result.source_advertised_count == len(result.rows)
            else None
        )
        scrape_generation.record_attempt(
            run.manifest_path,
            project["partition_id"],
            method="playwright",
            status="succeeded",
            started_at=started_at,
            retrieved_at=retrieved_at,
            completed_at=completed_at,
            artifact_path=artifact_path,
            source_reported_row_count=reported_count,
            observations=attempt_observations(result),
            attempt_id=attempt_id,
            now=completed_at,
        )
        append_diagnostic_attempt(args.log, project, result, "succeeded", "")
        print(
            f"[{idx}/{len(pending_projects)}] {project['name']}: "
            f"{len(result.rows)} rows, {result.pages_scraped} pages "
            f"({result.completion_reason})",
            flush=True,
        )
        if args.delay:
            await page.wait_for_timeout(int(args.delay * 1000))


def validate_candidate(
    path: Path,
    fieldnames: list[str],
    *,
    expected_count: int,
    projects_by_url: dict[str, dict[str, str]],
    expected_counts: dict[str, int],
) -> list[dict[str, str]]:
    rows = read_csv_exact(path, fieldnames)
    if len(rows) != expected_count:
        raise ContractError(
            f"{path} row count mismatch: expected {expected_count}, got {len(rows)}"
        )
    actual_counts = {source_url: 0 for source_url in expected_counts}
    for index, row in enumerate(rows):
        source_url = row.get("source_url", "")
        project = projects_by_url.get(source_url)
        if project is None:
            raise ContractError(f"{path} row {index} has out-of-scope source_url {source_url!r}")
        if row.get("source_slug") != project["slug"]:
            raise ContractError(
                f"{path} row {index} source_slug does not match exact source slug "
                f"{project['slug']!r}"
            )
        actual_counts[source_url] += 1
    if actual_counts != expected_counts:
        raise ContractError(
            f"{path} per-project row counts do not match selected artifacts"
        )
    return rows


def reconcile_generation(run: GenerationRun) -> dict[str, object]:
    manifest = scrape_generation.load_generation(
        run.manifest_path,
        expected_source=GENERATION_SOURCE,
        expected_scope=run.scope,
    )
    pending = scrape_generation.pending_partition_ids(
        manifest, manifest_path=run.manifest_path
    )
    if pending:
        raise ContractError(
            f"cannot reconcile generation while {len(pending)} requested partitions remain pending"
        )

    selected = scrape_generation.selected_artifacts(
        manifest, manifest_path=run.manifest_path
    )
    if len(selected) != len(run.projects):
        raise ContractError("every condo partition must select one positive-row artifact")
    projects_by_partition = {
        project["partition_id"]: project for project in run.projects
    }
    projects_by_url = {project["url"]: project for project in run.projects}
    expected_counts: dict[str, int] = {}
    unit_rows: list[dict[str, str]] = []
    for artifact in selected:
        project = projects_by_partition.get(artifact.partition_id)
        if project is None:
            raise ContractError(
                f"selected artifact partition is outside requested batch: {artifact.partition_id}"
            )
        rows = validate_unit_artifact(
            artifact.path, project, expected_count=artifact.row_count
        )
        unit_rows.extend(rows)
        expected_counts[project["url"]] = artifact.row_count
    expected_count = sum(artifact.row_count for artifact in selected)
    if len(unit_rows) != expected_count:
        raise ContractError("selected artifact rows were not assembled exactly once")

    output_relative = run.output_path.relative_to(run.root.resolve()).as_posix()
    if manifest["status"] == "complete":
        output = manifest["output"]
        assert isinstance(output, dict)
        if output["relative_path"] != output_relative:
            raise ContractError(
                "complete generation is bound to a different --out candidate path"
            )
        validate_candidate(
            run.output_path,
            FIELDS,
            expected_count=expected_count,
            projects_by_url=projects_by_url,
            expected_counts=expected_counts,
        )
        if run.unit_output_path:
            write_csv_atomic(run.unit_output_path, UNIT_FIELDS, unit_rows)
            validate_candidate(
                run.unit_output_path,
                UNIT_FIELDS,
                expected_count=expected_count,
                projects_by_url=projects_by_url,
                expected_counts=expected_counts,
            )
        return manifest

    if run.unit_output_path:
        write_csv_atomic(run.unit_output_path, UNIT_FIELDS, unit_rows)
        validate_candidate(
            run.unit_output_path,
            UNIT_FIELDS,
            expected_count=expected_count,
            projects_by_url=projects_by_url,
            expected_counts=expected_counts,
        )
    legacy_rows = [
        {field: row.get(field, "") for field in FIELDS} for row in unit_rows
    ]
    write_csv_atomic(run.output_path, FIELDS, legacy_rows)
    validate_candidate(
        run.output_path,
        FIELDS,
        expected_count=expected_count,
        projects_by_url=projects_by_url,
        expected_counts=expected_counts,
    )
    return scrape_generation.finalize_generation(
        run.manifest_path, run.output_path, now=utc_now()
    )


async def scrape(
    args: argparse.Namespace,
    *,
    page: Any | None = None,
    scrape_project_fn: Callable[..., Any] = scrape_project,
) -> None:
    """Run or resume one exact generation; injected pages keep tests offline."""
    run = prepare_generation(args)
    manifest = scrape_generation.load_generation(
        run.manifest_path,
        expected_source=GENERATION_SOURCE,
        expected_scope=run.scope,
        expected_generation_id=args.generation_id,
    )
    pending = scrape_generation.pending_partition_ids(
        manifest, manifest_path=run.manifest_path
    )

    if pending and page is not None:
        await scrape_pending_projects(
            run, args, page, scrape_project_fn=scrape_project_fn
        )
    elif pending:
        if async_playwright is None:
            raise SystemExit("pip install playwright --break-system-packages")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=not args.headed)
            try:
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 1600},
                    user_agent=DEFAULT_USER_AGENT,
                    storage_state=args.storage_state,
                )
                live_page = await context.new_page()
                await scrape_pending_projects(
                    run, args, live_page, scrape_project_fn=scrape_project_fn
                )
            finally:
                await browser.close()

    pending = scrape_generation.pending_partition_ids(run.manifest_path)
    if pending:
        print(
            f"ERROR: generation remains open with {len(pending)} pending partition(s); "
            "no candidate was replaced",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)

    complete = reconcile_generation(run)
    print(
        f"Finalized generation {complete['generation_id']} with "
        f"{complete['output']['row_count']} rows at {run.output_path}",
        flush=True,
    )
    if run.unit_output_path:
        print(f"Wrote full unit candidate to {run.unit_output_path}", flush=True)


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
    scrape_parser.add_argument(
        "--generation-manifest",
        required=True,
        help=(
            "Run-scoped JSON manifest. Its parent is the generation root; "
            "partition artifacts and candidates never leave that root."
        ),
    )
    scrape_parser.add_argument(
        "--generation-id",
        help=(
            "Optional identifier for a new generation or exact expected ID "
            "when resuming"
        ),
    )
    scrape_parser.add_argument(
        "--out",
        default=DEFAULT_GENERATION_OUTPUT,
        help=(
            "Legacy-schema candidate path, relative to the generation root "
            f"(default: {DEFAULT_GENERATION_OUTPUT})"
        ),
    )
    scrape_parser.add_argument(
        "--unit-out",
        help=(
            "Optional full-unit candidate path relative to the generation root. "
            "Exact unit_number values are written only when published."
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
    scrape_parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Compatibility flag; an existing exact manifest always resumes "
            "only selected, validated partitions"
        ),
    )
    scrape_parser.add_argument(
        "--resume-attempts",
        action="store_true",
        help=(
            "Rejected legacy option; attempt CSVs are diagnostics and never "
            "resume evidence"
        ),
    )
    scrape_parser.add_argument(
        "--log", help="Optional append-only human diagnostic CSV (never resume evidence)"
    )
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
