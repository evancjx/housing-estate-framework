#!/usr/bin/env python3
"""
Singapore Estate LIVEABILITY MATRIX (Document 2, v1.0)
=======================================================
Demand-side · person-relative · NON-comparable by design.
Takes provision_scores.csv + pipeline_data.json as inputs; outputs a
4-persona × 2-horizon (T0 / T5) liveability matrix per estate.

PRIMARY OUTPUT:  profile-first band grid (not a ranking).
SECONDARY:       Gap = Liveability_cell − Provision_band (the headline signal).

=== COMPUTED PERSONA WEIGHTS (audit table) ===

Base weights are imported from provision_model.W (17 components); see that file.

v1.3 change: eldercare carved from hlth (0.07→0.04). eldercare joins S6.
v1.2 change: air_noise carved from env (0.05→0.02). air_noise joins S9.

Deltas are applied at the S-group level (9 groups), then distributed to their
constituent 15 components proportionally by base weight.

S-group → 15-component mapping:
  S1 (conn)      → conn                   (base 0.15)
  S8 (infra)     → infra                  (base 0.15)
  S2 (amen)      → amen+community         (base 0.13+0.04=0.17)
  S3 (green)     → green+sport            (base 0.09+0.03=0.12)
  S4 (schools)   → sch+childcare          (base 0.07+0.06=0.13)
  S5 (density)   → dens                   (base 0.08)
  S6 (health)    → hlth+eldercare         (base 0.04+0.03=0.07)
  S7 (momentum)  → mom                    (base 0.05)
  S9 (env)       → env+flood+air_noise    (base 0.02+0.03+0.03=0.08)

Delta table (percentage points, each column sums to 0):
              YoungFam  SinglePro  Retiree  Lifestyle
  S1 conn:       -7        +8        -3        +6
  S2 amen:       +1        +2        +4        +3
  S3 green:      +4        -2        +4        -2
  S4 schools:    +7        -9        -9       -10
  S5 density:     0        -3        +2        +4
  S6 health:     +1        -4       +12        -6
  S7 momentum:   -5        +3        -5        +2
  S8 infra:      -2        +1        -2        +1
  S9 env:        +2        +4        -3        +2

Final normalised weights (computed programmatically; verify with --debug flag):
After distributing S-group deltas proportionally to constituent components,
each persona weight vector is re-normalised to sum=1.

=== BAND EDGES ===
  A:  score >= 4.5
  B+: score >= 4.0
  B:  score >= 3.5
  C:  score >= 3.0
  D:  score >= 2.5
  F:  score <  2.5
  Soft floor: Final(a) >= 1.5 regardless.

=== D MULTIPLIER (disruption-only, floor 0.70) ===
D(a) = max(0.70, 1 - Σ(severity × certainty × time_factor))
severity:   moderate=0.10, major=0.20, structural=0.30
certainty:  confirmed=1.0, gazetted=0.75, planned=0.40, rumour=0.0
time_factor: 0-2yr=1.0, 2-5yr=0.75, 5-10yr=0.40, >10yr=0.20

=== C VETO RULES (Doc 3 §5.1) ===
Rule 1: conn==1 AND infra<=2     → Universal cap <= C (score <= 3.49)
Rule 2: amen==1                  → Universal cap <= C
Rule 3: hlth==1                  → Retiree cap <= C; Universal cap <= B (score <= 4.49)
Rule 4: sch==1                   → Young-family cap <= C only
Rule 5: >=2 of {conn,amen,hlth,infra}==1 simultaneously → Universal cap <= D (score <= 2.99)
Rule 6: green, dens, mom==1      → No automatic cap
Conflict: most restrictive wins.
Soft floor: 1.5 regardless.

=== T5 HORIZON (items with expected_year <= 2031, CONFIRMED or GAZETTED only) ===
Items already open (expected_year <= 2026) have contribution=0, skip them.
delta = boost_magnitude × certainty_factor × time_factor_t5
certainty_factor:  CONFIRMED=1.0, GAZETTED=0.85
time_factor_t5:    2027-2028 → 1.0, 2029-2031 → 0.75
T5_component = min(5.0, T0_component + total_delta)

=== T15 HORIZON (items with expected_year <= 2041, CONFIRMED/GAZETTED/PLANNED) ===
Items already open (expected_year <= 2026) have contribution=0, skip them.
delta = boost_magnitude × certainty_factor × time_factor_t15
certainty_factor:  CONFIRMED=1.0, GAZETTED=0.85, PLANNED=0.40 (KEY DIFFERENCE from T5)
time_factor_t15:   2027-2028 → 1.0, 2029-2031 → 0.90, 2032-2036 → 0.75, 2037-2041 → 0.50
T15 D multiplier = 1.00 for ALL estates (all disruptions resolved by 2041)
T15_component = min(5.0, T0_component + total_delta)

Pipeline type → component boosts:
  MRT           → conn: +0.75, infra: +0.75 (if estate infra < 4)
                         conn: +0.25, infra: +0.25 (if estate infra >= 4)
  POLYCLINIC    → hlth: +0.5
  HOSPITAL      → hlth: +0.3
  SCHOOL        → sch:  +0.4
  HAWKER        → amen: +0.2
  MALL_COMMERCIAL → amen: +0.2
  TOWN_CENTRE   → amen: +0.3
  PARK_PCN      → green: +0.15
  SERS          → infra: +0.2
  NRP           → amen: +0.15, infra: +0.10   (v1.4)
  LUP           → infra: +0.10                (v1.4)

=== CLI ===
python liveability_model.py \\
    --scores  SG-Estate-Framework/data/provision_scores.csv \\
    --pipeline SG-Estate-Framework/data/pipeline_data.json \\
    --out     liveability_matrix.csv
"""

import argparse
import json
import sys
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Base provision weights (must mirror provision_model.py W dict exactly)
# ---------------------------------------------------------------------------
from provision_model import W as _PROV_W  # single source of truth (invariant)

BASE_W: Dict[str, float] = dict(_PROV_W)
assert abs(sum(BASE_W.values()) - 1.0) < 1e-9, "BASE_W must sum to 1.0"
assert set(BASE_W) == set(_PROV_W), "BASE_W must mirror provision_model.W exactly"

# S-group → component membership (for proportional delta distribution)
S_GROUPS: Dict[str, list] = {
    "S1": ["conn"],
    "S2": ["amen", "community", "hawker"],
    "S3": ["green", "sport"],
    "S4": ["sch", "childcare"],
    "S5": ["dens"],
    "S6": ["hlth", "eldercare"],
    "S7": ["mom"],
    "S8": ["infra"],
    "S9": ["env", "flood", "air_noise", "noise"],
}

# Persona delta table: S-group → delta in percentage points
# Each column sums to 0; doc-2 §2 values used verbatim.
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

PERSONAS = ["YoungFam", "SinglePro", "Retiree", "Lifestyle"]


def _build_persona_weights() -> Dict[str, Dict[str, float]]:
    """
    Compute final (normalised) 13-component weight vector per persona.

    Steps:
      1. For each S-group, add the persona delta (pp) to the group's base weight sum.
      2. Distribute the new group weight proportionally across constituent components.
      3. Normalise the full 13-component vector to sum=1.0.
    """
    persona_weights: Dict[str, Dict[str, float]] = {}

    for persona in PERSONAS:
        w = dict(BASE_W)  # start with base weights

        for s_group, components in S_GROUPS.items():
            delta_pp = PERSONA_DELTAS[s_group][persona] / 100.0
            base_group_weight = sum(BASE_W[c] for c in components)
            new_group_weight = base_group_weight + delta_pp

            # Proportional distribution within the group
            for c in components:
                if base_group_weight > 0:
                    proportion = BASE_W[c] / base_group_weight
                else:
                    proportion = 1.0 / len(components)
                w[c] = new_group_weight * proportion

        # Normalise to sum=1
        total = sum(w.values())
        persona_weights[persona] = {c: v / total for c, v in w.items()}

    return persona_weights


PERSONA_WEIGHTS = _build_persona_weights()

# ---------------------------------------------------------------------------
# 2. D Multiplier — computed from pipeline_data.json construction_disruptions
# ---------------------------------------------------------------------------
# Formula: D(a) = max(0.70, 1 - Σ(severity × certainty × time_factor))
# severity:   moderate=0.10, major=0.20, structural=0.30
# certainty:  confirmed=1.0, gazetted=0.75, planned=0.40, rumour=0.0
# time_factor: 0-2yr=1.0, 2-5yr=0.75, 5-10yr=0.40, >10yr=0.20
# Only losses/disruptions; positive additions must NOT appear here.
_SEVERITY  = {"moderate": 0.10, "major": 0.20, "structural": 0.30}
_CERTAINTY = {"confirmed": 1.0, "gazetted": 0.75, "planned": 0.40, "rumour": 0.0}
_DEFAULT_D = 1.00


def _time_factor(end_year: int, current_year: int) -> float:
    yrs = end_year - current_year
    if yrs <= 0:  return 0.0   # construction complete — no penalty
    if yrs <= 2:  return 1.0
    if yrs <= 5:  return 0.75
    if yrs <= 10: return 0.40
    return 0.20


def compute_d_multipliers(disruptions: list, current_year: int) -> Dict[str, float]:
    """Compute D multiplier per estate from construction_disruptions list in pipeline JSON."""
    penalties: Dict[str, float] = {}
    for site in disruptions:
        sev    = _SEVERITY.get(site.get("severity", "moderate"), 0.10)
        cert   = _CERTAINTY.get(site.get("certainty", "planned"), 0.40)
        tf     = _time_factor(site.get("end_year", current_year), current_year)
        penalty = sev * cert * tf
        if penalty == 0:
            continue
        for estate in site.get("estates", []):
            e = estate.upper()
            penalties[e] = penalties.get(e, 0.0) + penalty
    return {e: round(max(0.70, 1.0 - p), 4) for e, p in penalties.items()}


def get_d(estate: str, horizon: str = "T0",
          d_t0: Optional[Dict[str, float]] = None,
          d_t5: Optional[Dict[str, float]] = None) -> float:
    """Return D multiplier for an estate at a given horizon."""
    if horizon == "T5":
        return (d_t5 or {}).get(estate.upper(), _DEFAULT_D)
    return (d_t0 or {}).get(estate.upper(), _DEFAULT_D)


# ---------------------------------------------------------------------------
# 3. Alias map — pipeline estate names → provision_scores.csv estate names
# ---------------------------------------------------------------------------
ALIAS_MAP: Dict[str, str] = {
    "BIDADARI":      "WOODLEIGH",
    "MARSILING":     "WOODLANDS",
    "KAKI BUKIT":    "BEDOK",
    "EAST COAST":    "MARINE PARADE",
    "BOON LAY":      "JURONG WEST",    # Boon Lay is the town centre of Jurong West
    "TAMAN JURONG":  "JURONG WEST",
    "BUONA VISTA":   "HOLLAND VILLAGE",
    "NOVENA":        "TOA PAYOH",
    "WEST COAST":    "CLEMENTI",
    "TAMPINES NORTH":"TAMPINES",
    "YEW TEE":       "CHOA CHU KANG",
    # JURONG WEST: now a real estate — removed from alias map
    # KALLANG: now a real estate — removed from alias map
}


def canonicalise_estate(name: str) -> str:
    """Map pipeline estate name to canonical provision_scores.csv estate name."""
    u = name.strip().upper()
    return ALIAS_MAP.get(u, u)


# ---------------------------------------------------------------------------
# 4. Band classification
# ---------------------------------------------------------------------------
BAND_EDGES = [
    (4.5, "A"),
    (4.0, "B+"),
    (3.5, "B"),
    (3.0, "C"),
    (2.5, "D"),
]
SOFT_FLOOR = 1.5

# Band → numeric for gap computation (A=5, B+=4.5, B=4, C=3, D=2.5, F=1)
BAND_NUMERIC: Dict[str, float] = {
    "A": 5.0, "B+": 4.5, "B": 4.0, "C": 3.0, "D": 2.5, "F": 1.0,
}
CAP_A   = None    # no cap
CAP_B   = 3.99    # <= B means band B or lower → score must be < 4.0 (below B+ threshold)
CAP_C   = 3.49    # <= C means band C or lower → score must be < 3.5 (below B threshold)
CAP_D   = 2.99    # <= D means band D or lower → score must be < 3.0 (below C threshold)

GAP_DEAD_BAND = 0.5  # ~1σ of two ±0.3 inputs combined; below this = "matched"


def gap_label(g: float) -> str:
    if g > GAP_DEAD_BAND:
        return "punches_above"
    if g < -GAP_DEAD_BAND:
        return "over_equipped"
    return "matched"


def band(score: float) -> str:
    """Convert numeric score to band label. Applies soft floor 1.5."""
    s = max(SOFT_FLOOR, score)
    for threshold, label in BAND_EDGES:
        if s >= threshold:
            return label
    return "F"


def apply_cap(score: float, cap_score: Optional[float]) -> float:
    """Apply a score ceiling if a veto cap is active."""
    if cap_score is None:
        return score
    return min(score, cap_score)


# ---------------------------------------------------------------------------
# 5. C Veto rules (Doc 3 §5.1)
# ---------------------------------------------------------------------------
def veto_cap(
    components: Dict[str, float],
    persona: str
) -> Optional[float]:
    """
    Returns the most restrictive score cap for this estate × persona,
    or None if no veto applies.

    Rules (most restrictive cap wins):
      Rule 1: conn==1 AND infra<=2 → Universal cap <= C (3.49)
      Rule 2: amen==1              → Universal cap <= C (3.49)
      Rule 3: hlth==1              → Retiree cap <= C (3.49); Universal cap <= B (4.49)
      Rule 4: sch==1               → YoungFam cap <= C (3.49) only
      Rule 5: >=2 of {conn,amen,hlth,infra}==1 simultaneously → Universal cap <= D (2.99)
      Rule 6: green/dens/mom==1    → No cap
    Conflict: most restrictive (lowest cap) wins.
    """
    conn  = components.get("conn",  5)
    amen  = components.get("amen",  5)
    hlth  = components.get("hlth",  5)
    infra = components.get("infra", 5)
    sch   = components.get("sch",   5)

    caps = []

    # Rule 5 (check first — it can be the most restrictive)
    critical_count = sum(1 for v in [conn, amen, hlth, infra] if v == 1)
    if critical_count >= 2:
        caps.append(CAP_D)  # 2.99

    # Rule 1
    if conn == 1 and infra <= 2:
        caps.append(CAP_C)  # 3.49

    # Rule 2
    if amen == 1:
        caps.append(CAP_C)

    # Rule 3
    if hlth == 1:
        if persona == "Retiree":
            caps.append(CAP_C)
        else:
            caps.append(CAP_B)  # 4.49

    # Rule 4
    if sch == 1 and persona == "YoungFam":
        caps.append(CAP_C)

    return min(caps) if caps else None


# ---------------------------------------------------------------------------
# 6. T5 pipeline boosting
# ---------------------------------------------------------------------------
T5_CUTOFF_YEAR = 2031
T5_OPEN_CUTOFF = 2026  # items already open → skip

# ---------------------------------------------------------------------------
# 6b. T15 pipeline boosting constants
# ---------------------------------------------------------------------------
T15_CUTOFF_YEAR = 2041
T15_OPEN_CUTOFF = 2026  # same as T5 — items already open → skip

# Type → component boosts
PIPELINE_BOOSTS: Dict[str, Dict[str, float]] = {
    "MRT":           {},   # handled separately (infra-conditional)
    "POLYCLINIC":    {"hlth": 0.5},
    "HOSPITAL":      {"hlth": 0.3},
    "SCHOOL":        {"sch":  0.4},
    "HAWKER":        {"amen": 0.2},
    "MALL_COMMERCIAL": {"amen": 0.2},
    "TOWN_CENTRE":   {"amen": 0.3},
    "PARK_PCN":      {"green": 0.15},
    "SERS":          {"infra": 0.2},
    # v1.4: HDB upgrading programmes ingested from data.gov.sg (audit §2a).
    # NRP improves precinct common areas + landscape + lifts; LUP is lift-only.
    "NRP":           {"amen": 0.15, "infra": 0.10},
    "LUP":           {"infra": 0.10},
}

CERTAINTY_FACTORS: Dict[str, float] = {
    "CONFIRMED": 1.0,
    "GAZETTED":  0.85,
    "PLANNED":   0.0,   # excluded for T5
    "RUMOUR":    0.0,
}

CERTAINTY_FACTORS_T15: Dict[str, float] = {
    "CONFIRMED": 1.0,
    "GAZETTED":  0.85,
    "PLANNED":   0.40,  # KEY DIFFERENCE: included at 40% for T15
    "RUMOUR":    0.0,
}

def t5_time_factor(year: int) -> float:
    if year <= T5_OPEN_CUTOFF:
        return 0.0  # already open
    if year <= 2028:
        return 1.0
    if year <= T5_CUTOFF_YEAR:
        return 0.75
    return 0.0  # beyond T5 window


def t15_time_factor(year: int) -> float:
    if year <= T15_OPEN_CUTOFF:
        return 0.0  # already open
    if year <= 2028:
        return 1.0
    if year <= 2031:
        return 0.90
    if year <= 2036:
        return 0.75
    if year <= T15_CUTOFF_YEAR:
        return 0.50
    return 0.0  # beyond T15 window (> 2041)


def compute_t5_boosts(
    estate: str,
    pipeline_items: list,
    base_components: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute T5 component deltas from pipeline_data.json items.
    Returns a dict of component → total_boost for this estate.
    """
    boosts: Dict[str, float] = {}

    for item in pipeline_items:
        certainty = item.get("certainty", "RUMOUR").upper()
        cf = CERTAINTY_FACTORS.get(certainty, 0.0)
        if cf == 0.0:
            continue  # PLANNED / RUMOUR excluded from T5

        year = item.get("expected_year", 9999)
        if year <= T5_OPEN_CUTOFF:
            continue  # already open, no future uplift

        if year > T5_CUTOFF_YEAR:
            continue  # beyond T5 window

        tf = t5_time_factor(year)
        if tf == 0.0:
            continue

        # Check if this estate is a beneficiary (using alias map)
        benefiting = [canonicalise_estate(e) for e in item.get("benefiting_estates", [])]
        if estate not in benefiting:
            continue

        item_type = item.get("type", "").upper()
        magnitude = cf * tf

        if item_type == "MRT":
            # Conditional: large boost if estate lacks MRT (infra < 4), marginal otherwise
            if base_components.get("infra", 5) < 4:
                boosts["conn"]  = boosts.get("conn",  0) + 0.75 * magnitude
                boosts["infra"] = boosts.get("infra", 0) + 0.75 * magnitude
            else:
                boosts["conn"]  = boosts.get("conn",  0) + 0.25 * magnitude
                boosts["infra"] = boosts.get("infra", 0) + 0.25 * magnitude
        else:
            component_map = PIPELINE_BOOSTS.get(item_type, {})
            for comp, mag in component_map.items():
                boosts[comp] = boosts.get(comp, 0) + mag * magnitude

    return boosts


def compute_t15_boosts(
    estate: str,
    pipeline_items: list,
    base_components: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute T15 component deltas from pipeline_data.json items.
    Includes PLANNED items at 40% certainty (unlike T5 which excludes them).
    Returns a dict of component → total_boost for this estate.
    """
    boosts: Dict[str, float] = {}

    for item in pipeline_items:
        certainty = item.get("certainty", "RUMOUR").upper()
        cf = CERTAINTY_FACTORS_T15.get(certainty, 0.0)
        if cf == 0.0:
            continue  # RUMOUR excluded from T15

        year = item.get("expected_year", 9999)
        if year <= T15_OPEN_CUTOFF:
            continue  # already open, no future uplift

        if year > T15_CUTOFF_YEAR:
            continue  # beyond T15 window (> 2041)

        tf = t15_time_factor(year)
        if tf == 0.0:
            continue

        # Check if this estate is a beneficiary (using alias map)
        benefiting = [canonicalise_estate(e) for e in item.get("benefiting_estates", [])]
        if estate not in benefiting:
            continue

        item_type = item.get("type", "").upper()
        magnitude = cf * tf

        if item_type == "MRT":
            # Conditional: large boost if estate lacks MRT (infra < 4), marginal otherwise
            if base_components.get("infra", 5) < 4:
                boosts["conn"]  = boosts.get("conn",  0) + 0.75 * magnitude
                boosts["infra"] = boosts.get("infra", 0) + 0.75 * magnitude
            else:
                boosts["conn"]  = boosts.get("conn",  0) + 0.25 * magnitude
                boosts["infra"] = boosts.get("infra", 0) + 0.25 * magnitude
        else:
            component_map = PIPELINE_BOOSTS.get(item_type, {})
            for comp, mag in component_map.items():
                boosts[comp] = boosts.get(comp, 0) + mag * magnitude

    return boosts


def apply_t5_boosts(
    base: Dict[str, float],
    boosts: Dict[str, float]
) -> Dict[str, float]:
    """Apply T5/T15 boosts to base components, capping each at 5.0."""
    result = dict(base)
    for comp, delta in boosts.items():
        if comp in result:
            result[comp] = min(5.0, result[comp] + delta)
    return result


# ---------------------------------------------------------------------------
# 7. Score computation
# ---------------------------------------------------------------------------
def score_estate(
    components: Dict[str, float],
    persona: str,
    d: float,
) -> float:
    """
    Compute raw liveability score for one estate × persona × horizon.
    Formula: Σ(w_persona(i) × S_i) × D
    Then capped by veto rules (persona-specific).
    Soft floor applied last.
    """
    w = PERSONA_WEIGHTS[persona]
    raw = sum(w[c] * components.get(c, 0.0) for c in w)

    # Veto encodes a STRUCTURAL service failure -> cap the pre-D score so a
    # transient disruption (D<1) cannot mask it.
    cap = veto_cap(components, persona)
    raw = apply_cap(raw, cap)

    raw *= d
    return max(SOFT_FLOOR, raw)


def arrow(t0: float, t5: float) -> str:
    if t5 > t0 + 0.1:
        return "↑"
    if t5 < t0 - 0.1:
        return "↓"
    return "→"


# ---------------------------------------------------------------------------
# 8. Provision band helper (from CSV column)
# ---------------------------------------------------------------------------
def provision_band(score: float) -> str:
    return band(score)


# ---------------------------------------------------------------------------
# 9. Console pretty-print
# ---------------------------------------------------------------------------
def print_matrix(results: pd.DataFrame) -> None:
    """Print readable 4×3 band grid per estate to console (T0 / T5 / T15)."""
    personas_short = {
        "YoungFam":  "YoungFam",
        "SinglePro": "SinglePro",
        "Retiree":   "Retiree ",
        "Lifestyle": "Lifesyle",
    }
    prefix_map = {
        "YoungFam":  "yf",
        "SinglePro": "sp",
        "Retiree":   "ret",
        "Lifestyle": "ls",
    }
    has_t15 = f"yf_T15" in results.columns
    sep = "─" * (88 if has_t15 else 72)

    for _, row in results.iterrows():
        print(sep)
        prov = row.get("provision_band", "?")
        d_val = row.get("D_T0", 1.0)
        print(f"  {row['estate']:<22}  Provision: {prov}   D={d_val:.2f}")
        if has_t15:
            print(f"  {'Persona':<12}  {'T0':>6}  {'T0 Bnd':>6}  {'T5':>6}  {'T5 Bnd':>6}  {'T15':>6}  {'T15 Bnd':>7}  Arrow")
            print(f"  {'─'*12}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*7}  {'─'*5}")
        else:
            print(f"  {'Persona':<12}  {'T0':>6}  {'T0 Band':>7}  {'T5':>6}  {'T5 Band':>7}  Arrow")
            print(f"  {'─'*12}  {'─'*6}  {'─'*7}  {'─'*6}  {'─'*7}  {'─'*5}")
        for p, short in personas_short.items():
            pre = prefix_map[p]
            t0_s = row.get(f"{pre}_T0", 0)
            t5_s = row.get(f"{pre}_T5", 0)
            t0_b = row.get(f"{pre}_T0_band", "?")
            t5_b = row.get(f"{pre}_T5_band", "?")
            arr  = row.get(f"{pre}_T15_arrow", row.get(f"{pre}_arrow", "→"))
            if has_t15:
                t15_s = row.get(f"{pre}_T15", 0)
                t15_b = row.get(f"{pre}_T15_band", "?")
                print(f"  {short:<12}  {t0_s:>6.2f}  {t0_b:>6}  {t5_s:>6.2f}  {t5_b:>6}  {t15_s:>6.2f}  {t15_b:>7}  {arr}")
            else:
                print(f"  {short:<12}  {t0_s:>6.2f}  {t0_b:>7}  {t5_s:>6.2f}  {t5_b:>7}  {arr}")
    print(sep)


# ---------------------------------------------------------------------------
# 10. Main pipeline
# ---------------------------------------------------------------------------
def run(
    scores_path: str,
    pipeline_path: str,
    out_path: str,
    debug: bool = False,
    year: int = 2026,
    archetypes_path: Optional[str] = None,
) -> pd.DataFrame:

    # -- Load provision scores
    df = pd.read_csv(scores_path)
    df["estate"] = df["estate"].str.strip().str.upper()
    required_cols = list(BASE_W.keys()) + ["estate", "score", "band"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        sys.exit(f"provision_scores.csv missing columns: {missing}")

    # -- Load archetype tags (for the X = non-residential N/R gate, invariant 6)
    ARCH: Dict[str, str] = {}
    if archetypes_path and __import__("os").path.exists(archetypes_path):
        adf = pd.read_csv(archetypes_path)
        adf["estate"] = adf["estate"].str.strip().str.upper()
        ARCH = dict(zip(adf["estate"], adf["archetype"].str.strip().str.upper()))

    # -- Load pipeline
    with open(pipeline_path, "r", encoding="utf-8") as f:
        pipeline_data = json.load(f)
    pipeline_items = pipeline_data.get("pipeline_items", [])

    # -- Compute D multipliers dynamically from construction_disruptions
    disruptions = pipeline_data.get("construction_disruptions", [])
    d_t0_map = compute_d_multipliers(disruptions, year)
    d_t5_map = compute_d_multipliers(disruptions, year + 5)

    if debug:
        print("\n=== PERSONA WEIGHTS (normalised) ===")
        header = f"{'Component':<12}" + "".join(f"  {p:<12}" for p in PERSONAS)
        print(header)
        for c in BASE_W:
            row_str = f"{c:<12}"
            for p in PERSONAS:
                row_str += f"  {PERSONA_WEIGHTS[p][c]:.5f}     "
            print(row_str)
        print()

    # -- Compute matrix
    records = []

    for _, row in df.iterrows():
        estate = row["estate"]

        if ARCH.get(estate) == "X":
            nr = {"estate": estate, "archetype": "X", "provision_band": "N/R",
                  "provision_score": float(row.get("score", 0.0)),
                  "D_T0": 1.0, "D_T5": 1.0, "D_T15": 1.0}
            for pre in ["yf", "sp", "ret", "ls"]:
                for hz in ["T0", "T5", "T15"]:
                    nr[f"{pre}_{hz}"] = float("nan")
                    nr[f"{pre}_{hz}_band"] = "N/R"
                nr[f"{pre}_arrow"] = "→"
                nr[f"{pre}_T15_arrow"] = "→"
            records.append(nr)
            continue

        # Build component dict from CSV row
        components_t0: Dict[str, float] = {c: float(row[c]) for c in BASE_W}

        d_t0 = get_d(estate, "T0", d_t0_map, d_t5_map)
        d_t5 = get_d(estate, "T5", d_t0_map, d_t5_map)
        prov_score = float(row["score"])
        prov_band  = provision_band(prov_score)

        # T5 boosts
        boosts_t5 = compute_t5_boosts(estate, pipeline_items, components_t0)
        components_t5 = apply_t5_boosts(components_t0, boosts_t5)

        # T15 boosts (from T0 base, broader certainty and longer window)
        boosts_t15 = compute_t15_boosts(estate, pipeline_items, components_t0)
        components_t15 = apply_t5_boosts(components_t0, boosts_t15)  # reuse apply fn

        # T15 D multiplier: 1.00 for all estates (all disruptions resolved by 2041)
        d_t15 = 1.00

        record: Dict = {
            "estate":          estate,
            "archetype":       ARCH.get(estate, ""),
            "provision_band":  prov_band,
            "provision_score": round(prov_score, 3),
            "D_T0":            d_t0,
            "D_T5":            d_t5,
            "D_T15":           d_t15,
        }

        prefix_map = {
            "YoungFam":  "yf",
            "SinglePro": "sp",
            "Retiree":   "ret",
            "Lifestyle": "ls",
        }

        for persona in PERSONAS:
            pre = prefix_map[persona]

            t0_score  = score_estate(components_t0,  persona, d_t0)
            t5_score  = score_estate(components_t5,  persona, d_t5)
            t15_score = score_estate(components_t15, persona, d_t15)

            record[f"{pre}_T0"]       = round(t0_score,  3)
            record[f"{pre}_T0_band"]  = band(t0_score)
            record[f"{pre}_T5"]       = round(t5_score,  3)
            record[f"{pre}_T5_band"]  = band(t5_score)
            record[f"{pre}_T15"]      = round(t15_score, 3)
            record[f"{pre}_T15_band"] = band(t15_score)
            record[f"{pre}_arrow"]    = arrow(t0_score, t5_score)
            record[f"{pre}_T15_arrow"]= arrow(t0_score, t15_score)

        records.append(record)

    results = pd.DataFrame(records)

    # -- Gap on CONTINUOUS scores (both on the 1-5 scale). Band ladders are non-linear.
    # N/R rows (X-archetype) have float("nan") in score cells; pd.to_numeric coerces
    # them so the subtraction propagates NaN, and gap_label is skipped via pd.notna check.
    prov_score_col = results["provision_score"]
    for pre in ["yf", "sp", "ret", "ls"]:
        for hz in ["T0", "T5", "T15"]:
            live = pd.to_numeric(results[f"{pre}_{hz}"], errors="coerce")
            g = (live - prov_score_col).round(2)
            results[f"gap_{pre}_{hz}"] = g
            results[f"gap_{pre}_{hz}_label"] = g.map(
                lambda x: gap_label(x) if pd.notna(x) else "N/R")

    # -- Save
    results.to_csv(out_path, index=False)
    print(f"Wrote {len(results)} estates → {out_path}")

    # -- Console matrix
    print_matrix(results)

    return results


# ---------------------------------------------------------------------------
# 11. CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="SG Estate Liveability Matrix (Document 2 v1.0)"
    )
    parser.add_argument(
        "--scores",
        default="SG-Estate-Framework/data/provision_scores.csv",
        help="Path to provision_scores.csv (output of provision_model.py)",
    )
    parser.add_argument(
        "--pipeline",
        default="SG-Estate-Framework/data/pipeline_data.json",
        help="Path to pipeline_data.json",
    )
    parser.add_argument(
        "--out",
        default="liveability_matrix.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print computed persona weight table to console",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="Scoring year for D multiplier time decay (default: 2026)",
    )
    parser.add_argument(
        "--archetypes",
        default="SG-Estate-Framework/data/archetype_assignments.csv",
        help="archetype_assignments.csv (X = non-residential N/R gate)",
    )
    args = parser.parse_args()
    run(args.scores, args.pipeline, args.out, debug=args.debug, year=args.year,
        archetypes_path=args.archetypes)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# INPUT CONTRACT
# ---------------------------------------------------------------------------
# provision_scores.csv (output of provision_model.py):
#   Required columns: estate, conn, amen, green, sch, dens, hlth, mom, infra,
#                     env, childcare, community, sport, flood, score, band
#   All component columns: float, range 1.0–5.0
#   score: weighted provision score (float)
#   band:  provision band string (A/B+/B/C/D/F)
#
# pipeline_data.json (pipeline_data.json):
#   Top-level key: "pipeline_items" → list of objects with:
#     description:         str
#     benefiting_estates:  list[str]  (may use alias names — see ALIAS_MAP)
#     type:                str  (MRT | POLYCLINIC | HOSPITAL | SCHOOL | HAWKER |
#                                MALL_COMMERCIAL | TOWN_CENTRE | PARK_PCN | SERS)
#     certainty:           str  (CONFIRMED | GAZETTED | PLANNED | RUMOUR)
#     expected_year:       int
#
# RUN:
#   pip install pandas numpy --break-system-packages
#
#   python SG-Estate-Framework/models/liveability_model.py \
#       --scores   SG-Estate-Framework/data/provision_scores.csv \
#       --pipeline SG-Estate-Framework/data/pipeline_data.json \
#       --out      liveability_matrix.csv
#
#   # To inspect computed persona weights:
#   python SG-Estate-Framework/models/liveability_model.py \
#       --scores   SG-Estate-Framework/data/provision_scores.csv \
#       --pipeline SG-Estate-Framework/data/pipeline_data.json \
#       --out      liveability_matrix.csv \
#       --debug
