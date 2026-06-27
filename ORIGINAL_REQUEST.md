# Original User Request

## Initial Request — 2026-06-27T10:26:48+08:00

Review and enhance the Singapore Estate Liveability Framework codebase by wiring unwired ingesters, completing private transaction scrapers for Districts 15 and 16, updating UI deliverables, and ensuring robust test coverage.

Working directory: /Users/evancjx/workspace/Housing Estate/SG-Estate-Framework
Integrity mode: development

## Requirements

### R1. Pipeline Integration of Unwired Ingesters
Integrate the existing unwired ingesters (`ingest_tree_canopy.py`, `ingest_hdb_density.py`, `ingest_hawker_v2.py`, `ingest_coastal.py`, `ingest_bca_permits.py`) into the main scoring pipeline. The `provision_model.py` and `value_model.py` scripts must read from these generated CSVs/data inputs instead of falling back on hardcoded records in `judged_inputs.csv`.

### R2. Private Scraper Completion & Ingestion
Implement or run the missing scrapers to retrieve private transaction data from URA for Postal Districts 15 (Katong, Joo Chiat) and 16 (Bedok, Upper East Coast). Merge this data into `data/ura_private.csv` and ensure the value model calculates private housing value metrics for MARINE PARADE and BEDOK.

### R3. Interactive UI Deliverables Update
Regenerate `comparison_table.html` and `framework_diagram.html` to reflect the updated 20-component pipeline, ensuring that estate counts, diagram nodes, and column values correctly represent all newly wired components.

### R4. Robustness & Test Suite Expansion
Expand the pytest suite in `tests/` to verify the functionality of newly wired layers and scraper output ingestion. Ensure all existing invariants and characterization tests pass without regression.

## Acceptance Criteria

### Test Validation
- [ ] Running `make smoke` executes successfully with all tests passing.
- [ ] No regression on core database constraints or framework weights validation.

### Pipeline Execution
- [ ] Running `make pipeline` runs the end-to-end workflow successfully from data ingestion to master CSV output join.
- [ ] Master output CSV (`data/master_output.csv`) contains valid, updated metrics populated from the newly wired data layers.
- [ ] Private value output file includes valid, scored entries for Bedok and Marine Parade.

### Scraper Functionality
- [ ] Scraper execution fetches transactions for Districts 15 and 16 and successfully updates `data/ura_private.csv`.

### UI Validation
- [ ] `comparison_table.html` shows all 20 components, including the new geodata-driven components.
- [ ] `framework_diagram.html` accurately illustrates the updated architecture and data flow.
