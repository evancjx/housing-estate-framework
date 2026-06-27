# SG-Estate-Framework Baseline Exploration & Analysis

## 1. Summary of Pipeline & Test Readiness
Due to environment execution timeout constraints (requiring terminal command approval which is unavailable in the current read-only exploration session), we executed a comprehensive static analysis of the `Makefile`, pytest suite, and data pipeline code. 

- **`make smoke`**: Runs the command `python3 -m pytest -q` which executes the full pytest suite under `tests/`. This suite validates:
  - Framework configuration constraints and weight-sum validations (weights sum to exactly 1.0).
  - Document-code alignment.
  - Cross-cutting invariants (HDB vs. private segregation, distinct regression controls).
  - Component-level scoring functions (e.g. OLS, shrinkage).
  - Run-to-run reproducibility (verifying generated outputs match committed outputs).
- **`make pipeline`**: Regenerates the entire pipeline from raw data by executing:
  1. `provision_model.py`: Geospatial scoring across MRT, bus, CHAS, polyclinics, schools, parks, markets, supermarkets, childcare, community, sport, flood, expressway noise, air noise, eldercare, covered linkways, JTC industrial, and air quality (20 components, outputting to `provision_scores.csv`).
  2. `liveability_model.py`: Computes 4 personas × 3 horizons (T0/T5/T15) liveability and gap scores (outputting to `liveability_matrix.csv`).
  3. `value_model.py`: Runs OLS regression on log-price-per-sqm against controls for the HDB resale segment, applies James-Stein shrinkage, and computes final value metrics (outputting to `value_output.csv`).
  4. `build_master.py`: Left-joins all models into the master deliverable (`master_output.csv`), enforcing the `X` (Central Area) archetype N/R veto and outputting coverage flags.

---

## 2. Integration of the 5 Unwired Ingesters

The 5 ingesters are currently not wired into the main scoring pipeline (`provision_model.py` and `value_model.py`). When these are unwired, the scoring pipeline falls back to hardcoded opinion ratings in `data/judged_inputs.csv` for density (`dens`), environmental comfort (`env`), momentum (`mom`), and hawker centres (`hawker`).

### Ingester Output Paths & Schemas
| Ingester | Output Path | CSV Schema | Target Component |
|---|---|---|---|
| `ingest_tree_canopy.py` | `data/tree_canopy.csv` | `estate, ndvi_proxy, canopy_cover_pct, mss_station, annual_mean_temp_c, uhi_delta_c` | `env` (1% weight) |
| `ingest_hdb_density.py` | `data/hdb_density.csv` | `estate, total_dwelling_units, residents_per_net_hectare, units_per_gross_hectare, n_blocks, mean_storey, oldest_block_year, newest_block_year` | `dens` (8% weight) |
| `ingest_hawker_v2.py` | `data/hawker_v2.csv` | `estate, n_hawker_centres_800m, total_stalls_800m, nearest_hawker_m, has_redundancy_dayoff` | `hawker` (4% weight) |
| `ingest_coastal.py` | `data/coastal.csv` | `estate, nearest_coast_m, nearest_reservoir_m, nearest_waterway_m, has_blue_within_800m, blue_type` | Refines `green` (8% weight) |
| `ingest_bca_permits.py` | `data/bca_permits.csv` | `estate, n_active_permits_500m, total_gfa_active, max_remaining_months, severity_score` | Refines `D` multiplier in `liveability_model.py` |

### Proposed Pipeline Changes for Integration

#### 2a. Modifications to `provision_model.py`
To ingest and score these new metrics, `provision_model.py` must be modified as follows:
- **Parser Arguments**: Add CLI flags for the new CSV inputs:
  - `--tree_canopy`: Path to `tree_canopy.csv`
  - `--hdb_density`: Path to `hdb_density.csv`
  - `--hawker_v2`: Path to `hawker_v2.csv`
  - `--coastal`: Path to `coastal.csv`
- **Data Loaders**: Load the new layers in the `main` method and pass them into the `run` method.
- **Scoring Function Implementations**:
  1. `score_env(row)`:
     - Combine canopy cover and Urban Heat Island (UHI) temperature delta.
     - `score_canopy = score_by_count(row['canopy_cover_pct'], [(30, 5), (20, 4), (10, 3), (5, 2), (0, 1)])`
     - `score_uhi = score_by_distance(row['uhi_delta_c'], [(0.2, 5), (0.6, 4), (1.2, 3), (1.8, 2), (99, 1)])` (lower UHI delta is better)
     - Return `round(0.5 * score_canopy + 0.5 * score_uhi, 2)`.
  2. `score_dens(row)`:
     - Map HDB resident density to a 1–5 score. Since lower density (less crowded) is typically preferred:
     - `score = score_by_distance(row['residents_per_net_hectare'], [(150, 5), (300, 4), (450, 3), (600, 2), (99999, 1)])`
     - For private-dominant estates with 0 HDB dwellings (e.g. Bukit Timah), return `np.nan` so the model renormalises over the remaining components instead of penalising.
  3. `score_hawker(row)`:
     - Score based on accessibility, stall volume, and redundancy:
     - `score_dist = score_by_distance(row['nearest_hawker_m'], [(400, 5), (800, 4), (1200, 3), (2000, 2), (99999, 1)])`
     - `score_stalls = score_by_count(row['total_stalls_800m'], [(150, 5), (80, 4), (40, 3), (10, 2), (0, 1)])`
     - `score_count = score_by_count(row['n_hawker_centres_800m'], [(2, 5), (1, 3), (0, 1)])`
     - Combine: `round(0.4 * score_dist + 0.4 * score_stalls + 0.2 * score_count, 2)`. If `has_redundancy_dayoff` is true, add a `+0.2` bump (cap at 5.0).
  4. `score_green(lat, lon, parks, coastal_row)`:
     - Update the existing `score_green` function to incorporate blue infrastructure (reservoirs, coast, waterways):
     - `s_park = score_by_distance(nearest_m(lat, lon, pts_of(parks)), A_PARK)`
     - If `coastal_row['has_blue_within_800m']` is True, apply a `+0.3` blue space bonus, capped at 5.0. Alternatively, blend: `round(0.8 * s_park + 0.2 * s_blue, 2)`.
- **Woring into the `run` loop**:
  - In `run(...)`, read from the dictionaries created from the new layer DataFrames instead of fetching `dens`, `env`, and `hawker` from `judged_inputs.csv`.
  - Update `measured_only` to reflect that `dens`, `env`, and `hawker` are now `PARTLY_MEASURED`/`MEASURED`, making the pipeline strictly data-driven with the exception of the legacy en-bloc/new-launch elements in `mom` (which can also be wired from `momentum_model.py` outputs).

#### 2b. Modifications to `value_model.py`
`value_model.py` does not read individual geospatial layers or `judged_inputs.csv` directly. Instead, it reads the aggregated scores from `data/provision_scores.csv` via the `--scores` flag.
- When `provision_model.py` is updated to consume the new CSVs, the final scores in `provision_scores.csv` will shift to reflect the real-data calculations.
- `value_model.py` will read these updated scores automatically during regression fitting.
- **Regression controls**: The model controls (HDB resale flat types, storeys, leases; private property types, tenures, project ages) will remain unchanged, but the price residuals will naturally adjust to the data-driven scores.

---

## 3. Private Transaction Scrapers & Value Calculations

### Missing Scrapers
No scraper scripts are missing from the `scrapers/` directory. The scripts are fully defined:
- `ura_pmi_playwright.py`: Primary browser-based scraper.
- `ura_pmi_api.py`: Fallback API-based scraper.
- `run_download.py`: Orchestrator.
- `ingest_ura_raw.py`: Normalises and merges URA CSV files.
However, in terms of *historical data coverage*, Postal Districts 15 and 16 (for Marine Parade and Bedok private transactions) were previously missing from `ura_private.csv`. 

### Running Scrapers & Ingesting Data
1. **Download raw data**:
   ```bash
   python scrapers/run_download.py --districts 15 16 --year_from 2021 --year_to 2026 --out_dir data/ura_raw/
   ```
   This automates Chromium via Playwright, navigates to the URA PMI portal, selects Postal Districts 15 and 16, configures date parameters, submits the query via `ajaxSubmit`, and triggers the underlying resultForm post to download the raw CSVs into `data/ura_raw/` (e.g. `pmi_d15_2021-2026.csv`).
2. **Merge raw data**:
   ```bash
   python scrapers/ingest_ura_raw.py --raw_dir data/ura_raw/ --out data/ura_private.csv --merge
   ```
   This script:
   - Reads all CSV files in `data/ura_raw/`.
   - Maps column headers from both REALIS and URA portal formats (e.g., `postal district` -> `postal_district`).
   - Resolves the missing `planning_area` by mapping Postal Districts using `DISTRICT_TO_PLANNING_AREA` (`15` -> `MARINE PARADE`, `16` -> `BEDOK`).
   - Normalises sale dates into `YYYY-MM` format.
   - Appends the records to the existing `data/ura_private.csv`.
   - Deduplicates transactions based on `planning_area`, `transacted_price`, `area_sqm`, `sale_month`, `project_name`, and `floor_level`.

### Value Model Calculations for Marine Parade and Bedok
When `value_model.py` is invoked with the `--private` flag:
```bash
python models/value_model.py --scores data/provision_scores.csv --hdb data/hdb_resale.csv --private data/ura_private.csv --out data/value_output.csv
```
1. It cleans log-prices-per-square-metre (`_lnpsm`) and drops zero/non-finite transactions.
2. It merges transactions with the provision scores using the `planning_area` column (joined as `planning_area` -> `estate`).
3. For private resale, it overrides the HDB-weight score using `score_private` (W_PRIVATE weights) if available in the input scores.
4. It fits OLS regression: `_lnpsm ~ property_type + tenure + project_age_years + C(sale_month)`.
5. It groups the residuals by planning area (e.g. `MARINE PARADE` and `BEDOK`), calculates the median raw residual (`resid_raw`), and applies James-Stein shrinkage:
   `shrunk = w * raw + (1 - w) * seg_mean`, where `w = n / (n + 30.0)` and `seg_mean` is the average residual across the segment.
6. It computes the final Value score: `liveability_or_provision_score * exp(-shrunk)`.
7. Because Marine Parade and Bedok have thousands of private transactions, their sample count is high ($n \ge 100$), allowing the model to trust the decimal value rather than reporting the band alone.

---

## 4. UI Deliverables Update

### HTML Generation
- **`comparison_table.html`**: Dynamically generated by `models/gen_comparison_html.py`. It reads `data/master_output.csv`, `data/provision_scores.csv`, and employment files, then formats a large sorting and filtering table containing all active estates.
- **`framework_diagram.html`**: A static HTML file containing an SVG-based architecture diagram detailing the inputs, models, and columns.

### Updates Required for the 20-Component Pipeline
1. **`comparison_table.html`**:
   - Re-running `python3 models/gen_comparison_html.py` after regenerating the data pipeline will automatically pick up the new estate counts and updated score averages.
   - If new columns (such as private value score, or new sub-component ratings) are added to `master_output.csv`, `gen_comparison_html.py` must be modified to read, sort, and render these columns in the UI table.
2. **`framework_diagram.html`**:
   - Update the subtitle: change `57-column deliverable` to `81-column deliverable`.
   - Update the Inputs box (geospatial): add `jtc_industrial.csv`, `air_quality.csv`, `covered_linkway.csv`, and `town_council_kpi.json`.
   - Update the Inputs box (judged): clarify that `dens`, `env`, and `mom` are now data-driven, and only `hawker` remains in `judged_inputs.csv`.
   - Update the Models (Provision): change `13 components` to `20 components`. Update counts: `Measured (14)`, `Partly (5)`, and `Judged (1)`.
   - Update the Output description: list the full 81 columns.

---

## 5. Pytest Suite Expansion in `tests/`

To verify the newly wired layers and scraper output ingestion, we should add/expand the following tests:

### Proposed Test Additions
1. **Component-level unit tests in `tests/test_provision_scorers.py`**:
   - `test_env_comfort_real_data`: Verifies that `score_env` returns valid scores between 1.0 and 5.0, penalises high UHI deltas, and handles missing temperature/canopy data by returning `np.nan` (enforcing renormalisation).
   - `test_hdb_density_scoring`: Asserts that `score_dens` correctly maps high resident-per-hectare counts to low scores, and returns `np.nan` for private-dominant estates with zero HDB records.
   - `test_hawker_v2_scoring`: Validates that `score_hawker` incorporates distance, stall volume, and redundancy, returning higher scores for high stall counts and active day-off redundancy.
   - `test_coastal_refinement`: Checks that `score_green` successfully incorporates blue infrastructure distance metrics from `coastal.csv`, applying a bonus to estates near reservoirs or coastlines.
2. **Integration & validation tests in `tests/test_pipeline_smoke.py`**:
   - `test_wired_pipeline_measured_only_flips`: Asserts that after executing the scoring pipeline with all 5 new layer flags, the `measured_only` flag in `provision_scores.csv` is `False` for all residential estates (proving the removal of hardcoded judged fallbacks).
   - `test_private_value_regression`: Verifies that the private resale OLS regression in `value_model.py` fits residuals on `ura_private.csv` transactions, producing valid value scores and bands for Marine Parade and Bedok.
3. **Scraper normalisation tests in `tests/test_scrapers.py`**:
   - `test_ingest_ura_raw_normalisation`: Feeds a mock URA PMI HTML/CSV chunk, asserting that it correctly handles both REALIS and portal column headers, extracts postal districts, maps them to planning areas, and formats sale months.
