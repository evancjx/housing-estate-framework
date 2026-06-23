# SG Estate Framework — Remediation & Build Roadmap

> **Index document.** This is the phased master plan. Each phase has its own
> detailed, executable plan doc (TDD, bite-sized). Phase 0+1 is fully detailed in
> `2026-06-21-phase0-1-test-harness-and-correctness.md`. Phases 2–5 are scoped to
> the task level here and will be expanded into their own detailed plans when reached
> (deliberately not over-planned — later phases depend on earlier outcomes and on
> data that will shift once ingest lands).

**Source of findings:** the 2026-06-21 multi-agent review (35 agents, adversarially verified).

**Sequencing principle:** correctness before surfacing before coverage before methodology before product.
You cannot build a comparison view on numbers that are wrong (Phase 1) or on a join that doesn't exist (Phase 2).

**Repo:** `SG-Estate-Framework/` (the git repo). All paths below are relative to it unless absolute.

**Global constraints (apply to every task):**
- Python 3, `pandas`/`numpy`/`statsmodels`/`shapely`, install with `--break-system-packages` (Termux/Android-friendly, per existing docstrings).
- **Never blend HDB and private** into one price/value distribution (invariant 2).
- **Never rank raw Provision across archetype tags** (invariant 3).
- **Provenance never faked:** MEASURED / PARTLY_MEASURED / JUDGED; missing JUDGED inputs are flagged, never imputed silently.
- **Bands not decimals below n<100 / inside the noise floor.**
- When a number changes in code, update the matching framework `.md` and both `CLAUDE.md` files (docs are the spec).
- No silent error swallowing; no force-unwraps; flag any new race/threading/security issue.

---

## Phase 0 — Safety net (test harness) — DETAILED in companion doc

There is currently **no test suite**. Build one before touching correctness code.

| Task | Files | Deliverable | Depends on |
|---|---|---|---|
| 0.1 pytest scaffold + fixtures | `tests/conftest.py`, `pytest.ini`, `requirements-dev.txt` | `pytest` runs; tiny synthetic HDB/scores fixtures + path to committed real data | — |
| 0.2 End-to-end smoke test | `tests/test_pipeline_smoke.py` | provision→liveability→value runs on committed data without error; output schemas asserted | 0.1 |
| 0.3 Invariant tests (always-true properties) | `tests/test_invariants.py` | weights sum to 1; no NaN provision; segments never share a regression; band edges monotonic | 0.1 |
| 0.4 Snapshot/diff helper | `tests/snapshot.py`, `tests/test_characterization.py` | captures CURRENT outputs so every Phase-1 fix's effect is a visible, reviewed diff (NOT a frozen golden-master) | 0.1 |

---

## Phase 1 — Correctness fixes (today's numbers are wrong without these) — DETAILED in companion doc

| Task | Files | Fix | Severity |
|---|---|---|---|
| 1.1 Value circularity | `models/value_model.py:147` (+ remove shadow rows 113-122) | Drop provision `_score` from regression RHS; provision enters once, as the multiplier base | 🔴 critical |
| 1.2 Alias loop dedup + segment guard | `models/value_model.py:166-207` | No triple-count when target is a real estate; never give a private-dominant estate an HDB residual — flag instead | 🔴 critical |
| 1.3 Zero-area filter | `models/value_model.py:106-108` | Filter on finite positive area before `ln(psm)`; print dropped-row count | 🟡 medium |
| 1.4 BASE_W ↔ W reconcile | `models/liveability_model.py:124-140` | Add `hawker`+`noise`, fix 5 mismatched weights, OR compute Gap on same component set; add `set(BASE_W)==set(W)` assert | 🟠 high |
| 1.5 Gap on raw scores | `models/liveability_model.py:745-751` | Compute Gap from continuous scores, not the non-uniform BAND_NUMERIC ladder; bucket with ≥0.5 dead-band | 🟠 high |
| 1.6 Veto pre-D | `models/liveability_model.py:573-580` | Apply structural veto cap to the pre-D score | 🟠 medium |
| 1.7 X-archetype N/R gate | `models/liveability_model.py:run()`, `models/value_model.py:main()` | Read `archetype_assignments.csv`; X estates emit N/R, never a scored matrix | 🟠 high |
| 1.8 Momentum no-silent-zero | `models/momentum_model.py:73-78` | `.upper()` significance/certainty before lookup; warn on fallthrough/missing year | 🟡 low |
| 1.9 Momentum manual-addition reconcile | `models/momentum_model.py:90-102` | MARINE PARADE +0.255 contradicts the model's own `time_factor(2026)=0` rule — decide & fix in `pipeline_data.json`, not a hardcode | 🟡 low |
| 1.10 Doc-code drift | `models/provision_model.py:9,414`, both `CLAUDE.md`, `frameworks/1-provision-framework.md:45-58`, `liveability_model.py:14` | Single-source the 17-component count; document `W_PRIVATE`; regenerate the framework weight table from `W` | 🟡 medium |

---

## Phase 2 — Wiring (surface what is already built but thrown away)

Three working models (employment, lease, private value) and the entire private segment never reach `master_output.csv`. Pure plumbing — highest leverage per hour.

| Task | Files | Deliverable | Depends on |
|---|---|---|---|
| 2.1a Shared pipeline-name alias | `models/aliases.py` (new), `models/momentum_model.py`, `models/liveability_model.py` | ONE `PIPELINE_NAME_ALIAS` dict imported by momentum+liveability; resolve BOON LAY / TAMAN JURONG / BUONA VISTA conflicts; assert the two callers agree | 1.x |
| 2.1b Shared estate→town alias | `models/aliases.py`, `models/value_model.py`, `models/lease_risk_model.py` | ONE `ESTATE_TOWN_ALIAS` dict imported by value+lease; reconcile LENTOR handling; assert callers agree | 1.2 |
| 2.1c Alias-sync test | `tests/test_aliases.py` | Test asserts both maps are single-sourced and no model defines its own copy | 2.1a, 2.1b |
| 2.2 `build_master.py` joiner | `models/build_master.py` (new), `tests/test_build_master.py` | Left-join provision + liveability + value(hdb) + value(private) + employment + lease + archetype on canonical estate; per-cell provenance flag; **no empty columns**; X estates → N/R; fail loudly if a source CSV is missing | 1.7, 2.1 |
| 2.3 Wire into pipeline + regenerate | `SG-Estate-Framework/CLAUDE.md`, `data/master_output.csv` | Add `build_master.py` as the pipeline tail; regenerate; diff against the hand-assembled file; document the diff | 2.2 |
| 2.4 Private-value surfacing | `models/build_master.py`, `data/value_output_private.csv` | Run `value_model --private`; the 16 private-resale estates appear as a **separate** `value_private_*` block (segment label retained) | 2.2, 1.1, 1.2 |
| 2.5 README correction | `README.md`, root `CLAUDE.md` | Remove the stale "Value does NOT cover private/landed" claim; show HDB + private side-by-side (separate) | 2.4 |
| 2.6 Regenerate momentum chain + fix provision command | `data/judged_inputs.csv`, `data/provision_scores.csv` (+ derived), `SG-Estate-Framework/CLAUDE.md` | **Deferred from Phase 1 (1.9):** momentum model now omits the Marine Parade TEL5 hardcode but committed CSVs predate it (band-immaterial: provision 2.90→2.86, stays D). Re-run momentum→provision→liveability→value to refresh, AND fix the CLAUDE.md provision command which omits `--eldercare`/`--air_noise` (so it doesn't reproduce the committed provision_scores.csv). | — |

> **Phase 1 deferred doc-hygiene** (none block anything; do alongside 2.x): stale docstrings — `value_model.py` section comment `~ score + controls`, `liveability_model.py` `score_estate` `×D / Then capped` order and the S-group mapping base values (post-BASE_W reconcile), `liveability_model.py:30` `S7 mom base 0.05`→0.04; add 3 missing estates (HOLLAND VILLAGE, JURONG WEST, KALLANG) to `archetype_assignments.csv` + an `estates ⊆ archetypes` guard test; `value_band="N/A"` reads back as NaN so `build_master` must key off `value_basis`. The outer (non-repo) `../CLAUDE.md` still says "9 components" — user updates manually.

---

## Phase 3 — Coverage (toward "all districts, all property types")

The user's literal ask. Each segment is added as a **separate, non-blended** Value universe.

| Task | Files | Deliverable | Depends on |
|---|---|---|---|
| 3.1 Backfill `postal_district` | `scrapers/ingest_ura_raw.py`, `data/ura_private.csv` | 19,217 blank-district rows get district from project/street→postcode→district; ingest always populates BOTH `postal_district` and `planning_area` | 2.x |
| 3.2 Retain CCR/RCR/OCR | `scrapers/ingest_ura_raw.py` | Keep URA `Market Segment` column (or derive from district map); enables the market-tier view | 3.1 |
| 3.3 Landed segment | `scrapers/run_download.py:58` (prop_type 1/2), `models/value_model.py:SEGMENTS` | Ingest landed caveats; add a `landed_resale` segment (own regression, never blended) | 3.1 |
| 3.4 EC segment | `models/value_model.py:SEGMENTS`, ingest | Split the 362 EC rows out of `private_resale` into an `ec_resale` segment (thin → band-only) | 1.2 |
| 3.5 New-sale vs resale split | `models/value_model.py` | Separate `private_newsale` from `private_resale` (developer pricing ≠ resale) | 3.1 |
| 3.6 CCR district ingest | `scrapers/`, `data/` | Pull D1,2,6,7,9,10,11 private caveats — the priciest market, currently absent | 3.1 |
| 3.7 Rental segments | `scrapers/`, `data/`, `models/value_model.py` | Ingest URA private rental + HDB rental; wire the existing dead `--rental` flag; add an HDB-rental segment | — |
| 3.8 BTO/SBF primary market | `models/data_ingest.py`, `models/value_model.py` | Ingest HDB launch prices so pre-MOP new towns (Tengah, Lentor) get a primary-market Value instead of blank | — |
| 3.9 Canonical geographic unit | `data/estates.csv`, `models/build_master.py` | Define ONE unit + documented hierarchy; stop parent town and its sub-areas appearing as ranking peers; de-dup shared transaction pools (Tampines ×3) | 2.2, 3.1 |
| 3.10 Wire eldercare + air_noise layers | provision run, `data/provision_scores.csv` (+ derived) | **Discovered in Phase 2:** the committed provision run OMITS `--eldercare`/`--air_noise`, so both components sit at floor defaults (1.0/5.0) for every estate — dead weight. Wire `data/eldercare.csv` + `data/air_noise_corridors.csv` into the canonical run; regenerate; review band shifts (e.g. WOODLANDS C→B, PUNGGOL B→C, LENTOR air_noise→1 near Seletar) as a deliberate, reviewed change. | 2.x |
| 3.11 Refresh pipeline_data.json (NRP/LUP) | `data/pipeline_data.json` (+ momentum→provision→… cascade) | **Discovered in Phase 2.6:** `ingest_hdb_upgrading.py` (network-fed) now shares the corrected alias map, but the committed `pipeline_data.json` NRP/LUP items still carry legacy attribution (some Jurong West/Kallang precincts credited to Jurong East/Boon Keng). Run the ingester (needs data.gov.sg) → re-run momentum→provision→liveability→value→master; review the bounded Jurong-East/West + Kallang/Boon-Keng momentum shift. | 2.6 |

---

## Phase 4 — Methodology hardening

| Task | Files | Deliverable | Depends on |
|---|---|---|---|
| 4.1 Smooth distance anchors | `models/provision_model.py:156-196` | Piecewise-linear/exponential interpolation between anchor breakpoints (the docstring already claims "smooth decay"); re-measure how much "saturation" survives | 0.x |
| 4.2 Confidence intervals | `models/value_model.py`, `models/provision_model.py` | Residual SE → Value CI; bootstrap provision anchors + JUDGED ±1 → per-estate score sd; **gate ranking on CI non-overlap**, retiring the hard-coded ±0.3 | 4.1 |
| 4.3 Weight calibration (diagnostic) | `models/calibrate_weights.py` (new) | Hedonic regression of price-residual on component scores → market-implied weights, shown **side-by-side** with judged weights, never auto-adopted; audit divergence vs Axiom 2 | 1.1 |
| 4.4 Missing-component envelope | `models/provision_model.py:315-319` | When a JUDGED input is missing, report worst/best envelope (component at 1 vs 5), not a silent present-weighted mean | 0.x |
| 4.5 Continuous lease control | `scrapers/`, `models/value_model.py` | Parse private `Tenure` free-text → `remaining_lease_years` (continuous) + `is_freehold` (binary); replace the 85-level `C(tenure)` dummy that absorbs decay | 3.1 |

---

## Phase 5 — New comparison views / products

The legitimate cross-everything surface (design from the review, after the adversarial cut).

| Task | Files | Deliverable | Depends on |
|---|---|---|---|
| 5.1 Faceted comparison view | `views/compare.html` (replaces `comparison_table.html`) | Single-`W` provision dot-plot (±0.3 band, archetype as non-orderable colour) + **faceted** value-percentile small-multiples (one panel per segment); rank only within facet beyond ±0.3; segment label on every chip | 2.2, 4.2 |
| 5.2 Within-segment leaderboards | `views/`, `models/build_master.py` | Separate HDB / private Value leaderboards, n-gated, never one merged column | 2.4 |
| 5.3 Gap dashboard | `views/gap.html` | Provision×Liveability quadrant on **raw** scores, 3-bucket dead-band ("punches above" / "matched" / "over-equipped") | 1.5 |
| 5.4 Choropleth | `views/map.html`, URA planning-area GeoJSON | Provision / Value / gap layers; MRT nodes; provenance encoded as opacity; per-MRT-node comparison | 2.2 |
| 5.5 Affordability calculator | `views/`, `models/` | Budget + eligibility (dated) filters the **accessible** set, then ranks by provision or within-segment value-percentile; Value-side, never Provision | 2.4, 3.7 |
| 5.6 Price-momentum sub-view | `models/`, `views/` | Rolling 12-month subzone residual slope (realised) shown next to S7 (announced); Value-side, within-segment | 3.1 |
| 5.7 Climate-risk 2050 layer | `models/`, `data/` | PUB/CCRS sea-level + heat as a **T15 D-drag** for coastal estates (a projected loss, never a provision bonus); PARTLY_MEASURED | 1.x |
| 5.8 Read-only API substrate (optional) | `api/` | Static JSON or thin FastAPI over the master table; defer until ≥2 views exist | 5.1+ |

---

## Cross-phase forbidden list (enforce in code, not just docs)

These must remain impossible no matter which view ships:
1. A single cross-segment dollar/value league table.
2. Ranking raw Provision across archetypes (only component-by-component, or profile-with-noise-band).
3. Any average-over-personas "overall liveability" / "best overall".
4. Scoring the X-archetype as residential.
5. Re-importing rejected factors (social-mix, income, address-prestige, tenure-mix) through a "unified" surface.
6. Raw $/provision-point across segments (only the within-segment efficiency percentile may cross).
7. Treating a rental value-percentile as fungible with a resale one (segment label always on the row).

---

## Dated facts to re-verify before any scoring run (decay fast)
MRT opening dates (CCL6 12 Jul 2026, JRL ~2028, CRL phases), polyclinic openings (Serangoon Nov 2025, Bidadari 2027, Bishan ~2030), BTO Standard/Plus/Prime (Oct 2024), HDB/EC eligibility ceilings.
