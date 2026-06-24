#!/usr/bin/env python3
# DEFERRED / NOT WIRED: produces a CSV but no Provision component consumes it (no entry in framework_config.PROVISION_WEIGHTS). Placeholder for a future component.
"""
Pedestrian + cycling path ingester  (Provision v2.0 §1.6)
==========================================================
Two CSVs feeding the conn sub-metric refinement (Task 2.9):

  data/walking_routes.csv:
    estate, pct_sheltered_to_mrt, n_covered_linkway_segments_800m,
           provenance_note

  data/cycling_paths.csv:
    estate, dedicated_path_m_within_800m, pcn_continuous_m,
           bike_parks_at_mrt, provenance_note

PROVENANCE: UNFETCHED in this run.
  The required source layers — OneMap walking_routes and
  cycling_path_network themes, plus NParks PCN GeoJSON — all require an
  authenticated OneMap token. Per the brief (Step 1), if no token is
  configured this script writes a deterministic zero-filled stub with
  `provenance_note='unfetched (OneMap token required)'`.

  To upgrade to MEASURED, set ONEMAP_TOKEN in the env, then re-run.
  The score_conn function in provision_model.py must treat
  provenance_note='unfetched' rows as missing inputs and renormalise the
  conn sub-metric weights (not fall back to 0).

AUDIT TRAIL: keeping the stub committed lets every Phase-2 scoring change
exercise the same code path it will use once the token is available, and
documents the gap so the next audit can re-attempt the fetch.

INPUT CONTRACT:
  --estates  CSV with estate, lat, lon (UPPERCASE)
  --out-walking  output CSV path for walking-route stub
  --out-cycling  output CSV path for cycling-path stub

RUN:
  python3 models/ingest_pedestrian_paths.py \\
      --estates data/estates.csv \\
      --out-walking data/walking_routes.csv \\
      --out-cycling data/cycling_paths.csv
"""
import argparse
import os
import sys

import pandas as pd

ONEMAP_TOKEN = os.environ.get("ONEMAP_TOKEN", "")
NOTE_UNFETCHED = "unfetched (OneMap token required)"


def stub_walking(estates: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "estate": str(e).upper(),
        "pct_sheltered_to_mrt": 0.0,
        "n_covered_linkway_segments_800m": 0,
        "provenance_note": NOTE_UNFETCHED,
    } for e in estates["estate"]])


def stub_cycling(estates: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "estate": str(e).upper(),
        "dedicated_path_m_within_800m": 0,
        "pcn_continuous_m": 0,
        "bike_parks_at_mrt": 0,
        "provenance_note": NOTE_UNFETCHED,
    } for e in estates["estate"]])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--out-walking", required=True)
    ap.add_argument("--out-cycling", required=True)
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)

    if not ONEMAP_TOKEN:
        print("ONEMAP_TOKEN not set — writing zero-filled stubs.",
              file=sys.stderr)
        print("  See file header for upgrade path.", file=sys.stderr)
    else:
        # Reserved for future OneMap fetch. Per brief, the token path
        # would query walking_routes + cycling_path_network themes, then
        # buffer-intersect with 800m circles per estate. Out of scope for
        # this audit pass (no token in CI).
        print("ONEMAP_TOKEN set but OneMap fetcher not yet implemented; "
              "writing stubs anyway.", file=sys.stderr)

    walking = stub_walking(estates)
    cycling = stub_cycling(estates)
    walking.to_csv(args.out_walking, index=False)
    cycling.to_csv(args.out_cycling, index=False)
    print(f"Wrote {len(walking)} walking + {len(cycling)} cycling rows",
          file=sys.stderr)


if __name__ == "__main__":
    main()
