#!/usr/bin/env python3
"""Join all model outputs into one reproducible master_output.csv.

Left-joins (on canonical UPPERCASE estate) the liveability matrix (the richest
spine) with provision extras, HDB Value, employment, lease, and archetype.
Enforces the X-archetype N/R gate, emits explicit coverage flags instead of
blank cells, and fails loudly if a required input is missing. Private Value is
structurally supported but flagged 'not_covered' until Phase 3 ingests it.

RUN:
  python3 models/build_master.py            # uses data/ defaults
"""
import argparse
import os
import sys

import pandas as pd

_NR = "N/R"
_NODATA = "no_data"
_NOTCOV = "not_covered"


def _load(path, name):
    if not path or not os.path.exists(path):
        sys.exit(f"build_master: required input '{name}' not found: {path}")
    df = pd.read_csv(path, keep_default_na=False)  # keep "N/A"/"N/R" strings, not NaN
    df["estate"] = df["estate"].astype(str).str.strip().str.upper()
    return df


def build(args):
    live = _load(args.liveability, "liveability")
    prov = _load(args.provision, "provision")
    vhdb = _load(args.value_hdb, "value_hdb")
    emp = _load(args.employment, "employment")
    lease = _load(args.lease, "lease")
    arch = _load(args.archetypes, "archetypes").drop_duplicates(subset="estate", keep="first")

    m = live.copy()
    if "archetype" not in m.columns:
        m = m.merge(arch[["estate", "archetype"]], on="estate", how="left")
    m = m.merge(prov[["estate", "score_private", "measured_only"]]
                .rename(columns={"score_private": "provision_private"}), on="estate", how="left")
    m = m.merge(vhdb[["estate", "value_score", "value_band", "value_basis", "n"]]
                .rename(columns={"value_score": "value_hdb_score", "value_band": "value_hdb_band",
                                 "value_basis": "value_hdb_basis", "n": "value_hdb_n"}),
                on="estate", how="left")
    m = m.merge(emp[["estate", "emp_score", "emp_band", "best_node", "worst_node"]], on="estate", how="left")
    m = m.merge(lease[["estate", "lease_score", "lease_band", "source"]]
                .rename(columns={"source": "lease_source"}), on="estate", how="left")
    m = m.merge(arch[["estate", "confidence"]].rename(columns={"confidence": "archetype_confidence"}),
                on="estate", how="left")

    # blank merged cells -> explicit no_data flag (string cols and numeric-as-string)
    flag_cols = ["value_hdb_score", "value_hdb_band", "value_hdb_basis", "value_hdb_n",
                 "emp_score", "emp_band", "best_node", "worst_node",
                 "lease_score", "lease_band", "lease_source",
                 "provision_private", "measured_only", "archetype_confidence"]
    for c in flag_cols:
        m[c] = m[c].astype(str).replace("", _NODATA).replace("nan", _NODATA)

    # private Value — regenerated via the fixed value_model (R.3, value_basis-aware).
    # Estates without direct private data (or flagged no_hdb_segment) stay not_covered.
    m["value_private_band"] = _NOTCOV
    m["value_private_basis"] = _NOTCOV
    m["value_private_score"] = _NOTCOV
    m["value_private_n"] = _NOTCOV
    _vp_path = getattr(args, "value_private", None)
    if _vp_path and os.path.exists(_vp_path):
        vp = _load(_vp_path, "value_private")
        vp = vp[vp["value_basis"].astype(str) != "no_hdb_segment"]
        vp = vp.drop_duplicates(subset="estate", keep="first").set_index("estate")
        for est in vp.index:
            mask = m["estate"] == est
            if mask.any():
                m.loc[mask, "value_private_band"] = str(vp.loc[est, "value_band"])
                m.loc[mask, "value_private_basis"] = str(vp.loc[est, "value_basis"])
                m.loc[mask, "value_private_score"] = str(vp.loc[est, "value_score"])
                m.loc[mask, "value_private_n"] = str(vp.loc[est, "n"])

    # X-archetype N/R gate: scored fields become N/R for non-residential strategic districts
    xmask = m["archetype"].astype(str).str.upper() == "X"
    nr_cols = ["value_hdb_score", "value_hdb_band", "value_hdb_basis", "value_hdb_n",
               "emp_score", "emp_band", "best_node", "worst_node",
               "lease_score", "lease_band", "lease_source",
               "value_private_band", "value_private_basis", "value_private_score", "value_private_n"]
    for c in nr_cols:
        m.loc[xmask, c] = _NR

    m.to_csv(args.out, index=False)
    print(f"build_master: wrote {len(m)} estates x {len(m.columns)} cols -> {args.out}")
    for c in m.columns:
        if set(m[c].astype(str)) <= {_NODATA, _NR, _NOTCOV, ""}:
            print(f"  WARN: column '{c}' is entirely placeholder — check wiring")
    return m


def main():
    # __file__-relative so it works from any cwd (matches lease_risk_model.py)
    D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    ap = argparse.ArgumentParser(description="Join model outputs into master_output.csv")
    ap.add_argument("--liveability", default=f"{D}/liveability_matrix.csv")
    ap.add_argument("--provision", default=f"{D}/provision_scores.csv")
    ap.add_argument("--value_hdb", default=f"{D}/value_output.csv")
    ap.add_argument("--employment", default=f"{D}/employment_scores_T0.csv")
    ap.add_argument("--lease", default=f"{D}/lease_risk.csv")
    ap.add_argument("--archetypes", default=f"{D}/archetype_assignments.csv")
    ap.add_argument("--value_private", default=f"{D}/value_output_private.csv")
    ap.add_argument("--out", default=f"{D}/master_output.csv")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
