# District-Scoped Private Property Comparison Pages — Design

**Date:** 2026-07-07
**Status:** Approved (pending user spec review)
**First targets:** D17 (Changi/Loyang/Pasir Ris fringe), D27 (Sembawang/Yishun)

## Problem

`private_project_comparison_table.html` covers all 28 postal districts in one 4.6 MB page and
its data basis is the canonical `data/ura_private.csv`, which only reaches back to 2021 (URA's
API serves a rolling ~5-year window). The user wants a *within-district* property comparison,
one page per district, with a **2019–2026** window and an emphasis on **price trends** rather
than the wide amenity/model-context column set of the existing page.

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Page shape | Within-district per-project comparison (not district head-to-head) |
| Time window | 2019–2026, including EdgeProp condo backfill for 2019–2020 |
| Layout | **One HTML page per district** |
| Content | **Trend-focused slim table** — drop schools/model-context columns; centre on per-year PSF, volume, growth |
| Approach | **New standalone generator** (existing generator + its test untouched) |

## Data sources and merge rule

The 2019–2026 dataset is built in-memory per district from three sources. The merge rule is
strict backfill: canonical data owns 2021+, scraped/raw data contributes **2019–2020 rows only**.
This eliminates overlap/dedup risk between sources (EdgeProp rows are URA-sourced and would
double-count the canonical window otherwise).

| Source | Window used | Types | Notes |
|---|---|---|---|
| `data/ura_private.csv` | 2021–2026 (all of it) | all private | canonical; already normalised |
| `data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv` | **2019–2020 only** | Condominium, Apartment | flagged `not_clean`; requires in-memory cleaning; pre-2021 coverage is visibly thin (e.g. D27: 84 txns in 2019 vs 854 in 2021) — this caveat must be surfaced on the page |
| `data/ura_raw/pmi_d{NN}_landed_non_strata_2019-2026.csv` and `pmi_d{NN}_strata_landed_2019-2026.csv` | **2019–2020 only** | landed, strata landed | raw URA PMI downloads; comma-formatted numbers, `Jun-26`-style dates |

### Cleaning rules

EdgeProp (`not_clean`) rows:
- Parse `Date of Sale` (`11 May 2026` format) → sale year; drop unparseable dates.
- Coerce `Unit Price ($psf)`, `Price ($)`, `Area (sqm)` to numeric; drop rows missing price or area, or with non-positive values.
- Dedupe on (project, date of sale, price, area sqft).
- Filter `Postal District` (zero-padded) to the target district; keep sale year in 2019–2020.

`ura_raw` PMI rows:
- Strip commas from numerics (`Transacted Price ($)`, `Area (SQFT)`, `Unit Price ($ PSF)`, `Area (SQM)`).
- Parse `Sale Date` (`Jun-26` = Jun 2026) → sale year; keep sale year in 2019–2020.
- Filter `Postal District` to target.

### Unified schema

Every source normalises to:

```
project, street, property_type, tenure, sale_year, price, area_sqm, psf, sale_type, source
```

`source` ∈ {`ura_private`, `edgeprop_backfill`, `ura_raw_backfill`}.
PSF is taken from the source column where present, else derived `price / (area_sqm × 10.7639)`.

## Grouping

Group by **project name**, with one exception: rows named `LANDED HOUSING DEVELOPMENT`
(URA's placeholder for unnamed landed) group as `LANDED HOUSING DEVELOPMENT (<STREET NAME>)`
so distinct landed streets don't blend into one row.

## Per-project columns (the slim table)

1. Project (grouped name)
2. Property type(s) — mode, or joined list when mixed
3. Tenure — mode
4. Total transactions (2019–2026)
5. Median PSF per year, 2019 → 2026 (8 columns). A year cell renders `—` when that year has
   **n < 3** transactions; the cell tooltip shows the actual n.
6. Growth %: from the **earliest year with n ≥ 3** to the **latest year with n ≥ 3**,
   reported as annualised %: `(psf_last / psf_first) ** (1 / (year_last − year_first)) − 1`.
   Blank when fewer than two qualifying years exist.
7. Latest-year median PSF and median quantum (price).
8. Backfill badge — shown when any of the project's rows came from `edgeprop_backfill`
   (marks the ⚠ thin pre-2021 coverage).

Default sort: total transactions, descending. All columns click-sortable (vanilla JS, same
approach as the existing comparison pages; no external assets — pages must stay self-contained).

## Page structure (per district)

- **Header banner**: district id + name, window (2019–2026), explicit caveat that pre-2021
  condo/apartment rows come from an incomplete EdgeProp scrape and yearly medians for
  2019–2020 are indicative only.
- **District summary strip**: total txns, district-wide median PSF per year (2019–2026),
  top-3 and bottom-3 projects by growth % (among projects with a computable growth figure).
- **Project table** as specified above.

Output files: `private_project_comparison_D17.html`, `private_project_comparison_D27.html`
(repo root, alongside the existing artifact pages).

## Generator

New file: `models/gen_district_private_comparison_html.py`.

```
python3 models/gen_district_private_comparison_html.py --district 17 --district 27
```

- `--district` repeatable (int or zero-padded string); each district produces one output file.
- `--out-dir` optional, default repo root.
- Input paths default to the committed data files; overridable flags mirroring the existing
  generator's style (`--private`, `--edgeprop`, `--ura-raw-dir`).
- Missing `ura_raw` landed file for a requested district: warn and proceed without landed
  backfill (not all districts have one); missing canonical CSV: fail loudly.
- Follows repo conventions: INPUT CONTRACT block in the docstring, stdlib + pandas only.

## Testing

`tests/test_gen_district_private_comparison.py`:
- **Backfill cutoff**: EdgeProp and ura_raw loaders never emit rows with sale_year ≥ 2021.
- **Cleaning**: comma-numerics parsed; bad/missing price/area rows dropped; dedupe works.
- **Landed grouping**: `LANDED HOUSING DEVELOPMENT` rows split by street; named projects intact.
- **Growth rule**: n≥3 qualifying-year selection, annualisation, blank when <2 qualifying years.
- **Smoke/integration**: run the generator for D17 + D27 against committed data; both files
  exist, are non-trivial in size, and contain expected anchor projects (e.g. LOYANG VILLAS
  in D17, THE SHAUGHNESSY in D27).

## Out of scope

- No changes to `gen_private_project_comparison_html.py` or its test.
- No new committed intermediate CSV (merge happens in-memory).
- No MRT/school/model-context columns in the district pages.
- No cleaning pass promoted to `data/` — the `not_clean` EdgeProp files stay as-is on disk.

## Amendment 2026-07-08: landed excluded

Per user direction, landed property types (`*House`) are excluded from the district
comparison pages entirely. `load_canonical` filters them; the `ura_raw` landed backfill
ingestion and the `LANDED HOUSING DEVELOPMENT (street)` grouping were removed from
`gen_district_private_comparison_html.py`. Pages are condo/apartment only.
