"""Capture model outputs so each Phase-1 fix's effect is a reviewable diff.
NOT a frozen golden-master — fixes intentionally change outputs."""
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snapshots")
DATA = os.path.join(os.path.dirname(HERE), "data")


def capture(tag):
    """Copy the committed headline CSVs into snapshots/<tag>/ for later diffing."""
    out = os.path.join(SNAP, tag)
    os.makedirs(out, exist_ok=True)
    captured = {}
    for name in ["value_output.csv", "liveability_matrix.csv", "provision_scores.csv"]:
        src = os.path.join(DATA, name)
        if os.path.exists(src):
            df = pd.read_csv(src)
            df.to_csv(os.path.join(out, name), index=False)
            captured[name] = df
    return captured


def diff(tag_a, tag_b, name):
    a = pd.read_csv(os.path.join(SNAP, tag_a, name))
    b = pd.read_csv(os.path.join(SNAP, tag_b, name))
    merged = a.merge(b, on="estate", suffixes=("_before", "_after"), how="outer")
    return merged
