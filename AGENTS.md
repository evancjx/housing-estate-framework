# Repository Guidelines

This file gives Codex and other coding agents the working rules for this repository. It is based on
`CLAUDE.md`; keep the two files aligned when repository conventions change.

## What This Repo Is

This repository is a Python data/modeling pipeline for the Singapore Estate Liveability Framework.
It has a load-bearing conceptual split:

- **Provision** (`frameworks/1-provision-framework.md`): supply-side, objective, universal, comparable.
  It answers "what is here" and produces one score per estate plus an archetype tag.
- **Liveability** (`frameworks/2-liveability-matrix.md`): demand-side, person-relative, non-comparable
  by design. It produces a 4-persona x 3-horizon matrix per estate.
- **Value** lives inside Liveability. Cost is a relationship with a person, computed as
  `liveability x exp(-price_residual)`, segmented by tenure.

Do not merge Provision and Liveability into a unified ranking. The codebase, file naming, and CSV
outputs assume the split.

Framework document status:

- Active specs: `frameworks/1-provision-framework.md`, `frameworks/2-liveability-matrix.md`.
- Reference data: `frameworks/4-estate-timeline-matrix.md`, currently empirical support for S7
  momentum and archetype sequencing, not wired into models.
- Historical record: `frameworks/sg-estate-liveability-framework.md` and
  `frameworks/3-estate-growth-framework.md`. The latter is superseded; do not treat its old
  9-component unified design as current.

## Project Structure & Module Organization

Core model code lives in `models/`, including `provision_model.py`, `liveability_model.py`,
`value_model.py`, `lease_risk_model.py`, `employment_model.py`, and `build_master.py`.
Tests live in `tests/`; fixtures and before/after snapshots are under `tests/snapshots/`.
Inputs and generated outputs are in `data/`, with `data/outputs/master_output.csv` as the headline output.
URA/private transaction tooling is isolated in `scrapers/`.

The model pipeline is directed and run order matters:

```text
momentum_model.py      -> data/inputs/pipeline_data.json -> data/outputs/judged_inputs_updated.csv
provision_model.py     -> geospatial layers + judged inputs -> data/outputs/provision_scores.csv
liveability_model.py   -> provision_scores + pipeline_data -> data/outputs/liveability_matrix.csv
value_model.py         -> provision_scores + hdb_resale -> data/outputs/value_output.csv
lease_risk_model.py    -> hdb_resale -> data/outputs/lease_risk.csv
employment_model.py    -> embedded station data -> data/outputs/employment_scores_{T0,T5,T15}.csv
build_master.py        -> all model outputs -> data/outputs/master_output.csv
```

Each model file ends with an `INPUT CONTRACT` block in its docstring. Treat that block as the
authoritative schema for each input CSV. Update both the contract and loader when changing schemas.

## Cross-Cutting Invariants

These rules are enforced by code and tests:

- Constants are single-sourced in `models/framework_config.py`: `PROVISION_WEIGHTS`,
  `PROVISION_WEIGHTS_PRIVATE`, `PROVENANCE`, `S_GROUPS`, `PERSONA_DELTAS`, `BAND_EDGES`,
  `BAND_NUMERIC`, `band_label`, `build_persona_weights`, and `validate_framework_config`.
- Alias maps are single-sourced in `models/aliases.py`, not `framework_config.py`.
  `PIPELINE_NAME_ALIAS`, `ESTATE_TOWN_ALIAS`, and `PRIVATE_DOMINANT_PROXIES` are guarded by
  `tests/test_aliases.py`; do not reintroduce local copies.
- Provenance is never faked. `provision_model.py` tags components as `MEASURED`,
  `PARTLY_MEASURED`, or `JUDGED`. If a `PARTLY_MEASURED` input is missing, the model renormalizes
  over present components and sets `measured_only=True`; it does not impute.
- HDB and private are separate universes. Keep value segments distinct and do not blend or rank
  across tenure segments.
- Value reporting uses bands below the trust threshold. `value_model.py:CFG["trust_decimal_n"] = 100`;
  below that sample count, report bands rather than implying decimal precision.
- The D multiplier holds losses only. Positive additions go in S7 momentum or Liveability T5, never
  in D.
- Tengah has no HDB resale value. Canberra HDB is folded into Sembawang. Do not add synthetic HDB
  rows for these; aliases and manual overrides handle them.
- `data/inputs/pipeline_data.json` NRP/LUP attribution has been refreshed with the shared aliases.
  Jurong West and Kallang attribution is no longer folded into Jurong East / Boon Keng. Future
  regeneration still requires networked ingesters and a reviewed downstream cascade.

## Build, Test, and Development Commands

- `python3 -m pip install -r requirements-dev.txt` installs local development dependencies.
- `make smoke` runs the default pytest gate with snapshot tests excluded.
- `python3 -m pytest -q` is equivalent to the smoke test and useful for direct pytest flags.
- `make master` rebuilds only `data/outputs/master_output.csv` from current intermediate outputs.
- `make pipeline` regenerates provision, liveability, value, and master CSV outputs from committed data.

Targeted tests:

```bash
python3 -m pytest -q
python3 -m pytest tests/test_invariants.py
python3 -m pytest tests/test_value_model.py::test_clean_psm_drops_zero_area
python3 -m pytest -m integration
python3 -m pytest -m snapshot
```

`pytest.ini` deselects `snapshot` by default via `addopts = -m "not snapshot"`.

For scraper setup, see `scrapers/README.md`; Playwright and external credentials are outside the
default test path.

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation. Follow the existing procedural module style: helper
functions, `argparse` CLIs, pandas DataFrames for joins, and clear failure messages when inputs are
missing. Keep CSV column names stable and lowercase unless the schema requires otherwise.
Normalize estate keys with stripped uppercase names, matching `build_master.py`.

No formatter or linter config is checked in, so keep edits consistent with nearby code.

## Testing Guidelines

Add focused pytest coverage for model logic, schema changes, and pipeline invariants. Run
`make smoke` before and after meaningful changes when feasible. If CSV outputs change intentionally,
explain why and include the regenerated outputs.

The suite guards alias single-sourcing, `framework_config` validity, doc-code consistency,
cross-cutting invariants, value model behavior, and run-to-run reproducibility. For behavior changes,
also consider running the pipeline end to end and diffing resulting `data/` CSVs against committed
versions.

## Data Conventions

- `data/` is split four ways: `inputs/` (curated + ingester-refreshed layers), `outputs/` (model
  results from the most recent committed run), `raw/` (scraper artifacts: `raw/ura/`, `raw/edgeprop/`),
  and `_archive/` (superseded one-off outputs; nothing reads them).
- `_demo-files/` is synthetic data used only to smoke-test scripts; do not treat it as truthful.
- `data/inputs/pipeline_data.json` is the source of truth for announced infrastructure additions used by
  S7 momentum and Liveability T5/T15 horizons.
- CSV outputs use uppercase estate names matching `data/inputs/estates.csv`; joins assume that casing.

## Framework Change Rules

Per-component weights, persona deltas, band edges, and the D-multiplier formula are reproduced in
both markdown framework docs and Python model docstrings. When changing a number in code, update the
corresponding section of `frameworks/1-provision-framework.md` or
`frameworks/2-liveability-matrix.md`, and vice versa. The framework docs are the spec, not stale
documentation.

## Commit & Pull Request Guidelines

Git history uses short conventional prefixes such as `feat:`, `fix:`, `test:`, `docs:`, `chore:`,
and scoped forms like `feat(scrapers):`. Keep commits focused and mention regenerated data.

Pull requests should describe changed model or data behavior, list commands run, link related issues
or docs, and include screenshots only for HTML deliverables such as `comparison_table.html`.

## Security & Configuration Tips

Do not hardcode API keys or tokens. Use environment variables such as `URA_ACCESS_KEY` and local-only
OneMap credentials for networked ingesters. Re-verify dated public facts before relying on new
scoring inputs.
