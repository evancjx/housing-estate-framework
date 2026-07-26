# Canberra Strategy 6: Planning Context

> Classifies northern infrastructure as delivered, committed, or conceptual without converting plans into booked returns.

## Purpose

[Open the report](../../canberra_strategy_6_planning_context.html). This workbook is a source-led guardrail for infrastructure narratives around Canberra and northern Singapore. The deep analysis includes a compact planning table; this page adds an evidence ladder, peer-exposure controls, and explicit decision rules.

## Data & Scope

The transaction anchor is Canberra Crescent’s official URA PMI Apartment/Condominium caveats in the January 2025–June 2026 complete-month window. Planning evidence does not alter those prices. LTA and URA primary pages provide delivery status and published horizons reviewed on the report generation date.

The register covers Canberra MRT/Canberra Plaza, the North-South Corridor, RTS Link/Woodlands Regional Centre, Sembawang Shipyard transformation, and additional North-region housing.

## Comparison Framework

Each item records:

- evidence class: delivered, committed/targeted, progressive, or long-dated concept;
- authority-published horizon;
- treatment in the comparison; and
- direct primary source.

Delivered infrastructure belongs in present access/liveability evidence and is not counted again as future upside. Committed projects are scenario context subject to timing and indirect-benefit risk. Concepts receive zero base-case uplift while retaining optionality and competing-supply risk.

The peer-exposure matrix compares Canberra Crescent, nearby Canberra peers, North Park, and Wisteria/Nine. Shared exposure matters: district-wide plans should not be credited only to the subject. It also records location, age, lease, completion, and sale-state confounders.

## Controls & Outputs

This is a static workbook. Outputs include the three-class evidence cards, linked official planning register, peer-exposure matrix, and a Delivered → Targeted → Conceptual decision sequence. Buyers should observe delivered assets, scenario-test targets, and assign no base-case uplift to concepts.

## Interpretation Limits

Published dates and commitments can change; re-verify authority pages before deciding. A zero base-case uplift is a conservative treatment, not proof that infrastructure has no future effect. The page does not estimate causality, forecast returns, score condominiums, or modify Provision. Common district exposure and future competing supply can offset a simple catalyst narrative.

## Rebuild

Run `make canberra-d27-strategies` or `python3 models/gen_canberra_d27_control_strategy_html.py`. See the [generator](../../models/gen_canberra_d27_control_strategy_html.py), [tests](../../tests/test_canberra_d27_control_strategy_html.py), and [integration documentation](canberra_strategy_3_integration.md).
