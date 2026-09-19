"""Tests for the Katong condominium comparison explorer."""

from datetime import date
import os
import sys

import pandas as pd
from sg_estate.project_locations import LEGACY_LOCATION_COLUMNS
import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"),
)

import gen_katong_comparison_html as katong  # noqa: E402


PROJECTS = ("EMERALD OF KATONG", "HAIG COURT")


def _profiles(tmp_path):
    path = tmp_path / "profiles.csv"
    rows = []
    for index, project in enumerate(PROJECTS):
        rows.append(
            {
                "name": project,
                "url": f"https://example.com/{index}",
                "slug": project.lower().replace(" ", "-"),
                "cohort": "Current launches" if index == 0 else "Completed controls",
                "role": "Subject benchmark" if index == 0 else "Freehold control",
                "official_units": 100 + index * 100,
                "completion_label": "Expected 2028" if index == 0 else "Completed 2004",
                "tenure_profile": "99-year leasehold" if index == 0 else "Freehold",
                "micro_market": "Jalan Tembusu" if index == 0 else "Haig Road",
                "official_source_url": f"https://example.com/source/{index}",
                "why_compare": "Synthetic comparison rationale",
                "best_fit": "Synthetic buyer fit",
                "key_risk": "Synthetic comparison risk",
                "future_context": "Synthetic future context",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _transactions(tmp_path):
    rows = []
    for month, price in (
        ("2024-08", 1_000_000),
        ("2025-01", 1_000_000),
        ("2025-06", 1_000_000),
        ("2025-08", 1_100_000),
        ("2026-01", 1_100_000),
        ("2026-06", 1_100_000),
        ("2026-07", 9_000_000),
    ):
        rows.append(
            {
                "project_name": "EMERALD OF KATONG",
                "postal_district": "15",
                "planning_area": "MARINE PARADE",
                "property_type": "Apartment",
                "tenure": "99 years",
                "sale_month": month,
                "type_of_sale": "Resale",
                "transacted_price": price,
                "area_sqm": 50,
                "floor_level": "06 to 10",
                "data_source": "ura_private",
                "bedrooms": 2,
                "bedroom_source": "edgeprop_exact",
            }
        )
    rows.extend(
        [
            {
                **rows[-2],
                "project_name": "HAIG COURT",
                "sale_month": "2026-05",
                "transacted_price": 2_000_000,
                "area_sqm": 100,
                "floor_level": "01 to 05",
            },
            {
                **rows[-2],
                "sale_month": "2026-06",
                "type_of_sale": "New Sale",
                "transacted_price": 1_200_000,
            },
            {
                **rows[-2],
                "sale_month": "2026-06",
                "property_type": "Executive Condominium",
                "transacted_price": 99_000_000,
            },
        ]
    )
    path = tmp_path / "transactions.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _many_transactions(tmp_path, count=250):
    rows = []
    for index in range(count):
        project = PROJECTS[index % len(PROJECTS)]
        rows.append(
            {
                "project_name": project,
                "postal_district": "15",
                "planning_area": "MARINE PARADE",
                "property_type": "Apartment",
                "tenure": "Freehold" if project == "HAIG COURT" else "99 years",
                "sale_month": "2026-06" if index % 3 else "2026-05",
                "type_of_sale": "Resale",
                "transacted_price": 1_000_000 + index * 1_000,
                "area_sqm": 50 + index % 3,
                "floor_level": "06 to 10",
                "data_source": "ura_private",
                "bedrooms": 2,
                "bedroom_source": "edgeprop_exact",
            }
        )
    path = tmp_path / "many-transactions.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _spatial_files(tmp_path):
    locations = tmp_path / "locations.csv"
    schools = tmp_path / "schools.csv"
    mrt = tmp_path / "mrt.csv"
    pd.DataFrame(
        [
            {
                "project_name": project,
                "lat": 1.30 + index * 0.01,
                "lon": 103.89,
                "match_status": "matched",
                "review_status": "approved_legacy",
            }
            for index, project in enumerate(PROJECTS)
        ]
    ).reindex(columns=LEGACY_LOCATION_COLUMNS).to_csv(locations, index=False)
    pd.DataFrame(
        [
            {
                "project_name": project,
                "primary_1km_count": index + 1,
                "primary_1km_schools": "TEST PRIMARY",
            }
            for index, project in enumerate(PROJECTS)
        ]
    ).to_csv(schools, index=False)
    pd.DataFrame(
        [
            {
                "name": "TEST MRT",
                "stn_code": "TE99",
                "line": "TEL",
                "lat": 1.301,
                "lon": 103.89,
                "operational": True,
            }
        ]
    ).to_csv(mrt, index=False)
    return locations, schools, mrt


def _units(tmp_path):
    path = tmp_path / "units.csv"
    common = {
        "Project": "EMERALD OF KATONG",
        "Address": "1 TEST ROAD",
        "unit_floor": "06",
        "unit_stack": "15",
        "unit_number_source": "edgeprop_address",
        "Bedrooms": 2,
        "Sale Type": "Resale",
        "Area (sqft)": 538,
        "source_url": "https://example.com/unit-source",
    }
    pd.DataFrame(
        [
            {
                **common,
                "Date of Sale": "01 Jan 2024",
                "unit_number": "#06-15",
                "unit_number_status": "exact",
                "Unit Price ($psf)": 1800,
                "Price ($)": 968_400,
            },
            {
                **common,
                "Date of Sale": "01 Jan 2026",
                "unit_number": "#06-15",
                "unit_number_status": "exact",
                "Unit Price ($psf)": 1980,
                "Price ($)": 1_065_240,
            },
            {
                **common,
                "Date of Sale": "01 Feb 2026",
                "Address": "1 TEST ROAD #08-XX",
                "unit_number": "",
                "unit_floor": "",
                "unit_stack": "",
                "unit_number_status": "masked",
                "Unit Price ($psf)": 2000,
                "Price ($)": 1_076_000,
            },
        ]
    ).to_csv(path, index=False)
    return path


def test_complete_months_sale_states_and_growth_threshold(tmp_path):
    profiles = katong.load_profiles(_profiles(tmp_path))
    txns = katong.load_transactions(_transactions(tmp_path), set(profiles["project"]))
    periods = katong.analysis_periods(txns, date(2026, 7, 25))

    assert periods["full_end"] == pd.Period("2026-06", freq="M")
    assert periods["partial"] == pd.Period("2026-07", freq="M")
    assert not txns["property_type"].str.contains("Executive Condominium").any()

    emerald = txns[txns["project"].eq("EMERALD OF KATONG")]
    growth = katong.growth_stats(emerald, "resale", "2", periods)
    assert growth["prior_n"] == 3
    assert growth["recent_n"] == 3
    assert growth["growth_pct"] == pytest.approx(10.0)

    thin = katong.growth_stats(emerald.iloc[:2], "resale", "2", periods)
    assert thin["growth_pct"] is None


def test_unit_loader_never_promotes_masked_rows(tmp_path):
    units = katong.load_unit_transactions(_units(tmp_path), set(PROJECTS))

    assert len(units) == 3
    assert units["is_exact"].sum() == 2
    assert not units.loc[units["unit_number_status"].eq("masked"), "is_exact"].any()

    section = katong._unit_section(  # noqa: SLF001
        units,
        [
            {"name": project, "project": project}
            for project in PROJECTS
        ],
    )
    assert "#06-15" in section
    assert "Verified repeat sales" in section
    assert "#08-XX" not in section


def test_generate_builds_filters_ledger_and_honest_unit_empty_state(tmp_path):
    locations, schools, mrt = _spatial_files(tmp_path)
    out = tmp_path / "katong.html"
    missing_units = tmp_path / "no-unit-file.csv"
    out_path, rows, periods = katong.generate(
        _profiles(tmp_path),
        _transactions(tmp_path),
        locations,
        schools,
        mrt,
        missing_units,
        out,
        as_of=date(2026, 7, 25),
    )

    page = out_path.read_text(encoding="utf-8")
    assert len(rows) == 2
    assert periods["headline_start"] == pd.Period("2025-01", freq="M")
    assert "Like-for-like achieved prices" in page
    assert 'id="sale-state"' in page
    assert 'id="bedroom"' in page
    assert 'id="ledger-table"' in page
    assert '<tbody id="ledger-body"></tbody>' in page
    assert 'id="ledger-row-template"' in page
    assert 'id="ledger-show-more"' in page
    assert 'role="status" aria-live="polite"' in page
    assert "filteredLedgerRows.map" in page
    assert 'window.addEventListener("beforeprint"' in page
    assert "Exact-unit file not supplied" in page
    assert "unified project ranking" not in page
    assert "No asking prices, rental yields or estate-level Provision scores" in page


def test_transaction_ledger_pages_filters_exports_and_restores_print(tmp_path):
    playwright_api = pytest.importorskip("playwright.sync_api")
    locations, schools, mrt = _spatial_files(tmp_path)
    out = tmp_path / "katong-many.html"
    katong.generate(
        _profiles(tmp_path),
        _many_transactions(tmp_path),
        locations,
        schools,
        mrt,
        tmp_path / "no-unit-file.csv",
        out,
        as_of=date(2026, 7, 25),
    )

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")
        page = browser.new_page()
        try:
            page.goto(out.as_uri())
            assert page.locator("#ledger-body tr").count() == 100
            playwright_api.expect(page.locator("#ledger-count")).to_have_text(
                "100 of 250 filtered transactions shown"
            )

            page.locator("#ledger-show-more").click()
            assert page.locator("#ledger-body tr").count() == 200
            playwright_api.expect(page.locator("#ledger-body tr").nth(100)).to_be_focused()

            page.locator("#ledger-search").fill("HAIG COURT")
            assert page.locator("#ledger-body tr").count() == 100
            playwright_api.expect(page.locator("#ledger-count")).to_have_text(
                "100 of 125 filtered transactions shown"
            )
            with page.expect_download() as download_info:
                page.locator("#export-ledger").click()
            exported = download_info.value.path().read_text(encoding="utf-8")
            assert len(exported.splitlines()) == 126
            assert "Haig Court" in exported
            assert "Emerald Of Katong" not in exported

            page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            assert page.locator("#ledger-body tr").count() == 125
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            assert page.locator("#ledger-body tr").count() == 100
        finally:
            page.close()
            browser.close()
