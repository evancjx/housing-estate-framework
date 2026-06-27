## 2026-06-27T02:34:38Z
You are teamwork_preview_worker_r1.
Your working directory is /Users/evancjx/workspace/Housing Estate/SG-Estate-Framework/.agents/worker_r1.
Your task is to implement Milestone 2: R1: Pipeline Integration of Unwired Ingesters.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope Boundaries:
- Modify only models/provision_model.py, models/liveability_model.py, and the Makefile.
- Do NOT rewrite or modify other files unless necessary for compilation/running.
- Do NOT hardcode output results. All scores must be computed dynamically using the new scoring formulas from the data layers.

Inputs:
- Ingest scripts: models/ingest_tree_canopy.py, models/ingest_hdb_density.py, models/ingest_hawker_v2.py, models/ingest_coastal.py, models/ingest_bca_permits.py
- Estates coordinates: data/estates.csv

Objective:
1. Modify models/provision_model.py to:
   - Accept optional CLI flags:
     - `--tree_canopy` (path to data/tree_canopy.csv)
     - `--hdb_density` (path to data/hdb_density.csv)
     - `--hawker_v2` (path to data/hawker_v2.csv)
     - `--coastal` (path to data/coastal.csv)
   - When these flags are provided and files exist:
     - Load them using pandas.
     - For `tree_canopy` (`env` component): Implement a scoring function `score_env(row)` which averages:
       * `score_canopy = score_by_count(row['canopy_cover_pct'], [(30, 5), (20, 4), (10, 3), (5, 2), (0, 1)])`
       * `score_uhi = score_by_distance(row['uhi_delta_c'], [(0.2, 5), (0.6, 4), (1.2, 3), (1.8, 2), (99, 1)])` (lower delta is better)
       * Combine canopy and UHI delta: `round(0.5 * score_canopy + 0.5 * score_uhi, 2)`. Return `np.nan` if row data is missing or invalid.
     - For `hdb_density` (`dens` component): Implement a scoring function `score_dens(row)`:
       * If `row['total_dwelling_units'] == 0`, return `np.nan` (enforcing renormalization for private-dominant estates).
       * Otherwise: `score = score_by_distance(row['residents_per_net_hectare'], [(150, 5), (300, 4), (450, 3), (600, 2), (99999, 1)])` (lower density is better). Return `float(score)`.
     - For `hawker_v2` (`hawker` component): Implement `score_hawker_v2(row)`:
       * `score_dist = score_by_distance(row['nearest_hawker_m'], [(400, 5), (800, 4), (1200, 3), (2000, 2), (99999, 1)])`
       * `score_stalls = score_by_count(row['total_stalls_800m'], [(150, 5), (80, 4), (40, 3), (10, 2), (0, 1)])`
       * `score_count = score_by_count(row['n_hawker_centres_800m'], [(2, 5), (1, 3), (0, 1)])`
       * Combine: `score_combined = 0.4 * score_dist + 0.4 * score_stalls + 0.2 * score_count`
       * If `row['has_redundancy_dayoff']` is True, add `+0.2` bump. Cap the final score at `5.0`.
       * Return `round(score_combined, 2)`.
       - Wait, make sure that `score_hawker_v2` is used for `hawker` instead of the judged fallback when `--hawker_v2` is provided.
     - Update `score_green(lat, lon, parks, coastal_row=None)`:
       * `s_park = score_by_distance(nearest_m(lat, lon, pts_of(parks)), A_PARK)`
       * If `coastal_row` is not None and `coastal_row['has_blue_within_800m']` is True, add `+0.3` blue space bonus, capped at `5.0`.
       * Return `float(s_park)`, or with bonus: `float(round(min(5.0, s_park + 0.3), 2))`.
   - Update the loop in `run()` to score each estate using the new functions when data is available. If a layer's CLI argument is not provided, fall back to the existing behavior (read from judged_inputs.csv).
   - Ensure that `measured_only` flag calculation is correct.

2. Modify models/liveability_model.py to:
   - Accept optional CLI flag `--bca` (path to data/bca_permits.csv).
   - If provided and file exists:
     * Load the dataset.
     * In `compute_d_multipliers`, for each estate at T0, subtract `severity_score / 1000.0` from the D-multiplier.
     * Keep the floor at `0.70`.
     * Note: At T5, all these current permits will be completed, so the bca penalty at T5 should be 0.0.

3. Update the Makefile:
   - In the `pipeline` target, add commands to run the ingesters first:
     * `python3 models/ingest_tree_canopy.py --estates data/estates.csv --parks data/parks.csv --out data/tree_canopy.csv`
     * `python3 models/ingest_hdb_density.py --estates data/estates.csv --out data/hdb_density.csv`
     * `python3 models/ingest_hawker_v2.py --estates data/estates.csv --markets data/markets.csv --out data/hawker_v2.csv`
     * `python3 models/ingest_coastal.py --estates data/estates.csv --out data/coastal.csv`
     * `python3 models/ingest_bca_permits.py --pipeline data/pipeline_data.json --out data/bca_permits.csv`
   - In the same `pipeline` target:
     * Update `provision_model.py` invocation to pass the new flags pointing to the generated CSVs.
     * Update `liveability_model.py` invocation to pass the new `--bca` flag.
     * Add `python3 models/value_model.py --scores data/provision_scores.csv --hdb data/hdb_resale.csv --private data/ura_private.csv --out data/value_output_private.csv` right before `build_master.py` to regenerate the private value scores.

Output Requirements:
- Write a report of changes made and commands executed to /Users/evancjx/workspace/Housing Estate/SG-Estate-Framework/.agents/worker_r1/changes.md.
- Ensure all tests pass when running `make smoke` or `pytest -q`.
- Regenerate the pipeline by running `make pipeline`, making sure everything runs successfully and output CSV files are updated.
- Send a completion message to the parent (fd16db8f-6668-4819-8851-e872d14dae2a).
