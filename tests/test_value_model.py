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


def test_clean_psm_drops_zero_area():
    df = pd.DataFrame({"resale_price": [500000, 600000], "floor_area_sqm": [0, 100]})
    out = value_model.clean_psm(df, "resale_price", "floor_area_sqm")
    assert len(out) == 1
    assert np.isfinite(out["_lnpsm"]).all()
    assert (out["floor_area_sqm"] > 0).all()


def test_private_segment_uses_score_private():
    # Invariant 2: private value is a SEPARATE universe scored with W_PRIVATE weights.
    # The value base for a private segment must be score_private, not the public provision score.
    scores = pd.DataFrame({"estate": ["BISHAN"], "score": [3.61], "score_private": [3.65]})
    resid = pd.DataFrame({"estate": ["BISHAN"], "segment": ["private_resale"], "n": [2697],
                          "resid_raw": [0.0], "resid_shrunk": [0.0], "trust": ["decimal"]})
    out = value_model.value_scores(resid, scores, {"BISHAN"})
    row = out[out["estate"] == "BISHAN"].iloc[0]
    # resid_shrunk=0 -> mult=exp(0)=1.0 -> value_score == base; base must be score_private (3.65).
    assert abs(row["value_score"] - 3.65) < 1e-9


def test_hdb_segment_still_uses_public_score():
    # Guard the converse: HDB segments must keep using the public provision score.
    scores = pd.DataFrame({"estate": ["BISHAN"], "score": [3.61], "score_private": [3.65]})
    resid = pd.DataFrame({"estate": ["BISHAN"], "segment": ["hdb_resale"], "n": [4063],
                          "resid_raw": [0.0], "resid_shrunk": [0.0], "trust": ["decimal"]})
    out = value_model.value_scores(resid, scores, {"BISHAN"})
    row = out[out["estate"] == "BISHAN"].iloc[0]
    assert abs(row["value_score"] - 3.61) < 1e-9
