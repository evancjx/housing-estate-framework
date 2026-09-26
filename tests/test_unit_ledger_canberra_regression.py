"""Rebuild Canberra Crescent Residences from saved captures and compare with the approved page.

The captures hold third-party unit-level records and stay in Git-ignored data/runs/, so this
test skips on machines (including CI) that do not have them.
"""

import shutil
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from scrapers.unit_ledger import build

REGRESSION = Path(__file__).resolve().parents[1] / "data/runs/unit-ledger-regression/canberra-crescent-residences"
pytestmark = pytest.mark.skipif(not (REGRESSION / "raw" / "ura.json").exists(),
                                reason="local Canberra captures are not present")


def test_rebuild_reproduces_the_348_approved_assignments(tmp_path):
    shutil.copytree(REGRESSION / "raw", tmp_path / "raw")
    meta = build.build_run(tmp_path)
    got = pd.read_csv(tmp_path / "transactions.csv", dtype=str, keep_default_na=False)
    got = got[got.origin == "URA"][["block", "unit", "sale_date", "price"]]
    want = pd.read_csv(REGRESSION / "golden" / "assignments.csv", dtype=str, keep_default_na=False)
    missing = Counter(map(tuple, want.values)) - Counter(map(tuple, got.values))
    extra = Counter(map(tuple, got.values)) - Counter(map(tuple, want.values))
    assert not missing and not extra, f"missing={sorted(missing)[:10]} extra={sorted(extra)[:10]}"
    assert meta["counts"]["ura"] == 348 and meta["counts"]["pre_window"] == 0
    assert meta["counts"]["uniquely_located"] == 189
