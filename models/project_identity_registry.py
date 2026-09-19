#!/usr/bin/env python3
"""Build and publish the canonical private-project identity registry.

The registry is the routing contract between the EdgeProp name index, the URA
project explorer, reviewed geocodes, transaction shards, and dedicated reports.
It never upgrades a name-only source into achieved evidence by fuzzy matching.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
from typing import Any
from urllib.parse import quote, urlsplit
import uuid

import pandas as pd


ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import private_project_catalog
from build_private_bedrooms import normalise_project_name
from sg_estate.domain.aliases import URA_EDGEPROP_PROJECT_ALIAS
from sg_estate.project_locations import usable_project_locations
from sg_estate.reporting.property_analysis import (
    discover_property_analyses,
    latest_property_analyses,
)


DEFAULT_REGISTRY_OUT = ROOT / "site/assets/project-identity-registry"
DEFAULT_PROJECT_CATALOG = ROOT / "site/assets/project-catalog/manifest.json"
DEFAULT_TRANSACTION_MANIFEST = ROOT / "site/assets/condo-transactions/manifest.json"
DEFAULT_EDGE_PROJECTS = ROOT / "data/raw/edgeprop/edgeprop_condo_apartment_projects.csv"
DEFAULT_EDGE_TRANSACTIONS = (
    ROOT
    / "data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
)
DEFAULT_GEOCODES = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_REPORTS = ROOT / "site/reports.json"

REGISTRY_SCHEMA = "project-identity-registry.v1"
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_ROUTE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.html(?:\?[^#]*)?(?:#[^#]*)?$")

ROOT_KEYS = ("schema", "registry_revision", "source_revisions", "counts", "records")
SOURCE_REVISION_KEYS = (
    "project_catalog",
    "transactions",
    "edge_projects",
    "edge_district_observations",
    "geocodes",
    "reports",
)
COUNT_KEYS = (
    "records",
    "full",
    "name_only",
    "non_project",
    "explorer",
    "comparison",
    "transactions",
    "exit",
    "dedicated_report",
    "edgeprop",
    "geocoded",
    "property_analysis",
    "authored_report",
)
RECORD_KEYS = ("id", "identity", "aliases", "sources", "evidence", "capabilities")
IDENTITY_KEYS = (
    "name",
    "selection_label",
    "street",
    "district",
    "planning_area",
    "precision",
)
ALIAS_KEYS = ("source", "source_key", "name", "match_basis")
SOURCE_KEYS = (
    "project_catalog",
    "ura_explorer",
    "geocode",
    "transaction_manifest",
    "edgeprop",
    "property_analysis",
    "authored_report",
)
EVIDENCE_KEYS = (
    "identity_status",
    "geocode_status",
    "transaction_status",
    "report_status",
    "resolution",
)
CAPABILITY_KEYS = ("explorer", "comparison", "transactions", "exit", "dedicated_report")
CAPABILITY_VALUE_KEYS = ("available", "routes", "evidence_status", "reason")
ROUTE_KEYS = ("path", "source", "is_latest")
REPORT_ROUTE_KEYS = (
    "project_name",
    "project_slug",
    "path",
    "source",
    "is_latest",
    "street",
    "district",
    "planning_area",
)
GEOCODE_STATES = {
    "matched",
    "low_confidence",
    "needs_review",
    "error",
    "missing",
    "not_applicable",
}
IDENTITY_STATES = {"full", "name_only", "non_project"}
RESOLUTION_STATES = {"canonical_identity", "unmatched_name", "ambiguous_name", "report_only"}
GENERIC_NAMES = {"RESIDENTIAL APARTMENTS", "RESIDENTIAL APARTMENT", "-", "N/A"}


def _normalise(value: object) -> str:
    return " ".join(str(value or "").split()).upper()


def _district(value: object) -> str | None:
    text = _normalise(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(2) if text.isdigit() else (text or None)


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "unknown"


def _identity_key(values: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _normalise(values.get("project") or values.get("project_name") or values.get("name")),
        _normalise(values.get("street") or values.get("street_name")),
        _district(values.get("district") or values.get("postal_district")) or "",
        _normalise(values.get("planning_area")),
    )


def _canonical_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Registry source is not canonical JSON: {exc}") from exc
    return encoded.encode("utf-8")


def _content_revision(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def compute_registry_revision(payload: Mapping[str, Any]) -> str:
    """Return the deterministic revision, excluding the revision field itself."""

    normalized = dict(payload)
    normalized.pop("registry_revision", None)
    return _content_revision(normalized)


def registry_asset_path(revision: str) -> str:
    """Return the Pages-relative immutable path for a validated revision."""

    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise ValueError("Registry revision must be a lowercase SHA-256 digest")
    return f"assets/project-identity-registry/{revision}/registry.json"


def _safe_route(path: object) -> str:
    if not isinstance(path, str) or not LOCAL_ROUTE_RE.fullmatch(path):
        raise ValueError(f"Report route must be a root-local HTML path: {path!r}")
    parsed = urlsplit(path)
    pure = PurePosixPath(parsed.path)
    if pure.is_absolute() or len(pure.parts) != 1 or ".." in pure.parts:
        raise ValueError(f"Report route escapes the site root: {path!r}")
    return path


def _route(path: str, source: str, is_latest: bool = True) -> dict[str, Any]:
    return {"path": _safe_route(path), "source": source, "is_latest": bool(is_latest)}


def _capability(
    available: bool,
    routes: Sequence[Mapping[str, Any]],
    evidence_status: str,
    reason: str | None,
) -> dict[str, Any]:
    materialized = [dict(route) for route in routes]
    materialized.sort(key=lambda item: (not item["is_latest"], item["path"], item["source"]))
    return {
        "available": available,
        "routes": materialized,
        "evidence_status": evidence_status,
        "reason": reason,
    }


def _selection_label(name: str, street: str | None, district: str | None, duplicate: bool) -> str:
    if duplicate or name in GENERIC_NAMES:
        location = " / ".join(
            value for value in (f"D{district}" if district else None, street) if value
        )
        return f"{name} · {location or 'identity unavailable'}"
    return name


def _record_source_template() -> dict[str, list[str]]:
    return {key: [] for key in SOURCE_KEYS}


def _append_source(record: dict[str, Any], source: str, key: str) -> None:
    values = record["sources"][source]
    if key not in values:
        values.append(key)
        values.sort()


def _append_alias(
    record: dict[str, Any],
    *,
    source: str,
    source_key: str,
    name: str,
    match_basis: str,
) -> None:
    alias = {
        "source": source,
        "source_key": source_key,
        "name": name,
        "match_basis": match_basis,
    }
    if alias not in record["aliases"]:
        record["aliases"].append(alias)
        record["aliases"].sort(
            key=lambda item: (item["source"], item["source_key"], item["name"])
        )


def _unavailable_capabilities(reason: str) -> dict[str, dict[str, Any]]:
    return {
        key: _capability(False, [], "not_available", reason)
        for key in CAPABILITY_KEYS
    }


def _usable_geocode_identity_keys(
    rows: Sequence[Mapping[str, Any]],
) -> set[tuple[str, str, str, str]]:
    """Return full identities whose coordinates pass the shared review gate."""

    if not rows:
        return set()
    source_columns = tuple(rows[0])
    if any(tuple(row) != source_columns for row in rows):
        raise ValueError("Geocode source rows must use one consistent column contract")
    frame = pd.DataFrame.from_records(rows, columns=source_columns)
    usable = usable_project_locations(frame, source_columns=source_columns)
    return {
        _identity_key(row)
        for row in usable.to_dict(orient="records")
    }


def _geocode_evidence_status(
    row: Mapping[str, Any],
    identity: tuple[str, str, str, str],
    usable_identities: set[tuple[str, str, str, str]],
) -> str:
    """Keep raw weak states, but require reviewed coordinates for ``matched``."""

    raw_status = str(row.get("match_status") or "needs_review").strip().lower()
    if raw_status == "matched":
        return "matched" if identity in usable_identities else "needs_review"
    if raw_status in {"low_confidence", "needs_review", "error"}:
        return raw_status
    if raw_status in {"no_match", "missing"}:
        return "missing"
    return "needs_review"


def build_project_identity_registry(
    project_catalog: Mapping[str, Any],
    edge_projects: Sequence[Mapping[str, Any]],
    geocode_rows: Sequence[Mapping[str, Any]],
    transaction_manifest: Mapping[str, Any],
    report_routes: Sequence[Mapping[str, Any]],
    *,
    edge_district_observations: Sequence[Mapping[str, Any]] = (),
    previous_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the strict union registry from reviewed repository sources."""

    private_project_catalog.validate_project_catalog(
        project_catalog, transaction_manifest=transaction_manifest
    )
    transaction_projects = transaction_manifest["projects"]
    catalog_projects = list(project_catalog["projects"])
    name_counts = Counter(_normalise(row.get("project")) for row in catalog_projects)
    records: dict[str, dict[str, Any]] = {}
    by_identity: dict[tuple[str, str, str, str], str] = {}
    by_name: defaultdict[str, list[str]] = defaultdict(list)

    for project in catalog_projects:
        project_id = str(project["id"])
        key = _identity_key(project)
        if key in by_identity:
            raise ValueError(f"Project catalog repeats identity {key!r}")
        name, street, district, planning_area = key
        generic = name in GENERIC_NAMES
        flags = project["capabilities"]
        explorer = bool(flags["private_explorer"]) and not generic
        comparison = bool(flags["framework_comparison"]) and not generic
        transactions = bool(flags["transactions"]) and not generic
        exit_available = bool(flags["project_exit"]) and not generic
        explorer_query = " ".join(value for value in (name, street) if value)
        explorer_path = (
            "private_project_comparison_table.html?"
            f"q={quote(explorer_query)}&district={quote(district)}"
        )
        generic_reason = "This record is an address bucket, not a named project."
        record = {
            "id": project_id,
            "identity": {
                "name": name,
                "selection_label": _selection_label(
                    name, street or None, district or None, name_counts[name] > 1
                ),
                "street": street or None,
                "district": district or None,
                "planning_area": planning_area or None,
                "precision": "full",
            },
            "aliases": [],
            "sources": _record_source_template(),
            "evidence": {
                "identity_status": "non_project" if generic else "full",
                "geocode_status": "missing",
                "transaction_status": "canonical" if transactions else "not_available",
                "report_status": "not_available",
                "resolution": "canonical_identity",
            },
            "capabilities": {
                "explorer": _capability(
                    explorer,
                    [_route(explorer_path, "private_project_explorer")] if explorer else [],
                    "achieved_transactions" if explorer else "not_available",
                    None if explorer else generic_reason,
                ),
                "comparison": _capability(
                    comparison,
                    [_route(f"condo_framework_comparison.html?a={quote(project_id)}", "framework_comparison")]
                    if comparison
                    else [],
                    "project_and_estate_context" if comparison else "not_available",
                    None if comparison else generic_reason,
                ),
                "transactions": _capability(
                    transactions,
                    [_route(explorer_path, "private_project_explorer")] if transactions else [],
                    "canonical_ura" if transactions else "not_available",
                    None if transactions else generic_reason,
                ),
                "exit": _capability(
                    exit_available,
                    [_route(f"project_exit_comparison.html?p={quote(project_id)}", "project_exit")]
                    if exit_available
                    else [],
                    "canonical_ura" if exit_available else "not_available",
                    None if exit_available else generic_reason,
                ),
                "dedicated_report": _capability(
                    False,
                    [],
                    "not_available",
                    "No dedicated report is published for this identity.",
                ),
            },
        }
        _append_source(record, "project_catalog", project_id)
        _append_source(record, "ura_explorer", project_id)
        _append_alias(
            record,
            source="project_catalog",
            source_key=project_id,
            name=name,
            match_basis="exact_full_identity",
        )
        if transactions:
            if project_id not in transaction_projects:
                raise ValueError(f"Transaction-capable project {project_id} is not manifested")
            _append_source(record, "transaction_manifest", project_id)
        records[project_id] = record
        by_identity[key] = project_id
        by_name[name].append(project_id)

    if previous_registry is not None:
        validate_project_identity_registry(previous_registry)
        old_full = {
            (
                item["identity"]["name"],
                item["identity"]["street"] or "",
                item["identity"]["district"] or "",
                item["identity"]["planning_area"] or "",
            ): item["id"]
            for item in previous_registry["records"]
            if item["identity"]["precision"] == "full"
        }
        for key, old_id in old_full.items():
            if key in by_identity and by_identity[key] != old_id:
                raise ValueError(
                    f"Stable project identity {key!r} changed id from {old_id!r} "
                    f"to {by_identity[key]!r}"
                )

    geocode_materialized = [dict(row) for row in geocode_rows]
    usable_geocode_identities = _usable_geocode_identity_keys(geocode_materialized)
    geocode_seen: set[tuple[str, str, str, str]] = set()
    for row in geocode_materialized:
        key = _identity_key(row)
        if key in geocode_seen:
            raise ValueError(f"Geocode source repeats identity {key!r}")
        geocode_seen.add(key)
        project_id = by_identity.get(key)
        if project_id is None:
            raise ValueError(f"Geocode identity does not exist in project catalog: {key!r}")
        status = _geocode_evidence_status(row, key, usable_geocode_identities)
        record = records[project_id]
        source_key = "|".join(key)
        record["evidence"]["geocode_status"] = status
        _append_source(record, "geocode", source_key)
        _append_alias(
            record,
            source="geocode",
            source_key=source_key,
            name=key[0],
            match_basis="exact_full_identity",
        )

    edge_materialized = [dict(row) for row in edge_projects]
    observation_materialized = [dict(row) for row in edge_district_observations]
    edge_slugs: set[str] = set()
    observed_districts: defaultdict[str, set[str]] = defaultdict(set)
    for row in observation_materialized:
        slug = _normalise(row.get("source_slug") or row.get("slug")).lower()
        district = _district(row.get("Postal District") or row.get("district"))
        if slug and district:
            observed_districts[slug].add(district)

    reviewed_by_edge_name: defaultdict[str, set[str]] = defaultdict(set)
    reviewed_by_edge_district: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for (ura_name, district), edge_name in URA_EDGEPROP_PROJECT_ALIAS.items():
        candidates = [
            project_id
            for project_id, record in records.items()
            if normalise_project_name(record["identity"]["name"]) == ura_name
            and record["identity"]["district"] == _district(district)
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Reviewed alias {_normalise(ura_name)!r}/D{district} does not "
                "resolve to one project identity"
            )
        edge_key = normalise_project_name(edge_name)
        reviewed_by_edge_name[edge_key].add(candidates[0])
        reviewed_by_edge_district[(edge_key, _district(district) or "")].add(candidates[0])

    for row in edge_materialized:
        name = _normalise(row.get("name"))
        source_slug = str(row.get("slug") or "").strip()
        normalized_slug = _normalise(source_slug).lower()
        if not name or not source_slug or not normalized_slug:
            raise ValueError("EdgeProp project entries require name and slug")
        if normalized_slug in edge_slugs:
            raise ValueError(f"EdgeProp project slug is duplicated: {source_slug}")
        edge_slugs.add(normalized_slug)
        candidates = list(by_name.get(name, []))
        match_basis = "unique_name"
        if len(candidates) != 1:
            edge_key = normalise_project_name(name)
            reviewed = set(reviewed_by_edge_name.get(edge_key, set()))
            if len(reviewed) > 1:
                reviewed = set()
                for district in observed_districts.get(normalized_slug, set()):
                    reviewed.update(reviewed_by_edge_district.get((edge_key, district), set()))
            candidates = sorted(reviewed)
            match_basis = "reviewed_alias"
        if len(candidates) == 1:
            record = records[candidates[0]]
            _append_source(record, "edgeprop", source_slug)
            _append_alias(
                record,
                source="edgeprop",
                source_key=source_slug,
                name=name,
                match_basis=match_basis,
            )
            continue

        project_id = f"edgeprop:{normalized_slug}"
        if project_id in records:
            raise ValueError(f"EdgeProp name-only id collides: {project_id}")
        resolution = "ambiguous_name" if len(by_name.get(name, [])) > 1 else "unmatched_name"
        if resolution == "ambiguous_name":
            reason = "This name matches multiple street/district identities; choose a disambiguated project record."
        else:
            reason = "This indexed name has no reviewed achieved-project identity."
        record = {
            "id": project_id,
            "identity": {
                "name": name,
                "selection_label": f"{name} · name only",
                "street": None,
                "district": None,
                "planning_area": None,
                "precision": "name_only",
            },
            "aliases": [],
            "sources": _record_source_template(),
            "evidence": {
                "identity_status": "name_only",
                "geocode_status": "not_applicable",
                "transaction_status": "not_available",
                "report_status": "not_available",
                "resolution": resolution,
            },
            "capabilities": _unavailable_capabilities(reason),
        }
        _append_source(record, "edgeprop", source_slug)
        _append_alias(
            record,
            source="edgeprop",
            source_key=source_slug,
            name=name,
            match_basis=resolution,
        )
        records[project_id] = record
        by_name[name].append(project_id)

    route_keys: set[tuple[str, str, str, str]] = set()
    report_materialized = [dict(row) for row in report_routes]
    for position, raw_route in enumerate(report_materialized):
        if set(raw_route) != set(REPORT_ROUTE_KEYS):
            raise ValueError(
                f"Report route {position} fields must be exactly {REPORT_ROUTE_KEYS!r}"
            )
        source = raw_route["source"]
        if source not in {"property_analysis", "authored_report"}:
            raise ValueError(f"Report route {position} has invalid source {source!r}")
        if not isinstance(raw_route["is_latest"], bool):
            raise ValueError(f"Report route {position} is_latest must be boolean")
        path = _safe_route(raw_route["path"])
        name = _normalise(raw_route["project_name"])
        project_slug = _slug(raw_route["project_slug"] or name)
        descriptor_key = (source, path, name, project_slug)
        if descriptor_key in route_keys:
            raise ValueError(f"Report route is duplicated: {descriptor_key!r}")
        route_keys.add(descriptor_key)
        raw_qualifiers = (
            raw_route["street"],
            raw_route["district"],
            raw_route["planning_area"],
        )
        if not (
            all(value is None for value in raw_qualifiers)
            or all(value is not None for value in raw_qualifiers)
        ):
            raise ValueError(
                "Report route identity qualifiers must be all-null or complete"
            )
        qualifiers = (
            _normalise(raw_qualifiers[0]),
            _district(raw_qualifiers[1]) or "",
            _normalise(raw_qualifiers[2]),
        )
        qualified = any(value is not None for value in raw_qualifiers)
        if qualified and not all(qualifiers):
            raise ValueError(
                "Report route identity qualifiers must be all-null or complete"
            )
        candidates = [
            project_id
            for project_id in by_name.get(name, [])
            if (
                not qualified
                or (
                    (not qualifiers[0] or records[project_id]["identity"]["street"] == qualifiers[0])
                    and (not qualifiers[1] or records[project_id]["identity"]["district"] == qualifiers[1])
                    and (
                        not qualifiers[2]
                        or records[project_id]["identity"]["planning_area"] == qualifiers[2]
                    )
                )
            )
        ]
        if len(candidates) > 1:
            raise ValueError(f"Report route {path!r} is ambiguous for project name {name!r}")
        if candidates:
            project_id = candidates[0]
        else:
            project_id = f"report:{project_slug}"
            if project_id not in records:
                reason = "This report subject has no reviewed achieved-project identity."
                records[project_id] = {
                    "id": project_id,
                    "identity": {
                        "name": name,
                        "selection_label": f"{name} · report only",
                        "street": qualifiers[0] or None,
                        "district": qualifiers[1] or None,
                        "planning_area": qualifiers[2] or None,
                        "precision": "name_only",
                    },
                    "aliases": [],
                    "sources": _record_source_template(),
                    "evidence": {
                        "identity_status": "name_only",
                        "geocode_status": "not_applicable",
                        "transaction_status": "not_available",
                        "report_status": "available",
                        "resolution": "report_only",
                    },
                    "capabilities": _unavailable_capabilities(reason),
                }
                by_name[name].append(project_id)
        record = records[project_id]
        source_key = f"{path}#{project_slug}"
        _append_source(record, source, source_key)
        _append_alias(
            record,
            source=source,
            source_key=source_key,
            name=name,
            match_basis=(
                "exact_full_identity"
                if record["identity"]["precision"] == "full"
                else "report_only"
            ),
        )
        routes = list(record["capabilities"]["dedicated_report"]["routes"])
        route = _route(path, source, raw_route["is_latest"])
        if route not in routes:
            routes.append(route)
        record["capabilities"]["dedicated_report"] = _capability(
            True, routes, "published_report", None
        )
        record["evidence"]["report_status"] = "available"

    materialized_records = sorted(records.values(), key=lambda item: item["id"])
    edge_for_revision = sorted(edge_materialized, key=lambda row: str(row.get("slug") or ""))
    geocode_for_revision = sorted(geocode_materialized, key=_identity_key)
    reports_for_revision = sorted(
        report_materialized,
        key=lambda row: (str(row["source"]), str(row["path"]), str(row["project_slug"])),
    )
    observations_for_revision = sorted(
        observation_materialized,
        key=lambda row: (
            str(row.get("source_slug") or row.get("slug") or ""),
            str(row.get("Date of Sale") or ""),
            str(row.get("Address") or ""),
            _canonical_bytes(row),
        ),
    )
    source_revisions = {
        "project_catalog": str(project_catalog["catalog_revision"]),
        "transactions": str(transaction_manifest["dataset_revision"]),
        "edge_projects": _content_revision(edge_for_revision),
        "edge_district_observations": _content_revision(observations_for_revision),
        "geocodes": _content_revision(geocode_for_revision),
        "reports": _content_revision(reports_for_revision),
    }
    counts = {
        "records": len(materialized_records),
        "full": sum(item["identity"]["precision"] == "full" for item in materialized_records),
        "name_only": sum(
            item["identity"]["precision"] == "name_only" for item in materialized_records
        ),
        "non_project": sum(
            item["evidence"]["identity_status"] == "non_project"
            for item in materialized_records
        ),
        **{
            capability: sum(
                item["capabilities"][capability]["available"] for item in materialized_records
            )
            for capability in CAPABILITY_KEYS
        },
        "edgeprop": sum(bool(item["sources"]["edgeprop"]) for item in materialized_records),
        "geocoded": sum(bool(item["sources"]["geocode"]) for item in materialized_records),
        "property_analysis": sum(
            bool(item["sources"]["property_analysis"]) for item in materialized_records
        ),
        "authored_report": sum(
            bool(item["sources"]["authored_report"]) for item in materialized_records
        ),
    }
    payload: dict[str, Any] = {
        "schema": REGISTRY_SCHEMA,
        "registry_revision": None,
        "source_revisions": source_revisions,
        "counts": counts,
        "records": materialized_records,
    }
    payload["registry_revision"] = compute_registry_revision(payload)
    validate_project_identity_registry(
        payload,
        project_catalog=project_catalog,
        transaction_manifest=transaction_manifest,
        previous_registry=previous_registry,
    )
    return payload


def validate_project_identity_registry(
    payload: Mapping[str, Any],
    *,
    project_catalog: Mapping[str, Any] | None = None,
    transaction_manifest: Mapping[str, Any] | None = None,
    previous_registry: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless the complete identity, evidence, and route contract reconciles."""

    if not isinstance(payload, Mapping) or set(payload) != set(ROOT_KEYS):
        raise ValueError(f"Registry root fields must be exactly {ROOT_KEYS!r}")
    if payload.get("schema") != REGISTRY_SCHEMA:
        raise ValueError(f"Registry schema must be {REGISTRY_SCHEMA}")
    revision = payload.get("registry_revision")
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise ValueError("Registry revision must be a lowercase SHA-256 digest")
    if compute_registry_revision(payload) != revision:
        raise ValueError("Registry revision does not match normalized contents")
    source_revisions = payload.get("source_revisions")
    if not isinstance(source_revisions, Mapping) or set(source_revisions) != set(
        SOURCE_REVISION_KEYS
    ):
        raise ValueError("Registry source_revisions fields are invalid")
    if any(
        not isinstance(value, str) or not REVISION_RE.fullmatch(value)
        for value in source_revisions.values()
    ):
        raise ValueError("Registry source revisions must be SHA-256 digests")
    counts = payload.get("counts")
    records = payload.get("records")
    if not isinstance(counts, Mapping) or set(counts) != set(COUNT_KEYS):
        raise ValueError(f"Registry counts fields must be exactly {COUNT_KEYS!r}")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts.values()
    ):
        raise ValueError("Registry counts must be non-negative integers")
    if not isinstance(records, list) or not records:
        raise ValueError("Registry records must be a non-empty array")

    ids: set[str] = set()
    labels: set[str] = set()
    alias_keys: set[tuple[str, str]] = set()
    catalog_ids: set[str] = set()
    transaction_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or set(record) != set(RECORD_KEYS):
            raise ValueError(f"Registry record {index} fields are invalid")
        project_id = record.get("id")
        if not isinstance(project_id, str) or not project_id.strip() or project_id in ids:
            raise ValueError(f"Registry record {index} has a missing or duplicate id")
        ids.add(project_id)
        identity = record.get("identity")
        if not isinstance(identity, Mapping) or set(identity) != set(IDENTITY_KEYS):
            raise ValueError(f"Registry record {project_id} identity fields are invalid")
        if identity["precision"] not in {"full", "name_only"}:
            raise ValueError(f"Registry record {project_id} precision is invalid")
        for field in ("name", "selection_label"):
            if not isinstance(identity[field], str) or not identity[field].strip():
                raise ValueError(f"Registry record {project_id} {field} is invalid")
        if identity["selection_label"] in labels:
            raise ValueError(f"Registry selection label is ambiguous: {identity['selection_label']!r}")
        labels.add(identity["selection_label"])
        for field in ("street", "district", "planning_area"):
            if identity[field] is not None and (
                not isinstance(identity[field], str) or not identity[field].strip()
            ):
                raise ValueError(f"Registry record {project_id} {field} is invalid")
        if identity["precision"] == "full" and any(
            identity[field] is None for field in ("street", "district", "planning_area")
        ):
            raise ValueError(f"Registry full identity {project_id} is incomplete")

        aliases = record.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"Registry record {project_id} aliases are missing")
        for alias in aliases:
            if not isinstance(alias, Mapping) or set(alias) != set(ALIAS_KEYS):
                raise ValueError(f"Registry record {project_id} alias fields are invalid")
            if any(
                not isinstance(alias[key], str) or not alias[key].strip()
                for key in ALIAS_KEYS
            ):
                raise ValueError(f"Registry record {project_id} alias values are invalid")
        if aliases != sorted(
            aliases, key=lambda item: (item["source"], item["source_key"], item["name"])
        ):
            raise ValueError(f"Registry record {project_id} aliases are not sorted")
        for alias in aliases:
            typed_key = (alias["source"], alias["source_key"])
            if typed_key in alias_keys:
                raise ValueError(f"Registry source alias maps more than once: {typed_key!r}")
            alias_keys.add(typed_key)

        sources = record.get("sources")
        if not isinstance(sources, Mapping) or set(sources) != set(SOURCE_KEYS):
            raise ValueError(f"Registry record {project_id} source fields are invalid")
        for source, values in sources.items():
            if (
                not isinstance(values, list)
                or values != sorted(set(values))
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise ValueError(f"Registry record {project_id} source {source} is invalid")
        alias_sources = {(alias["source"], alias["source_key"]) for alias in aliases}
        for source in ("project_catalog", "geocode", "edgeprop", "property_analysis", "authored_report"):
            if any((source, value) not in alias_sources for value in sources[source]):
                raise ValueError(f"Registry record {project_id} source aliases do not reconcile")
        if sources["project_catalog"]:
            if sources["project_catalog"] != [project_id]:
                raise ValueError(f"Registry project catalog source differs from id {project_id}")
            catalog_ids.add(project_id)

        evidence = record.get("evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != set(EVIDENCE_KEYS):
            raise ValueError(f"Registry record {project_id} evidence fields are invalid")
        if evidence["identity_status"] not in IDENTITY_STATES:
            raise ValueError(f"Registry record {project_id} identity status is invalid")
        if evidence["geocode_status"] not in GEOCODE_STATES:
            raise ValueError(f"Registry record {project_id} geocode status is invalid")
        if evidence["transaction_status"] not in {"canonical", "not_available"}:
            raise ValueError(f"Registry record {project_id} transaction status is invalid")
        if evidence["report_status"] not in {"available", "not_available"}:
            raise ValueError(f"Registry record {project_id} report status is invalid")
        if evidence["resolution"] not in RESOLUTION_STATES:
            raise ValueError(f"Registry record {project_id} resolution is invalid")

        capabilities = record.get("capabilities")
        if not isinstance(capabilities, Mapping) or set(capabilities) != set(CAPABILITY_KEYS):
            raise ValueError(f"Registry record {project_id} capability fields are invalid")
        for capability, value in capabilities.items():
            if not isinstance(value, Mapping) or set(value) != set(CAPABILITY_VALUE_KEYS):
                raise ValueError(f"Registry record {project_id} {capability} fields are invalid")
            if not isinstance(value["available"], bool) or not isinstance(value["routes"], list):
                raise ValueError(f"Registry record {project_id} {capability} values are invalid")
            if not isinstance(value["evidence_status"], str) or not value["evidence_status"]:
                raise ValueError(f"Registry record {project_id} {capability} status is invalid")
            if value["reason"] is not None and (
                not isinstance(value["reason"], str) or not value["reason"].strip()
            ):
                raise ValueError(f"Registry record {project_id} {capability} reason is invalid")
            if value["available"] != bool(value["routes"]):
                raise ValueError(f"Registry record {project_id} {capability} availability differs")
            if value["available"] and value["reason"] is not None:
                raise ValueError(f"Registry record {project_id} available capability has a reason")
            if not value["available"] and value["reason"] is None:
                raise ValueError(f"Registry record {project_id} unavailable capability lacks a reason")
            seen_routes: set[tuple[str, str, bool]] = set()
            for route in value["routes"]:
                if not isinstance(route, Mapping) or set(route) != set(ROUTE_KEYS):
                    raise ValueError(f"Registry record {project_id} route fields are invalid")
                _safe_route(route["path"])
                if not isinstance(route["source"], str) or not route["source"].strip():
                    raise ValueError(f"Registry record {project_id} route source is invalid")
                if not isinstance(route["is_latest"], bool):
                    raise ValueError(f"Registry record {project_id} route flag is invalid")
                route_key = (route["path"], route["source"], route["is_latest"])
                if route_key in seen_routes:
                    raise ValueError(f"Registry record {project_id} repeats a route")
                seen_routes.add(route_key)

        if capabilities["exit"]["available"] and not capabilities["transactions"]["available"]:
            raise ValueError(f"Registry record {project_id} exit lacks transactions")
        if capabilities["transactions"]["available"] and not capabilities["comparison"]["available"]:
            raise ValueError(f"Registry record {project_id} transactions lack comparison")
        if capabilities["comparison"]["available"] and not capabilities["explorer"]["available"]:
            raise ValueError(f"Registry record {project_id} comparison lacks explorer")
        if identity["precision"] == "name_only" or evidence["identity_status"] == "non_project":
            if any(
                capabilities[key]["available"]
                for key in ("explorer", "comparison", "transactions", "exit")
            ):
                raise ValueError(f"Registry name-only/non-project record {project_id} claims evidence")
        if capabilities["transactions"]["available"]:
            transaction_ids.add(project_id)
            if sources["transaction_manifest"] != [project_id]:
                raise ValueError(f"Registry transaction source differs from id {project_id}")
            if evidence["transaction_status"] != "canonical":
                raise ValueError(f"Registry transaction evidence differs for {project_id}")
        elif sources["transaction_manifest"] or evidence["transaction_status"] != "not_available":
            raise ValueError(f"Registry non-transaction record {project_id} claims evidence")
        if sources["geocode"]:
            if evidence["geocode_status"] == "not_applicable":
                raise ValueError(f"Registry geocode evidence differs for {project_id}")
        elif evidence["geocode_status"] not in {"missing", "not_applicable"}:
            raise ValueError(f"Registry geocode evidence differs for {project_id}")
        if capabilities["dedicated_report"]["available"] != bool(
            sources["property_analysis"] or sources["authored_report"]
        ):
            raise ValueError(f"Registry dedicated report sources differ for {project_id}")

    if [record["id"] for record in records] != sorted(ids):
        raise ValueError("Registry records must be ordered by id")
    expected_counts = {
        "records": len(records),
        "full": sum(record["identity"]["precision"] == "full" for record in records),
        "name_only": sum(record["identity"]["precision"] == "name_only" for record in records),
        "non_project": sum(
            record["evidence"]["identity_status"] == "non_project" for record in records
        ),
        **{
            capability: sum(record["capabilities"][capability]["available"] for record in records)
            for capability in CAPABILITY_KEYS
        },
        "edgeprop": sum(bool(record["sources"]["edgeprop"]) for record in records),
        "geocoded": sum(bool(record["sources"]["geocode"]) for record in records),
        "property_analysis": sum(
            bool(record["sources"]["property_analysis"]) for record in records
        ),
        "authored_report": sum(bool(record["sources"]["authored_report"]) for record in records),
    }
    if dict(counts) != expected_counts:
        raise ValueError(f"Registry counts do not reconcile: {dict(counts)!r} != {expected_counts!r}")

    if project_catalog is not None:
        private_project_catalog.validate_project_catalog(
            project_catalog, transaction_manifest=transaction_manifest
        )
        expected_catalog_ids = {str(project["id"]) for project in project_catalog["projects"]}
        if catalog_ids != expected_catalog_ids:
            raise ValueError("Registry project-catalog membership does not reconcile")
        if source_revisions["project_catalog"] != project_catalog["catalog_revision"]:
            raise ValueError("Registry project catalog revision differs")
    if transaction_manifest is not None:
        if transaction_ids != set(transaction_manifest["projects"]):
            raise ValueError("Registry transaction membership does not reconcile")
        if source_revisions["transactions"] != transaction_manifest["dataset_revision"]:
            raise ValueError("Registry transaction revision differs")
    if previous_registry is not None:
        validate_project_identity_registry(previous_registry)
        old_full_records = [
            record
            for record in previous_registry["records"]
            if record["identity"]["precision"] == "full"
        ]
        old_full = {
            (
                record["identity"]["name"],
                record["identity"]["street"],
                record["identity"]["district"],
                record["identity"]["planning_area"],
            ): record["id"]
            for record in old_full_records
        }
        new_full = {
            (
                record["identity"]["name"],
                record["identity"]["street"],
                record["identity"]["district"],
                record["identity"]["planning_area"],
            ): record["id"]
            for record in records
            if record["identity"]["precision"] == "full"
        }
        for identity, old_id in old_full.items():
            if identity in new_full and new_full[identity] != old_id:
                raise ValueError(f"Stable registry identity {identity!r} changed id")
        new_by_id = {record["id"]: record for record in records}
        for old_record in old_full_records:
            new_record = new_by_id.get(old_record["id"])
            if new_record is None:
                continue
            old_identity = (
                old_record["identity"]["name"],
                old_record["identity"]["street"],
                old_record["identity"]["district"],
                old_record["identity"]["planning_area"],
            )
            new_identity = (
                new_record["identity"]["name"],
                new_record["identity"]["street"],
                new_record["identity"]["district"],
                new_record["identity"]["planning_area"],
            )
            if (
                new_record["identity"]["precision"] != "full"
                or new_identity != old_identity
            ):
                raise ValueError(
                    f"Stable registry id {old_record['id']!r} changed identity"
                )


def load_project_identity_registry(
    path: Path | str,
    *,
    project_catalog: Mapping[str, Any] | None = None,
    transaction_manifest: Mapping[str, Any] | None = None,
    previous_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate a registry JSON document."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load project identity registry {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Project identity registry {source} must be an object")
    validate_project_identity_registry(
        payload,
        project_catalog=project_catalog,
        transaction_manifest=transaction_manifest,
        previous_registry=previous_registry,
    )
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_project_identity_registry(
    output_dir: Path | str,
    payload: Mapping[str, Any],
    *,
    project_catalog: Mapping[str, Any] | None = None,
    transaction_manifest: Mapping[str, Any] | None = None,
    previous_registry: Mapping[str, Any] | None = None,
) -> list[Path]:
    """Publish an immutable revision, then atomically switch the root manifest."""

    materialized = dict(payload)
    validate_project_identity_registry(
        materialized,
        project_catalog=project_catalog,
        transaction_manifest=transaction_manifest,
        previous_registry=previous_registry,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    revision = materialized["registry_revision"]
    final_dir = output / revision
    stage = output.parent / f".{output.name}.stage-{revision[:12]}-{uuid.uuid4().hex}"
    root_temp: Path | None = None
    try:
        stage.mkdir()
        staged_file = stage / "registry.json"
        _write_json(staged_file, materialized)
        if load_project_identity_registry(
            staged_file,
            project_catalog=project_catalog,
            transaction_manifest=transaction_manifest,
            previous_registry=previous_registry,
        ) != materialized:
            raise ValueError("Staged registry failed round-trip validation")
        _fsync_dir(stage)
        if final_dir.exists():
            existing = load_project_identity_registry(
                final_dir / "registry.json",
                project_catalog=project_catalog,
                transaction_manifest=transaction_manifest,
                previous_registry=previous_registry,
            )
            if existing != materialized:
                raise ValueError(f"Immutable registry revision already differs: {revision}")
            shutil.rmtree(stage)
        else:
            os.replace(stage, final_dir)
            _fsync_dir(output)

        descriptor, temporary = tempfile.mkstemp(
            prefix=".manifest.", suffix=".json", dir=output
        )
        root_temp = Path(temporary)
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
        load_project_identity_registry(
            root_temp,
            project_catalog=project_catalog,
            transaction_manifest=transaction_manifest,
            previous_registry=previous_registry,
        )
        root = output / "manifest.json"
        os.replace(root_temp, root)
        root_temp = None
        _fsync_dir(output)
        return [final_dir / "registry.json", root]
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if root_temp is not None and root_temp.exists():
            root_temp.unlink()


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise ValueError(f"Cannot load registry source {path}: {exc}") from exc


def _committed_report_routes() -> list[dict[str, Any]]:
    reports = json.loads(DEFAULT_REPORTS.read_text(encoding="utf-8"))["reports"]
    routes: list[dict[str, Any]] = []
    for report in reports:
        for name in report.get("project_names", []):
            routes.append(
                {
                    "project_name": name,
                    "project_slug": _slug(name),
                    "path": report["path"],
                    "source": "authored_report",
                    "is_latest": True,
                    "street": None,
                    "district": None,
                    "planning_area": None,
                }
            )
    analyses = discover_property_analyses()
    latest = {analysis.output_path for analysis in latest_property_analyses(analyses)}
    for analysis in analyses:
        routes.append(
            {
                "project_name": analysis.project_name,
                "project_slug": analysis.project_slug,
                "path": analysis.output_path,
                "source": "property_analysis",
                "is_latest": analysis.output_path in latest,
                "street": None,
                "district": None,
                "planning_area": None,
            }
        )
    routes.sort(key=lambda item: (item["source"], item["project_slug"], item["path"]))
    return routes


def build_committed_registry() -> dict[str, Any]:
    """Build the registry from the repository's committed reviewed sources."""

    try:
        transaction_manifest = json.loads(
            DEFAULT_TRANSACTION_MANIFEST.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load transaction manifest: {exc}") from exc
    project_catalog = private_project_catalog.load_project_catalog(
        DEFAULT_PROJECT_CATALOG, transaction_manifest=transaction_manifest
    )
    previous = None
    previous_path = DEFAULT_REGISTRY_OUT / "manifest.json"
    if previous_path.is_file():
        previous = load_project_identity_registry(previous_path)
    return build_project_identity_registry(
        project_catalog,
        _read_csv(DEFAULT_EDGE_PROJECTS),
        _read_csv(DEFAULT_GEOCODES),
        transaction_manifest,
        _committed_report_routes(),
        edge_district_observations=_read_csv(DEFAULT_EDGE_TRANSACTIONS),
        previous_registry=previous,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_REGISTRY_OUT)
    args = parser.parse_args()
    payload = build_committed_registry()
    transaction_manifest = json.loads(
        DEFAULT_TRANSACTION_MANIFEST.read_text(encoding="utf-8")
    )
    project_catalog = private_project_catalog.load_project_catalog(
        DEFAULT_PROJECT_CATALOG, transaction_manifest=transaction_manifest
    )
    previous = None
    previous_path = args.out / "manifest.json"
    if previous_path.is_file():
        previous = load_project_identity_registry(previous_path)
    publish_project_identity_registry(
        args.out,
        payload,
        project_catalog=project_catalog,
        transaction_manifest=transaction_manifest,
        previous_registry=previous,
    )
    print(
        f"Published {payload['counts']['records']:,} project identities at "
        f"revision {payload['registry_revision']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
