"""Focused tests for bounded multi-condo transaction shards."""

from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

import multi_condo_transactions as transactions


def _project(
    project_id: str,
    *,
    name: str = "ALPHA RESIDENCES",
    street: str = "ONE ROAD",
    district: str = "10",
    area: str = "BUKIT TIMAH",
):
    return {
        "id": project_id,
        "project": name,
        "street": street,
        "district": district,
        "planning_area": area,
        "unrelated_catalog_field": "preserved",
    }


def _ura(
    *,
    name: str = "ALPHA RESIDENCES",
    street: str = "ONE ROAD",
    district: str = "10",
    area: str = "BUKIT TIMAH",
    month: str = "2026-07",
    price=2_000_000,
    sqm=100.0,
    sale_type: str = "Resale",
    floor: str = "10-15",
):
    return {
        "project_name": name,
        "street_name": street,
        "postal_district": district,
        "planning_area": area,
        "sale_month": month,
        "transacted_price": price,
        "area_sqm": sqm,
        "type_of_sale": sale_type,
        "floor_level": floor,
        "purchaser_address": "must never reach browser JSON",
    }


def _bedroom(
    *,
    name: str = "ALPHA RESIDENCES",
    district: str = "10",
    month: str = "2026-07",
    price=2_000_000,
    sqm=100.0,
    bedrooms=3,
    source: str = "edgeprop_exact",
    data_source: str = "ura_private",
):
    return {
        "project_name": name,
        "postal_district": district,
        "sale_month": month,
        "transacted_price": price,
        "area_sqm": sqm,
        "type_of_sale": "Resale",
        "floor_level": "10-15",
        "bedrooms": bedrooms,
        "bedroom_source": source,
        "data_source": data_source,
    }


def _build(raw_rows, bedroom_rows, projects):
    return transactions.build_transaction_shards(
        pd.DataFrame(raw_rows),
        pd.DataFrame(bedroom_rows),
        projects,
    )


def _records(shards, project_id):
    return shards[transactions.shard_index(project_id)]["projects"][project_id]


def _decode(shards, project_id):
    shard = shards[transactions.shard_index(project_id)]
    enumerations = shard["enumerations"]
    output = []
    for encoded in shard["projects"][project_id]:
        decoded = dict(zip(shard["schema"]["fields"], encoded))
        for field, enum_name in shard["schema"]["enumerated_fields"].items():
            if decoded[field] is not None:
                decoded[field] = enumerations[enum_name][decoded[field]]
        output.append(decoded)
    return output


def test_exact_four_part_identity_separates_same_named_projects():
    projects = [
        _project("alpha-one", street="ONE ROAD"),
        _project("alpha-two", street="TWO ROAD"),
        _project(
            "alpha-other-area",
            street="ONE ROAD",
            area="TANGLIN",
        ),
    ]
    raw = [
        _ura(street="ONE ROAD", price=1_000_000),
        _ura(street="TWO ROAD", price=2_000_000),
        _ura(street="ONE ROAD", area="TANGLIN", price=3_000_000),
        _ura(street="UNLISTED ROAD", price=4_000_000),
    ]
    _, shards, manifest = _build(raw, [], projects)

    assert _decode(shards, "alpha-one")[0]["price"] == 1_000_000
    assert _decode(shards, "alpha-two")[0]["price"] == 2_000_000
    assert _decode(shards, "alpha-other-area")[0]["price"] == 3_000_000
    assert manifest["source_metadata"]["counts"]["canonical_unmapped_rows"] == 1


def test_backfill_is_omitted_when_name_and_district_are_ambiguous():
    projects = [
        _project("alpha-one", street="ONE ROAD"),
        _project("alpha-two", street="TWO ROAD"),
    ]
    backfill = _bedroom(
        month="2020-05",
        data_source="edgeprop_backfill",
    )
    _, shards, manifest = _build([_ura(street="ONE ROAD")], [backfill], projects)

    assert len(_records(shards, "alpha-one")) == 1
    assert _records(shards, "alpha-two") == []
    counts = manifest["source_metadata"]["counts"]
    assert counts["backfill_input_rows"] == 1
    assert counts["backfill_ambiguous_rows"] == 1
    assert counts["backfill_included_rows"] == 0


def test_duplicate_official_rows_are_preserved_and_enriched_by_occurrence():
    official = _ura()
    raw = [official.copy(), official.copy()]
    bedrooms = [
        _bedroom(bedrooms=2),
        _bedroom(bedrooms=3),
    ]

    _, shards, manifest = _build(raw, bedrooms, [_project("alpha")])
    decoded = _decode(shards, "alpha")

    assert len(decoded) == 2
    assert [record["bedrooms"] for record in decoded] == [2, 3]
    assert all(record["bedroom_source"] == "edgeprop_exact" for record in decoded)
    assert manifest["projects"]["alpha"]["transaction_count"] == 2


def test_invalid_and_out_of_scope_rows_do_not_reach_browser_records():
    raw = [
        _ura(),
        _ura(month="July 2026"),
        _ura(price=0),
        _ura(sqm=-1),
        _ura(month="2020-12"),
    ]
    backfill = [
        _bedroom(month="2020-05", data_source="edgeprop_backfill"),
        _bedroom(month="2021-05", data_source="edgeprop_backfill"),
        _bedroom(month="2021-06", data_source="edgeprop_backfill"),
        _bedroom(month="2020-07", price=0, data_source="edgeprop_backfill"),
        _bedroom(
            name="UNKNOWN CONDO",
            month="2020-08",
            data_source="edgeprop_backfill",
        ),
    ]

    _, shards, manifest = _build(raw, backfill, [_project("alpha")])
    decoded = _decode(shards, "alpha")
    counts = manifest["source_metadata"]["counts"]

    assert [record["sale_month"] for record in decoded] == ["2026-07", "2020-05"]
    assert counts["canonical_invalid_rows"] == 4
    assert counts["backfill_invalid_rows"] == 3
    assert counts["backfill_unmapped_rows"] == 1
    assert all(set(record) == set(transactions.RECORD_FIELDS) for record in decoded)
    assert "purchaser_address" not in json.dumps(shards)


def test_shards_are_deterministic_and_counts_coverage_reconcile():
    projects = [
        _project("alpha"),
        _project(
            "beta",
            name="BETA CONDO",
            street="TWO ROAD",
            district="11",
            area="NOVENA",
        ),
    ]
    untouched = copy.deepcopy(projects)
    raw = [
        _ura(month="2021-06", price=1_000_000),
        _ura(month="2026-06", price=2_000_000),
        _ura(month="2026-07", price=2_100_000),
        _ura(
            name="BETA CONDO",
            street="TWO ROAD",
            district="11",
            area="NOVENA",
            month="2026-07",
            price=3_000_000,
            sqm=120,
        ),
    ]
    bedroom_rows = [
        _bedroom(
            month="2019-03",
            price=900_000,
            sqm=90,
            data_source="edgeprop_backfill",
        )
    ]

    first = _build(raw, bedroom_rows, projects)
    second = _build(raw, bedroom_rows, projects)
    copied, shards, manifest = first

    assert projects == untouched
    assert first == second
    assert len(shards) == transactions.SHARD_COUNT
    assert set(shards) == set(range(64))
    assert all(
        project["transaction_shard"]
        == f"assets/condo-transactions/shard-{transactions.shard_index(project['id']):02d}.json"
        for project in copied
    )
    canonical = manifest["source_metadata"]["canonical"]
    assert canonical["start_month"] == "2021-06"
    assert canonical["latest_month"] == "2026-07"
    assert canonical["partial_month"] == "2026-07"
    assert canonical["complete_end"] == "2026-06"
    assert canonical["analysis_60_start"] == "2021-07"
    assert manifest["source_metadata"]["historical_backfill"] == {
        "source": "edgeprop_backfill",
        "status": "incomplete",
        "period_start": "2019-01",
        "period_end": "2020-12",
        "observed_start": "2019-03",
        "observed_end": "2019-03",
    }
    reconciliation = manifest["source_metadata"]["reconciliation"]
    assert reconciliation == {
        "project_transaction_count": 5,
        "shard_transaction_count": 5,
        "matches": True,
    }
    assert sum(project["transaction_count"] for project in copied) == 5
    assert sum(
        shard["shard_metadata"]["transaction_count"] for shard in shards.values()
    ) == 5
    for index, shard in shards.items():
        assert shard["schema"]["fields"] == transactions.RECORD_FIELDS
        assert "enumerations" in shard
        assert "projects" in shard
        assert shard["shard_metadata"]["index"] == index

    alpha = _decode(shards, "alpha")
    expected_psf = 2_100_000 / (100 * transactions.SQM_TO_SQFT)
    assert alpha[0]["psf"] == pytest.approx(expected_psf, abs=0.01)


def test_write_shards_overwrites_only_fixed_targets(tmp_path):
    _, shards, manifest = _build([_ura()], [], [_project("alpha")])
    unrelated = tmp_path / "keep-me.json"
    unrelated.write_text("user data", encoding="utf-8")
    old_shard = tmp_path / "shard-00.json"
    old_shard.write_text("old", encoding="utf-8")

    written = transactions.write_shards(tmp_path, shards, manifest)

    assert len(written) == 65
    assert unrelated.read_text(encoding="utf-8") == "user data"
    assert old_shard.read_text(encoding="utf-8") != "old"
    assert len(list(tmp_path.glob("shard-*.json"))) == 64
    assert json.loads((tmp_path / "manifest.json").read_text())["projects"][
        "alpha"
    ]["transaction_count"] == 1


def test_rejects_non_fixed_shard_count_and_duplicate_project_ids():
    raw = pd.DataFrame([_ura()])
    with pytest.raises(ValueError, match="fixed at 64"):
        transactions.build_transaction_shards(
            raw, pd.DataFrame(), [_project("alpha")], shard_count=8
        )
    with pytest.raises(ValueError, match="IDs are not unique"):
        transactions.build_transaction_shards(
            raw, pd.DataFrame(), [_project("alpha"), _project("alpha")]
        )
