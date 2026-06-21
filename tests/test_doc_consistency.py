import provision_model


def test_w_has_17_components():
    assert len(provision_model.W) == 17


def test_provenance_keys_match_w():
    assert set(provision_model.PROVENANCE) == set(provision_model.W)


def test_w_private_same_keys_as_w():
    assert set(provision_model.W_PRIVATE) == set(provision_model.W)
