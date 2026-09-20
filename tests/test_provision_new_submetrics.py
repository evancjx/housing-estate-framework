"""Sub-metric wiring for the three layers added in the v2.1 provision refresh.

Covers:
  conn  += park-connector metres  (cycling_paths.csv, estate-keyed)
  amen  += mixed-use land share   (mixed_use.csv, estate-keyed)
  hlth  += nearest acute hospital (hospitals.csv, point layer)

Each scorer must keep its previous composition when the new layer is absent,
and a missing/blank value must never be read as a measured zero.
"""
import os

import numpy as np
import pandas as pd
import pytest

import provision_model as p

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.path.join(HERE, "data", "inputs")


# ---------------------------------------------------------------- fixtures

def _bus():
    return pd.DataFrame(columns=["lat", "lon"])


def _open_station(lat=1.35, lon=103.8015):
    return pd.DataFrame([{"lat": lat, "lon": lon, "operational": 1}])


def _linkways(n, lat=1.35, lon=103.8):
    return pd.DataFrame([{"lat": lat, "lon": lon} for _ in range(n)])


def _clinics(n, lat=1.35, lon=103.8):
    return pd.DataFrame([{"lat": lat, "lon": lon} for _ in range(n)])


def _poly(lat=1.35, lon=103.8):
    return pd.DataFrame([{"lat": lat, "lon": lon}])


# ------------------------------------------------------- band anchor tables

def test_pcn_anchors_span_the_observed_national_range():
    # C_PCN is a count-style table: metres >= threshold -> score.
    assert p.score_by_count(4410, p.C_PCN) == 5      # BOON KENG, national max
    assert p.score_by_count(3500, p.C_PCN) == 5
    assert p.score_by_count(2600, p.C_PCN) == 4
    assert p.score_by_count(1600, p.C_PCN) == 3
    assert p.score_by_count(600, p.C_PCN) == 2
    assert p.score_by_count(0, p.C_PCN) == 1         # CENTRAL AREA, LENTOR


def test_mixed_use_anchors_span_the_observed_national_range():
    assert p.score_by_count(0.118, p.C_MIXED) == 5   # CENTRAL AREA, national max
    assert p.score_by_count(0.06, p.C_MIXED) == 5
    assert p.score_by_count(0.04, p.C_MIXED) == 4
    assert p.score_by_count(0.02, p.C_MIXED) == 3
    assert p.score_by_count(0.006, p.C_MIXED) == 2
    assert p.score_by_count(0.0, p.C_MIXED) == 1


@pytest.mark.parametrize(
    "csv_name,column,anchors",
    [
        ("cycling_paths.csv", "pcn_continuous_m", "C_PCN"),
        ("mixed_use.csv", "mixed_use_share", "C_MIXED"),
    ],
)
def test_new_anchor_tables_put_the_national_median_at_band_3(csv_name, column, anchors):
    """A new sub-metric must re-rank estates, not deflate every score.

    An anchor table whose median lands at 1 or 2 drags every estate's component
    down instead of discriminating between them. Guarding the calibration rule
    directly stops a future edit from silently reintroducing that bias.
    """
    table = getattr(p, anchors)
    values = pd.read_csv(os.path.join(INPUTS, csv_name))[column].dropna()
    assert len(values) >= 30, f"{csv_name} lost rows; recalibrate before trusting this"
    assert p.score_by_count(values.median(), table) == 3

    scored = [p.score_by_count(v, table) for v in values]
    assert min(scored) == 1 and max(scored) == 5, "table must span the full 1-5 range"
    assert 2.6 <= sum(scored) / len(scored) <= 3.4, (
        f"{anchors} mean band {sum(scored) / len(scored):.2f} is off-centre; "
        "it would shift the component level rather than re-rank estates"
    )


def test_hospital_anchors_are_distance_style():
    # A_HOSP is a distance table: metres <= threshold -> score.
    assert p.score_by_distance(1500, p.A_HOSP) == 5
    assert p.score_by_distance(3000, p.A_HOSP) == 4
    assert p.score_by_distance(5000, p.A_HOSP) == 3
    assert p.score_by_distance(8000, p.A_HOSP) == 2
    assert p.score_by_distance(20000, p.A_HOSP) == 1


# ------------------------------------------------------------- connectivity

def test_connectivity_uses_base_weights_when_both_optional_layers_absent():
    """Pre-existing behaviour: 0.70 MRT + 0.30 bus."""
    score, _ = p.score_connectivity(1.35, 103.8, _open_station(), _bus(), None)
    s_mrt = p.score_by_distance(p.nearest_m(1.35, 103.8, [(1.35, 103.8015)]), p.A_MRT)
    assert score == round(0.70 * s_mrt + 0.30 * 1, 2)


def test_connectivity_keeps_linkway_weights_when_cycling_layer_absent():
    """Regression guard: covered_linkway alone must still be 0.60/0.25/0.15."""
    score, _ = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None, _linkways(60)
    )
    s_mrt = p.score_by_distance(p.nearest_m(1.35, 103.8, [(1.35, 103.8015)]), p.A_MRT)
    s_shelter = p.score_by_count(60, p.C_SHELTER)
    assert score == round(0.60 * s_mrt + 0.25 * 1 + 0.15 * s_shelter, 2)


def test_connectivity_reweights_to_include_park_connector_metres():
    """With both layers: 0.55 MRT + 0.25 bus + 0.12 shelter + 0.08 PCN."""
    score, meta = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None, _linkways(60),
        cycling_row={"pcn_continuous_m": 4410},
    )
    s_mrt = p.score_by_distance(p.nearest_m(1.35, 103.8, [(1.35, 103.8015)]), p.A_MRT)
    s_shelter = p.score_by_count(60, p.C_SHELTER)
    expected = round(0.55 * s_mrt + 0.25 * 1 + 0.12 * s_shelter + 0.08 * 5, 2)
    assert score == expected
    assert meta["pcn_continuous_m"] == 4410


def test_connectivity_rewards_more_park_connector_metres():
    common = dict(covered_linkway=_linkways(60))
    low, _ = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None,
        cycling_row={"pcn_continuous_m": 0}, **common
    )
    high, _ = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None,
        cycling_row={"pcn_continuous_m": 4410}, **common
    )
    assert high > low


@pytest.mark.parametrize("blank", [None, "", np.nan, float("nan")])
def test_connectivity_treats_blank_pcn_as_absent_not_zero(blank):
    """A blank must fall back to the linkway composition, never score as 0 metres."""
    blank_score, _ = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None, _linkways(60),
        cycling_row={"pcn_continuous_m": blank},
    )
    absent_score, _ = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None, _linkways(60)
    )
    zero_score, _ = p.score_connectivity(
        1.35, 103.8, _open_station(), _bus(), None, _linkways(60),
        cycling_row={"pcn_continuous_m": 0},
    )
    assert blank_score == absent_score
    assert blank_score != zero_score


# ---------------------------------------------------------------- amenities

def test_amenities_unchanged_when_mixed_use_row_absent():
    """Pre-existing behaviour: 0.40 market + 0.35 supermarket + 0.25 clinic."""
    markets, supers, clinics = _clinics(3), _clinics(4), _clinics(8)
    score, _ = p.score_amenities(1.35, 103.8, markets, supers, clinics)
    expected = round(
        0.40 * p.score_by_count(3, p.C_MARKET)
        + 0.35 * p.score_by_count(4, p.C_SUPER)
        + 0.25 * p.score_by_count(8, p.C_CLINIC),
        2,
    )
    assert score == expected


def test_amenities_reweights_to_include_mixed_use_share():
    """With mixed use: 0.34 market + 0.30 supermarket + 0.21 clinic + 0.15 mixed.

    The three original sub-metrics keep their relative shares (scaled by 0.85).
    """
    markets, supers, clinics = _clinics(3), _clinics(4), _clinics(8)
    score, meta = p.score_amenities(
        1.35, 103.8, markets, supers, clinics,
        mixed_use_row={"mixed_use_share": 0.118089},
    )
    expected = round(
        0.34 * p.score_by_count(3, p.C_MARKET)
        + 0.30 * p.score_by_count(4, p.C_SUPER)
        + 0.21 * p.score_by_count(8, p.C_CLINIC)
        + 0.15 * 5,
        2,
    )
    assert score == expected
    assert meta["mixed_use_share"] == pytest.approx(0.118089)


def test_amenities_treats_blank_mixed_use_as_absent_not_zero():
    markets, supers, clinics = _clinics(3), _clinics(4), _clinics(8)
    blank, _ = p.score_amenities(
        1.35, 103.8, markets, supers, clinics,
        mixed_use_row={"mixed_use_share": np.nan},
    )
    absent, _ = p.score_amenities(1.35, 103.8, markets, supers, clinics)
    zero, _ = p.score_amenities(
        1.35, 103.8, markets, supers, clinics,
        mixed_use_row={"mixed_use_share": 0.0},
    )
    assert blank == absent
    assert blank != zero


# --------------------------------------------------------------- healthcare

def test_healthcare_unchanged_when_hospital_layer_absent():
    """Pre-existing behaviour: 0.55 polyclinic + 0.45 GP."""
    score, _ = p.score_healthcare(1.35, 103.8, _clinics(8), _poly())
    expected = round(0.55 * 5 + 0.45 * p.score_by_count(8, p.C_CLINIC), 2)
    assert score == expected


def test_healthcare_reweights_to_include_acute_hospital_distance():
    """With hospitals: 0.40 polyclinic + 0.35 GP + 0.25 acute hospital."""
    hospitals = pd.DataFrame(
        [{"name": "Near General", "lat": 1.35, "lon": 103.8, "tier": "acute"}]
    )
    score, meta = p.score_healthcare(1.35, 103.8, _clinics(8), _poly(), hospitals)
    expected = round(
        0.40 * 5 + 0.35 * p.score_by_count(8, p.C_CLINIC) + 0.25 * 5, 2
    )
    assert score == expected
    assert meta["nearest_acute_hospital_m"] == 0


def test_healthcare_ignores_community_hospitals():
    """Only the acute tier counts; a community hospital next door must not help."""
    community_only = pd.DataFrame(
        [{"name": "Near Community", "lat": 1.35, "lon": 103.8, "tier": "community"}]
    )
    far_acute = pd.DataFrame(
        [
            {"name": "Near Community", "lat": 1.35, "lon": 103.8, "tier": "community"},
            {"name": "Far General", "lat": 1.42, "lon": 103.90, "tier": "acute"},
        ]
    )
    community_score, community_meta = p.score_healthcare(
        1.35, 103.8, _clinics(8), _poly(), community_only
    )
    mixed_score, mixed_meta = p.score_healthcare(
        1.35, 103.8, _clinics(8), _poly(), far_acute
    )
    # The community-only frame has no acute row at all -> no hospital sub-metric.
    absent_score, _ = p.score_healthcare(1.35, 103.8, _clinics(8), _poly())
    assert community_score == absent_score
    assert community_meta.get("nearest_acute_hospital_m") is None
    assert mixed_meta["nearest_acute_hospital_m"] > 5000
    assert mixed_score < round(0.40 * 5 + 0.35 * p.score_by_count(8, p.C_CLINIC) + 0.25 * 5, 2)


def test_healthcare_rewards_a_closer_acute_hospital():
    near = pd.DataFrame([{"name": "A", "lat": 1.3515, "lon": 103.8, "tier": "acute"}])
    far = pd.DataFrame([{"name": "B", "lat": 1.45, "lon": 103.95, "tier": "acute"}])
    near_score, _ = p.score_healthcare(1.35, 103.8, _clinics(8), _poly(), near)
    far_score, _ = p.score_healthcare(1.35, 103.8, _clinics(8), _poly(), far)
    assert near_score > far_score
