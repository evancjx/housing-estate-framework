# Singapore Estate Liveability Framework — Complete Bundle

Everything produced in the design session, organized. Start with the transcript.

## 📄 Start here
- **CONVERSATION-TRANSCRIPT.md** — the full session: the arc v0.1→v0.9, key decisions, the "why rejected" reasoning, verified facts, and the real-data results.

## 📁 frameworks/  (active specs, reference data, historical record)

**Active specs:**
- **[1-provision-framework.md](frameworks/1-provision-framework.md)** — Document 1. Supply-side, objective, comparable. 20-component Provision score + archetype tag.
- **[2-liveability-matrix.md](frameworks/2-liveability-matrix.md)** — Document 2. Demand-side, person-relative. 4-persona × horizon matrix, Value, life-paths. **Contains the full 44-point decision log (Appendix A).**

**Reference data:**
- **[4-estate-timeline-matrix.md](frameworks/4-estate-timeline-matrix.md)** — per-town maturation data (23 HDB towns: MRT lag, polyclinic gaps, SERS, sequencing). Not yet wired into any model; the empirical basis for the Canberra sequencing case and S7 momentum calibration.

**Historical record:**
- **[sg-estate-liveability-framework.md](frameworks/sg-estate-liveability-framework.md)** — v0.1–v0.8 monolith, superseded by the doc-1/doc-2 split; preserves full version-by-version reasoning.
- **[3-estate-growth-framework.md](frameworks/3-estate-growth-framework.md)** — ⚠ SUPERSEDED v0.3 unified design on the obsolete 9-component model. Do not use as a current spec.

## 📁 models/  (runnable pipeline)

Core scoring models (see [CLAUDE.md](CLAUDE.md) for the full pipeline with all ingesters and flags):
- **[provision_model.py](models/provision_model.py)** — 20-component Provision score from geospatial layers. Each model ends with an INPUT CONTRACT block (authoritative column spec).
- **[liveability_model.py](models/liveability_model.py)** — 4-persona × 3-horizon (T0/T5/T15) liveability matrix + Provision–Liveability Gap.
- **[value_model.py](models/value_model.py)** — Value = Provision × exp(−price_residual). HDB and private segmented; band-only below n=100.
- **[momentum_model.py](models/momentum_model.py)** — S7 momentum score from `pipeline_data.json` → updates `judged_inputs.csv`.
- **[build_master.py](models/build_master.py)** — joins all model outputs → [`data/outputs/master_output.csv`](data/outputs/master_output.csv) (headline deliverable).
- **[onemap_geocode_mrt.py](models/onemap_geocode_mrt.py)** — RUN LOCALLY (needs internet + OneMap token). MRT names → `data/inputs/mrt_layer.csv`.
- **12 `ingest_*.py` builders** — one per geospatial layer (jtc_industrial, air_quality, stewardship, tree_canopy, density, hawker v2, coastal, etc.). The canonical run now consumes derived `tree_canopy`, `hdb_density`, `hawker_v2`, `coastal`, and `bca_permits` outputs (see [CLAUDE.md](CLAUDE.md) for wiring status).

### Pipeline order

```bash
make pipeline   # full regeneration: derived layers → provision → liveability → value → master
make smoke      # pytest gate (run before and after changes)
```

See [CLAUDE.md](CLAUDE.md) or the [Makefile](Makefile) for the full per-flag command.

## 📁 data/  (real data — inputs and committed model outputs)

Organised into four subdirectories:
- **`data/inputs/`** — curated + ingester-refreshed layers the models consume (incl. `ura_private.csv`, the cleaned URA transaction layer).
- **`data/outputs/`** — model results from the most recent committed run.
- **`data/raw/`** — scraper artifacts: `raw/ura/` (per-district URA PMI dumps) and `raw/edgeprop/` (not-clean EdgeProp scrape dumps + project lists).
- **`data/_archive/`** — superseded one-off experiment outputs kept for reference; nothing reads them.

Canonical outputs from the most recent committed pipeline run (reproducible via `make pipeline`):
- **[master_output.csv](data/outputs/master_output.csv)** — headline deliverable; estates × Provision/Liveability/Value/Employment/Risk/Life-Path joined across all models.
- **provision_scores.csv**, **liveability_matrix.csv**, **value_output.csv** — intermediate model outputs.
- **lease_risk.csv**, **employment_scores_{T0,T5,T15}.csv** — supporting model outputs.
- **private_transactions_bedrooms.csv** — per-transaction bedroom attribution for the private condo/apartment sector (URA txns + EdgeProp 2019–20 backfill) with a `bedroom_source` provenance column; rebuilt via `make private-bedrooms`. `data/inputs/project_unit_mix.csv` is its curated research input (per-project bedroom↔sqft ranges with source URLs).

Superseded one-off experiment outputs live in `data/_archive/`.

## 📁 _demo-files/  (synthetic — safe to ignore/delete)
Throwaway synthetic data used only to verify the scripts run end-to-end. NOT real. Kept only so the demo runs in the transcript are reproducible.

## 📊 HTML deliverables
- **[comparison_table.html](comparison_table.html)** — interactive cross-model comparison table (estates × Provision/Liveability/Value/Employment/Risk). The headline visual. ⚠ Component/estate counts may lag pipeline regeneration — re-run `python models/gen_comparison_html.py` when counts change.
- **[mrt_comparison_table.html](mrt_comparison_table.html)** — interactive MRT/LRT station table with nearest-estate model context. Re-run `python models/gen_mrt_comparison_html.py` after `data/inputs/mrt_layer.csv` or estate outputs change.
- **[private_project_comparison_table.html](private_project_comparison_table.html)** — interactive private apartment/condo project table with MRT station and postal-district filters. Run `make private-project-locations` with `ONEMAP_TOKEN` to refresh `data/outputs/private_project_locations.csv`, then `make private-project-table`.
- **[condo_framework_comparison.html](condo_framework_comparison.html)** — select any two named condominium records and compare achieved transactions, tenure, access and schools alongside the same estate-context Provision, Liveability, private Value, Employment, Risk and Life Path factors as `comparison_table.html`. Run `make condo-framework-comparison`.
- **[multi_condo_framework_comparison.html](multi_condo_framework_comparison.html)** — build an ordered set of two to five named condominiums, keep project A as the reference, compare the latest five complete years or all safely mapped history, and inspect annual medians, detailed analysis and full filtered transaction ledgers before the separate estate-context framework. Run `make multi-condo-framework-comparison`; this also refreshes the compact on-demand shards in `site/assets/condo-transactions/`.
- **[katong_condo_comparison.html](katong_condo_comparison.html)** — reviewed eight-project Katong comparison with sale-state, bedroom, floor, size, growth, liquidity and full-ledger controls. Run `make katong-comparison`; verified exact-unit analysis activates only when the authorised EdgeProp unit CSV documented in `scrapers/README.md` is present.
- **`data/inputs/school_selectivity.csv` + `make private-project-school-metrics`** — seed school-demand/selectivity proxies and build private-project diagnostics such as primary schools within 1km and best-ranked school within level-specific radii. These are private-buyer diagnostics, not official MOE rankings.
- **[framework_diagram.html](framework_diagram.html)** — architecture diagram (Inputs → Models → `data/outputs/master_output.csv`). Same caveat.

### Static research site

Root HTML files remain the generated report artifacts. [`site/reports.json`](site/reports.json) is
the machine-readable catalog used for report discovery; every non-index root report must have one
entry. Shared browser assets belong in `site/assets/` and are referenced from reports as
`assets/<name>`.

The build also derives a compact `projects.json` lookup from the committed EdgeProp project list
and transaction district field. It contains only project names, slugs, and known districts; raw
transactions and exact-unit records are not published in the lookup.

```bash
make pages-check  # validate catalog coverage and report paths
make pages-build  # assemble the GitHub Pages artifact in _site/
```

The Pages workflow uses the same builder and rejects broken local HTML, stylesheet, script, and
image references before deployment.

## 🔧 Other files & directories
- **[Makefile](Makefile)** — `make smoke` (test gate), `make pipeline` (full regeneration), `make master` (rebuild master only). See [CLAUDE.md](CLAUDE.md) for details.
- **[scrapers/](scrapers/)** ([README](scrapers/README.md)) — URA private-transaction scrapers. Downloads apartment/condo, landed, and strata-landed PMI data by postal district for `value_model.py --private`.
- **[factor_audit_reports/](factor_audit_reports/)** — proposed new framework components from the factor-audit skill. Not auto-applied.
- **[tests/](tests/)** — 62-test pytest suite. `make smoke` or `pytest -q`. Markers: `integration` (slow, real pipeline) and `snapshot` (manual).

---

## ⚠️ Status & honest limitations (read before trusting any number)
1. **Provision is computed from real geospatial and derived layers** — MRT, bus, CHAS clinics, polyclinics, schools, parks, markets, supermarkets, childcare, community clubs, sport centres, flood-prone areas, expressway noise, aircraft-corridor (air_noise), eldercare, covered linkways, JTC industrial buffer (jtc_industrial), air-quality index proxy (air_quality), TC-KPI stewardship scores (stewardship), density, tree-canopy/UHI, hawker v2, and coastal blue-infra are all ingested. Provision numbers still carry a ±0.3 cross-grader noise bar. Run `make smoke` for the test gate, `make pipeline` to regenerate.
2. **Value is segmented by tenure universe.** HDB resale Value is real where HDB resale exists. Private resale Value is also generated from URA PMI data where district coverage maps cleanly to framework estates, including landed and strata-landed raw rows. These are separate segments and must not be blended.
3. **HDB gaps remain explicit.** Tengah has no HDB resale Value because it is pre-MOP, and Canberra HDB is folded into Sembawang town. Private-dominant gaps such as Holland Village still depend on clean mapped private coverage.
4. **6 of 20 components remain PARTLY_MEASURED** (`dens`, `env`, `mom`, `air_quality`, `stewardship`, `hawker`). They use generated layers or curated public snapshots, but still carry approximation limits; `provision_model.py` flags missing PARTLY inputs and renormalises rather than imputing.
5. **Report bands, not decimals.** Most established estates cluster within noise; the decimals are not real distinctions.
6. **Re-verify all dated facts** (in the transcript) before any scoring run — MRT dates, polyclinic openings, etc. decay.

## Data file note
`data/_archive/value_private.csv` is a stale pre-fix artifact superseded by `data/outputs/value_output_private.csv` (the canonical de-circularised private Value output) and is NOT consumed by the pipeline.

`data/outputs/private_project_locations.csv`, when present, is the reviewed OneMap geocode cache for private project coordinates. Without it, `private_project_comparison_table.html` falls back to estate/planning-area centroids and marks those rows as centroid fallback.

`data/inputs/school_selectivity.csv` is a sourced seed of unofficial ranking proxies: primary P1 demand, secondary PSLE AL cut-off, and JC/JAE cut-off. It is intentionally not blended into Provision until the source treatment is reviewed.

## Next step to make it more data-driven
Refresh `pipeline_data.json` through the networked ingesters, review the resulting momentum shifts, and add dedicated Value segments for rentals, ECs, and landed resale instead of folding all private resale into one segment.
