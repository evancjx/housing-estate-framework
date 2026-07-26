# Canberra Strategy 2: Newness

> Separates lease vintage, launch state, and transaction-period mix before interpreting price differences.

## Purpose

[Open the report](../../canberra_strategy_2_newness.html). This workbook studies “newness” as several observable factors rather than a single project-age premium. It uses the same four Canberra projects as Strategy 1. The deep analysis provides the full market and transaction audit; this page instead isolates lease clocks, first-observed market states, and time-mix changes.

## Data & Scope

Official URA PMI Apartment/Condominium rows provide prices and tenure text; EdgeProp supplies conservatively matched bedroom labels. Current controls use the common August 2025–June 2026 complete-month period. July 2026 is partial and excluded.

The vintage table also reads each project’s history through June 2026 in the rolling extract. “First observed New Sale” and “first observed exit” mean first within that extract—not the legal launch date, TOP date, or complete transaction history. Time tables split the common period into launch-era H2 2025 and H1 2026.

## Comparison Framework

The page considers:

- lease commencement and simple elapsed lease years;
- first observed New Sale and first Sub Sale/Resale;
- current sale-state composition;
- bedroom cohort;
- median quantum, PSF, and square feet; and
- H2 2025 versus H1 2026 transaction mix.

Canberra Crescent represents the youngest lease/developer-sale state. Watergardens controls for close geography and recent lease with Sub Sales; The Commodore adds emerging Resale evidence at similar vintage; Canberra Residences tests an older lease and larger-layout trade-off. No combined newness score is produced.

## Controls & Outputs

Synchronized tabs switch current-period and time-sliced tables between all units and 1BR–4BR. Outputs include the lease/market-state ladder, bedroom-matched common-period statistics, period medians, and an explanatory matrix for the four vintage roles.

## Interpretation Limits

Elapsed lease years are an as-of-year diagnostic, not a legal remaining-lease calculation. Period medians can change because of release sequence, bedroom availability, size, floor, or sale-state mix. Exact apartment identifiers are unavailable, so the H2/H1 comparison is not appreciation or a unit growth rate. Condition and completion effects also remain unobserved.

## Rebuild

Run `make canberra-d27-strategies` or `python3 models/gen_canberra_d27_peer_strategy_html.py`. See the [generator](../../models/gen_canberra_d27_peer_strategy_html.py), [tests](../../tests/test_canberra_d27_peer_strategy_html.py), and [micro-location documentation](canberra_strategy_1_micro_location.md).
