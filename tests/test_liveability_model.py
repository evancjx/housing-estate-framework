import liveability_model
import provision_model


def test_base_w_mirrors_provision_w():
    assert set(liveability_model.BASE_W) == set(provision_model.W)
    for k in provision_model.W:
        assert liveability_model.BASE_W[k] == provision_model.W[k], k


def test_every_base_component_in_an_s_group():
    grouped = {c for comps in liveability_model.S_GROUPS.values() for c in comps}
    assert set(liveability_model.BASE_W) <= grouped, set(liveability_model.BASE_W) - grouped
