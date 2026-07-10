"""Validation for the curated data/inputs/project_unit_mix.csv (bedroom<->sqft
ranges used by build_private_bedrooms tier 3). Skips cleanly until the file
exists. Overlapping ranges are a warning (they cost coverage, not correctness)."""

import os
import re
import sys
import warnings

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

from build_private_bedrooms import normalise_project_name  # noqa: E402

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "inputs", "project_unit_mix.csv")
REQUIRED = ["project_name_norm", "postal_district", "bedrooms", "min_sqft",
            "max_sqft", "source_url", "retrieved_date", "note"]

pytestmark = pytest.mark.skipif(not os.path.exists(PATH),
                                reason="project_unit_mix.csv not yet created")


@pytest.fixture(scope="module")
def mix():
    return pd.read_csv(PATH, dtype={"postal_district": str})


def test_schema(mix):
    assert list(mix.columns) == REQUIRED


def test_values(mix):
    assert mix["bedrooms"].between(1, 6).all()
    assert (mix["min_sqft"] >= 200).all()
    assert (mix["min_sqft"] < mix["max_sqft"]).all()
    assert (mix["max_sqft"] <= 20000).all()
    assert mix["source_url"].str.match(r"https?://").all()
    assert mix["retrieved_date"].str.match(r"\d{4}-\d{2}-\d{2}$").all()
    assert mix["postal_district"].str.match(r"^\d{2}$").all()


def test_names_are_normalised_fixed_points(mix):
    for name in mix["project_name_norm"].unique():
        assert normalise_project_name(name) == name, f"not a normalised name: {name!r}"


def test_overlaps_warned_not_failed(mix):
    overlaps = []
    for (proj, district), grp in mix.groupby(["project_name_norm", "postal_district"]):
        rows = grp.sort_values("min_sqft").reset_index(drop=True)
        for i in range(len(rows) - 1):
            if rows.loc[i, "max_sqft"] >= rows.loc[i + 1, "min_sqft"]:
                overlaps.append((proj, district,
                                 int(rows.loc[i, "bedrooms"]), int(rows.loc[i + 1, "bedrooms"])))
    if overlaps:
        warnings.warn(f"overlapping unit-mix ranges (cost coverage, not correctness): {overlaps}")
