# District 27 Private Project Comparison

> Review achieved non-landed transaction trends across Yishun and Sembawang by project, size, and estimated bedroom cohort.

## Purpose

The [District 27 report](../../private_project_comparison_D27.html) exposes sample-backed project trends for a district that includes established condominiums and Executive Condominium stock. The current build covers 29 projects and 3,435 transactions.

## Data & Scope

Canonical 2021–2026 transactions come from official [`ura_private.csv`](../../data/inputs/ura_private.csv). Incomplete 2019–2020 evidence is added only from the rendered [`not_clean` EdgeProp scrape](../../data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv) and is visibly badged. The loader excludes property types containing `House`; it retains Executive Condominium records where present despite the page’s abbreviated condo/apartment label.

## Comparison Framework

- Compare all transactions, then ≤50, 50–70, 70–100, 100–130, and >130 sqm bands.
- Infer an approximate project-and-size-band bedroom label only from at least two EdgeProp observations whose modal bedroom count reaches a 60% share.
- Report type, tenure, count, annual median PSF, latest-year median PSF, and latest-year median quantum.
- Withhold project-year PSF when `n < 3`.
- Annualise movement from the first to last available project year where both endpoint samples contain at least three transactions.

The result measures movement in project-level achieved-sale medians and must not be described as repeat-unit appreciation.

## Controls & Outputs

Tabs select all records, size cohorts, or estimated 1BR–5BR+/Unknown cohorts. Summary cards preserve annual sample counts and list the highest and lowest eligible movements. Project-table columns are sortable and horizontally scrollable.

## Interpretation Limits

EdgeProp backfill coverage before 2021 is incomplete and `not_clean`; a badge does not make it equivalent to canonical URA coverage. Bedroom classes are estimates that can misclassify unusual layouts. Sale state and physical-unit attributes are not controlled, while 2026 may be year-to-date.

## Rebuild

Run `python3 models/gen_district_private_comparison_html.py --district 27`, then `python3 -m pytest tests/test_gen_district_private_comparison.py`.
