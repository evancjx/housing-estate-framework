# Poiz and East Unit-type Growth and Transactions

> Inspect annual history, rolling transaction-median changes, and every available resale record for the nine-project Poiz comparison set.

## Purpose

Use the [transaction companion](../../poiz_east_unit_growth_transactions.html) to audit the records behind the Poiz-versus-East findings by project and observed unit type.

## Data & Scope

The cohort comes from [`poiz_east_project_profiles.csv`](../../data/inputs/poiz_east_project_profiles.csv). [`private_transactions_bedrooms.csv`](../../data/outputs/private_transactions_bedrooms.csv) combines canonical URA condo/apartment caveats from 2021 onward with separately identified, incomplete `not_clean` EdgeProp backfill limited to 2019–2020. Bedrooms are provenance-tagged enrichment because public URA rows do not expose them. The current build contains 1,757 resale records; 2026-07 is partial, while rolling analysis ends at 2026-06.

## Comparison Framework

- Keep projects separate and segment each by all records, 1–5 bedrooms, or unknown bedroom.
- Compare latest-12-month median achieved PSF and quantum with the preceding 12 complete months.
- Display a change only when both periods have at least three transactions.
- Show recent/prior counts, median size, full available history count, and first/last observed month beside each segment.
- Retain annual median PSF with its count, including visibly thin cells; include partial-month records in the ledger but not growth calculations.

These are changes in the composition-sensitive median of transactions, not verified appreciation of a physical unit.

## Controls & Outputs

Project tabs update the report and URL hash. Within each project, filter the full ledger by unit type, sale year, or free-text month, floor range, price, and PSF. Outputs include headline metrics, growth tables, annual history, and row-level price, size, tenure, bedroom evidence, and sale provenance.

## Interpretation Limits

“Exact row match” describes a bedroom joined to a transaction; it is not an exact unit number. Similar bedroom, size, and floor-range records may be different apartments. URA caveats are voluntary, floor values are bands, and older EdgeProp rows are incomplete and `not_clean`.

## Rebuild

Run `make poiz-east-unit-growth`, then `python3 -m pytest tests/test_poiz_east_unit_growth_html.py`.
