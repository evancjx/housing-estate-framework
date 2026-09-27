"""Month-windowed raw URA exports for the regional research batch."""

import pandas as pd
import pytest

from models import build_regional_transaction_batch as batch


def _dates(*values):
    return pd.to_datetime(pd.Series(values), format="%b-%y")


def test_window_keeps_only_months_inside_it():
    raw = pd.DataFrame({"x": [1, 2, 3]})
    kept, dates = batch.apply_window(raw, _dates("Sep-21", "Oct-21", "Jan-25"), ("2021-10", "2024-12"))
    assert list(kept.x) == [2]
    assert list(dates.dt.strftime("%Y-%m")) == ["2021-10"]


def test_no_window_keeps_every_row():
    raw = pd.DataFrame({"x": [1, 2]})
    kept, _ = batch.apply_window(raw, _dates("Oct-21", "Sep-26"), None)
    assert list(kept.x) == [1, 2]


def test_boundary_months_are_kept_once():
    raw = pd.DataFrame({"x": [1, 2]})
    old, _ = batch.apply_window(raw, _dates("Dec-24", "Jan-25"), ("2021-10", "2024-12"))
    new, _ = batch.apply_window(raw, _dates("Dec-24", "Jan-25"), ("2025-01", "2026-09"))
    assert list(old.x) == [1] and list(new.x) == [2]


def test_overlapping_windows_are_rejected():
    with pytest.raises(ValueError, match="overlap"):
        batch.check_window_overlap(["pmi_d17_a.csv", "pmi_d17_b.csv"],
                                   {"pmi_d17_a.csv": ("2021-10", "2025-03"), "pmi_d17_b.csv": ("2025-01", "2026-09")})


def test_second_export_without_a_window_is_rejected():
    with pytest.raises(ValueError, match="unwindowed"):
        batch.check_window_overlap(["pmi_d17_a.csv", "pmi_d17_b.csv"], {"pmi_d17_a.csv": ("2021-10", "2024-12")})


def test_adjacent_windows_and_separate_property_groups_pass():
    batch.check_window_overlap(
        ["pmi_d17_a.csv", "pmi_d17_b.csv", "pmi_d17_executive_condo_2021-2026.csv"],
        {"pmi_d17_a.csv": ("2021-10", "2024-12"), "pmi_d17_b.csv": ("2025-01", "2026-09")})


def test_configured_windows_lie_inside_the_ledger():
    batch.check_window_overlap(batch.EXPECTED)
    for name, (start, end) in batch.MONTH_WINDOWS.items():
        assert name in batch.EXPECTED
        assert "2021-10" <= start <= end <= "2026-09"
    assert {"pmi_d17_2021-2026.csv", "pmi_d17_2025-2026.csv"} <= set(batch.EXPECTED)


def test_source_rows_are_physical_lines_before_windowing(tmp_path, monkeypatch):
    name = "pmi_d17_test.csv"
    rows = []
    for sale_date in ("Sep-21", "Oct-21", "Jan-25"):
        row = {column: "1" for column in batch.RAW_COLUMNS}
        row.update({"Project Name": "DEMO", "Sale Date": sale_date, "Postal District": "17",
                    "Property Type": "Condominium", "Tenure": "99 yrs lease commencing from 2010"})
        rows.append(row)
    (tmp_path / "raw" / "ura").mkdir(parents=True)
    pd.DataFrame(rows, columns=batch.RAW_COLUMNS).to_csv(tmp_path / "raw" / "ura" / name, index=False, encoding="utf-8-sig")
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    monkeypatch.setattr(batch, "EXPECTED", [name])
    monkeypatch.setattr(batch, "MONTH_WINDOWS", {name: ("2021-10", "2024-12")})
    raw, manifest = batch.load_raw()
    assert list(raw.source_row) == [3]
    assert manifest[0]["rows"] == 1 and manifest[0]["rows_in_file"] == 3
    assert manifest[0]["month_window"] == ["2021-10", "2024-12"]
