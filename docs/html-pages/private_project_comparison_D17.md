# District 17 Private Project Comparison

> Review achieved non-landed transaction trends across Changi, Loyang, and Pasir Ris by project, size, and estimated bedroom cohort.

## Purpose

The [District 17 report](../../private_project_comparison_D17.html) compares project-level market evidence without treating unlike unit mixes as one investment ranking. The current build covers 35 projects and 2,573 transactions.

## Data & Scope

[`ura_private.csv`](../../data/inputs/ura_private.csv) is the canonical official URA source for 2021–2026. Only 2019–2020 rows are backfilled from [`edgeprop_condo_apartment_transactions_playwright_not_clean.csv`](../../data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv); this rendered EdgeProp evidence is incomplete and marked `not_clean`. Rows whose property type contains `House` are excluded. The loader does not separately exclude Executive Condominium records where present.

## Comparison Framework

- Compare all transactions and area bands of ≤50, 50–70, 70–100, 100–130, and >130 sqm.
- Estimate a project-and-size-band bedroom label only with at least two EdgeProp observations and a modal bedroom share of at least 60%; classify unlabelled transactions as Unknown.
- Display each project’s type, tenure, transaction count, annual median PSF, latest-year median PSF, and latest-year median quantum.
- Withhold a project-year PSF cell below three transactions.
- Annualise the change between the first and last years whose project samples each contain at least three transactions.

That growth field describes project transaction medians, not repeat-unit appreciation.

## Controls & Outputs

Switch between all, size, and estimated-bedroom tabs. Summary cards show district annual medians plus the top and bottom eligible project trends. Click any project-table heading to sort; wide tables scroll horizontally.

## Interpretation Limits

The 2019–2020 EdgeProp backfill is indicative only. Estimated bedroom labels can misclassify atypical layouts, and 2026 is a year-to-date mix rather than a completed year. Medians do not adjust for sale state, size, floor, facing, condition, or exact unit.

## Rebuild

Run `python3 models/gen_district_private_comparison_html.py --district 17`, then `python3 -m pytest tests/test_gen_district_private_comparison.py`.
