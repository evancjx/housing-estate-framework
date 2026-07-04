import pandas as pd

import buyer_profile_model as bpm


def _master():
    return pd.DataFrame({
        "estate": ["ALPHA", "BETA", "CENTRAL AREA"],
        "archetype": ["B", "C", "X"],
        "provision_band": ["B", "C", "N/R"],
        "provision_score": [3.8, 3.2, 4.2],
        "provision_private": [4.1, 3.6, 4.4],
        "D_T0": [1.0, 0.9, 1.0],
        "D_T5": [1.0, 1.0, 1.0],
        "D_T15": [1.0, 1.0, 1.0],
        "yf_T5": [4.2, 3.2, "N/R"],
        "yf_T5_band": ["B+", "C", "N/R"],
        "ls_T0": [3.9, 3.4, "N/R"],
        "ls_T0_band": ["B", "C", "N/R"],
        "value_hdb_score": [3.7, 3.3, "N/R"],
        "value_hdb_band": ["B", "C", "N/R"],
        "value_hdb_basis": ["direct", "direct", "N/R"],
        "value_hdb_n": [250, 30, "N/R"],
        "value_private_score": [4.0, "not_covered", "N/R"],
        "value_private_band": ["B+", "not_covered", "N/R"],
        "value_private_basis": ["direct", "not_covered", "N/R"],
        "value_private_n": [180, "not_covered", "N/R"],
        "emp_score": [4.0, 2.7, "N/R"],
        "emp_band": ["B+", "D", "N/R"],
        "lease_score": [4.0, 2.4, "N/R"],
        "lease_band": ["B+", "F", "N/R"],
        "measured_only": [False, False, False],
    })


def _life_paths():
    return pd.DataFrame({
        "estate": ["ALPHA", "BETA"],
        "path": ["forming_family", "forming_family"],
        "start_score": [3.8, 3.0],
        "end_score": [4.2, 3.2],
        "delta": [0.4, 0.2],
    })


def test_hard_filters_apply_before_scoring():
    profile = {
        "profile_id": "hdb-family",
        "tenure": "hdb",
        "persona": "YoungFam",
        "horizon": "T5",
        "life_path": "forming_family",
        "hard_filters": {
            "exclude_archetypes": ["X"],
            "min_value_band": "C",
            "min_lease_band": "C",
            "min_value_n": 100,
        },
    }
    out = bpm.run(_master(), _life_paths(), profile)

    alpha = out[out["estate"] == "ALPHA"].iloc[0]
    beta = out[out["estate"] == "BETA"].iloc[0]
    central = out[out["estate"] == "CENTRAL AREA"].iloc[0]

    assert bool(alpha["eligible"]) is True
    assert alpha["rank"] == 1
    assert bool(beta["eligible"]) is False
    assert "lease_below:C" in beta["filter_reasons"]
    assert "value_n_below:100" in beta["filter_reasons"]
    assert bool(central["eligible"]) is False
    assert "excluded_archetype:X" in central["filter_reasons"]


def test_tenure_segments_are_output_separately():
    profile = {
        "profile_id": "any-tenure",
        "tenure": "any",
        "persona": "YoungFam",
        "horizon": "T5",
        "hard_filters": {"exclude_archetypes": []},
    }
    out = bpm.run(_master(), _life_paths(), profile)
    alpha = out[out["estate"] == "ALPHA"].sort_values("tenure")

    assert list(alpha["tenure"]) == ["hdb", "private"]
    hdb = alpha[alpha["tenure"] == "hdb"].iloc[0]
    private = alpha[alpha["tenure"] == "private"].iloc[0]
    assert hdb["value_band"] == "B"
    assert hdb["lease_band"] == "B+"
    assert private["value_band"] == "B+"
    assert private["lease_band"] == ""
    assert hdb["profile_score"] != private["profile_score"]


def test_missing_private_value_can_be_filtered_or_renormalised():
    profile = {
        "profile_id": "private-strict",
        "tenure": "private",
        "persona": "YoungFam",
        "horizon": "T5",
        "hard_filters": {
            "exclude_archetypes": [],
            "min_value_band": "C",
        },
    }
    strict = bpm.run(_master(), _life_paths(), profile)
    beta = strict[strict["estate"] == "BETA"].iloc[0]
    assert bool(beta["eligible"]) is False
    assert "value_below:C" in beta["filter_reasons"]

    profile["hard_filters"] = {"exclude_archetypes": []}
    relaxed = bpm.run(_master(), _life_paths(), profile)
    beta = relaxed[relaxed["estate"] == "BETA"].iloc[0]
    assert bool(beta["eligible"]) is True
    assert beta["profile_score"] is not None
    assert beta["soft_weight_covered"] < 1.0


def test_life_path_scores_are_merged_when_requested():
    profile = {
        "profile_id": "family-path",
        "tenure": "hdb",
        "persona": "YoungFam",
        "horizon": "T5",
        "life_path": "forming_family",
        "hard_filters": {"exclude_archetypes": []},
    }
    out = bpm.run(_master(), _life_paths(), profile)
    alpha = out[out["estate"] == "ALPHA"].iloc[0]

    assert alpha["life_path_end_score"] == 4.2
    assert alpha["life_path_delta"] == 0.4
