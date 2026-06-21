# Phase 0 + 1: Test Harness & Correctness Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pytest safety net, then fix the correctness bugs that make the committed Value/Liveability/Gap numbers wrong or uninterpretable.

**Architecture:** Add a `tests/` suite (none exists today). Each correctness fix is TDD: write a test that encodes the *correct* behaviour, watch it fail against the current buggy code, fix, watch it pass. Small refactors (extracting `build_formula`, `clean_psm`) make the regression code unit-testable. Fixes are sequenced so each is an independently reviewable diff.

**Tech Stack:** Python 3, pytest, pandas, numpy, statsmodels. Run from the repo root `SG-Estate-Framework/`.

## Global Constraints
- Install: `pip install pytest pandas numpy statsmodels shapely --break-system-packages`.
- All paths relative to repo root `SG-Estate-Framework/` unless absolute.
- **Never blend HDB and private** value/price distributions (invariant 2).
- **Provenance never faked**; missing JUDGED inputs flagged, never silently imputed.
- When a number changes in code, update the matching `frameworks/*.md` and both `CLAUDE.md` files.
- No silent error swallowing. Tests assert behaviour, not implementation.
- Fixes WILL change committed CSV outputs — that is intended; capture the diff (Task 0.4) and document it in each commit message.

---

## File Structure

| File | Responsibility |
|---|---|
| `pytest.ini` | pytest config: testpaths, markers |
| `requirements-dev.txt` | dev deps |
| `tests/conftest.py` | sys.path setup (models/ on path), shared fixtures |
| `tests/test_pipeline_smoke.py` | end-to-end runs without error; output schemas |
| `tests/test_invariants.py` | always-true properties (weights sum to 1, no NaN, segments separate) |
| `tests/snapshot.py` + `tests/test_characterization.py` | before/after output diff helper |
| `tests/test_value_model.py` | unit tests for circularity, alias, area filter |
| `tests/test_liveability_model.py` | unit tests for BASE_W sync, gap, veto, X-gate |
| `tests/test_momentum_model.py` | unit tests for no-silent-zero |
| `tests/test_doc_consistency.py` | guard: component counts agree across code |
| `models/value_model.py` | fixes 1.1, 1.2, 1.3 |
| `models/liveability_model.py` | fixes 1.4, 1.5, 1.6, 1.7 |
| `models/momentum_model.py` | fixes 1.8, 1.9 |
| `models/provision_model.py` + docs | fix 1.10 |

---

## PHASE 0 — Safety Net

### Task 0.1: pytest scaffold + fixtures

**Files:**
- Create: `pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`, `tests/__init__.py`

**Interfaces:**
- Produces: fixtures `data_dir() -> str`, `tiny_scores() -> pd.DataFrame`, `tiny_hdb() -> pd.DataFrame`; `models/` and repo root on `sys.path`.

- [ ] **Step 1: Create dev deps and config**

`requirements-dev.txt`:
```
pytest>=8.0
pandas
numpy
statsmodels
shapely
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
markers =
    integration: runs the real pipeline on committed data (slow)
    snapshot: before/after characterization (run manually)
```

`tests/__init__.py`: (empty file)

- [ ] **Step 2: Write conftest with path setup + fixtures**

`tests/conftest.py`:
```python
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
```

- [ ] **Step 3: Verify pytest collects**

Run: `cd SG-Estate-Framework && python -m pytest -q`
Expected: `no tests ran` (exit 5) or collection success — NOT an import/config error.

- [ ] **Step 4: Commit**

```bash
git add pytest.ini requirements-dev.txt tests/__init__.py tests/conftest.py
git commit -m "test: add pytest scaffold and shared fixtures"
```

---

### Task 0.2: End-to-end smoke test

**Files:**
- Create: `tests/test_pipeline_smoke.py`

**Interfaces:**
- Consumes: `value_model.fit_segment`, `value_model.SEGMENTS`, `value_model.value_scores`, `tiny_hdb`, `tiny_scores`.

- [ ] **Step 1: Write the smoke test**

`tests/test_pipeline_smoke.py`:
```python
import value_model


def test_fit_segment_runs_and_returns_residuals(tiny_hdb, tiny_scores):
    out = value_model.fit_segment(tiny_hdb, "hdb_resale", tiny_scores)
    assert out is not None
    assert {"estate", "segment", "n", "resid_raw", "resid_shrunk", "trust"} <= set(out.columns)
    # both towns present, each n=8
    assert set(out["estate"]) == {"BISHAN", "TAMPINES"}
    assert (out["n"] == 8).all()


def test_value_scores_produces_bands(tiny_hdb, tiny_scores):
    resid = value_model.fit_segment(tiny_hdb, "hdb_resale", tiny_scores)
    scored = value_model.value_scores(resid, tiny_scores, set(tiny_scores["estate"]))
    assert "value_band" in scored.columns
    assert scored["value_band"].isin(["A", "B+", "B", "C", "D", "F"]).all()
```

- [ ] **Step 2: Run to verify it passes against current code**

Run: `python -m pytest tests/test_pipeline_smoke.py -v`
Expected: PASS (the current model runs; this is a baseline, not a bug test).

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_smoke.py
git commit -m "test: end-to-end smoke test for value_model"
```

---

### Task 0.3: Invariant tests

**Files:**
- Create: `tests/test_invariants.py`

- [ ] **Step 1: Write invariant tests**

`tests/test_invariants.py`:
```python
import value_model
import provision_model


def test_provision_weights_sum_to_one():
    assert abs(sum(provision_model.W.values()) - 1.0) < 1e-9
    assert abs(sum(provision_model.W_PRIVATE.values()) - 1.0) < 1e-9


def test_segments_have_distinct_controls():
    segs = value_model.SEGMENTS
    assert "hdb_resale" in segs and "private_resale" in segs
    # HDB and private must not key on the same geographic column blindly
    assert segs["hdb_resale"]["area_key"] == "town"
    assert segs["private_resale"]["area_key"] == "planning_area"


def test_band_edges_monotonic():
    edges = [e for e, _ in value_model.CFG["band_edges"]]
    assert edges == sorted(edges, reverse=True)
```

- [ ] **Step 2: Run to verify it passes**

Run: `python -m pytest tests/test_invariants.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_invariants.py
git commit -m "test: framework invariants (weights, segment separation, bands)"
```

---

### Task 0.4: Snapshot / diff helper

**Files:**
- Create: `tests/snapshot.py`, `tests/test_characterization.py`

**Interfaces:**
- Produces: `snapshot.capture(tag) -> dict[str, pd.DataFrame]` writing CSVs under `tests/snapshots/<tag>/`.

- [ ] **Step 1: Write the snapshot helper**

`tests/snapshot.py`:
```python
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
```

- [ ] **Step 2: Write a manually-run characterization test**

`tests/test_characterization.py`:
```python
import pytest

import snapshot


@pytest.mark.snapshot
def test_capture_before():
    """Run before Phase-1 fixes: python -m pytest -m snapshot -k before"""
    captured = snapshot.capture("before")
    assert "value_output.csv" in captured
```

- [ ] **Step 3: Capture the baseline**

Run: `python -m pytest -m snapshot -k before -v`
Expected: PASS; `tests/snapshots/before/` now holds the pre-fix CSVs.

- [ ] **Step 4: Commit**

```bash
git add tests/snapshot.py tests/test_characterization.py tests/snapshots/before/
git commit -m "test: snapshot helper + baseline capture before correctness fixes"
```

---

## PHASE 1 — Correctness Fixes

### Task 1.1: Value circularity — drop provision score from the regression RHS

**Files:**
- Modify: `models/value_model.py:135-150` (extract `build_formula`, remove `_score` from RHS)
- Test: `tests/test_value_model.py`

**Interfaces:**
- Produces: `value_model.build_formula(df, controls, month_col) -> str` (formula string with NO `_score` term).

**Context:** `_score` is currently both a regressor (`value_model.py:147`) and the Value multiplier base (`:177`). It partials the provision premium out of the residual, then multiplies it back in (residual shift correlates −0.99 with score). Provision must enter exactly once — as the base.
**Note:** Keep the shadow-row block (`:113-122`). Once `_score` is off the RHS it is harmless — its only remaining effect is keeping aliased target towns (KALLANG/WHAMPOA) in the regression sample via a placeholder score, preserving coverage. Do NOT delete it in this task.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_value_model.py`:
```python
import value_model


def test_build_formula_excludes_provision_score(tiny_hdb):
    f = value_model.build_formula(tiny_hdb, ["flat_type", "remaining_lease_years"], "month")
    assert "_score" not in f, "provision score must NOT be a regressor (circularity)"
    assert "C(flat_type)" in f
    assert "remaining_lease_years" in f
    assert "C(month)" in f
    assert f.startswith("_lnpsm ~")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_value_model.py::test_build_formula_excludes_provision_score -v`
Expected: FAIL with `AttributeError: module 'value_model' has no attribute 'build_formula'`.

- [ ] **Step 3: Extract `build_formula` and remove `_score` from the RHS**

In `models/value_model.py`, replace the formula/fit block (currently lines ~135-150) with:
```python
    # build controls-only formula: lnpsm ~ controls + C(month)
    # NOTE: provision _score is deliberately NOT a regressor — it is the Value
    # multiplier base (value_scores). Putting it here partials out the provision
    # premium then multiplies it back, double-counting provision.
    model_formula = build_formula(df, s["controls"], s["month_col"])
    model = smf.ols(model_formula, data=df).fit()
    df["_resid"] = model.resid
```

Add this helper above `fit_segment` (after the `band` function, ~line 69):
```python
def build_formula(df, controls, month_col):
    """RHS = within-segment quality controls only. Provision score is NEVER here."""
    ctrl_terms = []
    for c in controls:
        if c in df.columns:
            ctrl_terms.append(f"C({c})" if df[c].dtype == object else c)
    if month_col in df.columns:
        ctrl_terms.append(f"C({month_col})")
    rhs = " + ".join(ctrl_terms) if ctrl_terms else "1"
    return f"_lnpsm ~ {rhs}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_value_model.py::test_build_formula_excludes_provision_score -v`
Expected: PASS.

- [ ] **Step 5: Re-run smoke + capture the intended diff**

Run: `python -m pytest tests/test_pipeline_smoke.py -v` → PASS
Run the real pipeline and diff vs baseline:
```bash
python models/value_model.py --scores data/provision_scores.csv --hdb data/hdb_resale.csv --out data/value_output.csv
python -c "import sys; sys.path.insert(0,'tests'); import snapshot; snapshot.capture('after_1_1'); print(snapshot.diff('before','after_1_1','value_output.csv')[['estate','mult_before','mult_after']].to_string())"
```
Expected: multipliers move (high-provision towns down, low up), per the review. Review the diff before committing.

- [ ] **Step 6: Commit**

```bash
git add models/value_model.py tests/test_value_model.py data/value_output.csv
git commit -m "fix(value): remove provision score from residual regression (circularity)

Provision score was both a regressor and the multiplier base, partialling out
the provision premium then multiplying it back (resid shift corr -0.99 w/ score).
Now enters once, as the base. Multipliers shift accordingly."
```

---

### Task 1.2: Alias loop — stop triple-counting and HDB→private laundering

**Files:**
- Modify: `models/value_model.py:166-207` (`value_scores`)
- Test: `tests/test_value_model.py`

**Interfaces:**
- Consumes: `value_model.value_scores(resid_df, scores, original_estate_names)`.
- Produces: output rows carry a `value_basis` column: `"direct"` | `"proxy_from:<TOWN>"` | `"no_hdb_segment"`. Private-dominant proxies get `value_score=NaN`, `value_band="N/A"`.

**Context:** The alias loop (`:187-204`) emits a synthetic row per alias even when the target is a real estate, so QUEENSTOWN's residual also appears as DOVER and HOLLAND VILLAGE (identical n=6353). HOLLAND VILLAGE (archetype D, private-dominant) inheriting an HDB residual violates invariant 2.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_value_model.py`:
```python
import numpy as np
import pandas as pd


def _resid_df():
    return pd.DataFrame(
        {
            "estate": ["QUEENSTOWN", "TAMPINES"],
            "segment": ["hdb_resale", "hdb_resale"],
            "n": [6353, 16029],
            "resid_raw": [0.244, 0.074],
            "resid_shrunk": [0.244, 0.074],
            "trust": ["decimal", "decimal"],
        }
    )


def _scores():
    return pd.DataFrame(
        {
            "estate": ["QUEENSTOWN", "TAMPINES", "DOVER", "HOLLAND VILLAGE", "TAMPINES WEST"],
            "score": [3.59, 3.52, 3.60, 4.01, 3.71],
        }
    )


def test_private_dominant_proxy_gets_no_hdb_residual():
    out = value_model.value_scores(_resid_df(), _scores(), set(_scores()["estate"]))
    hv = out[out["estate"] == "HOLLAND VILLAGE"].iloc[0]
    assert hv["value_basis"] == "no_hdb_segment"
    assert pd.isna(hv["value_score"])
    assert hv["value_band"] == "N/A"


def test_subarea_proxy_is_tagged_not_silent():
    out = value_model.value_scores(_resid_df(), _scores(), set(_scores()["estate"]))
    dover = out[out["estate"] == "DOVER"].iloc[0]
    assert dover["value_basis"] == "proxy_from:QUEENSTOWN"


def test_direct_rows_tagged_direct():
    out = value_model.value_scores(_resid_df(), _scores(), set(_scores()["estate"]))
    q = out[out["estate"] == "QUEENSTOWN"].iloc[0]
    assert q["value_basis"] == "direct"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_value_model.py -k "proxy or direct_rows" -v`
Expected: FAIL (`value_basis` column does not exist).

- [ ] **Step 3: Implement the guard + tagging**

In `models/value_model.py`, add near the top (after `ESTATE_TOWN_ALIAS`, ~line 54):
```python
# Estates that are private-dominant: must NOT borrow an HDB-resale residual.
PRIVATE_DOMINANT_PROXIES = {"HOLLAND VILLAGE", "LENTOR"}
```

In `value_scores`, after `df["mult"] = mult` and before building the `reported` column, add:
```python
    df["value_basis"] = "direct"
```

Replace the alias-row loop (currently `:187-204`) with:
```python
    alias_rows = []
    for alias_estate, target_town in ESTATE_TOWN_ALIAS.items():
        alias_score_row = scores[scores["estate"] == alias_estate]
        target_resid_row = resid_df[resid_df["estate"] == target_town]
        if alias_score_row.empty or target_resid_row.empty:
            continue
        alias_score = float(alias_score_row["score"].iloc[0])

        if alias_estate in PRIVATE_DOMINANT_PROXIES:
            # invariant 2: never attribute an HDB residual to a private-dominant estate
            alias_rows.append(pd.Series({
                "estate": alias_estate, "segment": target_resid_row.iloc[0]["segment"],
                "n": 0, "resid_raw": np.nan, "resid_shrunk": np.nan,
                "trust": "band_only", "score": alias_score,
                "value_score": np.nan, "mult": np.nan, "value_band": "N/A",
                "value_basis": "no_hdb_segment",
                "reported": "no private-segment match",
            }))
            continue

        row = target_resid_row.iloc[0].copy()
        row["estate"] = alias_estate
        row["score"] = alias_score
        m = float(np.clip(np.exp(-row["resid_shrunk"]),
                          CFG["adj_cap_low"], CFG["adj_cap_high"]))
        row["mult"] = m
        row["value_score"] = alias_score * m
        row["value_band"] = band(row["value_score"])
        row["value_basis"] = f"proxy_from:{target_town}"   # non-independent: shares parent n
        row["reported"] = (str(round(row["value_score"], 2))
                           if row["trust"] == "decimal"
                           else row["value_band"] + " (band only, n<%d)" % CFG["trust_decimal_n"])
        alias_rows.append(row)
    if alias_rows:
        df = pd.concat([df, pd.DataFrame(alias_rows)], ignore_index=True)
    return df.sort_values("value_score", ascending=False, na_position="last")
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_value_model.py -k "proxy or direct_rows" -v`
Expected: PASS.

- [ ] **Step 5: Regenerate + review diff**

```bash
python models/value_model.py --scores data/provision_scores.csv --hdb data/hdb_resale.csv --out data/value_output.csv
```
Confirm HOLLAND VILLAGE / LENTOR now show `value_band=N/A`, DOVER/TAMPINES WEST show `value_basis=proxy_from:*`.

- [ ] **Step 6: Commit**

```bash
git add models/value_model.py tests/test_value_model.py data/value_output.csv
git commit -m "fix(value): tag alias rows; private-dominant proxies get no HDB residual

Adds value_basis (direct/proxy_from/no_hdb_segment). Stops HOLLAND VILLAGE and
LENTOR inheriting an HDB residual (invariant 2) and marks sub-area proxies as
non-independent so downstream never double-counts the shared parent n."
```

---

### Task 1.3: Zero-area filter in the residual regression

**Files:**
- Modify: `models/value_model.py:104-108` (extract `clean_psm`)
- Test: `tests/test_value_model.py`

**Interfaces:**
- Produces: `value_model.clean_psm(df, price_col, area_col) -> pd.DataFrame` with `_psm`,`_lnpsm`; drops non-finite/≤0.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_value_model.py`:
```python
def test_clean_psm_drops_zero_area():
    df = pd.DataFrame({"resale_price": [500000, 600000], "floor_area_sqm": [0, 100]})
    out = value_model.clean_psm(df, "resale_price", "floor_area_sqm")
    assert len(out) == 1
    assert np.isfinite(out["_lnpsm"]).all()
    assert (out["floor_area_sqm"] > 0).all()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_value_model.py::test_clean_psm_drops_zero_area -v`
Expected: FAIL (`clean_psm` undefined).

- [ ] **Step 3: Extract `clean_psm` and call it**

Add above `fit_segment`:
```python
def clean_psm(df, price_col, area_col):
    """Compute price-per-sqm and drop non-finite / non-positive rows (incl. area==0)."""
    df = df.copy()
    df["_psm"] = df[price_col] / df[area_col]
    df = df[(df[area_col] > 0) & np.isfinite(df["_psm"]) & (df["_psm"] > 0)]
    df["_lnpsm"] = np.log(df["_psm"])
    return df
```

In `fit_segment`, replace the three `_psm`/filter/`_lnpsm` lines (currently `:106-108`) with:
```python
    n_before = len(df)
    df = clean_psm(df, s["price_col"], s["area_col"])
    dropped = n_before - len(df)
    if dropped:
        print(f"  [{seg_name}] dropped {dropped} rows with non-finite/zero psm")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_value_model.py::test_clean_psm_drops_zero_area -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add models/value_model.py tests/test_value_model.py
git commit -m "fix(value): drop zero/non-finite area rows before ln(psm) regression"
```

---

### Task 1.4: Reconcile BASE_W with provision W (single source of truth)

**Files:**
- Modify: `models/liveability_model.py:121-154` (import W; extend S_GROUPS)
- Test: `tests/test_liveability_model.py`

**Interfaces:**
- Produces: `liveability_model.BASE_W` equals `provision_model.W` exactly.

**Context:** `BASE_W` silently drops `hawker`+`noise` (0.08) and disagrees on 5 weights, so `Gap = Liveability − Provision` mixes two weightings. Make BASE_W the same object source.

- [ ] **Step 1: Write the failing test**

`tests/test_liveability_model.py`:
```python
import liveability_model
import provision_model


def test_base_w_mirrors_provision_w():
    assert set(liveability_model.BASE_W) == set(provision_model.W)
    for k in provision_model.W:
        assert liveability_model.BASE_W[k] == provision_model.W[k], k


def test_every_base_component_in_an_s_group():
    grouped = {c for comps in liveability_model.S_GROUPS.values() for c in comps}
    assert set(liveability_model.BASE_W) <= grouped, set(liveability_model.BASE_W) - grouped
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_liveability_model.py -v`
Expected: FAIL (`hawker`/`noise` missing from BASE_W and from S_GROUPS).

- [ ] **Step 3: Source BASE_W from provision_model and group hawker/noise**

In `models/liveability_model.py`, replace the `BASE_W = {...}` literal (`:124-140`) with:
```python
from provision_model import W as _PROV_W  # single source of truth (invariant)

BASE_W: Dict[str, float] = dict(_PROV_W)
assert abs(sum(BASE_W.values()) - 1.0) < 1e-9, "BASE_W must sum to 1.0"
assert set(BASE_W) == set(_PROV_W), "BASE_W must mirror provision_model.W exactly"
```

Extend `S_GROUPS` (`:144-154`) so `hawker` joins S2 and `noise` joins S9:
```python
S_GROUPS: Dict[str, list] = {
    "S1": ["conn"],
    "S2": ["amen", "community", "hawker"],
    "S3": ["green", "sport"],
    "S4": ["sch", "childcare"],
    "S5": ["dens"],
    "S6": ["hlth", "eldercare"],
    "S7": ["mom"],
    "S8": ["infra"],
    "S9": ["env", "flood", "air_noise", "noise"],
}
```

Update the docstring audit table note (`:14-17`) to: `Base weights are imported from provision_model.W (17 components); see that file.`

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_liveability_model.py -v`
Expected: PASS.

- [ ] **Step 5: Regenerate + review diff**

```bash
python models/liveability_model.py --scores data/provision_scores.csv --pipeline data/pipeline_data.json --out data/liveability_matrix.csv
```
Expected: cells shift slightly (hawker/noise now weighted). Review.

- [ ] **Step 6: Commit**

```bash
git add models/liveability_model.py tests/test_liveability_model.py data/liveability_matrix.csv
git commit -m "fix(liveability): source BASE_W from provision.W; group hawker/noise

BASE_W silently dropped hawker+noise and disagreed on 5 weights, contaminating
the Gap. Now a single source of truth; hawker->S2, noise->S9."
```

---

### Task 1.5: Compute the Gap on raw scores, not the non-uniform band ladder

**Files:**
- Modify: `models/liveability_model.py:686-751` (store provision raw score; recompute gap)
- Test: `tests/test_liveability_model.py`

**Interfaces:**
- Produces: `gap_<persona>_<hz>` = continuous `liveability_score − provision_score`; new `gap_<persona>_<hz>_label` ∈ {punches_above, matched, over_equipped}.

**Context:** `BAND_NUMERIC` is non-uniform (B→C=1.0, others 0.5) and both inputs are banded before subtracting, collapsing the gap to {−1,0,0.5,1}. Subtract the continuous scores (both on the 1–5 scale).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_liveability_model.py`:
```python
def test_gap_label_dead_band():
    assert liveability_model.gap_label(0.2) == "matched"
    assert liveability_model.gap_label(0.8) == "punches_above"
    assert liveability_model.gap_label(-0.8) == "over_equipped"
    assert liveability_model.gap_label(0.5) == "matched"   # boundary inclusive
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_liveability_model.py::test_gap_label_dead_band -v`
Expected: FAIL (`gap_label` undefined).

- [ ] **Step 3: Add `gap_label`, store provision raw score, recompute gap**

Add near `BAND_NUMERIC` (~line 297):
```python
GAP_DEAD_BAND = 0.5  # ~1σ of two ±0.3 inputs combined; below this = "matched"


def gap_label(g: float) -> str:
    if g > GAP_DEAD_BAND:
        return "punches_above"
    if g < -GAP_DEAD_BAND:
        return "over_equipped"
    return "matched"
```

In `run()`, where the per-estate `record` is built (~line 710), add `provision_score`:
```python
        record: Dict = {
            "estate":           estate,
            "archetype":        ARCH.get(estate, ""),   # added in Task 1.7; "" until then
            "provision_band":   prov_band,
            "provision_score":  round(prov_score, 3),
            "D_T0":             d_t0,
            "D_T5":             d_t5,
            "D_T15":            d_t15,
        }
```
(If Task 1.7 is not yet done, drop the `archetype` line for now and add it in 1.7.)

Replace the gap block (`:745-751`) with:
```python
    # -- Gap on CONTINUOUS scores (both on the 1-5 scale). Band ladders are non-linear.
    prov_score_col = results["provision_score"]
    for pre in ["yf", "sp", "ret", "ls"]:
        for hz in ["T0", "T5", "T15"]:
            g = (results[f"{pre}_{hz}"] - prov_score_col).round(2)
            results[f"gap_{pre}_{hz}"] = g
            results[f"gap_{pre}_{hz}_label"] = g.map(gap_label)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_liveability_model.py::test_gap_label_dead_band -v`
Expected: PASS.

- [ ] **Step 5: Regenerate + sanity-check Holland Village**

```bash
python models/liveability_model.py --scores data/provision_scores.csv --pipeline data/pipeline_data.json --out data/liveability_matrix.csv
```
Expected: `gap_ls_T0` for HOLLAND VILLAGE is now a meaningful continuous value, not collapsed to 0.

- [ ] **Step 6: Commit**

```bash
git add models/liveability_model.py tests/test_liveability_model.py data/liveability_matrix.csv
git commit -m "fix(liveability): compute Gap on continuous scores + 3-bucket label

Band-numeric ladder was non-uniform and collapsed the gap to {-1,0,0.5,1}.
Now subtract raw 1-5 scores and bucket with a 0.5 dead-band."
```

---

### Task 1.6: Apply the veto cap to the structural (pre-D) score

**Files:**
- Modify: `models/liveability_model.py:562-580` (`score_estate`)
- Test: `tests/test_liveability_model.py`

**Context:** Vetoes encode structural service failures and should bind regardless of a transient disruption `D`. Currently the cap is applied after `raw *= d`, so a disruption can push the score below the cap and the veto never bites.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_liveability_model.py`:
```python
def test_veto_caps_pre_d():
    # amen==1 caps at C (3.49); with strong components raw>cap and D=0.8.
    comps = {c: 5.0 for c in liveability_model.BASE_W}
    comps["amen"] = 1.0
    score = liveability_model.score_estate(comps, "SinglePro", d=0.8)
    # structural cap 3.49 applied BEFORE D -> <= 3.49*0.8 = 2.792 (not 3.49)
    assert score <= 3.49 * 0.8 + 1e-6
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_liveability_model.py::test_veto_caps_pre_d -v`
Expected: FAIL (current order caps after D → ~3.49, not 2.79).

- [ ] **Step 3: Reorder cap before D**

Replace `score_estate` body (`:573-580`) with:
```python
    w = PERSONA_WEIGHTS[persona]
    raw = sum(w[c] * components.get(c, 0.0) for c in w)

    # Veto encodes a STRUCTURAL service failure -> cap the pre-D score so a
    # transient disruption (D<1) cannot mask it.
    cap = veto_cap(components, persona)
    raw = apply_cap(raw, cap)

    raw *= d
    return max(SOFT_FLOOR, raw)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_liveability_model.py::test_veto_caps_pre_d -v`
Expected: PASS.

- [ ] **Step 5: Regenerate + commit**

```bash
python models/liveability_model.py --scores data/provision_scores.csv --pipeline data/pipeline_data.json --out data/liveability_matrix.csv
git add models/liveability_model.py tests/test_liveability_model.py data/liveability_matrix.csv
git commit -m "fix(liveability): apply veto cap to structural pre-D score"
```

---

### Task 1.7: X-archetype N/R gate in liveability_model

**Files:**
- Modify: `models/liveability_model.py:646-755` (`run`: load archetypes, gate X)
- Test: `tests/test_liveability_model.py`

**Interfaces:**
- Consumes: `data/archetype_assignments.csv` (columns: estate, archetype, …).
- Produces: estates with archetype `X` emit a single N/R record (no scored matrix).

**Context:** CENTRAL AREA (X) is fully scored despite invariant 6 ("X exits with N/R"). `value_model`/`build_master` X-gating is handled in Phase 2; this task fixes the liveability leak.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_liveability_model.py`:
```python
import os

import pandas as pd


def test_x_archetype_emits_nr(tmp_path, data_dir):
    out = tmp_path / "lv.csv"
    liveability_model.run(
        scores_path=os.path.join(data_dir, "provision_scores.csv"),
        pipeline_path=os.path.join(data_dir, "pipeline_data.json"),
        out_path=str(out),
        archetypes_path=os.path.join(data_dir, "archetype_assignments.csv"),
    )
    df = pd.read_csv(out)
    ca = df[df["estate"] == "CENTRAL AREA"]
    assert not ca.empty
    assert (ca["yf_T0_band"] == "N/R").all()
    assert (ca["provision_band"] == "N/R").all()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_liveability_model.py::test_x_archetype_emits_nr -v`
Expected: FAIL (`run()` has no `archetypes_path`; CENTRAL AREA is scored).

- [ ] **Step 3: Load archetypes and gate X**

Change `run` signature (`:648-654`) to add `archetypes_path: Optional[str] = None`. After loading `df` (~line 658) add:
```python
    # -- Load archetype tags (for the X = non-residential N/R gate, invariant 6)
    ARCH: Dict[str, str] = {}
    if archetypes_path and __import__("os").path.exists(archetypes_path):
        adf = pd.read_csv(archetypes_path)
        adf["estate"] = adf["estate"].str.strip().str.upper()
        ARCH = dict(zip(adf["estate"], adf["archetype"].str.strip().str.upper()))
```

At the top of the per-estate loop (`for _, row in df.iterrows():`, ~line 688), after `estate = row["estate"]`:
```python
        if ARCH.get(estate) == "X":
            nr = {"estate": estate, "archetype": "X", "provision_band": "N/R",
                  "provision_score": float(row.get("score", 0.0)),
                  "D_T0": 1.0, "D_T5": 1.0, "D_T15": 1.0}
            for pre in ["yf", "sp", "ret", "ls"]:
                for hz in ["T0", "T5", "T15"]:
                    nr[f"{pre}_{hz}"] = None
                    nr[f"{pre}_{hz}_band"] = "N/R"
                nr[f"{pre}_arrow"] = "→"
                nr[f"{pre}_T15_arrow"] = "→"
            records.append(nr)
            continue
```

In the gap block (Task 1.5), guard against N/R rows so they don't produce a numeric gap:
```python
    for pre in ["yf", "sp", "ret", "ls"]:
        for hz in ["T0", "T5", "T15"]:
            live = pd.to_numeric(results[f"{pre}_{hz}"], errors="coerce")
            g = (live - prov_score_col).round(2)
            results[f"gap_{pre}_{hz}"] = g
            results[f"gap_{pre}_{hz}_label"] = g.map(
                lambda x: gap_label(x) if pd.notna(x) else "N/R")
```

Wire the CLI: add to `main()` (~line 785):
```python
    parser.add_argument("--archetypes", default="SG-Estate-Framework/data/archetype_assignments.csv",
                        help="archetype_assignments.csv (X = non-residential N/R gate)")
```
and pass `archetypes_path=args.archetypes` in the `run(...)` call.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_liveability_model.py::test_x_archetype_emits_nr -v`
Expected: PASS.

- [ ] **Step 5: Regenerate + commit**

```bash
python models/liveability_model.py --scores data/provision_scores.csv --pipeline data/pipeline_data.json --archetypes data/archetype_assignments.csv --out data/liveability_matrix.csv
git add models/liveability_model.py tests/test_liveability_model.py data/liveability_matrix.csv
git commit -m "fix(liveability): X-archetype (Central Area) emits N/R, not a scored matrix"
```

---

### Task 1.8: Momentum — no silent zeroing of mistyped inputs

**Files:**
- Modify: `models/momentum_model.py:73-78` (`item_contribution`)
- Test: `tests/test_momentum_model.py`

**Context:** `SIG.get(item.get('significance',''),0.0)` silently returns 0 for lowercase/typo'd keys while `type` is `.upper()`'d — asymmetric, violates "no silent error swallowing."

- [ ] **Step 1: Write the failing tests**

`tests/test_momentum_model.py`:
```python
import momentum_model


def test_lowercase_significance_not_silently_zeroed():
    hi = momentum_model.item_contribution(
        {"significance": "HIGH", "certainty": "CONFIRMED", "expected_year": 2028, "type": "POLYCLINIC"})
    lo = momentum_model.item_contribution(
        {"significance": "high", "certainty": "confirmed", "expected_year": 2028, "type": "polyclinic"})
    assert lo == hi and hi > 0


def test_unknown_significance_warns(capsys):
    c = momentum_model.item_contribution(
        {"significance": "ENORMOUS", "certainty": "CONFIRMED", "expected_year": 2028, "type": "MRT"})
    assert c == 0.0
    assert "unknown" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_momentum_model.py -v`
Expected: FAIL (lowercase → 0, and no warning emitted).

- [ ] **Step 3: Normalise case + warn on fallthrough**

Replace `item_contribution` (`:73-78`) with:
```python
def item_contribution(item):
    sig_key  = str(item.get('significance', '')).strip().upper()
    cert_key = str(item.get('certainty', '')).strip().upper()
    sig  = SIG.get(sig_key)
    cert = CERT.get(cert_key)
    if sig is None or cert is None:
        sys.stderr.write(
            f"WARN: unknown significance/certainty '{sig_key}'/'{cert_key}' "
            f"for item {item.get('description', item.get('type', '?'))} — counted as 0\n")
        return 0.0
    if 'expected_year' not in item:
        sys.stderr.write(
            f"WARN: missing expected_year for {item.get('description', '?')} — counted as 0\n")
        return 0.0
    tf   = time_factor(item['expected_year'])
    slip = SLIP_PREMIUM if str(item.get('type', '')).upper() in MRT_TYPES else 1.0
    return sig * cert * tf * slip
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_momentum_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add models/momentum_model.py tests/test_momentum_model.py
git commit -m "fix(momentum): normalise case; warn instead of silently zeroing unknown inputs"
```

---

### Task 1.9: Momentum — reconcile the MARINE PARADE manual addition

**Files:**
- Modify: `models/momentum_model.py:90-102` + `data/pipeline_data.json`

**Context (decision required):** `MANUAL_ADDITIONS["MARINE PARADE"]=0.255` bakes `time_factor=1.0` for a 2026 item, but the model's own rule (`time_factor`, `:67`) sets current-year items to 0 ("already delivered — not forward momentum"). The hardcode contradicts the invariant. This needs a **re-verification of the TEL Stage 5 opening date** (the dated-facts rule), then one of two fixes.

- [ ] **Step 1: Verify the fact**

Confirm the TEL5 (Bedok South TE30 / Sungei Bedok TE31) passenger-service date from a primary source (LTA). Record the verified year in the commit message.

- [ ] **Step 2: Apply the chosen fix**

- If TEL5 opens **2026 or earlier**: it is not forward momentum — remove the `MARINE PARADE` entry from `MANUAL_ADDITIONS` (`:96`) and update the docstring (`:34-35`).
- If TEL5 opens **2027+**: add it to `data/pipeline_data.json` as a normal `pipeline_items` entry with the correct `expected_year`, `type:"MRT"`, `certainty:"GAZETTED"`, `benefiting_estates:["EAST COAST"]`, and remove the hardcode so the normal discounted path reproduces the value.

- [ ] **Step 3: Add a guard test**

Add to `tests/test_momentum_model.py`:
```python
def test_no_current_year_forward_momentum():
    # a 2026 item must contribute 0 forward momentum
    assert momentum_model.item_contribution(
        {"significance": "HIGH", "certainty": "GAZETTED", "expected_year": 2026, "type": "MRT"}) == 0.0
```

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_momentum_model.py -v` → PASS
```bash
git add models/momentum_model.py data/pipeline_data.json tests/test_momentum_model.py
git commit -m "fix(momentum): reconcile MARINE PARADE TEL5 addition with time-discount rule

Verified TEL5 date: <YYYY>. <Removed hardcode | moved to pipeline_data.json>."
```

---

### Task 1.10: Doc-code component-count drift

**Files:**
- Modify: `models/provision_model.py:9`, `:414`; `SG-Estate-Framework/CLAUDE.md`; root `../CLAUDE.md`; `frameworks/1-provision-framework.md:45-58`; `models/liveability_model.py:24`
- Test: `tests/test_doc_consistency.py`

**Context:** Five different stated counts (9/13/15/17) for the 17-component `W`. Single-source the count and document `W_PRIVATE`.

- [ ] **Step 1: Write the guard test**

`tests/test_doc_consistency.py`:
```python
import provision_model


def test_w_has_17_components():
    assert len(provision_model.W) == 17


def test_provenance_keys_match_w():
    assert set(provision_model.PROVENANCE) == set(provision_model.W)


def test_w_private_same_keys_as_w():
    assert set(provision_model.W_PRIVATE) == set(provision_model.W)
```

- [ ] **Step 2: Run to verify it passes (code is internally consistent at 17)**

Run: `python -m pytest tests/test_doc_consistency.py -v`
Expected: PASS (these guard against future drift).

- [ ] **Step 3: Fix the prose counts**

- `models/provision_model.py:414`: already says "17 components" — confirm.
- Root `../CLAUDE.md`: change "9 components with documented weights" → "17 components (13 MEASURED + 3 PARTLY_MEASURED + 1 JUDGED)".
- `SG-Estate-Framework/CLAUDE.md`: change "`W` (15 components)" → "`W` (17 components)" and "`BASE_W` (13 components, after grouping)" → "`BASE_W` (17 components, sourced from `W`)".
- `models/liveability_model.py:24` docstring: "15 components" → "17 components (sourced from provision_model.W)".
- `frameworks/1-provision-framework.md:45-58`: regenerate the §1.1 table from `W` (17 rows with current weights conn .15 … flood .01), replacing the stale 9-component / 0.1709-weight table. Add a `W_PRIVATE` subsection documenting the private weight variant and its rationale (currently undocumented in any `.md`).

- [ ] **Step 4: Verify counts are gone**

Run: `grep -rn "9 components\|15 components\|13 components" .. --include=*.md --include=*.py`
Expected: no stale matches (only "17 components").

- [ ] **Step 5: Commit**

```bash
git add models/provision_model.py liveability_model.py ../CLAUDE.md CLAUDE.md frameworks/1-provision-framework.md tests/test_doc_consistency.py
git commit -m "docs: single-source 17-component count; document W_PRIVATE; guard test"
```

---

## Phase 1 wrap-up

- [ ] **Run the full suite:** `python -m pytest -v` → all PASS.
- [ ] **Capture the after-snapshot** and write a one-page diff summary (which estates' Value/Gap moved and why) into the commit / a `docs/` note:
```bash
python -m pytest -m snapshot -k before -v   # if not already captured
python -c "import sys; sys.path.insert(0,'tests'); import snapshot; snapshot.capture('after_phase1')"
```
- [ ] **Re-run the whole pipeline end-to-end** (provision → momentum → liveability → value) and confirm no errors and no empty-where-data-exists columns introduced.

---

## Self-Review (completed)

- **Spec coverage:** every Phase-1 row in the roadmap maps to a task here (1.1–1.10). Phase-0 harness (0.1–0.4) precedes them.
- **Placeholder scan:** no TBD/“handle errors”/“similar to”; every code step shows complete code.
- **Type consistency:** `build_formula(df, controls, month_col)`, `clean_psm(df, price_col, area_col)`, `value_basis` column, `gap_label(g)`, `score_estate(components, persona, d)`, `run(..., archetypes_path=None)`, `item_contribution(item)` are used consistently across tasks and tests.
- **Known cross-task dependency:** Task 1.7 adds the `archetype` field to the liveability `record`; Task 1.5 references `provision_score` in the record — 1.5 adds `provision_score`, 1.7 adds `archetype`. Execute 1.5 before 1.7 (or include both fields when 1.5 runs, as noted in 1.5 Step 3).
