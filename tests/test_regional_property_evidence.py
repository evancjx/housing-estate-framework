"""Peer comparability and official stock-accounting boundaries for research."""

import math

import pandas as pd
import pytest

from models.build_regional_property_evidence import (
    build_peer_matches as match_observed_peers,
    norm,
    official_developer_evidence,
)


def subject(**overrides):
    row = {
        "cohort_id": "subject-cohort",
        "project_name": "SUBJECT",
        "region": "Canberra",
        "ec_origin": False,
        "tenure_group": "99-year lease",
        "tenure": "99 yrs lease commencing from 2010",
        "sale_type": "New Sale",
        "size_band": ">70-100 sqm",
        "n": 8,
        "median_sqm": 100.0,
        "median_psf": 1_800.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def owner_rows(project="PEER", count=5, **overrides):
    row = {
        "project_name": project,
        "region": "Canberra",
        "ec_origin": False,
        "tenure_group": "99-year lease",
        "tenure": "99 yrs lease commencing from 2010",
        "sale_type": "Resale",
        "size_band": ">70-100 sqm",
        "sqm": 100.0,
        "psf": 1_500.0,
        "price": 1_600_000.0,
    }
    row.update(overrides)
    # Identical public fields can represent different units: retain occurrences.
    return pd.DataFrame([row.copy() for _ in range(count)])


def build_peer_matches(cohorts, peers, locations):
    """Supply actual subject observations along with the independent peer set."""
    row = cohorts.iloc[0]
    subject_records = owner_rows(
        row.project_name, count=row.n, region=row.region, ec_origin=row.ec_origin,
        tenure_group=row.tenure_group, tenure=row.tenure, sale_type=row.sale_type,
        size_band=row.size_band, sqm=row.median_sqm, psf=row.median_psf,
    )
    recent = pd.concat([subject_records, peers], ignore_index=True)
    return match_observed_peers(cohorts, recent, locations)


@pytest.mark.parametrize("ec_origin", [False, True])
def test_peer_universe_keeps_ec_origin_region_and_tenure_separate(ec_origin):
    recent = pd.concat([
        owner_rows("SAME COHORT", ec_origin=ec_origin),
        owner_rows("OTHER EC COHORT", ec_origin=not ec_origin),
        owner_rows("OTHER REGION", ec_origin=ec_origin, region="Tampines"),
        owner_rows("OTHER TENURE", ec_origin=ec_origin, tenure_group="Freehold", tenure="Freehold"),
        owner_rows("SUBJECT", ec_origin=ec_origin),
    ], ignore_index=True)

    result = build_peer_matches(subject(ec_origin=ec_origin), recent, {})

    assert result.peer_project.tolist() == ["SAME COHORT"]
    assert result.ec_origin.tolist() == [ec_origin]


def test_owner_sale_states_are_separate_and_developer_sales_are_not_owner_peers():
    recent = pd.concat([
        owner_rows(sale_type="Resale", psf=1_500),
        owner_rows(sale_type="Sub Sale", psf=1_700),
        owner_rows(sale_type="New Sale", psf=2_200),
    ], ignore_index=True)

    result = build_peer_matches(subject(), recent, {}).set_index("peer_sale_type")

    assert set(result.index) == {"Resale", "Sub Sale"}
    assert result.loc["Resale", "peer_n"] == 5
    assert result.loc["Sub Sale", "peer_n"] == 5
    assert result.loc["Resale", "peer_median_psf"] == 1_500
    assert result.loc["Sub Sale", "peer_median_psf"] == 1_700
    assert result.subject_sale_type.eq("New Sale").all()


def test_thin_sale_states_cannot_be_pooled_to_reach_peer_minimum():
    recent = pd.concat([
        owner_rows(count=3, sale_type="Resale"),
        owner_rows(count=3, sale_type="Sub Sale"),
    ], ignore_index=True)

    assert build_peer_matches(subject(), recent, {}).empty


@pytest.mark.parametrize(
    ("subject_n", "peer_n", "accepted"),
    [(4, 5, False), (5, 4, False), (5, 5, True)],
)
def test_both_subject_and_peer_need_five_observations(subject_n, peer_n, accepted):
    result = build_peer_matches(subject(n=subject_n), owner_rows(count=peer_n), {})

    assert (not result.empty) is accepted


@pytest.mark.parametrize(
    ("subject_sqm", "peer_sqm", "accepted"),
    [(40, 37, True), (40, 43, True), (40, 36.9, False), (40, 43.1, False),
     (100, 95, True), (100, 105, True), (100, 94.9, False), (100, 105.1, False)],
)
def test_area_tolerance_includes_boundary_and_uses_three_sqm_minimum(subject_sqm, peer_sqm, accepted):
    result = build_peer_matches(
        subject(median_sqm=subject_sqm), owner_rows(sqm=peer_sqm), {}
    )

    assert (not result.empty) is accepted


def test_peer_sample_minimum_applies_after_area_filtering():
    recent = pd.concat([
        owner_rows(count=4, sqm=100),
        owner_rows(count=10, sqm=110),
    ], ignore_index=True)

    assert build_peer_matches(subject(), recent, {}).empty


def test_subject_minimum_uses_observed_same_state_and_area_rows():
    recent = pd.concat([
        owner_rows("SUBJECT", count=4, sale_type="New Sale"),
        owner_rows("SUBJECT", count=10, sale_type="Sub Sale"),
        owner_rows("SUBJECT", count=10, sale_type="New Sale", sqm=90),
        owner_rows(),
    ], ignore_index=True)

    assert match_observed_peers(subject(n=14), recent, {}).empty


def test_peer_gap_uses_narrow_subject_distribution_not_broad_cohort_median():
    matching_subject = owner_rows(
        "SUBJECT", sale_type="New Sale", size_band=">100-130 sqm", sqm=115
    ).assign(psf=[1_500, 1_600, 1_700, 1_800, 1_900])
    recent = pd.concat([
        matching_subject,
        owner_rows("SUBJECT", count=3, sale_type="New Sale", size_band=">100-130 sqm", sqm=105, psf=1_000),
        owner_rows("SUBJECT", count=2, sale_type="New Sale", size_band=">100-130 sqm", sqm=125, psf=1_000),
        owner_rows(sqm=115, size_band=">100-130 sqm", psf=1_500),
    ], ignore_index=True)
    cohort = subject(n=10, size_band=">100-130 sqm", median_sqm=115, median_psf=1_250)
    before = recent.copy(deep=True)

    result = match_observed_peers(cohort, recent, {}).iloc[0]

    assert result.subject_cohort_n == 10
    assert result.subject_cohort_median_sqm == 115
    assert result.subject_n == 5
    assert result.subject_min_sqm == result.subject_max_sqm == 115
    assert result.subject_median_psf == 1_700
    assert result.unadjusted_psf_gap_pct == pytest.approx(100 * (1_700 / 1_500 - 1))
    pd.testing.assert_frame_equal(recent, before)


@pytest.mark.parametrize(("metres", "accepted"), [(1_999, True), (2_001, False)])
def test_known_project_distance_must_be_within_two_kilometres(metres, accepted):
    locations = {
        norm("SUBJECT"): {"lat": 0.0, "lon": 0.0},
        norm("PEER"): {"lat": 0.0, "lon": math.degrees(metres / 6_371_000)},
    }

    result = build_peer_matches(subject(), owner_rows(), locations)

    assert (not result.empty) is accepted
    if accepted:
        assert result.iloc[0].distance_m == pytest.approx(metres)
        assert result.iloc[0].location_basis == "Within 2km by matched project points"


def test_missing_geometry_is_explicitly_regional_not_assumed_nearby():
    locations = {norm("SUBJECT"): {"lat": 1.44, "lon": 103.83}}

    result = build_peer_matches(subject(), owner_rows(), locations)

    assert len(result) == 1
    assert pd.isna(result.iloc[0].distance_m)
    assert result.iloc[0].location_basis == "Regional size match; proximity unverified"


@pytest.mark.parametrize(
    ("peer_year", "accepted"), [(2000, True), (2020, True), (1999, False), (2021, False)]
)
def test_known_lease_commencement_must_be_within_ten_years(peer_year, accepted):
    result = build_peer_matches(
        subject(), owner_rows(tenure=f"99 yrs lease commencing from {peer_year}"), {}
    )

    assert (not result.empty) is accepted
    if accepted:
        assert result.iloc[0].lease_basis == "Lease commencement within 10 years"


def test_unknown_lease_start_is_not_reported_as_age_matched():
    result = build_peer_matches(
        subject(), owner_rows(tenure="99 years leasehold"), {}
    )

    assert len(result) == 1
    assert result.iloc[0].lease_basis == "Same tenure category; building age not matched"


def test_masked_duplicate_occurrences_count_and_weight_the_peer_distribution():
    recent = pd.concat([
        owner_rows(count=5, psf=1_000, price=1_000_000),
        owner_rows(count=1, psf=2_000, price=2_000_000),
    ], ignore_index=True)
    before = recent.copy(deep=True)

    result = build_peer_matches(subject(), recent, {})

    assert result.iloc[0].peer_n == 6
    assert result.iloc[0].peer_median_psf == 1_000
    assert result.iloc[0].peer_median_price == 1_000_000
    pd.testing.assert_frame_equal(recent, before)


def developer_snapshot(tmp_path, rows):
    directory = tmp_path / "enrichment" / "developer_sales"
    directory.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(directory / "snapshot.csv", index=False)
    return pd.DataFrame([
        {"project_name": "TEST PROJECT", "region": "Canberra", "ec_origin": False}
    ])


def test_developer_total_unsold_is_not_the_launched_unsold_balance(tmp_path):
    projects = developer_snapshot(tmp_path, [
        {"project_name": "Test Project", "ref_month": "2026-06", "units_avail": 100,
         "launched_to_date": 80, "sold_to_date": 50, "sold_in_month": 4},
        {"project_name": "Test Project", "ref_month": "2026-07", "units_avail": 100,
         "launched_to_date": 90, "sold_to_date": 60, "sold_in_month": 10},
        {"project_name": "OUTSIDE SCOPE", "ref_month": "2026-08", "units_avail": 10,
         "launched_to_date": 10, "sold_to_date": 9, "sold_in_month": 1},
    ])

    records, latest = official_developer_evidence(tmp_path, projects)

    assert records.project_name.tolist() == ["TEST PROJECT", "TEST PROJECT"]
    assert records.unsold_total.tolist() == [50, 40]
    assert records.launched_unsold.tolist() == [30, 30]
    assert records.unlaunched_units.tolist() == [20, 10]
    assert (records.unsold_total == records.launched_unsold + records.unlaunched_units).all()
    assert latest.iloc[0].ref_month == "2026-07"
    assert latest.iloc[0].sold_pct == 60
    assert latest.iloc[0].developer_sales_jun_aug == 14
    assert latest.iloc[0].months_reported_jun_aug == 2


@pytest.mark.parametrize(
    ("total", "launched", "sold"),
    [(100, 80, 81), (100, 100, 101), (100, 101, 50)],
)
def test_impossible_developer_stock_accounting_is_rejected(tmp_path, total, launched, sold):
    projects = developer_snapshot(tmp_path, [
        {"project_name": "Test Project", "ref_month": "2026-08", "units_avail": total,
         "launched_to_date": launched, "sold_to_date": sold, "sold_in_month": 1},
    ])

    with pytest.raises((AssertionError, ValueError)):
        official_developer_evidence(tmp_path, projects)
