# Poiz Versus East-side Resale Comparison

> Test The Poiz against eight East-side controls using bedroom-matched resale evidence, liquidity, access, buyer fit, and planning context.

## Purpose

The [buyer-oriented report](../../poiz_east_resale_comparison.html) treats The Poiz as a reference project rather than declaring an overall winner. Its controls cover integrated, high-liquidity, coastal, freehold, and larger-unit alternatives across Katong/Eunos and Bedok/Tampines.

## Data & Scope

Nine projects are curated in [`poiz_east_project_profiles.csv`](../../data/inputs/poiz_east_project_profiles.csv). Resale-only caveats come from [`private_transactions_bedrooms.csv`](../../data/outputs/private_transactions_bedrooms.csv), whose canonical recent rows are official URA evidence and whose bedroom fields retain explicit EdgeProp or research provenance. Reviewed OneMap coordinates, operational MRT stations, school metrics, official project facts, and primary URA/LTA planning sources provide supporting context. The current headline window is 2025-01–2026-06; liquidity uses 2025-07–2026-06.

## Comparison Framework

- Compare all resales and matched 1BR, 2BR, 3BR, or 4BR segments separately.
- Report sample size, median quantum with P10–P90 range, median PSF, median size, bedroom provenance, 12-month liquidity, nearest open MRT, and primary-school count.
- Calculate PSF, size, and quantum differences relative to Poiz only when both bedroom samples contain at least three transactions.
- Label samples as strong (`n ≥ 10`), usable (`n ≥ 5`), thin (`n ≥ 3`), or insufficient.
- Define liquidity as resale caveats divided by official unit stock, not seller turnover.

## Controls & Outputs

Bedroom tabs switch the comparison table. Project profiles, evidence-led findings, a buyer decision matrix, catalyst treatment, and source registers explain why each control belongs. A companion link opens the complete unit-type transaction ledger.

## Interpretation Limits

Bedroom matching does not control size, floor, facing, view, condition, or exact apartment. Achieved-sale medians are not repeat-unit appreciation. MRT and school distances are straight-line diagnostics, and future plans are context—not realised price uplift. This project diagnostic remains separate from estate Provision and persona-relative Liveability outputs.

## Rebuild

Run `make poiz-east-comparison`, then `python3 -m pytest tests/test_poiz_east_resale_comparison_html.py`.
