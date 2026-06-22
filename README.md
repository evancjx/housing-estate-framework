# Singapore Estate Liveability Framework — Complete Bundle

Everything produced in the design session, organized around a reproducible local pipeline.

## 📄 Start here
- **CLAUDE.md** — operating guide for the repository, including pipeline order, invariants, and the shared-config refactor decision.

## 📁 frameworks/  (the actual framework — two cross-referencing documents)
- **1-provision-framework.md** — Document 1. Supply-side, objective, comparable. "What is here." One score + archetype tag. This is the renamed "Core."
- **2-liveability-matrix.md** — Document 2. Demand-side, person-relative. Persona × horizon matrix, Value, life-paths. **Contains the full 44-point decision log (Appendix A).**
- **sg-estate-liveability-framework.md** — the original v0.1–v0.8 monolith, kept as the historical record (superseded by the two split documents but preserves the full version-by-version reasoning).

## 📁 models/  (runnable pipeline)
- **framework_config.py** — single source of truth for weights, bands, S-groups, and aliases.
- **provision_model.py** — computes Provision from geospatial layers (MRT, clinics, schools, parks, etc.). INPUT CONTRACT at bottom of file.
- **liveability_model.py** — computes persona × horizon liveability cells from Provision and pipeline data.
- **value_model.py** — computes Value = Provision × price-residual from transaction data. Segmented (HDB/private), shrinkage, band-only below n=100. INPUT CONTRACT at bottom.
- **build_master_output.py** — joins canonical outputs into `life_paths.csv` and `master_output.csv`.
- **onemap_geocode_mrt.py** — RUN LOCALLY (needs internet). Converts station names → coordinates via OneMap. Produces the MRT layer the provision model needs.
- **smoke_test.py** — regenerates deterministic outputs in a temp directory and compares them to committed canonical CSVs.

### Pipeline order
```
# 1. (local) geocode MRT if you don't have a coordinate file
python onemap_geocode_mrt.py            # needs OneMap token + internet

# 2. compute provision from geodata
python provision_model.py --estates estates.csv --mrt mrt_layer.csv \
    --clinics chas.csv --schools schools.csv --parks parks.csv ... \
    --judged judged.csv --out provision_scores.csv

# 3. compute value from provision + prices
python value_model.py --scores provision_scores.csv --hdb hdb_resale.csv

# 4. verify reproducibility from repo root
make smoke

# 5. rebuild aggregate report output
make master
```

## 📁 data/  (real outputs + inputs from this session)
- **value_real.csv** — Value scores from REAL HDB resale data (2025–26, ~36k txns). The headline result.
- **scores_real.csv** — the provision scores (judgment-based) fed into the real value run.
- **value_coastal.csv / scores_coastal.csv** — the Bedok / Marine Parade coastal comparison.
- **provision_demo.csv** — sample provision-model output.

## 📁 _demo-files/  (synthetic — safe to ignore/delete)
Throwaway synthetic data used only to verify the scripts run end-to-end. NOT real. Kept only so the demo runs in the transcript are reproducible.

---

## ⚠️ Status & honest limitations (read before trusting any number)
1. **Provision is partly measured and partly judged.** The repository now includes real geospatial layers for MRT, bus routes, clinics, polyclinics, schools, parks, markets, supermarkets, childcare, community, sport, flood, expressway noise, aircraft-corridor proxy, eldercare, and covered linkways. Density-feel, environmental comfort, momentum, and hawker reputation still carry judgment or partial-measurement caveats.
2. **Value is real where HDB resale exists.** It does NOT cover private/landed enclaves (East Coast, Siglap, Holland Village) — those need URA private transaction data (Postal Districts 15/16).
3. **Tengah & Canberra have no resale Value** — Tengah pre-MOP (no market yet), Canberra folded into Sembawang town.
4. **3 of 9 components are irreducibly judgment** (density-feel, environmental comfort, momentum) — they cannot come from a shapefile and are flagged as such in the model.
5. **Report bands, not decimals.** Most established estates cluster within noise; the decimals are not real distinctions.
6. **Re-verify all dated facts** in `data/pipeline_data.json` and the framework docs before any scoring run — MRT dates, polyclinic openings, etc. decay.

## Next step to make it fully data-driven
Replace remaining judged/partly-judged inputs with auditable data sources where possible, then add URA private transaction coverage for landed/private enclaves.
