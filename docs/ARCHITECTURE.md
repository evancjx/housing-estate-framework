# Architecture

The Singapore Estate Framework is a versioned analytical pipeline with two
load-bearing domain boundaries:

- **Provision** is objective, supply-side, universal, and comparable.
- **Liveability** is person-relative and expressed as a persona × horizon matrix.
  Tenure-segmented Value belongs on this side of the framework.

Provision and Liveability must never be collapsed into one ranking. HDB and
private Value must never be blended or ranked across tenure universes.

## Package boundaries

```text
sg_estate/
├── domain/          framework rules and model implementations
├── application/     orchestration, joins, and publication use cases
├── adapters/        external source and filesystem adapters
├── contracts.py     executable tabular boundary contracts
├── paths.py         repository path discovery
└── reporting/       shared report infrastructure and canonical builders

models/              compatibility CLIs and not-yet-migrated ingesters/reports
scrapers/            external private-transaction acquisition
data/catalog.json    logical data-zone ownership
data/runs/           ignored transactional staging and logs
data/outputs/        promoted canonical outputs
```

Dependencies point inward: adapters and compatibility CLIs may call application
and domain code; domain code must not import report builders or scrapers.

## Execution model

`make pipeline` creates an isolated run, refreshes derived inputs, runs each
model, validates executable contracts, and promotes the complete result with
rollback. `make pipeline-reuse` performs the same rebuild from committed derived
inputs without network refreshes.

Every promoted run records:

- framework model version and scoring year;
- Git commit and dirty state;
- Python version plus SHA-256 hashes for model source and dependency specs;
- SHA-256 hashes for source inputs, the data catalog, and outputs;
- stage commands, durations, return codes, and log paths.

S7 momentum remains outside automatic execution. Its generated proposal must be
reviewed before values are copied into `judged_inputs.csv`.

## Publication model

Internal numeric columns remain nullable. Availability semantics use companion
status columns (`available`, `no_data`, `not_covered`, `not_applicable`).
Human-readable bands and basis fields may continue to display `N/R` or
`not_covered`.

Root HTML files remain generated publication artifacts for GitHub Pages.
Canonical shared reporting utilities live under `sg_estate.reporting`; each
catalogued report retains a matching guide under `docs/html-pages/`.

## Data lifecycle

`data/catalog.json` classifies and assigns ownership to every committed model
input. Git keeps the reviewed snapshots needed for offline reproducibility, with
a CI-enforced 50 MiB per-file ceiling; larger immutable sources require Git LFS
or versioned release storage plus checksums. Transactional run directories are
local staging, while the promoted manifest and Git history identify published
generations.

See [Data governance and versioning](DATA_GOVERNANCE.md) for retention,
provenance, and restricted-data rules.
