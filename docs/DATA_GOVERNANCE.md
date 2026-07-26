# Data governance and versioning

The repository keeps enough reviewed data to rebuild the estate models offline,
while preventing scraper artifacts and generated files from growing without a
clear owner.

## Logical zones

Every committed file under `data/inputs/` is registered in
`data/catalog.json` with a logical zone, producer, and authority:

- **curated** — human-reviewed framework or geographic reference data;
- **derived** — reproducible output built from other committed inputs;
- **ingested** — normalized snapshot from an external authority;
- **research** — diagnostics that are not part of Provision;
- **example** — synthetic interface examples.

Changes to an input must update its catalog entry when its producer, authority,
or zone changes. Raw and research artifacts must not silently become scoring
inputs.

## Versioning policy

- Files required for an offline model rebuild remain in Git when they are below
  50 MiB.
- A tracked data file must not exceed 50 MiB. Use Git LFS or a versioned release
  asset for larger immutable snapshots, and record its checksum and retrieval
  procedure before changing the pipeline contract.
- `data/outputs/` contains only the current promoted publication generation.
  Historical generations are identified by Git history and
  `data/outputs/run_manifest.json`, not by accumulating dated copies.
- `data/runs/` is local, ignored transactional staging. Keep failed-run logs only
  while diagnosing them; successful runs may be removed after promotion.
- `data/_archive/` is never a pipeline dependency. New superseded outputs should
  normally be recovered from Git history instead of added there.

Migrating an existing dataset to LFS or external storage is a reviewed repository
operation because it changes clone and offline-rebuild behavior.

## Provenance and reproducibility

Promoted pipeline manifests record the model version, scoring year, Git state,
Python version, model/dependency source checksums, catalog checksum, source
checksums, stage commands, durations, and output checksums. Human-reviewed
momentum changes remain outside automatic execution until copied into
`judged_inputs.csv`.

Do not commit credentials, reusable browser state, API responses containing
restricted data, or licensed exact-unit records.
