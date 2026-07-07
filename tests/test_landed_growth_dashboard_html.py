import pandas as pd

import gen_landed_growth_dashboard_html as dashboard


def _raw_row(year, psf, project="TEST ESTATE", district=10, area="BUKIT TIMAH", sale_type="Resale"):
    return {
        "Project": project,
        "planning_area": area,
        "Postal District": district,
        "Date of Sale": f"1 Jun {year}",
        "Unit Price ($psf)": psf,
        "Price ($)": psf * 3000,
        "Area (sqft)": 3000,
        "Type": "Terrace House",
        "Tenure": "Freehold",
        "Sale Type": sale_type,
        "source_quality": "not_clean",
        "source_url": "https://www.edgeprop.sg/landed-house/test-estate",
    }


def test_prepare_dashboard_payload_builds_projection_rows(tmp_path):
    rows = []
    for year in range(2019, 2027):
        for idx in range(5):
            rows.append(_raw_row(year, int(1000 * (1.05 ** (year - 2019))) + idx))
    path = tmp_path / "landed.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    data = dashboard.load_landed_transactions(path)
    payload, metadata = dashboard.prepare_dashboard_payload(data, generated_on=pd.Timestamp("2026-07-05").date())

    district = next(row for row in payload if row["level"] == "district" and row["district"] == "10")
    project = next(row for row in payload if row["level"] == "project" and row["label"] == "TEST ESTATE")

    assert metadata["source_quality"] == "not_clean"
    assert metadata["trend_end_year"] == 2025
    assert district["projection_years"][0]["year"] == 2027
    assert district["projection_rate_pct"] > 0
    assert project["confidence"] == "High"
    assert any("freehold" in reason.lower() for reason in project["why"])


def test_render_html_contains_dashboard_controls():
    rows = [
        {
            "level": "district",
            "key": "D10",
            "label": "D10",
            "district": "10",
            "planning_area": "BUKIT TIMAH",
            "project": "",
            "total_n": 20,
            "recent_n": 3,
            "active_years": 5,
            "baseline_year": 2019,
            "baseline_psf": 1000,
            "recent_psf": 1300,
            "recent_growth_pct": 30.0,
            "projection_rate_pct": 4.0,
            "projection_source": "district trend",
            "projection_years": [{"year": 2027, "psf": 1352}, {"year": 2029, "psf": 1463}, {"year": 2031, "psf": 1581}],
            "confidence": "High",
            "trend_delta_pp": 1.0,
            "first_sale": "2019-01-01",
            "last_sale": "2026-01-01",
            "main_type": "Terrace House",
            "main_tenure": "Freehold",
            "annual": [{"year": 2019, "median_psf": 1000, "n": 5}, {"year": 2025, "median_psf": 1250, "n": 5}],
            "why": ["Mostly freehold transactions; scarcity can support stronger land psf."],
        }
    ]
    metadata = {
        "generated_on": "2026-07-05",
        "source_quality": "not_clean",
        "trend_start_year": 2019,
        "trend_end_year": 2025,
        "partial_year_note": "2026 is partial and excluded from the annual trend fit.",
        "row_count_2019_plus": 20,
        "project_count": 1,
        "district_count": 1,
        "market_recent_psf": 1300,
        "market_projection_rate_pct": 4.0,
        "projection_years": [2027, 2029, 2031],
    }

    html = dashboard.render_html(rows, metadata)

    assert "Singapore Landed PSF Growth Dashboard" in html
    assert 'id="projectMode"' in html
    assert 'id="topMovers"' in html
    assert "Mostly freehold transactions" in html
    assert "const DATA =" in html
    assert '""": "&quot;"' not in html
