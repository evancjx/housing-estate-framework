"""Contract for merging a fresh HDB resale download into the committed file.

data.gov.sg's "Jan 2017 onwards" resource dropped all of 2022 (verified
2026-09-20: 2021-12 and 2023-01 return rows, 2022-06 returns none, and no
other resource in the collection carries it). A plain replace would delete
26,720 committed transactions, so the refresh merges by month instead.
"""

import pandas as pd

import data_ingest


def _rows(month, town="ANG MO KIO", price=500000, n=1):
    return pd.DataFrame([{
        "town": town,
        "resale_price": price,
        "floor_area_sqm": 90.0,
        "flat_type": "4 ROOM",
        "storey_band": "07-09",
        "remaining_lease_years": 70.0,
        "month": month,
    }] * n)


def test_months_missing_from_the_download_are_preserved():
    existing = pd.concat([_rows("2022-06", n=3), _rows("2023-01", n=2)], ignore_index=True)
    fetched = _rows("2023-01", n=2)

    merged, stats = data_ingest.merge_hdb_resale(existing, fetched)

    assert sorted(merged.month.unique()) == ["2022-06", "2023-01"]
    assert (merged.month == "2022-06").sum() == 3
    assert stats["months_preserved"] == ["2022-06"]


def test_reported_months_take_the_downloaded_rows():
    # A month can gain late registrations, so upstream wins where it reports.
    existing = _rows("2023-01", n=2)
    fetched = _rows("2023-01", price=610000, n=4)

    merged, stats = data_ingest.merge_hdb_resale(existing, fetched)

    assert len(merged) == 4
    assert merged.resale_price.tolist() == [610000] * 4
    assert stats["rows_added"] == 2


def test_new_months_are_appended_in_month_order():
    existing = pd.concat([_rows("2022-06"), _rows("2026-06")], ignore_index=True)
    fetched = pd.concat([_rows("2026-06"), _rows("2026-09"), _rows("2026-07")], ignore_index=True)

    merged, stats = data_ingest.merge_hdb_resale(existing, fetched)

    assert merged.month.tolist() == ["2022-06", "2026-06", "2026-07", "2026-09"]
    assert stats["months_added"] == ["2026-07", "2026-09"]


def test_identical_rows_within_a_month_are_kept_as_separate_sales():
    # Two flats can sell on identical terms in the same month.
    existing = _rows("2023-01", n=1)
    fetched = _rows("2023-01", n=3)

    merged, _ = data_ingest.merge_hdb_resale(existing, fetched)

    assert len(merged) == 3


def test_only_selects_a_single_layer_without_forcing_the_others():
    # Refreshing one layer must not mean re-downloading every layer.
    assert data_ingest.layer_selected("hdb_resale.csv", ["hdb_resale"]) is True
    assert data_ingest.layer_selected("parks.csv", ["hdb_resale"]) is False
    assert data_ingest.layer_selected("parks.csv", []) is True
    assert data_ingest.layer_selected("parks.csv", None) is True


def test_schema_and_dtypes_survive_the_merge():
    existing = _rows("2022-06", n=2)
    fetched = _rows("2026-09", n=2)

    merged, _ = data_ingest.merge_hdb_resale(existing, fetched)

    assert list(merged.columns) == list(existing.columns)
    assert merged.dtypes.astype(str).tolist() == existing.dtypes.astype(str).tolist()
