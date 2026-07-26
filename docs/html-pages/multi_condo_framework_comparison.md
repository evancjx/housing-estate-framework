# Multi-Condominium Framework Comparison

> Compares two to five ordered condominium projects across a common achieved-sales cohort, detailed transaction evidence, and a separate estate-context framework.

## Purpose

Use [multi_condo_framework_comparison.html](../../multi_condo_framework_comparison.html) for detailed multi-project research. Project A is the neutral reference; the page reports descriptive differences but no winner or combined score.

## Data & Scope

The [generator](../../models/gen_multi_condo_framework_comparison_html.py) reconciles 118,619 rows across 2,307 named projects into on-demand [transaction shards](../../site/assets/condo-transactions/). Canonical URA coverage starts June 2021, the latest complete month is June 2026, and July 2026 is partial. A separately tagged, incomplete EdgeProp backfill covers observed 2019–2020 rows; January–May 2021 is not covered. The default cohort is the latest 60 complete months (July 2021–June 2026).

## Comparison Framework

The transaction section compares filtered coverage/count, median and P10–P90 achieved price and PSF, median size, sale-state mix, bedroom coverage, prior-vs-recent 12-month median PSF movement, annual median PSF with `n`, evidence depth, mix cautions, and full row ledgers.

The separate framework matrix then uses the same seven groups as the two-project page: project market evidence; access/education; Identity/Provision; persona-relative Liveability and Lifestyle trajectory; Liveability−Provision gaps; private Value context; and Employment/Risk/Life Paths. HDB Value and HDB lease risk are marked not applicable.

## Controls & Outputs

Add, remove, or keyboard-reorder 2–5 unique projects; A remains the reference. Filter transactions by 12/36/60 months or all history, sale state, bedroom, size, floor, and source. Expand/collapse factor groups, page through ledgers, download filtered CSV, copy an ordered link that preserves projects and filters, or print/save PDF.

Ledgers expose sale month/state, bedroom provenance, floor, size, achieved price/PSF, and source.

## Interpretation Limits

Medians and movement are cohort- and mix-sensitive, not repeat-unit appreciation, returns, forecasts, or liquidity rates. Older coverage is incomplete and the 2021 gap prevents a continuous long series. Bedroom evidence is transaction-row matched or size-band inferred; it is not an exact apartment number. Estate context is not a project/block/stack/unit score. Never combine Provision with persona-relative Liveability or blend private Value with HDB.

## Rebuild

```bash
make multi-condo-framework-comparison
```

This regenerates the HTML and compact transaction shards. Review the printed reconciliation counts and [manifest](../../site/assets/condo-transactions/manifest.json).
