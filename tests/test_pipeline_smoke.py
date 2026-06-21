import value_model


def test_fit_segment_runs_and_returns_residuals(tiny_hdb, tiny_scores):
    out = value_model.fit_segment(tiny_hdb, "hdb_resale", tiny_scores)
    assert out is not None
    assert {"estate", "segment", "n", "resid_raw", "resid_shrunk", "trust"} <= set(out.columns)
    # both towns present, each n=8
    assert set(out["estate"]) == {"BISHAN", "TAMPINES"}
    assert (out["n"] == 8).all()


def test_value_scores_produces_bands(tiny_hdb, tiny_scores):
    resid = value_model.fit_segment(tiny_hdb, "hdb_resale", tiny_scores)
    scored = value_model.value_scores(resid, tiny_scores, set(tiny_scores["estate"]))
    assert "value_band" in scored.columns
    assert scored["value_band"].isin(["A", "B+", "B", "C", "D", "F"]).all()
