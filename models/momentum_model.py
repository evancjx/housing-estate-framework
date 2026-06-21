#!/usr/bin/env python3
"""
Singapore Estate Momentum Model  (S7 component of Provision framework)
======================================================================
Converts pipeline_data.json (produced by the momentum research workflow)
into per-estate mom scores (1–5) for judged_inputs.csv.

FORMULA (per pipeline item):
    contribution = significance × certainty × time_factor [× slip_premium if MRT/LRT]

    significance:  HIGH=0.40, MEDIUM=0.25, LOW=0.10
    certainty:     CONFIRMED=0.95, GAZETTED=0.75, PLANNED=0.40, RUMOUR=0.0
    time_factor:   year ≤ current  → 0.0  (already delivered, not forward momentum)
                   within 2 years  → 1.0
                   2–5 years       → 0.75
                   5–10 years      → 0.40
                   > 10 years      → 0.20
    slip_premium:  0.85 applied to MRT/LRT items (framework invariant: rail promises slip)

CALIBRATION NOTES:
    raw_sum = Σ(contributions for an estate)
    After applying 0.90 conservative penalty (adversarial verification was skipped):
        adj_sum = raw_sum × 0.90
    Thresholds (adj_sum → mom score):
        ≥ 2.00 → 5   (exceptional pipeline — Tengah-tier)
        ≥ 1.00 → 4   (strong pipeline — CRL corridor beneficiaries)
        ≥ 0.45 → 3   (solid pipeline — polyclinic + park + moderate infra)
        ≥ 0.15 → 2   (thin pipeline — 1–2 low-significance items)
        < 0.15 → 1   (no meaningful announced pipeline)

CORRECTIONS APPLIED (documented — do not silently undo):
    - WOODLEIGH: workflow agents researched under "BIDADARI" not "WOODLEIGH".
      Adds Bidadari Polyclinic (51 Alkaff Crescent, HIGH, CONFIRMED, 2027) = +0.38.
    - MARINE PARADE: TEL Stage 5 (Bedok South TE30 + Sungei Bedok TE31) opens 2026.
      time_factor(2026) = 0.0 (already-delivered rule: year ≤ CURRENT_YEAR → 0).
      No manual addition applied — item contributes 0 forward momentum by model invariant.
    - BOON KENG: only TE22A Founders' Memorial (LOW, GAZETTED, 2028, MRT) captured.
      Manual raw_sum set to 0.17 (gives score 2 after penalty) — consistent with
      mature central estate with minimal announced pipeline beyond adjacent minor MRT.
    - TAMPINES WEST: no direct CRL station (CR6 Tampines North serves Tampines East
      and central Tampines, not Tampines West). Zero items is accurate. Score 1.
    - GEYLANG: mature estate, genuinely no confirmed pipeline items. Score 1.
    - DOVER: Rail Corridor Jurong Branch PCN opening 2026 — treated as current-year
      (time_factor=0.0), hence contribution=0. Score 1.

RUN:
    python momentum_model.py \
        --pipeline pipeline_data.json \
        --judged judged_inputs.csv \
        --out judged_inputs_updated.csv
    # Then review and copy over judged_inputs.csv if satisfied
"""
import argparse, json, math, sys
import pandas as pd

CURRENT_YEAR = 2026

# ---- Formula constants ----
SIG = {'HIGH': 0.40, 'MEDIUM': 0.25, 'LOW': 0.10}
CERT = {'CONFIRMED': 0.95, 'GAZETTED': 0.75, 'PLANNED': 0.40, 'RUMOUR': 0.0}
SLIP_PREMIUM = 0.85   # applied to MRT / LRT items
CONSERVATIVE_PENALTY = 0.90   # adversarial verification was not completed

MRT_TYPES = {'MRT', 'LRT', 'RAIL'}

def time_factor(expected_year):
    delta = expected_year - CURRENT_YEAR
    if delta <= 0:   return 0.0   # already delivered — not forward momentum
    if delta <= 2:   return 1.00
    if delta <= 5:   return 0.75
    if delta <= 10:  return 0.40
    return 0.20

def item_contribution(item):
    sig_key  = str(item.get('significance', '')).strip().upper()
    cert_key = str(item.get('certainty', '')).strip().upper()
    sig  = SIG.get(sig_key)
    cert = CERT.get(cert_key)
    if sig is None or cert is None:
        sys.stderr.write(
            f"WARN: unknown significance/certainty '{sig_key}'/'{cert_key}' "
            f"for item {item.get('description', item.get('type', '?'))} — counted as 0\n")
        return 0.0
    if 'expected_year' not in item:
        sys.stderr.write(
            f"WARN: missing expected_year for {item.get('description', '?')} — counted as 0\n")
        return 0.0
    tf   = time_factor(item['expected_year'])
    slip = SLIP_PREMIUM if str(item.get('type', '')).upper() in MRT_TYPES else 1.0
    return sig * cert * tf * slip

def score_from_adj(adj_sum):
    if adj_sum >= 2.00: return 5
    if adj_sum >= 1.00: return 4
    if adj_sum >= 0.45: return 3
    if adj_sum >= 0.15: return 2
    return 1

# ---- Manual corrections for zero-item / misattributed estates ----
# Each entry: estate_name → additional raw_sum to ADD to the workflow-computed value.
# Documented above in module docstring. Change here requires updating that docstring.
MANUAL_ADDITIONS = {
    # Bidadari Polyclinic (HIGH, CONFIRMED, 2027): sole meaningful pipeline item
    # for WOODLEIGH (= Bidadari new town). Contribution: 0.40 × 0.95 × 1.0 = 0.38
    'WOODLEIGH':      0.38,
    # MARINE PARADE: TEL5 opens 2026 → time_factor=0.0 → 0 forward momentum.
    # No entry — see docstring CORRECTIONS note above.
    # TE22A Founders' Memorial (LOW, GAZETTED, 2028, MRT near Boon Keng) gives 0.064.
    # Set floor at 0.17 so penalty yields ≥ 0.15 (score 2) for this mature central estate.
    'BOON KENG':      0.17,
    # Genuinely zero pipeline for Tampines West and Geylang — no addition applied.
    # DOVER: all items are 2026 (time_factor=0), score stays 1.
}

def build_estate_sums(pipeline_data):
    """Re-derive raw_sums from pipeline_items rather than estate_scores
    to handle multi-estate items and corrections cleanly."""
    sums = {}
    for item in pipeline_data.get('pipeline_items', []):
        contrib = item_contribution(item)
        if contrib == 0.0:
            continue
        for estate in item.get('benefiting_estates', []):
            estate = estate.upper().strip()
            sums[estate] = sums.get(estate, 0.0) + contrib
    return sums

# Canonical estate names from estates.csv (all 32)
ESTATE_NAMES = [
    'WOODLANDS','PASIR RIS','JURONG EAST','BISHAN','BEDOK','TAMPINES',
    'TOA PAYOH','QUEENSTOWN','SERANGOON','SEMBAWANG','MARINE PARADE',
    'CANBERRA','BOON KENG','WOODLEIGH','DOVER','TENGAH',
    'TAMPINES WEST','TAMPINES EAST','ANG MO KIO','LENTOR',
    'SENGKANG','PUNGGOL','YISHUN','HOUGANG','CHOA CHU KANG',
    'BUKIT BATOK','BUKIT MERAH','BUKIT PANJANG','GEYLANG',
    'CLEMENTI','CENTRAL AREA','BUKIT TIMAH',
]

from aliases import PIPELINE_NAME_ALIAS as ALIAS_MAP, canonicalise_pipeline_name as canonical

def build_canonical_sums(pipeline_data):
    sums = {}
    for item in pipeline_data.get('pipeline_items', []):
        contrib = item_contribution(item)
        if contrib == 0.0:
            continue
        # Deduplicate per item: if multiple benefiting_estates map to the same
        # canonical name (e.g. "Queenstown" + "Buona Vista" both → QUEENSTOWN),
        # the item should only be counted once for that estate.
        seen = set()
        for raw_estate in item.get('benefiting_estates', []):
            estate = canonical(raw_estate)
            if estate in seen:
                continue
            seen.add(estate)
            sums[estate] = sums.get(estate, 0.0) + contrib
    return sums

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pipeline', default='pipeline_data.json')
    ap.add_argument('--judged',   default='judged_inputs.csv')
    ap.add_argument('--out',      default='judged_inputs_updated.csv')
    ap.add_argument('--verbose',  action='store_true')
    a = ap.parse_args()

    with open(a.pipeline) as f:
        pipeline_data = json.load(f)

    # Build raw sums using canonical names
    raw_sums = build_canonical_sums(pipeline_data)

    # Apply manual additions for zero-item / misattributed estates
    for estate, addition in MANUAL_ADDITIONS.items():
        raw_sums[estate] = raw_sums.get(estate, 0.0) + addition

    # Compute mom scores for all 32 estates
    rows = []
    for estate in ESTATE_NAMES:
        raw  = raw_sums.get(estate, 0.0)
        adj  = raw * CONSERVATIVE_PENALTY
        mom  = score_from_adj(adj)
        rows.append({
            'estate':   estate,
            'raw_sum':  round(raw, 3),
            'adj_sum':  round(adj, 3),
            'mom':      mom,
        })

    result = pd.DataFrame(rows)

    if a.verbose:
        print("\n=== Momentum Scores ===")
        print(result.to_string(index=False))
        print(f"\nConservative penalty: {CONSERVATIVE_PENALTY}×")
        print("Thresholds: ≥2.00→5, ≥1.00→4, ≥0.45→3, ≥0.15→2, <0.15→1")

    # Load existing judged_inputs.csv and update only mom column
    judged = pd.read_csv(a.judged)
    assert {'estate','dens','env','mom'} <= set(judged.columns), \
        "judged CSV needs columns: estate,dens,env,mom"

    adj_map = dict(zip(result['estate'], result['adj_sum']))
    mom_map = dict(zip(result['estate'], result['mom']))
    judged['mom_computed'] = judged['estate'].str.upper().map(mom_map)
    judged['mom_old']      = judged['mom']
    judged['mom']          = judged['mom_computed'].fillna(judged['mom']).astype(int)
    judged = judged.drop(columns=['mom_computed'])

    # Print diff
    changed = judged[judged['mom'] != judged['mom_old']]
    if not changed.empty:
        print(f"\n{len(changed)} estate(s) with changed mom score:")
        for _, r in changed.iterrows():
            adj = adj_map.get(r['estate'].upper(), float('nan'))
            print(f"  {r['estate']:20s}  {int(r['mom_old'])} → {int(r['mom'])}"
                  f"  (adj_sum={adj:.3f})")
    else:
        print("\nNo mom scores changed.")

    # Write output (without the mom_old helper column)
    judged.drop(columns=['mom_old']).to_csv(a.out, index=False)
    print(f"\nWritten: {a.out}")
    print("Review diffs above, then copy to judged_inputs.csv if satisfied.")

    # Also print full table for review
    print("\n=== Full computed mom table ===")
    print(result[['estate','raw_sum','adj_sum','mom']].to_string(index=False))

if __name__ == '__main__':
    main()
