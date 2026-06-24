#!/usr/bin/env python3
"""
Shared framework constants for the Singapore estate scoring pipeline.

This module is intentionally small and dependency-free. Model files import from
here so framework constants cannot drift between pipeline stages.

NOTE: Alias maps (HDB_TOWN_ALIAS / PIPELINE_ESTATE_ALIAS) are intentionally
NOT here — they live in models/aliases.py as the single source of truth.
See CLAUDE.md "Alias maps are single-sourced in models/aliases.py".
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

# Lower-level provision components. These are the code-level split of the
# nine conceptual components in the framework documents.
PROVISION_WEIGHTS: Dict[str, float] = {
    "conn":           0.14,
    "infra":          0.14,
    "amen":           0.09,
    "green":          0.08,
    "dens":           0.08,
    "sch":            0.07,
    "childcare":      0.05,
    "hlth":           0.04,
    "mom":            0.04,
    "hawker":         0.04,
    "noise":          0.03,
    "air_noise":      0.03,
    "eldercare":      0.03,
    "stewardship":    0.03,
    "air_quality":    0.03,
    "community":      0.02,
    "sport":          0.02,
    "jtc_industrial": 0.02,
    "env":            0.01,
    "flood":          0.01,
}
assert abs(sum(PROVISION_WEIGHTS.values()) - 1.0) < 1e-9

# Private (condo) weight variant — 20 components, condo tilts vs PROVISION_WEIGHTS;
# see frameworks/1-provision-framework.md for rationale.
PROVISION_WEIGHTS_PRIVATE: Dict[str, float] = {
    "conn":           0.11,
    "amen":           0.12,
    "green":          0.07,
    "sch":            0.11,
    "dens":           0.08,
    "hlth":           0.04,
    "mom":            0.04,
    "infra":          0.13,
    "env":            0.02,
    "childcare":      0.05,
    "community":      0.03,
    "sport":          0.01,
    "flood":          0.01,
    "hawker":         0.02,
    "noise":          0.04,
    "air_noise":      0.03,
    "eldercare":      0.02,
    "air_quality":    0.03,
    "jtc_industrial": 0.02,
    "stewardship":    0.02,
}
assert abs(sum(PROVISION_WEIGHTS_PRIVATE.values()) - 1.0) < 1e-9

PROVENANCE: Dict[str, str] = {
    "conn":           "MEASURED",
    "amen":           "MEASURED",
    "green":          "MEASURED",
    "sch":            "MEASURED",
    "hlth":           "MEASURED",
    "infra":          "MEASURED",
    "childcare":      "MEASURED",
    "community":      "MEASURED",
    "sport":          "MEASURED",
    "flood":          "MEASURED",
    "noise":          "MEASURED",
    "air_noise":      "MEASURED",
    "eldercare":      "MEASURED",
    "jtc_industrial": "MEASURED",
    "dens":           "PARTLY_MEASURED",
    "env":            "PARTLY_MEASURED",
    "mom":            "PARTLY_MEASURED",
    "air_quality":    "PARTLY_MEASURED",
    "stewardship":    "PARTLY_MEASURED",
    "hawker":         "JUDGED",
}

# Conceptual S-groups used by persona deltas. Every provision component must
# appear in exactly one group.
S_GROUPS: Dict[str, List[str]] = {
    "S1": ["conn"],
    "S2": ["amen", "community", "hawker"],
    "S3": ["green", "sport"],
    "S4": ["sch", "childcare"],
    "S5": ["dens"],
    "S6": ["hlth", "eldercare"],
    "S7": ["mom"],
    "S8": ["infra", "stewardship"],
    "S9": ["env", "flood", "noise", "air_noise", "air_quality", "jtc_industrial"],
}

PERSONAS = ["YoungFam", "SinglePro", "Retiree", "Lifestyle"]

# Signed deltas are percentage points at the S-group level.
PERSONA_DELTAS: Dict[str, Dict[str, float]] = {
    "S1": {"YoungFam": -7,  "SinglePro": +8,  "Retiree":  -3,  "Lifestyle": +6},
    "S2": {"YoungFam": +1,  "SinglePro": +2,  "Retiree":  +4,  "Lifestyle": +3},
    "S3": {"YoungFam": +4,  "SinglePro": -2,  "Retiree":  +4,  "Lifestyle": -2},
    "S4": {"YoungFam": +7,  "SinglePro": -9,  "Retiree":  -9,  "Lifestyle": -10},
    "S5": {"YoungFam":  0,  "SinglePro": -3,  "Retiree":  +2,  "Lifestyle": +4},
    "S6": {"YoungFam": +1,  "SinglePro": -4,  "Retiree": +12,  "Lifestyle": -6},
    "S7": {"YoungFam": -5,  "SinglePro": +3,  "Retiree":  -5,  "Lifestyle": +2},
    "S8": {"YoungFam": -2,  "SinglePro": +1,  "Retiree":  -2,  "Lifestyle": +1},
    "S9": {"YoungFam": +2,  "SinglePro": +4,  "Retiree":  -3,  "Lifestyle": +2},
}

BAND_EDGES: Sequence[Tuple[float, str]] = (
    (4.5, "A"),
    (4.0, "B+"),
    (3.5, "B"),
    (3.0, "C"),
    (2.5, "D"),
    (0.0, "F"),
)
SOFT_FLOOR = 1.5
BAND_NUMERIC: Dict[str, float] = {
    "A": 5.0,
    "B+": 4.5,
    "B": 4.0,
    "C": 3.0,
    "D": 2.5,
    "F": 1.0,
}


def band_label(score: float, soft_floor: Optional[float] = None) -> str:
    s = max(soft_floor, score) if soft_floor is not None else score
    for edge, label in BAND_EDGES:
        if s >= edge:
            return label
    return "F"


def validate_framework_config() -> None:
    grouped = [component for group in S_GROUPS.values() for component in group]
    if sorted(grouped) != sorted(PROVISION_WEIGHTS):
        raise ValueError("S_GROUPS must cover each provision component exactly once")
    if len(grouped) != len(set(grouped)):
        raise ValueError("S_GROUPS contains duplicate component assignments")
    for group in S_GROUPS:
        if group not in PERSONA_DELTAS:
            raise ValueError(f"Missing persona deltas for {group}")
        missing_personas = set(PERSONAS) - set(PERSONA_DELTAS[group])
        if missing_personas:
            raise ValueError(f"Missing deltas for {group}: {sorted(missing_personas)}")


def build_persona_weights() -> Dict[str, Dict[str, float]]:
    """
    Build persona weight vectors from provision weights plus S-group deltas.

    If a signed delta would make a group negative after the lower-level real-data
    component split, the group is floored at zero and the full vector is
    renormalised. This keeps the model interpretable: a persona can de-emphasise
    a group to zero, but never assign a negative weight to a positive provision.
    """
    validate_framework_config()
    persona_weights: Dict[str, Dict[str, float]] = {}

    for persona in PERSONAS:
        weights = dict(PROVISION_WEIGHTS)
        for s_group, components in S_GROUPS.items():
            delta = PERSONA_DELTAS[s_group][persona] / 100.0
            base_group_weight = sum(PROVISION_WEIGHTS[c] for c in components)
            new_group_weight = max(0.0, base_group_weight + delta)

            for component in components:
                proportion = PROVISION_WEIGHTS[component] / base_group_weight
                weights[component] = new_group_weight * proportion

        total = sum(weights.values())
        persona_weights[persona] = {c: v / total for c, v in weights.items()}

    return persona_weights


validate_framework_config()
