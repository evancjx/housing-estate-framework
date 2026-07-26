# Canberra Strategy 3: Integration

> Compares rail proximity, retail-at-project, and town-centre integration as separate convenience layers.

## Purpose

[Open the report](../../canberra_strategy_3_integration.html). This workbook tests whether different forms of convenience correspond with different achieved-price evidence. It intentionally widens beyond Canberra to North Park Residences, The Wisteria, and Nine Residences, while retaining three nearby Canberra controls. Unlike the deep analysis, its primary output is a sourced access/retail diagnostic and buyer-fit interpretation, not a full district ledger.

## Data & Scope

Price evidence comes from official URA PMI Apartment/Condominium transactions in the latest 18 complete months, January 2025–June 2026. July 2026 is partial and excluded. EdgeProp supplies conservatively matched bedroom labels. Reviewed project coordinates and operational LTA station coordinates produce straight-line distance. Direct project/developer sources establish retail format.

The seven-project sample intentionally accepts Yishun/Canberra location drift so the report can contrast full integration, retail podiums, near-rail residential peers, and the subject.

## Comparison Framework

Convenience is split into:

- nearest operational MRT and straight-line distance;
- residential-only, retail-podium, mixed-use mall, or integrated town-centre format;
- factual retail relationship and buyer trade-off;
- lease vintage and sale-state depth;
- bedroom cohort, median quantum, median PSF, and median size; and
- P10–P90 price and PSF dispersion.

North Park is the full town-centre/transport-hub test. The Wisteria and Nine Residences test retail at the project without interchange-level integration. Canberra peers test near-rail access without an integrated-mall premise. The page does not estimate a causal “integration premium.”

## Controls & Outputs

Tabs switch the price/access table between all units and 1BR–4BR. The retail register links direct evidence and states each project’s access proposition. Additional cards provide three integration tests and a buyer-fit matrix for rail users, convenience-first households, value-focused buyers, and exit-focused buyers.

## Interpretation Limits

Haversine distance is not walking time: entrances, crossings, shelter, gradients, and routes are absent. Retail labels do not measure tenant quality, service depth, strata governance, or future performance. Wider geography, age, lease, size, and sale state confound observed price gaps. Asking prices, rents, and causal price adjustments are outside scope.

## Rebuild

Run `make canberra-d27-strategies` or `python3 models/gen_canberra_d27_peer_strategy_html.py`. See the [generator](../../models/gen_canberra_d27_peer_strategy_html.py), [tests](../../tests/test_canberra_d27_peer_strategy_html.py), and [planning-context documentation](canberra_strategy_6_planning_context.md).
