# Katong Condominium Comparison

> Compare eight reviewed Katong-area projects without collapsing different micro-markets, sale states, or evidence quality into one ranking.

## Purpose

Use the [interactive report](../../katong_condo_comparison.html) to research buyer fit, achieved prices, liquidity, access, floor sensitivity, and transaction evidence for four current-launch benchmarks and four completed controls.

## Data & Scope

The reviewed cohort is defined in [`katong_project_profiles.csv`](../../data/inputs/katong_project_profiles.csv). Transactions come from [`private_transactions_bedrooms.csv`](../../data/outputs/private_transactions_bedrooms.csv): canonical URA caveats own 2021 onward, while any 2019–2020 backfill is separately tagged from the `not_clean` EdgeProp scrape. OneMap-reviewed coordinates, operational MRT data, school diagnostics, and official project sources provide context. The current build contains 2,879 caveats; its headline period is 2025-01–2026-06.

## Comparison Framework

- Keep new sale, sub-sale, and resale selectable rather than pooling their price-setting conditions.
- Compare median quantum, P10–P90 quantum, median PSF, median size, and bedroom-label coverage over the latest 18 complete months.
- Show median-PSF change between adjacent 12-month windows only with at least three caveats in each window. This is transaction-median movement, not repeat-unit appreciation.
- Define liquidity as latest-12-month caveats divided by official project stock, not unique sellers.
- Report floor-band medians only where the headline window has at least three caveats.
- Admit repeat-sale analysis only from the optional authorised EdgeProp unit file when a row is marked `exact` and contains a valid unmasked `#floor-stack` token.

## Controls & Outputs

Filter by sale state, bedroom, launch/completed cohort, project, and ledger search. Copy the filtered URL or export visible ledger rows to CSV. The report also supplies project profiles, a coordinate locator, floor bands, the exact-unit evidence gate, planning risks, and a source register.

## Interpretation Limits

URA caveats are voluntary. Bedrooms are provenance-tagged secondary enrichment; MRT and school values are straight-line diagnostics. Do not blend project evidence into an estate Provision score or infer unit identity from bedroom, area, or floor band.

## Rebuild

Run `make katong-comparison`, then `python3 -m pytest tests/test_katong_comparison_html.py`.
