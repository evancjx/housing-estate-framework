# Pasir Ris Property Analyses — Design

**Date:** 2026-09-27
**Status:** Approved design; implementation plan pending
**Scope:** the 2026-09-20 regional research batch. This covers `models/build_regional_transaction_batch.py`,
`models/build_individual_project_profiles.py`, the downstream builders and packaging, and the
published archive `data/raw/property_research/2026-09-20.zip`.

## Problem

Seastrand has no dated property analysis. It is not missing by mistake: the 553 individual analyses
come from one regional batch scoped to the Tampines, Bedok, Canberra, Jurong East/West and Bukit
Timah planning areas. The batch's `scope_crosswalk.csv` lists **56 Pasir Ris planning-area
projects**, all `excluded` with the note "Outside the stated main regions". Seastrand is one of
them.

## Goal

Publish a dated analysis for **every Pasir Ris planning-area project** in the crosswalk (56),
Seastrand included, in the same form as the existing analyses. The pages must appear in the
directory under their postal district.

## Decisions (agreed 2026-09-27)

- **Extend the existing 2026-09-20 batch; do not create a new one.** The URA evidence was
  captured on 20 Sep 2026, so the pages carry that date.
- **Author 2–3 primary-source regional facts** for Pasir Ris, matching the other regions.
- **Pasir Ris spans postal districts D17 and D18.** 36 of the 56 projects are in D17, which the
  frozen batch does not contain.

## Non-goals

- Re-exporting URA data. The URA API cannot yet feed the batch, because of the identity mismatch
  recorded in PR #49.
- Changing analyses for projects outside Pasir Ris. If an existing page changes as a side effect,
  it is reported and held for the user's decision (see "Guard").
- Authored editorial notes for Pasir Ris projects. The generated conclusions use the project's own
  evidence, as for the other 498 projects without notes.

## Design

### 0. Working copy

Restore the full batch from `data/raw/property_research/2026-09-20.zip` into
`data/runs/regional-property-analysis/2026-09-20/`, as `docs/individual-property-research.md`
describes. The local folder currently lacks `enrichment/`. Before any change, rebuild once and
confirm the rebuild reproduces the committed Markdown and archive contents. This baseline is what
the guard compares against.

### 1. Scope

**Append** 56 rows to the batch's existing `scope_overrides.csv`, one per crosswalk project whose
`source_planning_area` is Pasir Ris:

- `region = "Pasir Ris"`;
- `subregion = "Pasir Ris recorded planning area"`;
- `scope_status = "main"`;
- `scope_basis = "Pasir Ris planning area added 2026-09-27"`.

Every other column is copied from the crosswalk row. `scope_crosswalk.csv` itself is not edited.

### 2. D17 transactions

Add the D17 exports to the batch's frozen `raw/ura/`, each with a **month window**, so that no sale
month is taken from two files:

| File | Months used | Capture |
| --- | --- | --- |
| `pmi_d17_2021-2026.csv` | 2021-06 → 2024-12 | earlier capture (repository commit `ad719b4`) |
| `pmi_d17_2025-2026.csv` | 2025-01 → 2026-09 | 2026-09-20 (PR #39) |

- `build_regional_transaction_batch.py` gains an optional month window per expected file. Rows
  outside the window are dropped before any other processing. Each kept row retains its source
  file and row number.
- The batch's "never merge overlapping exports" rule still holds, because windows do not overlap.
- `provenance.json` records each file's window, SHA-256, and the fact that pre-2025 D17 rows come
  from the earlier capture.
- If an EC export for D17 exists, it is handled the same way. Otherwise no D17 EC file is expected.

### 3. Regional facts

Add a `Pasir Ris` region entry to `enrichment/regional_context.json`, with its sources in the shared
`sources` register. Also add `REGIONAL_FACTS["Pasir Ris"] = ["PR-01", "PR-02", "PR-03"]`, and
`OWN_PROJECT_FACTS["PASIR RIS 8"] = "PR-02"`, in `build_individual_project_profiles.py`. All facts
were retrieved and checked on 2026-09-27.

- **PR-01, Cross Island Line (status: planned).**
  - Claim: "CRL1 is expected to be completed by 2030", and Pasir Ris is its interchange with the
    East-West Line. Pasir Ris East station is on Pasir Ris Drive 1, with passenger service expected
    in 2030. The CRL Punggol Extension is to be completed by 2032.
  - Sources:
    - LTA, Cross Island Line: https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/cross_island_line.html
    - LTA news release, 7 Feb 2022: https://www.lta.gov.sg/content/ltagov/en/newsroom/2022/2/news-releases/LTA_awards_civil_contract_for_design_and_construction.html
    - URA Master Plan 2025, East, "Transforming Towns for Tomorrow": https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/east/transforming-towns-for-tomorrow/
- **PR-02, Pasir Ris Integrated Transport Hub (status: completed).**
  - Claim: the new Pasir Ris Bus Interchange opened on 27 April 2025 within an integrated
    development with Pasir Ris Mall, adjacent to Pasir Ris MRT station (EWL). The development
    includes residences, a polyclinic, childcare facilities and a town plaza, and connects to the
    EWL and the upcoming CRL interchange.
  - Sources:
    - LTA news release, 3 Apr 2025: https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/4/news-releases/two-new-bus-interchanges-to-open-in-april-2025.html
    - URA Master Plan 2025, East.
- **PR-03, Sungei Loyang neighbourhood (status: under study).**
  - Claim: "Plans are being studied for a new neighbourhood near Sungei Loyang."
  - Source: URA Master Plan 2025, East.
  - Shown as a supply watch item, never as committed supply.

### 4. Rebuild, guard and publish

1. Run the four builders in order: `build_regional_transaction_batch`,
   `build_regional_property_evidence`, `build_individual_project_profiles`,
   `build_individual_property_analyses`. Then run `scripts/package_property_research.py`.
2. **Guard:** compare every pre-existing generated page and every archive member against the
   baseline from step 0.
   - Any page outside Pasir Ris whose content changes is listed with its diff.
   - That list goes to the user **before** anything is committed.
   - Nothing is published until the user approves or rejects each change.
3. The new pages keep the 20 Sep capture date and the existing naming:
   `property_analysis/2026-09-20-<slug>.md`, and in the site output
   `property-analysis-2026-09-20-<slug>.html`.
4. The regional comparison page and the "Individual property analyses" index gain Pasir Ris,
   because they list every project in scope.
5. The Pages directory lists the new analyses automatically under D17 and D18, since it takes
   districts from the finder index.

## Error handling

- **A Pasir Ris project with no transactions** after windowing gets the existing "sparse or
  no-transaction evidence-limit" treatment. It is never dropped silently.
- **A D17 export missing, or a window producing overlapping months:** the batch build fails with a
  clear message.
- **A crosswalk project whose name collides** with an existing override is reported, and the build
  fails. It is never overwritten silently.

## Testing

- Unit tests for the month-window loader:
  - rows outside the window are excluded;
  - two windows covering the same month raise an error;
  - kept rows keep their source file and row number.
- After the rebuild:
  - Seastrand's analysis exists, and its transaction count equals the batch's Seastrand rows from
    D18 (108 raw rows before exclusions);
  - all 56 Pasir Ris projects have exactly one analysis;
  - no Pasir Ris project analysis is empty unless it has no transactions.
- Existing research and pages tests, and `make smoke`, pass. The site build lists the new analyses.

## Risks

- **Pre-2025 D17 rows come from an earlier capture**, so any URA revisions to those rows since then
  are missing. This is recorded in the provenance and in each affected page's evidence register.
- **Adding 56 projects can shift cross-regional peer matches** for existing projects. The guard
  catches this, and the user decides.
- **The published archive** `2026-09-20.zip` changes. Its old version stays recoverable from Git
  history.
