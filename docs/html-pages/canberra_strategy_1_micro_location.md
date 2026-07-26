# Canberra Strategy 1: Micro-location

> Holds geography relatively tight by comparing Canberra Crescent with three same-precinct controls.

## Purpose

[Open the report](../../canberra_strategy_1_micro_location.html). This workbook asks what remains after minimising location drift. Canberra Crescent is compared with The Watergardens at Canberra, The Commodore, and Canberra Residences. Unlike the deep analysis, it omits the district-wide ledger, distant Yishun controls, schools, and planning context to concentrate on nearby achieved-price evidence.

## Data & Scope

Official URA PMI Apartment/Condominium rows are the transaction source; conservatively matched EdgeProp rows supply bedroom labels. All four projects use the same complete-month period, August 2025–June 2026, beginning with the subject’s first observed complete-month transaction. July 2026 is partial and excluded from medians.

The project roles are deliberately different: developer New Sale subject, recent same-precinct control, recent exit-state control, and older same-precinct Resale control.

## Comparison Framework

Geography is controlled first, then these factors are retained:

- bedroom type and median floor area;
- median total quantum and median PSF;
- P10–P90 price and PSF dispersion;
- New Sale, Sub Sale, and Resale composition;
- lease vintage and floor/layout heterogeneity; and
- future usefulness as an exit comparable.

The decision sequence is bedroom/area match → sale-state match → range inspection → exit-comparable stress test. Watergardens and The Commodore provide newer evidence; Canberra Residences tests the older-lease/larger-layout trade-off. Cross-project gaps are not combined into a winner.

## Controls & Outputs

Tabs switch all project rows together between all units and 1BR–4BR cohorts. Each row reports transaction count and states, median quantum with P10–P90, median PSF with P10–P90, and median size. Finding cards summarise the three peer roles; the decision matrix explains the comparison order.

## Interpretation Limits

A shared precinct does not make projects identical. Sale state, lease start, layout, floor, view, and condition remain confounders. Bedroom labels are secondary evidence, and thin bedroom cohorts should not be treated as valuations. Exact apartments are unavailable, so cross-sectional differences and period medians do not establish repeat-sale growth.

## Rebuild

Run `make canberra-d27-strategies` to regenerate all strategy workbooks, or `python3 models/gen_canberra_d27_peer_strategy_html.py` for strategies 1–3. See the [generator](../../models/gen_canberra_d27_peer_strategy_html.py), [tests](../../tests/test_canberra_d27_peer_strategy_html.py), and [deep-analysis documentation](canberra_crescent_d27_deep_analysis.md).
