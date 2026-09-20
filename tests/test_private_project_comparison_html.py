"""Contracts for the generated private-project evidence explorer."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re

import pandas as pd

import gen_private_project_comparison_html as table
from sg_estate.domain.value import CFG as VALUE_CFG


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "private_project_comparison_table.html"
SCRIPT = ROOT / "site" / "assets" / "private-project-comparison.js"
STYLE = ROOT / "site" / "assets" / "private-project-comparison.css"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _embedded(script_id: str) -> object:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        _page(),
        flags=re.DOTALL,
    )
    assert match, f"generated data script {script_id!r} is missing"
    return json.loads(match.group(1))


def _sample_row() -> dict:
    return {
        "project": "TEST CONDO",
        "street": "TEST ROAD",
        "property_type": "Condominium",
        "district": "10",
        "district_key": "d-10",
        "planning_area": "BISHAN",
        "station": "TEST MRT",
        "station_code": "TS1",
        "station_display": "TEST MRT (TS1)",
        "station_key": "test-mrt-ts1",
        "line": "Test Line",
        "line_short": "TS",
        "line_key": "test-line",
        "station_status": "Open",
        "station_distance_m": 100,
        "location_source": "project_geocode",
        "project_lat": 1.0,
        "project_lon": 103.0,
        "school_metrics_source": "project_geocode",
        "geocode_status": "matched",
        "geocode_score": 105,
        "has_primary_1km": True,
        "has_ranked_primary_1km": True,
        "primary_1km_count": 1,
        "primary_1km_schools": "TOP PRIMARY; NEAR PRIMARY",
        "primary_1km_ranked_count": 1,
        "top_primary_1km_count": 1,
        "best_primary_1km_school": "TOP PRIMARY",
        "best_primary_1km_rank": 3,
        "best_primary_1km_distance_m": 450,
        "best_primary_1km_metric": "proxy",
        "secondary_2km_count": 1,
        "best_secondary_2km_school": "TOP SECONDARY",
        "best_secondary_2km_rank": 4,
        "best_secondary_2km_distance_m": 1200,
        "jc_5km_count": 1,
        "best_jc_5km_school": "TOP JC",
        "best_jc_5km_rank": 5,
        "best_jc_5km_distance_m": 3000,
        "n": 1,
        "recent_n": 1,
        "median_psm": 10_000,
        "recent_median_psm": 10_500,
        "district_delta_pct": 1.0,
        "area_delta_pct": 2.0,
        "recent_delta_pct": 5.0,
        "median_price_mil": 1.0,
        "median_area_sqm": 100,
        "first_sale": "2026-01",
        "last_sale": "2026-01",
        "sale_mix": "Resale:1",
        "tenure": "Freehold",
        "market_segment": "Outside Central Region",
        "context_area": "BISHAN",
        "context_basis": "direct",
        "provision_band": "B+",
        "provision_score": 4.1,
        "private_value_band": "B",
        "private_value_score": 3.8,
        "private_value_n": 100,
    }


def test_aggregate_projects_includes_private_school_metrics() -> None:
    private = pd.DataFrame([
        {
            "project_name": "TEST CONDO",
            "street_name": "TEST ROAD",
            "district": "10",
            "planning_area": "BISHAN",
            "unit_price_psm": 10_000,
            "transacted_price": 1_000_000,
            "area_sqm": 100,
            "sale_month_dt": pd.Timestamp("2026-01-01"),
            "sale_type_norm": "Resale",
            "property_type": "Condominium",
            "tenure": "Freehold",
            "market_segment": "Outside Central Region",
        }
    ])
    estates = pd.DataFrame([{"estate": "BISHAN", "lat": 1.0, "lon": 103.0}])
    mrt = pd.DataFrame([
        {
            "name": "TEST MRT",
            "stn_code": "TS1",
            "line": "Test Line",
            "lat": 1.0,
            "lon": 103.01,
            "operational": 1,
        },
        {
            "name": "FUTURE MRT",
            "stn_code": "FS1",
            "line": "Future Line",
            "lat": 1.0,
            "lon": 103.0,
            "operational": 0,
        },
    ])
    master = pd.DataFrame([
        {
            "estate": "BISHAN",
            "provision_band": "B+",
            "provision_score": 4.1,
            "value_private_band": "B",
            "value_private_score": 3.8,
            "value_private_n": 100,
        }
    ]).set_index("estate")
    key = table.project_location_key("TEST CONDO", "TEST ROAD", "10", "BISHAN")
    school_metrics = {
        key: {
            "has_primary_1km": True,
            "has_ranked_primary_1km": True,
            "primary_1km_count": 2,
            "primary_1km_schools": "TOP PRIMARY; NEAR PRIMARY",
            "primary_1km_ranked_count": 1,
            "best_primary_1km_school": "TOP PRIMARY",
            "best_primary_1km_rank": 3,
            "best_primary_1km_distance_m": 450,
            "secondary_2km_count": 1,
            "best_secondary_2km_school": "TOP SECONDARY",
            "best_secondary_2km_rank": 4,
            "jc_5km_count": 1,
            "best_jc_5km_school": "TOP JC",
            "best_jc_5km_rank": 5,
        }
    }

    rows = table.aggregate_projects(private, estates, mrt, master, {}, school_metrics)

    assert len(rows) == 1
    row = rows[0]
    assert row["station"] == "TEST MRT"
    assert row["station_status"] == "Open"
    assert row["has_primary_1km"] is True
    assert row["primary_1km_count"] == 2
    assert row["primary_1km_schools"] == "TOP PRIMARY; NEAR PRIMARY"
    assert row["best_primary_1km_school"] == "TOP PRIMARY"
    assert row["best_primary_1km_rank"] == 3
    assert row["best_secondary_2km_school"] == "TOP SECONDARY"
    assert row["best_jc_5km_school"] == "TOP JC"


def test_band_context_withholds_thin_private_value_decimal() -> None:
    master = pd.DataFrame([
        {
            "estate": "BISHAN",
            "provision_band": "B+",
            "provision_score": 4.1,
            "value_private_band": "B",
            "value_private_score": 3.8,
            "value_private_n": int(VALUE_CFG["trust_decimal_n"]) - 1,
        }
    ]).set_index("estate")

    context = table.band_context(master, "BISHAN")

    assert context["private_value_band"] == "B"
    assert context["private_value_n"] == int(VALUE_CFG["trust_decimal_n"]) - 1
    assert context["private_value_score"] is None


def test_band_context_masks_non_residential_archetype() -> None:
    master = pd.DataFrame([
        {
            "estate": "CENTRAL AREA",
            "archetype": "X",
            "provision_band": "N/R",
            "provision_score": 4.26,
            "value_private_band": "N/R",
            "value_private_score": 4.0,
            "value_private_n": 1_000,
        }
    ]).set_index("estate")

    context = table.band_context(master, "CENTRAL AREA")

    assert context["context_status"] == "not_residential"
    assert context["archetype"] == "X"
    for key in (
        "provision_band",
        "provision_score",
        "private_value_band",
        "private_value_score",
        "private_value_n",
    ):
        assert context[key] is None


def test_rendered_explorer_uses_shared_shell_and_progressive_views() -> None:
    html = table.render_html([_sample_row()], "2026-01")

    assert html.count("assets/research-shell.css") == 1
    assert html.count("assets/research-shell.js") == 1
    assert html.count("assets/estate-explorer.css") == 1
    assert html.count("assets/private-project-comparison.css") == 1
    assert html.count("assets/private-project-comparison.js") == 1
    assert '<main id="research-content">' in html
    assert 'id="private-project-comparison-data" type="application/json"' in html
    assert 'id="private-project-comparison-config" type="application/json"' in html
    assert 'id="project-search" type="search"' in html
    assert 'role="status" aria-live="polite"' in html
    for view in (
        "overview",
        "access",
        "schools",
        "price",
        "transactions",
        "context",
    ):
        assert f'data-view="{view}"' in html
    assert 'data-view="overview" aria-pressed="true"' in html
    assert 'id="reset-view" type="button"' in html
    assert 'id="show-more" type="button"' in html
    assert 'id="private-project-table"' in html
    assert 'id="private-project-table-head"' in html
    assert 'id="private-project-table-body"' in html
    assert 'class="tbl-wrap" id="table-wrap" role="region"' in html
    assert "<caption>" in html
    assert "universal project ranking" in html.lower()
    assert "mix-sensitive" in html.lower()
    assert "not appreciation" in html.lower() or "not an appreciation" in html.lower()
    assert "onclick=" not in html
    assert "oninput=" not in html
    assert "onchange=" not in html


def test_rendered_explorer_exposes_single_value_filters_and_reset_states() -> None:
    html = table.render_html([_sample_row()], "2026-01")

    for filter_id in (
        "district-filter",
        "station-filter",
        "sale-filter",
        "source-filter",
        "primary-filter",
    ):
        assert f'id="{filter_id}"' in html
    assert '<option value="project_geocode">' in html
    assert '<option value="centroid_proxy">' in html
    assert '<option value="has">' in html
    assert '<option value="ranked">' in html
    assert '<option value="none">' in html
    assert '<option value="missing">' in html
    assert 'id="empty-state"' in html
    assert re.search(r'<button\b(?=[^>]*\bid="empty-reset")(?=[^>]*\btype="button")', html)
    assert 'id="visible-count"' in html
    assert 'id="rendered-copy"' in html
    assert " multiple" not in html


def test_committed_artifact_preserves_current_project_evidence_anchors() -> None:
    rows = _embedded("private-project-comparison-data")
    config = _embedded("private-project-comparison-config")

    assert isinstance(rows, list)
    assert isinstance(config, dict)
    counts = config["counts"]
    assert len(rows) == counts["projects"] == 2_413
    assert sum(row["n"] for row in rows) == counts["transactions"] == 110_781
    assert len({row["district"] for row in rows}) == counts["districts"] == 28
    assert len({row["station_key"] for row in rows}) == counts["stations"]
    assert (
        sum(row["location_source"] == "project_geocode" for row in rows)
        == counts["project_geocodes"]
        == 2_413
    )
    assert (
        sum(row["location_source"] == "centroid_proxy" for row in rows)
        == counts["centroid_fallbacks"]
        == 0
    )
    assert (
        sum(row["school_metrics_source"] == "project_geocode" for row in rows)
        == counts["school_metrics"]
    )
    assert max(row["last_sale"] for row in rows) == config["latest_month"]
    assert config["page_size"] == 100
    assert config["recent_window_months"] == 12
    assert config["value_trust_threshold"] == int(VALUE_CFG["trust_decimal_n"])

    projects = {row["project"] for row in rows}
    assert {
        "THE POIZ RESIDENCES",
        "PARK PLACE RESIDENCES AT PLQ",
        "THE LAKEGARDEN RESIDENCES",
        "CANBERRA CRESCENT RESIDENCES",
    } <= projects
    assert all(row["station_status"] == "Open" for row in rows)
    assert all(row["location_source"] in {"project_geocode", "centroid_proxy"} for row in rows)
    non_residential = [row for row in rows if row["context_status"] == "not_residential"]
    assert non_residential
    assert all(row["archetype"] == "X" for row in non_residential)
    assert all(
        row[key] is None
        for row in non_residential
        for key in (
            "provision_band",
            "provision_score",
            "private_value_band",
            "private_value_score",
            "private_value_n",
        )
    )


def test_committed_artifact_matches_the_template_renderer() -> None:
    rows = _embedded("private-project-comparison-data")
    config = _embedded("private-project-comparison-config")
    generated_on = date.fromisoformat(config["generated_on"])

    assert table.render_html(
        rows,
        config["latest_month"],
        generated_on=generated_on,
    ) == _page()


def test_committed_artifact_matches_fresh_committed_inputs(tmp_path: Path) -> None:
    config = _embedded("private-project-comparison-config")
    output = tmp_path / PAGE.name

    generated, count = table.generate(
        ROOT / "data/inputs/ura_private.csv",
        table.DEFAULT_LOCATION_PATH,
        table.DEFAULT_SCHOOL_METRICS_PATH,
        output,
        generated_on=date.fromisoformat(config["generated_on"]),
    )

    assert count == config["counts"]["projects"]
    assert generated.read_text(encoding="utf-8") == _page()


def test_browser_asset_implements_accessible_url_backed_batched_table() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "URLSearchParams" in script
    assert "history.replaceState" in script
    assert "popstate" in script
    assert "aria-sort" in script
    assert "aria-pressed" in script
    assert "escapeHTML" in script
    assert "function finiteNumber" in script
    assert "not a multiplier" in script
    assert "toFixed(2)}×" not in script
    assert "page_size" in script or "pageSize" in script
    assert 'getElementById("show-more")' in script or "getElementById('show-more')" in script
    assert STYLE.is_file()
