"""Tests for the curated Poiz-versus-East resale comparison."""

from datetime import date
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

import gen_poiz_east_resale_comparison_html as comparison  # noqa: E402


def _profiles(tmp_path):
    rows = []
    for name, region, role, units in (
        ("THE POIZ RESIDENCES", "Benchmark", "Benchmark", 100),
        ("PARK PLACE RESIDENCES AT PLQ", "Katong / Eunos", "Primary integrated match", 200),
        ("BEDOK RESIDENCES", "Bedok / Tampines", "Primary integrated match", 150),
    ):
        rows.append(
            {
                "name": name,
                "url": f"https://example.com/{name.lower().replace(' ', '-')}",
                "slug": name.lower().replace(" ", "-"),
                "region": region,
                "role": role,
                "official_units": units,
                "completion_year": 2019,
                "tenure_profile": "99-year lease from 2014",
                "integration": "Integrated with MRT",
                "official_source_url": "https://example.com/official",
                "why_compare": "Like-for-like integration control",
                "best_fit": "Synthetic buyer fit",
                "key_risk": "Synthetic fixture risk",
                "future_context": "Synthetic future context",
            }
        )
    path = tmp_path / "profiles.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _transactions(tmp_path):
    rows = []
    projects = (
        ("THE POIZ RESIDENCES", 1_000_000),
        ("PARK PLACE RESIDENCES AT PLQ", 1_200_000),
        ("BEDOK RESIDENCES", 900_000),
    )
    for project, base in projects:
        for month, price in (
            ("2025-08", base),
            ("2026-01", base + 100_000),
            ("2026-06", base + 200_000),
            ("2026-07", base + 3_000_000),
        ):
            rows.append(
                {
                    "project_name": project,
                    "postal_district": "13",
                    "planning_area": "AREA",
                    "property_type": "Apartment",
                    "tenure": "99 yrs lease commencing from 2014",
                    "sale_month": month,
                    "type_of_sale": "Resale",
                    "transacted_price": price,
                    "area_sqm": 50,
                    "data_source": "ura_private",
                    "bedrooms": 1,
                    "bedroom_source": "edgeprop_exact",
                }
            )
        rows.append(
            {
                **rows[-1],
                "project_name": project,
                "sale_month": "2026-06",
                "type_of_sale": "New Sale",
                "transacted_price": base + 9_000_000,
            }
        )
    path = tmp_path / "transactions.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _spatial_files(tmp_path):
    projects = (
        "THE POIZ RESIDENCES",
        "PARK PLACE RESIDENCES AT PLQ",
        "BEDOK RESIDENCES",
    )
    locations = tmp_path / "locations.csv"
    pd.DataFrame(
        [
            {"project_name": project, "lat": 1.30 + index * 0.001, "lon": 103.80}
            for index, project in enumerate(projects)
        ]
    ).to_csv(locations, index=False)

    schools = tmp_path / "schools.csv"
    pd.DataFrame(
        [
            {
                "project_name": project,
                "primary_1km_count": index,
                "primary_1km_schools": f"SCHOOL {index}",
            }
            for index, project in enumerate(projects)
        ]
    ).to_csv(schools, index=False)

    mrt = tmp_path / "mrt.csv"
    pd.DataFrame(
        [
            {
                "name": "OPEN STATION",
                "stn_code": "XX1",
                "line": "Test Line",
                "lat": 1.30,
                "lon": 103.80,
                "operational": 1,
            },
            {
                "name": "FUTURE STATION",
                "stn_code": "XX2",
                "line": "Test Line",
                "lat": 1.301,
                "lon": 103.80,
                "operational": 0,
            },
        ]
    ).to_csv(mrt, index=False)
    return locations, schools, mrt


def test_latest_complete_month_excludes_current_partial_month(tmp_path):
    txns = comparison.load_transactions(
        _transactions(tmp_path),
        {
            "THE POIZ RESIDENCES",
            "PARK PLACE RESIDENCES AT PLQ",
            "BEDOK RESIDENCES",
        },
    )
    complete, partial = comparison.latest_complete_month(txns, date(2026, 7, 25))
    assert str(complete) == "2026-06"
    assert str(partial) == "2026-07"


def test_generate_uses_resale_only_complete_months_and_renders_method(tmp_path):
    locations, schools, mrt = _spatial_files(tmp_path)
    out = tmp_path / "comparison.html"
    out_path, rows, window = comparison.generate(
        _profiles(tmp_path),
        _transactions(tmp_path),
        locations,
        schools,
        mrt,
        out,
        as_of=date(2026, 7, 25),
    )

    assert out_path == out
    assert window == {
        "current_start": "2025-01",
        "full_end": "2026-06",
        "ttm_start": "2025-07",
        "partial_month": "2026-07",
    }
    poiz = next(row for row in rows if row["project"] == "THE POIZ RESIDENCES")
    assert poiz["stats"]["1"]["n"] == 3
    assert poiz["stats"]["1"]["median_price"] == 1_100_000
    assert poiz["resale_12m_n"] == 3
    assert poiz["partial_n"] == 1

    text = out.read_text(encoding="utf-8")
    assert "Park Place Residences at PLQ is the closest city-fringe integrated match" in text
    assert "PSF vs Poiz" in text
    assert "Exact BR provenance" in text
    assert "No asking listings" in text
    assert "2026-07" in text and "excluded from headline medians" in text
    assert "Estate Provision/Value bands are deliberately omitted" in text
    assert "Research findings" in text
    assert "Buyer decision comparison" in text
    assert "Planning and catalyst comparison" in text
    assert "Sources and calculation register" in text
    assert "Synthetic buyer fit" in text
    assert "Open unit-type growth and every resale transaction" in text
