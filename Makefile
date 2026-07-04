.PHONY: smoke master private-project-locations private-project-school-metrics private-project-table pipeline

# Reproducibility + correctness gate: the full pytest suite.
smoke:
	python3 -m pytest -q

# Rebuild the joined master_output.csv from the current model outputs.
master:
	python3 models/build_master.py

# Geocode unique private apartment/condo project locations with OneMap.
# Requires ONEMAP_TOKEN and network access; review data/private_project_locations.csv before relying on it.
private-project-locations:
	python3 models/geocode_private_projects.py --resume

# Build project-level school proximity/selectivity diagnostics.
# Requires reviewed data/private_project_locations.csv from the target above.
private-project-school-metrics:
	python3 models/private_school_metrics.py

# Generate the private project comparison table from committed transactions and optional geocodes.
private-project-table:
	python3 models/gen_private_project_comparison_html.py

# Regenerate the whole pipeline from real data, then the master.
# Includes derived provision layers and BCA disruption severity; see CLAUDE.md.
pipeline:
	python3 models/ingest_tree_canopy.py --estates data/estates.csv --parks data/parks.csv \
	  --out data/tree_canopy.csv --mss-fallback data/tree_canopy.csv
	python3 models/ingest_hdb_density.py --estates data/estates.csv --out data/hdb_density.csv
	python3 models/ingest_hawker_v2.py --estates data/estates.csv --markets data/markets.csv --out data/hawker_v2.csv
	python3 models/ingest_coastal.py --estates data/estates.csv --out data/coastal.csv
	python3 models/ingest_bca_permits.py --pipeline data/pipeline_data.json --estates data/estates.csv --year 2026 --out data/bca_permits.csv
	python3 models/provision_model.py --estates data/estates.csv \
	  --mrt data/mrt_layer.csv --bus data/bus_routes.csv --clinics data/chas.csv \
	  --polyclinics data/polyclinics.csv --schools data/schools.csv --parks data/parks.csv \
	  --markets data/markets.csv --supermarkets data/supermarkets.csv \
	  --childcare data/childcare.csv --community data/community.csv --sport data/sport.csv \
	  --flood data/flood_risk.csv --noise data/expressways.csv \
	  --air_noise data/air_noise_corridors.csv --eldercare data/eldercare.csv \
	  --covered_linkway data/covered_linkway.csv \
	  --jtc_industrial data/jtc_industrial.csv --air_quality data/air_quality.csv \
	  --tcmr data/town_council_kpi.json \
	  --tree_canopy data/tree_canopy.csv \
	  --hdb_density data/hdb_density.csv \
	  --hawker_v2 data/hawker_v2.csv \
	  --coastal data/coastal.csv \
	  --judged data/judged_inputs.csv \
	  --out data/provision_scores.csv
	python3 models/liveability_model.py --scores data/provision_scores.csv \
	  --pipeline data/pipeline_data.json --archetypes data/archetype_assignments.csv \
	  --bca data/bca_permits.csv \
	  --out data/liveability_matrix.csv
	# Pass 1 — HDB-only residuals → value_output.csv (used by build_master for value_hdb_*).
	python3 models/value_model.py --scores data/provision_scores.csv \
	  --hdb data/hdb_resale.csv --out data/value_output.csv
	# Pass 2 — HDB + private combined → value_output_private.csv (used by build_master for value_private_*).
	# Both segments are written to the same file; build_master reads it and splits by the 'segment' column.
	python3 models/value_model.py --scores data/provision_scores.csv \
	  --hdb data/hdb_resale.csv --private data/ura_private.csv --out data/value_output_private.csv
	# Lease risk + employment are joined into master_output.csv by build_master, so regenerate them
	# here too (previously omitted — build_master would silently reuse stale committed copies).
	python3 models/lease_risk_model.py
	python3 models/employment_model.py
	# NOTE: S7 momentum is deliberately NOT auto-refreshed. momentum_model.py writes
	# judged_inputs_updated.csv for human review; its values must be vetted and copied into
	# judged_inputs.csv before re-running provision (judged_inputs.csv also carries manual mom
	# overrides that a blind copy would clobber). Run `python3 models/momentum_model.py` manually.
	python3 models/build_master.py
