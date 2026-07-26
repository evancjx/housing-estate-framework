# District 18 Private Project Comparison

> Review achieved non-landed transaction trends across Tampines and Pasir Ris by project, size, and estimated bedroom cohort.

## Purpose

The [District 18 report](../../private_project_comparison_D18.html) compares project-level market evidence while exposing transaction counts and unit-mix differences. The current build covers 37 projects and 6,257 transactions.

## Data & Scope

[`ura_private.csv`](../../data/inputs/ura_private.csv) supplies canonical official URA transactions for 2021–2026. The report supplements only 2019–2020 with incomplete rows from the [`not_clean` EdgeProp scrape](../../data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv). Prices from that source never replace later URA ownership. Rows whose property type contains `House` are removed; Executive Condominium records are not separately excluded where present.

## Comparison Framework

- Keep all transactions and ≤50, 50–70, 70–100, 100–130, and >130 sqm cohorts available separately.
- Add an approximate bedroom label to a project-and-size band only after at least two EdgeProp observations agree on one modal count at a 60% or greater share.
- Show type, tenure, total transactions, annual median PSF, latest-year median PSF, and latest-year median quantum by project.
- Suppress project-year PSF below three transactions.
- Calculate annualised movement from the first to last project year with at least three observations in each.

Annualised movement is the change in achieved project transaction medians; it is not repeat-unit appreciation.

## Controls & Outputs

Use size or estimated-bedroom tabs to make the cohort more comparable. Each tab supplies annual district evidence, top and bottom eligible trend lists, and a sortable project table. Click a column heading to toggle its order; the table supports horizontal scrolling.

## Interpretation Limits

Pre-2021 EdgeProp medians are indicative and `not_clean`. Estimated bedrooms may misclassify unusual units. New sale, sub-sale, and resale are not separated here, and 2026 can be partial. No mix adjustment controls exact unit, floor, view, condition, or project age.

## Rebuild

Run `python3 models/gen_district_private_comparison_html.py --district 18`, then `python3 -m pytest tests/test_gen_district_private_comparison.py`.
