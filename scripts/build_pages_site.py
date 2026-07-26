#!/usr/bin/env python3
"""Validate and assemble the static GitHub Pages research site."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from html import escape
from html.parser import HTMLParser
import json
import shutil
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sg_estate.reporting.property_analysis import (
    DEFAULT_PROPERTY_ANALYSIS_DIR,
    PropertyAnalysis,
    discover_property_analyses,
    latest_property_analyses,
    property_catalog_entries,
    render_property_analysis_page,
)

DEFAULT_MANIFEST = ROOT / "site" / "reports.json"
DEFAULT_ASSETS = ROOT / "site" / "assets"
DEFAULT_PROJECT_LIST = (
    ROOT / "data" / "raw" / "edgeprop" / "edgeprop_condo_apartment_projects.csv"
)
DEFAULT_PROJECT_TRANSACTIONS = (
    ROOT
    / "data"
    / "raw"
    / "edgeprop"
    / "edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
)
REQUIRED_FIELDS = {"id", "path", "title", "category", "kind", "summary", "tags"}
BUILD_MARKER = ".pages-build"
SHARED_CSS = "assets/research-shell.css"
SHARED_JS = "assets/research-shell.js"
PROPERTY_CARDS_MARKER = "      <!-- GENERATED_PROPERTY_ANALYSIS_CARDS -->"
PROPERTY_ROUTES_MARKER = "    /* GENERATED_PROPERTY_ANALYSIS_PROJECT_ROUTES */"


class _ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        attribute = "src" if tag in {"img", "script", "source"} else "href"
        if tag in {"a", "link", "img", "script", "source"} and values.get(attribute):
            self.references.append(values[attribute])  # type: ignore[arg-type]


def _safe_relative_file(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.name != value:
        raise ValueError(f"{field} must be a root-relative file name: {value!r}")
    return path


def load_catalog(manifest_path: Path = DEFAULT_MANIFEST) -> dict:
    """Load and validate the report catalog against root HTML artifacts."""
    try:
        catalog = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load report catalog {manifest_path}: {exc}") from exc

    if catalog.get("schema_version") != 1:
        raise ValueError("site/reports.json schema_version must be 1")
    reports = catalog.get("reports")
    if not isinstance(reports, list) or not reports:
        raise ValueError("site/reports.json reports must be a non-empty list")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for position, report in enumerate(reports):
        if not isinstance(report, dict):
            raise ValueError(f"reports[{position}] must be an object")
        missing = REQUIRED_FIELDS - report.keys()
        if missing:
            raise ValueError(
                f"reports[{position}] is missing: {', '.join(sorted(missing))}"
            )

        report_id = report["id"]
        if not isinstance(report_id, str) or not report_id.strip():
            raise ValueError(f"reports[{position}].id must be a non-empty string")
        if report_id in seen_ids:
            raise ValueError(f"Duplicate report id: {report_id}")
        seen_ids.add(report_id)

        relative_path = _safe_relative_file(
            report["path"], field=f"reports[{position}].path"
        )
        if relative_path.suffix != ".html" or relative_path.name == "index.html":
            raise ValueError(f"Report path must name a non-index HTML file: {relative_path}")
        if relative_path.name in seen_paths:
            raise ValueError(f"Duplicate report path: {relative_path}")
        seen_paths.add(relative_path.name)
        if not (ROOT / relative_path.name).is_file():
            raise ValueError(f"Catalogued report does not exist: {relative_path}")

        for field in ("title", "category", "kind", "summary"):
            if not isinstance(report[field], str) or not report[field].strip():
                raise ValueError(f"reports[{position}].{field} must be a non-empty string")
        if not isinstance(report["tags"], list) or not all(
            isinstance(tag, str) and tag.strip() for tag in report["tags"]
        ):
            raise ValueError(f"reports[{position}].tags must be a list of strings")

    root_reports = {path.name for path in ROOT.glob("*.html")} - {"index.html"}
    uncatalogued = root_reports - seen_paths
    if uncatalogued:
        raise ValueError(f"Uncatalogued root reports: {', '.join(sorted(uncatalogued))}")
    stale = seen_paths - root_reports
    if stale:
        raise ValueError(f"Catalog paths are not root reports: {', '.join(sorted(stale))}")
    return catalog


def build_project_catalog(
    projects_path: Path = DEFAULT_PROJECT_LIST,
    transactions_path: Path = DEFAULT_PROJECT_TRANSACTIONS,
) -> dict:
    """Build a public name/district index without exposing transaction details."""
    district_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    try:
        with transactions_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            required = {"source_slug", "Postal District"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{transactions_path} is missing: {', '.join(sorted(missing))}"
                )
            for row in reader:
                slug = row["source_slug"].strip()
                district = row["Postal District"].strip()
                if district.endswith(".0"):
                    district = district[:-2]
                if district.isdigit():
                    district = district.zfill(2)
                if slug and district:
                    district_counts[slug][district] += 1
    except OSError as exc:
        raise ValueError(f"Cannot load project transactions {transactions_path}: {exc}") from exc

    projects: list[dict[str, str]] = []
    seen_slugs: set[str] = set()
    try:
        with projects_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            required = {"name", "slug"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{projects_path} is missing: {', '.join(sorted(missing))}")
            for position, row in enumerate(reader, start=2):
                name = row["name"].strip()
                slug = row["slug"].strip()
                if not name or not slug:
                    raise ValueError(f"{projects_path}:{position} has an empty name or slug")
                if slug in seen_slugs:
                    raise ValueError(f"{projects_path}:{position} repeats slug {slug!r}")
                seen_slugs.add(slug)
                project = {"name": name, "slug": slug}
                if district_counts[slug]:
                    project["district"] = min(
                        district_counts[slug],
                        key=lambda value: (-district_counts[slug][value], value),
                    )
                projects.append(project)
    except OSError as exc:
        raise ValueError(f"Cannot load project list {projects_path}: {exc}") from exc

    if not projects:
        raise ValueError(f"{projects_path} contains no projects")
    return {"schema_version": 1, "projects": projects}


def inject_research_shell(site_dir: Path) -> None:
    """Add shared navigation/accessibility assets to built reports when available."""
    has_css = (site_dir / SHARED_CSS).is_file()
    has_js = (site_dir / SHARED_JS).is_file()
    if not has_css and not has_js:
        return

    for html_path in site_dir.glob("*.html"):
        source = html_path.read_text(encoding="utf-8")
        updated = source
        if has_css and SHARED_CSS not in updated:
            if "</head>" not in updated.lower():
                raise ValueError(f"{html_path.name} has no closing head tag")
            position = updated.lower().rfind("</head>")
            updated = (
                updated[:position]
                + f'<link rel="stylesheet" href="{SHARED_CSS}" data-research-shell>\n'
                + updated[position:]
            )
        if has_js and SHARED_JS not in updated:
            if "</body>" not in updated.lower():
                raise ValueError(f"{html_path.name} has no closing body tag")
            position = updated.lower().rfind("</body>")
            updated = (
                updated[:position]
                + f'<script src="{SHARED_JS}" data-research-shell></script>\n'
                + updated[position:]
            )
        if updated != source:
            html_path.write_text(updated, encoding="utf-8")


def validate_site_links(site_dir: Path) -> None:
    """Reject broken local HTML, script, stylesheet and image references."""
    broken: list[str] = []
    site_root = site_dir.resolve()
    for html_path in site_dir.rglob("*.html"):
        parser = _ResourceParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        for reference in parser.references:
            if reference.startswith(("#", "//")):
                continue
            parsed = urlsplit(reference)
            if parsed.scheme:
                continue
            if parsed.path.startswith("/"):
                broken.append(
                    f"{html_path.name} -> {reference} (must be relative on project Pages)"
                )
                continue
            relative = unquote(parsed.path)
            if not relative:
                continue
            target = html_path.parent / relative
            if target.is_dir():
                target /= "index.html"
            resolved_target = target.resolve()
            if site_root != resolved_target and site_root not in resolved_target.parents:
                broken.append(f"{html_path.name} -> {reference} (escapes the site)")
                continue
            if not target.is_file():
                broken.append(f"{html_path.name} -> {reference}")
    if broken:
        raise ValueError("Broken site references:\n" + "\n".join(sorted(broken)))


def _prepare_property_publication(
    catalog: dict,
    *,
    property_analysis_dir: Path,
) -> tuple[list[PropertyAnalysis], dict[str, str], dict]:
    """Validate, render and merge every dated property-analysis source."""

    analyses = discover_property_analyses(property_analysis_dir)
    existing_ids = {report["id"] for report in catalog["reports"]}
    existing_paths = {report["path"] for report in catalog["reports"]}
    rendered_pages: dict[str, str] = {}
    for analysis in analyses:
        if analysis.report_id in existing_ids:
            raise ValueError(
                f"Property analysis id collides with the report catalog: "
                f"{analysis.report_id}"
            )
        if analysis.output_path in existing_paths or (ROOT / analysis.output_path).exists():
            raise ValueError(
                f"Property analysis output collides with an authored report: "
                f"{analysis.output_path}"
            )
        rendered_pages[analysis.output_path] = render_property_analysis_page(analysis)

    merged_catalog = dict(catalog)
    merged_catalog["reports"] = [
        *property_catalog_entries(analyses),
        *catalog["reports"],
    ]
    return analyses, rendered_pages, merged_catalog


def _property_cards(analyses: list[PropertyAnalysis]) -> str:
    cards: list[str] = []
    for analysis in latest_property_analyses(analyses):
        search_text = " ".join(
            (
                analysis.project_name,
                analysis.title,
                analysis.property_description,
                analysis.summary,
                "condominium resale valuation quantum investment property analysis",
            )
        )
        cards.append(
            "\n".join(
                (
                    '      <a class="card property-analysis-card" '
                    'data-kind="analysis project" '
                    f'data-search="{escape(search_text, quote=True)}" '
                    f'href="{escape(analysis.output_path, quote=True)}">',
                    f'        <span class="tag">Property analysis · '
                    f"{escape(analysis.date_label)}</span>"
                    f"<h3>{escape(analysis.project_name)}</h3>",
                    f"        <p>{escape(analysis.summary)}</p>",
                    '        <span class="open">Read the dated analysis →</span>',
                    "      </a>",
                )
            )
        )
    return "\n".join(cards)


def _property_routes(analyses: list[PropertyAnalysis]) -> str:
    routes: list[str] = []
    for analysis in latest_property_analyses(analyses):
        project_key = " ".join(analysis.project_name.split()).upper()
        key_json = json.dumps(project_key, ensure_ascii=True).replace("<", "\\u003c")
        path_json = json.dumps(
            analysis.output_path, ensure_ascii=True
        ).replace("<", "\\u003c")
        routes.append(f"    {key_json}: {path_json},")
    return "\n".join(routes)


def inject_property_library(index_path: Path, analyses: list[PropertyAnalysis]) -> None:
    """Inject indexable newest-report cards and exact project-finder routes."""

    source = index_path.read_text(encoding="utf-8")
    for marker in (PROPERTY_CARDS_MARKER, PROPERTY_ROUTES_MARKER):
        if source.count(marker) != 1:
            raise ValueError(
                f"{index_path.name} must contain exactly one publication marker {marker}"
            )
    updated = source.replace(PROPERTY_CARDS_MARKER, _property_cards(analyses))
    updated = updated.replace(PROPERTY_ROUTES_MARKER, _property_routes(analyses))
    index_path.write_text(updated, encoding="utf-8")


def build_site(
    output_dir: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    assets_dir: Path = DEFAULT_ASSETS,
    property_analysis_dir: Path = DEFAULT_PROPERTY_ANALYSIS_DIR,
) -> int:
    """Build a self-contained Pages artifact and return its report count."""
    catalog = load_catalog(manifest_path)
    analyses, rendered_pages, merged_catalog = _prepare_property_publication(
        catalog,
        property_analysis_dir=property_analysis_dir,
    )
    project_catalog = build_project_catalog()
    output_dir = output_dir.resolve()
    if output_dir == ROOT or ROOT not in output_dir.parents:
        raise ValueError(f"Output must be a directory inside the repository: {output_dir}")

    if output_dir.is_dir() and any(output_dir.iterdir()):
        if not (output_dir / BUILD_MARKER).is_file():
            raise ValueError(
                f"Refusing to replace unowned non-empty output directory: {output_dir}"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / BUILD_MARKER).touch()
    for html_path in ROOT.glob("*.html"):
        shutil.copy2(html_path, output_dir / html_path.name)
    for relative_path, page in rendered_pages.items():
        (output_dir / relative_path).write_text(page, encoding="utf-8")
    (output_dir / "reports.json").write_text(
        json.dumps(merged_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "projects.json").write_text(
        json.dumps(project_catalog, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    if assets_dir.is_dir():
        shutil.copytree(
            assets_dir,
            output_dir / "assets",
            dirs_exist_ok=True,
        )
    inject_property_library(output_dir / "index.html", analyses)
    inject_research_shell(output_dir)
    (output_dir / ".nojekyll").touch()
    if not (output_dir / "index.html").is_file():
        raise ValueError("Built site is missing index.html")
    validate_site_links(output_dir)
    return len(merged_catalog["reports"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the report catalog and assemble the GitHub Pages artifact."
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output directory. Omit to validate the catalog without writing files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.out is None:
        catalog = load_catalog()
        analyses, _, merged_catalog = _prepare_property_publication(
            catalog,
            property_analysis_dir=DEFAULT_PROPERTY_ANALYSIS_DIR,
        )
        project_catalog = build_project_catalog()
        print(
            f"Validated {len(merged_catalog['reports'])} research reports "
            f"({len(analyses)} dated property analyses) and "
            f"{len(project_catalog['projects'])} private projects."
        )
    else:
        count = build_site(args.out)
        print(f"Built {count} research reports in {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
