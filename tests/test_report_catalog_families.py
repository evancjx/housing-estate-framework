"""Report-catalog data-family mapping contract checks."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import build_pages_site
from sg_estate.reporting.catalog import (
    DATA_FAMILY_IDS,
    REPORT_CATALOG_SCHEMA_VERSION,
)
from sg_estate.reporting.property_analysis import (
    discover_property_analyses,
    property_catalog_entries,
)


ROOT = Path(__file__).parent.parent


def _authored_catalog() -> dict:
    return json.loads((ROOT / "site" / "reports.json").read_text(encoding="utf-8"))


def _write_catalog(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "reports.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_authored_catalog_uses_complete_v2_data_family_vocabulary():
    catalog = build_pages_site.load_catalog()
    observed = {
        family_id
        for report in catalog["reports"]
        for family_id in report["data_families"]
    }

    assert catalog["schema_version"] == REPORT_CATALOG_SCHEMA_VERSION == 2
    assert observed == set(DATA_FAMILY_IDS)
    assert all(report["data_families"] for report in catalog["reports"])
    assert all(
        len(report["data_families"]) == len(set(report["data_families"]))
        for report in catalog["reports"]
    )


def test_representative_reports_map_to_distinct_evidence_families():
    reports = {
        report["id"]: report for report in build_pages_site.load_catalog()["reports"]
    }

    assert reports["estate-comparison"]["data_families"] == [
        "estate_model",
        "private_transactions",
    ]
    assert reports["home-loan-planner"]["data_families"] == [
        "finance_assumptions"
    ]
    assert reports["mrt-comparison"]["data_families"] == [
        "rail_network",
        "estate_model",
        "private_transactions",
    ]
    assert reports["project-exit-comparison"]["data_families"] == [
        "private_transactions",
        "rail_network",
        "finance_assumptions",
        "market_research",
    ]


def test_authored_project_reports_declare_registry_match_names():
    reports = {
        report["id"]: report for report in build_pages_site.load_catalog()["reports"]
    }

    assert reports["poiz-east-comparison"]["project_names"] == [
        "THE POIZ RESIDENCES"
    ]
    assert reports["poiz-east-transactions"]["project_names"] == [
        "THE POIZ RESIDENCES"
    ]
    assert reports["canberra-d27"]["project_names"] == [
        "CANBERRA CRESCENT RESIDENCES"
    ]
    assert reports["katong-comparison"]["project_names"] == [
        "EMERALD OF KATONG",
        "TEMBUSU GRAND",
        "GRAND DUNMAN",
        "THE CONTINUUM",
        "KATONG REGENCY",
        "HAIG COURT",
        "THE SHORE RESIDENCES",
        "ONE AMBER",
    ]


def test_generated_property_analyses_map_only_to_market_research():
    entries = property_catalog_entries(discover_property_analyses())

    assert entries
    assert all(
        entry["data_families"] == ["market_research"] for entry in entries
    )


def test_data_status_uses_the_report_catalog_family_vocabulary():
    status = build_pages_site.build_data_status()

    assert set(status["families"]) == DATA_FAMILY_IDS


def test_catalog_validation_rejects_missing_data_families(tmp_path):
    catalog = copy.deepcopy(_authored_catalog())
    catalog["reports"][0].pop("data_families")

    with pytest.raises(ValueError, match="missing: data_families"):
        build_pages_site.load_catalog(_write_catalog(tmp_path, catalog))


@pytest.mark.parametrize(
    ("families", "message"),
    (
        ([], "must be a non-empty list"),
        ([""], "must contain non-empty string identifiers"),
        (["market_estimates"], "unknown data family identifiers"),
        (["estate_model", "estate_model"], "duplicate identifiers"),
    ),
)
def test_catalog_validation_rejects_invalid_data_families(
    tmp_path,
    families,
    message,
):
    catalog = copy.deepcopy(_authored_catalog())
    catalog["reports"][0]["data_families"] = families

    with pytest.raises(ValueError, match=message):
        build_pages_site.load_catalog(_write_catalog(tmp_path, catalog))


def test_catalog_validation_rejects_pre_mapping_schema(tmp_path):
    catalog = _authored_catalog()
    catalog["schema_version"] = 1

    with pytest.raises(ValueError, match="schema_version must be 2"):
        build_pages_site.load_catalog(_write_catalog(tmp_path, catalog))


@pytest.mark.parametrize(
    "project_names",
    (
        [],
        [""],
        "THE POIZ RESIDENCES",
        ["The Poiz Residences", "  THE   POIZ RESIDENCES  "],
    ),
)
def test_catalog_validation_rejects_invalid_project_names(
    tmp_path,
    project_names,
):
    catalog = copy.deepcopy(_authored_catalog())
    catalog["reports"][0]["project_names"] = project_names

    with pytest.raises(ValueError, match="project_names"):
        build_pages_site.load_catalog(_write_catalog(tmp_path, catalog))
