import os

import pandas as pd
import pytest

import build_master


def _write(tmp, name, df):
    p = os.path.join(tmp, name)
    df.to_csv(p, index=False)
    return p


@pytest.fixture
def inputs(tmp_path):
    t = str(tmp_path)
    live = pd.DataFrame({
        "estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
        "archetype": ["B", "X", "D"],
        "provision_band": ["B", "N/R", "B+"],
        "provision_score": [3.63, 4.36, 4.01],
        "D_T0": [1.0, 1.0, 1.0],
        "D_T5": [1.0, 1.0, 1.0],
        "D_T15": [1.0, 1.0, 1.0],
        "yf_T0_band": ["B", "N/R", "B+"],
        "gap_yf_T0": [0.0, None, 0.0],
        "gap_yf_T0_label": ["matched", "N/R", "matched"],
    })
    prov = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                         "score_private": [3.7, 4.4, 4.1], "measured_only": [False, False, False]})
    vhdb = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                         "segment": ["hdb_resale", "hdb_resale", "hdb_resale"],
                         "value_score": [2.73, 3.55, ""], "value_band": ["D", "B", "N/A"],
                         "value_basis": ["direct", "direct", "no_hdb_segment"], "n": [4063, 1815, 0]})
    emp = pd.DataFrame({"estate": ["BISHAN", "HOLLAND VILLAGE"], "emp_score": [3.5, 3.8],
                        "emp_band": ["B", "B"], "best_node": ["cbd", "one_north"], "worst_node": ["changi", "changi"]})
    lease = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                          "lease_score": [4.0, 3.0, 5.0], "lease_band": ["B+", "B", "A"],
                          "source": ["hdb_resale", "hdb_resale", "manual_override"]})
    arch = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                         "archetype": ["B", "X", "D"], "confidence": ["High", "High", "Med"]})
    return dict(liveability=_write(t,"live.csv",live), provision=_write(t,"prov.csv",prov),
                value_hdb=_write(t,"v.csv",vhdb), employment=_write(t,"emp.csv",emp),
                lease=_write(t,"lease.csv",lease), archetypes=_write(t,"arch.csv",arch),
                out=os.path.join(t,"master.csv"))


def _ns(d):
    import argparse
    return argparse.Namespace(**d)


def test_joins_all_models(inputs):
    m = build_master.build(_ns(inputs))
    row = m[m["estate"] == "BISHAN"].iloc[0]
    assert row["emp_band"] == "B"          # employment wired in
    assert row["lease_band"] == "B+"       # lease wired in
    assert row["value_hdb_band"] == "D"    # HDB value wired in
    assert row["archetype"] == "B"
    assert row["value_hdb_status"] == "available"
    assert row["employment_status"] == "available"
    assert pd.api.types.is_float_dtype(m["value_hdb_score"].dtype)


def test_x_archetype_is_nr(inputs):
    m = build_master.build(_ns(inputs))
    ca = m[m["estate"] == "CENTRAL AREA"].iloc[0]
    assert ca["value_hdb_band"] == "N/R"
    assert ca["emp_band"] == "N/R"
    assert ca["lease_band"] == "N/R"
    assert ca["value_hdb_status"] == "not_applicable"
    assert pd.isna(ca["value_hdb_score"])


def test_missing_employment_row_flagged_not_blank(inputs):
    m = build_master.build(_ns(inputs))
    ca = m[m["estate"] == "CENTRAL AREA"].iloc[0]
    # CENTRAL AREA has no employment row; it is X so becomes N/R (not blank)
    assert ca["emp_band"] in ("N/R", "no_data")
    assert ca["emp_band"] != ""


def test_private_value_flagged_not_covered(inputs):
    m = build_master.build(_ns(inputs))
    assert (m["value_private_band"].isin(["not_covered", "N/R"])).all()


def test_private_dominant_keeps_no_hdb_segment(inputs):
    m = build_master.build(_ns(inputs))
    hv = m[m["estate"] == "HOLLAND VILLAGE"].iloc[0]
    assert hv["value_hdb_basis"] == "no_hdb_segment"   # survived keep_default_na=False


def test_missing_required_input_fails_loudly(inputs):
    bad = dict(inputs)
    bad["lease"] = "/nonexistent/lease.csv"
    with pytest.raises(SystemExit):
        build_master.build(_ns(bad))


def test_archetype_coverage_complete():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = os.path.join(here, "data", "inputs")
    est = pd.read_csv(os.path.join(data, "estates.csv"))
    arch = pd.read_csv(os.path.join(data, "archetype_assignments.csv"))
    est_names = set(est["estate"].str.strip().str.upper())
    arch_names = set(arch["estate"].str.strip().str.upper())
    missing = est_names - arch_names
    assert not missing, f"estates with no archetype: {missing}"


def test_real_private_value_surfaces_and_x_gated(inputs, tmp_path):
    # add a private-value file: BISHAN has direct private data; HOLLAND VILLAGE has no_hdb_segment (no direct)
    vp = pd.DataFrame({
        "estate": ["BISHAN", "HOLLAND VILLAGE"],
        "segment": ["private_resale", "private_resale"],
        "value_score": [4.1, ""], "value_band": ["A", "N/A"],
        "value_basis": ["direct", "no_hdb_segment"], "n": [3316, 0],
    })
    d = dict(inputs)
    d["value_private"] = _write(str(tmp_path), "vp.csv", vp)
    m = build_master.build(_ns(d))
    bishan = m[m["estate"] == "BISHAN"].iloc[0]
    assert bishan["value_private_band"] == "A"          # real direct private value surfaced
    assert bishan["value_private_basis"] == "direct"
    hv = m[m["estate"] == "HOLLAND VILLAGE"].iloc[0]
    assert hv["value_private_band"] == "not_covered"    # no_hdb_segment -> not borrowed
    ca = m[m["estate"] == "CENTRAL AREA"].iloc[0]
    assert ca["value_private_band"] == "N/R"            # X-gate applies to private cells


def test_private_value_prefers_private_segment_over_hdb(inputs, tmp_path):
    # value_output_private.csv carries BOTH an hdb_resale and a private_resale row for BISHAN
    # (the value_model --private pass writes both). The published value_private_* must be the
    # PRIVATE row, not the first (HDB) row that drop_duplicates(keep="first") would grab.
    vp = pd.DataFrame({
        "estate":      ["BISHAN", "BISHAN"],
        "segment":     ["hdb_resale", "private_resale"],   # HDB row FIRST — the bug trap
        "value_score": [2.77, 3.30],
        "value_band":  ["D", "C"],
        "value_basis": ["direct", "direct"],
        "n":           [4063, 2697],
    })
    d = dict(inputs)
    d["value_private"] = _write(str(tmp_path), "vp.csv", vp)
    m = build_master.build(_ns(d))
    bishan = m[m["estate"] == "BISHAN"].iloc[0]
    assert bishan["value_private_band"] == "C"          # private segment, not HDB "D"
    assert bishan["value_private_basis"] == "direct"
    assert bishan["value_private_status"] == "available"
    assert bishan["value_private_score"] == pytest.approx(3.30)


def test_duplicate_join_key_fails_contract(inputs, tmp_path):
    duplicate = pd.read_csv(inputs["provision"])
    duplicate = pd.concat([duplicate, duplicate.iloc[[0]]], ignore_index=True)
    changed = dict(inputs)
    changed["provision"] = _write(str(tmp_path), "duplicate-provision.csv", duplicate)
    with pytest.raises(SystemExit, match="duplicate key"):
        build_master.build(_ns(changed))
