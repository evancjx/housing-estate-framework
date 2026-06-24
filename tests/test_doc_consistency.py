import provision_model


def test_w_has_20_components():
    assert len(provision_model.W) == 20


def test_provenance_keys_match_w():
    assert set(provision_model.PROVENANCE) == set(provision_model.W)


def test_w_private_same_keys_as_w():
    assert set(provision_model.W_PRIVATE) == set(provision_model.W)


from collections import Counter


def test_provenance_split_counts():
    c = Counter(provision_model.PROVENANCE.values())
    assert c["MEASURED"] == 14
    assert c["PARTLY_MEASURED"] == 5
    assert c["JUDGED"] == 1


def test_new_v2_components_provenance():
    prov = provision_model.PROVENANCE
    assert prov["jtc_industrial"] == "MEASURED"
    assert prov["air_quality"] == "PARTLY_MEASURED"
    assert prov["stewardship"] == "PARTLY_MEASURED"
    assert prov["hawker"] == "JUDGED"
