"""Tests for framework_config.py — Task R.1 gate assertions."""
import sys
import os

# Ensure models/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

import framework_config
import provision_model


def test_validate_framework_config_passes():
    """validate_framework_config() must not raise."""
    framework_config.validate_framework_config()


def test_provision_weights_matches_provision_model_w():
    """PROVISION_WEIGHTS in framework_config must equal provision_model.W exactly."""
    assert framework_config.PROVISION_WEIGHTS == provision_model.W, (
        "framework_config.PROVISION_WEIGHTS and provision_model.W have drifted — "
        "update one to match the other."
    )


def test_s_groups_covers_all_provision_weights():
    """Every provision component must appear in exactly one S_GROUP."""
    grouped = [
        component
        for group in framework_config.S_GROUPS.values()
        for component in group
    ]
    assert set(grouped) == set(framework_config.PROVISION_WEIGHTS), (
        "S_GROUPS does not cover the same set of components as PROVISION_WEIGHTS."
    )


def test_provision_weights_private_sums_to_one():
    """PROVISION_WEIGHTS_PRIVATE must sum to 1.0 within floating-point tolerance."""
    total = sum(framework_config.PROVISION_WEIGHTS_PRIVATE.values())
    assert abs(total - 1.0) < 1e-9, f"PROVISION_WEIGHTS_PRIVATE sums to {total}, expected 1.0"


def test_provision_weights_private_same_keys_as_provision_weights():
    """PROVISION_WEIGHTS_PRIVATE must have the same component keys as PROVISION_WEIGHTS."""
    assert set(framework_config.PROVISION_WEIGHTS_PRIVATE) == set(
        framework_config.PROVISION_WEIGHTS
    ), "PROVISION_WEIGHTS_PRIVATE has different keys than PROVISION_WEIGHTS."


def test_band_label_correct_values():
    """band_label should return correct band for known scores."""
    assert framework_config.band_label(4.5) == "A"
    assert framework_config.band_label(4.0) == "B+"
    assert framework_config.band_label(3.5) == "B"
    assert framework_config.band_label(3.0) == "C"
    assert framework_config.band_label(2.5) == "D"
    assert framework_config.band_label(1.0) == "F"


def test_build_persona_weights_sums_to_one():
    """Each persona's weight vector must sum to 1.0."""
    pw = framework_config.build_persona_weights()
    for persona, weights in pw.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, (
            f"Persona {persona} weights sum to {total}, expected 1.0"
        )


def test_build_persona_weights_same_keys():
    """Each persona weight vector must have same keys as PROVISION_WEIGHTS."""
    pw = framework_config.build_persona_weights()
    expected_keys = set(framework_config.PROVISION_WEIGHTS)
    for persona, weights in pw.items():
        assert set(weights) == expected_keys, (
            f"Persona {persona} weight keys differ from PROVISION_WEIGHTS keys."
        )
