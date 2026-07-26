# Landed Property Growth Dashboard

> Explore landed-house PSF trends by district and project with transparent sample thresholds, peer blending, and capped extrapolations.

## Purpose

The [dashboard](../../landed_growth_dashboard.html) diagnoses public landed transaction patterns and why an observed district or project trend differs from its peer baseline. It is not an investment forecast.

## Data & Scope

The current build uses 7,027 valid rows for 584 projects in 23 districts, dated 2019-01-01–2026-06-27. Its sole transaction source is the rendered [`edgeprop_landed_transactions_playwright_not_clean.csv`](../../data/raw/edgeprop/edgeprop_landed_transactions_playwright_not_clean.csv). EdgeProp labels the public tables as URA-sourced, but this artifact remains `source_quality=not_clean`, not canonical official URA data. Positive price, area, and PSF plus a usable project and district are required.

## Comparison Framework

- Aggregate annual median PSF, price, area, and count; use the latest 365 days for recent metrics.
- Fit a sample-weighted log trend only across complete years with at least five district or two project transactions; at least two eligible years are required.
- Exclude partial 2026 from the fit while retaining its rows in recent metrics.
- Blend high-confidence project trends 70% project/30% district, medium 50/50, and low-confidence projects to the district fallback; districts can fall back to market.
- Cap projection rates between -10% and +18% annually and extrapolate directional PSF values. The current horizons are 2027, 2029, and 2031.

Confidence also reflects total count, active years, eligible trend years, and recent project evidence.

## Controls & Outputs

Search by district, project, or planning area; switch district/project mode; filter district and confidence; set minimum transactions; and sort by projection rate, recent movement, count, PSF, or peer delta. Click charts, movers, or table rows for annual observed/projected PSF, evidence details, explanatory mix signals, and confidence.

## Interpretation Limits

Annual medians are mix-sensitive to tenure, sale state, house type, and plot area. Simple capped extrapolation can compound source and model error and is not valuation advice. No exact physical-unit evidence exists, so trends are never repeat-unit appreciation.

## Rebuild

Run `python3 models/gen_landed_growth_dashboard_html.py`, then `python3 -m pytest tests/test_landed_growth_dashboard_html.py`.
