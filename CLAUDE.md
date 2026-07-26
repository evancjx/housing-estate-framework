# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A two-document conceptual framework + runnable Python pipeline that scores Singapore housing estates.
The conceptual split is load-bearing — it shapes how every model is named, structured, and combined:

- **Provision** ([Document 1](frameworks/1-provision-framework.md)) — supply-side, objective, universal,
  comparable. "What is here." Produces ONE score per estate + an archetype tag.
- **Liveability** ([Document 2](frameworks/2-liveability-matrix.md)) — demand-side, person-relative,
  NON-comparable by design. Produces a 4-persona × 3-horizon (T0/T5/T15) matrix per estate.
- **Value** lives inside Liveability (cost is a relationship with a person). Computed as
  `liveability × exp(−price_residual)`, segmented by tenure.

All five `frameworks/` docs, with status:

| Status | Doc |
|---|---|
| Active spec | [1-provision-framework.md](frameworks/1-provision-framework.md), [2-liveability-matrix.md](frameworks/2-liveability-matrix.md) |
| Reference data | [4-estate-timeline-matrix.md](frameworks/4-estate-timeline-matrix.md) — per-town maturation (23 HDB towns); not yet wired into any model, but the empirical basis for S7 momentum / archetype sequencing |
| Historical record | [sg-estate-liveability-framework.md](frameworks/sg-estate-liveability-framework.md) (v0.1–v0.8 monolith); [3-estate-growth-framework.md](frameworks/3-estate-growth-framework.md) (⚠ SUPERSEDED — obsolete 9-component unified design; do not treat as current spec) |

The split exists to solve a construct-validity problem: a single number cannot be both
objectively-comparable AND person-relevant.
**Do not merge the two outputs into a unified ranking** — the codebase, file naming, and CSV outputs
all assume the split.

## Pipeline architecture

The Python models in `models/` form a directed pipeline. Curated/refreshed layers live in
`data/inputs/`, model results in `data/outputs/`. Run order matters:

```
# --- SHARED CONFIG (imported libraries, not pipeline stages) ---
# framework_config.py       → PROVISION_WEIGHTS×20, PROVENANCE, BAND_EDGES, PERSONA_DELTAS (see invariants)
# aliases.py                → PIPELINE_NAME_ALIAS, ESTATE_TOWN_ALIAS — single-sourced; do not copy locally

# --- BASE LAYER INGESTERS (NETWORK required; each builds a data/inputs/* file for provision_model.py) ---
data_ingest.py               → data/inputs/{parks,markets,schools,polyclinics,hdb_resale,...}.csv  (data.gov.sg)
fetch_chas.py                → data/inputs/chas.csv                        (CHAS clinics via OneMap fallback)
onemap_geocode_mrt.py        → data/inputs/mrt_layer.csv                   (RUN LOCALLY; needs OneMap token)

# WIRED — output committed to data/inputs/ and consumed by the canonical pipeline:
ingest_jtc_industrial.py     → data/inputs/jtc_industrial.csv              (--jtc_industrial)
ingest_nea_air.py            → data/inputs/air_quality.csv                 (--air_quality)
ingest_tcmr.py               → data/inputs/town_council_kpi.json           (--tcmr; stewardship component)
ingest_tree_canopy.py        → data/inputs/tree_canopy.csv                 (--tree_canopy; env)
ingest_hdb_density.py        → data/inputs/hdb_density.csv                 (--hdb_density; dens)
ingest_hawker_v2.py          → data/inputs/hawker_v2.csv                   (--hawker_v2; hawker PARTLY_MEASURED)
ingest_coastal.py            → data/inputs/coastal.csv                     (--coastal; green sub-metric)
ingest_bca_permits.py        → data/inputs/bca_permits.csv                 (--bca; D-multiplier severity)
ingest_hdb_upgrading.py  ↘
ingest_private_pipeline.py   → data/inputs/pipeline_data.json              (momentum S7 + liveability T5)

# STUBS — zero-filled, explicitly deferred, not consumed by any model:
# ingest_ev_chargers.py        (EV coverage — fetcher not yet implemented)
# ingest_pedestrian_paths.py   (walking/cycling — fetcher not yet implemented)

# --- SCORING PIPELINE ---
momentum_model.py            → data/inputs/pipeline_data.json → data/outputs/judged_inputs_updated.csv  (S7 score)
provision_model.py           → all geospatial layers + data/inputs/judged_inputs.csv → data/outputs/provision_scores.csv
liveability_model.py         → data/outputs/provision_scores.csv + data/inputs/pipeline_data.json → data/outputs/liveability_matrix.csv
value_model.py               → data/outputs/provision_scores.csv + data/inputs/hdb_resale.csv → data/outputs/value_output.csv
lease_risk_model.py          → data/inputs/hdb_resale.csv → data/outputs/lease_risk.csv           (standalone, joined later)
employment_model.py          → (embedded station data) → data/outputs/employment_scores_{T0,T5,T15}.csv
build_master.py              → all above → data/outputs/master_output.csv                  (headline deliverable)

# --- SIDE PIPELINE (private transactions, not estate scores; run via `make private-bedrooms`) ---
build_private_bedrooms.py    → data/inputs/ura_private.csv + edgeprop scrape [+ data/inputs/project_unit_mix.csv]
                               → data/outputs/private_transactions_bedrooms.csv  (per-txn bedrooms + bedroom_source provenance)
```

Each model file ends with an **INPUT CONTRACT** block in its docstring — the authoritative spec for
what columns each CSV must have. Update both the contract and the loader when you change a schema.

## Cross-cutting invariants enforced in code

These are not stylistic preferences — they are framework rules the code actively enforces:

- **Constants are single-sourced in `models/framework_config.py`.** `PROVISION_WEIGHTS` (20 — added v2.0: air_quality, jtc_industrial, stewardship),
  `PROVISION_WEIGHTS_PRIVATE`, `PROVENANCE`, `S_GROUPS`, `PERSONA_DELTAS`, `BAND_EDGES`,
  `BAND_NUMERIC`, `band_label`, `build_persona_weights`, `validate_framework_config`. `provision_model.py`
  imports `W`/`W_PRIVATE`/`PROVENANCE` from it; `liveability_model.py` imports `BASE_W`/`S_GROUPS`/
  `PERSONA_DELTAS`. When adding/renaming a component, edit framework_config (and S_GROUPS).
  **Alias maps stay in `models/aliases.py`** (NOT framework_config — its alias dicts are intentionally absent).
  Note: `liveability_model._build_persona_weights` is deliberately UNFLOORED (committed-output behaviour);
  `framework_config.build_persona_weights` floors a negative group weight at zero (origin improvement, not yet adopted).
- **Provenance is never faked.** `provision_model.py` tags each component MEASURED / PARTLY_MEASURED /
  JUDGED. Provenance split: 14 MEASURED + 6 PARTLY_MEASURED (dens, env, mom, air_quality, stewardship, hawker) + 0 JUDGED.
  If a PARTLY_MEASURED input is missing, the model renormalises over present
  components and sets `measured_only=True` — it does NOT impute. Preserve this behaviour.
  Same culture in `build_private_bedrooms.py`: every bedrooms value carries a `bedroom_source`
  (edgeprop_exact / edgeprop_band_label / research_unit_mix / unknown); ambiguity → unknown, never a guess.
- **HDB and private are separate universes.** `value_model.py` keeps them as distinct SEGMENTS with
  different control variables; never blend or rank across them.
- **Bands, not decimals, below thresholds.** `value_model.py:CFG["trust_decimal_n"] = 100` — under that
  sample count, the `reported` field shows a band only. The ±0.3 cross-grader noise floor means
  differences smaller than that are not real distinctions; report bands when in doubt.
- **Alias maps are single-sourced in `models/aliases.py`** (Phase 2). `PIPELINE_NAME_ALIAS`
  (imported by `momentum_model.py`, `liveability_model.py`, `ingest_hdb_upgrading.py`) and
  `ESTATE_TOWN_ALIAS` + `PRIVATE_DOMINANT_PROXIES` (imported by `value_model.py`,
  `lease_risk_model.py`) — e.g. CANBERRA→SEMBAWANG, WOODLEIGH→TOA PAYOH. `tests/test_aliases.py`
  guards single-sourcing with `is`-identity checks; do not re-introduce a local copy.
- **D multiplier holds LOSSES ONLY.** Positive additions go in S7 momentum / liveability T5, never
  in D. This avoids the v0.2–0.4 double-count.
- **Tengah has no HDB resale value.** Canberra HDB is folded into Sembawang. Don't add synthetic
  HDB rows for these; the alias mechanism + manual overrides in `lease_risk_model.py` handle them.
- **`pipeline_data.json` NRP/LUP attribution has been refreshed with the shared aliases.**
  `ingest_hdb_upgrading.py` imports `aliases.PIPELINE_NAME_ALIAS` and the committed NRP/LUP items
  were regenerated from data.gov.sg on 2026-06-27. Jurong West and Kallang attribution is no longer
  folded into Jurong East / Boon Keng. Future refreshes still require network access and a reviewed
  momentum→provision→liveability→value→master cascade.

## Commands

```bash
# Install once (Termux/Android-friendly flag in the docstrings)
pip install pandas numpy statsmodels shapely --break-system-packages

# End-to-end run against the real data already checked in
python models/provision_model.py \
    --estates data/inputs/estates.csv \
    --mrt data/inputs/mrt_layer.csv --bus data/inputs/bus_routes.csv \
    --clinics data/inputs/chas.csv --polyclinics data/inputs/polyclinics.csv \
    --schools data/inputs/schools.csv --parks data/inputs/parks.csv \
    --markets data/inputs/markets.csv --supermarkets data/inputs/supermarkets.csv \
    --childcare data/inputs/childcare.csv --community data/inputs/community.csv \
    --sport data/inputs/sport.csv --flood data/inputs/flood_risk.csv \
    --noise data/inputs/expressways.csv --air_noise data/inputs/air_noise_corridors.csv \
    --eldercare data/inputs/eldercare.csv \
    --covered_linkway data/inputs/covered_linkway.csv \
    --jtc_industrial data/inputs/jtc_industrial.csv --air_quality data/inputs/air_quality.csv \
    --tree_canopy data/inputs/tree_canopy.csv --hdb_density data/inputs/hdb_density.csv \
    --hawker_v2 data/inputs/hawker_v2.csv --coastal data/inputs/coastal.csv \
    --tcmr data/inputs/town_council_kpi.json \
    --judged data/inputs/judged_inputs.csv \
    --out data/outputs/provision_scores.csv
# eldercare, air_noise, jtc_industrial, air_quality, tree_canopy, hdb_density, hawker_v2,
# coastal, and tcmr (stewardship) are all wired into the
# canonical run. This command is kept in sync with the `pipeline` target in the Makefile — if you add
# a scoring flag, update BOTH. Supplying a missing file now fails loudly.

python models/liveability_model.py \
    --scores data/outputs/provision_scores.csv \
    --pipeline data/inputs/pipeline_data.json \
    --archetypes data/inputs/archetype_assignments.csv \
    --bca data/inputs/bca_permits.csv \
    --out data/outputs/liveability_matrix.csv

python models/value_model.py \
    --scores data/outputs/provision_scores.csv \
    --hdb data/inputs/hdb_resale.csv \
    --out data/outputs/value_output.csv

# Refresh the momentum (S7) component from pipeline_data.json, then re-run provision
python models/momentum_model.py \
    --pipeline data/inputs/pipeline_data.json \
    --judged data/inputs/judged_inputs.csv \
    --out data/outputs/judged_inputs_updated.csv

# Consolidate all model outputs into master_output.csv
python3 models/build_master.py
```

### Tests & Makefile

The repo has a pytest suite (`tests/`, config in `pytest.ini`) and a `Makefile` — there is no linter.
Dev deps: `pip install -r requirements-dev.txt`.

```bash
make smoke                       # full suite: python3 -m pytest -q (the reproducibility + correctness gate)
make master                      # rebuild data/outputs/master_output.csv from current model outputs
make pipeline                    # regenerate everything from real data, then the master

pytest -q                        # same as `make smoke`
pytest tests/test_invariants.py  # one file
pytest tests/test_value_model.py::test_clean_psm_drops_zero_area  # one test
pytest -m integration            # only the slow real-pipeline-on-committed-data tests
pytest -m snapshot               # before/after characterization (DESELECTED by default in pytest.ini; run manually)
```

`pytest.ini` deselects `snapshot` by default via `addopts = -m "not snapshot"`. Two custom markers:
`integration` (runs the real pipeline on committed data, slow) and `snapshot` (characterization).
What the suite actually guards: alias single-sourcing (`is`-identity), framework_config validity,
doc⇄code consistency (`test_doc_consistency.py`), the cross-cutting invariants above
(`test_invariants.py`), and run-to-run reproducibility (`test_reproducibility.py`). Beyond `make smoke`,
validate behaviour changes by running the pipeline end-to-end and diffing the resulting `data/` CSVs
against the committed versions.

## Data conventions

- `data/` is split four ways, and every file is version-controlled so anyone can reproduce the
  headline results without re-running:
  - `data/inputs/` — curated + ingester-refreshed layers the models consume (incl. `ura_private.csv`,
    the cleaned URA transaction layer assembled from `data/raw/ura/`).
  - `data/outputs/` — results from the most recent committed model run.
  - `data/raw/` — scraper artifacts: `raw/ura/` (per-district URA PMI dumps) and `raw/edgeprop/`
    (not-clean EdgeProp scrape dumps + project lists consumed by the HTML generators).
  - `data/_archive/` — superseded one-off experiment outputs kept for reference; nothing reads them.
- `_demo-files/` is synthetic data used only to smoke-test the scripts. Do not treat it as truthful.
- `data/inputs/pipeline_data.json` is the curated list of announced infrastructure additions (MRT, schools,
  polyclinics, etc.) with significance/certainty/year. It is the source of truth for both momentum
  (S7) and liveability T5/T15 horizons.
- CSV outputs use UPPERCASE estate names matching `data/inputs/estates.csv`. Joins assume that casing.

## When you change the framework

Per-component weights, persona deltas, band edges, and the D-multiplier formula are reproduced
verbatim in both the markdown framework docs AND the Python model docstrings. When you change a
number in code, update the corresponding section of
[`frameworks/1-provision-framework.md`](frameworks/1-provision-framework.md) or
[`frameworks/2-liveability-matrix.md`](frameworks/2-liveability-matrix.md) — and vice versa.
The framework documents are not stale documentation; they are the spec.

## Artifacts & ancillary files

- **[comparison_table.html](comparison_table.html)** — rendered cross-model comparison table (estates × Provision / Liveability / Value / Employment / Risk / Life-Path). The headline visual deliverable. ⚠ Estate/component counts lag after a pipeline regeneration — re-run `build_master.py` when counts change.
- **[framework_diagram.html](framework_diagram.html)** — architecture diagram (Inputs → 4 Models → `data/outputs/master_output.csv`). Same regeneration caveat.
- **[scrapers/](scrapers/README.md)** — URA private-transaction scrapers (Playwright primary, API fallback). Downloads apartment/condo, landed, and strata-landed PMI data by postal district for `value_model.py --private`.
- **[factor_audit_reports/](factor_audit_reports/)** — output from the `factor-audit` skill; proposed new framework components with evidence citations. Not auto-applied to any model.
- **[docs/html-pages/](docs/html-pages/README.md)** — one guide per catalogued root HTML report, covering purpose, data scope, comparison factors, controls, interpretation limits, and rebuild commands.
- **[tests/snapshots/before/](tests/snapshots/before/)** — committed baseline CSVs (`provision_scores`, `liveability_matrix`, `value_output`) for the snapshot characterization tests. Update manually when a pipeline change intentionally alters output.
