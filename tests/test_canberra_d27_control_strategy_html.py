"""Tests for the Canberra comparison-control workbooks."""

import os
import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(ROOT, "models"))

import gen_canberra_crescent_d27_html as core  # noqa: E402
import gen_canberra_d27_control_strategy_html as strategies  # noqa: E402


def _cell_rows(project: str, n: int, psf: float) -> list[dict]:
    return [
        {
            "project_name": project,
            "unit_key": "2",
            "size_band_low": 700,
            "type_of_sale": "New Sale" if project == core.SUBJECT else "Resale",
            "price": psf * 750,
            "psf": psf,
            "sqft": 750,
        }
        for _ in range(n)
    ]


def test_strict_unit_matching_requires_three_rows_on_both_sides():
    rows = _cell_rows(core.SUBJECT, 3, 2_000)
    rows += _cell_rows("THE WATERGARDENS AT CANBERRA", 3, 1_700)
    rows += _cell_rows("THE COMMODORE", 2, 1_750)

    matched = strategies.unit_matching_rows(pd.DataFrame(rows))

    assert len(matched) == 1
    assert matched[0]["peer"] == "THE WATERGARDENS AT CANBERRA"
    assert matched[0]["delta_psf"] == pytest.approx(-15.0)


def test_generated_strategy_pages_are_responsive_and_keep_controls_visible():
    expected = {
        "canberra_strategy_4_unit_matching.html": (
            "Match the home before comparing the price",
            "Strict bedroom-and-size matches",
        ),
        "canberra_strategy_5_sale_state.html": (
            "Keep launch, sub-sale and resale evidence apart",
            "Three different price-forming processes",
        ),
        "canberra_strategy_6_planning_context.html": (
            "Treat future plans as context, not booked returns",
            "An evidence ladder, not an uplift score",
        ),
    }
    for filename, phrases in expected.items():
        content = (ROOT / filename).read_text(encoding="utf-8")
        assert 'name="viewport"' in content
        assert "overflow-x:auto" in content
        assert "@media (max-width:600px)" in content
        for phrase in phrases:
            assert phrase in content


def test_planning_register_uses_primary_sources_and_no_uplift_treatment():
    rendered = " ".join(" ".join(row) for row in strategies.planning_rows())

    assert "lta.gov.sg" in rendered
    assert "ura.gov.sg" in rendered
    assert "No price uplift" in rendered
    assert "already available" in rendered.lower()
