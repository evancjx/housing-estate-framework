# Task M3 Report — 20-Component Provision Model

**Status:** DONE

**Commit:** pending (scoped add + commit below)

**Test summary:** 42 passed, 1 deselected, 0 failed (`python3 -m pytest -q`)

**3 new columns present?** YES — `jtc_industrial`, `air_quality`, `stewardship` in provision_scores.csv for all 35 estates. Jurong West + Holland Village show NaN for stewardship (no TC mapping in kpi.json) — correct renormalisation behaviour.

**Provision band shifts (3 estates vs HEAD):**
- MARINE PARADE: D → C (new components favour it; jtc=4, air=3, stewardship=5)
- LENTOR: C → B (weight rebalance lifts it; was borderline)
- HOLLAND VILLAGE: B+ → B (infra weight cut 15→14, amen down, new components NaN-penalise slightly via renormalisation)

**Concerns:** None blocking. Holland Village and Jurong West lack TC mappings in town_council_kpi.json — stewardship scores NaN for both and renormalise correctly. Add TC entries when TCMR data is sourced. Marine Parade D→C shift is plausible (low JTC exposure, decent air quality). Lentor C→B is consistent with its measured components improving relative to the new weight structure.

**Report path:** `/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework/.superpowers/sdd/task-M3-report.md`
