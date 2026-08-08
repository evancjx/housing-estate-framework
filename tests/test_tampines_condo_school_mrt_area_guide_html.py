"""Tests for the dated Tampines condo, school and MRT area guide."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))

import gen_tampines_condo_school_mrt_area_guide_html as guide  # noqa: E402


def test_inventory_is_boundary_controlled_and_classifications_reconcile():
    projects = [row[0] for row in guide.PROJECTS]
    school_statuses = [row[1] for row in guide.PROJECTS]
    mrt_statuses = [row[3] for row in guide.PROJECTS]

    assert len(projects) == 34
    assert len(projects) == len(set(projects))
    assert "ParkTown Residence" in projects
    assert "Pinery Residences" in projects
    assert "Tropicana Condominium" in projects
    assert "Pasir Ris 8" not in projects
    assert school_statuses.count("yes") == 30
    assert school_statuses.count("borderline") == 1
    assert school_statuses.count("no") == 3
    assert mrt_statuses.count("yes") == 6
    assert mrt_statuses.count("borderline") == 4
    assert mrt_statuses.count("future") == 3
    assert mrt_statuses.count("no") == 21


def test_render_page_is_deterministic_semantic_and_source_visible():
    page = guide.render_page()

    assert guide.render_page() == page
    assert page.count("<h1>") == 1
    assert page.count("<tr") == 35
    assert 'class="table-wrap"' in page
    assert 'id="school-filter"' in page
    assert 'id="mrt-filter"' in page
    assert 'data-school="yes"' in page
    assert 'data-mrt="future"' in page
    assert "Showing 34 of 34 projects" in page
    assert "URA Master Plan 2019 subzone boundary dataset" in page
    assert "MOE Home-School Distance methodology" in page
    assert "LTA CRL1 and Tampines North timing" in page
    assert "2026-08-08 02:15:00 SGT (UTC+08:00)" in page
    assert "Pasir Ris 8" not in page


def test_generate_writes_the_rendered_page(tmp_path):
    output = guide.generate(tmp_path / "guide.html")

    assert output.read_text(encoding="utf-8") == guide.render_page()
