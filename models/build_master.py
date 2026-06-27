#!/usr/bin/env python3
"""Join all model outputs into one reproducible master_output.csv.

Left-joins (on canonical UPPERCASE estate) the liveability matrix (the richest
spine) with provision extras, HDB Value, employment, lease, and archetype.
Enforces the X-archetype N/R gate, emits explicit coverage flags instead of
blank cells, and fails loudly if a required input is missing. Private Value is
structurally supported but flagged 'not_covered' until Phase 3 ingests it.

Also generates data/life_paths.csv from the liveability matrix persona scores.

RUN:
  python3 models/build_master.py            # uses data/ defaults
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_config import band_label as _band

_NR = "N/R"
_NODATA = "no_data"
_NOTCOV = "not_covered"

# Maps each life path to (start_persona_prefix, end_persona_prefix) in liveability_matrix.
# start_score = {prefix}_T0, end_score = {prefix}_T5.
# Choices encode the life-stage transition each path represents.
# Source of truth: frameworks/2-liveability-matrix.md §4 (life-paths table).
# Each path reads a START persona at T0 and an END persona at T5 (the diagonal across the matrix).
_LIFE_PATH_MAP = {
    "forming_family":  ("sp",  "yf"),   # couple planning kids: single-pro now → young-family T5
    "settling_single": ("ls",  "sp"),   # career-focused, staying urban: lifestyle now → single-pro T5
    "ageing_in_place": ("ret", "ret"),  # already retired: same persona, will they still cope
    "downsizing":      ("yf",  "ret"),  # empty-nesters: young-family now → retiree T5
    "upgrader":        ("sp",  "ls"),   # trading up: single-pro now → lifestyle/family T5
}


def build_life_paths(live: pd.DataFrame, out_path: str) -> pd.DataFrame:
    """Generate data/life_paths.csv from liveability_matrix persona scores.

    Each estate × 5 life paths. Archetype X estates are excluded.
    Scores are the T0/T5 liveability values for the mapped start/end persona.
    """
    rows = []
    for _, r in live.iterrows():
        estate = str(r["estate"]).strip().upper()
        if str(r.get("archetype", "")).strip().upper() == "X":
            continue
        for path, (p0, p1) in _LIFE_PATH_MAP.items():
            s0_col, s1_col = f"{p0}_T0", f"{p1}_T5"
            try:
                s0 = float(r[s0_col])
                s1 = float(r[s1_col])
            except (KeyError, ValueError, TypeError):
                continue
            if pd.isna(s0) or pd.isna(s1):
                continue
            delta = round(s1 - s0, 3)
            arrow = "↑" if delta > 0.1 else ("↓" if delta < -0.1 else "→")
            rows.append({
                "estate":      estate,
                "path":        path,
                "start_score": round(s0, 3),
                "start_band":  _band(s0),
                "end_score":   round(s1, 3),
                "end_band":    _band(s1),
                "delta":       delta,
                "arrow":       arrow,
                "band_shift":  f"{_band(s0)}→{_band(s1)}",
            })
    lp = pd.DataFrame(rows)
    lp.to_csv(out_path, index=False)
    n_estates = lp["estate"].nunique() if not lp.empty else 0
    print(f"build_life_paths: wrote {len(lp)} rows ({n_estates} estates × 5 paths) -> {out_path}")
    return lp


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

    _lp_path = getattr(args, "life_paths", None)
    if _lp_path:
        build_life_paths(live, _lp_path)

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
        # value_output_private.csv holds BOTH segments (the model writes hdb_resale + private_resale).
        # This column is the PRIVATE-tenure value, so drop the HDB rows — otherwise
        # drop_duplicates(keep="first") would publish the HDB value as "private" (invariant 2).
        if "segment" in vp.columns:
            vp = vp[vp["segment"].astype(str) != "hdb_resale"]
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
    ap.add_argument("--life_paths", default=f"{D}/life_paths.csv")
    ap.add_argument("--out", default=f"{D}/master_output.csv")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
