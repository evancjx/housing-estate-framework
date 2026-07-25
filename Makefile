.PHONY: smoke pages-check pages-build master private-project-locations private-project-school-metrics private-project-table poiz-east-comparison poiz-east-unit-growth katong-comparison canberra-d27-analysis canberra-d27-strategies canberra-d27-reports private-bedrooms pipeline

# Reproducibility + correctness gate: the full pytest suite.
smoke:
	python3 -m pytest -q

# Validate the static research catalog without writing a Pages artifact.
pages-check:
	python3 scripts/build_pages_site.py

# Assemble the same static artifact deployed by the GitHub Pages workflow.
pages-build:
	python3 scripts/build_pages_site.py --out _site

# Rebuild the joined master_output.csv from the current model outputs.
master:
	python3 models/build_master.py

# Geocode unique private apartment/condo project locations with OneMap.
# Requires ONEMAP_TOKEN and network access; review data/outputs/private_project_locations.csv before relying on it.
private-project-locations:
	python3 models/geocode_private_projects.py --resume

# Build project-level school proximity/selectivity diagnostics.
# Requires reviewed data/outputs/private_project_locations.csv from the target above.
private-project-school-metrics:
	python3 models/private_school_metrics.py

# Generate the private project comparison table from committed transactions and optional geocodes.
private-project-table:
	python3 models/gen_private_project_comparison_html.py

# Generate the curated, resale-only Poiz-versus-East project diagnostic.
poiz-east-comparison:
	python3 models/gen_poiz_east_resale_comparison_html.py

# Generate unit-type growth and full resale ledgers for the curated Poiz/East projects.
poiz-east-unit-growth:
	python3 models/gen_poiz_east_unit_growth_html.py

# Generate the reviewed Katong project, sale-state and transaction comparison.
# Exact-unit analysis activates only when an authorised EdgeProp unit CSV exists.
katong-comparison:
	python3 models/gen_katong_comparison_html.py

# Generate Canberra Crescent Residences versus District 27 deep analysis.
canberra-d27-analysis:
	python3 models/gen_canberra_crescent_d27_html.py

# Generate the six Canberra comparison-strategy workbooks.
canberra-d27-strategies:
	python3 models/gen_canberra_d27_peer_strategy_html.py
	python3 models/gen_canberra_d27_control_strategy_html.py

# Rebuild the Canberra district analysis and every linked strategy workbook.
canberra-d27-reports: canberra-d27-analysis canberra-d27-strategies

# Per-transaction bedroom attribution (URA txns + EdgeProp 2019-20 backfill).
# NOT part of `pipeline` — different data family (private transactions, not estate scores);
# refresh after an EdgeProp re-scrape or a project_unit_mix.csv research batch.
private-bedrooms:
	python3 models/build_private_bedrooms.py --report

# Regenerate the whole pipeline from real data, then the master.
# Includes derived provision layers and BCA disruption severity; see CLAUDE.md.
pipeline:
	python3 models/ingest_tree_canopy.py --estates data/inputs/estates.csv --parks data/inputs/parks.csv \
	  --out data/inputs/tree_canopy.csv --mss-fallback data/inputs/tree_canopy.csv
	python3 models/ingest_hdb_density.py --estates data/inputs/estates.csv --out data/inputs/hdb_density.csv
	python3 models/ingest_hawker_v2.py --estates data/inputs/estates.csv --markets data/inputs/markets.csv --out data/inputs/hawker_v2.csv
	python3 models/ingest_coastal.py --estates data/inputs/estates.csv --out data/inputs/coastal.csv
	python3 models/ingest_bca_permits.py --pipeline data/inputs/pipeline_data.json --estates data/inputs/estates.csv --year 2026 --out data/inputs/bca_permits.csv
	python3 models/provision_model.py --estates data/inputs/estates.csv \
	  --mrt data/inputs/mrt_layer.csv --bus data/inputs/bus_routes.csv --clinics data/inputs/chas.csv \
	  --polyclinics data/inputs/polyclinics.csv --schools data/inputs/schools.csv --parks data/inputs/parks.csv \
	  --markets data/inputs/markets.csv --supermarkets data/inputs/supermarkets.csv \
	  --childcare data/inputs/childcare.csv --community data/inputs/community.csv --sport data/inputs/sport.csv \
	  --flood data/inputs/flood_risk.csv --noise data/inputs/expressways.csv \
	  --air_noise data/inputs/air_noise_corridors.csv --eldercare data/inputs/eldercare.csv \
	  --covered_linkway data/inputs/covered_linkway.csv \
	  --jtc_industrial data/inputs/jtc_industrial.csv --air_quality data/inputs/air_quality.csv \
	  --tcmr data/inputs/town_council_kpi.json \
	  --tree_canopy data/inputs/tree_canopy.csv \
	  --hdb_density data/inputs/hdb_density.csv \
	  --hawker_v2 data/inputs/hawker_v2.csv \
	  --coastal data/inputs/coastal.csv \
	  --judged data/inputs/judged_inputs.csv \
	  --out data/outputs/provision_scores.csv
	python3 models/liveability_model.py --scores data/outputs/provision_scores.csv \
	  --pipeline data/inputs/pipeline_data.json --archetypes data/inputs/archetype_assignments.csv \
	  --bca data/inputs/bca_permits.csv \
	  --out data/outputs/liveability_matrix.csv
	# Pass 1 — HDB-only residuals → value_output.csv (used by build_master for value_hdb_*).
	python3 models/value_model.py --scores data/outputs/provision_scores.csv \
	  --hdb data/inputs/hdb_resale.csv --out data/outputs/value_output.csv
	# Pass 2 — HDB + private combined → value_output_private.csv (used by build_master for value_private_*).
	# Both segments are written to the same file; build_master reads it and splits by the 'segment' column.
	python3 models/value_model.py --scores data/outputs/provision_scores.csv \
	  --hdb data/inputs/hdb_resale.csv --private data/inputs/ura_private.csv --out data/outputs/value_output_private.csv
	# Lease risk + employment are joined into master_output.csv by build_master, so regenerate them
	# here too (previously omitted — build_master would silently reuse stale committed copies).
	python3 models/lease_risk_model.py
	python3 models/employment_model.py
	# NOTE: S7 momentum is deliberately NOT auto-refreshed. momentum_model.py writes
	# judged_inputs_updated.csv for human review; its values must be vetted and copied into
	# judged_inputs.csv before re-running provision (judged_inputs.csv also carries manual mom
	# overrides that a blind copy would clobber). Run manually:
#   python3 models/momentum_model.py --pipeline data/inputs/pipeline_data.json \
#     --judged data/inputs/judged_inputs.csv --out data/outputs/judged_inputs_updated.csv
	python3 models/build_master.py
