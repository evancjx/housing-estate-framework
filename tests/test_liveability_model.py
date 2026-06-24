import os

import pandas as pd
import liveability_model
import provision_model


def test_x_archetype_emits_nr(tmp_path, data_dir):
    out = tmp_path / "lv.csv"
    liveability_model.run(
        scores_path=os.path.join(data_dir, "provision_scores.csv"),
        pipeline_path=os.path.join(data_dir, "pipeline_data.json"),
        out_path=str(out),
        archetypes_path=os.path.join(data_dir, "archetype_assignments.csv"),
    )
    df = pd.read_csv(out)
    ca = df[df["estate"] == "CENTRAL AREA"]
    assert not ca.empty
    assert (ca["yf_T0_band"] == "N/R").all()
    assert (ca["provision_band"] == "N/R").all()


def test_base_w_mirrors_provision_w():
    assert set(liveability_model.BASE_W) == set(provision_model.W)
    for k in provision_model.W:
        assert liveability_model.BASE_W[k] == provision_model.W[k], k


def test_every_base_component_in_an_s_group():
    grouped = {c for comps in liveability_model.S_GROUPS.values() for c in comps}
    assert set(liveability_model.BASE_W) <= grouped, set(liveability_model.BASE_W) - grouped


def test_gap_label_dead_band():
    assert liveability_model.gap_label(0.2) == "matched"
    assert liveability_model.gap_label(0.8) == "punches_above"
    assert liveability_model.gap_label(-0.8) == "over_equipped"
    assert liveability_model.gap_label(0.5) == "matched"   # boundary inclusive


def test_veto_caps_pre_d():
    # amen==1 caps at C (3.49); with strong components raw>cap and D=0.8.
    comps = {c: 5.0 for c in liveability_model.BASE_W}
    comps["amen"] = 1.0
    score = liveability_model.score_estate(comps, "SinglePro", d=0.8)
    # structural cap 3.49 applied BEFORE D -> <= 3.49*0.8 = 2.792 (not 3.49)
    assert score <= 3.49 * 0.8 + 1e-6


def test_nan_component_renormalises_not_floor():
    import numpy as np
    from framework_config import PROVISION_WEIGHTS
    for missing in PROVISION_WEIGHTS:
        comps = {c: 3.5 for c in PROVISION_WEIGHTS}
        comps[missing] = np.nan
        for p in liveability_model.PERSONAS:
            s = liveability_model.score_estate(comps, p, d=1.0)
            assert s > liveability_model.SOFT_FLOOR + 0.5, f"missing {missing} collapsed {p} to {s}"
