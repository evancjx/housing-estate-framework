import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
MODELS = os.path.join(ROOT, "models")
DATA = os.path.join(ROOT, "data")

# Match runtime: scripts run with their own dir on sys.path[0].
for p in (MODELS, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def data_dir():
    return DATA


@pytest.fixture
def tiny_scores():
    """Minimal provision scores: estate, score."""
    return pd.DataFrame(
        {"estate": ["BISHAN", "TAMPINES", "TENGAH"], "score": [4.47, 4.00, 2.96]}
    )


@pytest.fixture
def tiny_hdb():
    """Synthetic HDB resale rows with enough variation to fit a regression."""
    rows = []
    base = {"BISHAN": 600000, "TAMPINES": 520000}
    for town, price0 in base.items():
        for i in range(8):
            rows.append(
                {
                    "town": town,
                    "resale_price": price0 + i * 12000,
                    "floor_area_sqm": 90 + (i % 3) * 5,
                    "flat_type": "4 ROOM" if i % 2 == 0 else "5 ROOM",
                    "storey_band": "04 TO 06" if i % 2 == 0 else "10 TO 12",
                    "remaining_lease_years": 80 + (i % 4),
                    "month": "2025-01" if i % 2 == 0 else "2025-02",
                }
            )
    return pd.DataFrame(rows)
