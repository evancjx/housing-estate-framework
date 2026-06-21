import numpy as np
import pandas as pd
import value_model


def test_build_formula_excludes_provision_score(tiny_hdb):
    f = value_model.build_formula(tiny_hdb, ["flat_type", "remaining_lease_years"], "month")
    assert "_score" not in f, "provision score must NOT be a regressor (circularity)"
    assert "C(flat_type)" in f
    assert "remaining_lease_years" in f
    assert "C(month)" in f
    assert f.startswith("_lnpsm ~")


def _resid_df():
    return pd.DataFrame(
        {
            "estate": ["QUEENSTOWN", "TAMPINES"],
            "segment": ["hdb_resale", "hdb_resale"],
            "n": [6353, 16029],
            "resid_raw": [0.244, 0.074],
            "resid_shrunk": [0.244, 0.074],
            "trust": ["decimal", "decimal"],
        }
    )


def _scores():
    return pd.DataFrame(
        {
            "estate": ["QUEENSTOWN", "TAMPINES", "DOVER", "HOLLAND VILLAGE", "TAMPINES WEST"],
            "score": [3.59, 3.52, 3.60, 4.01, 3.71],
        }
    )


def test_private_dominant_proxy_gets_no_hdb_residual():
    out = value_model.value_scores(_resid_df(), _scores(), set(_scores()["estate"]))
    hv = out[out["estate"] == "HOLLAND VILLAGE"].iloc[0]
    assert hv["value_basis"] == "no_hdb_segment"
    assert pd.isna(hv["value_score"])
    assert hv["value_band"] == "N/A"


def test_subarea_proxy_is_tagged_not_silent():
    out = value_model.value_scores(_resid_df(), _scores(), set(_scores()["estate"]))
    dover = out[out["estate"] == "DOVER"].iloc[0]
    assert dover["value_basis"] == "proxy_from:QUEENSTOWN"


def test_direct_rows_tagged_direct():
    out = value_model.value_scores(_resid_df(), _scores(), set(_scores()["estate"]))
    q = out[out["estate"] == "QUEENSTOWN"].iloc[0]
    assert q["value_basis"] == "direct"
