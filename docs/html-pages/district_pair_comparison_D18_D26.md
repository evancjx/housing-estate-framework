# District 18 Versus District 26 Comparison

> Compare Pasir Ris/Tampines with Lentor/Upper Thomson across like-for-like bedroom, size, and operational-MRT-distance cohorts.

## Purpose

The [static district-pair report](../../district_pair_comparison_D18_D26.html) tests whether headline district differences persist inside observable unit and access cohorts. Its current build covers 9,557 D18 transactions across 46 projects and 3,695 D26 transactions across 20 projects, from 2019–2026.

## Data & Scope

Transaction rows come solely from [`edgeprop_condo_apartment_transactions_playwright_not_clean.csv`](../../data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv). EdgeProp’s public table labels the records as URA-sourced, but this repository artifact remains `source_quality=not_clean`; it is not the canonical URA input. Reviewed project geocodes and [`mrt_layer.csv`](../../data/inputs/mrt_layer.csv) add operational-station context. Types containing `House` are excluded; EC rows can remain.

## Comparison Framework

Each cohort reports transaction count, median PSF, median quantum, and median sqft for both districts:

- Bedrooms: 1, 2, 3, 4, and 5+; rows without bedrooms are excluded from this view.
- Size: under 600, 600–800, 800–1,000, 1,000–1,300, and 1,300+ sqft.
- Nearest operational MRT: under 400, 400–800, 800–1,200, and 1,200+ metres.

Every transaction inherits its project’s straight-line MRT distance. No minimum sample gate or mix adjustment is applied, so always read `n` with a median.

## Controls & Outputs

This page has no filters. It supplies district overview cards, side-by-side cohort tables, and project detail with nearest open MRT, distance, transaction count, and median PSF. Tables scroll horizontally on narrow screens.

## Interpretation Limits

The MRT metric is straight-line distance—not walking distance—while ungeocoded projects are excluded from that axis. Current geocode coverage represents 63% of D18 and 100% of D26 transaction rows. `not_clean` EdgeProp records, bedroom labels, different sale states, and changing project mix limit causal or investment conclusions. Medians are not repeat-unit appreciation.

## Rebuild

Run `python3 models/gen_district_pair_comparison_html.py --district-a 18 --district-b 26 --label-a "Pasir Ris / Tampines" --label-b "Lentor / Upper Thomson"`, then `python3 -m pytest tests/test_page_documentation.py`.
