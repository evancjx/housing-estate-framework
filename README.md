# Singapore Estate Liveability Framework — Complete Bundle

Everything produced in the design session, organized. Start with the transcript.

## 📄 Start here
- **CONVERSATION-TRANSCRIPT.md** — the full session: the arc v0.1→v0.9, key decisions, the "why rejected" reasoning, verified facts, and the real-data results.

## 📁 frameworks/  (the actual framework — two cross-referencing documents)
- **1-provision-framework.md** — Document 1. Supply-side, objective, comparable. "What is here." One score + archetype tag. This is the renamed "Core."
- **2-liveability-matrix.md** — Document 2. Demand-side, person-relative. Persona × horizon matrix, Value, life-paths. **Contains the full 44-point decision log (Appendix A).**
- **sg-estate-liveability-framework.md** — the original v0.1–v0.8 monolith, kept as the historical record (superseded by the two split documents but preserves the full version-by-version reasoning).

## 📁 models/  (runnable pipeline)
- **provision_model.py** — computes Provision from geospatial layers (MRT, clinics, schools, parks, etc.). Measures 14 components geospatially, flags 5 as partly-measured and 1 (hawker) as judgment. INPUT CONTRACT at bottom of file.
- **value_model.py** — computes Value = Provision × price-residual from transaction data. Segmented (HDB/private), shrinkage, band-only below n=100. INPUT CONTRACT at bottom.
- **onemap_geocode_mrt.py** — RUN LOCALLY (needs internet). Converts station names → coordinates via OneMap. Produces the MRT layer the provision model needs.

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
1. **Provision is computed from real geospatial layers** — MRT, bus, CHAS clinics, polyclinics, schools, parks, markets, supermarkets, childcare, community clubs, sport centres, flood-prone areas, expressway noise, aircraft-corridor (air_noise), eldercare, covered linkways, JTC industrial buffer (jtc_industrial), air-quality index proxy (air_quality), and TC-KPI stewardship scores (stewardship) are all ingested. The remaining judgement inputs are the 5 PARTLY/JUDGED components (dens/env "feel", momentum, air_quality, stewardship, hawker fame). Provision numbers still carry a ±0.3 cross-grader noise bar. Run `make smoke` for the test gate, `make pipeline` to regenerate.
2. **Value is real where HDB resale exists.** It does NOT cover private/landed enclaves (East Coast, Siglap, Holland Village) — those need URA private transaction data (Postal Districts 15/16).
3. **Tengah & Canberra have no resale Value** — Tengah pre-MOP (no market yet), Canberra folded into Sembawang town.
4. **3 of 9 components are irreducibly judgment** (density-feel, environmental comfort, momentum) — they cannot come from a shapefile and are flagged as such in the model.
5. **Report bands, not decimals.** Most established estates cluster within noise; the decimals are not real distinctions.
6. **Re-verify all dated facts** (in the transcript) before any scoring run — MRT dates, polyclinic openings, etc. decay.

## Data file note
`data/value_private.csv` is a stale pre-fix artifact superseded by `data/value_output_private.csv` (the canonical de-circularised private Value output) and is NOT consumed by the pipeline.

## Next step to make it fully data-driven
Upload the **MRT location layer** (coordinates) → lights up Connectivity + Infrastructure (34% of score). Then parks, schools, food layers. Then URA private data for the landed enclaves.
