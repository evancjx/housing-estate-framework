import pandas as pd

import ingest_hdb_density
import liveability_model
import provision_model


def _empty_points(extra_cols=None):
    cols = ["lat", "lon"] + list(extra_cols or [])
    return pd.DataFrame(columns=cols)


def test_generated_layers_override_judged_fallbacks():
    estates = pd.DataFrame({"estate": ["TEST"], "lat": [1.35], "lon": [103.8]})
    judged = pd.DataFrame({"estate": ["TEST"], "dens": [1.0], "env": [1.0], "mom": [3.0], "hawker": [1.0]})
    layers = {
        "mrt": _empty_points(["operational"]),
        "bus": _empty_points(["route_count"]),
        "clinics": _empty_points(),
        "polyclinics": _empty_points(),
        "schools": _empty_points(),
        "parks": _empty_points(),
        "markets": _empty_points(),
        "supermarkets": _empty_points(),
        "childcare": _empty_points(),
        "community": _empty_points(),
        "sport": _empty_points(),
        "flood": _empty_points(),
        "noise": _empty_points(),
        "air_noise": _empty_points(),
        "eldercare": _empty_points(),
        "covered_linkway": None,
        "jtc_industrial": None,
        "air_quality": None,
        "tree_canopy": pd.DataFrame({"estate": ["TEST"], "canopy_cover_pct": [30.0], "uhi_delta_c": [0.1]}),
        "hdb_density": pd.DataFrame({"estate": ["TEST"], "total_dwelling_units": [1000], "residents_per_net_hectare": [100.0]}),
        "hawker_v2": pd.DataFrame({
            "estate": ["TEST"],
            "nearest_hawker_m": [100.0],
            "total_stalls_800m": [200],
            "n_hawker_centres_800m": [2],
            "has_redundancy_dayoff": [True],
        }),
        "coastal": pd.DataFrame({"estate": ["TEST"], "has_blue_within_800m": [False]}),
    }

    row = provision_model.run(estates, layers, judged).iloc[0]

    assert row["dens"] == 5.0
    assert row["env"] == 5.0
    assert row["hawker"] == 5.0
    assert row["mom"] == 3.0


def test_hdb_density_keeps_jurong_west_and_duplicates_kwn():
    csv_text = """residential,bldg_contract_town,total_dwelling_units,year_completed,max_floor_lvl
Y,JW,100,1990,12
Y,KWN,80,1980,10
"""
    agg = ingest_hdb_density.aggregate_by_estate(csv_text)

    assert agg["JURONG WEST"]["dus"] == 100
    assert agg["BOON KENG"]["dus"] == 80
    assert agg["KALLANG"]["dus"] == 80


def test_bca_severity_lowers_d_multiplier():
    bca = pd.DataFrame({"estate": ["TEST"], "severity_score": [125.0]})

    assert liveability_model.compute_d_multipliers([], 2026, bca) == {"TEST": 0.875}


def _layers_all_present():
    return {
        "mrt": _empty_points(["operational"]),
        "bus": _empty_points(["route_count"]),
        "clinics": _empty_points(),
        "polyclinics": _empty_points(),
        "schools": _empty_points(),
        "parks": _empty_points(),
        "markets": _empty_points(),
        "supermarkets": _empty_points(),
        "childcare": _empty_points(),
        "community": _empty_points(),
        "sport": _empty_points(),
        "flood": _empty_points(),
        "noise": _empty_points(),
        "air_noise": _empty_points(),
        "eldercare": _empty_points(),
        "covered_linkway": None,
        "jtc_industrial": None,
        "air_quality": None,
        "tree_canopy": pd.DataFrame({"estate": ["TEST"], "canopy_cover_pct": [30.0], "uhi_delta_c": [0.1]}),
        "hdb_density": pd.DataFrame({"estate": ["TEST"], "total_dwelling_units": [1000], "residents_per_net_hectare": [100.0]}),
        "hawker_v2": pd.DataFrame({
            "estate": ["TEST"], "nearest_hawker_m": [100.0], "total_stalls_800m": [200],
            "n_hawker_centres_800m": [2], "has_redundancy_dayoff": [True],
        }),
        "coastal": pd.DataFrame({"estate": ["TEST"], "has_blue_within_800m": [False]}),
    }


def test_measured_only_reflects_all_six_partly_components():
    # air_quality and stewardship are PARTLY_MEASURED (framework_config.PROVENANCE). When they are
    # absent (no --air_quality layer, no --tcmr) the score is renormalised over present components,
    # so measured_only MUST be True even though dens/env/mom/hawker are all present.
    estates = pd.DataFrame({"estate": ["TEST"], "lat": [1.35], "lon": [103.8]})
    judged = pd.DataFrame({"estate": ["TEST"], "dens": [3.0], "env": [3.0], "mom": [3.0], "hawker": [3.0]})
    row = provision_model.run(estates, _layers_all_present(), judged).iloc[0]  # no tcmr -> stewardship NaN
    assert pd.isna(row["stewardship"]) or pd.isna(row["air_quality"])
    assert bool(row["measured_only"]) is True
