# Project: SG-Estate-Framework Enhancement

## Architecture
The framework scores Singapore housing estates based on two distinct conceptual pillars:
1. **Provision**: Objective, supply-side, comparable score.
2. **Liveability & Value**: Relative, demand-side, persona-based.

Data flows from base geospatial and transactional data, through individual model scripts, to a final consolidated dataset `data/outputs/master_output.csv`.

## Code Layout
- `models/` — Python scoring models and ingesters.
- `scrapers/` — URA private transaction data scrapers.
- `data/` — Canonical datasets: `inputs/` (curated layers), `outputs/` (model results), `raw/` (scraper artifacts), `_archive/` (superseded one-offs).
- `tests/` — Pytest verification suite.
- `frameworks/` — Markdown documentation defining framework rules and weights.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Exploration & Baselining | Run baseline tests, inspect codebase, analyze all requirements | none | DONE |
| 2 | R1: Pipeline Integration | Wire tree_canopy, hdb_density, hawker_v2, coastal, bca_permits into the pipeline and provision/value models | M1 | DONE |
| 3 | R2: Private Scrapers & Value | Complete scrapers for Districts 15/16, merge private data, calculate Bedok/Marine Parade value | M1 | DONE |
| 4 | R3 & R4: UI & Test Suite | Update comparison table/framework diagram, expand pytest suite for new layers | M2, M3 | IN_PROGRESS (Conv: 09024513-17a0-4815-bd7c-104cfcbd258a) |
| 5 | Victory Audit | Verify full pipeline and execute Forensic Audit | M4 | PLANNED |

## Interface Contracts
### Ingest CSVs ↔ provision_model.py
- Each new CSV must follow the column schemas defined in `models/framework_config.py` and the input contract of `models/provision_model.py`.
- New geospatial files are registered in the `provision_model.py` parser arguments.
### scrapers ↔ data/inputs/ura_private.csv
- Scrapers output raw District transaction data.
- Merger merges this into `data/inputs/ura_private.csv` maintaining schema consistency.
