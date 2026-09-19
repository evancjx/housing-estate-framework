#!/usr/bin/env python3
"""Validate and assemble the static GitHub Pages research site."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import json
import re
import shutil
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
for import_root in (ROOT, MODELS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import multi_condo_transactions as transaction_data
import private_project_catalog as project_catalog_data
import project_identity_registry as project_registry_data

from sg_estate.reporting.property_analysis import (
    DEFAULT_PROPERTY_ANALYSIS_DIR,
    PropertyAnalysis,
    discover_property_analyses,
    latest_property_analyses,
    property_catalog_entries,
    render_property_analysis_page,
)
from sg_estate.reporting.catalog import (
    DATA_FAMILY_IDS,
    REPORT_CATALOG_SCHEMA_VERSION,
    validate_data_families,
)
from sg_estate.contracts import ContractError, SOURCE_RECEIPT
from sg_estate.source_receipts import receipt_acquisition_mode, sha256_file

DEFAULT_MANIFEST = ROOT / "site" / "reports.json"
DEFAULT_ASSETS = ROOT / "site" / "assets"
DEFAULT_DATA_CATALOG = ROOT / "data" / "catalog.json"
DEFAULT_INPUT_DIR = ROOT / "data" / "inputs"
DEFAULT_RUN_MANIFEST = ROOT / "data" / "outputs" / "run_manifest.json"
DEFAULT_TRANSACTION_MANIFEST = (
    ROOT / "site" / "assets" / "condo-transactions" / "manifest.json"
)
REQUIRED_FIELDS = {
    "id",
    "path",
    "title",
    "category",
    "kind",
    "summary",
    "tags",
    "data_families",
}
BUILD_MARKER = ".pages-build"
SHARED_CSS = "assets/research-shell.css"
SHARED_JS = "assets/research-shell.js"
PROPERTY_CARDS_MARKER = "      <!-- GENERATED_PROPERTY_ANALYSIS_CARDS -->"
REPORT_LIBRARY_START_MARKER = "      <!-- GENERATED_REPORT_LIBRARY_START -->"
REPORT_LIBRARY_END_MARKER = "      <!-- GENERATED_REPORT_LIBRARY_END -->"
REPORT_CATEGORY_OPTIONS_START_MARKER = (
    "          <!-- GENERATED_REPORT_CATEGORY_OPTIONS_START -->"
)
REPORT_CATEGORY_OPTIONS_END_MARKER = (
    "          <!-- GENERATED_REPORT_CATEGORY_OPTIONS_END -->"
)
REPORT_LIBRARY_CONFIG_MARKER = "<!-- GENERATED_REPORT_LIBRARY_CONFIG -->"
REPORT_LIBRARY_CONFIG_START_MARKER = (
    "<!-- GENERATED_REPORT_LIBRARY_CONFIG_START -->"
)
REPORT_LIBRARY_CONFIG_END_MARKER = "<!-- GENERATED_REPORT_LIBRARY_CONFIG_END -->"
REPORT_LIBRARY_CONFIG_SCHEMA = 1
REPORT_TOKEN_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
DISTRICT_REPORT_ID_RE = re.compile(r"^district-(?P<district>0?[1-9]|1[0-9]|2[0-8])$")
DATA_STATUS_MARKER = "    <!-- GENERATED_DATA_STATUS -->"
PROJECT_REGISTRY_CONFIG_ID = "project-identity-registry-config"
PROJECT_REGISTRY_BOOTSTRAP_IDS = (
    "treasure-at-tampines",
    "the-poiz-residences",
    "canberra-crescent-residences",
)
REPORT_HTML_BUDGETS = {
    "private_project_comparison_table.html": 750 * 1024,
    "condo_framework_comparison.html": 500 * 1024,
    "multi_condo_framework_comparison.html": 500 * 1024,
    "project_exit_comparison.html": 500 * 1024,
}
PROJECT_OPTION_BUDGETS = {
    "condo_framework_comparison.html": 2,
    "multi_condo_framework_comparison.html": 3,
    "project_exit_comparison.html": 3,
}


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
    parsed = urlsplit(value)
    path = PurePosixPath(value)
    decoded = unquote(value)
    decoded_path = PurePosixPath(decoded)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or path.is_absolute()
        or decoded_path.is_absolute()
        or ".." in path.parts
        or ".." in decoded_path.parts
        or path.as_posix() != value
        or decoded_path.as_posix() != decoded
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts)
    ):
        raise ValueError(f"{field} must be a safe root-relative file path: {value!r}")
    return path


def load_catalog(manifest_path: Path = DEFAULT_MANIFEST) -> dict:
    """Load and validate the report catalog against root HTML artifacts."""
    try:
        catalog = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load report catalog {manifest_path}: {exc}") from exc

    if catalog.get("schema_version") != REPORT_CATALOG_SCHEMA_VERSION:
        raise ValueError(
            "site/reports.json schema_version must be "
            f"{REPORT_CATALOG_SCHEMA_VERSION}"
        )
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
        normalized_path = relative_path.as_posix()
        if normalized_path in seen_paths:
            raise ValueError(f"Duplicate report path: {relative_path}")
        seen_paths.add(normalized_path)
        if not ROOT.joinpath(*relative_path.parts).is_file():
            raise ValueError(f"Catalogued report does not exist: {relative_path}")

        for field in ("title", "category", "kind", "summary"):
            if not isinstance(report[field], str) or not report[field].strip():
                raise ValueError(f"reports[{position}].{field} must be a non-empty string")
        if not isinstance(report["tags"], list) or not all(
            isinstance(tag, str) and tag.strip() for tag in report["tags"]
        ):
            raise ValueError(f"reports[{position}].tags must be a list of strings")
        project_names = report.get("project_names")
        if project_names is not None:
            if not isinstance(project_names, list) or not project_names or not all(
                isinstance(project_name, str) and project_name.strip()
                for project_name in project_names
            ):
                raise ValueError(
                    f"reports[{position}].project_names must be a non-empty list "
                    "of strings"
                )
            normalized_project_names = {
                " ".join(project_name.split()).casefold()
                for project_name in project_names
            }
            if len(normalized_project_names) != len(project_names):
                raise ValueError(
                    f"reports[{position}].project_names must not repeat names"
                )
        validate_data_families(
            report["data_families"],
            source=f"reports[{position}].data_families",
        )

    root_reports = {path.name for path in ROOT.glob("*.html")} - {"index.html"}
    uncatalogued = root_reports - seen_paths
    if uncatalogued:
        raise ValueError(f"Uncatalogued root reports: {', '.join(sorted(uncatalogued))}")
    return catalog


def _load_json_object(path: Path, *, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return payload


def _max_csv_value(path: Path, column: str) -> str | None:
    """Return a source-declared maximum without inferring a retrieval date."""

    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if column not in (reader.fieldnames or []):
                return None
            values = [str(row.get(column, "")).strip() for row in reader]
    except OSError as exc:
        raise ValueError(f"Cannot inspect data coverage in {path}: {exc}") from exc
    values = [value for value in values if value]
    return max(values) if values else None


def build_data_status(
    *,
    catalog_path: Path = DEFAULT_DATA_CATALOG,
    run_manifest_path: Path = DEFAULT_RUN_MANIFEST,
    transaction_manifest_path: Path = DEFAULT_TRANSACTION_MANIFEST,
    input_dir: Path = DEFAULT_INPUT_DIR,
) -> dict:
    """Build honest source status without treating a build date as data freshness."""

    catalog = _load_json_object(catalog_path, label="data catalog")
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("datasets"), dict):
        raise ValueError("data/catalog.json must contain schema_version 1 and datasets")
    run_manifest = _load_json_object(run_manifest_path, label="pipeline run manifest")
    run_schema = run_manifest.get("schema_version")
    if run_schema not in {2, 3}:
        raise ValueError(
            "pipeline run manifest schema_version must be 2 (legacy) or 3"
        )
    if run_manifest.get("status") != "complete":
        raise ValueError("pipeline run manifest must describe a complete promoted run")
    transaction_manifest = _load_json_object(
        transaction_manifest_path,
        label="transaction manifest",
    )
    canonical_transactions = transaction_manifest.get("source_metadata", {}).get(
        "canonical", {}
    )
    if not isinstance(canonical_transactions, dict):
        raise ValueError("transaction manifest canonical source metadata must be an object")

    coverage_by_dataset = {
        "hdb_resale.csv": _max_csv_value(
            input_dir / "hdb_resale.csv", "month"
        ),
        "ura_private.csv": canonical_transactions.get("latest_month"),
        "mrt_layer.csv": _max_csv_value(
            input_dir / "mrt_layer.csv", "status_as_of"
        ),
        "mrt_network_status.csv": _max_csv_value(
            input_dir / "mrt_network_status.csv", "status_as_of"
        ),
    }
    run_inputs = run_manifest.get("inputs", {})
    if not isinstance(run_inputs, dict):
        raise ValueError("pipeline run manifest inputs must be an object")

    raw_receipts = run_manifest.get("source_receipts", {})
    if run_schema == 3 and not isinstance(raw_receipts, dict):
        raise ValueError("pipeline run manifest source_receipts must be an object")
    if run_schema == 2:
        raw_receipts = {}
    receipts: dict[str, dict[str, object]] = {}
    for receipt_key, raw_receipt in sorted(raw_receipts.items()):
        if not isinstance(receipt_key, str):
            raise ValueError("pipeline source receipt keys must be dataset IDs")
        try:
            receipt = SOURCE_RECEIPT.validate(
                raw_receipt,
                source=f"pipeline source receipt {receipt_key!r}",
            )
        except ContractError as exc:
            raise ValueError(str(exc)) from exc
        if receipt["dataset_id"] != receipt_key:
            raise ValueError(
                f"pipeline source receipt key {receipt_key!r} does not match "
                f"dataset_id {receipt['dataset_id']!r}"
            )
        if receipt["validation_status"] != "passed":
            raise ValueError(
                f"promoted source receipt {receipt_key!r} was not validated"
            )
        receipts[receipt_key] = receipt
    unknown_receipts = sorted(set(receipts) - set(catalog["datasets"]))
    if unknown_receipts:
        raise ValueError(
            "pipeline source receipts are absent from data/catalog.json: "
            + ", ".join(unknown_receipts)
        )

    datasets = []
    for dataset_id, metadata in sorted(catalog["datasets"].items()):
        if not isinstance(metadata, dict):
            raise ValueError(f"data catalog entry {dataset_id!r} must be an object")
        path = input_dir / dataset_id
        if not path.is_file():
            raise ValueError(f"Catalogued dataset does not exist: {path}")
        receipt = receipts.get(dataset_id)
        if receipt is not None and receipt["authority"] != metadata.get("authority"):
            raise ValueError(
                f"Source receipt authority for {dataset_id!r} differs from "
                "data/catalog.json"
            )
        current_sha256 = sha256_file(path)
        run_sha256 = run_inputs.get(dataset_id)
        if receipt is not None:
            # A promoted v3 receipt is the run's byte-level evidence for a
            # refreshed/derived output. Such outputs are intentionally absent
            # from ``inputs`` (and tree_canopy may appear there only as the
            # *pre-refresh fallback*), so requiring both hashes would falsely
            # mark successfully promoted data as stale.
            verified_in_run = receipt["sha256"] == current_sha256
        else:
            verified_in_run = (
                isinstance(run_sha256, str) and run_sha256 == current_sha256
            )
        status = (
            "verified_in_model_run"
            if verified_in_run
            else (
                "modified_since_run"
                if receipt is not None or dataset_id in run_inputs
                else "catalogued_snapshot"
            )
        )
        coverage_end = (
            receipt["coverage_end"]
            if receipt is not None and receipt["coverage_end"] is not None
            else coverage_by_dataset.get(dataset_id)
        )
        coverage_basis = (
            "source_receipt"
            if receipt is not None and receipt["coverage_end"] is not None
            else ("committed_data" if coverage_end is not None else None)
        )
        datasets.append(
            {
                "dataset_id": dataset_id,
                "path": f"data/inputs/{dataset_id}",
                "zone": metadata.get("zone"),
                "producer": metadata.get("producer"),
                "authority": metadata.get("authority"),
                "status": status,
                "source_url": receipt["source_url"] if receipt is not None else None,
                "source_urls": receipt["source_urls"] if receipt is not None else None,
                "source_identity": (
                    receipt["source_identity"] if receipt is not None else None
                ),
                "coverage_start": (
                    receipt["coverage_start"] if receipt is not None else None
                ),
                "coverage_end": coverage_end,
                "coverage_basis": coverage_basis,
                # Legacy manifests do not have consistent retrieval timestamps.
                # Keep that uncertainty explicit instead of using file mtimes.
                "retrieved_at": receipt["retrieved_at"] if receipt is not None else None,
                "row_count": receipt["row_count"] if receipt is not None else None,
                "sha256": receipt["sha256"] if receipt is not None else run_sha256,
                "cache_state": receipt["cache_state"] if receipt is not None else "unknown",
                "fallback_state": (
                    receipt["fallback_state"] if receipt is not None else "unknown"
                ),
                "validation_status": (
                    receipt["validation_status"] if receipt is not None else "unknown"
                ),
                "acquisition_mode": (
                    receipt_acquisition_mode(receipt) if receipt is not None else "unknown"
                ),
            }
        )

    receipt_modes = {
        dataset_id: receipt_acquisition_mode(receipt)
        for dataset_id, receipt in receipts.items()
    }
    private_receipt = receipts.get("ura_private.csv")
    rail_receipt = receipts.get("mrt_layer.csv")
    private_complete_through = (
        canonical_transactions.get("complete_through")
        or canonical_transactions.get("complete_end")
    )
    private_partial_period = canonical_transactions.get("partial_month")
    if not private_complete_through:
        private_status = "unknown"
        private_note = "No complete transaction period is recorded."
    elif canonical_transactions.get("latest_month_partial"):
        private_status = "partial_latest_period"
        private_note = (
            f"{private_partial_period} is partial; Data through uses the last "
            "complete month."
            if private_partial_period
            else "The latest period is partial; Data through uses the last complete month."
        )
    else:
        private_status = "complete_latest_period"
        private_note = "Data through uses the latest complete recorded month."
    mode_values = set(receipt_modes.values())
    if "fallback" in mode_values:
        refresh_mode = "reviewed_fallback"
    elif "fresh" in mode_values or "mixed" in mode_values:
        refresh_mode = "network_refresh"
    elif "cached" in mode_values:
        refresh_mode = "cached_sources"
    elif receipts:
        refresh_mode = "committed_derived_snapshots"
    else:
        refresh_mode = (
            "network_refresh"
            if run_manifest.get("refresh_derived") is True
            else "committed_derived_snapshots"
        )
    result = {
        "schema_version": 2,
        "model_run": {
            "status": run_manifest.get("status"),
            "scoring_year": run_manifest.get("as_of_year"),
            "generated_at": run_manifest.get("completed_at"),
            "refresh_mode": refresh_mode,
            "source_receipt_modes": receipt_modes,
        },
        "families": {
            "estate_model": {
                "label": "Estate model",
                "status": run_manifest.get("status"),
                # The model combines sources with different coverage periods.
                # A scoring year is not a truthful substitute for data coverage.
                "data_through": None,
                "last_checked": None,
                "generated_at": run_manifest.get("completed_at"),
                "scoring_year": run_manifest.get("as_of_year"),
                "hdb_transactions_through": coverage_by_dataset["hdb_resale.csv"],
                "note": (
                    "The model combines sources with different coverage periods; "
                    "its scoring year is not a source-coverage date."
                ),
            },
            "private_transactions": {
                "label": "Private transactions",
                "status": private_status,
                "data_through": private_complete_through,
                "last_checked": (
                    private_receipt.get("retrieved_at")
                    if private_receipt is not None
                    else None
                ),
                "generated_at": None,
                "latest_period": canonical_transactions.get("latest_month"),
                "complete_through": private_complete_through,
                "partial_period": private_partial_period,
                "note": private_note,
            },
            "rail_network": {
                "label": "Rail network",
                "status": "reviewed_snapshot",
                "data_through": None,
                "last_checked": (
                    rail_receipt.get("retrieved_at")
                    if rail_receipt is not None and rail_receipt.get("retrieved_at")
                    else coverage_by_dataset["mrt_network_status.csv"]
                ),
                "generated_at": None,
                "checked_through": coverage_by_dataset["mrt_layer.csv"],
                "note": "Reviewed status snapshot; not a live service feed.",
            },
            "finance_assumptions": {
                "label": "Finance assumptions",
                "status": "assumption_driven",
                "data_through": None,
                "last_checked": None,
                "generated_at": None,
                "note": (
                    "User-entered scenarios and visible assumptions; no live "
                    "market-data feed."
                ),
            },
            "market_research": {
                "label": "Market research",
                "status": "point_in_time_or_unreceipted",
                "data_through": None,
                "last_checked": None,
                "generated_at": None,
                "note": (
                    "Point-in-time or source-specific project research; generic "
                    "dates remain unknown unless the report records a capture."
                ),
            },
        },
        "datasets": datasets,
    }
    if set(result["families"]) != DATA_FAMILY_IDS:
        raise ValueError("data-status family vocabulary drifted from the report catalog")
    return result


def _date_label(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%d %b %Y")


def _month_label(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "Unknown"
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return value


def inject_data_status(index_path: Path, status: dict) -> None:
    """Render the three most decision-relevant source vintages on the landing page."""

    source = index_path.read_text(encoding="utf-8")
    if source.count(DATA_STATUS_MARKER) != 1:
        raise ValueError(
            f"{index_path.name} must contain exactly one publication marker "
            f"{DATA_STATUS_MARKER}"
        )
    model = status["model_run"]
    estate = status["families"]["estate_model"]
    private = status["families"]["private_transactions"]
    rail = status["families"]["rail_network"]
    refresh_note = {
        "network_refresh": "This run includes reviewed network-refreshed layers.",
        "cached_sources": "This run used reviewed cached source payloads.",
        "reviewed_fallback": "This run used at least one reviewed fallback source.",
        "committed_derived_snapshots": (
            "This was an offline rebuild from committed derived snapshots."
        ),
    }.get(model["refresh_mode"], "See machine-readable source receipts for details.")
    partial_note = (
        f"{escape(_month_label(private['partial_period']))} is partial and is "
        "not presented as a complete month."
        if private.get("partial_period")
        else "The latest recorded month is marked complete."
    )
    markup = f"""    <div class="section-head">
      <div><div class="eyebrow">Data currency</div><h2 id="data-status-title">Know what is fresh—and what is not</h2></div>
      <p>Generation time and source coverage are different. Unknown retrieval dates stay unknown.</p>
    </div>
    <div class="data-status-grid">
      <article><b>Estate model</b><strong>Scoring year {escape(str(model.get('scoring_year') or 'unknown'))}</strong><p>Published pipeline run: {escape(_date_label(model.get('generated_at')))}. {escape(refresh_note)}</p></article>
      <article><b>Private transactions</b><strong>Complete through {escape(_month_label(private.get('complete_through')))}</strong><p>{escape(partial_note)}</p></article>
      <article><b>Rail network</b><strong>Reviewed through {escape(_date_label(rail.get('checked_through')))}</strong><p>Status dates come from the committed, reviewed LTA/URA rail contract.</p></article>
    </div>
    <p class="data-status-link"><a href="data-status.json">Open machine-readable status for every catalogued dataset</a></p>"""
    index_path.write_text(source.replace(DATA_STATUS_MARKER, markup), encoding="utf-8")


def _report_generated_at(html_source: str) -> str | None:
    """Return an explicitly authored report generation date, if present."""

    parser = _GeneratedTimeParser()
    parser.feed(html_source)
    return parser.generated_at


class _GeneratedTimeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.generated_at: str | None = None
        self._label_tag: str | None = None
        self._label_text: list[str] = []
        self._awaiting_generated_time = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.generated_at is not None:
            return
        if tag in {"b", "strong"} and self._label_tag is None:
            self._label_tag = tag
            self._label_text = []
        if tag == "time" and self._awaiting_generated_time:
            value = dict(attrs).get("datetime")
            if value:
                self.generated_at = value
            self._awaiting_generated_time = False

    def handle_data(self, data: str) -> None:
        if self._label_tag is not None:
            self._label_text.append(data)
        elif self._awaiting_generated_time and data.strip():
            # Only an explicitly labelled adjacent time qualifies.
            self._awaiting_generated_time = False

    def handle_endtag(self, tag: str) -> None:
        if tag == self._label_tag:
            label = " ".join(self._label_text).strip().rstrip(":").casefold()
            self._awaiting_generated_time = label == "generated"
            self._label_tag = None
            self._label_text = []


def _inject_report_status_bootstrap(
    html_source: str,
    *,
    report: dict,
    data_status: dict,
) -> str:
    families = {
        family_id: dict(data_status["families"][family_id])
        for family_id in report["data_families"]
    }
    generated_at = _report_generated_at(html_source)
    if (
        isinstance(report.get("captured_at"), str)
        and "market_research" in families
    ):
        # A dated analysis capture is evidence of review/checking, not data
        # coverage or report generation. Preserve it in its own field.
        families["market_research"]["last_checked"] = report["captured_at"]
    payload = {
        "schema_version": 1,
        "report_path": report["path"],
        "data_families": report["data_families"],
        "families": families,
        "generated_at": generated_at,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c")
    script = (
        '<script type="application/json" id="research-report-status">'
        f"{encoded}</script>\n"
    )
    position = html_source.lower().rfind("</body>")
    if position < 0:
        raise ValueError(f"{report['path']} has no closing body tag")
    return html_source[:position] + script + html_source[position:]


def inject_research_shell(
    site_dir: Path,
    *,
    catalog: dict | None = None,
    data_status: dict | None = None,
) -> None:
    """Add shared navigation/accessibility assets to built reports when available."""
    has_css = (site_dir / SHARED_CSS).is_file()
    has_js = (site_dir / SHARED_JS).is_file()
    if not has_css and not has_js and (catalog is None or data_status is None):
        return

    reports_by_path = {
        report["path"]: report for report in (catalog or {}).get("reports", [])
    }
    for html_path in site_dir.rglob("*.html"):
        source = html_path.read_text(encoding="utf-8")
        updated = source
        relative = html_path.relative_to(site_dir).as_posix()
        if (
            catalog is not None
            and data_status is not None
            and relative in reports_by_path
            and 'id="research-report-status"' not in updated
        ):
            updated = _inject_report_status_bootstrap(
                updated,
                report=reports_by_path[relative],
                data_status=data_status,
            )
        relative_assets = Path(*([".."] * (len(html_path.relative_to(site_dir).parts) - 1)))
        asset_prefix = "" if str(relative_assets) == "." else relative_assets.as_posix() + "/"
        css_href = asset_prefix + SHARED_CSS
        js_src = asset_prefix + SHARED_JS
        if has_css and SHARED_CSS not in updated:
            if "</head>" not in updated.lower():
                raise ValueError(f"{html_path.name} has no closing head tag")
            position = updated.lower().rfind("</head>")
            updated = (
                updated[:position]
                + f'<link rel="stylesheet" href="{css_href}" data-research-shell>\n'
                + updated[position:]
            )
        if has_js and SHARED_JS not in updated:
            if "</body>" not in updated.lower():
                raise ValueError(f"{html_path.name} has no closing body tag")
            position = updated.lower().rfind("</body>")
            updated = (
                updated[:position]
                + f'<script src="{js_src}" data-research-shell></script>\n'
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


def validate_transaction_assets(assets_dir: Path) -> None:
    """Load and validate the complete revision selected by the runtime manifest."""

    assets_root = assets_dir.resolve()
    transaction_dir = assets_dir / "condo-transactions"
    transaction_root = transaction_dir.resolve()
    if assets_root != transaction_root and assets_root not in transaction_root.parents:
        raise ValueError("Transaction asset directory escapes the Pages assets directory")

    manifest = _load_json_object(
        transaction_dir / "manifest.json",
        label="transaction manifest",
    )
    revision = manifest.get("dataset_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 64
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise ValueError(
            "Transaction manifest dataset_revision must be a lowercase SHA-256 digest"
        )

    generation_dir = transaction_dir / revision
    resolved_generation = generation_dir.resolve()
    if transaction_root != resolved_generation and transaction_root not in (
        resolved_generation.parents
    ):
        raise ValueError("Transaction revision directory escapes the asset directory")
    versioned_manifest = _load_json_object(
        generation_dir / "manifest.json",
        label="versioned transaction manifest",
    )
    if versioned_manifest != manifest:
        raise ValueError(
            "Versioned transaction manifest differs from the published manifest"
        )

    inventory = manifest.get("shards")
    if not isinstance(inventory, list) or len(inventory) != transaction_data.SHARD_COUNT:
        raise ValueError(
            f"Transaction manifest must inventory exactly "
            f"{transaction_data.SHARD_COUNT} shards"
        )

    shards: dict[int, dict] = {}
    for expected_index, entry in enumerate(inventory):
        expected_reference = (
            f"assets/condo-transactions/{revision}/shard-{expected_index:02d}.json"
        )
        if (
            not isinstance(entry, dict)
            or entry.get("index") != expected_index
            or entry.get("path") != expected_reference
        ):
            raise ValueError(
                f"Transaction shard inventory entry {expected_index} has an unsafe "
                "or unexpected path"
            )
        relative = PurePosixPath(expected_reference)
        shard_path = assets_dir.joinpath(*relative.parts[1:])
        resolved_shard = shard_path.resolve()
        if resolved_generation != resolved_shard and resolved_generation not in (
            resolved_shard.parents
        ):
            raise ValueError(
                f"Transaction shard escapes its revision directory: {expected_reference}"
            )
        if not shard_path.is_file():
            raise ValueError(f"Transaction shard does not exist: {expected_reference}")
        shards[expected_index] = _load_json_object(
            shard_path,
            label="transaction shard",
        )

    try:
        transaction_data.validate_transaction_bundle(shards, manifest)
    except ValueError as exc:
        raise ValueError(f"Invalid transaction publication: {exc}") from exc


def validate_project_catalog_assets(assets_dir: Path) -> None:
    """Validate the immutable project catalog selected by its root manifest."""

    catalog_dir = assets_dir / "project-catalog"
    root_manifest_path = catalog_dir / "manifest.json"
    transaction_manifest_path = assets_dir / "condo-transactions" / "manifest.json"
    transaction_manifest = _load_json_object(
        transaction_manifest_path,
        label="transaction manifest",
    )
    try:
        root_manifest = project_catalog_data.load_project_catalog(
            root_manifest_path,
            transaction_manifest=transaction_manifest,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid project catalog publication: {exc}") from exc
    revision = root_manifest["catalog_revision"]
    immutable_path = catalog_dir / revision / "catalog.json"
    resolved_root = catalog_dir.resolve()
    resolved_immutable = immutable_path.resolve()
    if resolved_root not in resolved_immutable.parents:
        raise ValueError("Project catalog immutable path escapes its asset directory")
    try:
        immutable = project_catalog_data.load_project_catalog(
            immutable_path,
            transaction_manifest=transaction_manifest,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid immutable project catalog: {exc}") from exc
    if immutable != root_manifest:
        raise ValueError(
            "Immutable project catalog differs from the published root manifest"
        )


def validate_report_performance_budgets(site_root: Path) -> None:
    """Fail publication when the project tools regress to eager multi-MiB HTML."""

    failures: list[str] = []
    for file_name, maximum in REPORT_HTML_BUDGETS.items():
        path = site_root / file_name
        size = path.stat().st_size
        if size > maximum:
            failures.append(
                f"{file_name} is {size:,} bytes; budget is {maximum:,} bytes"
            )
        source = path.read_text(encoding="utf-8")
        if "assets/data-loader.js" not in source:
            failures.append(f"{file_name} does not load the shared data loader")

    private_source = (site_root / "private_project_comparison_table.html").read_text(
        encoding="utf-8"
    )
    private_match = re.search(
        r'<script id="private-project-comparison-data" '
        r'type="application/json">(.*?)</script>',
        private_source,
        flags=re.DOTALL,
    )
    if not private_match:
        failures.append("private project explorer bootstrap JSON is missing")
    else:
        try:
            bootstrap = json.loads(private_match.group(1))
        except json.JSONDecodeError as exc:
            failures.append(f"private project explorer bootstrap JSON is invalid: {exc}")
        else:
            if not isinstance(bootstrap, list) or len(bootstrap) > 100:
                failures.append(
                    "private project explorer must inline at most 100 bootstrap rows"
                )

    for file_name, maximum in PROJECT_OPTION_BUDGETS.items():
        source = (site_root / file_name).read_text(encoding="utf-8")
        match = re.search(
            r'<datalist id="project-options">(.*?)</datalist>',
            source,
            flags=re.DOTALL,
        )
        if not match:
            failures.append(f"{file_name} project datalist is missing")
            continue
        option_count = len(re.findall(r"<option\b", match.group(1)))
        if option_count > maximum:
            failures.append(
                f"{file_name} inlines {option_count} project options; budget is {maximum}"
            )
    if failures:
        raise ValueError("Report performance budgets failed:\n" + "\n".join(failures))


def validate_project_catalog_consumer_references(
    site_root: Path,
    *,
    assets_dir: Path,
) -> None:
    """Require every project tool to request the same immutable catalog URL."""

    transaction_manifest = _load_json_object(
        assets_dir / "condo-transactions" / "manifest.json",
        label="transaction manifest",
    )
    catalog = project_catalog_data.load_project_catalog(
        assets_dir / "project-catalog" / "manifest.json",
        transaction_manifest=transaction_manifest,
    )
    expected_path = project_catalog_data.catalog_asset_path(
        catalog["catalog_revision"]
    )
    failures: list[str] = []
    for file_name in REPORT_HTML_BUDGETS:
        source = (site_root / file_name).read_text(encoding="utf-8")
        if expected_path not in source:
            failures.append(f"{file_name} does not reference {expected_path}")
        if catalog["catalog_revision"] not in source:
            failures.append(
                f"{file_name} does not embed catalog revision "
                f"{catalog['catalog_revision']}"
            )
    if failures:
        raise ValueError(
            "Project catalog consumer references failed:\n" + "\n".join(failures)
        )


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


def _catalog_token(value: object, *, field: str) -> str:
    """Return one normalized catalog token or fail instead of aliasing it."""

    if not isinstance(value, str) or not REPORT_TOKEN_RE.fullmatch(value):
        raise ValueError(
            f"{field} must be a normalized lowercase URL-safe token: {value!r}"
        )
    return value


def _captured_datetime(report: dict, *, position: int) -> datetime:
    value = report.get("captured_at")
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"reports[{position}].captured_at must be a non-empty ISO timestamp"
        )
    try:
        captured = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"reports[{position}].captured_at must be an ISO timestamp"
        ) from exc
    if captured.utcoffset() is None:
        raise ValueError(
            f"reports[{position}].captured_at must include a UTC offset"
        )
    return captured


def _validated_library_groups(catalog: dict) -> list[list[dict]]:
    """Validate and group only dated property-analysis histories."""

    reports = catalog.get("reports")
    if not isinstance(reports, list):
        raise ValueError("Merged report catalog reports must be a list")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    standalone: list[tuple[int, list[dict]]] = []
    property_groups: dict[str, list[tuple[int, datetime, dict]]] = {}
    first_property_position: dict[str, int] = {}

    for position, report in enumerate(reports):
        if not isinstance(report, dict):
            raise ValueError(f"reports[{position}] must be an object")
        report_id = report.get("id")
        if not isinstance(report_id, str) or not report_id.strip():
            raise ValueError(f"reports[{position}].id must be a non-empty string")
        if report_id in seen_ids:
            raise ValueError(f"Duplicate merged report id: {report_id}")
        seen_ids.add(report_id)
        relative_path = _safe_relative_file(
            report.get("path"), field=f"reports[{position}].path"
        )
        if relative_path.suffix != ".html" or relative_path.name == "index.html":
            raise ValueError(
                f"reports[{position}].path must name a non-index HTML file"
            )
        normalized_path = relative_path.as_posix()
        if normalized_path in seen_paths:
            raise ValueError(f"Duplicate merged report path: {normalized_path}")
        seen_paths.add(normalized_path)
        for field in ("title", "summary", "kind"):
            if not isinstance(report.get(field), str) or not report[field].strip():
                raise ValueError(
                    f"reports[{position}].{field} must be a non-empty string"
                )
        _catalog_token(report.get("category"), field=f"reports[{position}].category")
        tags = report.get("tags")
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise ValueError(f"reports[{position}].tags must be a list of strings")
        validate_data_families(
            report.get("data_families"),
            source=f"reports[{position}].data_families",
        )
        featured = report.get("featured", False)
        if not isinstance(featured, bool):
            raise ValueError(f"reports[{position}].featured must be a boolean")
        if "captured_at" in report:
            _captured_datetime(report, position=position)

        if report["kind"] != "property-analysis":
            standalone.append((position, [report]))
            continue

        project_slug = _catalog_token(
            report.get("project_slug"),
            field=f"reports[{position}].project_slug",
        )
        if not isinstance(report.get("project_name"), str) or not report[
            "project_name"
        ].strip():
            raise ValueError(
                f"reports[{position}].project_name must be a non-empty string"
            )
        if report.get("category") != "property-analysis":
            raise ValueError(
                f"reports[{position}] property analysis must use "
                "category 'property-analysis'"
            )
        if not isinstance(report.get("is_latest"), bool):
            raise ValueError(f"reports[{position}].is_latest must be a boolean")
        captured = _captured_datetime(report, position=position)
        group = property_groups.setdefault(project_slug, [])
        if any(existing_capture == captured for _, existing_capture, _ in group):
            raise ValueError(
                f"Property analysis {project_slug!r} repeats captured_at {captured.isoformat()}"
            )
        group.append((position, captured, report))
        first_property_position.setdefault(project_slug, position)

    grouped: list[tuple[int, list[dict]]] = list(standalone)
    for project_slug, captures in property_groups.items():
        captures.sort(key=lambda item: (-item[1].timestamp(), item[2]["path"]))
        latest = [item for item in captures if item[2]["is_latest"]]
        if len(latest) != 1:
            raise ValueError(
                f"Property analysis {project_slug!r} must declare exactly one latest capture"
            )
        if latest[0][1] != captures[0][1]:
            raise ValueError(
                f"Property analysis {project_slug!r} latest capture is not the newest"
            )
        project_names = {
            " ".join(item[2]["project_name"].split()).casefold()
            for item in captures
        }
        if len(project_names) != 1:
            raise ValueError(
                f"Property analysis {project_slug!r} uses inconsistent project names"
            )
        grouped.append(
            (
                first_property_position[project_slug],
                [captures[0][2], *(item[2] for item in captures[1:])],
            )
        )

    # Featured authored reports lead the default preview. Within each tier, retain
    # the merged catalog's stable order; a property group uses its first occurrence.
    grouped.sort(
        key=lambda item: (
            not bool(item[1][0].get("featured", False)),
            item[0],
        )
    )
    return [group for _, group in grouped]


def _report_freshness(report: dict) -> str:
    # A report-specific capture is the only honest library freshness datum.
    # Family coverage and build timestamps answer different questions.
    return "dated" if report.get("captured_at") else "unknown"


def _report_search_text(report: dict) -> str:
    values: list[str] = [
        report["title"],
        report["summary"],
        report["path"],
        report["category"],
        report["kind"],
        *report["tags"],
    ]
    for field in (
        "project_name",
        "project_slug",
        "market_stage",
        "captured_at",
    ):
        value = report.get(field)
        if isinstance(value, str) and value:
            values.append(value)
    project_names = report.get("project_names", [])
    if isinstance(project_names, list):
        values.extend(value for value in project_names if isinstance(value, str))
    return " ".join(" ".join(values).split()).casefold()


def _evidence_tokens(report: dict) -> str:
    return " ".join(report["data_families"])


def _card_tag(report: dict) -> str:
    if report["kind"] == "property-analysis":
        captured = _captured_datetime(report, position=0).strftime("%d %b %Y")
        market_stage = str(report.get("market_stage") or "property research").title()
        return f"Property analysis · {market_stage} · {captured} · Latest"
    category = report["category"].replace("-", " ").title()
    kind = report["kind"].replace("-", " ").title()
    return f"{category} · {kind}"


def _render_history_link(report: dict) -> str:
    captured = _captured_datetime(report, position=0)
    captured_label = captured.strftime("%d %b %Y")
    path = escape(report["path"], quote=True)
    return (
        "          <li>"
        f'<a class="report-history-link" href="{path}" '
        f'data-report-id="{escape(report["id"], quote=True)}" '
        f'data-report-path="{path}" '
        f'data-search="{escape(_report_search_text(report), quote=True)}" '
        f'data-freshness="{_report_freshness(report)}" '
        f'data-evidence-family="{escape(_evidence_tokens(report), quote=True)}">'
        f"{escape(report['title'])} · {escape(captured_label)}"
        "</a></li>"
    )


def _render_report_card(group: list[dict]) -> str:
    report = group[0]
    path = escape(report["path"], quote=True)
    classes = ["card", "report-card"]
    if report.get("featured") is True:
        classes.append("featured")
    if report["kind"] == "property-analysis":
        classes.append("property-analysis-card")
    attributes = [
        f'class="{" ".join(classes)}"',
        f'data-report-id="{escape(report["id"], quote=True)}"',
        f'data-report-path="{path}"',
        f'data-category="{escape(report["category"], quote=True)}"',
        f'data-search="{escape(_report_search_text(report), quote=True)}"',
        f'data-freshness="{_report_freshness(report)}"',
        f'data-evidence-family="{escape(_evidence_tokens(report), quote=True)}"',
    ]
    if report["kind"] == "property-analysis":
        attributes.extend(
            (
                'data-kind="analysis project"',
                f'data-project-slug="{escape(report["project_slug"], quote=True)}"',
            )
        )
    else:
        attributes.append(
            f'data-kind="{escape(report["kind"], quote=True)}"'
        )
    lines = [
        f"      <article {' '.join(attributes)}>",
        f'        <a class="report-primary-link" href="{path}">',
        f'          <span class="tag">{escape(_card_tag(report))}</span>',
        f"          <h3>{escape(report['title'])}</h3>",
        f"          <p>{escape(report['summary'])}</p>",
        '          <span class="open">Open report →</span>',
        "        </a>",
    ]
    history = group[1:]
    if history:
        noun = "snapshot" if len(history) == 1 else "snapshots"
        lines.extend(
            (
                '        <div class="report-history">',
                "          <details>",
                "            <summary>"
                f'<span class="report-history-count">{len(history)} earlier {noun}</span>'
                "</summary>",
                '            <ul class="report-history-list">',
                *(_render_history_link(item) for item in history),
                "            </ul>",
                "          </details>",
                "        </div>",
            )
        )
    lines.append("      </article>")
    return "\n".join(lines)


def render_report_library(catalog: dict) -> str:
    """Render every merged report once, grouping only older dated captures."""

    return "\n".join(
        _render_report_card(group) for group in _validated_library_groups(catalog)
    )


def _property_cards(analyses: list[PropertyAnalysis]) -> str:
    """Compatibility helper rendering generated analyses through the catalog path."""

    return render_report_library(
        {
            "reports": property_catalog_entries(analyses),
        }
    )


def build_project_report_routes(
    catalog: dict,
    analyses: list[PropertyAnalysis],
) -> list[dict[str, object]]:
    """Return registry route descriptors for authored and generated reports."""

    latest_ids = {
        analysis.report_id for analysis in latest_property_analyses(analyses)
    }
    routes: list[dict[str, object]] = []
    for report in catalog["reports"]:
        for project_name in report.get("project_names", []):
            project_slug = re.sub(
                r"[^a-z0-9]+", "-", project_name.casefold()
            ).strip("-")
            routes.append(
                {
                    "project_name": project_name,
                    "project_slug": project_slug,
                    "path": report["path"],
                    "source": "authored_report",
                    "is_latest": True,
                    "street": None,
                    "district": None,
                    "planning_area": None,
                }
            )
    for analysis in analyses:
        routes.append(
            {
                "project_name": analysis.project_name,
                "project_slug": analysis.project_slug,
                "path": analysis.output_path,
                "source": "property_analysis",
                "is_latest": analysis.report_id in latest_ids,
                "street": None,
                "district": None,
                "planning_area": None,
            }
        )
    return routes


def _replace_marker_region(
    source: str,
    *,
    start_marker: str,
    end_marker: str,
    replacement: str,
    label: str,
) -> str:
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise ValueError(f"Landing page must contain exactly one {label} marker region")
    start = source.index(start_marker)
    end = source.index(end_marker)
    if end < start:
        raise ValueError(f"Landing page {label} markers are reversed")
    end += len(end_marker)
    return (
        source[:start]
        + start_marker
        + "\n"
        + replacement
        + "\n"
        + end_marker
        + source[end:]
    )


def _category_options(catalog: dict) -> str:
    groups = _validated_library_groups(catalog)
    categories = sorted({group[0]["category"] for group in groups})
    lines = ['          <option value="all">All categories</option>']
    for category in categories:
        label = category.replace("-", " ").title()
        lines.append(
            f'          <option value="{escape(category, quote=True)}">'
            f"{escape(label)}</option>"
        )
    return "\n".join(lines)


def build_report_library_config(catalog: dict) -> dict:
    """Build exact dedicated-district finder routes from catalog identifiers."""

    # Validate the complete library before deriving a partial route view.
    _validated_library_groups(catalog)
    district_routes: dict[str, str] = {}
    for position, report in enumerate(catalog["reports"]):
        if report["kind"] == "property-analysis" or report["category"] != "district":
            continue
        match = DISTRICT_REPORT_ID_RE.fullmatch(report["id"])
        if not match:
            continue
        district = str(int(match.group("district")))
        relative_path = _safe_relative_file(
            report["path"], field=f"reports[{position}].path"
        )
        if relative_path.suffix != ".html" or relative_path.name == "index.html":
            raise ValueError(f"District route must name a non-index HTML file: {relative_path}")
        route_path = relative_path.as_posix()
        existing = district_routes.setdefault(district, route_path)
        if existing != route_path:
            raise ValueError(
                f"Conflicting dedicated report routes for District {district}: "
                f"{existing!r} and {route_path!r}"
            )
    return {
        "schema_version": REPORT_LIBRARY_CONFIG_SCHEMA,
        "district_routes": dict(
            sorted(district_routes.items(), key=lambda item: int(item[0]))
        ),
    }


def inject_report_library(index_path: Path, catalog: dict) -> None:
    """Inject catalog-derived cards, category options and finder configuration."""

    source = index_path.read_text(encoding="utf-8")
    source = _replace_marker_region(
        source,
        start_marker=REPORT_LIBRARY_START_MARKER,
        end_marker=REPORT_LIBRARY_END_MARKER,
        replacement=render_report_library(catalog),
        label="report-library",
    )
    source = _replace_marker_region(
        source,
        start_marker=REPORT_CATEGORY_OPTIONS_START_MARKER,
        end_marker=REPORT_CATEGORY_OPTIONS_END_MARKER,
        replacement=_category_options(catalog),
        label="report-category-options",
    )
    encoded_config = json.dumps(
        build_report_library_config(catalog),
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    config_script = (
        '<script type="application/json" id="report-library-config">'
        f"{encoded_config}</script>"
    )
    source = _replace_marker_region(
        source,
        start_marker=REPORT_LIBRARY_CONFIG_START_MARKER,
        end_marker=REPORT_LIBRARY_CONFIG_END_MARKER,
        replacement=config_script,
        label="report-library-config",
    )
    index_path.write_text(source, encoding="utf-8")


def inject_property_library(index_path: Path, analyses: list[PropertyAnalysis]) -> None:
    """Compatibility wrapper for legacy analysis-only publication fixtures."""

    source = index_path.read_text(encoding="utf-8")
    cards = _property_cards(analyses)
    if source.count(PROPERTY_CARDS_MARKER) == 1:
        index_path.write_text(
            source.replace(PROPERTY_CARDS_MARKER, cards), encoding="utf-8"
        )
        return
    if (
        source.count(REPORT_LIBRARY_START_MARKER) == 1
        and source.count(REPORT_LIBRARY_END_MARKER) == 1
    ):
        index_path.write_text(
            _replace_marker_region(
                source,
                start_marker=REPORT_LIBRARY_START_MARKER,
                end_marker=REPORT_LIBRARY_END_MARKER,
                replacement=cards,
                label="report-library",
            ),
            encoding="utf-8",
        )
        return
    raise ValueError(f"{index_path.name} has no supported report publication marker")


def validate_project_identity_registry_assets(assets_dir: Path) -> dict:
    """Validate the root and immutable canonical project registry assets."""

    registry_dir = assets_dir / "project-identity-registry"
    registry = project_registry_data.load_project_identity_registry(
        registry_dir / "manifest.json",
    )
    relative = PurePosixPath(
        project_registry_data.registry_asset_path(registry["registry_revision"])
    )
    immutable = assets_dir.joinpath(*relative.parts[1:])
    immutable_registry = project_registry_data.load_project_identity_registry(
        immutable,
    )
    if immutable_registry != registry:
        raise ValueError(
            "Immutable project identity registry differs from its root manifest"
        )
    return registry


def validate_project_registry_report_routes(
    registry: dict,
    catalog: dict,
    analyses: list[PropertyAnalysis],
) -> None:
    """Reconcile route ownership as well as aggregate path metadata."""

    expected = Counter()
    for route in build_project_report_routes(catalog, analyses):
        source_key = f"{route['path']}#{route['project_slug']}"
        expected[
            (source_key, route["path"], route["source"], route["is_latest"])
        ] += 1

    actual = Counter()
    for record in registry["records"]:
        for route in record["capabilities"]["dedicated_report"]["routes"]:
            source = route["source"]
            source_keys = record["sources"].get(source)
            if not isinstance(source_keys, list):
                raise ValueError(
                    f"Project registry route source {source!r} has no source-key list"
                )
            path_prefix = f"{route['path']}#"
            matching_keys = [
                source_key
                for source_key in source_keys
                if isinstance(source_key, str) and source_key.startswith(path_prefix)
            ]
            if len(matching_keys) != 1:
                raise ValueError(
                    "Project registry dedicated-report route does not have exactly "
                    f"one same-record source key: {record['id']} {route['path']}"
                )
            actual[
                (
                    matching_keys[0],
                    route["path"],
                    source,
                    route["is_latest"],
                )
            ] += 1
    if actual != expected:
        raise ValueError(
            "Project registry dedicated-report route ownership differs from report metadata"
        )


def inject_project_registry_config(index_path: Path, registry: dict) -> None:
    """Embed the immutable registry path and revision into the landing page."""

    source = index_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(<script type="application/json" id="{PROJECT_REGISTRY_CONFIG_ID}">)'
        r".*?(</script>)",
        flags=re.DOTALL,
    )
    if len(pattern.findall(source)) != 1:
        raise ValueError(
            f"{index_path.name} must contain exactly one {PROJECT_REGISTRY_CONFIG_ID}"
        )
    config = {
        "schema": registry["schema"],
        "revision": registry["registry_revision"],
        "path": project_registry_data.registry_asset_path(
            registry["registry_revision"]
        ),
        "counts": registry["counts"],
        "bootstrap": project_registry_bootstrap_records(registry),
    }
    encoded = json.dumps(config, ensure_ascii=True, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c")
    index_path.write_text(
        pattern.sub(rf"\g<1>{encoded}\g<2>", source),
        encoding="utf-8",
    )


def project_registry_bootstrap_records(registry: dict) -> list[dict]:
    """Return exact registry records used when the immutable asset is unavailable."""

    records_by_id = {record["id"]: record for record in registry["records"]}
    missing = [
        project_id
        for project_id in PROJECT_REGISTRY_BOOTSTRAP_IDS
        if project_id not in records_by_id
    ]
    if missing:
        raise ValueError(
            "Project identity registry is missing landing bootstrap identities: "
            + ", ".join(missing)
        )
    return [records_by_id[project_id] for project_id in PROJECT_REGISTRY_BOOTSTRAP_IDS]


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
    data_status = build_data_status()
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
    for report in catalog["reports"]:
        relative_path = _safe_relative_file(
            report["path"], field=f"catalog report {report['id']!r}.path"
        )
        if len(relative_path.parts) == 1:
            continue
        destination = output_dir.joinpath(*relative_path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT.joinpath(*relative_path.parts), destination)
    for relative_path, page in rendered_pages.items():
        (output_dir / relative_path).write_text(page, encoding="utf-8")
    (output_dir / "reports.json").write_text(
        json.dumps(merged_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "data-status.json").write_text(
        json.dumps(data_status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if assets_dir.is_dir():
        shutil.copytree(
            assets_dir,
            output_dir / "assets",
            dirs_exist_ok=True,
        )
    validate_transaction_assets(output_dir / "assets")
    validate_project_catalog_assets(output_dir / "assets")
    project_registry = validate_project_identity_registry_assets(
        output_dir / "assets"
    )
    validate_project_registry_report_routes(
        project_registry,
        catalog,
        analyses,
    )
    validate_report_performance_budgets(output_dir)
    if assets_dir.resolve() == DEFAULT_ASSETS.resolve():
        validate_project_catalog_consumer_references(
            output_dir,
            assets_dir=output_dir / "assets",
        )
    inject_report_library(output_dir / "index.html", merged_catalog)
    inject_project_registry_config(output_dir / "index.html", project_registry)
    inject_data_status(output_dir / "index.html", data_status)
    inject_research_shell(
        output_dir,
        catalog=merged_catalog,
        data_status=data_status,
    )
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
        data_status = build_data_status()
        validate_transaction_assets(DEFAULT_ASSETS)
        validate_project_catalog_assets(DEFAULT_ASSETS)
        project_registry = validate_project_identity_registry_assets(DEFAULT_ASSETS)
        validate_project_registry_report_routes(
            project_registry,
            catalog,
            analyses,
        )
        validate_report_performance_budgets(ROOT)
        validate_project_catalog_consumer_references(
            ROOT,
            assets_dir=DEFAULT_ASSETS,
        )
        print(
            f"Validated {len(merged_catalog['reports'])} research reports "
            f"({len(analyses)} dated property analyses) and "
            f"{project_registry['counts']['records']} project identities; "
            f"source status covers {len(data_status['datasets'])} datasets."
        )
    else:
        count = build_site(args.out)
        print(f"Built {count} research reports in {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
