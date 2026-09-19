"""Build and publish the shared private-project browser catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_CATALOG_OUT = ROOT / "site/assets/project-catalog"
DEFAULT_TRANSACTION_MANIFEST = ROOT / "site/assets/condo-transactions/manifest.json"
CATALOG_SCHEMA = "private-project-catalog.v1"
CAPABILITY_KEYS = (
    "private_explorer",
    "framework_comparison",
    "transactions",
    "project_exit",
)
CATALOG_COUNT_KEYS = (
    "all",
    "comparison",
    "transaction",
)
TRANSACTION_PROJECT_FIELDS = (
    "transaction_shard",
    "transaction_count",
    "transaction_first_month",
    "transaction_last_month",
    "transaction_complete_through",
)
CATALOG_ROOT_KEYS = (
    "schema",
    "catalog_revision",
    "transaction_dataset_revision",
    "latest_project_month",
    "counts",
    "projects",
    "contexts",
)
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
MONTH_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    normalized = dict(payload)
    normalized.pop("catalog_revision", None)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Project catalog is not canonical JSON: {exc}") from exc
    return encoded.encode("utf-8")


def _identity_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    def cleaned(*names: str) -> str:
        for name in names:
            value = row.get(name)
            if value is not None and str(value).strip():
                return " ".join(str(value).split()).upper()
        return ""

    district = cleaned("district", "postal_district")
    if district.isdigit():
        district = district.zfill(2)
    return (
        cleaned("project", "project_name", "name"),
        cleaned("street", "street_name"),
        district,
        cleaned("planning_area"),
    )


def _slug(value: object) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return cleaned or "unknown"


def _write_json_file(path: pathlib.Path, payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    )
    with path.open("w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: pathlib.Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def catalog_asset_path(revision: str) -> str:
    """Return the Pages-relative immutable catalog asset path."""
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise ValueError("Project catalog revision must be a lowercase SHA-256 digest")
    return f"assets/project-catalog/{revision}/catalog.json"


def compute_catalog_revision(payload: Mapping[str, Any]) -> str:
    """Return the deterministic catalog revision, excluding the revision field."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def build_project_catalog(
    explorer_rows: Sequence[Mapping[str, Any]],
    comparison_rows: Sequence[Mapping[str, Any]],
    contexts: Mapping[str, Mapping[str, Any]],
    transaction_manifest: Mapping[str, Any],
    *,
    latest_project_month: str | None,
) -> dict[str, Any]:
    """Build the 2,400-row union catalog without mutating caller inputs."""
    transaction_revision = transaction_manifest.get("dataset_revision")
    transaction_projects = transaction_manifest.get("projects")
    if not isinstance(transaction_revision, str) or not REVISION_RE.fullmatch(
        transaction_revision
    ):
        raise ValueError(
            "Transaction manifest dataset_revision must be a lowercase SHA-256 digest"
        )
    if not isinstance(transaction_projects, Mapping):
        raise ValueError("Transaction manifest projects must be an object")

    comparison_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    comparison_ids: set[str] = set()
    for raw in comparison_rows:
        row = dict(raw)
        key = _identity_key(row)
        project_id = str(row.get("id", "")).strip()
        if not all(key) or not project_id:
            raise ValueError("Comparison project identity is incomplete")
        if key in comparison_by_key:
            raise ValueError(f"Duplicate comparison project identity: {key!r}")
        if project_id in comparison_ids:
            raise ValueError(f"Duplicate comparison project id: {project_id}")
        comparison_by_key[key] = row
        comparison_ids.add(project_id)

    if comparison_ids != set(transaction_projects):
        missing = sorted(set(transaction_projects) - comparison_ids)
        extra = sorted(comparison_ids - set(transaction_projects))
        raise ValueError(
            "Comparison and transaction project membership differ "
            f"(missing={missing[:3]}, extra={extra[:3]})"
        )

    catalog_projects: list[dict[str, Any]] = []
    matched: set[tuple[str, str, str, str]] = set()
    generic_ids: Counter[str] = Counter()
    for raw in explorer_rows:
        explorer = dict(raw)
        key = _identity_key(explorer)
        comparison = comparison_by_key.get(key)
        row = dict(explorer)
        if comparison is not None:
            matched.add(key)
            row.update(comparison)
            project_id = str(comparison["id"])
            transaction = transaction_projects.get(project_id)
            if not isinstance(transaction, Mapping):
                raise ValueError(
                    f"Transaction metadata is missing for comparison project {project_id}"
                )
            for field in TRANSACTION_PROJECT_FIELDS:
                row[field] = transaction.get(field)
            row["capabilities"] = {
                "private_explorer": True,
                "framework_comparison": True,
                "transactions": True,
                "project_exit": True,
            }
        else:
            project_name, street, district, planning_area = key
            base_id = (
                f"explorer-{_slug(project_name)}-d{_slug(district)}-"
                f"{_slug(street)}-{_slug(planning_area)}"
            )
            generic_ids[base_id] += 1
            row["id"] = (
                base_id
                if generic_ids[base_id] == 1
                else f"{base_id}-{generic_ids[base_id]}"
            )
            row["selection_label"] = str(
                explorer.get("project") or explorer.get("project_name") or "Unknown project"
            )
            row["context_key"] = None
            for field in TRANSACTION_PROJECT_FIELDS:
                row[field] = None
            row["capabilities"] = {
                "private_explorer": True,
                "framework_comparison": False,
                "transactions": False,
                "project_exit": False,
            }
        catalog_projects.append(row)

    unmatched = sorted(set(comparison_by_key) - matched)
    if unmatched:
        raise ValueError(
            f"Comparison projects are absent from the explorer universe: {unmatched[:3]}"
        )

    catalog_projects.sort(
        key=lambda row: (
            str(row.get("project", "")).upper(),
            str(row.get("district", "")),
            str(row.get("street", "")).upper(),
            str(row["id"]),
        )
    )
    payload: dict[str, Any] = {
        "schema": CATALOG_SCHEMA,
        "catalog_revision": None,
        "transaction_dataset_revision": transaction_revision,
        "latest_project_month": latest_project_month,
        "counts": {
            "all": len(catalog_projects),
            "comparison": len(comparison_ids),
            "transaction": len(transaction_projects),
        },
        "projects": catalog_projects,
        "contexts": {str(key): dict(value) for key, value in contexts.items()},
    }
    payload["catalog_revision"] = compute_catalog_revision(payload)
    validate_project_catalog(payload, transaction_manifest=transaction_manifest)
    return payload


def validate_project_catalog(
    payload: Mapping[str, Any],
    *,
    transaction_manifest: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless the complete catalog contract is internally consistent."""
    if not isinstance(payload, Mapping) or set(payload) != set(CATALOG_ROOT_KEYS):
        raise ValueError(
            "Project catalog root fields must be exactly "
            + ", ".join(CATALOG_ROOT_KEYS)
        )
    if payload.get("schema") != CATALOG_SCHEMA:
        raise ValueError(f"Project catalog schema must be {CATALOG_SCHEMA}")
    revision = payload.get("catalog_revision")
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise ValueError("Project catalog revision must be a lowercase SHA-256 digest")
    if compute_catalog_revision(payload) != revision:
        raise ValueError("Project catalog revision does not match normalized contents")
    transaction_revision = payload.get("transaction_dataset_revision")
    if not isinstance(transaction_revision, str) or not REVISION_RE.fullmatch(
        transaction_revision
    ):
        raise ValueError(
            "Project catalog transaction_dataset_revision must be a SHA-256 digest"
        )
    latest = payload.get("latest_project_month")
    if latest is not None and (
        not isinstance(latest, str) or not MONTH_RE.fullmatch(latest)
    ):
        raise ValueError("Project catalog latest_project_month must be YYYY-MM or null")

    counts = payload.get("counts")
    projects = payload.get("projects")
    contexts = payload.get("contexts")
    if not isinstance(counts, Mapping) or set(counts) != set(CATALOG_COUNT_KEYS):
        raise ValueError("Project catalog counts have unexpected fields")
    if any(type(counts[key]) is not int or counts[key] < 0 for key in counts):
        raise ValueError("Project catalog counts must be non-negative integers")
    if not isinstance(projects, list) or not projects:
        raise ValueError("Project catalog projects must be a non-empty array")
    if not isinstance(contexts, Mapping):
        raise ValueError("Project catalog contexts must be an object")
    if any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, Mapping)
        for key, value in contexts.items()
    ):
        raise ValueError("Project catalog context entries must be named objects")

    transaction_projects: Mapping[str, Any] | None = None
    if transaction_manifest is not None:
        if transaction_manifest.get("dataset_revision") != transaction_revision:
            raise ValueError("Project catalog and transaction revisions differ")
        candidate = transaction_manifest.get("projects")
        if not isinstance(candidate, Mapping):
            raise ValueError("Transaction manifest projects must be an object")
        transaction_projects = candidate

    ids: set[str] = set()
    used_contexts: set[str] = set()
    comparison_ids: set[str] = set()
    transaction_ids: set[str] = set()
    sort_keys: list[tuple[str, str, str, str]] = []
    for index, row in enumerate(projects):
        if not isinstance(row, Mapping):
            raise ValueError(f"Project catalog projects[{index}] must be an object")
        project_id = row.get("id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError(f"Project catalog projects[{index}].id is invalid")
        if project_id in ids:
            raise ValueError(f"Project catalog contains duplicate id {project_id}")
        ids.add(project_id)
        if not isinstance(row.get("selection_label"), str) or not row[
            "selection_label"
        ].strip():
            raise ValueError(f"Project catalog {project_id} selection_label is invalid")
        capabilities = row.get("capabilities")
        if not isinstance(capabilities, Mapping) or set(capabilities) != set(
            CAPABILITY_KEYS
        ):
            raise ValueError(f"Project catalog {project_id} capabilities are invalid")
        if any(not isinstance(capabilities[key], bool) for key in CAPABILITY_KEYS):
            raise ValueError(f"Project catalog {project_id} capabilities must be boolean")
        if not capabilities["private_explorer"]:
            raise ValueError(f"Project catalog {project_id} is not explorer-capable")
        if capabilities["transactions"] != capabilities["project_exit"]:
            raise ValueError(
                f"Project catalog {project_id} transaction/exit capabilities differ"
            )
        if capabilities["transactions"] and not capabilities["framework_comparison"]:
            raise ValueError(
                f"Project catalog {project_id} has transactions without comparison"
            )
        context_key = row.get("context_key")
        if capabilities["framework_comparison"]:
            comparison_ids.add(project_id)
            if (
                not isinstance(context_key, str)
                or not context_key.strip()
                or context_key not in contexts
            ):
                raise ValueError(f"Project catalog {project_id} context is missing")
            used_contexts.add(context_key)
        elif context_key is not None:
            raise ValueError(
                f"Explorer-only project {project_id} must not claim framework context"
            )

        missing_transaction_fields = [
            field for field in TRANSACTION_PROJECT_FIELDS if field not in row
        ]
        if missing_transaction_fields:
            raise ValueError(
                f"Project catalog {project_id} is missing transaction fields: "
                + ", ".join(missing_transaction_fields)
            )
        if capabilities["transactions"]:
            transaction_ids.add(project_id)
            if transaction_projects is not None:
                expected = transaction_projects.get(project_id)
                if not isinstance(expected, Mapping):
                    raise ValueError(
                        f"Project catalog transaction id {project_id} is not manifested"
                    )
                for field in TRANSACTION_PROJECT_FIELDS:
                    if row.get(field) != expected.get(field):
                        raise ValueError(
                            f"Project catalog {project_id}.{field} differs from manifest"
                        )
            shard = row.get("transaction_shard")
            expected_path = re.compile(
                rf"assets/condo-transactions/{re.escape(transaction_revision)}/"
                r"shard-(?:[0-5][0-9]|6[0-3])\.json"
            )
            if not isinstance(shard, str) or not expected_path.fullmatch(shard):
                raise ValueError(
                    f"Project catalog {project_id} transaction shard is not revisioned"
                )
            if type(row.get("transaction_count")) is not int or row[
                "transaction_count"
            ] < 0:
                raise ValueError(
                    f"Project catalog {project_id} transaction_count is invalid"
                )
        elif any(row.get(field) is not None for field in TRANSACTION_PROJECT_FIELDS):
            raise ValueError(
                f"Explorer-only project {project_id} has transaction metadata"
            )
        sort_keys.append(
            (
                str(row.get("project", "")).upper(),
                str(row.get("district", "")),
                str(row.get("street", "")).upper(),
                project_id,
            )
        )

    if sort_keys != sorted(sort_keys):
        raise ValueError("Project catalog projects are not in canonical order")
    if used_contexts != set(contexts):
        raise ValueError("Project catalog contains missing or unused framework contexts")
    expected_counts = {
        "all": len(projects),
        "comparison": len(comparison_ids),
        "transaction": len(transaction_ids),
    }
    if dict(counts) != expected_counts:
        raise ValueError(
            f"Project catalog counts do not reconcile: {dict(counts)!r} != "
            f"{expected_counts!r}"
        )
    if transaction_projects is not None and transaction_ids != set(transaction_projects):
        raise ValueError("Project catalog transaction membership does not reconcile")


def publish_project_catalog(
    output_dir: pathlib.Path | str,
    payload: Mapping[str, Any],
    *,
    transaction_manifest: Mapping[str, Any] | None = None,
) -> list[pathlib.Path]:
    """Publish an immutable revision, then atomically switch the root manifest."""
    materialized = dict(payload)
    validate_project_catalog(materialized, transaction_manifest=transaction_manifest)
    output = pathlib.Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    revision = str(materialized["catalog_revision"])
    revision_dir = output / revision
    staging = output.parent / f".{output.name}.stage-{revision[:12]}-{uuid.uuid4().hex}"
    root_temp: pathlib.Path | None = None
    published: list[pathlib.Path] = []
    try:
        staging.mkdir()
        staged_catalog = staging / "catalog.json"
        _write_json_file(staged_catalog, materialized)
        staged_payload = load_project_catalog(
            staged_catalog, transaction_manifest=transaction_manifest
        )
        if staged_payload != materialized:
            raise ValueError("Staged project catalog bytes did not round-trip")
        _fsync_dir(staging)

        if revision_dir.exists():
            existing = load_project_catalog(
                revision_dir / "catalog.json",
                transaction_manifest=transaction_manifest,
            )
            if existing != materialized:
                raise ValueError(
                    f"Immutable project catalog revision already differs: {revision}"
                )
            shutil.rmtree(staging)
        else:
            os.replace(staging, revision_dir)
            _fsync_dir(output)
        published.append(revision_dir / "catalog.json")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".manifest.", suffix=".json", dir=output
        )
        root_temp = pathlib.Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                materialized,
                handle,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        reloaded_root = load_project_catalog(
            root_temp, transaction_manifest=transaction_manifest
        )
        if reloaded_root != materialized:
            raise ValueError("Root project catalog manifest did not round-trip")
        root_manifest = output / "manifest.json"
        os.replace(root_temp, root_manifest)
        root_temp = None
        _fsync_dir(output)
        published.append(root_manifest)
        return published
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if root_temp is not None and root_temp.exists():
            root_temp.unlink()


def load_project_catalog(
    path: pathlib.Path | str,
    *,
    transaction_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate a catalog JSON document."""
    source = pathlib.Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load project catalog {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Project catalog {source} must contain a JSON object")
    validate_project_catalog(payload, transaction_manifest=transaction_manifest)
    return payload


def comparison_projects(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract comparison-capable records in canonical catalog order."""
    return [
        dict(project)
        for project in payload.get("projects", [])
        if project.get("capabilities", {}).get("framework_comparison") is True
    ]


def explorer_projects(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract private-explorer-capable records in canonical catalog order."""
    return [
        dict(project)
        for project in payload.get("projects", [])
        if project.get("capabilities", {}).get("private_explorer") is True
    ]


def build_committed_catalog() -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the union payload from the repository's reviewed, committed inputs."""
    import gen_condo_framework_comparison_html as comparison
    import gen_private_project_comparison_html as explorer

    private = explorer.load_private(explorer.ROOT / "data/inputs/ura_private.csv")
    aggregate_rows = explorer.aggregate_projects(
        private,
        pd.read_csv(explorer.ROOT / "data/inputs/estates.csv"),
        pd.read_csv(explorer.ROOT / "data/inputs/mrt_layer.csv"),
        pd.read_csv(explorer.ROOT / "data/outputs/master_output.csv").set_index(
            "estate"
        ),
        explorer.load_project_locations(explorer.DEFAULT_LOCATION_PATH),
        explorer.load_school_metrics(explorer.DEFAULT_SCHOOL_METRICS_PATH),
    )
    prepared, latest_month = comparison.load_projects_for_comparison()
    browser_projects, contexts = comparison.build_browser_payload(prepared)
    try:
        transaction_manifest = json.loads(
            DEFAULT_TRANSACTION_MANIFEST.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Cannot load transaction manifest {DEFAULT_TRANSACTION_MANIFEST}: {exc}"
        ) from exc
    payload = build_project_catalog(
        aggregate_rows,
        browser_projects,
        contexts,
        transaction_manifest,
        latest_project_month=latest_month,
    )
    return payload, transaction_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the immutable shared private-project browser catalog"
    )
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_CATALOG_OUT)
    args = parser.parse_args()
    payload, transaction_manifest = build_committed_catalog()
    paths = publish_project_catalog(
        args.out,
        payload,
        transaction_manifest=transaction_manifest,
    )
    print(
        f"Published {payload['counts']['all']:,} private-project records at "
        f"revision {payload['catalog_revision']} ({len(paths)} catalog paths)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
