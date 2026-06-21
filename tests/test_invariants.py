import value_model
import provision_model


def test_provision_weights_sum_to_one():
    assert abs(sum(provision_model.W.values()) - 1.0) < 1e-9
    assert abs(sum(provision_model.W_PRIVATE.values()) - 1.0) < 1e-9


def test_segments_have_distinct_controls():
    segs = value_model.SEGMENTS
    assert "hdb_resale" in segs and "private_resale" in segs
    # HDB and private must not key on the same geographic column blindly
    assert segs["hdb_resale"]["area_key"] == "town"
    assert segs["private_resale"]["area_key"] == "planning_area"


def test_band_edges_monotonic():
    edges = [e for e, _ in value_model.CFG["band_edges"]]
    assert edges == sorted(edges, reverse=True)
