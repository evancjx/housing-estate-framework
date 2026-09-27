# Pasir Ris Property Analyses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a dated 2026-09-20 analysis for all 56 Pasir Ris planning-area projects, Seastrand
included, by extending the existing regional research batch.

**Architecture:** The batch is restored from its committed archive into the git-ignored
`data/runs/regional-property-analysis/2026-09-20/`, and a baseline rebuild is recorded first.

The changes are:
- a per-file month window in `build_regional_transaction_batch.py`, so the two D17 exports can
  join the batch without overlapping;
- 56 appended scope overrides and a "Pasir Ris" regional-context entry with facts PR-01 to PR-03,
  both in the batch's data;
- the matching constants in `build_individual_project_profiles.py`.

The four builders then rerun and the archive is repackaged. A guard compares every
pre-existing page with the baseline, and any unexpected change goes to the user before anything is
committed.

**Tech Stack:** Python 3.11+, pandas, pytest; the existing research builders and packaging script.

**Spec:** `docs/superpowers/specs/2026-09-27-pasir-ris-property-analyses-design.md`

## Global Constraints

- Every command reads and writes only inside the repository. Scratch output goes under
  `data/runs/pasir-ris-plan/`, which Git ignores. Never use `/tmp`.
- Pages keep the capture date **2026-09-20**. Page files are `property_analysis/2026-09-20-<slug>.md`.
- No two raw exports may supply the same sale month for the same district and property group.
- Every kept transaction keeps its physical source row: `source_row` is the CSV line number,
  counting the header as line 1.
- `scope_crosswalk.csv` is never edited. Pasir Ris enters only through appended rows in
  `scope_overrides.csv`.
- Facts PR-01 to PR-03 use exactly the claims, statuses and sources written in the spec. Their
  `retrieved` date is `2026-09-27`.
- **Stop rule:** if the guard finds a changed page outside the expected set (Task 4), stop and show
  the user the diff. Do not commit or publish until they decide.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01GQZjKzKc8YhJC4NnJM92BT`.

## Review Focus

1. **A raw file whose window sits partly outside the batch ledger (before 2021-10 or after
   2026-09):** the build must fail, not silently shift the ledger. Tested in Task 2
   (`test_configured_windows_lie_inside_the_ledger`).
2. **A D17 row exactly on a window boundary** (Dec 2024 or Jan 2025) must be kept exactly once.
   Tested in Task 2 (`test_boundary_months_are_kept_once`).
3. **Windowing must not renumber rows:** the kept row's `source_row` is its line in the original
   file. Tested in Task 2 (`test_source_rows_are_physical_lines_before_windowing`).
4. **A crosswalk Pasir Ris name that already has an override row** must fail loudly, not be
   overwritten. Tested in Task 3 (`test_pasir_ris_overrides_do_not_collide`).
5. **Pasir Ris projects not geocoded** (7 of 56) must still get a page, with location recorded as
   missing evidence. Checked in Task 5, Step 2.

---

### Task 1: Restore the batch and record the baseline

No code changes. This task shows that a rebuild with no changes reproduces what is committed, so
the Task 4 guard compares against something trustworthy.

**Files:**
- Local only: `data/runs/regional-property-analysis/2026-09-20/` (restored) and
  `data/runs/pasir-ris-plan/baseline.json`

**Interfaces:**
- Produces: `data/runs/pasir-ris-plan/baseline.json`. It maps
  `{"pages": {filename: sha256}, "archive": {member: sha256}}` for every
  `property_analysis/2026-09-20-*.md` and every member of `data/raw/property_research/2026-09-20.zip`.

- [ ] **Step 1: Restore the batch from the committed archive**

```bash
rm -rf data/runs/regional-property-analysis/2026-09-20
python3 -m zipfile -e data/raw/property_research/2026-09-20.zip data/runs/regional-property-analysis/2026-09-20
ls data/runs/regional-property-analysis/2026-09-20/enrichment/regional_context.json data/runs/regional-property-analysis/2026-09-20/scope_overrides.csv
```

Expected: both files are listed.

- [ ] **Step 2: Record the baseline hashes**

```bash
mkdir -p data/runs/pasir-ris-plan
python3 - <<'EOF'
import hashlib, json, zipfile
from pathlib import Path
pages = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path("property_analysis").glob("2026-09-20-*.md"))}
z = zipfile.ZipFile("data/raw/property_research/2026-09-20.zip")
archive = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith("/")}
Path("data/runs/pasir-ris-plan/baseline.json").write_text(json.dumps({"pages": pages, "archive": archive}, indent=1))
print(len(pages), "pages;", len(archive), "archive members")
EOF
```

Expected: about 557 pages (553 projects, 4 future sites and the directory/regional pages) and
several hundred archive members.

- [ ] **Step 3: Rebuild without changes and check it reproduces the committed pages**

```bash
L=data/runs/pasir-ris-plan && python3 models/build_regional_transaction_batch.py > $L/b1.log 2>&1 && python3 models/build_regional_property_evidence.py > $L/b2.log 2>&1 && python3 models/build_individual_project_profiles.py > $L/b3.log 2>&1 && python3 models/build_individual_property_analyses.py > $L/b4.log 2>&1; echo "exit $?"; git status --short property_analysis | head
```

Expected: `exit 0`, and no changed files under `property_analysis/`.

**If any page changes, stop.** The pipeline is not reproducible as it stands, so the guard would
be meaningless. Report the changed files to the user.

---

### Task 2: Month-windowed raw exports (`build_regional_transaction_batch.py`)

**Files:**
- Modify: `models/build_regional_transaction_batch.py`. This touches `EXPECTED`, `load_raw`, the
  limitations text and `scope_note`.
- Test: `tests/test_regional_transaction_batch.py` (new)

**Interfaces:**
- Produces:
  - `MONTH_WINDOWS: dict[str, tuple[str, str]]`
  - `apply_window(raw: DataFrame, dates: Series, window: tuple[str, str] | None) -> tuple[DataFrame, Series]`
  - `check_window_overlap(names: list[str], windows: dict = MONTH_WINDOWS) -> None`, which raises
    `ValueError`
  - `load_raw()` now drops rows outside a file's window before asserting.

- [ ] **Step 1: Write the failing tests**

`tests/test_regional_transaction_batch.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_regional_transaction_batch.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'apply_window'`.

- [ ] **Step 3: Implement the change**

In `models/build_regional_transaction_batch.py`:

a) Directly after the `EXPECTED += [...executive_condo...]` line, add:

```python
# Pasir Ris (added 2026-09-27) spans D17. Two D17 exports are stitched by month
# so no sale month comes from two files; the older one is an earlier capture.
EXPECTED += ["pmi_d17_2021-2026.csv", "pmi_d17_2025-2026.csv"]
MONTH_WINDOWS = {
    "pmi_d17_2021-2026.csv": ("2021-10", "2024-12"),
    "pmi_d17_2025-2026.csv": ("2025-01", "2026-09"),
}
CAPTURE_NOTES = {
    "pmi_d17_2021-2026.csv": ("earlier repository capture (commit ad719b4)",
                              "Earlier URA PMI export; used for 2021-10 to 2024-12 only"),
    "pmi_d17_2025-2026.csv": ("2026-09-20", "Fresh public URA PMI browser CSV export (PR #39); used for 2025-01 to 2026-09"),
}


def apply_window(raw, dates, window):
    """Keep only rows whose sale month lies inside an inclusive (start, end) YYYY-MM window."""
    if window is None:
        return raw, dates
    months = dates.dt.strftime("%Y-%m")
    keep = months.between(window[0], window[1])
    return raw.loc[keep.values].copy(), dates.loc[keep.values]


def check_window_overlap(names, windows=None):
    """Reject two exports that could supply the same month for one district and property group."""
    windows = MONTH_WINDOWS if windows is None else windows
    groups = {}
    for name in names:
        district = re.search(r"pmi_d(\d+)", name).group(1)
        group = "EC" if "executive" in name else "condo"
        groups.setdefault((district, group), []).append((name, windows.get(name)))
    for key, files in groups.items():
        if len(files) < 2:
            continue
        if any(window is None for _, window in files):
            raise ValueError(f"{key}: an unwindowed export would overlap another export: {[n for n, _ in files]}")
        spans = sorted(window for _, window in files)
        for (start_a, end_a), (start_b, end_b) in zip(spans, spans[1:]):
            if start_b <= end_a:
                raise ValueError(f"{key}: month windows overlap: {start_a}–{end_a} and {start_b}–{end_b}")
```

b) In `load_raw`, replace the block from `assert list(raw.columns) == RAW_COLUMNS` through the end
of the loop body (`parts.append(raw)`) with:

```python
        assert list(raw.columns) == RAW_COLUMNS, (name, raw.columns.tolist())
        rows_in_file = len(raw)
        raw["source_row"] = range(2, len(raw) + 2)  # CSV header is physical line 1; kept before windowing.
        dates = pd.to_datetime(raw["Sale Date"], format="%b-%y", errors="raise")
        window = MONTH_WINDOWS.get(name)
        raw, dates = apply_window(raw, dates, window)
        assert len(raw) > 0
        assert dates.min() >= pd.Timestamp("2021-10-01")
        assert dates.max() <= pd.Timestamp("2026-09-01")
        expected_district = int(re.search(r"pmi_d(\d+)", name).group(1))
        assert set(numeric(raw["Postal District"])) == {expected_district}
        expected_types = {"Executive Condominium"} if "executive" in name else {"Apartment", "Condominium"}
        assert set(raw["Property Type"]) <= expected_types
        captured_date, capture_note = CAPTURE_NOTES.get(name, (
            "2026-09-20",
            "Reused same-day full district export from local LakeGarden batch"
            if expected_district == 22 and "executive" not in name else "Fresh public URA PMI browser CSV export"))
        signatures = raw.drop(columns=["source_row"])
        manifest.append({
            "file": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "encoding": encoding, "rows": len(raw), "rows_in_file": rows_in_file,
            "month_window": list(window) if window else None,
            "distinct_public_signatures": len(signatures.drop_duplicates()),
            "repeated_signature_occurrences_retained": int(signatures.duplicated().sum()),
            "district": expected_district, "property_group": "EC" if "executive" in name else "Apartments/condominiums",
            "first_sale_month": dates.min().strftime("%Y-%m"), "last_sale_month": dates.max().strftime("%Y-%m"),
            "captured_date": captured_date, "source_url": URL, "capture_note": capture_note,
        })
        raw["source_file"] = name
        raw["sale_month"] = dates.dt.strftime("%Y-%m")
        raw["key"] = raw["Project Name"].map(norm)
        parts.append(raw)
```

At the top of `load_raw`, before `parts, manifest = [], []`, add `check_window_overlap(EXPECTED)`.

c) In the limitations list, replace
`"The wider Sembawang context is separate from the five requested regions.`
with
`"The wider Sembawang context is separate from the six requested regions (Pasir Ris added 2026-09-27; its pre-2025 D17 rows come from an earlier capture).`.
Keep the rest of that string unchanged.

d) In `scope_note`, replace
`"Tampines and Bedok recorded planning areas; Canberra precinct;` with
`"Tampines, Bedok and Pasir Ris recorded planning areas; Canberra precinct;`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_regional_transaction_batch.py -q`
Expected: 8 passed.

**Why a test for unchanged manifests:** the old manifest counted distinct signatures over columns
that did not include `source_row`, because `source_row` was added later. The new code drops
`source_row` before counting, so the counts for unwindowed files are unchanged. Task 4's guard
confirms this through `provenance.json`.

- [ ] **Step 5: Copy the D17 exports into the batch and commit the code**

```bash
cp data/raw/ura/pmi_d17_2021-2026.csv data/raw/ura/pmi_d17_2025-2026.csv data/runs/regional-property-analysis/2026-09-20/raw/ura/
git add models/build_regional_transaction_batch.py tests/test_regional_transaction_batch.py
git commit -m "feat(research): month-window raw exports so D17 can join the regional batch

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GQZjKzKc8YhJC4NnJM92BT"
```

---

### Task 3: Pasir Ris scope, regional facts and profile constants

**Files:**
- Modify: `models/build_individual_project_profiles.py` (`REGIONAL_FACTS` and `OWN_PROJECT_FACTS`)
- Modify: `models/build_regional_property_evidence.py:151` (the register title)
- Batch data, packaged into the archive in Task 4:
  - `data/runs/regional-property-analysis/2026-09-20/scope_overrides.csv` (56 rows appended);
  - `data/runs/regional-property-analysis/2026-09-20/enrichment/regional_context.json` (a region
    and 3 sources added);
  - `enrichment/regional_context.md` (a section appended).
- Test: `tests/test_regional_transaction_batch.py` (append)

**Interfaces:**
- Consumes: the crosswalk columns
  (`project_name, source_planning_area, source_districts, region, subregion, ec_origin, scope_basis, source_reference, scope_status, project_name_normalized, source_project_names, source_property_types, source_file`).
- Produces:
  - `REGIONAL_FACTS["Pasir Ris"] == ["PR-01", "PR-02", "PR-03"]`
  - `OWN_PROJECT_FACTS["PASIR RIS 8"] == "PR-02"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_regional_transaction_batch.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_regional_transaction_batch.py -q -k "pasir"`
Expected: 2 failed, with a `KeyError: 'Pasir Ris'` and a `StopIteration`/assertion failure.

- [ ] **Step 3: Update the profile constants and the register title**

In `models/build_individual_project_profiles.py`, add `"Pasir Ris": ["PR-01", "PR-02", "PR-03"],` as
the last entry of `REGIONAL_FACTS`, and `"PASIR RIS 8": "PR-02",` as the last entry of
`OWN_PROJECT_FACTS`.

In `models/build_regional_property_evidence.py`, change
`Tampines / Bedok / Canberra / Jurong / Bukit Timah` to
`Tampines / Bedok / Canberra / Jurong / Bukit Timah / Pasir Ris`.

- [ ] **Step 4: Append the overrides and the regional context in the batch**

```bash
python3 - <<'EOF'
import json
import pandas as pd
from pathlib import Path
B = Path("data/runs/regional-property-analysis/2026-09-20")
cw = pd.read_csv(B / "scope_crosswalk.csv", keep_default_na=False, dtype=str)
ov = pd.read_csv(B / "scope_overrides.csv", keep_default_na=False, dtype=str)
pr = cw[cw.source_planning_area.str.upper() == "PASIR RIS"].copy()
clash = set(pr.project_name) & set(ov.project_name)
assert not clash, f"override collision: {sorted(clash)}"
pr["region"] = "Pasir Ris"
pr["subregion"] = "Pasir Ris recorded planning area"
pr["scope_status"] = "main"
pr["scope_basis"] = "Pasir Ris planning area added 2026-09-27; URA-recorded planning area Pasir Ris in the audited crosswalk."
pd.concat([ov, pr[ov.columns]], ignore_index=True).to_csv(B / "scope_overrides.csv", index=False, encoding="utf-8")

ctx_path = B / "enrichment/regional_context.json"
ctx = json.loads(ctx_path.read_text())
ctx["sources"].update({
    "lta-pasir-ris-east-2022": {"title": "LTA — Civil contract for Pasir Ris East station (CRL Phase 1), 7 Feb 2022",
        "url": "https://www.lta.gov.sg/content/ltagov/en/newsroom/2022/2/news-releases/LTA_awards_civil_contract_for_design_and_construction.html", "source_as_of": "2022-02-07"},
    "lta-bus-interchanges-2025": {"title": "LTA — Two new bus interchanges to open in April 2025, 3 Apr 2025",
        "url": "https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/4/news-releases/two-new-bus-interchanges-to-open-in-april-2025.html", "source_as_of": "2025-04-03"},
    "ura-mp2025-east": {"title": "URA Master Plan 2025 — East: Transforming Towns for Tomorrow",
        "url": "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/east/transforming-towns-for-tomorrow/", "source_as_of": "2026-09-27"},
})
ctx["regions"].append({
    "region": "Pasir Ris",
    "decision_view": "Separate what Pasir Ris already has (the East-West Line and the integrated transport hub opened in April 2025) from what is still future (Cross Island Line by 2030) or only under study (a Sungei Loyang neighbourhood).",
    "facts": [
        {"id": "PR-01", "title": "Cross Island Line is future provision", "status": "planned; expected 2030",
         "verified_claim": "LTA states that CRL1 is expected to be completed by 2030, with Pasir Ris as its interchange with the East-West Line. Pasir Ris East station on Pasir Ris Drive 1 is expected to begin passenger service in 2030. URA's Master Plan 2025 states that the CRL Punggol Extension will be completed by 2032.",
         "source_ids": ["crl", "lta-pasir-ris-east-2022", "ura-mp2025-east"], "named_projects": [],
         "decision_implication": "A 2030 railway should not be treated as available on a 2026 move-in date; compare today's East-West Line or bus journey.",
         "implication_evidence_class": "analyst inference", "retrieved": "2026-09-27"},
        {"id": "PR-02", "title": "Pasir Ris Integrated Transport Hub is open", "status": "completed; opened 27 April 2025",
         "verified_claim": "The new Pasir Ris Bus Interchange opened on 27 April 2025 within an integrated development with Pasir Ris Mall, adjacent to Pasir Ris MRT station on the East-West Line. The development includes residences, a polyclinic, childcare facilities and a town plaza connected to the EWL and the upcoming CRL interchange.",
         "source_ids": ["lta-bus-interchanges-2025", "ura-mp2025-east"], "named_projects": ["PASIR RIS 8"],
         "decision_implication": "The hub is existing provision; its convenience is already visible in achieved prices near it.",
         "implication_evidence_class": "analyst inference", "retrieved": "2026-09-27"},
        {"id": "PR-03", "title": "Sungei Loyang neighbourhood is only under study", "status": "under study",
         "verified_claim": "URA's Master Plan 2025 states: Plans are being studied for a new neighbourhood near Sungei Loyang.",
         "source_ids": ["ura-mp2025-east"], "named_projects": [],
         "decision_implication": "Treat as a supply watch item, not committed supply or a dated competitor.",
         "implication_evidence_class": "analyst inference", "retrieved": "2026-09-27"},
    ],
    "buyer_decisions": [],
})
ctx_path.write_text(json.dumps(ctx, ensure_ascii=False, indent=2) + "\n")
md = B / "enrichment/regional_context.md"
md.write_text(md.read_text().rstrip() + "\n\n## Pasir Ris (added 2026-09-27)\n\n"
    "- **PR-01 — Cross Island Line (planned; expected 2030).** CRL1 expected by 2030 with a Pasir Ris EWL interchange; Pasir Ris East station on Pasir Ris Drive 1, service expected 2030; CRL Punggol Extension by 2032. Sources: LTA CRL page; LTA 7 Feb 2022; URA MP2025 East.\n"
    "- **PR-02 — Pasir Ris Integrated Transport Hub (completed).** Bus interchange opened 27 April 2025 within Pasir Ris Mall's integrated development (residences, polyclinic, childcare, town plaza), adjacent to Pasir Ris MRT (EWL). Sources: LTA 3 Apr 2025; URA MP2025 East.\n"
    "- **PR-03 — Sungei Loyang neighbourhood (under study).** URA MP2025 East: plans are being studied for a new neighbourhood near Sungei Loyang.\n")
print("overrides:", len(pd.read_csv(B / "scope_overrides.csv")), "| regions:", [r["region"] for r in ctx["regions"]])
EOF
```

Expected: `overrides: 63` (7 existing plus 56), and regions ending with `'Pasir Ris'`.

The spec gave the older D17 window as 2021-06 → 2024-12. The loader's ledger starts at 2021-10, so
the implemented window is 2021-10 → 2024-12. Ledger this as a ruling.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_regional_transaction_batch.py -q`
Expected: 10 passed.

- [ ] **Step 6: Commit the code** (the batch data is packaged and committed in Task 4)

```bash
git add models/build_individual_project_profiles.py models/build_regional_property_evidence.py tests/test_regional_transaction_batch.py
git commit -m "feat(research): add the Pasir Ris region and its primary-source facts

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GQZjKzKc8YhJC4NnJM92BT"
```

---

### Task 4: Rebuild, guard, then package

**Files:**
- Regenerated: `property_analysis/2026-09-20-*.md` and `data/raw/property_research/2026-09-20.zip`
- Local report: `data/runs/pasir-ris-plan/guard.json`

- [ ] **Step 1: Run the four builders**

```bash
L=data/runs/pasir-ris-plan && python3 models/build_regional_transaction_batch.py > $L/r1.log 2>&1 && python3 models/build_regional_property_evidence.py > $L/r2.log 2>&1 && python3 models/build_individual_project_profiles.py > $L/r3.log 2>&1 && python3 models/build_individual_property_analyses.py > $L/r4.log 2>&1; echo "exit $?"; tail -3 $L/r4.log
```

Expected: `exit 0`.

- [ ] **Step 2: Run the guard**

```bash
python3 - <<'EOF'
import hashlib, json, pandas as pd
from pathlib import Path
base = json.loads(Path("data/runs/pasir-ris-plan/baseline.json").read_text())["pages"]
now = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path("property_analysis").glob("2026-09-20-*.md")}
scope = pd.read_csv("data/runs/regional-property-analysis/2026-09-20/project_scope.csv", keep_default_na=False, dtype=str)
manifest = json.loads(Path("data/runs/regional-property-analysis/2026-09-20/individual_report_manifest.json").read_text())
text = json.dumps(manifest)
pasir = {n for n in scope[scope.region == "Pasir Ris"].project_name}
expected_changes = {"2026-09-20-individual-project-analyses.md", "2026-09-20-regional-condo-and-ec-comparison.md",
                    "2026-09-20-regional-project-evidence-register.md"}
added = sorted(set(now) - set(base))
changed = sorted(n for n in base if n in now and now[n] != base[n])
removed = sorted(set(base) - set(now))
unexpected = [n for n in changed if n not in expected_changes]
report = {"added": added, "changed": changed, "unexpected_changes": unexpected, "removed": removed}
Path("data/runs/pasir-ris-plan/guard.json").write_text(json.dumps(report, indent=1))
print(f"added {len(added)} | changed {len(changed)} | unexpected {len(unexpected)} | removed {len(removed)}")
print("unexpected:", unexpected[:20])
EOF
```

Expected: `added` equals the number of Pasir Ris projects that get a page (56, allowing for any
names that already had a page), with `unexpected 0` and `removed 0`.

**Stop rule:** if `unexpected` or `removed` is non-zero, stop. Show the user the list and
`git diff --stat` of those files, plus two representative diffs, and wait for their decision. Do not
package or commit.

If the names of the regional register and comparison pages differ from `expected_changes`, correct
the set to the real filenames. Find them with `grep -l "Regional project evidence register\|regional condo" property_analysis/2026-09-20-*.md`.
Record the correction as a ruling, then re-run the guard.

- [ ] **Step 3: Package the archive**

```bash
python3 scripts/package_property_research.py > data/runs/pasir-ris-plan/pkg.log 2>&1; echo "exit $?"; tail -2 data/runs/pasir-ris-plan/pkg.log
python3 -m zipfile -l data/raw/property_research/2026-09-20.zip | grep -cE "raw/ura/pmi_d17_20(21|25)-2026.csv"
```

Expected: `exit 0` and `2`.

---

### Task 5: Verify and commit

- [ ] **Step 1: Seastrand's page and transaction count**

```bash
python3 - <<'EOF'
import pandas as pd
from pathlib import Path
page = Path("property_analysis/2026-09-20-seastrand.md")
assert page.exists(), "missing Seastrand page"
tx = pd.read_csv("data/runs/regional-property-analysis/2026-09-20/transactions.csv", dtype=str, keep_default_na=False)
print("Seastrand batch rows:", int((tx.project_name == "SEASTRAND").sum()))
print(page.read_text()[:600])
EOF
```

Expected: the page exists, and the batch row count is in line with the 108 raw D18 rows (it can be
lower only where the builder's documented exclusions apply). The page shows PR-01 to PR-03 as
regional context.

- [ ] **Step 2: Every Pasir Ris project has exactly one page; ungeocoded ones say so**

```bash
python3 - <<'EOF'
import json, pandas as pd
from pathlib import Path
scope = pd.read_csv("data/runs/regional-property-analysis/2026-09-20/project_scope.csv", keep_default_na=False, dtype=str)
names = set(scope[scope.region == "Pasir Ris"].project_name)
profiles = json.loads(Path("data/runs/regional-property-analysis/2026-09-20/enrichment/individual_project_profiles.json").read_text())
prof = profiles.get("profiles", profiles)
missing = [n for n in names if n not in prof]
no_loc = [n for n in names if n in prof and any("location" in str(m).lower() for m in prof[n].get("missing_evidence", []))]
print("Pasir Ris projects:", len(names), "| without profile:", missing, "| location missing:", len(no_loc))
EOF
```

Expected: `56`, no project without a profile, and about 7 with location recorded as missing.

- [ ] **Step 3: Test gate and site build**

```bash
make smoke > data/runs/pasir-ris-plan/smoke.log 2>&1; grep -E "passed|failed" data/runs/pasir-ris-plan/smoke.log | tail -1; grep -E "^FAILED" data/runs/pasir-ris-plan/smoke.log
rm -rf data/runs/pages-check && python3 scripts/build_pages_site.py --out data/runs/pages-check 2>&1 | tail -1
grep -c 'href="property-analysis-2026-09-20-seastrand.html"' data/runs/pages-check/property-analyses.html
rm -rf data/runs/pages-check
```

Expected:
- `make smoke` passes, except for the known untracked `data/inputs/bus_*.json` catalog check.
- The site builds.
- The directory contains the Seastrand link (`1`).

- [ ] **Step 4: Commit**

```bash
git add property_analysis/2026-09-20-*.md data/raw/property_research/2026-09-20.zip
git commit -m "data(research): publish Pasir Ris project analyses in the 2026-09-20 batch

Adds 56 Pasir Ris planning-area projects (Seastrand included) through
scope overrides, D17 exports month-windowed with no overlap (pre-2025
from an earlier capture), and primary-source facts PR-01 to PR-03.
Guard: no existing project page changed except the regional pages.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GQZjKzKc8YhJC4NnJM92BT"
```
