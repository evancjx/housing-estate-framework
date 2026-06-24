import os

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


def test_no_current_year_forward_momentum():
    # a 2026 item must contribute 0 forward momentum (year <= CURRENT_YEAR → time_factor=0)
    assert momentum_model.item_contribution(
        {"significance": "HIGH", "certainty": "GAZETTED", "expected_year": 2026, "type": "MRT"}) == 0.0


def test_enbloc_launch_twin_not_double_counted():
    import json
    d = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pipeline_data.json")))
    sums = momentum_model.build_canonical_sums(d)
    assert momentum_model.score_from_adj(sums.get("SERANGOON", 0) * momentum_model.CONSERVATIVE_PENALTY) == 4
    assert momentum_model.score_from_adj(sums.get("JURONG EAST", 0) * momentum_model.CONSERVATIVE_PENALTY) == 4
