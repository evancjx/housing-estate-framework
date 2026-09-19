#!/usr/bin/env python3
"""
Playwright scraper for public EdgeProp landed transaction tables.

This only reads rows visible in an unauthenticated browser session. EdgeProp
still masks unit numbers/addresses and gates unit-number search behind login/Pro.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import os
import posixpath
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError
    async_playwright = None

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sg_estate import scrape_generation
from sg_estate.contracts import ContractError

try:
    from scrapers.edgeprop_landed import (
        DEFAULT_USER_AGENT,
        parse_transaction_text,
    )
except ModuleNotFoundError:
    from edgeprop_landed import DEFAULT_USER_AGENT, parse_transaction_text


FIELDS = [
    "Project", "planning_area", "Postal District", "Date of Sale", "Street",
    "Unit Price ($psf)", "Price ($)", "Type", "Tenure", "Sale Type",
    "Area (sqft)", "Area (sqm)", "Type of Area", "Purchaser Address", "Source",
    "source_quality", "source_url", "source_slug",
]

SOURCE = "edgeprop_landed"
ARTIFACT_SCHEMA = "edgeprop-landed-transaction.v1"
DEFAULT_CANDIDATE_NAME = "candidate.csv"
TERMINAL_COMPLETION = "terminal_page"
SALES_COUNT_RE = re.compile(r"ALL SALES TRANSACTIONS?\s*\((\d+)\)", re.I)

ATTEMPT_FIELDS = ["source_url", "source_slug", "name", "row_count", "status", "error"]


@dataclass
class ScrapeResult:
    """Structured evidence returned by one project scrape.

    Rows are usable only when ``completion_reason`` is ``terminal_page``. A
    populated partial result remains useful diagnostic evidence, but never
    becomes a selected generation artifact.
    """

    rows: list[dict[str, Any]]
    pages_scraped: int = 0
    completion_reason: str = ""
    source_reported_row_count: int | None = None
    error_message: str = ""

    @property
    def complete(self) -> bool:
        return self.completion_reason == TERMINAL_COMPLETION


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


def advertised_sales_count(text: str) -> int | None:
    """Return EdgeProp's rendered transaction count when it is present."""

    match = SALES_COUNT_RE.search(text)
    return int(match.group(1)) if match else None


def canonical_project_url(url: str) -> str:
    """Canonicalize a project URL solely for stable partition identity."""

    if not isinstance(url, str) or not url or url != url.strip():
        raise ValueError("project URL must be a non-empty string without surrounding whitespace")
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"project URL must be absolute HTTP(S): {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("project URL must not contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"project URL has an invalid port: {url!r}") from exc

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"

    raw_path = parsed.path or "/"
    path = posixpath.normpath(raw_path)
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and raw_path.endswith("/"):
        path = path.rstrip("/")
    path = re.sub(
        r"%[0-9A-Fa-f]{2}",
        lambda match: match.group(0).upper(),
        path,
    )
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def partition_id_for_url(url: str) -> str:
    """Return an identifier-safe, collision-resistant ID derived from a URL."""

    digest = hashlib.sha256(canonical_project_url(url).encode("utf-8")).hexdigest()
    return f"url-{digest}"


# Short aliases keep the identity helpers discoverable for callers and tests.
canonicalize_url = canonical_project_url
project_partition_id = partition_id_for_url


def read_project_links(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"name", "url", "slug"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"ERROR: {path} missing columns: {sorted(missing)}")
        return [row for row in reader if row.get("url")]


def select_projects(
    projects: Sequence[dict[str, str]],
    *,
    match: str | None = None,
    start: int = 0,
    limit: int | None = None,
) -> list[dict[str, str]]:
    """Resolve CLI slicing to the exact project batch captured by a manifest."""

    if start < 0:
        raise ValueError("--start must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    selected = list(projects)
    if match:
        needle = match.lower()
        selected = [
            project
            for project in selected
            if needle in project.get("name", "").lower()
            or needle in project.get("slug", "").lower()
        ]
    selected = selected[start:]
    if limit is not None:
        selected = selected[:limit]
    return selected


def requested_scope(
    catalog_path: Path,
    projects: Sequence[dict[str, str]],
    *,
    max_pages: int,
) -> dict[str, object]:
    """Build the exact shared-contract scope for one landed batch."""

    if max_pages <= 0:
        raise ValueError("--max-pages must be positive")
    if not projects:
        raise ValueError("the resolved project batch is empty")
    partitions = [
        {
            "partition_id": partition_id_for_url(project.get("url", "")),
            "name": project.get("name", ""),
            "source_url": project.get("url", ""),
            "source_slug": project.get("slug", ""),
        }
        for project in projects
    ]
    return {
        "project_catalog": {
            "name": catalog_path.name,
            "sha256": scrape_generation.sha256_file(catalog_path),
        },
        "partitions": partitions,
        "parameters": {
            "artifact_schema": ARTIFACT_SCHEMA,
            "max_pages": max_pages,
        },
    }


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


def read_validated_artifact(
    path: Path,
    *,
    source_url: str,
    source_slug: str,
) -> list[dict[str, str]]:
    """Read one exact landed artifact and reconcile its row provenance."""

    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot open landed artifact {path}: {exc}") from exc
    with handle:
        try:
            reader = csv.DictReader(handle)
            if reader.fieldnames != FIELDS:
                raise ContractError(
                    f"landed artifact {path} must have the exact FIELDS header"
                )
            rows = list(reader)
        except (csv.Error, UnicodeDecodeError) as exc:
            raise ContractError(f"cannot parse landed artifact {path}: {exc}") from exc
    if not rows:
        raise ContractError(f"landed artifact {path} must contain positive rows")
    for index, row in enumerate(rows, start=2):
        if None in row or set(row) != set(FIELDS) or any(value is None for value in row.values()):
            raise ContractError(f"landed artifact {path}:{index} has an invalid row shape")
        if row["source_url"] != source_url:
            raise ContractError(
                f"landed artifact {path}:{index} source_url does not match its partition"
            )
        if row["source_slug"] != source_slug:
            raise ContractError(
                f"landed artifact {path}:{index} source_slug does not match its partition"
            )
    return rows


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    validator: Callable[[Path], object],
    replace: bool = True,
) -> Path:
    """Write exact ``FIELDS`` bytes and replace the destination only if valid."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in FIELDS})
            handle.flush()
            os.fsync(handle.fileno())
        validator(temporary)
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise ContractError(f"immutable artifact already exists: {path}") from exc
            temporary.unlink()
        _fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def write_partition_artifact(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    project: Mapping[str, str],
) -> Path:
    """Atomically publish one positive, provenance-exact project artifact."""

    source_url = project.get("url", "")
    source_slug = project.get("slug", "")
    if not rows:
        raise ContractError("a successful landed partition requires positive rows")
    for index, row in enumerate(rows, start=1):
        if row.get("source_url") != source_url:
            raise ContractError(
                f"project result row {index} source_url does not match {source_url!r}"
            )
        if row.get("source_slug") != source_slug:
            raise ContractError(
                f"project result row {index} source_slug does not match {source_slug!r}"
            )
    return _atomic_write_csv(
        path,
        rows,
        validator=lambda candidate: read_validated_artifact(
            candidate,
            source_url=source_url,
            source_slug=source_slug,
        ),
        replace=False,
    )


def _first_row_key(rows: Sequence[Mapping[str, Any]]) -> tuple[Any, ...] | None:
    if not rows:
        return None
    row = rows[0]
    return (
        row.get("Date of Sale"),
        row.get("Street"),
        row.get("Unit Price ($psf)"),
        row.get("Price ($)"),
        row.get("Area (sqft)"),
        row.get("Type"),
    )


async def _wait_for_table_change(
    page,
    old_key: tuple[Any, ...] | None,
    *,
    project_name: str,
    planning_area: str,
    postal_district: str,
    wait_ms: int,
) -> bool:
    """Verify that a successful click actually advanced the rendered table."""

    if wait_ms:
        await page.wait_for_timeout(max(250, wait_ms // 2))
    for _ in range(24):
        try:
            text = await page.locator("body").inner_text(timeout=5_000)
            rows = parse_transaction_text(
                text,
                project_name=project_name,
                planning_area=planning_area,
                postal_district=postal_district,
            )
            if rows and _first_row_key(rows) != old_key:
                return True
        except Exception:
            pass
        await page.wait_for_timeout(250)
    return False


async def scrape_project(
    page,
    project: dict[str, str],
    wait_ms: int,
    max_pages: int,
    timeout_ms: int,
) -> ScrapeResult:
    """Scrape one project, succeeding only at a disabled terminal next control."""

    if max_pages <= 0:
        raise ValueError("max_pages must be positive")
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
    source_count = advertised_sales_count(text)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    pages_scraped = 0
    completion_reason = ""
    error_message = ""
    while True:
        text = await page.locator("body").inner_text(timeout=15_000)
        rendered_count = advertised_sales_count(text)
        if rendered_count is not None:
            source_count = rendered_count
        page_rows = parse_transaction_text(
            text,
            project_name=project_name,
            planning_area=planning_area,
            postal_district=postal_district,
        )
        pages_scraped += 1
        if not page_rows:
            completion_reason = "zero_rows" if pages_scraped == 1 else "pagination_parse_failed"
            error_message = "rendered transaction page contained no parseable rows"
            break

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
                row["source_quality"] = "not_clean"
                row["source_url"] = url
                row["source_slug"] = project.get("slug", "")
                rows.append(row)

        next_button = page.locator(
            "#SalesTransaction .ant-pagination-next:not(.ant-pagination-disabled) button"
        )
        if await next_button.count() == 0:
            terminal = page.locator(
                "#SalesTransaction .ant-pagination-next.ant-pagination-disabled"
            )
            if await terminal.count() > 0:
                completion_reason = TERMINAL_COMPLETION
            else:
                completion_reason = "pagination_state_missing"
                error_message = "could not prove a terminal next-page state"
            break
        if pages_scraped >= max_pages:
            completion_reason = "max_pages_exhausted"
            error_message = f"enabled next page remained after max_pages={max_pages}"
            break

        old_key = _first_row_key(page_rows)
        try:
            await next_button.first.click(timeout=5_000)
        except Exception as exc:
            completion_reason = "pagination_click_failed"
            error_message = str(exc) or "next-page click failed"
            break
        changed = await _wait_for_table_change(
            page,
            old_key,
            project_name=project_name,
            planning_area=planning_area,
            postal_district=postal_district,
            wait_ms=wait_ms,
        )
        if not changed:
            completion_reason = "pagination_did_not_advance"
            error_message = "transaction rows did not change after next-page click"
            break

    if (
        completion_reason == TERMINAL_COMPLETION
        and source_count is not None
        and source_count != len(rows)
    ):
        completion_reason = "source_count_mismatch"
        error_message = (
            f"EdgeProp reported {source_count} rows but {len(rows)} unique rows were parsed"
        )
    return ScrapeResult(
        rows=rows,
        pages_scraped=pages_scraped,
        completion_reason=completion_reason,
        source_reported_row_count=source_count,
        error_message=error_message,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _error_code(result: ScrapeResult | None, exc: Exception | None) -> str:
    if result is not None and not result.complete:
        return result.completion_reason or "incomplete_project"
    if exc is not None:
        return "project_scrape_error"
    assert result is not None
    return result.completion_reason or "incomplete_project"


def _generation_local_path(root: Path, requested: str | Path, *, label: str) -> Path:
    path = Path(requested)
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ContractError(f"{label} must be inside the generation root {root}") from exc
    return resolved


def _partition_descriptors(scope: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    partitions = scope["partitions"]
    assert isinstance(partitions, list)
    return {str(value["partition_id"]): value for value in partitions}


def merge_generation_candidate(
    manifest_path: Path,
    candidate_path: Path,
) -> Path:
    """Validate and deterministically merge every selected artifact once."""

    manifest = scrape_generation.load_generation(
        manifest_path,
        expected_source=SOURCE,
    )
    pending = scrape_generation.pending_partition_ids(
        manifest,
        manifest_path=manifest_path,
    )
    if pending:
        raise ContractError(
            "cannot build a landed candidate while partitions remain pending: "
            + ", ".join(sorted(pending))
        )
    descriptors = _partition_descriptors(manifest["requested_scope"])
    artifacts = scrape_generation.selected_artifacts(manifest_path)
    requested_ids = [
        str(value["partition_id"])
        for value in manifest["requested_scope"]["partitions"]
    ]
    artifact_ids = [artifact.partition_id for artifact in artifacts]
    if artifact_ids != requested_ids or len(set(artifact_ids)) != len(requested_ids):
        raise ContractError("selected landed artifacts do not reconcile one-to-one with scope")

    merged: list[dict[str, str]] = []
    expected_total = 0
    for artifact in artifacts:
        descriptor = descriptors[artifact.partition_id]
        rows = read_validated_artifact(
            artifact.path,
            source_url=str(descriptor["source_url"]),
            source_slug=str(descriptor["source_slug"]),
        )
        if len(rows) != artifact.row_count:
            raise ContractError(
                f"landed artifact row count changed for {artifact.partition_id}"
            )
        expected_total += artifact.row_count
        merged.extend(rows)
    if len(merged) != expected_total or Counter(
        (row["source_url"], row["source_slug"]) for row in merged
    ) != Counter(
        {
            (
                str(descriptors[artifact.partition_id]["source_url"]),
                str(descriptors[artifact.partition_id]["source_slug"]),
            ): artifact.row_count
            for artifact in artifacts
        }
    ):
        raise ContractError("landed candidate provenance/count reconciliation failed")

    def validate_candidate(path: Path) -> None:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != FIELDS:
                raise ContractError("landed candidate must have the exact FIELDS header")
            candidate_rows = list(reader)
        if len(candidate_rows) != expected_total:
            raise ContractError("landed candidate row count does not reconcile")

    return _atomic_write_csv(candidate_path, merged, validator=validate_candidate)


build_candidate = merge_generation_candidate


@asynccontextmanager
async def _playwright_page(args: argparse.Namespace) -> AsyncIterator[Any]:
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is unavailable; install it with "
            "`python3 -m pip install playwright` and install Chromium"
        )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.headed)
        try:
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1600},
                user_agent=DEFAULT_USER_AGENT,
            )
            yield await context.new_page()
        finally:
            await browser.close()


def _coerce_result(value: Any) -> ScrapeResult:
    if isinstance(value, ScrapeResult):
        return value
    if isinstance(value, Mapping):
        return ScrapeResult(
            rows=list(value.get("rows", [])),
            pages_scraped=int(value.get("pages_scraped", 0)),
            completion_reason=str(value.get("completion_reason", "")),
            source_reported_row_count=value.get("source_reported_row_count"),
            error_message=str(value.get("error_message", "")),
        )
    raise TypeError("project scraper must return ScrapeResult or a compatible mapping")


async def _invoke_project_scraper(
    scraper: Callable[..., Any],
    page: Any,
    project: dict[str, str],
    args: argparse.Namespace,
) -> ScrapeResult:
    value = scraper(
        page,
        project,
        wait_ms=args.wait_ms,
        max_pages=args.max_pages,
        timeout_ms=args.timeout_ms,
    )
    if inspect.isawaitable(value):
        value = await value
    return _coerce_result(value)


async def run(
    args: argparse.Namespace,
    *,
    project_scraper: Callable[..., Any] = scrape_project,
    page_factory: Callable[[argparse.Namespace], Any] | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, object]:
    """Run or resume one exact generation; return its validated manifest."""

    if getattr(args, "resume_attempts", False):
        raise ValueError(
            "--resume-attempts is unsafe and unsupported; only selected successful "
            "generation partitions are completion evidence"
        )
    input_path = Path(args.input)
    all_projects = read_project_links(input_path)
    projects = select_projects(
        all_projects,
        match=getattr(args, "match", None),
        start=getattr(args, "start", 0),
        limit=getattr(args, "limit", None),
    )
    scope = requested_scope(input_path, projects, max_pages=args.max_pages)
    manifest_path = Path(args.generation_manifest)
    generation_root = manifest_path.resolve().parent
    candidate_path = _generation_local_path(
        generation_root,
        getattr(args, "out", DEFAULT_CANDIDATE_NAME),
        label="--out",
    )
    if candidate_path == manifest_path.resolve():
        raise ContractError("--out must not overwrite the generation manifest")
    artifacts_root = (generation_root / "artifacts").resolve()
    try:
        candidate_path.relative_to(artifacts_root)
    except ValueError:
        pass
    else:
        raise ContractError("--out must not overlap partition artifacts")
    log_value = getattr(args, "log", None)
    log_path = Path(log_value) if log_value else None
    if log_path is not None:
        resolved_log = log_path.resolve()
        if resolved_log in {manifest_path.resolve(), candidate_path}:
            raise ContractError("--log must not overwrite generation evidence or candidate")
        try:
            resolved_log.relative_to(artifacts_root)
        except ValueError:
            pass
        else:
            raise ContractError("--log must not overlap partition artifacts")

    if manifest_path.exists():
        manifest = scrape_generation.load_generation(
            manifest_path,
            expected_source=SOURCE,
            expected_scope=scope,
            expected_generation_id=getattr(args, "generation_id", None),
        )
    else:
        manifest = scrape_generation.new_generation(
            SOURCE,
            scope,
            generation_id=getattr(args, "generation_id", None),
            now=now(),
        )
        scrape_generation.write_generation(manifest_path, manifest)

    if manifest["status"] == "complete":
        scrape_generation.finalize_generation(manifest_path, candidate_path)
        print(f"Generation already complete: {manifest_path}", flush=True)
        return manifest

    successful = scrape_generation.successful_partition_ids(manifest_path)
    pending_projects = [
        project
        for project in projects
        if partition_id_for_url(project["url"]) not in successful
    ]
    if pending_projects and page_factory is None and async_playwright is None:
        raise RuntimeError(
            "Playwright is unavailable; install it with "
            "`python3 -m pip install playwright` and install Chromium"
        )

    factory = page_factory or _playwright_page
    if pending_projects:
        async with factory(args) as page:
            for index, project in enumerate(pending_projects, start=1):
                partition_id = partition_id_for_url(project["url"])
                attempt_id = str(uuid.uuid4())
                started_at = now()
                result: ScrapeResult | None = None
                exc: Exception | None = None
                try:
                    result = await _invoke_project_scraper(
                        project_scraper,
                        page,
                        project,
                        args,
                    )
                    if not result.rows:
                        raise ValueError(result.error_message or "zero rows parsed")
                    if not result.complete:
                        raise ValueError(
                            result.error_message
                            or f"incomplete scrape: {result.completion_reason or 'unknown'}"
                        )
                    if (
                        result.source_reported_row_count is not None
                        and result.source_reported_row_count != len(result.rows)
                    ):
                        raise ValueError("source-reported row count does not match parsed rows")
                    artifact_path = (
                        generation_root
                        / "artifacts"
                        / partition_id
                        / f"{attempt_id}.csv"
                    )
                    write_partition_artifact(artifact_path, result.rows, project)
                except Exception as caught:
                    exc = caught

                completed_at = now()
                if exc is None:
                    assert result is not None
                    manifest = scrape_generation.record_attempt(
                        manifest_path,
                        partition_id,
                        method="playwright",
                        status="succeeded",
                        started_at=started_at,
                        completed_at=completed_at,
                        retrieved_at=completed_at,
                        artifact_path=artifact_path,
                        source_reported_row_count=result.source_reported_row_count,
                        observations={
                            "pages_scraped": result.pages_scraped,
                            "completion_reason": result.completion_reason,
                            "source_reported_row_count": result.source_reported_row_count,
                        },
                        attempt_id=attempt_id,
                        now=completed_at,
                    )
                    status = "succeeded"
                    error = ""
                    row_count = len(result.rows)
                else:
                    manifest = scrape_generation.record_attempt(
                        manifest_path,
                        partition_id,
                        method="playwright",
                        status="failed",
                        started_at=started_at,
                        completed_at=completed_at,
                        error_code=_error_code(result, exc),
                        error_message=str(exc) or exc.__class__.__name__,
                        observations={
                            "pages_scraped": result.pages_scraped if result else 0,
                            "parsed_row_count": len(result.rows) if result else 0,
                            "completion_reason": result.completion_reason if result else "exception",
                            "source_reported_row_count": (
                                result.source_reported_row_count if result else None
                            ),
                        },
                        attempt_id=attempt_id,
                        now=completed_at,
                    )
                    status = "failed"
                    error = str(exc)
                    row_count = len(result.rows) if result else 0
                    print(
                        f"[{index}/{len(pending_projects)}] ERROR {project['url']}: {error}",
                        file=sys.stderr,
                        flush=True,
                    )
                if log_path is not None:
                    append_attempt(log_path, project, row_count, status, error)
                print(
                    f"[{index}/{len(pending_projects)}] {project.get('name', '')}: "
                    f"{row_count} rows ({status})",
                    flush=True,
                )
                if args.delay:
                    await page.wait_for_timeout(int(args.delay * 1000))

    pending = scrape_generation.pending_partition_ids(manifest_path)
    if pending:
        print(
            f"Generation remains open with {len(pending)} pending partition(s).",
            file=sys.stderr,
            flush=True,
        )
        return scrape_generation.load_generation(manifest_path)

    merge_generation_candidate(manifest_path, candidate_path)
    manifest = scrape_generation.finalize_generation(
        manifest_path,
        candidate_path,
        now=now(),
    )
    print(
        f"Finalized {manifest['summary']['succeeded']} requested project partitions "
        f"to {candidate_path}",
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape public EdgeProp landed transaction rows with Playwright",
    )
    parser.add_argument(
        "--input",
        default="data/raw/edgeprop/edgeprop_landed_projects_playwright.csv",
        help="CSV with name,url,slug columns",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_CANDIDATE_NAME,
        help="Generation-local reconciled candidate CSV (default: candidate.csv)",
    )
    parser.add_argument(
        "--generation-manifest",
        required=True,
        help="Run-scoped checkpoint JSON; its parent directory is the generation root",
    )
    parser.add_argument(
        "--generation-id",
        help="Optional identifier for a new generation or exact identity check on resume",
    )
    parser.add_argument("--limit", type=int, help="Maximum project pages to scrape")
    parser.add_argument("--start", type=int, default=0, help="Zero-based project offset")
    parser.add_argument("--match", help="Filter project name/slug substring")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Compatibility flag; an exact existing manifest always resumes selected successes",
    )
    parser.add_argument(
        "--resume-attempts",
        action="store_true",
        help="Rejected: attempt logs are diagnostic and never completion evidence",
    )
    parser.add_argument("--log", help="Optional human-readable diagnostic attempt CSV")
    parser.add_argument("--wait-ms", type=int, default=2500, help="Post-render wait per page")
    parser.add_argument("--timeout-ms", type=int, default=30_000, help="Navigation timeout per page")
    parser.add_argument("--max-pages", type=int, default=200, help="Maximum Sales-table pages per project")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between pages in seconds")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    try:
        manifest = asyncio.run(run(args))
    except (ContractError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    if manifest["status"] != "complete":
        parser.exit(1, "ERROR: generation remains incomplete; prior candidate was not replaced\n")


if __name__ == "__main__":
    main()
