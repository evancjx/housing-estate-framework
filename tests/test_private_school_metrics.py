import pandas as pd
import pytest

import private_school_metrics as psm
from sg_estate.project_locations import (
    CURRENT_LOCATION_COLUMNS,
    LEGACY_LOCATION_COLUMNS,
    canonical_project_location_match_sha256,
)


def test_school_levels_expands_mixed_level_schools():
    assert psm.school_levels("PRIMARY") == ["primary"]
    assert psm.school_levels("SECONDARY (S1-S5)") == ["secondary"]
    assert psm.school_levels("MIXED LEVEL (P1-S4)") == ["primary", "secondary"]
    assert psm.school_levels("MIXED LEVEL (S1-JC2)") == ["secondary", "year_5_jc"]


def test_load_locations_uses_only_matched_geocodes_by_default(tmp_path):
    locations_path = tmp_path / "locations.csv"
    pd.DataFrame([
        {
            "project_name": "MATCHED CONDO",
            "street_name": "TEST ROAD",
            "postal_district": "10",
            "planning_area": "BISHAN",
            "lat": 1.0,
            "lon": 103.0,
            "match_status": "matched",
        },
        {
            "project_name": "UNREVIEWED CONDO",
            "street_name": "TEST ROAD",
            "postal_district": "10",
            "planning_area": "BISHAN",
            "lat": 1.0,
            "lon": 103.0,
            "match_status": "needs_review",
        },
    ], columns=LEGACY_LOCATION_COLUMNS).to_csv(locations_path, index=False)

    out = psm.load_locations(locations_path)

    assert list(out["project_name"]) == ["MATCHED CONDO"]


def test_load_locations_withholds_pending_and_unbound_approved_rows(tmp_path):
    locations_path = tmp_path / "locations.csv"
    common: dict[str, object] = {
        "street_name": "TEST ROAD",
        "postal_district": "10",
        "planning_area": "BISHAN",
        "lat": 1.0,
        "lon": 103.0,
        "match_status": "matched",
        "match_sha256": "a" * 64,
        "reviewed_match_sha256": "a" * 64,
        "reviewed_at": "2026-08-13T00:00:00Z",
        "retrieved_at": "2026-08-13T00:00:00Z",
        "response_sha256": "b" * 64,
        "retry_state": "complete",
        "attempt_count": 1,
        "last_error": "",
        "review_decision_note": "fixture",
        "match_score": 105,
        "query_used": "TEST CONDO TEST ROAD",
        "onemap_building": "TEST CONDO",
        "onemap_road": "TEST ROAD",
        "onemap_address": "1 TEST ROAD",
        "onemap_postal": "238800",
        "review_note": "project,street",
    }
    rows = [
            {**common, "project_name": "APPROVED", "review_status": "approved"},
            {
                **common,
                "project_name": "PENDING",
                "review_status": "pending_changed",
            },
            {
                **common,
                "project_name": "UNBOUND",
                "review_status": "approved",
                "reviewed_match_sha256": "b" * 64,
            },
            {
                **common,
                "project_name": "WEAK",
                "match_status": "needs_review",
                "review_status": "approved_legacy",
            },
        ]
    for row in rows:
        if row["project_name"] == "APPROVED":
            row["match_sha256"] = canonical_project_location_match_sha256(row)
            row["reviewed_match_sha256"] = row["match_sha256"]
    pd.DataFrame(rows, columns=CURRENT_LOCATION_COLUMNS).to_csv(
        locations_path, index=False
    )

    with pytest.raises(SystemExit, match="invalid review/hash binding"):
        psm.load_locations(locations_path, {"matched", "needs_review"})

    approved_path = tmp_path / "approved-locations.csv"
    pd.DataFrame([rows[0]], columns=CURRENT_LOCATION_COLUMNS).to_csv(
        approved_path, index=False
    )
    out = psm.load_locations(approved_path, {"matched", "needs_review"})
    assert list(out["project_name"]) == ["APPROVED"]


def test_build_project_school_metrics_uses_level_specific_radii():
    locations = pd.DataFrame([
        {
            "project_name": "TEST CONDO",
            "street_name": "TEST ROAD",
            "postal_district": "10",
            "planning_area": "BISHAN",
            "lat": 1.0,
            "lon": 103.0,
            "match_status": "matched",
        }
    ])
    schools = pd.DataFrame([
        {
            "school_name": "TOP PRIMARY",
            "school_name_norm": psm.normalise_school_name("TOP PRIMARY"),
            "level": "primary",
            "school_lat": 1.0,
            "school_lon": 103.0,
            "mainlevel_code": "PRIMARY",
        },
        {
            "school_name": "FAR PRIMARY",
            "school_name_norm": psm.normalise_school_name("FAR PRIMARY"),
            "level": "primary",
            "school_lat": 1.02,
            "school_lon": 103.0,
            "mainlevel_code": "PRIMARY",
        },
        {
            "school_name": "NEAR PRIMARY",
            "school_name_norm": psm.normalise_school_name("NEAR PRIMARY"),
            "level": "primary",
            "school_lat": 1.001,
            "school_lon": 103.0,
            "mainlevel_code": "PRIMARY",
        },
        {
            "school_name": "TOP SECONDARY",
            "school_name_norm": psm.normalise_school_name("TOP SECONDARY"),
            "level": "secondary",
            "school_lat": 1.01,
            "school_lon": 103.0,
            "mainlevel_code": "SECONDARY (S1-S5)",
        },
        {
            "school_name": "TOP JC",
            "school_name_norm": psm.normalise_school_name("TOP JC"),
            "level": "year_5_jc",
            "school_lat": 1.03,
            "school_lon": 103.0,
            "mainlevel_code": "JUNIOR COLLEGE",
        },
    ])
    selectivity = pd.DataFrame([
        {
            "school_name": "TOP PRIMARY",
            "level": "primary",
            "rank": 2,
            "score_raw": "310%",
            "score_normalized": 90,
            "metric_type": "p1_phase_2b_subscription_rate",
            "source_year": 2025,
            "source_quality": "test",
            "source_url": "test",
        },
        {
            "school_name": "TOP SECONDARY",
            "level": "secondary",
            "rank": 4,
            "score_raw": "IP AL6",
            "score_normalized": 70,
            "metric_type": "psle_al_cutoff_proxy",
            "source_year": 2025,
            "source_quality": "test",
            "source_url": "test",
        },
        {
            "school_name": "TOP JC",
            "level": "year_5_jc",
            "rank": 5,
            "score_raw": "Science 5",
            "score_normalized": 60,
            "metric_type": "jae_l1r5_cutoff_proxy",
            "source_year": 2025,
            "source_quality": "test",
            "source_url": "test",
        },
    ])
    selectivity["school_name_norm"] = selectivity["school_name"].apply(psm.normalise_school_name)

    out = psm.build_project_school_metrics(locations, schools, selectivity)
    row = out.iloc[0]

    assert bool(row["has_primary_1km"]) is True
    assert row["primary_1km_count"] == 2
    assert row["primary_1km_schools"] == "TOP PRIMARY; NEAR PRIMARY"
    assert row["best_primary_1km_school"] == "TOP PRIMARY"
    assert row["best_primary_1km_rank"] == 2
    assert row["secondary_2km_count"] == 1
    assert row["best_secondary_2km_school"] == "TOP SECONDARY"
    assert row["jc_5km_count"] == 1
    assert row["best_jc_5km_school"] == "TOP JC"
