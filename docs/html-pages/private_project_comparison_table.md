# Private Condominium Project Comparison

> Filters private apartment and condominium projects using achieved URA transactions, project-location evidence, school diagnostics, and separate estate context.

## Purpose

Use [private_project_comparison_table.html](../../private_project_comparison_table.html) for broad project discovery by district, MRT, sale state, price evidence, and school context before opening a focused comparison.

## Data & Scope

The [generator](../../models/gen_private_project_comparison_html.py) keeps Apartment, Condominium, and Executive Condominium rows from [ura_private.csv](../../data/inputs/ura_private.csv); landed rows are excluded. The source spans June 2021–July 2026. The committed build groups 102,895 transactions into 2,400 project/street/district/planning-area records.

Optional reviewed OneMap project coordinates supply MRT distances; missing coordinates use disclosed estate/planning-area centroids. Optional [school metrics](../../data/outputs/private_project_school_metrics.csv) supply project diagnostics. `master_output.csv` contributes estate-level Provision and private Value context.

## Comparison Framework

- **Project/location:** project, street, property type, district, planning area, nearest rail station/line/distance, coordinate source, and geocode quality.
- **Schools:** primary count and best proxy within 1km, best secondary proxy within 2km, and best JC/Year 5 proxy within 5km.
- **Price:** all-history and recent 12-month median $/sqm, project-vs-district delta, recent-vs-all delta, median achieved price, and median area.
- **Transactions:** total/recent samples, first/last sale, New Sale/Resale/Sub Sale mix, tenure, and market segment.
- **Estate context:** context estate, Provision band, private Value band, and Value sample count.

## Controls & Outputs

Search project/place text; multi-filter by district, nearest MRT, sale evidence, coordinate quality, and primary-school access. Clear filters from the active-query banner. Click any column heading to sort.

## Interpretation Limits

Price fields are achieved medians, not valuation or appreciation. “Recent vs all” is unit- and sale-mix-sensitive. MRT distances are straight-line; centroid rows are proxies. School ranks are sourced selectivity diagnostics, not admission guarantees—verify eligibility with MOE OneMap. Provision and private Value describe the estate context, never the project, block, stack, or unit. HDB Value is not applied.

## Rebuild

```bash
make private-project-locations       # optional refresh; requires ONEMAP_TOKEN
make private-project-school-metrics # requires reviewed project locations
make private-project-table
```

Review refreshed geocodes and generated output before relying on spatial comparisons.
