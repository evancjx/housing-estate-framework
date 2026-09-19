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

After download, reconcile the attempt manifest into a run-scoped candidate.
Canonical publication requires a separate manual review and explicit promotion;
see scrapers/README.md. Existing raw files are never treated as evidence that a
requested partition completed.
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sg_estate.contracts import ContractError
from sg_estate.scrape_generation import (
    load_generation,
    new_generation,
    pending_partition_ids,
    record_attempt,
    write_generation,
)

try:
    from scrapers.ura_pmi_playwright import (
        PROP_TYPE_MAP,
        PORTAL_URL,
        atomic_write_json,
        build_attempt_manifest,
        new_attempt,
        normalize_prop_types,
        raw_filename,
        utc_now,
    )
except ModuleNotFoundError:
    from ura_pmi_playwright import (
        PROP_TYPE_MAP,
        PORTAL_URL,
        atomic_write_json,
        build_attempt_manifest,
        new_attempt,
        normalize_prop_types,
        raw_filename,
        utc_now,
    )

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

GENERATION_SOURCE = "ura_pmi"
_GENERATION_OBSERVATION_KEY = "ura_attempt_v1"


def generation_scope(
    districts: list[str],
    prop_types: list[str],
    *,
    year_from: str,
    month_from: str,
    year_to: str,
    month_to: str,
    sale_types: list[str],
) -> dict[str, object]:
    """Translate the exact DATA-103 request into the generic checkpoint scope."""

    normalized_districts = sorted({str(value).zfill(2) for value in districts})
    normalized_types = sorted(set(normalize_prop_types(prop_types)))
    normalized_sales = sorted(set(sale_types))
    parameters = {
        "artifact_schema": "ura-pmi-attempt-manifest.v1",
        "districts": normalized_districts,
        "property_types": normalized_types,
        "sale_types": normalized_sales,
        "year_from": str(int(year_from)),
        "month_from": str(int(month_from)),
        "year_to": str(int(year_to)),
        "month_to": str(int(month_to)),
    }
    partitions = []
    for district in normalized_districts:
        for prop_type in normalized_types:
            identity = f"d{district}-p{prop_type}"
            query = urlencode(
                {
                    "district": district,
                    "property_type": prop_type,
                    "sale_types": ",".join(normalized_sales),
                    "from": f"{parameters['year_from']}-{int(parameters['month_from']):02d}",
                    "to": f"{parameters['year_to']}-{int(parameters['month_to']):02d}",
                }
            )
            partitions.append(
                {
                    "partition_id": identity,
                    "name": f"URA PMI D{district} / {PROP_TYPE_MAP[prop_type]}",
                    "source_url": f"{PORTAL_URL}?{query}",
                    "source_slug": identity,
                }
            )
    return {
        "project_catalog": None,
        "partitions": partitions,
        "parameters": parameters,
    }


def _generation_manifest_path(
    selected_manifest: Path,
    requested: str | None,
) -> Path:
    path = (
        Path(requested)
        if requested
        else selected_manifest.with_name(
            f"{selected_manifest.stem}.generation{selected_manifest.suffix}"
        )
    )
    if path.resolve().parent != selected_manifest.resolve().parent:
        raise ValueError(
            "--generation-manifest must be alongside --attempt-manifest so both "
            "sidecars resolve the same run-scoped artifacts"
        )
    if path.resolve() == selected_manifest.resolve():
        raise ValueError(
            "--generation-manifest and --attempt-manifest must be different files"
        )
    return path


def _open_generation(
    path: Path,
    scope: dict[str, object],
    *,
    generation_id: str | None,
) -> dict[str, object]:
    if path.is_file():
        return load_generation(
            path,
            expected_source=GENERATION_SOURCE,
            expected_scope=scope,
            expected_generation_id=generation_id,
        )
    manifest = new_generation(
        GENERATION_SOURCE,
        scope,
        generation_id=generation_id,
    )
    write_generation(path, manifest)
    return manifest


def _pending_groups(
    generation_path: Path,
    districts: list[str],
    prop_types: list[str],
) -> list[tuple[list[str], list[str]]]:
    """Return exact rectangular child scopes without retrying selected pairs."""

    pending = pending_partition_ids(generation_path)
    grouped: dict[tuple[str, ...], list[str]] = {}
    for prop_type in prop_types:
        pending_districts = tuple(
            district
            for district in districts
            if f"d{district}-p{prop_type}" in pending
        )
        if pending_districts:
            grouped.setdefault(pending_districts, []).append(prop_type)
    return [(list(group), types) for group, types in grouped.items()]


def _attempt_observations(
    attempt: dict[str, object],
    source_requests: list[dict[str, object]],
) -> dict[str, object]:
    return {
        _GENERATION_OBSERVATION_KEY: {
            "district": attempt["district"],
            "property_type": attempt["property_type"],
            "property_type_label": attempt["property_type_label"],
            "observations": attempt.get("observations"),
            "source_requests": source_requests,
        }
    }


def _append_child_attempts(
    generation_path: Path,
    child_manifest_path: Path,
    child_manifest: dict[str, object],
) -> None:
    """Append fresh child terminals while selecting only passing current bytes."""

    source_requests = child_manifest.get("source_requests")
    if not isinstance(source_requests, list):
        raise ContractError("URA child source_requests must be a list")
    for value in child_manifest["attempts"]:
        if not isinstance(value, dict):
            raise ContractError("URA child attempt must be an object")
        identity = str(value["partition_id"])
        # A child scope is computed from pending IDs. Recheck after each append
        # so no passing partition can accidentally acquire a second selection.
        if identity not in pending_partition_ids(generation_path):
            continue
        status = str(value["status"])
        artifact = value.get("artifact")
        artifact_path = None
        reported_count = None
        observations = value.get("observations")
        if isinstance(observations, dict):
            reported_count = observations.get("row_count")
        if status == "succeeded":
            if not isinstance(artifact, dict):
                raise ContractError(f"successful URA child attempt {identity} has no artifact")
            relative = artifact.get("relative_path")
            if not isinstance(relative, str):
                raise ContractError(f"URA child attempt {identity} has no artifact path")
            artifact_path = child_manifest_path.parent / relative
        elif status == "confirmed_empty":
            reported_count = 0
        record_attempt(
            generation_path,
            identity,
            method=str(value["method"]),
            status=status,
            started_at=str(value["started_at"]),
            completed_at=str(value["completed_at"]),
            retrieved_at=(
                str(value["completed_at"])
                if status in {"succeeded", "confirmed_empty"}
                else None
            ),
            artifact_path=artifact_path,
            source_reported_row_count=reported_count,
            error_code=value.get("error_code"),
            error_message=value.get("error_message"),
            observations=_attempt_observations(value, source_requests),
            now=str(value["completed_at"]),
        )


def _selected_or_latest_attempt(partition: dict[str, object]) -> dict[str, object]:
    attempts = partition["attempts"]
    if not isinstance(attempts, list) or not attempts:
        raise ContractError(
            f"URA generation partition {partition['partition_id']} has no terminal attempt"
        )
    selected_id = partition["selected_attempt_id"]
    if selected_id is None:
        value = attempts[-1]
    else:
        value = next(
            attempt
            for attempt in attempts
            if isinstance(attempt, dict) and attempt["attempt_id"] == selected_id
        )
    if not isinstance(value, dict):
        raise ContractError("URA generation attempt must be an object")
    return value


def attempt_manifest_from_generation(
    generation_path: str | Path,
    *,
    method_hint: str | None = None,
) -> dict[str, object]:
    """Rebuild the unchanged DATA-103 v1 terminal snapshot from one generation."""

    generation = load_generation(
        generation_path,
        expected_source=GENERATION_SOURCE,
    )
    parameters = generation["requested_scope"]["parameters"]
    if not isinstance(parameters, dict):
        raise ContractError("URA generation parameters must be an object")
    attempts: list[dict[str, object]] = []
    request_groups: list[list[dict[str, object]]] = []
    for partition in generation["partitions"]:
        if not isinstance(partition, dict):
            raise ContractError("URA generation partition must be an object")
        generic_attempt = _selected_or_latest_attempt(partition)
        bridge = generic_attempt["observations"].get(_GENERATION_OBSERVATION_KEY)
        if not isinstance(bridge, dict):
            raise ContractError(
                f"URA generation attempt for {partition['partition_id']} lacks v1 evidence"
            )
        source_requests = bridge.get("source_requests")
        if isinstance(source_requests, list) and source_requests not in request_groups:
            request_groups.append(source_requests)
        attempts.append(
            new_attempt(
                district=str(bridge["district"]),
                prop_type=str(bridge["property_type"]),
                method=str(generic_attempt["method"]),
                status=str(generic_attempt["status"]),
                started_at=str(generic_attempt["started_at"]),
                completed_at=str(generic_attempt["completed_at"]),
                artifact=generic_attempt.get("artifact"),
                observations=bridge.get("observations"),
                error_code=generic_attempt.get("error_code"),
                error_message=generic_attempt.get("error_message"),
            )
        )
    source_requests: list[dict[str, object]] = []
    request_ids: set[str] = set()
    for group_index, group in enumerate(request_groups, start=1):
        for request in group:
            if not isinstance(request, dict):
                raise ContractError("URA generation source request must be an object")
            copied = dict(request)
            identity = str(copied.get("request_id") or "source-request")
            if identity in request_ids:
                identity = f"{identity}-resume-{group_index}"
                copied["request_id"] = identity
            request_ids.add(identity)
            source_requests.append(copied)
    methods = {str(attempt["method"]) for attempt in attempts}
    if len(methods) == 1:
        method = next(iter(methods))
    elif "api" in methods:
        # The unchanged v1 envelope has one legacy top-level method even though
        # its attempts are method-specific. Use a deterministic fallback label;
        # the per-attempt fields remain the acquisition authority.
        method = "api"
    elif method_hint in {"playwright", "api"}:
        method = method_hint
    else:  # pragma: no cover - generic contract currently allows only two methods
        method = str(attempts[-1]["method"])
    completed_at = max(str(attempt["completed_at"]) for attempt in attempts)
    return build_attempt_manifest(
        method=method,
        started_at=str(generation["started_at"]),
        completed_at=completed_at,
        districts=list(parameters["districts"]),
        prop_types=list(parameters["property_types"]),
        year_from=str(parameters["year_from"]),
        month_from=str(parameters["month_from"]),
        year_to=str(parameters["year_to"]),
        month_to=str(parameters["month_to"]),
        sale_types=list(parameters["sale_types"]),
        attempts=attempts,
        source_requests=source_requests,
    )


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
    attempt_manifest: Path | None = None,
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
    if attempt_manifest is not None:
        cmd.extend(["--attempt-manifest", str(attempt_manifest)])
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def run_api_subprocess(
    out_dir: Path,
    prop_types: list[str],
    districts: list[str] | None = None,
    attempt_manifest: Path | None = None,
    year_from: str | None = None,
    year_to: str | None = None,
) -> bool:
    """Run API client as subprocess. Returns True on success."""
    script = Path(__file__).parent / "ura_pmi_api.py"
    cmd = [sys.executable, str(script), "--out_dir", str(out_dir)]
    if districts:
        cmd.extend(["--districts", *districts])
    if prop_types:
        cmd.extend(["--prop_types", *prop_types])
    if year_from is not None:
        cmd.extend(["--year_from", year_from])
    if year_to is not None:
        cmd.extend(["--year_to", year_to])
    if attempt_manifest is not None:
        cmd.extend(["--attempt-manifest", str(attempt_manifest)])
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def _copy_attempt_manifest(source: Path, destination: Path) -> bool:
    """Atomically publish the selected child manifest at the requested path."""
    if not source.is_file():
        return False
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError(f"invalid child attempt manifest: {source}")
    atomic_write_json(destination, value)
    return True


def _write_missing_child_manifest(
    path: Path,
    *,
    method: str,
    districts: list[str],
    prop_types: list[str],
    year_from: str | None,
    year_to: str | None,
) -> None:
    """Replace stale evidence if a child exits before it can write a manifest."""
    started_at = utc_now()
    attempts = [
        new_attempt(
            district=district,
            prop_type=prop_type,
            method=method,
            status="failed",
            started_at=started_at,
            completed_at=utc_now(),
            error_code="subprocess_failed_without_manifest",
            error_message="Downloader exited without a current attempt manifest",
        )
        for district in districts
        for prop_type in prop_types
    ]
    manifest = build_attempt_manifest(
        method=method,
        started_at=started_at,
        completed_at=utc_now(),
        districts=districts,
        prop_types=prop_types,
        year_from=year_from,
        month_from="1" if year_from is not None else None,
        year_to=year_to,
        month_to="12" if year_to is not None else None,
        sale_types=["1", "2", "3"],
        attempts=attempts,
    )
    atomic_write_json(path, manifest)


def _manifest_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _validate_fresh_child_manifest(
    path: Path,
    previous: bytes | None,
    *,
    method: str,
    districts: list[str],
    prop_types: list[str],
    year_from: str,
    year_to: str,
) -> dict[str, object] | None:
    """Accept only a newly written manifest for the exact subprocess scope."""
    current = _manifest_bytes(path)
    if current is None or current == previous:
        return None
    try:
        value = json.loads(current)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    required = {
        "schema_version",
        "source",
        "method",
        "status",
        "started_at",
        "completed_at",
        "requested_scope",
        "source_requests",
        "attempts",
        "summary",
    }
    if set(value) != required:
        return None
    if (
        value.get("schema_version") != 1
        or value.get("source") != "URA PMI"
        or value.get("method") != method
        or value.get("status") not in {"succeeded", "failed"}
    ):
        return None
    scope = value.get("requested_scope")
    if not isinstance(scope, dict):
        return None
    if scope.get("districts") != districts or scope.get("property_types") != prop_types:
        return None
    if scope.get("sale_types") != ["1", "2", "3"]:
        return None
    if (
        scope.get("year_from") != str(int(year_from))
        or scope.get("month_from") != "1"
        or scope.get("year_to") != str(int(year_to))
        or scope.get("month_to") != "12"
    ):
        return None
    attempts = value.get("attempts")
    if not isinstance(attempts, list):
        return None
    expected = {
        (district, prop_type)
        for district in districts
        for prop_type in prop_types
    }
    observed = {
        (attempt.get("district"), attempt.get("property_type"))
        for attempt in attempts
        if isinstance(attempt, dict)
    }
    if observed != expected or len(attempts) != len(expected):
        return None
    statuses = [attempt.get("status") for attempt in attempts]
    if any(status not in {"succeeded", "confirmed_empty", "failed"} for status in statuses):
        return None
    summary = value.get("summary")
    expected_summary = {
        "requested": len(expected),
        "succeeded": statuses.count("succeeded"),
        "confirmed_empty": statuses.count("confirmed_empty"),
        "failed": statuses.count("failed"),
    }
    if summary != expected_summary:
        return None
    expected_status = "failed" if expected_summary["failed"] else "succeeded"
    if value["status"] != expected_status:
        return None
    return value


def _child_manifest_path(
    selected_manifest: Path,
    *,
    method: str,
    separate_method: bool,
    group_index: int,
    group_count: int,
) -> Path:
    if not separate_method and group_count == 1:
        return selected_manifest
    index_suffix = f".{group_index}" if group_count > 1 else ""
    return selected_manifest.with_name(
        f"{selected_manifest.stem}.{method}{index_suffix}{selected_manifest.suffix}"
    )


def _run_pending_method(
    *,
    method: str,
    generation_path: Path,
    selected_manifest: Path,
    districts: list[str],
    prop_types: list[str],
    year_from: str,
    year_to: str,
    out_dir: Path,
    separate_method: bool,
) -> bool:
    """Run one downloader method over exactly the still-pending pairs."""

    groups = _pending_groups(generation_path, districts, prop_types)
    for group_index, (group_districts, group_types) in enumerate(groups, start=1):
        child_path = _child_manifest_path(
            selected_manifest,
            method=method,
            separate_method=separate_method,
            group_index=group_index,
            group_count=len(groups),
        )
        previous_manifest = _manifest_bytes(child_path)
        if method == "playwright":
            process_ok = run_playwright_subprocess(
                group_districts,
                year_from,
                year_to,
                out_dir,
                group_types,
                child_path,
            )
        else:
            process_ok = run_api_subprocess(
                out_dir,
                group_types,
                group_districts,
                child_path,
                year_from,
                year_to,
            )
        child = _validate_fresh_child_manifest(
            child_path,
            previous_manifest,
            method=method,
            districts=group_districts,
            prop_types=group_types,
            year_from=year_from,
            year_to=year_to,
        )
        if child is None or process_ok != (child["status"] == "succeeded"):
            _write_missing_child_manifest(
                child_path,
                method=method,
                districts=group_districts,
                prop_types=group_types,
                year_from=year_from,
                year_to=year_to,
            )
            child = _validate_fresh_child_manifest(
                child_path,
                previous_manifest,
                method=method,
                districts=group_districts,
                prop_types=group_types,
                year_from=year_from,
                year_to=year_to,
            )
            if child is None:
                raise ContractError(
                    f"could not synthesize a current {method} child manifest"
                )
        _append_child_attempts(generation_path, child_path, child)
    return not pending_partition_ids(generation_path)


def main(argv: list[str] | None = None) -> int:
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
        "--attempt-manifest",
        help="Selected structured attempt JSON (default: <out_dir>/ura_pmi_attempts.json)",
    )
    ap.add_argument(
        "--generation-manifest",
        help=(
            "Append-only generic checkpoint beside --attempt-manifest "
            "(default: <attempt stem>.generation.json)"
        ),
    )
    ap.add_argument(
        "--generation-id",
        help="Stable generation ID for a new checkpoint; validated on resume",
    )
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
        help=(
            "Compatibility flag; requested partitions are always rechecked because "
            "an existing raw file is not verified acquisition evidence"
        ),
    )
    args = ap.parse_args(argv)
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

    if not districts:
        print("Nothing to download.")
        return 0

    # Existing raw files are not evidence of a successful acquisition. They
    # never suppress a requested partition; only a validated manifest may do
    # that in a future explicit resume workflow.
    existing = [
        raw_filename(district, args.year_from, args.year_to, prop_type)
        for district in districts
        for prop_type in prop_types
        if (out_dir / raw_filename(
            district, args.year_from, args.year_to, prop_type
        )).is_file()
    ]
    if existing and not args.include_existing:
        print(
            f"Found {len(existing)} existing raw artifact(s); re-requesting them "
            "because file existence is not verified acquisition evidence."
        )

    print(f"Districts to download: {districts}")
    print("Property types: " + ", ".join(PROP_TYPE_MAP[p] for p in prop_types))
    print(f"Output: {out_dir}")
    print()

    selected_manifest = (
        Path(args.attempt_manifest)
        if args.attempt_manifest
        else out_dir / "ura_pmi_attempts.json"
    )
    generation_path = _generation_manifest_path(
        selected_manifest,
        args.generation_manifest,
    )
    districts = sorted(dict.fromkeys(districts))
    prop_types = sorted(dict.fromkeys(prop_types))
    scope = generation_scope(
        districts,
        prop_types,
        year_from=args.year_from,
        month_from="1",
        year_to=args.year_to,
        month_to="12",
        sale_types=["1", "2", "3"],
    )
    _open_generation(
        generation_path,
        scope,
        generation_id=args.generation_id,
    )
    method_hint: str | None = None

    if pending_partition_ids(generation_path) and args.mode in (
        "playwright",
        "both",
        "all",
    ):
        method_hint = "playwright"
        playwright_ok = _run_pending_method(
            method="playwright",
            generation_path=generation_path,
            selected_manifest=selected_manifest,
            districts=districts,
            prop_types=prop_types,
            year_from=args.year_from,
            year_to=args.year_to,
            out_dir=out_dir,
            separate_method=args.mode == "both",
        )
        if not playwright_ok and args.mode == "both":
            print("\nPlaywright scraper left pending partitions. Trying API fallback...")

    if pending_partition_ids(generation_path) and args.mode in ("api", "both"):
        method_hint = "api"
        _run_pending_method(
            method="api",
            generation_path=generation_path,
            selected_manifest=selected_manifest,
            districts=districts,
            prop_types=prop_types,
            year_from=args.year_from,
            year_to=args.year_to,
            out_dir=out_dir,
            separate_method=args.mode == "both",
        )

    snapshot = attempt_manifest_from_generation(
        generation_path,
        method_hint=method_hint,
    )
    atomic_write_json(selected_manifest, snapshot)
    remaining = pending_partition_ids(generation_path)
    print(f"Generation checkpoint: {generation_path}")
    if remaining:
        print(f"Pending partitions: {', '.join(sorted(remaining))}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
