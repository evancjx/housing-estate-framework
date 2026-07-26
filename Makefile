PYTHON ?= python3
AS_OF_YEAR ?= 2026

.PHONY: smoke pages-check pages-build framework-diagram master private-project-locations private-project-school-metrics private-project-table condo-framework-comparison multi-condo-framework-comparison poiz-east-comparison poiz-east-unit-growth katong-comparison canberra-d27-analysis canberra-d27-strategies canberra-d27-reports private-bedrooms pipeline pipeline-reuse

# Reproducibility + correctness gate: the full pytest suite.
smoke:
	$(PYTHON) -m pytest -q

# Validate the static research catalog without writing a Pages artifact.
pages-check:
	$(PYTHON) scripts/build_pages_site.py

# Assemble the same static artifact deployed by the GitHub Pages workflow.
pages-build:
	$(PYTHON) scripts/build_pages_site.py --out _site

framework-diagram:
	$(PYTHON) -m sg_estate.reporting.builders.framework_diagram

# Rebuild the joined master_output.csv from the current model outputs.
master:
	$(PYTHON) -m sg_estate.application.master

# Geocode unique private apartment/condo project locations with OneMap.
# Requires ONEMAP_TOKEN and network access; review data/outputs/private_project_locations.csv before relying on it.
private-project-locations:
	$(PYTHON) models/geocode_private_projects.py --resume

# Build project-level school proximity/selectivity diagnostics.
# Requires reviewed data/outputs/private_project_locations.csv from the target above.
private-project-school-metrics:
	$(PYTHON) models/private_school_metrics.py

# Generate the private project comparison table from committed transactions and optional geocodes.
private-project-table:
	$(PYTHON) models/gen_private_project_comparison_html.py

# Generate the interactive two-condominium project and estate-context comparison.
condo-framework-comparison:
	$(PYTHON) models/gen_condo_framework_comparison_html.py

# Generate the 2–5 project matrix plus on-demand five-year/all-history transaction shards.
multi-condo-framework-comparison:
	$(PYTHON) models/gen_multi_condo_framework_comparison_html.py

# Generate the curated, resale-only Poiz-versus-East project diagnostic.
poiz-east-comparison:
	$(PYTHON) models/gen_poiz_east_resale_comparison_html.py

# Generate unit-type growth and full resale ledgers for the curated Poiz/East projects.
poiz-east-unit-growth:
	$(PYTHON) models/gen_poiz_east_unit_growth_html.py

# Generate the reviewed Katong project, sale-state and transaction comparison.
# Exact-unit analysis activates only when an authorised EdgeProp unit CSV exists.
katong-comparison:
	$(PYTHON) models/gen_katong_comparison_html.py

# Generate Canberra Crescent Residences versus District 27 deep analysis.
canberra-d27-analysis:
	$(PYTHON) models/gen_canberra_crescent_d27_html.py

# Generate the six Canberra comparison-strategy workbooks.
canberra-d27-strategies:
	$(PYTHON) models/gen_canberra_d27_peer_strategy_html.py
	$(PYTHON) models/gen_canberra_d27_control_strategy_html.py

# Rebuild the Canberra district analysis and every linked strategy workbook.
canberra-d27-reports: canberra-d27-analysis canberra-d27-strategies

# Per-transaction bedroom attribution (URA txns + EdgeProp 2019-20 backfill).
# NOT part of `pipeline` — different data family (private transactions, not estate scores);
# refresh after an EdgeProp re-scrape or a project_unit_mix.csv research batch.
private-bedrooms:
	$(PYTHON) models/build_private_bedrooms.py --report

# Regenerate and validate the whole pipeline in a staging run, then promote all
# canonical files as one rollback-safe transaction. Momentum remains a manual
# review gate and is deliberately outside this command.
pipeline:
	$(PYTHON) -m sg_estate.application.pipeline --as-of-year $(AS_OF_YEAR)

# Deterministic/offline rebuild using the committed derived input layers.
pipeline-reuse:
	$(PYTHON) -m sg_estate.application.pipeline --as-of-year $(AS_OF_YEAR) --reuse-derived
