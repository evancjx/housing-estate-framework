"""Cross-source reconciliation tests for the project identity registry."""

from __future__ import annotations

from collections import Counter
import copy
import csv
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import private_project_catalog as project_catalog
import project_identity_registry as registry
from sg_estate.project_locations import (
    CURRENT_LOCATION_COLUMNS,
    LEGACY_LOCATION_COLUMNS,
    ProjectLocationContractError,
    canonical_project_location_match_sha256,
)


TRANSACTION_REVISION = "a" * 64
COMMITTED_REGISTRY_REVISION = (
    "771a82ca0e5c234ac04b4d6e26a0f7cdb41c24b651eec1794cb47692bb68a49f"
)


def _transaction_metadata(shard: int) -> dict[str, object]:
    return {
        "transaction_shard": (
            f"assets/condo-transactions/{TRANSACTION_REVISION}/"
            f"shard-{shard:02d}.json"
        ),
        "transaction_count": shard + 1,
        "transaction_first_month": "2020-01",
        "transaction_last_month": "2026-05",
        "transaction_complete_through": "2026-06",
    }


def _legacy_geocode(
    project_name: str,
    street_name: str,
    postal_district: str,
    planning_area: str,
    match_status: str,
) -> dict[str, str]:
    values = {
        "project_name": project_name,
        "street_name": street_name,
        "postal_district": postal_district,
        "planning_area": planning_area,
        "lat": "1.3000",
        "lon": "103.8000",
        "match_status": match_status,
        "match_score": "105",
        "query_used": f"{project_name} {street_name}",
        "onemap_building": project_name,
        "onemap_road": street_name,
        "onemap_address": f"1 {street_name}",
        "onemap_postal": "123456",
        "review_note": "synthetic legacy fixture",
    }
    return {column: values[column] for column in LEGACY_LOCATION_COLUMNS}


def _current_geocode(*, review_status: str) -> dict[str, str]:
    values = {column: "" for column in CURRENT_LOCATION_COLUMNS}
    values.update(
        {
            "project_name": "ALPHA RESIDENCES",
            "street_name": "ONE ROAD",
            "postal_district": "10",
            "planning_area": "BUKIT TIMAH",
            "lat": "1.3000",
            "lon": "103.8000",
            "match_status": "matched",
            "match_score": "105",
            "query_used": "ALPHA RESIDENCES ONE ROAD",
            "onemap_building": "ALPHA RESIDENCES",
            "onemap_road": "ONE ROAD",
            "onemap_address": "1 ONE ROAD",
            "onemap_postal": "123456",
            "retrieved_at": "2026-08-13T01:02:03Z",
            "response_sha256": "b" * 64,
            "retry_state": "complete",
            "attempt_count": "1",
            "review_status": review_status,
        }
    )
    values["match_sha256"] = canonical_project_location_match_sha256(values)
    if review_status == "approved":
        values["reviewed_at"] = "2026-08-13T02:03:04+08:00"
        values["reviewed_match_sha256"] = values["match_sha256"]
        values["review_decision_note"] = "reviewed synthetic fixture"
    return {column: values[column] for column in CURRENT_LOCATION_COLUMNS}


def _synthetic_inputs() -> dict[str, object]:
    explorer_rows = [
        {
            "project": "ALPHA RESIDENCES",
            "street": "ONE ROAD",
            "district": "10",
            "planning_area": "BUKIT TIMAH",
        },
        {
            "project": "TWIN COURT",
            "street": "EAST ROAD",
            "district": "15",
            "planning_area": "BEDOK",
        },
        {
            "project": "TWIN COURT",
            "street": "WEST ROAD",
            "district": "16",
            "planning_area": "BEDOK",
        },
        {
            "project": "RESIDENTIAL APARTMENTS",
            "street": "BUCKET ROAD",
            "district": "14",
            "planning_area": "GEYLANG",
        },
    ]
    comparison_rows = [
        {
            "id": "alpha-id",
            "project": "ALPHA RESIDENCES",
            "street": "ONE ROAD",
            "district": "10",
            "planning_area": "BUKIT TIMAH",
            "selection_label": "ALPHA RESIDENCES",
            "context_key": "shared-context",
        },
        {
            "id": "twin-east-id",
            "project": "TWIN COURT",
            "street": "EAST ROAD",
            "district": "15",
            "planning_area": "BEDOK",
            "selection_label": "TWIN COURT · D15 · EAST ROAD",
            "context_key": "shared-context",
        },
        {
            "id": "twin-west-id",
            "project": "TWIN COURT",
            "street": "WEST ROAD",
            "district": "16",
            "planning_area": "BEDOK",
            "selection_label": "TWIN COURT · D16 · WEST ROAD",
            "context_key": "shared-context",
        },
    ]
    manifest = {
        "dataset_revision": TRANSACTION_REVISION,
        "projects": {
            "alpha-id": _transaction_metadata(0),
            "twin-east-id": _transaction_metadata(1),
            "twin-west-id": _transaction_metadata(2),
        },
    }
    catalog = project_catalog.build_project_catalog(
        explorer_rows,
        comparison_rows,
        {"shared-context": {"estate": "TEST", "archetype": "Test"}},
        manifest,
        latest_project_month="2026-05",
    )
    return {
        "catalog": catalog,
        "manifest": manifest,
        "edge": [
            {"name": "ALPHA RESIDENCES", "slug": "Alpha-Mixed", "url": "one"},
            {"name": "TWIN COURT", "slug": "twin-court", "url": "two"},
            {"name": "ORPHAN CONDO", "slug": "orphan-condo", "url": "three"},
        ],
        "geocodes": [
            _legacy_geocode(
                "ALPHA RESIDENCES", "ONE ROAD", "10", "BUKIT TIMAH", "matched"
            ),
            _legacy_geocode(
                "TWIN COURT", "EAST ROAD", "15", "BEDOK", "low_confidence"
            ),
            _legacy_geocode(
                "TWIN COURT", "WEST ROAD", "16", "BEDOK", "needs_review"
            ),
        ],
        "reports": [
            {
                "project_name": "ALPHA RESIDENCES",
                "project_slug": "alpha-residences",
                "path": "alpha-analysis.html",
                "source": "property_analysis",
                "is_latest": True,
                "street": None,
                "district": None,
                "planning_area": None,
            }
        ],
        "observations": [
            {"source_slug": "twin-court", "Postal District": "15", "Address": "1"}
        ],
    }


def _build(inputs: dict[str, object], **overrides):
    values = {
        "project_catalog": inputs["catalog"],
        "edge_projects": inputs["edge"],
        "geocode_rows": inputs["geocodes"],
        "transaction_manifest": inputs["manifest"],
        "report_routes": inputs["reports"],
        "edge_district_observations": inputs["observations"],
    }
    values.update(overrides)
    return registry.build_project_identity_registry(**values)


def _resign(payload: dict[str, object]) -> None:
    payload["registry_revision"] = registry.compute_registry_revision(payload)


@pytest.fixture
def synthetic(monkeypatch):
    # Reviewed production aliases deliberately require the full committed catalog.
    monkeypatch.setattr(registry, "URA_EDGEPROP_PROJECT_ALIAS", {})
    inputs = _synthetic_inputs()
    inputs["payload"] = _build(inputs)
    return inputs


@pytest.fixture(scope="module")
def committed():
    manifest = json.loads(registry.DEFAULT_TRANSACTION_MANIFEST.read_text(encoding="utf-8"))
    catalog = project_catalog.load_project_catalog(
        registry.DEFAULT_PROJECT_CATALOG, transaction_manifest=manifest
    )
    payload = registry.load_project_identity_registry(
        registry.DEFAULT_REGISTRY_OUT / "manifest.json",
        project_catalog=catalog,
        transaction_manifest=manifest,
    )
    return {"payload": payload, "catalog": catalog, "manifest": manifest}


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _source_keys(payload, source):
    return {
        source_key
        for record in payload["records"]
        for source_key in record["sources"][source]
    }


def test_revision_is_order_independent_and_content_sensitive(synthetic):
    inputs = synthetic
    first = inputs["payload"]
    reordered = _build(
        inputs,
        edge_projects=list(reversed(inputs["edge"])),
        geocode_rows=list(reversed(inputs["geocodes"])),
        report_routes=list(reversed(inputs["reports"])),
        edge_district_observations=list(reversed(inputs["observations"])),
    )
    assert reordered == first
    assert registry.compute_registry_revision(first) == first["registry_revision"]

    revision_field_changed = copy.deepcopy(first)
    revision_field_changed["registry_revision"] = "f" * 64
    assert registry.compute_registry_revision(revision_field_changed) == first[
        "registry_revision"
    ]

    changed_edge = copy.deepcopy(inputs["edge"])
    changed_edge[0]["url"] = "content-changed"
    changed = _build(inputs, edge_projects=changed_edge)
    assert changed["source_revisions"]["edge_projects"] != first["source_revisions"][
        "edge_projects"
    ]
    assert changed["registry_revision"] != first["registry_revision"]


def test_committed_registry_reconciles_every_exact_source_key(committed):
    payload = committed["payload"]
    catalog = committed["catalog"]
    manifest = committed["manifest"]
    edge_rows = _csv_rows(registry.DEFAULT_EDGE_PROJECTS)
    geocode_rows = _csv_rows(registry.DEFAULT_GEOCODES)
    report_routes = registry._committed_report_routes()

    expected_reports = {
        source: {
            f"{route['path']}#{registry._slug(route['project_slug'] or route['project_name'])}"
            for route in report_routes
            if route["source"] == source
        }
        for source in ("property_analysis", "authored_report")
    }
    assert _source_keys(payload, "project_catalog") == {
        project["id"] for project in catalog["projects"]
    }
    assert _source_keys(payload, "ura_explorer") == {
        project["id"] for project in catalog["projects"]
    }
    assert _source_keys(payload, "transaction_manifest") == set(manifest["projects"])
    assert _source_keys(payload, "edgeprop") == {
        row["slug"].strip() for row in edge_rows
    }
    assert _source_keys(payload, "geocode") == {
        "|".join(registry._identity_key(row)) for row in geocode_rows
    }
    assert _source_keys(payload, "property_analysis") == expected_reports[
        "property_analysis"
    ]
    assert _source_keys(payload, "authored_report") == expected_reports[
        "authored_report"
    ]
    assert (
        len(catalog["projects"]),
        len(manifest["projects"]),
        len(edge_rows),
        len(geocode_rows),
    ) == (2400, 2307, 3477, 2397)


def test_committed_registry_contains_exactly_three_reviewed_aliases(committed):
    reviewed = {
        (record["identity"]["name"], alias["name"], alias["source_key"])
        for record in committed["payload"]["records"]
        for alias in record["aliases"]
        if alias["source"] == "edgeprop" and alias["match_basis"] == "reviewed_alias"
    }
    assert reviewed == {
        ("CHUAN PARK (DEMOLISHED)", "CHUAN PARK (OLD)", "chuan-park"),
        ("MERAWOODS", "MERA WOODS", "mera-woods"),
        (
            "SKYLINE 360 @ SAINT THOMAS WALK",
            "SKYLINE 360 @ ST THOMAS WALK",
            "skyline-360-st-thomas-walk",
        ),
    }


def test_duplicate_names_remain_disambiguated_and_name_only(committed):
    records = [
        record
        for record in committed["payload"]["records"]
        if record["identity"]["name"] == "EASTERN LAGOON"
    ]
    full = [record for record in records if record["identity"]["precision"] == "full"]
    ambiguous = [
        record for record in records if record["identity"]["precision"] == "name_only"
    ]

    assert {(record["identity"]["district"], record["identity"]["street"]) for record in full} == {
        ("15", "UPPER EAST COAST ROAD"),
        ("16", "UPPER EAST COAST ROAD"),
    }
    assert len({record["identity"]["selection_label"] for record in full}) == 2
    assert [record["id"] for record in ambiguous] == ["edgeprop:eastern-lagoon"]
    assert ambiguous[0]["evidence"]["resolution"] == "ambiguous_name"
    assert not any(
        ambiguous[0]["capabilities"][key]["available"]
        for key in ("explorer", "comparison", "transactions", "exit")
    )


def test_explorer_routes_include_full_identity_and_are_distinct(committed):
    achieved = [
        record
        for record in committed["payload"]["records"]
        if record["capabilities"]["explorer"]["available"]
    ]
    route_paths = []
    for record in achieved:
        route = record["capabilities"]["explorer"]["routes"][0]
        query = parse_qs(urlsplit(route["path"]).query)
        assert query == {
            "q": [f"{record['identity']['name']} {record['identity']['street']}"],
            "district": [record["identity"]["district"]],
        }
        assert record["capabilities"]["transactions"]["routes"] == [route]
        route_paths.append(route["path"])

    assert len(route_paths) == len(set(route_paths))
    espira_routes = {
        record["capabilities"]["explorer"]["routes"][0]["path"]
        for record in achieved
        if record["identity"]["name"] == "ESPIRA SUITES"
    }
    assert espira_routes == {
        "private_project_comparison_table.html?"
        "q=ESPIRA%20SUITES%20LORONG%20G%20TELOK%20KURAU&district=15",
        "private_project_comparison_table.html?"
        "q=ESPIRA%20SUITES%20LORONG%20H%20TELOK%20KURAU&district=15",
    }


def test_previous_registry_rejects_changed_id_for_same_full_identity(synthetic):
    new_catalog = copy.deepcopy(synthetic["catalog"])
    new_manifest = copy.deepcopy(synthetic["manifest"])
    row = next(project for project in new_catalog["projects"] if project["id"] == "alpha-id")
    row["id"] = "replacement-alpha-id"
    new_manifest["projects"]["replacement-alpha-id"] = new_manifest["projects"].pop(
        "alpha-id"
    )
    new_catalog["catalog_revision"] = project_catalog.compute_catalog_revision(new_catalog)

    with pytest.raises(ValueError, match="Stable project identity.*changed id"):
        _build(
            synthetic,
            project_catalog=new_catalog,
            transaction_manifest=new_manifest,
            previous_registry=synthetic["payload"],
        )


def test_previous_registry_rejects_existing_id_reassigned_to_new_identity(synthetic):
    new_catalog = copy.deepcopy(synthetic["catalog"])
    alpha = next(project for project in new_catalog["projects"] if project["id"] == "alpha-id")
    alpha["street"] = "REASSIGNED ROAD"
    new_catalog["catalog_revision"] = project_catalog.compute_catalog_revision(new_catalog)
    geocodes = copy.deepcopy(synthetic["geocodes"])
    geocodes[0]["street_name"] = "REASSIGNED ROAD"

    with pytest.raises(ValueError, match="Stable registry id.*changed identity"):
        _build(
            synthetic,
            project_catalog=new_catalog,
            geocode_rows=geocodes,
            previous_registry=synthetic["payload"],
        )


@pytest.mark.parametrize(
    ("disabled", "message"),
    [
        ("transactions", "exit lacks transactions"),
        ("comparison", "transactions lack comparison"),
        ("explorer", "comparison lacks explorer"),
    ],
)
def test_validation_enforces_capability_implications(synthetic, disabled, message):
    payload = copy.deepcopy(synthetic["payload"])
    record = next(record for record in payload["records"] if record["id"] == "alpha-id")
    record["capabilities"][disabled].update(
        available=False,
        routes=[],
        evidence_status="not_available",
        reason="Deliberately unavailable.",
    )
    _resign(payload)

    with pytest.raises(ValueError, match=message):
        registry.validate_project_identity_registry(payload)


def test_validation_blocks_name_only_records_from_achieved_capabilities(synthetic):
    payload = copy.deepcopy(synthetic["payload"])
    record = next(
        record for record in payload["records"] if record["id"] == "edgeprop:orphan-condo"
    )
    record["capabilities"]["explorer"].update(
        available=True,
        routes=[
            {
                "path": "private_project_comparison_table.html?q=ORPHAN",
                "source": "private_project_explorer",
                "is_latest": True,
            }
        ],
        evidence_status="achieved_transactions",
        reason=None,
    )
    _resign(payload)

    with pytest.raises(ValueError, match="name-only/non-project.*claims evidence"):
        registry.validate_project_identity_registry(payload)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../escape.html",
        "nested/report.html",
        "/absolute.html",
        "https://example.com/report.html",
        "report.json",
        "report.html#one#two",
    ],
)
def test_build_rejects_unsafe_report_routes(synthetic, unsafe_path):
    reports = copy.deepcopy(synthetic["reports"])
    reports[0]["path"] = unsafe_path
    with pytest.raises(ValueError, match="root-local HTML path|escapes the site root"):
        _build(synthetic, report_routes=reports)


def test_build_rejects_partial_report_identity_qualifiers(synthetic):
    reports = copy.deepcopy(synthetic["reports"])
    reports[0]["street"] = "ONE ROAD"
    with pytest.raises(ValueError, match="qualifiers must be all-null or complete"):
        _build(synthetic, report_routes=reports)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update(schema="project-identity-registry.v0"), "schema must be"),
        (lambda payload: payload.update(unexpected=True), "root fields must be exactly"),
        (
            lambda payload: payload["counts"].update(records=999),
            "counts do not reconcile",
        ),
    ],
)
def test_validation_rejects_resigned_schema_and_count_mutations(
    synthetic, mutate, message
):
    payload = copy.deepcopy(synthetic["payload"])
    mutate(payload)
    _resign(payload)
    with pytest.raises(ValueError, match=message):
        registry.validate_project_identity_registry(payload)


def test_validation_rejects_unsigned_content_mutation(synthetic):
    payload = copy.deepcopy(synthetic["payload"])
    payload["records"][0]["identity"]["name"] = "UNSIGNED CHANGE"
    with pytest.raises(ValueError, match="revision does not match"):
        registry.validate_project_identity_registry(payload)


def test_committed_geocode_states_are_explicit_and_honest(committed):
    payload = committed["payload"]
    statuses = Counter(record["evidence"]["geocode_status"] for record in payload["records"])
    assert payload["registry_revision"] == COMMITTED_REGISTRY_REVISION
    assert statuses == {
        "matched": 2223,
        "low_confidence": 134,
        "needs_review": 40,
        "missing": 3,
        "not_applicable": 1209,
    }
    assert statuses["low_confidence"] + statuses["needs_review"] == 174
    assert sum(bool(record["sources"]["geocode"]) for record in payload["records"]) == 2397
    missing = {
        (
            record["identity"]["name"],
            record["identity"]["street"],
            record["identity"]["district"],
            record["identity"]["planning_area"],
        )
        for record in payload["records"]
        if record["evidence"]["geocode_status"] == "missing"
    }
    assert missing == {
        ("OCHO", "LORONG 32 GEYLANG", "14", "GEYLANG"),
        ("RESIDENTIAL APARTMENTS", "LORONG 30 GEYLANG", "14", "GEYLANG"),
        ("TROPICS @ HAIGSVILLE", "HAIGSVILLE DRIVE", "15", "MARINE PARADE"),
    }
    assert all(
        record["identity"]["precision"] == "name_only"
        for record in payload["records"]
        if record["evidence"]["geocode_status"] == "not_applicable"
    )


def test_unknown_geocode_state_is_not_promoted_to_matched(synthetic):
    geocodes = copy.deepcopy(synthetic["geocodes"])
    geocodes[0]["match_status"] = "unknown-upstream-state"
    payload = _build(synthetic, geocode_rows=geocodes)
    alpha = next(record for record in payload["records"] if record["id"] == "alpha-id")
    assert alpha["evidence"]["geocode_status"] == "needs_review"


@pytest.mark.parametrize("review_status", ["pending_changed", "rejected"])
def test_current_matched_geocode_requires_review_binding(synthetic, review_status):
    row = _current_geocode(review_status=review_status)
    payload = _build(synthetic, geocode_rows=[row])
    alpha = next(record for record in payload["records"] if record["id"] == "alpha-id")

    assert alpha["evidence"]["geocode_status"] == "needs_review"
    assert alpha["sources"]["geocode"] == [
        "ALPHA RESIDENCES|ONE ROAD|10|BUKIT TIMAH"
    ]
    assert payload["counts"]["geocoded"] == 1
    assert payload["source_revisions"]["geocodes"] == registry._content_revision([row])


def test_current_hash_bound_approved_geocode_remains_matched(synthetic):
    row = _current_geocode(review_status="approved")
    payload = _build(synthetic, geocode_rows=[row])
    alpha = next(record for record in payload["records"] if record["id"] == "alpha-id")

    assert alpha["evidence"]["geocode_status"] == "matched"
    assert alpha["sources"]["geocode"] == [
        "ALPHA RESIDENCES|ONE ROAD|10|BUKIT TIMAH"
    ]


@pytest.mark.parametrize(
    ("match_status", "review_status", "expected_status"),
    [
        ("low_confidence", "pending_low_confidence", "low_confidence"),
        ("needs_review", "pending_low_confidence", "needs_review"),
        ("error", "pending_error", "error"),
        ("no_match", "pending_error", "missing"),
    ],
)
def test_current_nonmatched_geocode_states_remain_explicit(
    synthetic, match_status, review_status, expected_status
):
    row = _current_geocode(review_status=review_status)
    row["match_status"] = match_status
    row["match_sha256"] = canonical_project_location_match_sha256(row)
    payload = _build(synthetic, geocode_rows=[row])
    alpha = next(record for record in payload["records"] if record["id"] == "alpha-id")

    assert alpha["evidence"]["geocode_status"] == expected_status
    assert alpha["sources"]["geocode"]


def test_current_malformed_claimed_approval_fails_closed(synthetic):
    row = _current_geocode(review_status="approved")
    row["lat"] = "1.3999"

    with pytest.raises(ProjectLocationContractError, match="invalid review/hash binding"):
        _build(synthetic, geocode_rows=[row])


def test_validation_rejects_catalog_and_transaction_membership_drift(synthetic):
    missing_catalog = copy.deepcopy(synthetic["payload"])
    alpha = next(record for record in missing_catalog["records"] if record["id"] == "alpha-id")
    alpha["sources"]["project_catalog"] = []
    _resign(missing_catalog)
    with pytest.raises(ValueError, match="project-catalog membership does not reconcile"):
        registry.validate_project_identity_registry(
            missing_catalog,
            project_catalog=synthetic["catalog"],
            transaction_manifest=synthetic["manifest"],
        )

    missing_transaction = copy.deepcopy(synthetic["manifest"])
    missing_transaction["projects"].pop("alpha-id")
    with pytest.raises(ValueError, match="transaction membership does not reconcile"):
        registry.validate_project_identity_registry(
            synthetic["payload"], transaction_manifest=missing_transaction
        )


def _changed_payload(synthetic):
    edge = copy.deepcopy(synthetic["edge"])
    edge[0]["url"] = "new immutable input"
    return _build(synthetic, edge_projects=edge)


def test_publish_retains_previous_immutable_generation(tmp_path, synthetic):
    output = tmp_path / "registry"
    first = synthetic["payload"]
    second = _changed_payload(synthetic)
    registry.publish_project_identity_registry(
        output,
        first,
        project_catalog=synthetic["catalog"],
        transaction_manifest=synthetic["manifest"],
    )
    registry.publish_project_identity_registry(
        output,
        second,
        project_catalog=synthetic["catalog"],
        transaction_manifest=synthetic["manifest"],
        previous_registry=first,
    )

    assert registry.load_project_identity_registry(
        output / first["registry_revision"] / "registry.json"
    ) == first
    assert registry.load_project_identity_registry(
        output / second["registry_revision"] / "registry.json"
    ) == second
    assert registry.load_project_identity_registry(output / "manifest.json") == second


def test_root_switch_failure_preserves_previous_manifest(
    tmp_path, synthetic, monkeypatch
):
    output = tmp_path / "registry"
    first = synthetic["payload"]
    second = _changed_payload(synthetic)
    registry.publish_project_identity_registry(output, first)
    original_root = (output / "manifest.json").read_bytes()
    real_replace = registry.os.replace

    def fail_root_switch(source, destination):
        if Path(destination) == output / "manifest.json":
            raise OSError("injected root switch failure")
        return real_replace(source, destination)

    monkeypatch.setattr(registry.os, "replace", fail_root_switch)
    with pytest.raises(OSError, match="injected root switch failure"):
        registry.publish_project_identity_registry(
            output, second, previous_registry=first
        )

    assert (output / "manifest.json").read_bytes() == original_root
    assert registry.load_project_identity_registry(output / "manifest.json") == first
    assert registry.load_project_identity_registry(
        output / second["registry_revision"] / "registry.json"
    ) == second
    assert not list(output.glob(".manifest.*"))
    assert not list(tmp_path.glob(".registry.stage-*"))


def test_committed_root_and_immutable_asset_validate_and_match(committed):
    payload = committed["payload"]
    immutable = registry.DEFAULT_REGISTRY_OUT / payload["registry_revision"] / "registry.json"
    assert registry.registry_asset_path(payload["registry_revision"]) == (
        f"assets/project-identity-registry/{payload['registry_revision']}/registry.json"
    )
    assert registry.load_project_identity_registry(
        immutable,
        project_catalog=committed["catalog"],
        transaction_manifest=committed["manifest"],
    ) == payload
    rebuilt = registry.build_committed_registry()
    assert rebuilt == payload
    assert rebuilt["registry_revision"] == COMMITTED_REGISTRY_REVISION
    assert registry._canonical_bytes(rebuilt) == registry._canonical_bytes(payload)
    generated_reports = {
        analysis.output_path for analysis in registry.discover_property_analyses()
    }
    assert all(
        (registry.ROOT / urlsplit(route["path"]).path).is_file()
        or urlsplit(route["path"]).path in generated_reports
        for record in payload["records"]
        for capability in record["capabilities"].values()
        for route in capability["routes"]
    )
