#!/usr/bin/env python3
# DEFERRED / NOT WIRED: produces a CSV but no Provision component consumes it (no entry in framework_config.PROVISION_WEIGHTS). Placeholder for a future component.
"""
LTA EV charger ingester  (Provision v2.0 §1.9)
==============================================
Per-estate EV charging coverage, feeding the new ev_charging component
(Task 2.5).

PROVENANCE: UNFETCHED in this run.
  The LTA DataMall EV charger registry requires a free AccountKey
  registration. The HDB Carpark Information dataset referenced in the
  brief (d_ca933a644e55d34fe21f28b8052fac63) is now CarparkAvailability
  (real-time slot count, not the static carpark registry), so the
  per-carpark EV-coverage % is not computable from the open feed alone.

  Per the brief's Step 1 fallback, this script writes a deterministic
  zero-filled CSV with provenance_note='unfetched (LTA AccountKey
  required)'. The score_ev_charging function should treat 'unfetched'
  rows as missing inputs and renormalise (not score them as 1).

  To upgrade: register at datamall2.mytransport.sg, set LTA_ACCOUNT_KEY
  in the env, and extend this script with a paged GET against
  http://datamall2.mytransport.sg/ltaodataservice/EVChargingStations
  (returns ~3500 charger locations as of 2026).

INPUT CONTRACT:
  --estates  CSV with estate, lat, lon (UPPERCASE)
  --out      output CSV path

RUN:
  python3 models/ingest_ev_chargers.py \\
      --estates data/inputs/estates.csv \\
      --out data/inputs/ev_chargers.csv
"""
import argparse
import os
import sys

import pandas as pd

LTA_ACCOUNT_KEY = os.environ.get("LTA_ACCOUNT_KEY", "")
NOTE_UNFETCHED = "unfetched (LTA AccountKey required)"


def stub_rows(estates: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "estate": str(e).upper(),
        "n_chargers_800m": 0,
        "n_fast_chargers_800m": 0,
        "hdb_carpark_ev_coverage_pct": 0.0,
        "nearest_charger_m": -1,
        "provenance_note": NOTE_UNFETCHED,
    } for e in estates["estate"]])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)

    if not LTA_ACCOUNT_KEY:
        print("LTA_ACCOUNT_KEY not set — writing zero-filled stub.",
              file=sys.stderr)
    else:
        # Reserved for future LTA DataMall fetcher.
        print("LTA_ACCOUNT_KEY set but EV fetcher not yet implemented; "
              "writing stub anyway.", file=sys.stderr)

    out_df = stub_rows(estates)
    out_df.to_csv(args.out, index=False)
    print(f"Wrote {len(out_df)} rows → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
