"""Financial boundaries and missing-evidence semantics for regional research."""

import pandas as pd
import pytest

from models.regional_research_economics import (
    bsd_residential,
    capital_only_scenarios,
    enrich_cohorts,
    rental_lens,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 1), (180_000, 1_800), (360_000, 5_400), (1_000_000, 24_600),
     (1_500_000, 44_600), (3_000_000, 119_600), (4_500_100, 209_606),
     (1_500_019.99, 44_600), (1_500_020, 44_601)],
)
def test_current_residential_bsd_boundaries_and_whole_dollar_rounding(value, expected):
    assert bsd_residential(value) == expected


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_bsd_rejects_invalid_dutiable_values(value):
    with pytest.raises(ValueError):
        bsd_residential(value)


def test_break_even_and_target_cover_purchase_duty_and_stated_friction():
    scenario = capital_only_scenarios(1_000_000, 800)
    assert scenario["scenario_bsd"] == 24_600
    assert scenario["scenario_acquisition_cost"] == 1_029_600
    assert scenario["break_even_sale"] * 0.975 == pytest.approx(1_029_600)
    assert scenario["target_500k_sale"] * 0.975 - 1_029_600 == pytest.approx(500_000)
    assert scenario["break_even_psf"] == pytest.approx(scenario["break_even_sale"] / 800)
    assert scenario["profit_down_10"] == -152_100
    assert scenario["profit_flat"] == -54_600
    assert scenario["profit_up_10"] == 42_900
    assert scenario["sc_second_property_absd"] == 200_000
    assert scenario["sc_second_property_break_even_sale"] * 0.975 == pytest.approx(1_229_600)


def rent_records():
    return pd.DataFrame([
        {"project_name": " TEST  PROJECT ", "ref_quarter": "2026Q2", "median_psf_pm": 5, "psf25": 4, "psf75": 6},
        {"project_name": "TEST PROJECT", "ref_quarter": "2025Q2", "median_psf_pm": 4, "psf25": 3, "psf75": 5},
        {"project_name": "OLD PROJECT", "ref_quarter": "2025Q2", "median_psf_pm": 3, "psf25": 2, "psf75": 4},
    ])


def cohorts():
    return pd.DataFrame([
        {"project_name": "Test Project", "ec_origin": False, "tenure": "99 years from 2010", "sale_type": "Resale", "n": 12, "median_price": 1_000_000, "median_psf": 2_000, "median_sqft": 800},
        {"project_name": "OLD PROJECT", "ec_origin": True, "tenure": "99 years from 2020", "sale_type": "New Sale", "n": 20, "median_price": 1_200_000, "median_psf": 1_500, "median_sqft": 800},
        {"project_name": "NO RENT", "ec_origin": False, "tenure": "Freehold", "sale_type": "Resale", "n": 3, "median_price": 2_000_000, "median_psf": 2_000, "median_sqft": 1_000},
    ], index=[5, 2, 9])


def test_rental_lens_uses_separate_psf_aggregate_and_does_not_backfill_missing_quarter():
    source = cohorts()
    rent = rent_records()
    before, rent_before = source.copy(deep=True), rent.copy(deep=True)
    result = rental_lens(source, rent)
    assert result.loc[5, "gross_yield_median_pct"] == 3  # 12 * 5 / 2,000
    assert result.loc[5, "gross_yield_p25_pct"] == 2.4
    assert result.loc[5, "rent_median_yoy_change_pct"] == 25
    assert result.loc[2, "rent_latest_available_quarter"] == "2025Q2"
    assert pd.isna(result.loc[2, "rent_current_median_psf_pm"])
    assert pd.isna(result.loc[2, "gross_yield_median_pct"])
    assert result.loc[2, "rent_match_status"] == "requested_quarter_missing"
    assert pd.isna(result.loc[9, "rent_latest_available_quarter"])
    pd.testing.assert_frame_equal(source, before)
    pd.testing.assert_frame_equal(rent, rent_before)


def test_ambiguous_normalized_rent_identity_is_rejected():
    rent = rent_records()
    ambiguous = pd.concat([rent, rent.iloc[[0]].assign(project_name="test project")])
    with pytest.raises(ValueError, match="Ambiguous rental"):
        rental_lens(cohorts(), ambiguous)


def test_duplicates_outside_requested_projects_do_not_block_valid_matches():
    rent = rent_records()
    unrelated = rent.iloc[[0]].assign(project_name="OUTSIDE SCOPE")
    result = rental_lens(cohorts(), pd.concat([rent, unrelated, unrelated]))
    assert result.loc[5, "gross_yield_median_pct"] == 3


def test_future_rent_is_not_substituted_for_requested_quarter():
    rent = rent_records().iloc[[2]].assign(ref_quarter="2026Q3")
    result = rental_lens(cohorts(), rent)
    assert pd.isna(result.loc[2, "rent_latest_available_quarter"])
    assert pd.isna(result.loc[2, "gross_yield_median_pct"])


def test_enrichment_preserves_segment_rows_and_marks_synthetic_anchor_and_ec_limit(tmp_path):
    rental_csv = tmp_path / "rents.csv"
    rent_records().to_csv(rental_csv, index=False)
    source = cohorts()
    before = source.copy(deep=True)
    result = enrich_cohorts(source, rental_csv)
    pd.testing.assert_frame_equal(result[source.columns], before)
    pd.testing.assert_frame_equal(source, before)
    assert result.loc[5, "scenario_entry_psf"] == 1_250
    assert result.loc[5, "median_psf"] == 2_000
    assert result.loc[5, "gross_yield_median_pct"] == 3
    assert "synthetic" in result.loc[5, "scenario_anchor_basis"]
    assert pd.isna(result.loc[2, "sc_second_property_absd"])
    assert result.loc[5, "sc_second_property_absd"] == 200_000
    assert result.attrs["economics_provenance"]["rental_quarter"] == "2026Q2"
    assert len(result.attrs["economics_provenance"]["rental_sha256"]) == 64


def test_enrichment_rejects_missing_area_instead_of_inventing_unit_area(tmp_path):
    source = cohorts().drop(columns="median_sqft")
    with pytest.raises(ValueError, match="median_sqft"):
        enrich_cohorts(source, tmp_path / "unused.csv")
