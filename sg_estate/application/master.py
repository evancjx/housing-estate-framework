#!/usr/bin/env python3
"""Join all model outputs into one reproducible master_output.csv.

Left-joins (on canonical UPPERCASE estate) the liveability matrix (the richest
spine) with provision extras, HDB Value, employment, lease, and archetype.
Enforces the X-archetype N/R gate, emits typed nullable values plus explicit
coverage status fields, and fails loudly if a required input is missing.
Private resale Value is published only where that distinct segment is covered.

Also generates data/outputs/life_paths.csv from the liveability matrix persona scores.

RUN:
  python3 -m sg_estate.application.master   # uses data/ defaults
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

from sg_estate.domain.framework import MODEL_VERSION, band_label as _band
from sg_estate.contracts import (
    ARCHETYPES,
    EMPLOYMENT,
    LEASE_RISK,
    LIVEABILITY,
    MASTER_OUTPUT,
    MASTER_PROVISION,
    VALUE,
    ContractError,
    require_estate_coverage,
)
from sg_estate.paths import INPUT_DIR, OUTPUT_DIR

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
    """Generate data/outputs/life_paths.csv from liveability_matrix persona scores.

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
                "model_version": MODEL_VERSION,
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


def _load(path, name, contract):
    if not path or not os.path.exists(path):
        sys.exit(f"build_master: required input '{name}' not found: {path}")
    df = pd.read_csv(path)
    try:
        contract.validate(df, source=path)
    except ContractError as exc:
        sys.exit(f"build_master contract error: {exc}")
    df["estate"] = df["estate"].astype(str).str.strip().str.upper()
    return df


def build(args):
    live = _load(args.liveability, "liveability", LIVEABILITY)
    prov = _load(args.provision, "provision", MASTER_PROVISION)
    vhdb = _load(args.value_hdb, "value_hdb", VALUE)
    emp = _load(args.employment, "employment", EMPLOYMENT)
    lease = _load(args.lease, "lease", LEASE_RISK)
    arch = _load(args.archetypes, "archetypes", ARCHETYPES)

    spine = live["estate"]
    for name, frame in (
        ("provision", prov),
        ("value_hdb", vhdb),
        ("employment", emp),
        ("lease", lease),
        ("archetypes", arch),
    ):
        try:
            require_estate_coverage(spine, frame["estate"], source=name)
        except ContractError as exc:
            sys.exit(f"build_master contract error: {exc}")

    _lp_path = getattr(args, "life_paths", None)
    if _lp_path:
        build_life_paths(live, _lp_path)

    m = live.copy()
    if "archetype" not in m.columns:
        m = m.merge(
            arch[["estate", "archetype"]],
            on="estate",
            how="left",
            validate="one_to_one",
        )
    m = m.merge(prov[["estate", "score_private", "measured_only"]]
                .rename(columns={"score_private": "provision_private"}),
                on="estate", how="left", validate="one_to_one")
    m = m.merge(vhdb[["estate", "value_score", "value_band", "value_basis", "n"]]
                .rename(columns={"value_score": "value_hdb_score", "value_band": "value_hdb_band",
                                 "value_basis": "value_hdb_basis", "n": "value_hdb_n"}),
                on="estate", how="left", validate="one_to_one")
    m = m.merge(emp[["estate", "emp_score", "emp_band", "best_node", "worst_node"]],
                on="estate", how="left", validate="one_to_one")
    m = m.merge(lease[["estate", "lease_score", "lease_band", "source"]]
                .rename(columns={"source": "lease_source"}), on="estate", how="left",
                validate="one_to_one")
    m = m.merge(arch[["estate", "confidence"]].rename(columns={"confidence": "archetype_confidence"}),
                on="estate", how="left", validate="one_to_one")

    # Preserve nullable numeric columns. Human-readable placeholders remain in
    # textual fields, with an explicit status column for machine consumers.
    numeric_columns = [
        "provision_private",
        "value_hdb_score",
        "value_hdb_n",
        "emp_score",
        "lease_score",
    ]
    for column in numeric_columns:
        m[column] = pd.to_numeric(m[column], errors="coerce")

    text_columns = [
        "value_hdb_band",
        "value_hdb_basis",
        "emp_band",
        "best_node",
        "worst_node",
        "lease_band",
        "lease_source",
        "archetype_confidence",
    ]
    for column in text_columns:
        m[column] = m[column].fillna(_NODATA).replace("", _NODATA)

    m["provision_private_status"] = np.where(
        m["provision_private"].notna(), "available", _NODATA
    )
    m["value_hdb_status"] = np.select(
        [
            m["value_hdb_basis"].eq("no_hdb_segment"),
            m["value_hdb_score"].notna(),
        ],
        [_NOTCOV, "available"],
        default=_NODATA,
    )
    m["employment_status"] = np.where(m["emp_score"].notna(), "available", _NODATA)
    m["lease_status"] = np.where(m["lease_score"].notna(), "available", _NODATA)

    # Private Value is segment-specific and value_basis-aware.
    # Estates without direct private data (or flagged no_hdb_segment) stay not_covered.
    m["value_private_band"] = _NOTCOV
    m["value_private_basis"] = _NOTCOV
    m["value_private_score"] = np.nan
    m["value_private_n"] = pd.NA
    m["value_private_status"] = _NOTCOV
    _vp_path = getattr(args, "value_private", None)
    if _vp_path and os.path.exists(_vp_path):
        vp = _load(_vp_path, "value_private", VALUE)
        try:
            require_estate_coverage(spine, vp["estate"], source="value_private")
        except ContractError as exc:
            sys.exit(f"build_master contract error: {exc}")
        # value_output_private.csv holds BOTH segments (the model writes hdb_resale + private_resale).
        # Publish only private resale here; rental remains a distinct universe.
        if "segment" in vp.columns:
            vp = vp[vp["segment"].astype(str) == "private_resale"]
        vp = vp[vp["value_basis"].astype(str) != "no_hdb_segment"]
        if vp["estate"].duplicated().any():
            duplicates = sorted(vp.loc[vp["estate"].duplicated(False), "estate"].unique())
            sys.exit(f"build_master contract error: duplicate private Value estates: {duplicates}")
        vp = vp.set_index("estate")
        for est in vp.index:
            mask = m["estate"] == est
            if mask.any():
                m.loc[mask, "value_private_band"] = str(vp.loc[est, "value_band"])
                m.loc[mask, "value_private_basis"] = str(vp.loc[est, "value_basis"])
                m.loc[mask, "value_private_score"] = float(vp.loc[est, "value_score"])
                m.loc[mask, "value_private_n"] = int(vp.loc[est, "n"])
                m.loc[mask, "value_private_status"] = "available"

    # X-archetype N/R gate: scored fields become N/R for non-residential strategic districts
    xmask = m["archetype"].astype(str).str.upper() == "X"
    nr_numeric = [
        "value_hdb_score",
        "value_hdb_n",
        "emp_score",
        "lease_score",
        "value_private_score",
        "value_private_n",
    ]
    for c in nr_numeric:
        m.loc[xmask, c] = pd.NA
    nr_text = ["value_hdb_band", "value_hdb_basis",
               "emp_band", "best_node", "worst_node",
               "lease_band", "lease_source",
               "value_private_band", "value_private_basis"]
    for c in nr_text:
        m.loc[xmask, c] = _NR
    for c in ["value_hdb_status", "employment_status", "lease_status",
              "value_private_status"]:
        m.loc[xmask, c] = "not_applicable"

    for column in ["provision_private", "value_hdb_score", "emp_score",
                   "lease_score", "value_private_score"]:
        m[column] = pd.to_numeric(m[column], errors="coerce").astype("Float64")
    for column in ["value_hdb_n", "value_private_n"]:
        m[column] = pd.to_numeric(m[column], errors="coerce").astype("Int64")

    m["model_version"] = MODEL_VERSION
    try:
        MASTER_OUTPUT.validate(m, source=args.out)
    except ContractError as exc:
        sys.exit(f"build_master contract error: {exc}")
    m.to_csv(args.out, index=False)
    print(f"build_master: wrote {len(m)} estates x {len(m.columns)} cols -> {args.out}")
    for c in m.columns:
        if set(m[c].dropna().astype(str)) <= {
            _NODATA, _NR, _NOTCOV, "not_applicable", ""
        }:
            print(f"  WARN: column '{c}' is entirely placeholder — check wiring")
    return m


def main():
    ap = argparse.ArgumentParser(description="Join model outputs into master_output.csv")
    ap.add_argument("--liveability", default=str(OUTPUT_DIR / "liveability_matrix.csv"))
    ap.add_argument("--provision", default=str(OUTPUT_DIR / "provision_scores.csv"))
    ap.add_argument("--value_hdb", default=str(OUTPUT_DIR / "value_output.csv"))
    ap.add_argument("--employment", default=str(OUTPUT_DIR / "employment_scores_T0.csv"))
    ap.add_argument("--lease", default=str(OUTPUT_DIR / "lease_risk.csv"))
    ap.add_argument("--archetypes", default=str(INPUT_DIR / "archetype_assignments.csv"))
    ap.add_argument("--value_private", default=str(OUTPUT_DIR / "value_output_private.csv"))
    ap.add_argument("--life_paths", default=str(OUTPUT_DIR / "life_paths.csv"))
    ap.add_argument("--out", default=str(OUTPUT_DIR / "master_output.csv"))
    build(ap.parse_args())


if __name__ == "__main__":
    main()
