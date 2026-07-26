# Canberra Strategy 5: Sale State

> Keeps New Sale, Sub Sale, and Resale evidence separate when comparing price formation and liquidity.

## Purpose

[Open the report](../../canberra_strategy_5_sale_state.html). This workbook prevents developer launch absorption from being mistaken for resale liquidity or appreciation. The deep analysis preserves sale state per row; this page expands it into state-by-year market breadth, current project liquidity, and the subject’s launch sequence.

## Data & Scope

Official URA PMI Apartment/Condominium caveats cover District 27. The headline and project-liquidity window is January 2025–June 2026, the latest 18 complete months in the current build. July 2026 remains in the deep ledger but is excluded here as partial. The state-by-year table uses complete rows through June 2026. EdgeProp-derived bedroom labels are used only to describe the subject’s monthly bedroom mix.

Counts are official caveat rows, not unique buyers, completed sales, or developer-confirmed sell-through.

## Comparison Framework

Three price-forming processes remain separate:

- **New Sale:** developer release, booking, incentive, and launch-unit mix;
- **Sub Sale:** assignment and pre-/early-completion seller conditions; and
- **Resale:** owner decisions, condition, remaining lease, and a lived-in project market.

The page compares transaction count, number of represented projects, median quantum, median PSF and PSF IQR, median size, and observed months. Project breadth shows whether a state/year median is broad or launch-dominated. The subject sequence also reports bedroom mix and PSF versus its first launch month, expressly as compositional evidence.

## Controls & Outputs

This is a static, horizontally scrollable workbook. Outputs include one headline card per sale state, the state-by-year district table, current-window project results grouped by state and transaction depth, and Canberra Crescent’s monthly launch sequence. Interpretation cards distinguish launch absorption, Resale exits, and the Sub Sale bridge.

## Interpretation Limits

Sale states can be displayed side by side but must not be spliced into one appreciation line. A high New Sale count does not demonstrate future exit liquidity. The first launch month is not a repeat-sale base, and changing unit/floor mix can move its median. Caveats are voluntary and non-exhaustive; apartment identity, incentives, condition, and buyer identity are unavailable.

## Rebuild

Run `make canberra-d27-strategies` or `python3 models/gen_canberra_d27_control_strategy_html.py`. See the [generator](../../models/gen_canberra_d27_control_strategy_html.py), [tests](../../tests/test_canberra_d27_control_strategy_html.py), and [unit-matching documentation](canberra_strategy_4_unit_matching.md).
