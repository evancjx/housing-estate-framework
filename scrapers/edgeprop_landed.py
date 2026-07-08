#!/usr/bin/env python3
"""
EdgeProp landed directory scraper
=================================

Scrapes public landed-project metadata from EdgeProp and parses
EdgeProp-style sales tables from pages or copied text the user is
authorised to access.

The public EdgeProp project pages do not expose Pro-only transaction
rows to unauthenticated HTTP clients. This script therefore has two
separate paths:

1. Discover/detail scrape public project pages from /landed-house/all.
2. Parse transaction rows from a saved authenticated HTML page or a
   copied text file, then write a URA-ingestor-compatible CSV.

Examples:
    # Build a landed-project index from the public directory.
    python scrapers/edgeprop_landed.py discover \\
        --out data/raw/edgeprop/edgeprop_landed_projects.csv

    # Fetch public detail metadata for projects in the discovered index.
    python scrapers/edgeprop_landed.py details \\
        --input data/raw/edgeprop/edgeprop_landed_projects.csv \\
        --out data/raw/edgeprop/edgeprop_landed_project_details.csv \\
        --limit 25

    # Parse transaction rows from copied/saved EdgeProp text.
    python scrapers/edgeprop_landed.py parse-transactions \\
        --text-file data/edgeprop_raw/kembangan.txt \\
        --project-name "KEMBANGAN ESTATE" \\
        --planning-area BEDOK \\
        --postal-district 14 \\
        --out data/raw/ura/edgeprop_kembangan.csv
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import re
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://www.edgeprop.sg"
DEFAULT_INDEX_URL = f"{BASE_URL}/landed-house/all"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
SQFT_TO_SQM = 0.09290304

DATE_RE = re.compile(r"^\d{1,2}\s+[A-Z]{3}\s+\d{4}$", re.I)
MONEY_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
DETAIL_PATH_RE = re.compile(r"^/landed-house/[^/?#]+$")


@dataclass(frozen=True)
class ProjectLink:
    name: str
    url: str
    slug: str


class LinkTextParser(HTMLParser):
    """Collect links and their visible text from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self._active_href: str | None = None
        self._active_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {k.lower(): v for k, v in attrs}
        href = attr_map.get("href")
        if href:
            self._active_href = href
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._active_href:
            text = " ".join(" ".join(self._active_text).split())
            self.links.append((self._active_href, text))
            self._active_href = None
            self._active_text = []


class TextExtractor(HTMLParser):
    """Extract visible-ish text blocks from HTML without external deps."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(self.parts)


def fetch_text(url: str, timeout: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> str:
    """Fetch a URL as text using stdlib urllib."""
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"})
    with urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def discover_project_links(html_text: str, base_url: str = BASE_URL) -> list[ProjectLink]:
    """Return unique /landed-house/{slug} project links from an EdgeProp index page."""
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
        name = text.strip() or slug.replace("-", " ").title()
        projects.append(ProjectLink(name=name, url=url, slug=slug))
    return projects


def extract_next_data(html_text: str) -> dict[str, Any]:
    """Extract Next.js __NEXT_DATA__ from a page, if present."""
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.S | re.I,
    )
    if not match:
        return {}
    raw = html_lib.unescape(match.group(1)).strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def page_props(next_data: dict[str, Any]) -> dict[str, Any]:
    props = next_data.get("props")
    if not isinstance(props, dict):
        return {}
    value = props.get("pageProps")
    return value if isinstance(value, dict) else {}


def scalar(value: Any) -> str:
    """Flatten common JSON scalar/list values into a compact CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, list):
        return "; ".join(scalar(v) for v in value if scalar(v))
    if isinstance(value, dict):
        for key in ("display", "name", "label", "value", "text"):
            if key in value:
                return scalar(value[key])
    return ""


def first_value(data: Any, keys: tuple[str, ...]) -> Any:
    """Depth-first search for the first non-empty value under any key."""
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if value not in (None, "", [], {}):
                return value
        for value in data.values():
            found = first_value(value, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(data, list):
        for item in data:
            found = first_value(item, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def list_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return sum(list_count(v) for v in value.values())
    return 0


def parse_detail_page(html_text: str, url: str = "") -> dict[str, Any]:
    """Extract public project metadata from an EdgeProp landed detail page."""
    data = extract_next_data(html_text)
    props = page_props(data)
    project_detail = props.get("projectDetail") if isinstance(props.get("projectDetail"), dict) else {}
    project_info_root = props.get("projectInfo") if isinstance(props.get("projectInfo"), dict) else {}
    project_info = (
        project_info_root.get("data")
        if isinstance(project_info_root.get("data"), dict)
        else project_info_root
    )
    score = project_info.get("score") if isinstance(project_info.get("score"), dict) else {}
    sales_data = props.get("salesTransactionData", {})

    street_numbers = project_info.get("street_numbers") or project_info.get("streetNumbers") or []
    if isinstance(street_numbers, str):
        addresses = [street_numbers]
    elif isinstance(street_numbers, list):
        addresses = [scalar(v) for v in street_numbers if scalar(v)]
    else:
        addresses = []

    return {
        "url": url,
        "project_name": scalar(
            project_detail.get("name")
            or project_info.get("name")
            or first_value(props, ("projectName", "project_name"))
        ),
        "alias": scalar(project_detail.get("alias") or project_info.get("alias")),
        "project_id": scalar(project_detail.get("id") or project_info.get("id")),
        "ext_id": scalar(project_detail.get("ext_id") or project_detail.get("extId")),
        "planning_area": scalar(project_detail.get("planning_area") or project_info.get("planning_area")),
        "district": scalar(project_info.get("district") or project_detail.get("district")),
        "property_type": scalar(project_info.get("property_type") or project_detail.get("property_type")),
        "tenure": scalar(project_info.get("tenure") or project_detail.get("tenure")),
        "lat": scalar(project_detail.get("lat") or project_info.get("lat")),
        "lon": scalar(project_detail.get("lon") or project_info.get("lon")),
        "indicative_price_psf": scalar(score.get("indicative_price")),
        "indicative_price_range": scalar(score.get("indicative_price_range")),
        "address_count": len(addresses),
        "addresses": "; ".join(addresses),
        "public_sales_record_count": list_count(sales_data),
        "has_public_next_data": bool(data),
    }


def clean_line(line: str) -> str:
    line = html_lib.unescape(line)
    line = line.replace("\xa0", " ").replace("\t", " ")
    return " ".join(line.split()).strip()


def text_from_html(html_text: str) -> str:
    extractor = TextExtractor()
    extractor.feed(html_text)
    return extractor.text()


def parse_number(value: str) -> float | None:
    value = clean_line(value).replace(",", "")
    if not MONEY_RE.match(value):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def title_date(value: str) -> str:
    parts = clean_line(value).split()
    if len(parts) != 3:
        return clean_line(value)
    return f"{int(parts[0])} {parts[1].title()} {parts[2]}"


def parse_transaction_text(
    text: str,
    project_name: str = "",
    planning_area: str = "",
    postal_district: str = "",
) -> list[dict[str, Any]]:
    """
    Parse EdgeProp copied/rendered sales-table text.

    The parser intentionally looks for row starts by date and then consumes the
    fixed EdgeProp sales-table column order.
    """
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if not DATE_RE.match(lines[i]):
            i += 1
            continue
        if i + 9 >= len(lines):
            break

        date = lines[i]
        address = lines[i + 1]
        unit_price_psf = parse_number(lines[i + 2])
        price = parse_number(lines[i + 3])
        property_type = lines[i + 4]
        tenure = lines[i + 5]
        sale_type = lines[i + 6]
        area_sqft = parse_number(lines[i + 7])
        type_of_area = lines[i + 8]
        purchaser_address = lines[i + 9]
        source_idx = i + 10

        if "\t" in type_of_area:
            parts = [part.strip() for part in type_of_area.split("\t") if part.strip()]
            if len(parts) >= 2:
                type_of_area = parts[0]
                purchaser_address = parts[1]
                source_idx = i + 9
        else:
            combined = re.match(r"^(Land|Strata)\s+(.+)$", type_of_area, flags=re.I)
            if combined and purchaser_address.upper() in {"URA", "EDGEPROP", "REALIS"}:
                type_of_area = combined.group(1)
                purchaser_address = combined.group(2).strip()
                source_idx = i + 9

        if source_idx >= len(lines):
            break
        source = lines[source_idx]

        valid = (
            unit_price_psf is not None
            and price is not None
            and area_sqft is not None
            and source.upper() in {"URA", "EDGEPROP", "REALIS"}
        )
        if not valid:
            i += 1
            continue

        rows.append({
            "Project": project_name,
            "planning_area": planning_area.upper().strip(),
            "Postal District": str(postal_district).zfill(2) if postal_district else "",
            "Date of Sale": title_date(date),
            "Street": address,
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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_urls_from_csv(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "url" not in (reader.fieldnames or []):
            raise SystemExit(f"ERROR: {path} must contain a 'url' column")
        return [row["url"] for row in reader if row.get("url")]


def cmd_discover(args: argparse.Namespace) -> None:
    html_text = fetch_text(args.index_url, timeout=args.timeout)
    projects = discover_project_links(html_text)
    if args.match:
        needle = args.match.lower()
        projects = [
            project for project in projects
            if needle in project.name.lower() or needle in project.slug.lower()
        ]
    rows = [project.__dict__ for project in projects]
    write_csv(Path(args.out), rows, fieldnames=["name", "url", "slug"])
    print(f"Wrote {len(rows)} landed project links to {args.out}")


def cmd_details(args: argparse.Namespace) -> None:
    if args.urls:
        urls = args.urls
    elif args.input:
        urls = read_urls_from_csv(Path(args.input))
    else:
        raise SystemExit("ERROR: provide --input or --urls")

    if args.limit:
        urls = urls[: args.limit]

    rows: list[dict[str, Any]] = []
    for idx, url in enumerate(urls, 1):
        print(f"[{idx}/{len(urls)}] {url}", file=sys.stderr)
        html_text = fetch_text(url, timeout=args.timeout)
        rows.append(parse_detail_page(html_text, url=url))
        if args.delay and idx < len(urls):
            time.sleep(args.delay)

    fields = [
        "url", "project_name", "alias", "project_id", "ext_id",
        "planning_area", "district", "property_type", "tenure", "lat", "lon",
        "indicative_price_psf", "indicative_price_range",
        "address_count", "addresses", "public_sales_record_count", "has_public_next_data",
    ]
    write_csv(Path(args.out), rows, fieldnames=fields)
    print(f"Wrote {len(rows)} project detail rows to {args.out}")


def cmd_scrape(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    links_path = out_dir / "edgeprop_landed_projects.csv"
    details_path = out_dir / "edgeprop_landed_project_details.csv"

    discover_args = argparse.Namespace(
        index_url=args.index_url,
        timeout=args.timeout,
        match=args.match,
        out=str(links_path),
    )
    cmd_discover(discover_args)

    detail_args = argparse.Namespace(
        input=str(links_path),
        urls=None,
        out=str(details_path),
        limit=args.limit,
        delay=args.delay,
        timeout=args.timeout,
    )
    cmd_details(detail_args)


def cmd_parse_transactions(args: argparse.Namespace) -> None:
    parts: list[str] = []
    for path_text in args.html_file or []:
        path = Path(path_text)
        parts.append(text_from_html(path.read_text(encoding="utf-8", errors="replace")))
    for path_text in args.text_file or []:
        path = Path(path_text)
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    if not parts:
        raise SystemExit("ERROR: provide --html-file or --text-file")

    rows: list[dict[str, Any]] = []
    for text in parts:
        rows.extend(parse_transaction_text(
            text,
            project_name=args.project_name,
            planning_area=args.planning_area,
            postal_district=args.postal_district,
        ))

    fields = [
        "Project", "planning_area", "Postal District", "Date of Sale", "Street",
        "Unit Price ($psf)", "Price ($)", "Type", "Tenure", "Sale Type",
        "Area (sqft)", "Area (sqm)", "Type of Area", "Purchaser Address", "Source",
    ]
    write_csv(Path(args.out), rows, fieldnames=fields)
    print(f"Wrote {len(rows)} transaction rows to {args.out}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape public EdgeProp landed metadata and parse landed transaction tables",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Discover project links from /landed-house/all")
    discover.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    discover.add_argument("--out", default="data/raw/edgeprop/edgeprop_landed_projects.csv")
    discover.add_argument("--match", help="Filter discovered links by name/slug substring")
    discover.add_argument("--timeout", type=int, default=30)
    discover.set_defaults(func=cmd_discover)

    details = sub.add_parser("details", help="Fetch public detail metadata for project URLs")
    details.add_argument("--input", help="CSV with a url column, usually discover output")
    details.add_argument("--urls", nargs="*", help="Specific project detail URLs")
    details.add_argument("--out", default="data/raw/edgeprop/edgeprop_landed_project_details.csv")
    details.add_argument("--limit", type=int, help="Maximum number of URLs to fetch")
    details.add_argument("--delay", type=float, default=1.0, help="Delay between detail requests")
    details.add_argument("--timeout", type=int, default=30)
    details.set_defaults(func=cmd_details)

    scrape = sub.add_parser("scrape", help="Run discover and details together")
    scrape.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    scrape.add_argument("--out-dir", default="data/raw/edgeprop/edgeprop_landed")
    scrape.add_argument("--match", help="Filter discovered links by name/slug substring")
    scrape.add_argument("--limit", type=int, help="Maximum detail pages to fetch")
    scrape.add_argument("--delay", type=float, default=1.0)
    scrape.add_argument("--timeout", type=int, default=30)
    scrape.set_defaults(func=cmd_scrape)

    tx = sub.add_parser(
        "parse-transactions",
        help="Parse EdgeProp sales-table rows from saved HTML or copied text",
    )
    tx.add_argument("--html-file", nargs="*", help="Saved EdgeProp project HTML page(s)")
    tx.add_argument("--text-file", nargs="*", help="Copied sales-table text file(s)")
    tx.add_argument("--project-name", default="")
    tx.add_argument("--planning-area", default="")
    tx.add_argument("--postal-district", default="")
    tx.add_argument("--out", required=True)
    tx.set_defaults(func=cmd_parse_transactions)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
