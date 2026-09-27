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



def test_earlier_capture_is_dated_and_cites_the_capture_commit():
    captured_date, note = batch.CAPTURE_NOTES["pmi_d17_2021-2026.csv"]
    assert captured_date == "2026-06-27"
    assert "61e79a5" in note and "ad719b4" not in note


def _export(*rows):
    frame = pd.DataFrame([{column: "1" for column in batch.RAW_COLUMNS} | row for row in rows],
                         columns=batch.RAW_COLUMNS)
    return frame


def test_capture_comparison_reports_revised_and_added_rows_in_shared_months():
    old_tenure, new_tenure = "999 yrs lease commencing from 1937", "946 yrs lease commencing from 1937"
    earlier = _export(
        {"Project Name": "SHORE", "Sale Date": "Dec-24", "Tenure": old_tenure},
        {"Project Name": "SHORE", "Sale Date": "Jan-25", "Tenure": old_tenure},
        {"Project Name": "BAY", "Sale Date": "Feb-25", "Tenure": "Freehold"},
    )
    later = _export(
        {"Project Name": "SHORE", "Sale Date": "Jan-25", "Tenure": new_tenure},
        {"Project Name": "BAY", "Sale Date": "Feb-25", "Tenure": "Freehold"},
        {"Project Name": "BAY", "Sale Date": "Feb-25", "Tenure": "Freehold", "Floor Level": "06 to 10"},
        {"Project Name": "BAY", "Sale Date": "Mar-25", "Tenure": "Freehold"},
    )
    result = batch.compare_captures(earlier, later)
    assert result["overlap_months"] == ["2025-01", "2025-02"]
    assert result["revised_rows"] == 1
    assert result["unmatched_earlier_rows"] == 0
    assert result["later_only_rows"] == 1
    assert result["revisions"] == [{
        "project_name": "SHORE", "field": "Tenure", "earlier": old_tenure, "later": new_tenure,
        "rows": 1, "sale_months": ["2025-01"],
    }]


def test_zero_row_note_says_when_the_export_was_never_captured():
    missing = batch.zero_row_note(True, "17", batch.EXPECTED)
    assert "D17 executive condominium export was not captured" in missing
    assert "not evidence of no sales" in missing
    fetched = "No rows in the fetched 60-month URA exports; not evidence of no development or no stock."
    assert batch.zero_row_note(True, "18", batch.EXPECTED) == fetched
    assert batch.zero_row_note(False, "17", batch.EXPECTED) == fetched


from pathlib import Path
from models import build_individual_project_profiles as profiles

BATCH = Path(__file__).resolve().parents[1] / "data/runs/regional-property-analysis/2026-09-20"


def test_pasir_ris_facts_are_wired_into_profiles():
    assert profiles.REGIONAL_FACTS["Pasir Ris"] == ["PR-01", "PR-02", "PR-03"]
    assert profiles.OWN_PROJECT_FACTS["PASIR RIS 8"] == "PR-02"


@pytest.mark.skipif(not (BATCH / "scope_crosswalk.csv").exists(), reason="batch not restored locally")
def test_pasir_ris_overrides_do_not_collide():
    import json
    overrides = pd.read_csv(BATCH / "scope_overrides.csv", keep_default_na=False, dtype=str)
    assert overrides.project_name.map(batch.norm).is_unique
    pasir = overrides[overrides.region == "Pasir Ris"]
    crosswalk = pd.read_csv(BATCH / "scope_crosswalk.csv", keep_default_na=False, dtype=str)
    expected = set(crosswalk[crosswalk.source_planning_area.str.upper() == "PASIR RIS"].project_name)
    assert set(pasir.project_name) == expected and len(expected) == 56
    assert set(pasir.scope_status) == {"main"}
    context = json.loads((BATCH / "enrichment/regional_context.json").read_text())
    region = next(r for r in context["regions"] if r["region"] == "Pasir Ris")
    assert [f["id"] for f in region["facts"]] == ["PR-01", "PR-02", "PR-03"]
    assert all(source in context["sources"] for f in region["facts"] for source in f["source_ids"])
