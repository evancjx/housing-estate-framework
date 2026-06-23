# Phase 2: Wiring (shared aliases + build_master + consistent regeneration) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the headline `master_output.csv` reproducible and complete — wire in the three orphaned model outputs (employment, lease, archetype), enforce the X-gate, consolidate the divergent alias maps, and regenerate all outputs consistently.

**Architecture:** (1) One shared `models/aliases.py` holds the two DISTINCT alias concepts; the four models import from it (kills the divergence bugs F6/F7). (2) A new `models/build_master.py` left-joins the committed model outputs onto the liveability matrix (the richest spine), enforces the X-archetype N/R gate, and emits explicit coverage flags instead of blank cells. (3) One controlled full-pipeline regeneration realizes the alias fixes + the deferred Marine Parade momentum fix, with a bounded expected-change set. (4) Docs are corrected.

**Tech Stack:** Python 3, pandas, pytest. Run from repo root `SG-Estate-Framework/`. Tests exist (Phase 0 harness).

## Global Constraints
- Install already present (`pandas numpy statsmodels`). Use `python3`.
- **Two alias concepts are distinct — never merge them into one dict:** `PIPELINE_NAME_ALIAS` (pipeline benefiting-estate name → canonical estate; momentum + liveability) vs `ESTATE_TOWN_ALIAS` (estate → HDB town for transaction joins; value + lease).
- **Never blend HDB and private.** Private Value is NOT surfaced in this phase — `build_master` flags it `not_covered` (Phase 3 ingests it). Do not touch the user's uncommitted WIP (`data/ura_private.csv`, `data/value_private.csv`, `scrapers/`, `data/ura_raw/`, `data/ura_private_new.csv`, `comparison_table.html`).
- **X-archetype (CENTRAL AREA) emits N/R**, never a scored value across any model's columns.
- **No empty-where-data-exists columns** in master_output: every cell is a real value or an explicit flag (`N/R` / `not_covered` / `no_data`).
- **`build_master` reads CSVs with `keep_default_na=False`** so the `"N/A"`/`"N/R"` string flags from Phase 1 survive (don't become NaN).
- When code behavior changes, regenerate the affected committed CSVs in the same commit.
- Commits scoped (`git add` only the task's files). End commit bodies with the Co-Authored-By + Claude-Session footer.

---

## File Structure

| File | Responsibility |
|---|---|
| `models/aliases.py` | NEW — the two shared alias dicts + helpers + `PRIVATE_DOMINANT_PROXIES` |
| `models/momentum_model.py` | import pipeline alias; delete local copy |
| `models/liveability_model.py` | import pipeline alias; delete local copy |
| `models/value_model.py` | import estate-town alias + PRIVATE_DOMINANT_PROXIES; delete local copies |
| `models/lease_risk_model.py` | import estate-town alias; delete local copy (keep MANUAL_OVERRIDES) |
| `models/build_master.py` | NEW — the joiner |
| `tests/test_aliases.py` | alias single-source + conflict-resolution tests |
| `tests/test_build_master.py` | joiner unit tests on synthetic inputs |
| `data/*.csv` | regenerated outputs (Task 2.3) |
| `CLAUDE.md`, framework docs | pipeline + doc-hygiene corrections (Task 2.4) |

---

## Task 2.1: Shared alias module (resolves the divergence bugs)

**Files:**
- Create: `models/aliases.py`, `tests/test_aliases.py`
- Modify: `models/momentum_model.py`, `models/liveability_model.py`, `models/value_model.py`, `models/lease_risk_model.py`

**Interfaces:**
- Produces: `aliases.PIPELINE_NAME_ALIAS`, `aliases.ESTATE_TOWN_ALIAS`, `aliases.PRIVATE_DOMINANT_PROXIES`, `aliases.canonicalise_pipeline_name(name)`, `aliases.estate_to_town(estate)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_aliases.py`:
```python
import aliases
import momentum_model
import liveability_model
import value_model
import lease_risk_model


def test_pipeline_conflicts_resolved():
    # Boon Lay / Taman Jurong belong to Jurong West (momentum previously wrongly mapped them to Jurong East)
    assert aliases.canonicalise_pipeline_name("BOON LAY") == "JURONG WEST"
    assert aliases.canonicalise_pipeline_name("TAMAN JURONG") == "JURONG WEST"
    # Buona Vista is in Queenstown planning area (liveability previously wrongly mapped it to Holland Village)
    assert aliases.canonicalise_pipeline_name("BUONA VISTA") == "QUEENSTOWN"
    # Real estates map to themselves (no stale fold)
    assert aliases.canonicalise_pipeline_name("JURONG WEST") == "JURONG WEST"
    assert aliases.canonicalise_pipeline_name("KALLANG") == "KALLANG"


def test_pipeline_alias_single_source():
    # momentum.canonical and liveability.canonicalise_estate are the SAME shared function
    assert momentum_model.canonical is liveability_model.canonicalise_estate
    assert momentum_model.canonical("BUONA VISTA") == "QUEENSTOWN"


def test_estate_town_single_source():
    assert value_model.ESTATE_TOWN_ALIAS is aliases.ESTATE_TOWN_ALIAS
    assert lease_risk_model.ESTATE_TOWN_ALIAS is aliases.ESTATE_TOWN_ALIAS
    assert value_model.PRIVATE_DOMINANT_PROXIES is aliases.PRIVATE_DOMINANT_PROXIES


def test_estate_town_unchanged_entries():
    assert aliases.ESTATE_TOWN_ALIAS["CANBERRA"] == "SEMBAWANG"
    assert aliases.ESTATE_TOWN_ALIAS["HOLLAND VILLAGE"] == "QUEENSTOWN"
    assert aliases.ESTATE_TOWN_ALIAS["LENTOR"] == "ANG MO KIO"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_aliases.py -v`
Expected: FAIL (`No module named 'aliases'`).

- [ ] **Step 3: Create `models/aliases.py`**

```python
"""Shared estate-name alias maps — single source of truth for ALL models.

TWO DISTINCT concepts. Do NOT merge them:
  PIPELINE_NAME_ALIAS — pipeline/research benefiting-estate names -> canonical estate.
                        Used by momentum_model + liveability_model.
  ESTATE_TOWN_ALIAS   — estate -> HDB town, for joining resale transactions.
                        Used by value_model + lease_risk_model.
"""

PIPELINE_NAME_ALIAS = {
    "BIDADARI":       "WOODLEIGH",
    "MARSILING":      "WOODLANDS",
    "KAKI BUKIT":     "BEDOK",
    "EAST COAST":     "MARINE PARADE",
    "BOON LAY":       "JURONG WEST",    # town centre of Jurong West (momentum had JURONG EAST — wrong)
    "TAMAN JURONG":   "JURONG WEST",    # physically in Jurong West planning area
    "BUONA VISTA":    "QUEENSTOWN",     # Buona Vista is in Queenstown planning area (liveability had HOLLAND VILLAGE — wrong)
    "NOVENA":         "TOA PAYOH",
    "WEST COAST":     "CLEMENTI",
    "TAMPINES NORTH": "TAMPINES",
    "YEW TEE":        "CHOA CHU KANG",
    # JURONG WEST, KALLANG: now real estates in estates.csv — map to themselves (no stale fold).
}

ESTATE_TOWN_ALIAS = {
    "CANBERRA":        "SEMBAWANG",
    "BOON KENG":       "KALLANG/WHAMPOA",
    "KALLANG":         "KALLANG/WHAMPOA",
    "WOODLEIGH":       "TOA PAYOH",
    "DOVER":           "QUEENSTOWN",
    "TAMPINES WEST":   "TAMPINES",
    "TAMPINES EAST":   "TAMPINES",
    "LENTOR":          "ANG MO KIO",      # indicative proxy; lease_risk overrides via MANUAL_OVERRIDES
    "HOLLAND VILLAGE": "QUEENSTOWN",      # private-dominant; HDB proxy only
}

# Private-dominant estates: must NOT borrow an HDB-resale residual (value_model).
PRIVATE_DOMINANT_PROXIES = {"HOLLAND VILLAGE", "LENTOR"}


def canonicalise_pipeline_name(name):
    """Pipeline/research estate name -> canonical estate."""
    return PIPELINE_NAME_ALIAS.get(str(name).strip().upper(), str(name).strip().upper())


def estate_to_town(estate):
    """Estate -> HDB town for transaction joins."""
    return ESTATE_TOWN_ALIAS.get(str(estate).strip().upper(), str(estate).strip().upper())
```

- [ ] **Step 4: Point momentum_model at the shared map**

In `models/momentum_model.py`: DELETE the local `ALIAS_MAP = {...}` block and the `def canonical(name): ...` function. Add near the top imports:
```python
from aliases import PIPELINE_NAME_ALIAS as ALIAS_MAP, canonicalise_pipeline_name as canonical
```
(Keep `ESTATE_NAMES`, `MANUAL_ADDITIONS`, everything else. `canonical(...)` call sites stay valid.)

- [ ] **Step 5: Point liveability_model at the shared map**

In `models/liveability_model.py`: DELETE the local `ALIAS_MAP: Dict[str, str] = {...}` block and `def canonicalise_estate(name): ...`. Add to the imports near the top:
```python
from aliases import PIPELINE_NAME_ALIAS as ALIAS_MAP, canonicalise_pipeline_name as canonicalise_estate
```

- [ ] **Step 6: Point value_model + lease_risk_model at the shared estate-town map**

In `models/value_model.py`: DELETE the local `ESTATE_TOWN_ALIAS = {...}` block and the `PRIVATE_DOMINANT_PROXIES = {...}` line; add near the top imports:
```python
from aliases import ESTATE_TOWN_ALIAS, PRIVATE_DOMINANT_PROXIES
```
In `models/lease_risk_model.py`: DELETE the local `ESTATE_TOWN_ALIAS = {...}` block; add near the imports:
```python
from aliases import ESTATE_TOWN_ALIAS
```
(Keep `MANUAL_OVERRIDES` — it is lease-specific and short-circuits before the alias lookup, so LENTOR in the shared map is harmless.)

- [ ] **Step 7: Run to verify GREEN + full suite**

Run: `python3 -m pytest tests/test_aliases.py -v` → PASS
Run: `python3 -m pytest -q` → all PASS (no import breakage).

- [ ] **Step 8: Commit**

```bash
git add models/aliases.py tests/test_aliases.py models/momentum_model.py models/liveability_model.py models/value_model.py models/lease_risk_model.py
git commit -m "refactor(aliases): single-source the two alias maps; resolve momentum/liveability divergence

PIPELINE_NAME_ALIAS (momentum+liveability) and ESTATE_TOWN_ALIAS (value+lease) now
live in models/aliases.py. Resolves conflicts: BOON LAY/TAMAN JURONG->JURONG WEST,
BUONA VISTA->QUEENSTOWN, and drops stale JURONG WEST/KALLANG folds (now real estates).
ESTATE_TOWN_ALIAS consolidation is output-neutral. Data regenerated in Task 2.3."
```
(append the footer)

---

## Task 2.2: `build_master.py` — the reproducible joiner

**Files:**
- Create: `models/build_master.py`, `tests/test_build_master.py`

**Interfaces:**
- Produces: `build_master.build(args) -> pd.DataFrame`; CLI writes `data/master_output.csv`.
- Consumes (all keyed on `estate`, read with `keep_default_na=False`): `liveability_matrix.csv` (spine — has estate, archetype, provision_band, provision_score, *_band, gap_*, gap_*_label), `provision_scores.csv` (score_private, measured_only), `value_output.csv` (value_score, value_band, value_basis, n), `employment_scores_T0.csv` (emp_score, emp_band, best_node, worst_node), `lease_risk.csv` (lease_score, lease_band, source), `archetype_assignments.csv` (archetype, confidence).

- [ ] **Step 1: Write the failing tests**

`tests/test_build_master.py`:
```python
import os

import pandas as pd
import pytest

import build_master


def _write(tmp, name, df):
    p = os.path.join(tmp, name)
    df.to_csv(p, index=False)
    return p


@pytest.fixture
def inputs(tmp_path):
    t = str(tmp_path)
    live = pd.DataFrame({
        "estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
        "archetype": ["B", "X", "D"],
        "provision_band": ["B", "N/R", "B+"],
        "provision_score": [3.63, 4.36, 4.01],
        "yf_T0_band": ["B", "N/R", "B+"],
        "gap_yf_T0": [0.0, None, 0.0],
        "gap_yf_T0_label": ["matched", "N/R", "matched"],
    })
    prov = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                         "score_private": [3.7, 4.4, 4.1], "measured_only": [False, False, False]})
    vhdb = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                         "value_score": [2.73, 3.55, ""], "value_band": ["D", "B", "N/A"],
                         "value_basis": ["direct", "direct", "no_hdb_segment"], "n": [4063, 1815, 0]})
    emp = pd.DataFrame({"estate": ["BISHAN", "HOLLAND VILLAGE"], "emp_score": [3.5, 3.8],
                        "emp_band": ["B", "B"], "best_node": ["cbd", "one_north"], "worst_node": ["changi", "changi"]})
    lease = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                          "lease_score": [4.0, 3.0, 5.0], "lease_band": ["B+", "B", "A"],
                          "source": ["hdb_resale", "hdb_resale", "manual_override"]})
    arch = pd.DataFrame({"estate": ["BISHAN", "CENTRAL AREA", "HOLLAND VILLAGE"],
                         "archetype": ["B", "X", "D"], "confidence": ["High", "High", "Med"]})
    return dict(liveability=_write(t,"live.csv",live), provision=_write(t,"prov.csv",prov),
                value_hdb=_write(t,"v.csv",vhdb), employment=_write(t,"emp.csv",emp),
                lease=_write(t,"lease.csv",lease), archetypes=_write(t,"arch.csv",arch),
                out=os.path.join(t,"master.csv"))


def _ns(d):
    import argparse
    return argparse.Namespace(**d)


def test_joins_all_models(inputs):
    m = build_master.build(_ns(inputs))
    row = m[m["estate"] == "BISHAN"].iloc[0]
    assert row["emp_band"] == "B"          # employment wired in
    assert row["lease_band"] == "B+"       # lease wired in
    assert row["value_hdb_band"] == "D"    # HDB value wired in
    assert row["archetype"] == "B"


def test_x_archetype_is_nr(inputs):
    m = build_master.build(_ns(inputs))
    ca = m[m["estate"] == "CENTRAL AREA"].iloc[0]
    assert ca["value_hdb_band"] == "N/R"
    assert ca["emp_band"] == "N/R"
    assert ca["lease_band"] == "N/R"


def test_missing_employment_row_flagged_not_blank(inputs):
    m = build_master.build(_ns(inputs))
    ca = m[m["estate"] == "CENTRAL AREA"].iloc[0]
    # CENTRAL AREA has no employment row; it is X so becomes N/R (not blank)
    assert ca["emp_band"] in ("N/R", "no_data")
    assert ca["emp_band"] != ""


def test_private_value_flagged_not_covered(inputs):
    m = build_master.build(_ns(inputs))
    assert (m["value_private_band"].isin(["not_covered", "N/R"])).all()


def test_private_dominant_keeps_no_hdb_segment(inputs):
    m = build_master.build(_ns(inputs))
    hv = m[m["estate"] == "HOLLAND VILLAGE"].iloc[0]
    assert hv["value_hdb_basis"] == "no_hdb_segment"   # survived keep_default_na=False


def test_missing_required_input_fails_loudly(inputs):
    bad = dict(inputs)
    bad["lease"] = "/nonexistent/lease.csv"
    with pytest.raises(SystemExit):
        build_master.build(_ns(bad))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_build_master.py -v`
Expected: FAIL (`No module named 'build_master'`).

- [ ] **Step 3: Create `models/build_master.py`**

```python
#!/usr/bin/env python3
"""Join all model outputs into one reproducible master_output.csv.

Left-joins (on canonical UPPERCASE estate) the liveability matrix (the richest
spine) with provision extras, HDB Value, employment, lease, and archetype.
Enforces the X-archetype N/R gate, emits explicit coverage flags instead of
blank cells, and fails loudly if a required input is missing. Private Value is
structurally supported but flagged 'not_covered' until Phase 3 ingests it.

RUN:
  python3 models/build_master.py            # uses data/ defaults
"""
import argparse
import os
import sys

import pandas as pd

_NR = "N/R"
_NODATA = "no_data"
_NOTCOV = "not_covered"


def _load(path, name):
    if not path or not os.path.exists(path):
        sys.exit(f"build_master: required input '{name}' not found: {path}")
    df = pd.read_csv(path, keep_default_na=False)  # keep "N/A"/"N/R" strings, not NaN
    df["estate"] = df["estate"].astype(str).str.strip().str.upper()
    return df


def build(args):
    live = _load(args.liveability, "liveability")
    prov = _load(args.provision, "provision")
    vhdb = _load(args.value_hdb, "value_hdb")
    emp = _load(args.employment, "employment")
    lease = _load(args.lease, "lease")
    arch = _load(args.archetypes, "archetypes").drop_duplicates(subset="estate", keep="first")

    m = live.copy()
    if "archetype" not in m.columns:
        m = m.merge(arch[["estate", "archetype"]], on="estate", how="left")
    m = m.merge(prov[["estate", "score_private", "measured_only"]]
                .rename(columns={"score_private": "provision_private"}), on="estate", how="left")
    m = m.merge(vhdb[["estate", "value_score", "value_band", "value_basis", "n"]]
                .rename(columns={"value_score": "value_hdb_score", "value_band": "value_hdb_band",
                                 "value_basis": "value_hdb_basis", "n": "value_hdb_n"}),
                on="estate", how="left")
    m = m.merge(emp[["estate", "emp_score", "emp_band", "best_node", "worst_node"]], on="estate", how="left")
    m = m.merge(lease[["estate", "lease_score", "lease_band", "source"]]
                .rename(columns={"source": "lease_source"}), on="estate", how="left")
    m = m.merge(arch[["estate", "confidence"]].rename(columns={"confidence": "archetype_confidence"}),
                on="estate", how="left")

    # blank merged cells -> explicit no_data flag (string cols and numeric-as-string)
    flag_cols = ["value_hdb_score", "value_hdb_band", "value_hdb_basis", "value_hdb_n",
                 "emp_score", "emp_band", "best_node", "worst_node",
                 "lease_score", "lease_band", "lease_source",
                 "provision_private", "measured_only", "archetype_confidence"]
    for c in flag_cols:
        m[c] = m[c].astype(str).replace("", _NODATA).replace("nan", _NODATA)

    # private Value not yet ingested (Phase 3)
    m["value_private_band"] = _NOTCOV
    m["value_private_basis"] = _NOTCOV

    # X-archetype N/R gate: scored fields become N/R for non-residential strategic districts
    xmask = m["archetype"].astype(str).str.upper() == "X"
    nr_cols = ["value_hdb_score", "value_hdb_band", "value_hdb_basis", "value_hdb_n",
               "emp_score", "emp_band", "best_node", "worst_node",
               "lease_score", "lease_band", "lease_source",
               "value_private_band", "value_private_basis"]
    for c in nr_cols:
        m.loc[xmask, c] = _NR

    m.to_csv(args.out, index=False)
    print(f"build_master: wrote {len(m)} estates x {len(m.columns)} cols -> {args.out}")
    for c in m.columns:
        if set(m[c].astype(str)) <= {_NODATA, _NR, _NOTCOV, ""}:
            print(f"  WARN: column '{c}' is entirely placeholder — check wiring")
    return m


def main():
    # __file__-relative so it works from any cwd (matches lease_risk_model.py)
    D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    ap = argparse.ArgumentParser(description="Join model outputs into master_output.csv")
    ap.add_argument("--liveability", default=f"{D}/liveability_matrix.csv")
    ap.add_argument("--provision", default=f"{D}/provision_scores.csv")
    ap.add_argument("--value_hdb", default=f"{D}/value_output.csv")
    ap.add_argument("--employment", default=f"{D}/employment_scores_T0.csv")
    ap.add_argument("--lease", default=f"{D}/lease_risk.csv")
    ap.add_argument("--archetypes", default=f"{D}/archetype_assignments.csv")
    ap.add_argument("--out", default=f"{D}/master_output.csv")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify GREEN + full suite**

Run: `python3 -m pytest tests/test_build_master.py -v` → PASS (6 tests)
Run: `python3 -m pytest -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add models/build_master.py tests/test_build_master.py
git commit -m "feat(build_master): reproducible joiner wiring employment+lease+archetype with X-gate + coverage flags"
```
(append the footer)

---

## Task 2.3: Controlled full-pipeline regeneration (realizes alias + momentum fixes)

**Files:**
- Modify (regenerate): `data/judged_inputs.csv`, `data/provision_scores.csv`, `data/liveability_matrix.csv`, `data/value_output.csv`, `data/master_output.csv`

**This is a controlled data regeneration, not a TDD task.** The verification IS the diff review against a bounded expected-change set.

> **IMPORTANT (corrected after a BLOCKED run):** the committed `provision_scores.csv` was generated **without** `--eldercare` and `--air_noise` (both components sit at floor defaults: eldercare=1.0, air_noise=5.0 for every estate). Therefore the reproducing command does **NOT** pass those two flags. Wiring in the real `data/eldercare.csv` + `data/air_noise_corridors.csv` layers shifts ~35 estates (some band changes, e.g. WOODLANDS, PUNGGOL) and is a deliberate **Phase 3** data-completeness task — keep it OUT of this bounded regeneration.

**Expected-change set (everything else must stay byte-identical):**
- **Momentum / provision shifts** for: `JURONG EAST` (loses Boon Lay/Taman Jurong/Jurong-West credit → mom may drop), `JURONG WEST` (gains own + Boon Lay/Taman Jurong → mom may rise), `KALLANG` (gains own → may rise), `BOON KENG` (loses Kallang fold → may drop), `MARINE PARADE` (TEL5=2026 → mom 2→1, provision 2.90→2.86, stays D).
- **Liveability shifts** for: `QUEENSTOWN` and `HOLLAND VILLAGE` (Buona Vista pipeline now boosts Queenstown, not Holland Village) plus the provision-driven shifts above.

- [ ] **Step 1: Sanity — confirm the provision command reproduces today's committed file BEFORE changing anything**

Run the command that reproduces the committed baseline — **without** `--eldercare`/`--air_noise` (see the IMPORTANT note above):
```bash
python3 models/provision_model.py --estates data/estates.csv \
  --mrt data/mrt_layer.csv --bus data/bus_routes.csv \
  --clinics data/chas.csv --polyclinics data/polyclinics.csv \
  --schools data/schools.csv --parks data/parks.csv \
  --markets data/markets.csv --supermarkets data/supermarkets.csv \
  --childcare data/childcare.csv --community data/community.csv \
  --sport data/sport.csv --flood data/flood_risk.csv \
  --noise data/expressways.csv \
  --covered_linkway data/covered_linkway.csv \
  --judged data/judged_inputs.csv --out /tmp/prov_check.csv
git --no-pager diff --no-index data/provision_scores.csv /tmp/prov_check.csv | head -40
```
Expected: NO diff (byte-identical). If it differs, STOP and report — do not proceed.

- [ ] **Step 2: Regenerate momentum → judged_inputs (alias + Marine Parade fixes realized here)**

```bash
python3 models/momentum_model.py --pipeline data/pipeline_data.json --judged data/judged_inputs.csv --out /tmp/judged_updated.csv --verbose
git --no-pager diff --no-index data/judged_inputs.csv /tmp/judged_updated.csv
```
Inspect the `mom` diff. CONFIRM only the expected-change estates' `mom` values move (Jurong East/West, Kallang, Boon Keng, Marine Parade). If any OTHER estate's mom changes, STOP and report with the diff. If confirmed, copy the mom column into the real file:
```bash
cp /tmp/judged_updated.csv data/judged_inputs.csv
```

- [ ] **Step 3: Regenerate provision → liveability → value → master**

```bash
# provision (SAME layer set as Step 1 — NO --eldercare/--air_noise, to stay byte-identical except for the momentum change)
python3 models/provision_model.py --estates data/estates.csv \
  --mrt data/mrt_layer.csv --bus data/bus_routes.csv --clinics data/chas.csv \
  --polyclinics data/polyclinics.csv --schools data/schools.csv --parks data/parks.csv \
  --markets data/markets.csv --supermarkets data/supermarkets.csv \
  --childcare data/childcare.csv --community data/community.csv --sport data/sport.csv \
  --flood data/flood_risk.csv --noise data/expressways.csv \
  --covered_linkway data/covered_linkway.csv --judged data/judged_inputs.csv \
  --out data/provision_scores.csv
# liveability (with archetypes for the X-gate)
python3 models/liveability_model.py --scores data/provision_scores.csv \
  --pipeline data/pipeline_data.json --archetypes data/archetype_assignments.csv \
  --out data/liveability_matrix.csv
# value (HDB)
python3 models/value_model.py --scores data/provision_scores.csv \
  --hdb data/hdb_resale.csv --out data/value_output.csv
# master
python3 models/build_master.py
```

- [ ] **Step 4: Review the diffs against the expected-change set**

```bash
git --no-pager diff --stat data/provision_scores.csv data/liveability_matrix.csv data/value_output.csv
```
For each changed estate, confirm it is in the expected-change set. Spot-check: MARINE PARADE provision ≈ 2.86 (band D); QUEENSTOWN/HOLLAND VILLAGE liveability T5 moved (Buona Vista re-attribution). Confirm `master_output.csv` has NO blank cells in emp/lease/value columns and CENTRAL AREA shows N/R. If anything outside the expected set changed materially, STOP and report.

- [ ] **Step 5: Commit**

```bash
git add data/judged_inputs.csv data/provision_scores.csv data/liveability_matrix.csv data/value_output.csv data/master_output.csv
git commit -m "data: regenerate pipeline with consolidated aliases + Marine Parade momentum fix

Realizes Task 2.1 alias resolution (Boon Lay/Taman Jurong->Jurong West, Buona Vista
->Queenstown, Jurong West/Kallang un-folded) and the deferred 1.9 Marine Parade fix
(TEL5=2026 -> mom 2->1, provision 2.90->2.86, band stays D). master_output.csv now
joins employment+lease+archetype with X-gate via build_master.py."
```
(append the footer; do NOT add the user's WIP files)

---

## Task 2.4: Docs — pipeline wiring + provision command fix + deferred doc-hygiene

**Files:**
- Modify: `SG-Estate-Framework/CLAUDE.md`, `models/value_model.py` (comment), `models/liveability_model.py` (docstrings)

- [ ] **Step 1: Fix the CLAUDE.md pipeline section**

In `SG-Estate-Framework/CLAUDE.md`:
- Add `build_master.py` as the pipeline tail in the architecture diagram and the Commands section: `python3 models/build_master.py` after value/liveability/lease/employment.
- Do NOT add `--eldercare`/`--air_noise` to the provision command — the committed `provision_scores.csv` was generated WITHOUT them, so the current (no-flags) command correctly reproduces it. Instead add a one-line note next to the provision command: "eldercare/air_noise layers (`data/eldercare.csv`, `data/air_noise_corridors.csv`) exist but are not yet wired into the canonical run — Phase 3 ingests them (will shift some bands)."

- [ ] **Step 2: Deferred doc-hygiene (zero behavior change)**

- `models/value_model.py`: the section banner `# 3. CORE — fit ln(price_psm) ~ score + controls + month` → `# 3. CORE — fit ln(price_psm) ~ controls + C(month), take residuals` (score was removed in Phase 1).
- `models/liveability_model.py`: `score_estate` docstring `Σ(w_persona(i) × S_i) × D / Then capped by veto rules` → reflect cap-before-D order (e.g. `Σ(w_persona(i) × S_i), capped by veto, then × D`).
- `models/liveability_model.py` docstring S-group block: `S7 (momentum) → mom (base 0.05)` → `(base 0.04)`; and any other stale base value in that block that disagrees with `provision_model.W` (amen, community, etc. — match W) OR replace the per-line base numbers with "(base weights: see provision_model.W)".

- [ ] **Step 3: Verify nothing broke**

Run: `python3 -m pytest -q` → all PASS (doc edits don't touch behavior).

- [ ] **Step 4: Commit**

```bash
git add SG-Estate-Framework/CLAUDE.md models/value_model.py models/liveability_model.py
git commit -m "docs: wire build_master into pipeline; fix provision command (eldercare/air_noise); doc-hygiene"
```
(append the footer)

---

## Task 2.5: Complete archetype coverage (close the master_output blank-cell gap)

**Files:**
- Modify: `data/archetype_assignments.csv`
- Create: add `test_archetype_coverage` to `tests/test_build_master.py`
- Regenerate: `data/liveability_matrix.csv`, `data/master_output.csv`

**Context:** Task 2.3's review found `JURONG WEST` and `KALLANG` (de-folded in Task 2.1) plus `HOLLAND VILLAGE` are absent from `archetype_assignments.csv`, so their `archetype` cell is blank in master_output — undercutting the no-blank-cells goal. Assign the canonical tags (matching the prior hand-assembled master): `HOLLAND VILLAGE` → `D` (private lifestyle enclave), `JURONG WEST` → `B`, `KALLANG` → `B` (mature HDB towns).

- [ ] **Step 1: Write the failing coverage test**

Add to `tests/test_build_master.py`:
```python
def test_archetype_coverage_complete():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = os.path.join(here, "data")
    est = pd.read_csv(os.path.join(data, "estates.csv"))
    arch = pd.read_csv(os.path.join(data, "archetype_assignments.csv"))
    est_names = set(est["estate"].str.strip().str.upper())
    arch_names = set(arch["estate"].str.strip().str.upper())
    missing = est_names - arch_names
    assert not missing, f"estates with no archetype: {missing}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_build_master.py::test_archetype_coverage_complete -v`
Expected: FAIL — missing `{HOLLAND VILLAGE, JURONG WEST, KALLANG}`.

- [ ] **Step 3: Add the three archetype rows**

Append to `data/archetype_assignments.csv` (match the existing column order `estate,archetype,confidence,rationale`):
```
HOLLAND VILLAGE,D,High,Private/mixed-use lifestyle enclave; F&B/character-driven; canonical D archetype
JURONG WEST,B,High,Large mature HDB town (Boon Lay/Pioneer/Lakeside); de-folded from Jurong East alias in v2
KALLANG,B,High,Central mature HDB town (Kallang/Whampoa); de-folded from Boon Keng alias in v2
```
(If `archetype_assignments.csv` contains a duplicate `CENTRAL AREA` row, remove the duplicate while here.)

- [ ] **Step 4: Run to verify GREEN**

Run: `python3 -m pytest tests/test_build_master.py::test_archetype_coverage_complete -v` → PASS

- [ ] **Step 5: Regenerate liveability + master (bounded: only the 3 archetype cells change, no scores)**

```bash
python3 models/liveability_model.py --scores data/provision_scores.csv \
  --pipeline data/pipeline_data.json --archetypes data/archetype_assignments.csv \
  --out data/liveability_matrix.csv
python3 models/build_master.py
git --no-pager diff --stat data/liveability_matrix.csv data/master_output.csv
```
Confirm: the liveability diff is ONLY the `archetype` column for HOLLAND VILLAGE/JURONG WEST/KALLANG (blank → D/B/B); NO score/band/gap changes. master_output now has a non-blank `archetype` for every estate. If any score changed, STOP and report.

- [ ] **Step 6: Commit**

```bash
git add data/archetype_assignments.csv data/liveability_matrix.csv data/master_output.csv tests/test_build_master.py
git commit -m "data: complete archetype coverage (Holland Village D, Jurong West/Kallang B); regen liveability+master"
```
(append the footer)

---

## Task 2.6: Reconcile the fifth alias map (ingest_hdb_upgrading.py) + disclose data divergence

**Files:**
- Modify: `models/ingest_hdb_upgrading.py`
- Create: add a guard test to `tests/test_aliases.py`
- Modify: `SG-Estate-Framework/CLAUDE.md` (disclosure note)

**Context (found by the final whole-branch review):** `ingest_hdb_upgrading.py` is a FIFTH alias map, upstream of momentum (it regenerates the NRP/LUP `pipeline_items` in `pipeline_data.json`). Its local `ALIAS_MAP` (lines 69-83) and `NAME_HINTS` (lines 90-159) still encode the exact bugs Task 2.1 fixed (`BOON LAY/TAMAN JURONG/JURONG WEST→JURONG EAST`, `KALLANG→BOON KENG`). The committed `pipeline_data.json` is only consistent because nobody has re-run this network-fed ingester. Make the CODE single-source so the next refresh is correct; disclose that the committed data carries legacy attribution (the ingester needs network, so a full `pipeline_data.json` regeneration + cascade is deferred to Phase 3).

- [ ] **Step 1: Write the failing guard test**

Add to `tests/test_aliases.py`:
```python
def test_ingest_hdb_upgrading_uses_shared_alias():
    import ingest_hdb_upgrading as ih
    assert ih.ALIAS_MAP is aliases.PIPELINE_NAME_ALIAS
    hints = dict(ih.NAME_HINTS)
    assert hints["JURONG WEST"] == "JURONG WEST"
    assert hints["BOON LAY"] == "JURONG WEST"
    assert hints["TAMAN JURONG"] == "JURONG WEST"
    assert hints["KALLANG"] == "KALLANG"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_aliases.py::test_ingest_hdb_upgrading_uses_shared_alias -v`
Expected: FAIL (local ALIAS_MAP is a separate dict; NAME_HINTS map those names to JURONG EAST / BOON KENG).

- [ ] **Step 3: Reconcile the ingester**

In `models/ingest_hdb_upgrading.py`:
- DELETE the local `ALIAS_MAP = {...}` literal (lines ~67-83) and the "Mirror its ALIAS_MAP" comment; add `from aliases import PIPELINE_NAME_ALIAS as ALIAS_MAP` to the top imports.
- Fix the four conflicting `NAME_HINTS` entries to match the resolved pipeline aliases:
  - `("JURONG WEST", "JURONG EAST")` → `("JURONG WEST", "JURONG WEST")`
  - `("BOON LAY", "JURONG EAST")` → `("BOON LAY", "JURONG WEST")`
  - `("TAMAN JURONG", "JURONG EAST")` → `("TAMAN JURONG", "JURONG WEST")`
  - `("KALLANG", "BOON KENG")` → `("KALLANG", "KALLANG")`
- Leave the other NAME_HINTS as-is (finer precinct-geography mappings like TEBAN/YUNG/WHAMPOA/BENDEMEER are not in the flagged bug set; reconciling them belongs with the Phase-3 ingester refresh).

- [ ] **Step 4: Run to verify GREEN + full suite**

Run: `python3 -m pytest tests/test_aliases.py -v` → PASS
Run: `python3 -m pytest -q` → all PASS (no data changed; pipeline_data.json untouched).

- [ ] **Step 5: Disclose the data divergence**

In `SG-Estate-Framework/CLAUDE.md`, near the pipeline/momentum description, add a note: "`ingest_hdb_upgrading.py` now shares `aliases.PIPELINE_NAME_ALIAS`, but the committed `pipeline_data.json` NRP/LUP items were generated under the OLD attribution (some Jurong West / Kallang precincts credited to Jurong East / Boon Keng). The ingester fetches from data.gov.sg (network), so regenerating `pipeline_data.json` + the momentum→provision cascade is deferred to Phase 3. Until then, Jurong East momentum is mildly overstated by Jurong West NRP precincts."

- [ ] **Step 6: Commit**

```bash
git add models/ingest_hdb_upgrading.py tests/test_aliases.py SG-Estate-Framework/CLAUDE.md
git commit -m "fix(aliases): reconcile ingest_hdb_upgrading to shared PIPELINE_NAME_ALIAS + guard; disclose pipeline_data.json legacy attribution"
```
(append the footer)

---

## Self-Review (completed)

- **Coverage:** roadmap Phase-2 tasks 2.1a/b/c (→2.1), 2.2 (→2.2), 2.3 (→2.4 docs), 2.6 + deferred momentum (→2.3) all mapped. Private-value surfacing (original 2.4) + README (2.5) deferred to Phase 3 with the private-data coverage work — explicitly flagged `not_covered` in build_master so it's structurally ready.
- **Placeholder scan:** complete code for aliases.py, build_master.py, and all tests; Task 2.3 is commands + an explicit expected-change gate, not placeholders.
- **Type/interface consistency:** `canonicalise_pipeline_name`/`estate_to_town`, `PIPELINE_NAME_ALIAS`/`ESTATE_TOWN_ALIAS`/`PRIVATE_DOMINANT_PROXIES`, `build(args) -> DataFrame`, column names (`value_hdb_*`, `emp_*`, `lease_*`, `value_private_*`) are used consistently across tasks and tests.
- **Dependency order:** 2.1 → 2.2 → 2.3 (needs both) → 2.4. Task 2.3 is the one that mutates committed data; it gates on a bounded expected-change set.
- **Risk:** 2.1 changes momentum/liveability attribution; 2.3's diff review is the safety gate. The estate-town consolidation is output-neutral (verified by reasoning: lease short-circuits LENTOR; value's map is unchanged).
