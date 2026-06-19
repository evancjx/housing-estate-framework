#!/usr/bin/env python3
"""
Singapore Estate Lease Risk Model
==================================
Computes a standalone lease_risk score per estate based on mean remaining
lease years from HDB resale transactions.

Score rubric:
    >= 85 years  -> 5.0  (A)   new or near-new leases
    >= 75 years  -> 4.0  (B+)
    >= 65 years  -> 3.0  (B)
    >= 55 years  -> 2.0  (C)
    <  55 years  -> 1.0  (D)

Output: data/lease_risk.csv  (estate, mean_lease_years, lease_score, lease_band)

RUN:
    python3 models/lease_risk_model.py
"""
import os, sys
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Estate -> HDB town mapping (estates that are sub-areas of a larger HDB town)
# ---------------------------------------------------------------------------
ESTATE_TOWN_ALIAS = {
    "CANBERRA":      "SEMBAWANG",
    "BOON KENG":     "KALLANG/WHAMPOA",
    "WOODLEIGH":     "TOA PAYOH",
    "DOVER":         "QUEENSTOWN",
    "TAMPINES WEST": "TAMPINES",
    "TAMPINES EAST": "TAMPINES",
}

# Manual overrides: estates with no (or meaningless) HDB resale data
# These are new BTOs or new private estates with ~94-99yr leases remaining
MANUAL_OVERRIDES = {
    "TENGAH":    5.0,   # new BTOs ~2021+, ~94 years remaining
    "CANBERRA":  5.0,   # new BTOs ~2019-2022
    "WOODLEIGH": 5.0,   # Bidadari new BTOs ~2019-2022
    "LENTOR":    5.0,   # new private, 99-yr from 2022+
}

BAND_LABELS = {5: "A", 4: "B+", 3: "B", 2: "C", 1: "D"}


def lease_score(years: float) -> float:
    if years >= 85:
        return 5.0
    if years >= 75:
        return 4.0
    if years >= 65:
        return 3.0
    if years >= 55:
        return 2.0
    return 1.0


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir   = os.path.join(script_dir, "..", "data")
    hdb_path   = os.path.join(data_dir, "hdb_resale.csv")
    out_path   = os.path.join(data_dir, "lease_risk.csv")
    estates_path = os.path.join(data_dir, "estates.csv")

    if not os.path.exists(hdb_path):
        sys.exit(f"ERROR: {hdb_path} not found")

    hdb = pd.read_csv(hdb_path)
    assert {"town", "remaining_lease_years"} <= set(hdb.columns), \
        "hdb_resale.csv must have columns: town, remaining_lease_years"

    # Compute mean remaining lease per HDB town (drop NaN)
    hdb = hdb.dropna(subset=["remaining_lease_years"])
    hdb["town_upper"] = hdb["town"].str.strip().str.upper()
    town_mean = (
        hdb.groupby("town_upper")["remaining_lease_years"]
        .mean()
        .rename("mean_lease_years")
        .reset_index()
        .rename(columns={"town_upper": "town"})
    )

    # Load estate list
    if not os.path.exists(estates_path):
        sys.exit(f"ERROR: {estates_path} not found")
    estates_df = pd.read_csv(estates_path)
    estate_names = estates_df["estate"].str.strip().str.upper().tolist()

    rows = []
    for estate in estate_names:
        # Manual override takes priority
        if estate in MANUAL_OVERRIDES:
            mean_yrs = None
            sc = MANUAL_OVERRIDES[estate]
            source = "manual_override"
        else:
            # Resolve HDB town alias
            town_key = ESTATE_TOWN_ALIAS.get(estate, estate)
            match = town_mean[town_mean["town"] == town_key]
            if match.empty:
                print(f"WARNING: No HDB resale data for '{estate}' (town key: '{town_key}') — marking as NaN")
                mean_yrs = None
                sc = None
                source = "missing"
            else:
                mean_yrs = round(float(match["mean_lease_years"].iloc[0]), 1)
                sc = lease_score(mean_yrs)
                source = "hdb_resale"

        band_label = BAND_LABELS.get(int(sc), "N/A") if sc is not None else "N/A"
        rows.append({
            "estate":           estate,
            "mean_lease_years": mean_yrs,
            "lease_score":      sc,
            "lease_band":       band_label,
            "source":           source,
        })

    result = pd.DataFrame(rows)
    result.to_csv(out_path, index=False)

    # Print summary table sorted by lease_score ascending (worst first)
    printable = result.copy()
    printable["_sort"] = printable["lease_score"].fillna(-1)
    printable = printable.sort_values("_sort").drop(columns="_sort")

    print("\n=== LEASE RISK — sorted worst first ===")
    print(f"{'Estate':<20} {'Mean Yrs':>9} {'Score':>6} {'Band':>5}  Source")
    print("-" * 60)
    for _, r in printable.iterrows():
        mean_str  = f"{r['mean_lease_years']:.1f}" if r["mean_lease_years"] is not None and not pd.isna(r["mean_lease_years"]) else "   N/A"
        score_str = f"{r['lease_score']:.1f}"      if r["lease_score"]  is not None and not pd.isna(r["lease_score"])  else "  N/A"
        print(f"{r['estate']:<20} {mean_str:>9} {score_str:>6} {r['lease_band']:>5}  {r['source']}")

    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
