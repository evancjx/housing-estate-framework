import momentum_model


def test_lowercase_significance_not_silently_zeroed():
    hi = momentum_model.item_contribution(
        {"significance": "HIGH", "certainty": "CONFIRMED", "expected_year": 2028, "type": "POLYCLINIC"})
    lo = momentum_model.item_contribution(
        {"significance": "high", "certainty": "confirmed", "expected_year": 2028, "type": "polyclinic"})
    assert lo == hi and hi > 0


def test_unknown_significance_warns(capsys):
    c = momentum_model.item_contribution(
        {"significance": "ENORMOUS", "certainty": "CONFIRMED", "expected_year": 2028, "type": "MRT"})
    assert c == 0.0
    assert "unknown" in capsys.readouterr().err.lower()
