# Canberra Strategy 4: Unit Matching

> Withholds broad comparisons until bedroom and 100-sqft size cohorts are sufficiently deep on both sides.

## Purpose

[Open the report](../../canberra_strategy_4_unit_matching.html). This workbook tests Canberra Crescent against The Watergardens at Canberra, The Commodore, and Canberra Residences after matching the home more tightly. The deep analysis matches primary tables by bedroom; this page adds a strict same-size-band rule and a subject floor-band audit.

## Data & Scope

Official URA PMI District 27 Apartment/Condominium caveats provide transaction price, area, floor band, and sale state. EdgeProp supplies conservatively attributed bedroom labels. The current build uses the latest 18 complete months, January 2025–June 2026. July 2026 is partial and excluded.

Eligible unit types are 1BR–4BR. Each strict cell is bedroom count × 100-sqft band. A subject cell and peer cell must each contain at least three caveats; otherwise the comparison is withheld.

## Comparison Framework

The control order is bedroom → 100-sqft size band → URA floor band. Every matched result retains:

- subject and peer sample counts;
- peer New Sale/Sub Sale/Resale state;
- subject and peer median total quantum;
- subject and peer median PSF;
- peer-versus-subject PSF gap; and
- peer-versus-subject quantum gap.

Positive gaps mean the peer achieved more than the subject; they are not forecasts. The pre-match coverage table exposes all-unit mix, while the subject floor audit helps identify launch release sequencing. Missing strict cells are reported as weak comparability rather than silently widened.

## Controls & Outputs

This is a static workbook with horizontally scrollable tables rather than interactive filters. Outputs are the subject headline median, count of eligible matched cells, peer bedroom/state coverage, strict matched results, and subject bedroom × floor-band medians.

## Interpretation Limits

Three caveats are a minimum disclosure threshold, not proof of a stable market. URA supplies floor bands rather than exact floors and does not expose view, facing, layout, condition, discounts, or apartment identity. EdgeProp bedroom attribution is secondary. Even matched cells may differ in sale state and lease vintage. Compact units can carry higher PSF but lower quantum, so neither metric should be read alone.

## Rebuild

Run `make canberra-d27-strategies` or `python3 models/gen_canberra_d27_control_strategy_html.py`. See the [generator](../../models/gen_canberra_d27_control_strategy_html.py), [tests](../../tests/test_canberra_d27_control_strategy_html.py), and [deep-analysis documentation](canberra_crescent_d27_deep_analysis.md).
