"""Tests for the interactive two-condominium framework comparison."""

from datetime import date
import json
from pathlib import Path
import re

import pandas as pd
import pytest

import gen_condo_framework_comparison_html as comparison
import private_project_catalog


ROOT = Path(__file__).resolve().parents[1]
TRANSACTION_REVISION = "a" * 64


def _master():
    return pd.DataFrame(
        [
            {
                "estate": "TEST ESTATE",
                "archetype": "C",
                "provision_band": "B+",
                "provision_score": 4.0,
                "D_T0": 0.9,
                "yf_T0_band": "B",
                "sp_T0_band": "B+",
                "ret_T0_band": "C",
                "ls_T0_band": "B",
                "ls_T5_band": "B+",
                "ls_T15_band": "A",
                "gap_yf_T0": 0.1,
                "gap_sp_T0": 0.2,
                "gap_ret_T0": -0.3,
                "gap_ls_T0": 0.0,
                "value_private_band": "B+",
                "value_private_score": 4.4,
                "value_private_n": 120,
            }
        ]
    )


def _employment(score, band):
    return pd.DataFrame(
        [{"estate": "TEST ESTATE", "emp_score": score, "emp_band": band}]
    )


def _contexts():
    life_paths = pd.DataFrame(
        [
            {
                "estate": "TEST ESTATE",
                "path": "forming_family",
                "delta": 0.8,
                "band_shift": "C→B+",
            },
            {
                "estate": "TEST ESTATE",
                "path": "downsizing",
                "delta": -0.1,
                "band_shift": "B→B",
            },
        ]
    )
    return comparison.build_framework_contexts(
        _master(),
        pd.DataFrame([{"estate": "TEST ESTATE", "noise": 4}]),
        _employment(4.0, "B+"),
        _employment(4.2, "B+"),
        _employment(4.5, "A"),
        life_paths,
    )


def _aggregate(project, street, price=2.0):
    return {
        "project": project,
        "street": street,
        "district": "15",
        "planning_area": "TEST ESTATE",
        "context_area": "TEST ESTATE",
        "context_basis": "direct",
        "property_type": "Condominium",
        "tenure": "Freehold",
        "market_segment": "Rest of Central Region",
        "n": 20,
        "recent_n": 5,
        "first_sale": "2022-01",
        "last_sale": "2026-06",
        "sale_mix": "Resale:20",
        "median_price_mil": price,
        "median_psm": 20_000,
        "median_area_sqm": 100,
        "recent_delta_pct": 3.0,
        "district_delta_pct": 2.0,
        "station_display": "TEST MRT (TE99)",
        "station_distance_m": 400,
        "station_status": "Open",
        "location_source": "project_geocode",
        "primary_1km_count": 2,
        "primary_1km_schools": "ONE PRIMARY; TWO PRIMARY",
        "best_primary_1km_school": "ONE PRIMARY",
        "best_primary_1km_distance_m": 450,
        "school_metrics_source": "project_geocode",
    }


def _catalog(projects):
    browser_projects, contexts = comparison.build_browser_payload(projects)
    for index, project in enumerate(browser_projects):
        project.update(
            {
                "capabilities": {
                    "private_explorer": True,
                    "framework_comparison": True,
                    "transactions": True,
                    "project_exit": True,
                },
                "transaction_shard": (
                    f"assets/condo-transactions/{TRANSACTION_REVISION}/"
                    f"shard-{index:02d}.json"
                ),
                "transaction_count": project["transactions_n"],
                "transaction_first_month": project["first_sale"],
                "transaction_last_month": project["last_sale"],
                "transaction_complete_through": "2026-05",
            }
        )
    payload = {
        "schema": private_project_catalog.CATALOG_SCHEMA,
        "catalog_revision": None,
        "transaction_dataset_revision": TRANSACTION_REVISION,
        "latest_project_month": "2026-06",
        "counts": {
            "all": len(browser_projects),
            "comparison": len(browser_projects),
            "transaction": len(browser_projects),
        },
        "projects": browser_projects,
        "contexts": contexts,
    }
    payload["catalog_revision"] = private_project_catalog.compute_catalog_revision(
        payload
    )
    return payload


def test_framework_context_matches_comparison_table_factor_families():
    context = _contexts()["TEST ESTATE"]

    assert context["d_t0"] == pytest.approx(0.9)
    assert context["provision_band"] == "B+"
    assert context["yf_t0_band"] == "B"
    assert context["ls_t15_band"] == "A"
    assert context["private_value_multiplier"] == pytest.approx(1.1)
    assert context["employment_t15_band"] == "A"
    assert context["best_path"] == "forming_family"
    assert context["worst_path"] == "downsizing"
    assert "Current disruption" in context["flags"]


def test_prepare_projects_removes_generic_names_and_disambiguates_duplicates():
    aggregates = [
        _aggregate("TEST CONDO", "FIRST ROAD"),
        _aggregate("TEST CONDO", "SECOND ROAD"),
        _aggregate("OTHER CONDO", "THIRD ROAD"),
        _aggregate("RESIDENTIAL APARTMENTS", "UNKNOWN ROAD"),
    ]

    projects = comparison.prepare_projects(aggregates, _contexts())

    assert len(projects) == 3
    assert len({project["id"] for project in projects}) == 3
    duplicate_labels = [
        project["selection_label"]
        for project in projects
        if project["project"] == "TEST CONDO"
    ]
    assert all("D15" in label for label in duplicate_labels)
    assert all(project["provision_score"] == 4.0 for project in projects)
    assert projects[0]["median_psf"] == pytest.approx(
        20_000 / comparison.SQM_TO_SQFT
    )


def test_render_exposes_two_inputs_and_keeps_estate_context_disclosed():
    projects = comparison.prepare_projects(
        [
            _aggregate("FIRST CONDO", "FIRST ROAD"),
            _aggregate("SECOND CONDO", "SECOND ROAD", price=2.5),
        ],
        _contexts(),
    )

    page = comparison.render_html(
        projects, "2026-06", date(2026, 7, 26), _catalog(projects)
    )

    assert 'id="project-a"' in page
    assert 'id="project-b"' in page
    assert 'id="swap-projects"' in page
    assert "Identity and Provision context" in page
    assert "Liveability (T0) and lifestyle trajectory" in page
    assert "HDB Value band / multiplier" in page
    assert '"Not applicable","Not applicable"' in page
    assert "Estate framework values describe the planning-area context" in page
    assert "without manufacturing a single winner" in page
    assert "let CONTEXTS =" in page
    assert '<script src="assets/data-loader.js"></script>' in page
    assert "hydrateProjectCatalog" in page
    assert "Retry project catalog" in page
    assert "file:// pages" in page
    assert "capabilities.framework_comparison" in page
    assert "revision:PROJECT_CATALOG.revision" in page
    inline_options = page.split('<datalist id="project-options">', 1)[1].split(
        "</datalist>", 1
    )[0]
    assert inline_options.count('<option value="') == 2


def test_inline_json_cannot_terminate_the_script():
    payload = '</script><script>alert("x")</script>\u2028\u2029'

    encoded = comparison.script_safe_json({"value": payload})

    assert "</script>" not in encoded
    assert "<\\/script>" in encoded
    assert "\\u2028" in encoded
    assert "\\u2029" in encoded


def test_committed_page_meets_bootstrap_budget_and_reuses_shared_catalog_url():
    page_path = ROOT / "condo_framework_comparison.html"
    page = page_path.read_text(encoding="utf-8")
    options = page.split('<datalist id="project-options">', 1)[1].split(
        "</datalist>", 1
    )[0]
    catalog_path = re.search(
        r'"path":"(assets/project-catalog/[0-9a-f]{64}/catalog\.json)"',
        page,
    )
    exit_payload = json.loads(
        re.search(
            r'<script id="project-exit-data" type="application/json">(.*?)</script>',
            (ROOT / "project_exit_comparison.html").read_text(encoding="utf-8"),
        ).group(1)
    )

    assert page_path.stat().st_size <= 500 * 1024
    assert options.count("<option ") == 2
    assert catalog_path
    assert catalog_path.group(1) == exit_payload["catalog"]["path"]
