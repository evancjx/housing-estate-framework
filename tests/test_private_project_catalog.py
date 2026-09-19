"""Focused tests for the shared, immutable private-project catalog."""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

import private_project_catalog as catalog


TRANSACTION_REVISION = "a" * 64


def _transaction_metadata(
    shard: int,
    *,
    count: int,
    first_month: str,
) -> dict[str, object]:
    return {
        "transaction_shard": (
            f"assets/condo-transactions/{TRANSACTION_REVISION}/"
            f"shard-{shard:02d}.json"
        ),
        "transaction_count": count,
        "transaction_first_month": first_month,
        "transaction_last_month": "2026-07",
        "transaction_complete_through": "2026-06",
    }


def _inputs():
    explorer_rows = [
        {
            "project": "GENERIC COURT",
            "street": "THREE ROAD",
            "district": "9",
            "planning_area": "QUEENSTOWN",
            "tenure": "99-year",
        },
        {
            "project": "BETA GARDENS",
            "street": "TWO ROAD",
            "district": "11",
            "planning_area": "NOVENA",
            "tenure": "Freehold",
        },
        {
            "project": "ALPHA RESIDENCES",
            "street": "ONE ROAD",
            "district": "10",
            "planning_area": "BUKIT TIMAH",
            "tenure": "999-year",
        },
    ]
    comparison_rows = [
        {
            "id": "existing-beta-id",
            "project": "BETA GARDENS",
            "street": "TWO ROAD",
            "district": "11",
            "planning_area": "NOVENA",
            "selection_label": "BETA GARDENS · D11 · TWO ROAD",
            "context_key": "city-fringe",
            "provision_score": 4.1,
        },
        {
            "id": "existing-alpha-id",
            "project": "ALPHA RESIDENCES",
            "street": "ONE ROAD",
            "district": "10",
            "planning_area": "BUKIT TIMAH",
            "selection_label": "ALPHA RESIDENCES · D10 · ONE ROAD",
            "context_key": "mature-central",
            "provision_score": 4.4,
        },
    ]
    contexts = {
        "mature-central": {"estate": "BUKIT TIMAH", "archetype": "Mature"},
        "city-fringe": {"estate": "NOVENA", "archetype": "Central"},
    }
    manifest = {
        "dataset_revision": TRANSACTION_REVISION,
        "projects": {
            "existing-alpha-id": _transaction_metadata(
                0, count=1, first_month="2021-01"
            ),
            "existing-beta-id": _transaction_metadata(
                63, count=2, first_month="2020-02"
            ),
        },
    }
    return explorer_rows, comparison_rows, contexts, manifest


def _build(*, latest_project_month: str = "2026-07"):
    explorer_rows, comparison_rows, contexts, manifest = _inputs()
    payload = catalog.build_project_catalog(
        explorer_rows,
        comparison_rows,
        contexts,
        manifest,
        latest_project_month=latest_project_month,
    )
    return payload, manifest


def _resign(payload: dict[str, object]) -> dict[str, object]:
    payload["catalog_revision"] = catalog.compute_catalog_revision(payload)
    return payload


def _replace_first_context_with_blank(payload: dict[str, object]) -> None:
    project = payload["projects"][0]
    context_key = project["context_key"]
    payload["contexts"][""] = payload["contexts"].pop(context_key)
    project["context_key"] = ""


def test_builds_exact_union_capabilities_and_preserves_comparison_ids():
    payload, manifest = _build()
    projects = {project["id"]: project for project in payload["projects"]}

    assert payload["counts"] == {"all": 3, "comparison": 2, "transaction": 2}
    assert set(projects) == {
        "existing-alpha-id",
        "existing-beta-id",
        "explorer-generic-court-d09-three-road-queenstown",
    }
    assert [project["project"] for project in payload["projects"]] == [
        "ALPHA RESIDENCES",
        "BETA GARDENS",
        "GENERIC COURT",
    ]

    expected_full_capabilities = {
        "private_explorer": True,
        "framework_comparison": True,
        "transactions": True,
        "project_exit": True,
    }
    for project_id in ("existing-alpha-id", "existing-beta-id"):
        assert projects[project_id]["capabilities"] == expected_full_capabilities
        for field in catalog.TRANSACTION_PROJECT_FIELDS:
            assert projects[project_id][field] == manifest["projects"][project_id][
                field
            ]

    generic = projects["explorer-generic-court-d09-three-road-queenstown"]
    assert generic["selection_label"] == "GENERIC COURT"
    assert generic["context_key"] is None
    assert generic["capabilities"] == {
        "private_explorer": True,
        "framework_comparison": False,
        "transactions": False,
        "project_exit": False,
    }
    assert all(generic[field] is None for field in catalog.TRANSACTION_PROJECT_FIELDS)


def test_revision_is_deterministic_order_independent_and_content_sensitive():
    explorer_rows, comparison_rows, contexts, manifest = _inputs()
    first = catalog.build_project_catalog(
        explorer_rows,
        comparison_rows,
        contexts,
        manifest,
        latest_project_month="2026-07",
    )
    reordered = catalog.build_project_catalog(
        list(reversed(explorer_rows)),
        list(reversed(comparison_rows)),
        dict(reversed(list(contexts.items()))),
        {
            "projects": dict(reversed(list(manifest["projects"].items()))),
            "dataset_revision": manifest["dataset_revision"],
        },
        latest_project_month="2026-07",
    )

    assert first == reordered
    assert catalog.compute_catalog_revision(first) == first["catalog_revision"]
    revision_field_changed = copy.deepcopy(first)
    revision_field_changed["catalog_revision"] = "f" * 64
    assert catalog.compute_catalog_revision(revision_field_changed) == first[
        "catalog_revision"
    ]

    changed_explorer = copy.deepcopy(explorer_rows)
    changed_explorer[0]["tenure"] = "Freehold"
    changed = catalog.build_project_catalog(
        changed_explorer,
        comparison_rows,
        contexts,
        manifest,
        latest_project_month="2026-07",
    )
    assert changed["catalog_revision"] != first["catalog_revision"]


@pytest.mark.parametrize(
    ("comparison_change", "manifest_change", "message"),
    [
        (
            lambda rows: rows.pop(),
            lambda manifest: None,
            "membership differ",
        ),
        (
            lambda rows: None,
            lambda manifest: manifest["projects"].pop("existing-beta-id"),
            "membership differ",
        ),
        (
            lambda rows: None,
            lambda manifest: manifest["projects"].update(
                {"manifest-only": _transaction_metadata(2, count=0, first_month="2021-01")}
            ),
            "membership differ",
        ),
    ],
)
def test_build_rejects_comparison_transaction_membership_drift(
    comparison_change, manifest_change, message
):
    explorer_rows, comparison_rows, contexts, manifest = _inputs()
    comparison_change(comparison_rows)
    manifest_change(manifest)

    with pytest.raises(ValueError, match=message):
        catalog.build_project_catalog(
            explorer_rows,
            comparison_rows,
            contexts,
            manifest,
            latest_project_month="2026-07",
        )


def test_validation_rejects_unsigned_content_tampering():
    payload, manifest = _build()
    payload["projects"][0]["selection_label"] = "TAMPERED"

    with pytest.raises(ValueError, match="revision does not match"):
        catalog.validate_project_catalog(payload, transaction_manifest=manifest)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload.update(schema="private-project-catalog.v0"),
            "schema must be",
        ),
        (
            lambda payload: payload.update(unexpected=True),
            "root fields must be exactly",
        ),
        (
            lambda payload: payload["counts"].update(all=99),
            "counts do not reconcile",
        ),
        (
            lambda payload: payload["counts"].update(all=True),
            "counts must be non-negative integers",
        ),
        (
            lambda payload: payload.update(latest_project_month="２０２６-07"),
            "latest_project_month must be YYYY-MM",
        ),
        (
            lambda payload: payload["projects"][1].update(
                id=payload["projects"][0]["id"]
            ),
            "duplicate id",
        ),
        (
            lambda payload: payload["projects"][0]["capabilities"].update(
                unexpected=False
            ),
            "capabilities are invalid",
        ),
        (
            lambda payload: payload["projects"][0].update(context_key="missing"),
            "context is missing",
        ),
        (
            lambda payload: payload["contexts"].update(
                {"unused": {"estate": "NOWHERE"}}
            ),
            "missing or unused framework contexts",
        ),
        (
            _replace_first_context_with_blank,
            "context entries must be named objects",
        ),
        (
            lambda payload: payload["projects"][0].pop("transaction_last_month"),
            "missing transaction fields",
        ),
    ],
)
def test_validation_rejects_resigned_schema_count_and_context_corruption(
    mutate, message
):
    payload, _ = _build()
    mutate(payload)
    _resign(payload)

    with pytest.raises(ValueError, match=message):
        catalog.validate_project_catalog(payload)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        f"assets/condo-transactions/{TRANSACTION_REVISION}/shard-64.json",
        f"assets/condo-transactions/{TRANSACTION_REVISION}/shard-00.json/extra",
        f"assets/condo-transactions/{TRANSACTION_REVISION}/shard-00.json?x=1",
        f"assets/condo-transactions/{TRANSACTION_REVISION}/shard-../manifest.json",
        f"assets/condo-transactions/{'b' * 64}/shard-00.json",
        f"/assets/condo-transactions/{TRANSACTION_REVISION}/shard-00.json",
    ],
)
def test_validation_rejects_noncanonical_transaction_shard_paths(unsafe_path):
    payload, _ = _build()
    payload["projects"][0]["transaction_shard"] = unsafe_path
    _resign(payload)

    with pytest.raises(ValueError, match="transaction shard is not revisioned"):
        catalog.validate_project_catalog(payload)


def test_validation_rejects_boolean_transaction_count():
    payload, _ = _build()
    assert payload["projects"][0]["transaction_count"] == 1
    payload["projects"][0]["transaction_count"] = True
    _resign(payload)

    with pytest.raises(ValueError, match="transaction_count is invalid"):
        catalog.validate_project_catalog(payload)


@pytest.mark.parametrize(
    ("mutate_manifest", "message"),
    [
        (
            lambda manifest: manifest.update(dataset_revision="b" * 64),
            "catalog and transaction revisions differ",
        ),
        (
            lambda manifest: manifest["projects"]["existing-alpha-id"].update(
                transaction_count=99
            ),
            "differs from manifest",
        ),
        (
            lambda manifest: manifest["projects"].pop("existing-alpha-id"),
            "is not manifested",
        ),
        (
            lambda manifest: manifest["projects"].update(
                {"manifest-only": _transaction_metadata(2, count=0, first_month="2021-01")}
            ),
            "membership does not reconcile",
        ),
    ],
)
def test_validation_reconciles_transaction_manifest_exactly(
    mutate_manifest, message
):
    payload, manifest = _build()
    mutate_manifest(manifest)

    with pytest.raises(ValueError, match=message):
        catalog.validate_project_catalog(payload, transaction_manifest=manifest)


@pytest.mark.parametrize(
    "unsafe_revision",
    [
        "",
        "a" * 63,
        "A" * 64,
        "../manifest.json",
        "a" * 64 + "/catalog.json",
    ],
)
def test_catalog_asset_path_accepts_only_safe_sha256_revisions(unsafe_revision):
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        catalog.catalog_asset_path(unsafe_revision)

    assert catalog.catalog_asset_path("b" * 64) == (
        f"assets/project-catalog/{'b' * 64}/catalog.json"
    )


def test_publish_retains_immutable_revisions_switches_root_and_loads_helpers(
    tmp_path,
):
    output = tmp_path / "catalog"
    old, manifest = _build(latest_project_month="2026-07")
    new, _ = _build(latest_project_month="2026-08")

    old_paths = catalog.publish_project_catalog(
        output, old, transaction_manifest=manifest
    )
    new_paths = catalog.publish_project_catalog(
        output, new, transaction_manifest=manifest
    )

    assert old_paths == [
        output / old["catalog_revision"] / "catalog.json",
        output / "manifest.json",
    ]
    assert new_paths == [
        output / new["catalog_revision"] / "catalog.json",
        output / "manifest.json",
    ]
    assert catalog.load_project_catalog(
        old_paths[0], transaction_manifest=manifest
    ) == old
    assert catalog.load_project_catalog(
        new_paths[0], transaction_manifest=manifest
    ) == new
    assert catalog.load_project_catalog(
        output / "manifest.json", transaction_manifest=manifest
    ) == new

    comparisons = catalog.comparison_projects(new)
    explorers = catalog.explorer_projects(new)
    assert [row["id"] for row in comparisons] == [
        "existing-alpha-id",
        "existing-beta-id",
    ]
    assert len(explorers) == 3
    comparisons[0]["selection_label"] = "CALLER MUTATION"
    assert new["projects"][0]["selection_label"] != "CALLER MUTATION"


def test_staged_write_failure_preserves_prior_root_and_revision(tmp_path, monkeypatch):
    output = tmp_path / "catalog"
    old, manifest = _build(latest_project_month="2026-07")
    new, _ = _build(latest_project_month="2026-08")
    catalog.publish_project_catalog(output, old, transaction_manifest=manifest)
    old_root = (output / "manifest.json").read_bytes()

    def fail_staged_write(path, payload):
        assert ".catalog.stage-" in path.parent.name
        raise OSError("injected staged catalog write failure")

    monkeypatch.setattr(catalog, "_write_json_file", fail_staged_write)
    with pytest.raises(OSError, match="injected staged catalog write failure"):
        catalog.publish_project_catalog(output, new, transaction_manifest=manifest)

    assert (output / "manifest.json").read_bytes() == old_root
    assert (output / old["catalog_revision"] / "catalog.json").is_file()
    assert not (output / new["catalog_revision"]).exists()
    assert not list(tmp_path.glob(".catalog.stage-*"))


def test_failed_root_switch_preserves_prior_root_and_complete_new_revision(
    tmp_path, monkeypatch
):
    output = tmp_path / "catalog"
    old, manifest = _build(latest_project_month="2026-07")
    new, _ = _build(latest_project_month="2026-08")
    catalog.publish_project_catalog(output, old, transaction_manifest=manifest)
    old_root = (output / "manifest.json").read_bytes()
    real_replace = catalog.os.replace

    def fail_root_switch(source, destination):
        if pathlib.Path(destination) == output / "manifest.json":
            raise OSError("injected root catalog switch failure")
        return real_replace(source, destination)

    monkeypatch.setattr(catalog.os, "replace", fail_root_switch)
    with pytest.raises(OSError, match="injected root catalog switch failure"):
        catalog.publish_project_catalog(output, new, transaction_manifest=manifest)

    assert (output / "manifest.json").read_bytes() == old_root
    assert (output / old["catalog_revision"] / "catalog.json").is_file()
    new_catalog = output / new["catalog_revision"] / "catalog.json"
    assert catalog.load_project_catalog(
        new_catalog, transaction_manifest=manifest
    ) == new
    assert not list(output.glob(".manifest.*.json"))
    assert not list(tmp_path.glob(".catalog.stage-*"))


@pytest.mark.parametrize("contents", ["not JSON", "[]"])
def test_load_rejects_invalid_or_nonobject_documents(tmp_path, contents):
    path = tmp_path / "catalog.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot load|must contain a JSON object"):
        catalog.load_project_catalog(path)


def test_publish_rejects_corrupt_existing_immutable_revision(tmp_path):
    output = tmp_path / "catalog"
    payload, manifest = _build()
    catalog.publish_project_catalog(output, payload, transaction_manifest=manifest)
    root_before = (output / "manifest.json").read_bytes()
    immutable = output / payload["catalog_revision"] / "catalog.json"
    immutable.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="root fields must be exactly"):
        catalog.publish_project_catalog(
            output, payload, transaction_manifest=manifest
        )

    assert (output / "manifest.json").read_bytes() == root_before
    assert not list(tmp_path.glob(".catalog.stage-*"))
