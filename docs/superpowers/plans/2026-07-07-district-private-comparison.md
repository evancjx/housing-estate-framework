# District-Scoped Private Comparison Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New generator `models/gen_district_private_comparison_html.py` that writes one trend-focused, self-contained HTML comparison page per postal district (starting D17, D27) from a merged 2019–2026 private-transaction dataset.

**Architecture:** One standalone script following the repo's `gen_*_html.py` pattern (docstring INPUT CONTRACT, `ROOT` pathlib constant, pandas load → aggregate → `render_html` → write). Three loaders normalise sources into one unified schema; canonical `ura_private.csv` owns 2021+, EdgeProp scrape and `ura_raw` PMI files contribute **2019–2020 rows only** (strict backfill — no dedup across sources needed). Existing generator `gen_private_project_comparison_html.py` and its test are NOT touched.

**Tech Stack:** Python 3, pandas, stdlib (`argparse`, `pathlib`, `html`, `json`). Vanilla-JS sortable table, zero external assets.

**Spec:** `docs/superpowers/specs/2026-07-07-district-private-comparison-design.md`

## Global Constraints

- Backfill sources (EdgeProp, ura_raw) may only ever emit rows with `sale_year` in **2019–2020**.
- Unified schema columns, exactly: `project, street, property_type, tenure, sale_year, price, area_sqm, psf, sale_type, source`.
- `source` ∈ {`ura_private`, `edgeprop_backfill`, `ura_raw_backfill`}.
- Year-cell threshold: median shown only when that year has **n ≥ 3** txns (constant `MIN_YEAR_N = 3`).
- Growth: `(psf_last / psf_first) ** (1 / (year_last − year_first)) − 1`, between earliest/latest years with n ≥ 3; `None` if < 2 qualifying years.
- Output files: `private_project_comparison_D{NN}.html` at repo root (zero-padded NN).
- HTML pages must be fully self-contained (inline CSS/JS, no external URLs).
- Missing canonical CSV → fail loudly. Missing `ura_raw` landed file → warn and continue.
- Constants: `SQM_TO_SQFT = 10.7639`, `YEARS = list(range(2019, 2027))`.

---

### Task 1: Module skeleton + canonical loader

**Files:**
- Create: `models/gen_district_private_comparison_html.py`
- Create: `tests/test_gen_district_private_comparison.py`

**Interfaces:**
- Produces: `normalise_district(value) -> str` (zero-padded 2-digit string);
  `load_canonical(path: pathlib.Path, district: str) -> pd.DataFrame` (unified schema, all years, source=`ura_private`);
  module constants `ROOT`, `YEARS`, `SQM_TO_SQFT`, `MIN_YEAR_N`, `UNIFIED_COLUMNS`, `DISTRICT_NAMES`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gen_district_private_comparison.py
import pandas as pd
import pytest

import gen_district_private_comparison_html as gen


def _write_canonical(tmp_path):
    df = pd.DataFrame([
        {"planning_area": "SEMBAWANG", "transacted_price": 1_500_000, "area_sqm": 100.0,
         "property_type": "Condominium", "tenure": "99 yrs lease commencing from 2015",
         "project_age_years": 8, "sale_month": "2023-04", "project_name": "THE SHAUGHNESSY",
         "street_name": "MILTONIA CLOSE", "postal_district": "27",
         "market_segment": "Outside Central Region", "floor_level": "01-05",
         "type_of_sale": "Resale", "type_of_area": "Strata", "unit_price_psm": 15_000},
        {"planning_area": "PASIR RIS", "transacted_price": 1_200_000, "area_sqm": 90.0,
         "property_type": "Condominium", "tenure": "Freehold",
         "project_age_years": 20, "sale_month": "2022-01", "project_name": "LOYANG VILLAS",
         "street_name": "LOYANG RISE", "postal_district": "17",
         "market_segment": "Outside Central Region", "floor_level": "-",
         "type_of_sale": "Resale", "type_of_area": "Strata", "unit_price_psm": 13_000},
        {"planning_area": "SEMBAWANG", "transacted_price": 0, "area_sqm": 100.0,
         "property_type": "Condominium", "tenure": "Freehold",
         "project_age_years": 8, "sale_month": "2023-04", "project_name": "BAD ROW",
         "street_name": "X", "postal_district": "27",
         "market_segment": "Outside Central Region", "floor_level": "-",
         "type_of_sale": "Resale", "type_of_area": "Strata", "unit_price_psm": 15_000},
    ])
    path = tmp_path / "ura_private.csv"
    df.to_csv(path, index=False)
    return path


def test_normalise_district():
    assert gen.normalise_district("17") == "17"
    assert gen.normalise_district("7") == "07"
    assert gen.normalise_district(7) == "07"
    assert gen.normalise_district(" 27 ") == "27"


def test_load_canonical_filters_district_and_maps_schema(tmp_path):
    path = _write_canonical(tmp_path)
    out = gen.load_canonical(path, "27")
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert set(out["project"]) == {"THE SHAUGHNESSY"}  # D17 row and zero-price row excluded
    row = out.iloc[0]
    assert row["sale_year"] == 2023
    assert row["source"] == "ura_private"
    assert row["psf"] == pytest.approx(15_000 / gen.SQM_TO_SQFT)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'gen_district_private_comparison_html'`

- [ ] **Step 3: Write the module skeleton and canonical loader**

```python
# models/gen_district_private_comparison_html.py
"""
Generate per-district private property comparison pages (trend-focused).

Reads:
  data/ura_private.csv - canonical URA private transactions (2021+; owns 2021-2026)
  data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
                       - EdgeProp scrape; ONLY 2019-2020 rows used (condo/apartment backfill)
  data/ura_raw/pmi_d{NN}_landed_non_strata_2019-2026.csv   (optional per district)
  data/ura_raw/pmi_d{NN}_strata_landed_2019-2026.csv       (optional per district)
                       - raw URA PMI landed downloads; ONLY 2019-2020 rows used

Writes:
  private_project_comparison_D{NN}.html  (repo root; one per --district)

Run:
  python3 models/gen_district_private_comparison_html.py --district 17 --district 27

INPUT CONTRACT
  ura_private.csv columns: project_name, street_name, postal_district, property_type,
    tenure, sale_month (YYYY-MM), transacted_price, area_sqm, unit_price_psm, type_of_sale
  edgeprop csv columns: Project, Street, Postal District, Date of Sale (DD Mon YYYY),
    Type, Tenure, Sale Type, Price ($), Area (sqm), Area (sqft), Unit Price ($psf)
  ura_raw pmi csv columns: Project Name, Street Name, Postal District, Property Type,
    Tenure, Sale Date (Mon-YY), Transacted Price ($), Area (SQFT), Area (SQM),
    Unit Price ($ PSF), Type of Sale
  Backfill invariant: EdgeProp and ura_raw loaders never emit sale_year outside 2019-2020.
"""

from __future__ import annotations

import argparse
import html as html_mod
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
YEARS = list(range(2019, 2027))
SQM_TO_SQFT = 10.7639
MIN_YEAR_N = 3
UNIFIED_COLUMNS = [
    "project", "street", "property_type", "tenure", "sale_year",
    "price", "area_sqm", "psf", "sale_type", "source",
]
DISTRICT_NAMES = {
    "17": "Changi / Loyang / Pasir Ris",
    "27": "Yishun / Sembawang",
}
DEFAULT_PRIVATE = ROOT / "data/ura_private.csv"
DEFAULT_EDGEPROP = ROOT / "data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
DEFAULT_URA_RAW_DIR = ROOT / "data/ura_raw"


def normalise_district(value) -> str:
    text = str(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(2)[-2:] if digits else ""


def load_canonical(path: pathlib.Path, district: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"postal_district": str})
    df = df[df["postal_district"].map(normalise_district) == district].copy()
    out = pd.DataFrame({
        "project": df["project_name"].astype(str).str.strip().str.upper(),
        "street": df["street_name"].astype(str).str.strip().str.upper(),
        "property_type": df["property_type"].astype(str).str.strip(),
        "tenure": df["tenure"].astype(str).str.strip(),
        "sale_year": pd.to_numeric(df["sale_month"].astype(str).str[:4], errors="coerce"),
        "price": pd.to_numeric(df["transacted_price"], errors="coerce"),
        "area_sqm": pd.to_numeric(df["area_sqm"], errors="coerce"),
        "psf": pd.to_numeric(df["unit_price_psm"], errors="coerce") / SQM_TO_SQFT,
        "sale_type": df["type_of_sale"].astype(str).str.strip(),
        "source": "ura_private",
    })
    out = out.dropna(subset=["sale_year", "price", "area_sqm"])
    out = out[(out["price"] > 0) & (out["area_sqm"] > 0)]
    out["sale_year"] = out["sale_year"].astype(int)
    return out[UNIFIED_COLUMNS].reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: canonical loader for district private comparison generator"
```

---

### Task 2: EdgeProp 2019–2020 backfill loader

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append after `load_canonical`)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Consumes: `normalise_district`, `UNIFIED_COLUMNS`, `SQM_TO_SQFT` from Task 1.
- Produces: `load_edgeprop_backfill(path: pathlib.Path, district: str) -> pd.DataFrame`
  (unified schema, sale_year strictly in {2019, 2020}, source=`edgeprop_backfill`;
  empty DataFrame with `UNIFIED_COLUMNS` when the file is missing).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_district_private_comparison.py

def _edgeprop_row(**over):
    row = {"Project": "SELETARIS", "planning_area": "SEMBAWANG", "Postal District": "27",
           "Date of Sale": "15 Mar 2019", "Address": "X #05-XX", "Street": "SEMBAWANG ROAD",
           "Bedrooms": "3", "Unit Price ($psf)": "800", "Price ($)": "1000000",
           "Type": "Condominium", "Tenure": "Freehold", "Sale Type": "Resale",
           "Area (sqft)": "1250", "Area (sqm)": "116.1", "Type of Area": "Strata",
           "Purchaser Address": "Private", "Source": "URA", "source_quality": "not_clean",
           "source_url": "u", "source_slug": "s"}
    row.update(over)
    return row


def _write_edgeprop(tmp_path, rows):
    path = tmp_path / "edgeprop.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_edgeprop_backfill_keeps_only_2019_2020(tmp_path):
    path = _write_edgeprop(tmp_path, [
        _edgeprop_row(),
        _edgeprop_row(**{"Date of Sale": "10 Jun 2020", "Price ($)": "1100000"}),
        _edgeprop_row(**{"Date of Sale": "10 Jun 2021", "Price ($)": "1200000"}),
        _edgeprop_row(**{"Date of Sale": "10 Jun 2018", "Price ($)": "900000"}),
    ])
    out = gen.load_edgeprop_backfill(path, "27")
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert sorted(out["sale_year"]) == [2019, 2020]
    assert set(out["source"]) == {"edgeprop_backfill"}


def test_edgeprop_backfill_dedupes_and_drops_bad_rows(tmp_path):
    dup = _edgeprop_row()
    path = _write_edgeprop(tmp_path, [
        dup, dict(dup),                                    # exact duplicate
        _edgeprop_row(**{"Price ($)": "", "Date of Sale": "16 Mar 2019"}),   # missing price
        _edgeprop_row(**{"Area (sqm)": "0", "Date of Sale": "17 Mar 2019"}), # bad area
    ])
    out = gen.load_edgeprop_backfill(path, "27")
    assert len(out) == 1


def test_edgeprop_backfill_derives_psf_when_missing(tmp_path):
    path = _write_edgeprop(tmp_path, [_edgeprop_row(**{"Unit Price ($psf)": ""})])
    out = gen.load_edgeprop_backfill(path, "27")
    expected = 1_000_000 / (116.1 * gen.SQM_TO_SQFT)
    assert out.iloc[0]["psf"] == pytest.approx(expected, rel=1e-6)


def test_edgeprop_backfill_missing_file_returns_empty(tmp_path):
    out = gen.load_edgeprop_backfill(tmp_path / "nope.csv", "27")
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert out.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 4 new tests FAIL with `AttributeError: ... has no attribute 'load_edgeprop_backfill'`; Task 1 tests still pass.

- [ ] **Step 3: Implement the loader**

```python
# append to models/gen_district_private_comparison_html.py

def _empty_unified() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIFIED_COLUMNS)


def load_edgeprop_backfill(path: pathlib.Path, district: str) -> pd.DataFrame:
    if not path.exists():
        return _empty_unified()
    df = pd.read_csv(path, dtype={"Postal District": str})
    df = df[df["Postal District"].map(normalise_district) == district].copy()
    df["sale_dt"] = pd.to_datetime(df["Date of Sale"], format="%d %b %Y", errors="coerce")
    df = df.dropna(subset=["sale_dt"])
    df["sale_year"] = df["sale_dt"].dt.year
    df = df[df["sale_year"].between(2019, 2020)]
    df["price"] = pd.to_numeric(df["Price ($)"], errors="coerce")
    df["area_sqm"] = pd.to_numeric(df["Area (sqm)"], errors="coerce")
    df["psf_raw"] = pd.to_numeric(df["Unit Price ($psf)"], errors="coerce")
    df = df.dropna(subset=["price", "area_sqm"])
    df = df[(df["price"] > 0) & (df["area_sqm"] > 0)]
    df = df.drop_duplicates(subset=["Project", "Date of Sale", "Price ($)", "Area (sqft)"])
    derived_psf = df["price"] / (df["area_sqm"] * SQM_TO_SQFT)
    out = pd.DataFrame({
        "project": df["Project"].astype(str).str.strip().str.upper(),
        "street": df["Street"].astype(str).str.strip().str.upper(),
        "property_type": df["Type"].astype(str).str.strip(),
        "tenure": df["Tenure"].astype(str).str.strip(),
        "sale_year": df["sale_year"].astype(int),
        "price": df["price"],
        "area_sqm": df["area_sqm"],
        "psf": df["psf_raw"].where(df["psf_raw"] > 0, derived_psf),
        "sale_type": df["Sale Type"].astype(str).str.strip(),
        "source": "edgeprop_backfill",
    })
    return out[UNIFIED_COLUMNS].reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: EdgeProp 2019-2020 backfill loader for district comparison"
```

---

### Task 3: URA raw landed 2019–2020 backfill loader

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Consumes: `normalise_district`, `UNIFIED_COLUMNS`, `_empty_unified` from Tasks 1–2.
- Produces: `load_ura_raw_backfill(raw_dir: pathlib.Path, district: str) -> pd.DataFrame`
  (unified schema, sale_year strictly in {2019, 2020}, source=`ura_raw_backfill`;
  reads `pmi_d{NN}_landed_non_strata_2019-2026.csv` and `pmi_d{NN}_strata_landed_2019-2026.csv`,
  warns via `print` and skips each missing file).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_district_private_comparison.py

def _ura_raw_row(**over):
    row = {"Project Name": "LANDED HOUSING DEVELOPMENT", "Transacted Price ($)": "4,653,000",
           "Area (SQFT)": "3,614.55", "Unit Price ($ PSF)": "1,287", "Sale Date": "Jun-19",
           "Street Name": "JALAN PERNAMA", "Type of Sale": "Resale", "Type of Area": "Land",
           "Area (SQM)": "335.8", "Unit Price ($ PSM)": "13,856", "Nett Price($)": "-",
           "Property Type": "Semi-Detached House", "Number of Units": "1", "Tenure": "Freehold",
           "Postal District": "17", "Market Segment": "Outside Central Region", "Floor Level": "-"}
    row.update(over)
    return row


def _write_ura_raw(tmp_path, district, rows):
    raw_dir = tmp_path / "ura_raw"
    raw_dir.mkdir(exist_ok=True)
    path = raw_dir / f"pmi_d{district}_landed_non_strata_2019-2026.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return raw_dir


def test_ura_raw_backfill_parses_commas_and_dates(tmp_path):
    raw_dir = _write_ura_raw(tmp_path, "17", [_ura_raw_row()])
    out = gen.load_ura_raw_backfill(raw_dir, "17")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["price"] == pytest.approx(4_653_000)
    assert row["area_sqm"] == pytest.approx(335.8)
    assert row["psf"] == pytest.approx(1287)
    assert row["sale_year"] == 2019
    assert row["source"] == "ura_raw_backfill"


def test_ura_raw_backfill_keeps_only_2019_2020(tmp_path):
    raw_dir = _write_ura_raw(tmp_path, "17", [
        _ura_raw_row(),
        _ura_raw_row(**{"Sale Date": "Dec-20"}),
        _ura_raw_row(**{"Sale Date": "Jan-21"}),
        _ura_raw_row(**{"Sale Date": "Jun-26"}),
    ])
    out = gen.load_ura_raw_backfill(raw_dir, "17")
    assert sorted(out["sale_year"]) == [2019, 2020]


def test_ura_raw_backfill_missing_files_warns_and_returns_empty(tmp_path, capsys):
    empty_dir = tmp_path / "ura_raw"
    empty_dir.mkdir()
    out = gen.load_ura_raw_backfill(empty_dir, "17")
    assert out.empty
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert "WARN" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 3 new tests FAIL with `AttributeError: ... has no attribute 'load_ura_raw_backfill'`

- [ ] **Step 3: Implement the loader**

```python
# append to models/gen_district_private_comparison_html.py

def _comma_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def load_ura_raw_backfill(raw_dir: pathlib.Path, district: str) -> pd.DataFrame:
    frames = []
    stems = (
        f"pmi_d{district}_landed_non_strata_2019-2026.csv",
        f"pmi_d{district}_strata_landed_2019-2026.csv",
    )
    for stem in stems:
        path = raw_dir / stem
        if not path.exists():
            print(f"WARN: {path} missing; skipping landed backfill file")
            continue
        df = pd.read_csv(path, dtype={"Postal District": str})
        df = df[df["Postal District"].map(normalise_district) == district].copy()
        df["sale_dt"] = pd.to_datetime(df["Sale Date"], format="%b-%y", errors="coerce")
        df = df.dropna(subset=["sale_dt"])
        df["sale_year"] = df["sale_dt"].dt.year
        df = df[df["sale_year"].between(2019, 2020)]
        if df.empty:
            continue
        out = pd.DataFrame({
            "project": df["Project Name"].astype(str).str.strip().str.upper(),
            "street": df["Street Name"].astype(str).str.strip().str.upper(),
            "property_type": df["Property Type"].astype(str).str.strip(),
            "tenure": df["Tenure"].astype(str).str.strip(),
            "sale_year": df["sale_year"].astype(int),
            "price": _comma_numeric(df["Transacted Price ($)"]),
            "area_sqm": _comma_numeric(df["Area (SQM)"]),
            "psf": _comma_numeric(df["Unit Price ($ PSF)"]),
            "sale_type": df["Type of Sale"].astype(str).str.strip(),
            "source": "ura_raw_backfill",
        })
        out = out.dropna(subset=["price", "area_sqm"])
        out = out[(out["price"] > 0) & (out["area_sqm"] > 0)]
        frames.append(out[UNIFIED_COLUMNS])
    if not frames:
        return _empty_unified()
    return pd.concat(frames, ignore_index=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: URA raw landed 2019-2020 backfill loader"
```

---

### Task 4: Annualised growth computation

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Consumes: `MIN_YEAR_N` from Task 1.
- Produces: `annualised_growth(year_stats: dict[int, tuple[float | None, int]]) -> tuple[float, int, int] | None`
  — input maps year → (median_psf_or_None, n); returns (annualised_rate_fraction, from_year, to_year) or None.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_district_private_comparison.py

def test_annualised_growth_uses_first_and_last_qualifying_years():
    stats = {2019: (1000.0, 5), 2021: (900.0, 2), 2023: (1200.0, 4)}
    rate, y0, y1 = gen.annualised_growth(stats)
    assert (y0, y1) == (2019, 2023)  # 2021 skipped: n < MIN_YEAR_N
    assert rate == pytest.approx((1200.0 / 1000.0) ** (1 / 4) - 1)


def test_annualised_growth_none_when_fewer_than_two_qualifying_years():
    assert gen.annualised_growth({2019: (1000.0, 5)}) is None
    assert gen.annualised_growth({2019: (1000.0, 2), 2020: (1100.0, 2)}) is None
    assert gen.annualised_growth({}) is None


def test_annualised_growth_ignores_none_medians():
    stats = {2019: (None, 5), 2020: (1000.0, 3), 2022: (1210.0, 3)}
    rate, y0, y1 = gen.annualised_growth(stats)
    assert (y0, y1) == (2020, 2022)
    assert rate == pytest.approx(0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 3 new tests FAIL with `AttributeError: ... has no attribute 'annualised_growth'`

- [ ] **Step 3: Implement**

```python
# append to models/gen_district_private_comparison_html.py

def annualised_growth(year_stats: dict) -> tuple | None:
    qualifying = sorted(
        year for year, (median, n) in year_stats.items()
        if n >= MIN_YEAR_N and median is not None and median > 0
    )
    if len(qualifying) < 2:
        return None
    y0, y1 = qualifying[0], qualifying[-1]
    p0 = year_stats[y0][0]
    p1 = year_stats[y1][0]
    rate = (p1 / p0) ** (1.0 / (y1 - y0)) - 1.0
    return rate, y0, y1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: annualised growth over qualifying years"
```

---

### Task 5: Project grouping + aggregation

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Consumes: `annualised_growth`, `YEARS`, `MIN_YEAR_N` from earlier tasks; unified-schema DataFrames from the loaders.
- Produces:
  - `display_project(project: str, street: str) -> str` — `"LANDED HOUSING DEVELOPMENT"` becomes `"LANDED HOUSING DEVELOPMENT (<STREET>)"`, all other names pass through.
  - `mode_text(series: pd.Series, default: str = "-") -> str`.
  - `aggregate_projects(df: pd.DataFrame) -> list[dict]` — one dict per project, sorted by `n_total` desc, keys: `project, street, property_types, tenure, n_total, year_stats (dict year -> (median_psf|None, n)), growth_pct (float|None, percent), growth_from, growth_to, latest_year, latest_median_psf, latest_median_price, has_edgeprop_backfill (bool)`.
  - `district_summary(df: pd.DataFrame, rows: list[dict]) -> dict` — keys: `total_txns, yearly (dict year -> (median_psf|None, n)), top_growth (up to 3 row-dicts desc), bottom_growth (up to 3 row-dicts asc)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_district_private_comparison.py

def _unified(rows):
    return pd.DataFrame(rows, columns=gen.UNIFIED_COLUMNS)


def _u_row(project, year, psf, street="STREET A", ptype="Condominium",
           tenure="Freehold", source="ura_private", price=1_000_000, area=100.0):
    return [project, street, ptype, tenure, year, price, area, psf, "Resale", source]


def test_display_project_splits_generic_landed_by_street():
    assert gen.display_project("LANDED HOUSING DEVELOPMENT", "TOH CRESCENT") == \
        "LANDED HOUSING DEVELOPMENT (TOH CRESCENT)"
    assert gen.display_project("LOYANG VILLAS", "LOYANG RISE") == "LOYANG VILLAS"


def test_aggregate_projects_groups_and_computes_year_stats():
    df = _unified(
        [_u_row("ALPHA", 2021, 1000.0) for _ in range(3)]
        + [_u_row("ALPHA", 2023, 1100.0) for _ in range(3)]
        + [_u_row("ALPHA", 2022, 1050.0)]  # n=1 -> below MIN_YEAR_N
        + [_u_row("LANDED HOUSING DEVELOPMENT", 2021, 900.0, street="TOH CRESCENT")]
        + [_u_row("LANDED HOUSING DEVELOPMENT", 2021, 950.0, street="JALAN PERNAMA")]
    )
    rows = gen.aggregate_projects(df)
    names = [r["project"] for r in rows]
    assert names[0] == "ALPHA"  # most txns first
    assert "LANDED HOUSING DEVELOPMENT (TOH CRESCENT)" in names
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in names
    alpha = rows[0]
    assert alpha["n_total"] == 7
    assert alpha["year_stats"][2021] == (1000.0, 3)
    assert alpha["year_stats"][2019] == (None, 0)
    assert alpha["growth_pct"] == pytest.approx(((1100 / 1000) ** 0.5 - 1) * 100)
    assert (alpha["growth_from"], alpha["growth_to"]) == (2021, 2023)
    assert alpha["latest_year"] == 2023
    assert alpha["latest_median_psf"] == pytest.approx(1100.0)
    assert alpha["has_edgeprop_backfill"] is False


def test_aggregate_projects_flags_edgeprop_backfill():
    df = _unified([
        _u_row("BETA", 2019, 800.0, source="edgeprop_backfill"),
        _u_row("BETA", 2022, 1000.0),
    ])
    rows = gen.aggregate_projects(df)
    assert rows[0]["has_edgeprop_backfill"] is True


def test_district_summary_totals_and_growth_rankings():
    df = _unified(
        [_u_row("ALPHA", 2021, 1000.0) for _ in range(3)]
        + [_u_row("ALPHA", 2023, 1200.0) for _ in range(3)]
        + [_u_row("BETA", 2021, 1000.0) for _ in range(3)]
        + [_u_row("BETA", 2023, 900.0) for _ in range(3)]
        + [_u_row("GAMMA", 2021, 500.0)]  # no growth (single low-n year)
    )
    rows = gen.aggregate_projects(df)
    summary = gen.district_summary(df, rows)
    assert summary["total_txns"] == 13
    assert summary["yearly"][2021] == (1000.0, 7)
    assert summary["top_growth"][0]["project"] == "ALPHA"
    assert summary["bottom_growth"][0]["project"] == "BETA"
    growth_names = {r["project"] for r in summary["top_growth"] + summary["bottom_growth"]}
    assert "GAMMA" not in growth_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 4 new tests FAIL with `AttributeError`

- [ ] **Step 3: Implement**

```python
# append to models/gen_district_private_comparison_html.py

GENERIC_LANDED_NAME = "LANDED HOUSING DEVELOPMENT"


def display_project(project: str, street: str) -> str:
    if project == GENERIC_LANDED_NAME:
        return f"{GENERIC_LANDED_NAME} ({street})"
    return project


def mode_text(series: pd.Series, default: str = "-") -> str:
    values = series.dropna()
    values = values[values.astype(str).str.strip() != ""]
    if values.empty:
        return default
    return str(values.mode().iloc[0])


def _year_stats(grp: pd.DataFrame) -> dict:
    stats = {}
    for year in YEARS:
        sub = grp[grp["sale_year"] == year]
        median = float(sub["psf"].median()) if len(sub) else None
        stats[year] = (median, int(len(sub)))
    return stats


def aggregate_projects(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["display_project"] = [
        display_project(p, s) for p, s in zip(df["project"], df["street"])
    ]
    rows = []
    for name, grp in df.groupby("display_project"):
        stats = _year_stats(grp)
        growth = annualised_growth(stats)
        active_years = [y for y in YEARS if stats[y][1] > 0]
        latest_year = active_years[-1] if active_years else None
        latest = grp[grp["sale_year"] == latest_year] if latest_year else grp.iloc[0:0]
        types = sorted(t for t in grp["property_type"].dropna().unique() if str(t).strip())
        rows.append({
            "project": name,
            "street": mode_text(grp["street"]),
            "property_types": " / ".join(types) if types else "-",
            "tenure": mode_text(grp["tenure"]),
            "n_total": int(len(grp)),
            "year_stats": stats,
            "growth_pct": growth[0] * 100.0 if growth else None,
            "growth_from": growth[1] if growth else None,
            "growth_to": growth[2] if growth else None,
            "latest_year": latest_year,
            "latest_median_psf": float(latest["psf"].median()) if len(latest) else None,
            "latest_median_price": float(latest["price"].median()) if len(latest) else None,
            "has_edgeprop_backfill": bool((grp["source"] == "edgeprop_backfill").any()),
        })
    rows.sort(key=lambda r: (-r["n_total"], r["project"]))
    return rows


def district_summary(df: pd.DataFrame, rows: list[dict]) -> dict:
    with_growth = [r for r in rows if r["growth_pct"] is not None]
    ranked = sorted(with_growth, key=lambda r: r["growth_pct"], reverse=True)
    return {
        "total_txns": int(len(df)),
        "yearly": _year_stats(df),
        "top_growth": ranked[:3],
        "bottom_growth": ranked[::-1][:3],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: project grouping, aggregation, and district summary"
```

---

### Task 6: HTML rendering, generate(), CLI

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces:
  - `render_html(district: str, rows: list[dict], summary: dict) -> str` — full self-contained page.
  - `generate(district, private_path, edgeprop_path, raw_dir, out_dir) -> tuple[pathlib.Path, int]` — writes `private_project_comparison_D{NN}.html`, returns (path, n_projects).
  - `main() -> None` — argparse CLI: repeatable `--district` (required), `--private`, `--edgeprop`, `--ura-raw-dir`, `--out-dir`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_district_private_comparison.py

def _full_fixture(tmp_path):
    """Canonical + edgeprop + ura_raw covering district 27."""
    canonical = _write_canonical(tmp_path)  # has 1 valid D27 row (THE SHAUGHNESSY 2023)
    edgeprop = _write_edgeprop(tmp_path, [_edgeprop_row()])  # SELETARIS 2019, D27
    raw_dir = _write_ura_raw(tmp_path, "27", [_ura_raw_row(**{"Postal District": "27"})])
    return canonical, edgeprop, raw_dir


def test_generate_writes_self_contained_page(tmp_path):
    canonical, edgeprop, raw_dir = _full_fixture(tmp_path)
    out_path, n_rows = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    assert out_path.name == "private_project_comparison_D27.html"
    assert out_path.exists()
    assert n_rows >= 3  # SHAUGHNESSY + SELETARIS + landed street group
    text = out_path.read_text(encoding="utf-8")
    assert "THE SHAUGHNESSY" in text
    assert "SELETARIS" in text
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in text
    assert "2019" in text and "2026" in text
    assert "EdgeProp" in text          # caveat banner mentions the backfill source
    assert "http://" not in text and "https://" not in text  # self-contained


def test_render_html_marks_low_n_years_and_backfill():
    rows = [{
        "project": "ALPHA", "street": "S", "property_types": "Condominium",
        "tenure": "Freehold", "n_total": 4,
        "year_stats": {y: (None, 0) for y in gen.YEARS} | {2021: (1000.0, 3), 2022: (1050.0, 1)},
        "growth_pct": None, "growth_from": None, "growth_to": None,
        "latest_year": 2022, "latest_median_psf": 1050.0, "latest_median_price": 1_000_000.0,
        "has_edgeprop_backfill": True,
    }]
    summary = {"total_txns": 4, "yearly": rows[0]["year_stats"],
               "top_growth": [], "bottom_growth": []}
    html_text = gen.render_html("27", rows, summary)
    assert "1,000" in html_text        # 2021 median shown (n>=3)
    assert "1,050" not in html_text or html_text.count("1,050") == 1  # 2022 hidden in year cell (n<3); latest-psf col may show it
    assert "backfill" in html_text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 2 new tests FAIL with `AttributeError: ... has no attribute 'generate'` / `'render_html'`

- [ ] **Step 3: Implement rendering, generate, and CLI**

```python
# append to models/gen_district_private_comparison_html.py

def _fmt(value, digits=0):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _esc(value) -> str:
    return html_mod.escape(str(value))


def render_html(district: str, rows: list[dict], summary: dict) -> str:
    district_name = DISTRICT_NAMES.get(district, f"District {district}")
    year_heads = "".join(f"<th class='num sortable' data-col='y{y}'>{y}</th>" for y in YEARS)

    body_rows = []
    for r in rows:
        year_cells = []
        for y in YEARS:
            median, n = r["year_stats"][y]
            if n >= MIN_YEAR_N and median is not None:
                year_cells.append(
                    f"<td class='num' data-v='{median:.0f}' title='n={n}'>{_fmt(median)}</td>"
                )
            else:
                year_cells.append(f"<td class='num muted' data-v='' title='n={n}'>—</td>")
        growth = r["growth_pct"]
        if growth is None:
            growth_cell = "<td class='num muted' data-v=''>—</td>"
        else:
            cls = "pos" if growth >= 0 else "neg"
            growth_cell = (
                f"<td class='num {cls}' data-v='{growth:.2f}' "
                f"title='{r['growth_from']}→{r['growth_to']}'>{growth:+.1f}%/yr</td>"
            )
        badge = " <span class='badge' title='includes EdgeProp 2019–2020 backfill rows (incomplete coverage)'>backfill</span>" \
            if r["has_edgeprop_backfill"] else ""
        body_rows.append(
            "<tr>"
            f"<td data-v='{_esc(r['project'])}'>{_esc(r['project'])}{badge}</td>"
            f"<td data-v='{_esc(r['property_types'])}'>{_esc(r['property_types'])}</td>"
            f"<td data-v='{_esc(r['tenure'])}'>{_esc(r['tenure'])}</td>"
            f"<td class='num' data-v='{r['n_total']}'>{r['n_total']}</td>"
            + "".join(year_cells)
            + growth_cell
            + f"<td class='num' data-v='{r['latest_median_psf'] or ''}'>{_fmt(r['latest_median_psf'])}</td>"
            + f"<td class='num' data-v='{r['latest_median_price'] or ''}'>{_fmt(r['latest_median_price'])}</td>"
            "</tr>"
        )

    yearly_cells = "".join(
        f"<td class='num'>{_fmt(summary['yearly'][y][0])}<div class='n'>n={summary['yearly'][y][1]}</div></td>"
        for y in YEARS
    )
    def _growth_list(items):
        if not items:
            return "<li class='muted'>—</li>"
        return "".join(
            f"<li>{_esc(i['project'])} <span class='{'pos' if i['growth_pct'] >= 0 else 'neg'}'>"
            f"{i['growth_pct']:+.1f}%/yr</span></li>"
            for i in items
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>D{district} Private Property Comparison ({district_name})</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 24px; color: #1a1a2e; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .caveat {{ background: #fff7e0; border: 1px solid #e8c96a; border-radius: 8px;
             padding: 10px 14px; margin: 12px 0 20px; font-size: 13px; max-width: 900px; }}
  .summary {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 20px; }}
  .summary .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .summary h3 {{ margin: 0 0 6px; font-size: 13px; }}
  .summary ul {{ margin: 0; padding-left: 18px; }}
  table {{ border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 5px 9px; border-bottom: 1px solid #e4e4ee; text-align: left; white-space: nowrap; }}
  th {{ background: #f4f4fa; position: sticky; top: 0; cursor: pointer; user-select: none; }}
  td.num, th.num {{ text-align: right; }}
  .muted {{ color: #9a9ab0; }}
  .pos {{ color: #0a7a3d; }}
  .neg {{ color: #b02a2a; }}
  .badge {{ background: #fdecc8; color: #8a6100; border-radius: 4px; padding: 1px 5px; font-size: 11px; }}
  .n {{ font-size: 10px; color: #9a9ab0; }}
</style>
</head>
<body>
<h1>District {district} — {_esc(district_name)}: Private Property Comparison</h1>
<div>Window: 2019–2026 · median PSF (S$) by sale year · {summary['total_txns']:,} transactions</div>
<div class="caveat">⚠ 2019–2020 condo/apartment rows are backfilled from an incomplete EdgeProp scrape
(the canonical URA feed only reaches back to 2021). Pre-2021 medians are indicative only —
projects using that data carry a <span class="badge">backfill</span> badge. Landed 2019–2020 rows
come from raw URA PMI downloads. Year cells show — when the year has fewer than {MIN_YEAR_N} transactions.</div>
<div class="summary">
  <div class="card"><h3>District median PSF by year</h3>
    <table><tr>{"".join(f"<th class='num'>{y}</th>" for y in YEARS)}</tr><tr>{yearly_cells}</tr></table>
  </div>
  <div class="card"><h3>Top growth</h3><ul>{_growth_list(summary['top_growth'])}</ul></div>
  <div class="card"><h3>Bottom growth</h3><ul>{_growth_list(summary['bottom_growth'])}</ul></div>
</div>
<table id="projects">
<thead><tr>
  <th class="sortable">Project</th><th class="sortable">Type</th><th class="sortable">Tenure</th>
  <th class="num sortable">Txns</th>{year_heads}
  <th class="num sortable">Growth %/yr</th>
  <th class="num sortable">Latest median PSF</th><th class="num sortable">Latest median price</th>
</tr></thead>
<tbody>
{"".join(body_rows)}
</tbody>
</table>
<script>
document.querySelectorAll('#projects th').forEach(function (th, idx) {{
  th.addEventListener('click', function () {{
    var tbody = document.querySelector('#projects tbody');
    var rows = Array.from(tbody.rows);
    var dir = th.dataset.dir === 'asc' ? -1 : 1;
    document.querySelectorAll('#projects th').forEach(function (h) {{ delete h.dataset.dir; }});
    th.dataset.dir = dir === 1 ? 'asc' : 'desc';
    rows.sort(function (a, b) {{
      var av = a.cells[idx].dataset.v, bv = b.cells[idx].dataset.v;
      if (av === '' && bv === '') return 0;
      if (av === '') return 1;
      if (bv === '') return -1;
      var an = parseFloat(av), bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return (an - bn) * dir;
      return av.localeCompare(bv) * dir;
    }});
    rows.forEach(function (r) {{ tbody.appendChild(r); }});
  }});
}});
</script>
</body>
</html>
"""


def generate(district, private_path, edgeprop_path, raw_dir, out_dir):
    district = normalise_district(district)
    frames = [
        load_canonical(private_path, district),
        load_edgeprop_backfill(edgeprop_path, district),
        load_ura_raw_backfill(raw_dir, district),
    ]
    merged = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    rows = aggregate_projects(merged)
    summary = district_summary(merged, rows)
    out_path = pathlib.Path(out_dir) / f"private_project_comparison_D{district}.html"
    out_path.write_text(render_html(district, rows, summary), encoding="utf-8")
    return out_path, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-district private comparison HTML")
    parser.add_argument("--district", action="append", required=True,
                        help="Postal district (repeatable), e.g. --district 17 --district 27")
    parser.add_argument("--private", default=str(DEFAULT_PRIVATE))
    parser.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    parser.add_argument("--ura-raw-dir", default=str(DEFAULT_URA_RAW_DIR))
    parser.add_argument("--out-dir", default=str(ROOT))
    args = parser.parse_args()
    for district in args.district:
        out_path, n_rows = generate(
            district,
            pathlib.Path(args.private),
            pathlib.Path(args.edgeprop),
            pathlib.Path(args.ura_raw_dir),
            pathlib.Path(args.out_dir),
        )
        print(f"Written: {out_path} ({out_path.stat().st_size // 1024} KB, {n_rows} projects)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: render + CLI for per-district private comparison pages"
```

---

### Task 7: Integration test + generate D17/D27 for real

**Files:**
- Modify: `tests/test_gen_district_private_comparison.py` (append)
- Create (generated): `private_project_comparison_D17.html`, `private_project_comparison_D27.html`

**Interfaces:**
- Consumes: `generate` from Task 6 and the committed data files.

- [ ] **Step 1: Write the integration test**

```python
# append to tests/test_gen_district_private_comparison.py
import pathlib

ROOT = pathlib.Path(__file__).parent.parent


@pytest.mark.integration
def test_generate_real_d17_d27(tmp_path):
    for district, anchor in (("17", "LOYANG VILLAS"), ("27", "THE SHAUGHNESSY")):
        out_path, n_rows = gen.generate(
            district,
            ROOT / "data/ura_private.csv",
            ROOT / "data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv",
            ROOT / "data/ura_raw",
            tmp_path,
        )
        assert n_rows > 20
        text = out_path.read_text(encoding="utf-8")
        assert anchor in text
        assert "2019" in text
```

- [ ] **Step 2: Run the integration test**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -m integration -v`
Expected: 1 passed (slow — reads the 21 MB EdgeProp CSV twice)

- [ ] **Step 3: Run the full suite to check nothing else broke**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && make smoke`
Expected: all tests pass (snapshot tests remain deselected)

- [ ] **Step 4: Generate the real pages**

Run:
```bash
cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && \
python3 models/gen_district_private_comparison_html.py --district 17 --district 27
```
Expected output (two lines):
```
Written: .../private_project_comparison_D17.html (... KB, N projects)
Written: .../private_project_comparison_D27.html (... KB, N projects)
```
Sanity-check: open each file, confirm the caveat banner, district summary strip, year columns 2019–2026, and that LOYANG VILLAS (D17) / THE SHAUGHNESSY (D27) appear with plausible PSF values.

- [ ] **Step 5: Commit generated pages + integration test**

```bash
git add tests/test_gen_district_private_comparison.py \
        private_project_comparison_D17.html private_project_comparison_D27.html
git commit -m "feat: district private comparison pages for D17 and D27"
```
