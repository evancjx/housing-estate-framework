"""Tests for the Poiz/East unit-type growth and transaction ledger."""

from datetime import date
import json
import os
import re
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

import gen_poiz_east_unit_growth_html as unit_growth  # noqa: E402


def _profiles(tmp_path):
    path = tmp_path / "profiles.csv"
    pd.DataFrame(
        [
            {
                "name": "THE POIZ RESIDENCES",
                "url": "https://example.com/transactions",
                "slug": "the-poiz-residences",
                "region": "Benchmark",
                "role": "Benchmark",
                "official_units": 731,
                "official_source_url": "https://example.com/official",
            }
        ]
    ).to_csv(path, index=False)
    return path


def _transactions(tmp_path):
    rows = []
    windows = (
        (1, 50, 1_000_000, 1_100_000),
        (2, 70, 1_400_000, 1_680_000),
    )
    prior_months = ("2024-08", "2025-01", "2025-06")
    recent_months = ("2025-08", "2026-01", "2026-06")
    for bedrooms, area_sqm, prior_price, recent_price in windows:
        for month in prior_months:
            rows.append(
                {
                    "project_name": "THE POIZ RESIDENCES",
                    "property_type": "Apartment",
                    "tenure": "99 yrs lease commencing from 2014",
                    "sale_month": month,
                    "type_of_sale": "Resale",
                    "transacted_price": prior_price,
                    "area_sqm": area_sqm,
                    "floor_level": "06 to 10",
                    "data_source": "ura_private",
                    "bedrooms": bedrooms,
                    "bedroom_source": "edgeprop_exact",
                }
            )
        for month in recent_months:
            rows.append(
                {
                    **rows[-1],
                    "sale_month": month,
                    "transacted_price": recent_price,
                }
            )
    rows.append(
        {
            **rows[-1],
            "sale_month": "2026-07",
            "transacted_price": 9_000_000,
        }
    )
    rows.append(
        {
            **rows[-1],
            "sale_month": "2026-06",
            "type_of_sale": "New Sale",
            "transacted_price": 10_000_000,
        }
    )
    path = tmp_path / "transactions.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_growth_uses_two_complete_12_month_windows(tmp_path):
    profiles = unit_growth.load_profiles(_profiles(tmp_path))
    txns = unit_growth.load_transactions(
        _transactions(tmp_path),
        {"THE POIZ RESIDENCES"},
    )
    projects, periods = unit_growth.build_projects(
        profiles,
        txns,
        date(2026, 7, 25),
    )

    assert periods == {
        "prior_start": "2024-07",
        "prior_end": "2025-06",
        "recent_start": "2025-07",
        "full_end": "2026-06",
        "partial": "2026-07",
    }
    project = projects[0]
    assert project["complete_n"] == 12
    assert project["partial_n"] == 1
    assert project["stats"]["1"]["recent_n"] == 3
    assert project["stats"]["1"]["prior_n"] == 3
    assert project["stats"]["1"]["psf_growth_pct"] == pytest.approx(10.0)
    assert project["stats"]["2"]["price_growth_pct"] == pytest.approx(20.0)


def test_generate_lists_every_resale_record_and_unit_limit(tmp_path):
    out = tmp_path / "unit-growth.html"
    out_path, projects, _ = unit_growth.generate(
        _profiles(tmp_path),
        _transactions(tmp_path),
        out,
        as_of=date(2026, 7, 25),
    )

    assert out_path == out
    assert len(projects[0]["transactions"]) == 13
    text = out.read_text(encoding="utf-8")
    assert "exact apartment numbers are not published" in text
    assert "Growth by bedroom / unit type" in text
    assert "Every available resale transaction" in text
    assert "2026-07" in text
    assert "partial month" in text
    assert "1 bedroom · 538 sqft" in text
    assert "2 bedrooms · 753 sqft" in text
    assert "filterLedger" in text
    assert "LEDGER_PAGE_SIZE = 100" in text
    assert "Download filtered CSV" in text
    assert "Show 100 more" in text
    assert 'role=\'status\' aria-live=\'polite\'' in text
    assert "beforeprint" in text
    assert re.search(r"<tbody></tbody>.*transaction-data", text, re.DOTALL)


def test_transaction_ledger_batches_filters_exports_and_restores_print(tmp_path):
    playwright_api = pytest.importorskip("playwright.sync_api")
    profiles_path = _profiles(tmp_path)
    base_rows = pd.read_csv(_transactions(tmp_path)).to_dict("records")
    seed = base_rows[0]
    rows = []
    for index in range(250):
        rows.append(
            {
                **seed,
                "sale_month": "2026-06" if index < 240 else "2025-06",
                "transacted_price": 1_000_000 + index * 1_000,
                "bedrooms": 1 if index < 125 else 2,
                "floor_level": "06 to 10" if index % 2 else "11 to 15",
            }
        )
    transactions_path = tmp_path / "many-transactions.csv"
    pd.DataFrame(rows).to_csv(transactions_path, index=False)
    out = tmp_path / "unit-growth-many.html"
    unit_growth.generate(
        profiles_path,
        transactions_path,
        out,
        as_of=date(2026, 7, 25),
    )

    source = out.read_text(encoding="utf-8")
    payload_match = re.search(
        r"<script type='application/json' class='transaction-data'>(.*?)</script>",
        source,
        re.DOTALL,
    )
    assert payload_match
    assert len(json.loads(payload_match.group(1))) == 250
    assert "<tbody></tbody>" in source

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")
        page = browser.new_page()
        try:
            page.goto(out.as_uri())
            rows_locator = page.locator(".project-panel.active .transaction-table tbody tr")
            assert rows_locator.count() == 100
            playwright_api.expect(
                page.locator(".project-panel.active .visible-count")
            ).to_have_text("100 of 250 filtered records shown")

            page.locator(".project-panel.active .show-more").click()
            assert rows_locator.count() == 200
            playwright_api.expect(rows_locator.nth(100)).to_be_focused()

            page.locator(".project-panel.active .txn-unit").select_option("2")
            assert rows_locator.count() == 100
            playwright_api.expect(
                page.locator(".project-panel.active .visible-count")
            ).to_have_text("100 of 125 filtered records shown")

            with page.expect_download() as download_info:
                page.locator(".project-panel.active .download-ledger").click()
            exported = download_info.value.path().read_text(encoding="utf-8")
            assert len(exported.splitlines()) == 126

            page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            assert rows_locator.count() == 125
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            assert rows_locator.count() == 100
        finally:
            page.close()
            browser.close()
