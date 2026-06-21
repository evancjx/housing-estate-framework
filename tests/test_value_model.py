import value_model


def test_build_formula_excludes_provision_score(tiny_hdb):
    f = value_model.build_formula(tiny_hdb, ["flat_type", "remaining_lease_years"], "month")
    assert "_score" not in f, "provision score must NOT be a regressor (circularity)"
    assert "C(flat_type)" in f
    assert "remaining_lease_years" in f
    assert "C(month)" in f
    assert f.startswith("_lnpsm ~")
