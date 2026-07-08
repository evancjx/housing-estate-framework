#!/usr/bin/env python3
"""
Build segment-specific private Value outputs for condo and landed buyers.

The existing value_model.py can score private resale as one tenure universe.
This sidecar keeps that universe split by property form so buyer-profile
evaluation can compare:

- condo: Apartment / Condominium / Strata private resale
- landed: Terrace House / Semi-Detached House / Detached House / Land resale

Both segments still inherit estate liveability separately in buyer_profile_model;
this file only creates segment-specific Value evidence.

RUN:
    python3 models/private_segment_value_model.py \
        --scores data/outputs/provision_scores.csv \
        --private data/inputs/ura_private.csv \
        --out data/outputs/private_segment_value.csv

INPUT CONTRACT:
  --scores: provision_scores.csv with estate,score,score_private
  --private: URA private resale CSV in value_model.py private_resale schema:
      planning_area, transacted_price, area_sqm, property_type, tenure,
      project_age_years, sale_month, type_of_area

OUTPUT:
  data/outputs/private_segment_value.csv with estate,property_segment,n,value_score,
  value_band,value_basis,trust,reported,mult.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import pandas as pd

import value_model


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONDO_TYPES = {"APARTMENT", "CONDOMINIUM"}
LANDED_TYPES = {"TERRACE HOUSE", "SEMI-DETACHED HOUSE", "DETACHED HOUSE"}


def _norm(value: Any) -> str:
    return str(value).strip().upper()


def filter_private_segment(df: pd.DataFrame, property_segment: str) -> pd.DataFrame:
    """Return URA private rows for a segment: condo or landed."""
    if property_segment not in {"condo", "landed"}:
        raise ValueError("property_segment must be condo or landed")

    prop = df.get("property_type", pd.Series("", index=df.index)).map(_norm)
    area = df.get("type_of_area", pd.Series("", index=df.index)).map(_norm)

    if property_segment == "condo":
        mask = prop.isin(CONDO_TYPES) | (area == "STRATA")
        # Guard against future strata-landed rows being counted as condo.
        mask &= ~prop.isin(LANDED_TYPES)
    else:
        mask = prop.isin(LANDED_TYPES) | (area == "LAND")
    return df[mask].copy()


def score_segment(private_df: pd.DataFrame, scores: pd.DataFrame, property_segment: str) -> pd.DataFrame:
    """Fit existing private_resale Value model on one property segment."""
    seg_df = filter_private_segment(private_df, property_segment)
    if seg_df.empty:
        return pd.DataFrame()

    original_estate_names = set(scores["estate"])
    resid = value_model.fit_segment(seg_df, "private_resale", scores.copy())
    if resid is None or resid.empty:
        return pd.DataFrame()

    valued = value_model.value_scores(resid, scores.copy(), original_estate_names)
    valued = valued.copy()
    valued["property_segment"] = property_segment
    return valued


def build(scores: pd.DataFrame, private_df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for property_segment in ("condo", "landed"):
        scored = score_segment(private_df, scores, property_segment)
        if not scored.empty:
            frames.append(scored)
    if not frames:
        return pd.DataFrame(columns=[
            "estate", "property_segment", "n", "value_score", "value_band",
            "value_basis", "trust", "reported", "mult",
        ])

    out = pd.concat(frames, ignore_index=True)
    keep = [
        "estate", "property_segment", "n", "resid_raw", "resid_shrunk",
        "trust", "value_score", "value_band", "mult", "value_basis", "reported",
    ]
    out = out[[c for c in keep if c in out.columns]].copy()
    out["estate"] = out["estate"].astype(str).str.strip().str.upper()
    out = out.sort_values(["property_segment", "value_score", "estate"], ascending=[True, False, True])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build condo/landed private Value outputs")
    parser.add_argument("--scores", default=os.path.join(ROOT, "data/outputs/provision_scores.csv"))
    parser.add_argument("--private", default=os.path.join(ROOT, "data/inputs/ura_private.csv"))
    parser.add_argument("--out", default=os.path.join(ROOT, "data/outputs/private_segment_value.csv"))
    args = parser.parse_args()

    if not os.path.exists(args.scores):
        sys.exit(f"private_segment_value_model: scores not found: {args.scores}")
    if not os.path.exists(args.private):
        sys.exit(f"private_segment_value_model: private transactions not found: {args.private}")

    scores = value_model.load_scores(args.scores)
    private_df = pd.read_csv(args.private)
    out = build(scores, private_df)
    if out.empty:
        sys.exit("private_segment_value_model: no segment output produced")

    out.to_csv(args.out, index=False)
    print(f"private_segment_value_model: wrote {len(out)} rows -> {args.out}")
    print(out.groupby("property_segment")["estate"].nunique().to_string())


if __name__ == "__main__":
    main()
