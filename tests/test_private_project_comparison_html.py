import pandas as pd

import gen_private_project_comparison_html as table


def test_aggregate_projects_includes_private_school_metrics():
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
            "lon": 103.0,
            "operational": 1,
        }
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
    assert row["has_primary_1km"] is True
    assert row["primary_1km_count"] == 2
    assert row["best_primary_1km_school"] == "TOP PRIMARY"
    assert row["best_primary_1km_rank"] == 3
    assert row["best_secondary_2km_school"] == "TOP SECONDARY"
    assert row["best_jc_5km_school"] == "TOP JC"
