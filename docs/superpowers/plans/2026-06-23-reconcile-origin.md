# Reconcile origin/main (0f8b885) with local Phase 1+2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Integrate origin's parallel "centralize config + refresh outputs" refactor with my Phase 1+2 work, taking **origin's structure/presentation/data-completeness + ALL my correctness fixes**, then regenerate every output from the reconciled code.

**Decisions (locked by the user):**
- **Config:** adopt origin's `framework_config.py` as the home for non-alias constants (weights, provenance, S_GROUPS, persona deltas, band edges, `band_label`, `build_persona_weights`, `validate`). **Keep `aliases.py` as the single home for the two alias maps + `PRIVATE_DOMINANT_PROXIES`** (do NOT use framework_config's alias dicts — they're the old broken maps).
- **Data scope = FULL:** wire `--eldercare` + `--air_noise` into the canonical provision run (origin did; mine had floor defaults — this is Phase 3.10), and surface **real private Value** regenerated through my fixed value_model (not origin's buggy output).

**Base:** my `main` (HEAD), which has the tested correctness. We PORT origin's structure/features onto it — safer than starting from origin and re-applying 13 fixes.

## Global Constraints
- `python3`. Run from repo root `SG-Estate-Framework/`. Branch `reconcile-origin`.
- **Preserve every Phase-1/2 correctness fix** (VM-1 no `_score` on RHS; F1 `value_basis`/`no_hdb_segment`/`PRIVATE_DOMINANT_PROXIES`; F8 `clean_psm`; raw-score Gap + `gap_label` — NOT `BAND_NUMERIC`; veto cap pre-D; X-archetype N/R gate; momentum uppercase+warn + Marine-Parade-removed; dynamic `compute_d_multipliers`+`--year`; `W_PRIVATE`/`provision_private`/`score_private`; resolved aliases).
- **Never blend HDB/private.** Private Value routed through the `no_hdb_segment` guard; X-gate applies to all master cells.
- **No CSV hand-merged** — regenerate every output from reconciled code; outputs must reproduce byte-identical on a second run.
- Read origin's versions via `git show origin/main:<path>`. Do NOT touch the user's uncommitted WIP that isn't part of a task.
- Commit footer: Co-Authored-By + Claude-Session lines.

---

## Task R.1 — Adopt framework_config.py for constants (output-neutral structural refactor)

**Files:** add `models/framework_config.py`; modify `models/provision_model.py`, `models/liveability_model.py`, `models/value_model.py`, `models/momentum_model.py`; add `tests/test_framework_config.py`.

**Contract:** Port origin's `framework_config.py` (`git show origin/main:models/framework_config.py`) but **remove its `HDB_TOWN_ALIAS` and `PIPELINE_ESTATE_ALIAS` dicts** (aliases stay in `aliases.py`), and **add `PROVISION_WEIGHTS_PRIVATE`** (= my `provision_model.W_PRIVATE`, with a sum-to-1 assert). Then repoint:
- `provision_model.py`: import `PROVISION_WEIGHTS as W`, `PROVISION_WEIGHTS_PRIVATE as W_PRIVATE`, `PROVENANCE`, `band_label` from framework_config (keep W/W_PRIVATE/PROVENANCE names as module attrs so existing references + `tests/test_doc_consistency.py`/`test_invariants.py` still pass). Keep all scoring logic.
- `liveability_model.py`: import `PROVISION_WEIGHTS as` the base for `BASE_W`, `S_GROUPS`, `PERSONA_DELTAS`, `band_label`, `build_persona_weights`, `validate_framework_config`, `BAND_EDGES`, `SOFT_FLOOR` from framework_config. **KEEP my fixes intact**: the raw-score Gap + `gap_label`/`GAP_DEAD_BAND`/N-R block (do NOT switch to `BAND_NUMERIC`), pre-D veto order, X-archetype gate, dynamic `compute_d_multipliers`+`--year`. Use origin's floored `build_persona_weights` (identical output for current non-negative deltas).
- `value_model.py`, `momentum_model.py`: optionally adopt `band_label`/`BAND_EDGES` from framework_config; keep importing aliases from `aliases.py`; keep all fixed bodies.
- `aliases.py`: unchanged (still the alias home). `tests/test_aliases.py` is-identity guards unchanged.

**Gate:** This must be **output-neutral**. After repointing, regenerate `provision_scores.csv` (current no-eldercare/air_noise command), `liveability_matrix.csv`, `value_output.csv` and confirm **byte-identical** to the committed versions. Full suite passes. Add `tests/test_framework_config.py` asserting `validate_framework_config()` passes, `PROVISION_WEIGHTS == provision_model.W`, `set(S_GROUPS components) == set(W)`, and `sum(PROVISION_WEIGHTS_PRIVATE)==1`.

- [ ] Steps: write the framework_config test (RED) → port framework_config.py (no alias dicts, + PRIVATE weights) → repoint the 4 models preserving fixes → GREEN + full suite → regenerate the 3 CSVs, confirm byte-identical → commit (`refactor(config): adopt framework_config.py for constants; keep aliases.py + all Phase-1/2 fixes`). If any CSV is NOT byte-identical, STOP/BLOCKED with the diff (a non-neutral change means a fix or constant drifted).

---

## Task R.2 — Wire eldercare + air_noise into the canonical provision run (Phase 3.10)

**Files:** modify `SG-Estate-Framework/CLAUDE.md` (provision command), `data/provision_scores.csv` + `data/liveability_matrix.csv` + `data/value_output.csv` (regenerate).

**Contract:** Add `--eldercare data/eldercare.csv --air_noise data/air_noise_corridors.csv` to the canonical provision command (CLAUDE.md + the documented pipeline). Regenerate provision → liveability (`--archetypes`) → value (`--hdb`). This is a **deliberate band-shifting change** (eldercare/air_noise move from floor defaults to real values).

**Gate:** Review the diff. Expected: eldercare goes from all-1.0 to real values (1.5–5.0), air_noise from all-5.0 to real (1.0–5.0); provision/value/liveability shift on affected estates (e.g. WOODLANDS, PUNGGOL, LENTOR). Confirm the shifts are sensible (cite a few). The committed `provision_scores.csv` now matches origin's eldercare/air_noise columns (compare to `git show origin/main:data/provision_scores.csv` eldercare/air_noise columns — they should agree, since same layers). Report the band changes. Commit (`data: wire eldercare+air_noise into provision (Phase 3.10); regenerate`).

---

## Task R.3 — Regenerate real private Value through the fixed value_model

**Files:** add `data/value_private.csv` (or `value_output_private.csv`); modify nothing in models (value_model already supports `--private`).

**Contract:** Run my fixed `value_model.py --private <URA private csv> --scores data/provision_scores.csv` against the committed URA private inputs (`data/ura_private_d15_d16.csv`, `data/ura_private_d5_d21_d27.csv` — confirm their schema matches value_model's `private_resale` SEGMENT contract: planning_area, transacted_price, area_sqm, property_type, tenure, project_age_years, sale_month; if the columns differ, write a tiny adapter or report the schema gap). Output carries the F1 guard + `value_basis`. This produces CORRECT private Value (vs origin's circular-regression output).

**Gate:** Private Value rows have `value_basis` tags, no private-dominant estate borrows an HDB residual, `n`/bands present. Spot-check a couple (e.g. BEDOK private_resale). Commit (`data: regenerate private Value via fixed value_model (no-circularity + no_hdb_segment guard)`).

---

## Task R.4 — Graft origin's master richness onto build_master.py

**Files:** modify `models/build_master.py`; add `data/life_paths.csv` + regenerate `data/master_output.csv`. Read origin's `git show origin/main:models/build_master_output.py` to port the features.

**Contract:** Keep my `build_master.py` correctness skeleton (X-gate, coverage flags, `keep_default_na=False`, fail-loud, 35-estate liveability spine). GRAFT from origin: (a) `build_life_paths()` → emit `life_paths.csv` + best/worst-lifepath columns; (b) per-persona liveability Value joins (`value_live_yf/sp/ret/ls` — regenerate via `value_model --liveability --persona` if needed, or join origin's if compatible — prefer regenerating through the fixed model); (c) real private Value columns from R.3 (replace the `not_covered` stub, keep `value_basis`); (d) employment T0/T5/T15 (`employment_scores_T5/T15.csv` or `employment_trajectory.csv`); (e) origin's human-readable `notes` column. **Apply the X-archetype N/R gate AFTER all new joins** so Central Area's lifepath/private/persona-value cells are also N/R. Source `DATA_DIR` from framework_config.

**Gate:** master_output has the new columns populated; CENTRAL AREA is N/R across ALL scored cells (incl. new ones); no blank cells; private columns carry `value_basis`; `tests/test_build_master.py` still passes (extend it for the new X-gate cells + life_paths). Commit.

---

## Task R.5 — Tooling + docs

**Files:** add `Makefile`; add `tests/test_pipeline_regen.py`; merge `SG-Estate-Framework/CLAUDE.md` + `README.md`.

**Contract:**
- Add a `Makefile` (`make smoke` → `python3 -m pytest`; `make master` → run the pipeline + `build_master.py`). Port origin's targets but point `smoke` at pytest.
- Fold origin's `smoke_test.py` regen-byte-identical check into a new `tests/test_pipeline_regen.py` (marked `@pytest.mark.integration`): regenerate provision/liveability/value to a temp dir and `assert_frame_equal` vs committed. Drop standalone `smoke_test.py`.
- Docs: ADOPT from origin — fresher README ingestion status (real geospatial layers ingested; point to CLAUDE.md), the framework_config architecture section. KEEP from local — aliases.py single-sourcing, pipeline_data.json legacy-attribution disclosure, Phase-2/3 deferrals. Rewrite the "config home" section to describe the ACTUAL final layout (framework_config for constants + aliases.py for aliases).

**Gate:** `make smoke` runs the full suite green (incl. the new regen test). Commit.

---

## Task R.6 — Record the integration

**Contract:** After R.1–R.5 are merged to `reconcile-origin` and all gates pass, record origin/main as integrated so future fetches don't re-surface it: `git merge -s ours origin/main -m "merge: integrate origin/main 0f8b885 (config centralization + features) — superseded by reconcile-origin which keeps it + all Phase-1/2 correctness fixes"`. (The `-s ours` keeps our reconciled tree but makes origin/main an ancestor.) Then the final whole-branch review + finishing-a-development-branch (merge to main; pushing is a separate user decision).

**Gate:** `git log --graph` shows origin/main merged; `git diff origin/main..HEAD` is the reconciled superset; tree clean; full suite green.

---

## Self-Review
- Coverage: config (R.1), correctness preserved (R.1 gate = byte-identical), eldercare/air_noise (R.2), private Value (R.3), master richness (R.4), tooling/docs (R.5), integration (R.6).
- Risk order: output-neutral first (R.1), then data-shifting (R.2/R.3), then additive (R.4/R.5), then integration (R.6). Each gated by the test suite; R.1 additionally by byte-identical regeneration.
- The one place to watch: R.1 MUST be byte-identical (proves no fix/constant drifted when adopting framework_config). R.2 onward intentionally change data.
