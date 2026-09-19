"""Tests for the Canberra Crescent versus District 27 deep analysis."""

from datetime import date
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

import gen_canberra_crescent_d27_html as canberra  # noqa: E402


def _many_transaction_report(count=250):
    projects = (
        canberra.SUBJECT,
        "THE WATERGARDENS AT CANBERRA",
        "THE COMMODORE",
        "NORTH PARK RESIDENCES",
    )
    project_counts = (125, 50, 40, count - 215)
    rows = []
    index = 0
    for project, project_count in zip(projects, project_counts):
        for _ in range(project_count):
            price = 1_000_000 + index * 1_000
            area_sqm = 50 + index % 3
            sqft = area_sqm * canberra.SQM_TO_SQFT
            rows.append(
                {
                    "project_name": project,
                    "sale_period": pd.Period("2026-06", freq="M"),
                    "type_of_sale": "New Sale" if project == canberra.SUBJECT else "Resale",
                    "price": price,
                    "area_sqm": area_sqm,
                    "sqft": sqft,
                    "psf": price / sqft,
                    "unit_key": "2",
                    "bedrooms": 2,
                    "year": 2026,
                    "size_band_low": int(sqft // 100 * 100),
                    "floor_level": "06 to 10",
                    "bedroom_source": "edgeprop_exact",
                    "tenure": "99 yrs lease commencing from 2024",
                }
            )
            index += 1
    txns = canberra.add_transaction_diagnostics(pd.DataFrame(rows))
    window = {
        "current_start": pd.Period("2025-01", freq="M"),
        "full_end": pd.Period("2026-06", freq="M"),
        "partial": None,
    }
    locations = {
        project: {"lat": 1.44 + offset * 0.001, "lon": 103.829}
        for offset, project in enumerate(projects)
    }
    mrt = pd.DataFrame(
        [
            {
                "lat": 1.4432,
                "lon": 103.8296,
                "name": "Canberra",
                "stn_code": "NS12",
                "operational": 1,
            }
        ]
    )
    project_rows = canberra.build_project_rows(txns, window, locations, {}, mrt)
    matched_rows = canberra.build_matched_rows(txns, window, project_rows)
    subject = canberra.build_subject(txns, window)
    return canberra.render_html(
        txns,
        window,
        project_rows,
        matched_rows,
        subject,
        date(2026, 7, 25),
    )


def _raw(tmp_path):
    rows = []
    for sale_date, price in (("Jun-26", 1_000_000), ("Jun-26", 1_000_000), ("Jul-26", 1_100_000)):
        rows.append(
            {
                "Project Name": "CANBERRA CRESCENT RESIDENCES",
                "Transacted Price ($)": price,
                "Sale Date": sale_date,
                "Street Name": "CANBERRA CRESCENT",
                "Type of Sale": "New Sale",
                "Area (SQM)": 50,
                "Property Type": "Apartment",
                "Tenure": "99 yrs lease commencing from 2024",
                "Postal District": 27,
                "Floor Level": "01 to 05",
            }
        )
    path = tmp_path / "pmi_d27_2021-2026.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _edgeprop(tmp_path):
    rows = []
    for sale_date, price in (("02 Jun 2026", 1_000_000), ("02 Jul 2026", 1_100_000)):
        rows.append(
            {
                "Project": "CANBERRA CRESCENT RESIDENCES",
                "Date of Sale": sale_date,
                "Price ($)": price,
                "Area (sqft)": 538,
                "Area (sqm)": 50,
                "Address": "51 CANBERRA CRESCENT #03-XX",
                "Postal District": "27",
                "Bedrooms": "2",
                "Type": "Apartment",
                "Sale Type": "New Sale",
                "Tenure": "99 yrs from 2024",
            }
        )
    path = tmp_path / "edgeprop.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_official_transaction_multiplicity_is_preserved(tmp_path):
    txns = canberra.load_district_transactions(
        _raw(tmp_path),
        _edgeprop(tmp_path),
    )

    assert len(txns) == 3
    duplicates = txns[
        txns["sale_month"].eq("2026-06")
        & txns["price"].eq(1_000_000)
        & txns["area_sqm"].eq(50)
    ]
    assert len(duplicates) == 2
    assert txns["bedrooms"].astype(int).eq(2).all()
    assert txns["bedroom_source"].eq("edgeprop_exact").all()

    window = canberra.comparison_window(txns, date(2026, 7, 25))
    assert str(window["full_end"]) == "2026-06"
    assert str(window["partial"]) == "2026-07"


def test_transaction_diagnostics_keep_sale_states_and_cohort_breadth_visible():
    rows = [
        {
            "project_name": "LAUNCH",
            "year": 2026,
            "type_of_sale": "New Sale",
            "unit_key": "2",
            "psf": psf,
            "sqft": 700,
            "size_band_low": 700,
            "bedroom_source": "edgeprop_exact",
        }
        for psf in (1_900, 2_000, 2_100)
    ]
    rows.extend(
        [
            {
                "project_name": project,
                "year": 2026,
                "type_of_sale": "Resale",
                "unit_key": "2",
                "psf": psf,
                "sqft": 700,
                "size_band_low": 700,
                "bedroom_source": "edgeprop_exact",
            }
            for project, psf in (("RESALE A", 1_400), ("RESALE B", 1_600))
        ]
    )

    out = canberra.add_transaction_diagnostics(pd.DataFrame(rows))
    launch = out[out["project_name"].eq("LAUNCH")]
    resale = out[out["type_of_sale"].eq("Resale")]

    assert launch["cohort_project_n"].eq(1).all()
    assert launch["analysis"].str.contains("launch-position signal only").all()
    assert resale["cohort_project_n"].eq(2).all()
    assert resale["analysis"].str.contains("2 projects in cohort").all()


def test_canberra_mrt_uses_reviewed_ns12_coordinate_not_bad_legacy_point():
    locations = {
        canberra.SUBJECT: {
            "lat": 1.449921230269529,
            "lon": 103.8293971626456,
        },
        "THE COMMODORE": {
            "lat": 1.441213593738426,
            "lon": 103.8277840489972,
        },
    }
    mrt = pd.DataFrame(
        [
            {
                "lat": 1.44967,
                "lon": 103.82988,
                "name": "Canberra",
                "stn_code": "NS12",
                "operational": 1,
            }
        ]
    )

    subject = canberra.nearest_station(canberra.SUBJECT, locations, mrt)
    commodore = canberra.nearest_station("THE COMMODORE", locations, mrt)

    assert subject["station"] == "Canberra (NS12)"
    assert 740 <= subject["station_distance_m"] <= 755
    assert 290 <= commodore["station_distance_m"] <= 305
    assert commodore["station_distance_m"] < subject["station_distance_m"]


def test_transaction_ledger_uses_bounded_live_rows_and_full_filtered_actions():
    page = _many_transaction_report()

    assert "<tbody id='ledger-body'></tbody>" in page
    assert "id='ledger-row-template'" in page
    assert "id='ledger-show-more'" in page
    assert "id='ledger-export'" in page
    assert "role='status' aria-live='polite'" in page
    assert "filteredLedgerRows.map" in page
    assert 'window.addEventListener("beforeprint"' in page
    assert "The transaction ledger needs JavaScript" in page


def test_transaction_ledger_pages_filters_exports_and_restores_print(tmp_path):
    playwright_api = pytest.importorskip("playwright.sync_api")
    report = tmp_path / "canberra-many.html"
    report.write_text(_many_transaction_report(), encoding="utf-8")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")
        page = browser.new_page()
        try:
            page.goto(report.as_uri())
            assert page.locator("#ledger-body tr").count() == 100
            playwright_api.expect(page.locator("#ledger-count")).to_have_text(
                "100 of 250 filtered transactions shown"
            )

            page.locator("#ledger-show-more").click()
            assert page.locator("#ledger-body tr").count() == 200
            playwright_api.expect(page.locator("#ledger-body tr").nth(100)).to_be_focused()

            page.locator("#ledger-project").select_option(
                canberra.slugify(canberra.SUBJECT)
            )
            assert page.locator("#ledger-body tr").count() == 100
            playwright_api.expect(page.locator("#ledger-count")).to_have_text(
                "100 of 125 filtered transactions shown"
            )
            with page.expect_download() as download_info:
                page.locator("#ledger-export").click()
            exported = download_info.value.path().read_text(encoding="utf-8")
            assert len(exported.splitlines()) == 126
            assert "CANBERRA CRESCENT RESIDENCES" in exported
            assert "THE COMMODORE" not in exported

            page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            assert page.locator("#ledger-body tr").count() == 125
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            assert page.locator("#ledger-body tr").count() == 100
        finally:
            page.close()
            browser.close()
