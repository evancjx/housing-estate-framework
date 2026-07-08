#!/usr/bin/env python3
"""
BCA construction-permit ingester  (Provision v2.0 §1.11)
=========================================================
Per-estate active-construction severity, feeding the D-multiplier
construction-disruption penalty (Task 2.12 — losses-only routing per
the framework invariant).

PROVENANCE: PARTLY_MEASURED (fallback-derived).
  BCA's permit-granularity dataset on data.gov.sg is not at the
  active-permit + GFA + remaining-months level required by the audit
  §B3 severity formula. Per brief Step 2 fallback, we derive severity
  from pipeline_data.json items that are:
    - certainty = CONFIRMED, AND
    - expected_year ∈ [now, now+3], AND
    - type ∈ {PRIVATE_NEW_LAUNCH, EN_BLOC_TENDER, NRP, LUP,
              SERS, MALL_COMMERCIAL, TOWN_CENTRE, HAWKER, POLYCLINIC,
              SCHOOL, HOSPITAL}.
  MRT items are excluded — surface disruption is largely complete by
  the time CRL-style projects reach the 'opening within 3y' window.

  GFA is estimated from item type (typical floor-plate sizes); setback
  defaults to 100m absent geometry. Both approximations are documented
  in audit §B3.

SEVERITY FORMULA (audit §B3):
  severity_score = sum_over_items(
    GFA_kSF × remaining_months / max(setback_m, 1)
  )
  where remaining_months = max(0, (expected_year - this_year) × 12).

OUTPUT (data/inputs/bca_permits.csv):
  estate, n_active_permits_500m, total_gfa_active, max_remaining_months,
         severity_score

INPUT CONTRACT:
  --pipeline  data/inputs/pipeline_data.json
  --estates   data/inputs/estates.csv
  --out       output CSV path

RUN:
  python3 models/ingest_bca_permits.py \\
      --pipeline data/inputs/pipeline_data.json \\
      --estates data/inputs/estates.csv \\
      --out data/inputs/bca_permits.csv
"""
import argparse
import json
import sys

import pandas as pd

# GFA estimates per item type (rough; pulled from typical project
# announcements). Units: thousand-sq-ft (kSF).
TYPE_GFA_KSF = {
    "PRIVATE_NEW_LAUNCH": 600,    # typical ~500-unit condo footprint
    "EN_BLOC_TENDER":     500,    # similar
    "NRP":                400,    # neighbourhood renewal precinct
    "LUP":                150,    # lift upgrading block-cluster
    "SERS":              1200,    # SERS = total block redevelopment
    "MALL_COMMERCIAL":   1500,    # mall/office build-out
    "TOWN_CENTRE":       2000,    # town centre redevelopment
    "HAWKER":              80,    # standalone hawker centre
    "POLYCLINIC":         300,
    "SCHOOL":             350,
    "HOSPITAL":          1800,
}
CONSTRUCTION_TYPES = set(TYPE_GFA_KSF)
DEFAULT_SETBACK_M = 100  # absent geometry, treat as moderate-distance


def derive_severity(pipeline_items, this_year):
    """Per-estate aggregation.
    Returns {estate: {n, total_gfa, max_months, severity}}."""
    by_estate = {}
    for it in pipeline_items:
        if it.get("type") not in CONSTRUCTION_TYPES:
            continue
        if it.get("certainty") != "CONFIRMED":
            continue
        try:
            year = int(it.get("expected_year") or 0)
        except (TypeError, ValueError):
            continue
        if year < this_year or year > this_year + 3:
            continue
        remaining_m = max(0, (year - this_year) * 12)
        gfa = TYPE_GFA_KSF[it["type"]]
        for est in it.get("benefiting_estates", []):
            e = str(est).upper()
            a = by_estate.setdefault(e, {
                "n": 0, "total_gfa": 0, "max_months": 0, "severity": 0.0,
            })
            a["n"] += 1
            a["total_gfa"] += gfa
            a["max_months"] = max(a["max_months"], remaining_m)
            a["severity"] += gfa * remaining_m / DEFAULT_SETBACK_M
    return by_estate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pipeline", required=True)
    ap.add_argument("--estates", default="data/inputs/estates.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--year", type=int, default=2026,
                    help="scoring year for the [now, now+3] window. Default 2026 matches "
                         "liveability_model's scoring year; avoids date.today() non-determinism "
                         "across calendar boundaries (committed bca_permits.csv would otherwise drift).")
    args = ap.parse_args()

    with open(args.pipeline) as f:
        data = json.load(f)
    items = data.get("pipeline_items", [])
    print(f"Loaded {len(items)} pipeline items", file=sys.stderr)

    this_year = args.year
    sev = derive_severity(items, this_year)
    print(f"Estates with active construction: {len(sev)}", file=sys.stderr)

    # Union with master estate list (zero-fill the rest)
    estates_df = pd.read_csv(args.estates)
    rows = []
    for est in estates_df["estate"]:
        e = str(est).upper()
        a = sev.get(e, {"n": 0, "total_gfa": 0, "max_months": 0, "severity": 0.0})
        rows.append({
            "estate": e,
            "n_active_permits_500m": a["n"],
            "total_gfa_active": a["total_gfa"],
            "max_remaining_months": a["max_months"],
            "severity_score": round(a["severity"], 1),
        })

    out_df = pd.DataFrame(rows)[
        ["estate", "n_active_permits_500m", "total_gfa_active",
         "max_remaining_months", "severity_score"]
    ]
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {len(out_df)} rows → {args.out}", file=sys.stderr)

    # Spot-check: which estates have highest construction severity?
    print("\nTop-10 severity:", file=sys.stderr)
    top = out_df.sort_values("severity_score", ascending=False).head(10)
    for _, r in top.iterrows():
        print(f"  {r['estate']:15s}  n={int(r['n_active_permits_500m']):2d}  "
              f"gfa={int(r['total_gfa_active']):5d} kSF  "
              f"sev={r['severity_score']:7.1f}", file=sys.stderr)


if __name__ == "__main__":
    main()
