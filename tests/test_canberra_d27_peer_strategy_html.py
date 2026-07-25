"""Focused tests for the three Canberra / District 27 strategy pages."""

from datetime import date
import os
import sys

import pandas as pd

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
    ),
)

import gen_canberra_d27_peer_strategy_html as strategy  # noqa: E402


def _transactions():
    projects = strategy.INTEGRATION_PROJECTS
    rows = []
    for index, project in enumerate(projects):
        tenure_start = {
            strategy.SUBJECT: 2024,
            "THE WATERGARDENS AT CANBERRA": 2020,
            "THE COMMODORE": 2020,
            "CANBERRA RESIDENCES": 2010,
        }.get(project, 2015)
        state = "New Sale" if project == strategy.SUBJECT else "Resale"
        for month, bedrooms in (
            ("2025-01", 1),
            ("2025-08", 1),
            ("2025-12", 2),
            ("2026-02", 2),
            ("2026-06", 3),
            ("2026-07", 4),
        ):
            if project == strategy.SUBJECT and month == "2025-01":
                continue
            price = 1_000_000 + index * 50_000 + bedrooms * 25_000
            area_sqm = 40 + bedrooms * 15
            rows.append(
                {
                    "project_name": project,
                    "sale_period": pd.Period(month, freq="M"),
                    "price": price,
                    "area_sqm": area_sqm,
                    "sqft": area_sqm * 10.7639,
                    "psf": price / (area_sqm * 10.7639),
                    "bedrooms": bedrooms,
                    "unit_key": str(bedrooms),
                    "type_of_sale": state,
                    "tenure": f"99 yrs lease commencing from {tenure_start}",
                }
            )
    return pd.DataFrame(rows)


def _spatial(tmp_path):
    locations = tmp_path / "locations.csv"
    pd.DataFrame(
        [
            {
                "project_name": project,
                "lat": 1.40 + index * 0.0001,
                "lon": 103.82,
            }
            for index, project in enumerate(strategy.INTEGRATION_PROJECTS)
        ]
    ).to_csv(locations, index=False)
    mrt = tmp_path / "mrt.csv"
    pd.DataFrame(
        [
            {
                "name": "TEST STATION",
                "stn_code": "NS99",
                "line": "North South Line",
                "lat": 1.40,
                "lon": 103.82,
                "operational": 1,
            },
            {
                "name": "FUTURE STATION",
                "stn_code": "NS98",
                "line": "North South Line",
                "lat": 1.4001,
                "lon": 103.82,
                "operational": 0,
            },
        ]
    ).to_csv(mrt, index=False)
    return locations, mrt


def test_strategy_windows_are_subject_active_and_exclude_partial_month():
    windows = strategy.strategy_windows(_transactions(), date(2026, 7, 25))

    assert str(windows["current_start"]) == "2025-01"
    assert str(windows["matched_start"]) == "2025-08"
    assert str(windows["full_end"]) == "2026-06"
    assert str(windows["partial"]) == "2026-07"


def test_pages_keep_sale_state_time_mix_and_framework_boundaries(tmp_path):
    locations, mrt = _spatial(tmp_path)
    outputs = (
        tmp_path / "micro.html",
        tmp_path / "newness.html",
        tmp_path / "integration.html",
    )
    result = strategy.generate_from_transactions(
        _transactions(),
        locations,
        mrt,
        outputs,
        as_of=date(2026, 7, 25),
    )

    assert all(path.exists() for path in outputs)
    assert result["micro_rows"][0]["stats"]["all"]["n"] == 4
    assert result["micro_rows"][0]["states"] == "New Sale 4"
    assert result["vintage_rows"][0]["lease_start"] == 2024

    micro = outputs[0].read_text(encoding="utf-8")
    assert "Compare Canberra with Canberra" in micro
    assert "2025-08–2026-06" in micro
    assert "complete-month window" in micro
    assert "New Sale evidence" in micro
    assert "No unified condominium ranking" in micro

    newness = outputs[1].read_text(encoding="utf-8")
    assert "Separate age from price" in newness
    assert "Not appreciation" in newness
    assert "H2 2025 and H1 2026" in newness
    assert "unit growth rates" in newness

    integration = outputs[2].read_text(encoding="utf-8")
    assert "Price convenience in layers" in integration
    assert "North Park" in integration
    assert "retail-at-project" in integration
    assert "straight-line" in integration
    assert "No unified condominium ranking" in integration
