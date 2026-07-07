#!/usr/bin/env python3
"""
Playwright scraper for public EdgeProp landed transaction tables.

This only reads rows visible in an unauthenticated browser session. EdgeProp
still masks unit numbers/addresses and gates unit-number search behind login/Pro.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from pathlib import Path
from typing import Any

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("pip install playwright --break-system-packages")

try:
    from scrapers.edgeprop_landed import (
        DEFAULT_USER_AGENT,
        parse_transaction_text,
        write_csv,
    )
except ModuleNotFoundError:
    from edgeprop_landed import DEFAULT_USER_AGENT, parse_transaction_text, write_csv


FIELDS = [
    "Project", "planning_area", "Postal District", "Date of Sale", "Street",
    "Unit Price ($psf)", "Price ($)", "Type", "Tenure", "Sale Type",
    "Area (sqft)", "Area (sqm)", "Type of Area", "Purchaser Address", "Source",
    "source_quality", "source_url", "source_slug",
]

ATTEMPT_FIELDS = ["source_url", "source_slug", "name", "row_count", "status", "error"]


def clean_line(line: str) -> str:
    return " ".join(line.replace("\xa0", " ").split()).strip()


def detail_value(text: str, label: str) -> str:
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line and line != ":"]
    for idx, line in enumerate(lines):
        if line.lower() != label.lower():
            continue
        for value in lines[idx + 1: idx + 6]:
            if value and value != ":":
                return value
    return ""


def project_context(text: str, fallback_name: str = "") -> tuple[str, str, str]:
    project_name = detail_value(text, "Project Name") or fallback_name
    district_area = detail_value(text, "District/Planning Area")
    district = ""
    planning_area = ""
    match = re.search(r"D\s*(\d{1,2})\s*/\s*(.+)", district_area, flags=re.I)
    if match:
        district = match.group(1).zfill(2)
        planning_area = match.group(2).strip().upper()
    return project_name, planning_area, district


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


def read_attempted_urls(path: Path) -> set[str]:
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


def append_attempt(path: Path, project: dict[str, str], row_count: int, status: str, error: str = "") -> None:
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
            "row_count": row_count,
            "status": status,
            "error": error[:500],
        })


async def scrape_project(
    page,
    project: dict[str, str],
    wait_ms: int,
    max_pages: int,
    timeout_ms: int,
) -> list[dict[str, Any]]:
    url = project["url"]
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.get_by_text("Sales Transaction of", exact=False).first.wait_for(timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    if wait_ms:
        await page.wait_for_timeout(wait_ms)
    text = await page.locator("body").inner_text(timeout=15_000)
    project_name, planning_area, postal_district = project_context(text, project.get("name", ""))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    pages_scraped = 0
    while pages_scraped < max_pages:
        text = await page.locator("body").inner_text(timeout=15_000)
        page_rows = parse_transaction_text(
            text,
            project_name=project_name,
            planning_area=planning_area,
            postal_district=postal_district,
        )
        for row in page_rows:
            key = (
                row.get("Date of Sale"),
                row.get("Street"),
                row.get("Unit Price ($psf)"),
                row.get("Price ($)"),
                row.get("Area (sqft)"),
                row.get("Type"),
            )
            if key not in seen:
                seen.add(key)
                rows.append(row)

        pages_scraped += 1
        next_button = page.locator(
            "#SalesTransaction .ant-pagination-next:not(.ant-pagination-disabled) button"
        )
        if await next_button.count() == 0:
            break
        try:
            await next_button.first.click(timeout=5_000)
            await page.wait_for_timeout(max(800, wait_ms // 2))
        except Exception:
            break

    for row in rows:
        row["source_quality"] = "not_clean"
        row["source_url"] = url
        row["source_slug"] = project.get("slug", "")
    return rows


async def run(args: argparse.Namespace) -> None:
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
    log_path = Path(args.log) if args.log else out.with_name(f"{out.stem}_attempts.csv")
    completed = read_completed_urls(out) if args.resume else set()
    completed |= read_attempted_urls(log_path) if args.resume_attempts else set()
    if completed:
        projects = [project for project in projects if project["url"] not in completed]

    if not projects:
        print("Nothing to scrape.")
        return

    total_rows = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1600},
            user_agent=DEFAULT_USER_AGENT,
        )
        page = await context.new_page()
        for idx, project in enumerate(projects, 1):
            error = ""
            status = "ok"
            try:
                rows = await scrape_project(
                    page,
                    project,
                    args.wait_ms,
                    args.max_pages,
                    args.timeout_ms,
                )
            except Exception as exc:
                error = str(exc)
                status = "error"
                print(f"[{idx}/{len(projects)}] ERROR {project['url']}: {exc}", file=sys.stderr, flush=True)
                rows = []
            if rows:
                append_rows(out, rows)
                total_rows += len(rows)
            append_attempt(log_path, project, len(rows), status, error)
            print(f"[{idx}/{len(projects)}] {project.get('name', '')}: {len(rows)} rows", flush=True)
            if args.delay:
                await page.wait_for_timeout(int(args.delay * 1000))
        await browser.close()

    print(f"Wrote {total_rows} transaction rows to {out}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape public EdgeProp landed transaction rows with Playwright",
    )
    parser.add_argument(
        "--input",
        default="data/edgeprop_playwright_probe/edgeprop_landed_projects_playwright.csv",
        help="CSV with name,url,slug columns",
    )
    parser.add_argument(
        "--out",
        default="data/edgeprop_landed_transactions_playwright_not_clean.csv",
        help="Output CSV",
    )
    parser.add_argument("--limit", type=int, help="Maximum project pages to scrape")
    parser.add_argument("--start", type=int, default=0, help="Zero-based project offset")
    parser.add_argument("--match", help="Filter project name/slug substring")
    parser.add_argument("--resume", action="store_true", help="Skip source_url values already in --out")
    parser.add_argument(
        "--resume-attempts",
        action="store_true",
        help="Also skip source_url values already recorded in --log",
    )
    parser.add_argument("--log", help="Project attempt log CSV")
    parser.add_argument("--wait-ms", type=int, default=2500, help="Post-render wait per page")
    parser.add_argument("--timeout-ms", type=int, default=30_000, help="Navigation timeout per page")
    parser.add_argument("--max-pages", type=int, default=200, help="Maximum Sales-table pages per project")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between pages in seconds")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
