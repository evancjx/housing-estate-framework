## 2026-06-27T02:53:01Z

You are teamwork_preview_worker_ui_tests.
Your working directory is /Users/evancjx/workspace/Housing Estate/SG-Estate-Framework/.agents/worker_ui_tests.
Your task is to implement and verify Milestone 4: R3 & R4: Interactive UI Deliverables Update & Robustness / Test Suite Expansion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope Boundaries:
- Update only UI HTML files, tests, and the test/committed output CSVs (if they changed).
- Do NOT rewrite or modify core logic of scrapers or models unless necessary.

Objective:
1. Update `/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework/framework_diagram.html` to reflect the 20-component pipeline, 81 columns, and the new inputs and models. Specifically:
   - Change `57-column deliverable` to `81-column deliverable` in the subtitle.
   - Update inputs: add `jtc_industrial.csv`, `air_quality.csv`, `covered_linkway.csv`, `town_council_kpi.json` (under geodata). Clarify that `dens`, `env` and `mom` are now data-driven and only `hawker` remains in `judged_inputs.csv`.
   - Update Model 1 (Provision): change `13 components` to `20 components`, and count measured (14), partly (5), judged (1).
   - Update outputs list (master_output.csv): change `32 rows · 57 cols` to `32 rows · 81 cols`. List the new categories: Identity (2), Provision (5), Liveability (32), Gap (24), HDB Value (4), Private Value (4), Extras (2), Employment (4), Lease Risk (4).
2. Regenerate `comparison_table.html` by running:
   `python3 models/gen_comparison_html.py`
3. Update `tests/test_reproducibility.py` to pass the correct new flags during test runs so that the tests pass. Specifically:
   - Add the new CLI flags to the `provision_model.py` command arguments in `test_provision_reproduces`.
   - Add the `--bca` flag to the `liveability_model.py` command arguments in `test_liveability_reproduces`.
   - Add the `--private` flag to the `value_model.py` command arguments in `test_value_reproduces` (writes to value_output_private.csv). Or write a new test for private resale.
4. Expand the pytest suite in `tests/`:
   - In `tests/test_provision_scorers.py`, add unit tests:
     * `test_env_comfort_real_data`: verifies that `score_env` returns valid scores between 1.0 and 5.0, penalises high UHI deltas, and handles missing temperature/canopy data by returning `np.nan` (enforcing renormalisation).
     * `test_hdb_density_scoring`: asserts that `score_dens` correctly maps high resident-per-hectare counts to low scores, and returns `np.nan` for private-dominant estates with zero HDB records.
     * `test_hawker_v2_scoring`: validates that `score_hawker_v2` incorporates distance, stall volume, and redundancy, returning higher scores for high stall counts and active day-off redundancy.
     * `test_coastal_refinement`: checks that `score_green` successfully incorporates blue infrastructure distance metrics from `coastal.csv`, applying a bonus to estates near reservoirs or coastlines.
   - In `tests/test_pipeline_smoke.py`, add integration tests:
     * `test_wired_pipeline_measured_only_flips`: asserts that after executing the scoring pipeline with all 5 new layer flags, the `measured_only` flag in `provision_scores.csv` is `False` for all HDB residential estates.
     * `test_private_value_regression`: verifies that the private resale OLS regression in `value_model.py` fits residuals on `ura_private.csv` transactions, producing valid value scores and bands for Marine Parade and Bedok.
5. Update the snapshot CSV files in `tests/snapshots/before/` to match the newly regenerated `data/` files (provision_scores, liveability_matrix, value_output) so that characterization/snapshot tests pass.
6. Run `make smoke` and verify that all tests pass.
7. Run `make pipeline` to ensure the entire end-to-end pipeline regenerates all outputs correctly and compiles successfully.
8. Record your findings, modifications, and command outputs in /Users/evancjx/workspace/Housing Estate/SG-Estate-Framework/.agents/worker_ui_tests/changes.md.
9. Send a completion message to the parent (fd16db8f-6668-4819-8851-e872d14dae2a).
