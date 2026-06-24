.PHONY: smoke master pipeline

# Reproducibility + correctness gate: the full pytest suite.
smoke:
	python3 -m pytest -q

# Rebuild the joined master_output.csv from the current model outputs.
master:
	python3 models/build_master.py

# Regenerate the whole pipeline from real data, then the master.
# (eldercare + air_noise + jtc_industrial + air_quality + tcmr are wired in; see CLAUDE.md.)
pipeline:
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
	  --judged data/judged_inputs.csv \
	  --out data/provision_scores.csv
	python3 models/liveability_model.py --scores data/provision_scores.csv \
	  --pipeline data/pipeline_data.json --archetypes data/archetype_assignments.csv \
	  --out data/liveability_matrix.csv
	python3 models/value_model.py --scores data/provision_scores.csv \
	  --hdb data/hdb_resale.csv --out data/value_output.csv
	python3 models/build_master.py
