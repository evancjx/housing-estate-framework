# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A two-document conceptual framework + runnable Python pipeline that scores Singapore housing estates.
The conceptual split is load-bearing — it shapes how every model is named, structured, and combined:

- **Provision** (Document 1, `frameworks/1-provision-framework.md`) — supply-side, objective, universal,
  comparable. "What is here." Produces ONE score per estate + an archetype tag.
- **Liveability** (Document 2, `frameworks/2-liveability-matrix.md`) — demand-side, person-relative,
  NON-comparable by design. Produces a 4-persona × 2-horizon (T0/T5) matrix per estate.
- **Value** lives inside Liveability (cost is a relationship with a person). Computed as
  `liveability × exp(−price_residual)`, segmented by tenure.

The framework docs evolved through v0.1→v0.9; the prior monolith is preserved at
`frameworks/sg-estate-liveability-framework.md` as historical record. The split exists to solve a
construct-validity problem: a single number cannot be both objectively-comparable AND person-relevant.
**Do not merge the two outputs into a unified ranking** — the codebase, file naming, and CSV outputs
all assume the split.

## Pipeline architecture

The Python models in `models/` form a directed pipeline. Outputs land in `data/`. Run order matters:

```
data_ingest.py            → downloads parks/markets/schools/polyclinics/hdb_resale from data.gov.sg
fetch_chas.py             → CHAS clinics via OneMap fallback
onemap_geocode_mrt.py     → MRT names → coordinates (RUN LOCALLY; needs OneMap token + internet)
momentum_model.py         → pipeline_data.json → S7 momentum score → updates judged_inputs.csv
provision_model.py        → all geospatial layers + judged_inputs.csv → provision_scores.csv
liveability_model.py      → provision_scores.csv + pipeline_data.json → liveability_matrix.csv
value_model.py            → provision_scores.csv (or liveability_matrix.csv) + hdb_resale.csv → value_output.csv
lease_risk_model.py       → hdb_resale.csv → lease_risk.csv (standalone, joined later)
employment_model.py       → station-count commute approximation → employment_scores_{T0,T5,T15}.csv
```

Each model file ends with an **INPUT CONTRACT** block in its docstring — the authoritative spec for
what columns each CSV must have. Update both the contract and the loader when you change a schema.

## Cross-cutting invariants enforced in code

These are not stylistic preferences — they are framework rules the code actively enforces:

- **Weight vectors must stay in sync.** `provision_model.py:W` (15 components) and
  `liveability_model.py:BASE_W` (13 components, after grouping) must agree on the base weights.
  When adding/renaming a component, update both, plus the S-group mapping in `liveability_model.py:S_GROUPS`.
- **Provenance is never faked.** `provision_model.py` tags each component MEASURED / PARTLY_MEASURED /
  JUDGED. If a JUDGED input (dens/env/mom/hawker) is missing, the model renormalises over present
  components and sets `measured_only=True` — it does NOT impute. Preserve this behaviour.
- **HDB and private are separate universes.** `value_model.py` keeps them as distinct SEGMENTS with
  different control variables; never blend or rank across them.
- **Bands, not decimals, below thresholds.** `value_model.py:CFG["trust_decimal_n"] = 100` — under that
  sample count, the `reported` field shows a band only. The ±0.3 cross-grader noise floor means
  differences smaller than that are not real distinctions; report bands when in doubt.
- **`ESTATE_TOWN_ALIAS` is duplicated** across `value_model.py`, `lease_risk_model.py`, and
  (as `ALIAS_MAP`) `liveability_model.py`. Keep them aligned — e.g. CANBERRA→SEMBAWANG,
  WOODLEIGH→TOA PAYOH. Diverging maps silently break joins.
- **D multiplier holds LOSSES ONLY.** Positive additions go in S7 momentum / liveability T5, never
  in D. This avoids the v0.2–0.4 double-count.
- **Tengah has no resale value.** Canberra is folded into Sembawang. Don't add synthetic rows for
  these; the alias mechanism + manual overrides in `lease_risk_model.py` handle them.

## Commands

```bash
# Install once (Termux/Android-friendly flag in the docstrings)
pip install pandas numpy statsmodels shapely --break-system-packages

# End-to-end run against the real data already checked in
python models/provision_model.py \
    --estates data/estates.csv \
    --mrt data/mrt_layer.csv --bus data/bus_routes.csv \
    --clinics data/chas.csv --polyclinics data/polyclinics.csv \
    --schools data/schools.csv --parks data/parks.csv \
    --markets data/markets.csv --supermarkets data/supermarkets.csv \
    --childcare data/childcare.csv --community data/community.csv \
    --sport data/sport.csv --flood data/flood_risk.csv \
    --noise data/expressways.csv \
    --covered_linkway data/covered_linkway.csv \
    --judged data/judged_inputs.csv \
    --out data/provision_scores.csv

python models/liveability_model.py \
    --scores data/provision_scores.csv \
    --pipeline data/pipeline_data.json \
    --out data/liveability_matrix.csv

python models/value_model.py \
    --scores data/provision_scores.csv \
    --hdb data/hdb_resale.csv \
    --out data/value_output.csv

# Refresh the momentum (S7) component from pipeline_data.json, then re-run provision
python models/momentum_model.py \
    --pipeline data/pipeline_data.json \
    --judged data/judged_inputs.csv \
    --out data/judged_inputs_updated.csv
```

There is no test suite, linter config, or build system. Validate changes by running the pipeline
end-to-end and diffing the resulting CSVs in `data/` against the committed versions.

## Data conventions

- `data/` holds canonical real-data inputs AND outputs from the most recent committed run. The CSVs
  are intentionally version-controlled so anyone can reproduce the headline results without re-running.
- `_demo-files/` is synthetic data used only to smoke-test the scripts. Do not treat it as truthful.
- `data/pipeline_data.json` is the curated list of announced infrastructure additions (MRT, schools,
  polyclinics, etc.) with significance/certainty/year. It is the source of truth for both momentum
  (S7) and liveability T5/T15 horizons.
- CSV outputs use UPPERCASE estate names matching `data/estates.csv`. Joins assume that casing.

## When you change the framework

Per-component weights, persona deltas, band edges, and the D-multiplier formula are reproduced
verbatim in both the markdown framework docs AND the Python model docstrings. When you change a
number in code, update the corresponding section of `frameworks/1-provision-framework.md` or
`frameworks/2-liveability-matrix.md` — and vice versa. The framework documents are not stale
documentation; they are the spec.
