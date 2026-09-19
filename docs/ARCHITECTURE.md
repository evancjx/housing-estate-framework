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
model, and validates executable contracts and digest-bound source receipts. A
network refresh then stops in `awaiting_review`; it cannot replace canonical
files. After reviewing the staged data and manifest, `make pipeline-promote
RUN_ID=<id>` revalidates catalog, code, inputs, outputs, receipts, and exact
bytes before one rollback-safe promotion. `make pipeline-reuse` performs an
offline rebuild from committed derived inputs and may promote immediately.

Every promoted run records:

- framework model version and scoring year;
- Git commit and dirty state;
- Python version plus SHA-256 hashes for model source and dependency specs;
- SHA-256 hashes for source inputs, the data catalog, and outputs;
- versioned receipts for every effective derived input and every canonical
  source input that has acquisition evidence, including authority, stable
  source identity, retrieval and coverage evidence, accepted row count,
  exact-byte hash, cache/fallback state, and validation result. Historical
  inputs without receipts remain unknown rather than being backfilled;
- stage commands, durations, return codes, and log paths.

S7 momentum remains outside automatic execution. Its generated proposal must be
reviewed before values are copied into `judged_inputs.csv`.

URA private-transaction acquisition follows the same review boundary. The API
and browser downloaders write run-scoped artifacts plus a terminal attempt for
every requested district/property-type partition. The ingestor reconciles the
requested month range, dimensions, counts, hashes, invalid rows, and duplicates
into `ura_private.csv`, a digest-bound receipt, and
`ura_private.csv.acquisition.json`. A live generation remains staged in
`awaiting_review`; only the explicit promotion command revalidates and replaces
that three-file bundle, with the acquisition manifest written last as the
commit marker. Missing sale dates or project ages remain null.

## Publication model

Internal numeric columns remain nullable. Availability semantics use companion
status columns (`available`, `no_data`, `not_covered`, `not_applicable`).
Human-readable bands and basis fields may continue to display `N/R` or
`not_covered`.

Root HTML files remain generated publication artifacts for GitHub Pages.
Canonical shared reporting utilities live under `sg_estate.reporting`; each
catalogued report retains a matching guide under `docs/html-pages/`.

The Pages build derives public metadata contracts rather than asking report
pages to contact upstream authorities at runtime:

- `site/assets/project-identity-registry/<revision>/registry.json` is the
  stable-ID discovery and routing contract across the URA project universe,
  EdgeProp's name index, reviewed geocodes, transaction shards, and dedicated
  reports. Each explorer, comparison, transaction, exit, and report capability
  is independently evidence-backed. Ambiguous names remain separate from
  their street/district identities; unmatched names remain explicitly
  name-only. A root manifest switches to a validated immutable revision.
- `data-status.json` distinguishes pipeline generation time from the known
  coverage of HDB, private-transaction, and rail snapshots. Validated v3 run
  receipts expose fresh/cached/mixed/fallback/offline/derived acquisition state;
  current bytes that differ from the recorded run are marked
  `modified_since_run`. Missing historical retrieval dates remain `null`; file
  modification times are never used as provenance.

Runtime JSON stays same-origin and reproducible. `site/assets/data-loader.js`
provides bounded timeouts, response/schema errors, success-only caching,
in-flight request deduplication, and settled multi-source loading. Reports must
show loading, partial, and failure states instead of silently substituting zero
or an incomplete fallback.

Private-transaction browser shards are immutable generations. Their root
manifest, every shard, and both consuming reports carry the same deterministic
SHA-256 revision; shard URLs include that revision in both their path and query
string. A generator writes and validates all 64 shards in staging, atomically
promotes the revision directory, then switches the root manifest last. Prior
generations remain readable by prior pages. Consumers withhold transaction
results and require a reload if a shard's revision or exact schema differs from
the page, while the Pages build independently recomputes and validates the
complete selected generation.

The private-project explorer and two-, multi-, and exit-comparison tools share
one immutable browser catalog under `site/assets/project-catalog/<revision>/`.
Its deterministic revision binds the full project identity/capability union,
deduplicated framework contexts, and the selected transaction generation. Each
HTML report inlines only a small usable bootstrap, then hydrates the same
revisioned URL through the shared loader; normal HTTP caching therefore reuses
one response across tools. Generic explorer rows carry an explicit
explorer-only capability and cannot masquerade as transaction or comparison
evidence. Publication validates the staged catalog before switching its root
manifest, and the Pages build enforces catalog, consumer-reference, initial HTML,
bootstrap-row, and project-option budgets.

The project catalog above is the full-record data source for the four project
tools; the identity registry is the semantic boundary used for landing search,
aliases, and destination choice. Existing catalog and transaction project IDs
remain stable. Source keys reconcile exactly, reviewed aliases are
single-sourced, unreviewed geocodes cannot grant location evidence, and a
name-only record cannot inherit an achieved-data route from a similar name.

## Data lifecycle

`data/catalog.json` classifies and assigns ownership to every committed model
input. Git keeps the reviewed snapshots needed for offline reproducibility, with
a CI-enforced 50 MiB per-file ceiling; larger immutable sources require Git LFS
or versioned release storage plus checksums. Transactional run directories are
local staging, while the promoted manifest and Git history identify published
generations.

See [Data governance and versioning](DATA_GOVERNANCE.md) for retention,
provenance, and restricted-data rules.
