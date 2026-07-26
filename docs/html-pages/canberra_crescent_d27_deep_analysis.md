# Canberra Crescent District 27 Deep Analysis

> Audits Canberra Crescent Residences launch evidence against matched peers and every condominium transaction in the current District 27 extract.

## Purpose

[Open the report](../../canberra_crescent_d27_deep_analysis.html). This is the Canberra research hub and deepest evidence view. It combines a subject launch audit, bedroom-matched primary peers, an all-project district table, planning context, and a row-level transaction diagnostic. It supports Liveability/Value research; it does not create a condominium ranking or alter estate-level Provision scores.

## Data & Scope

The committed URA PMI extract contains 2,884 official District 27 Apartment/Condominium rows from July 2021 through July 2026. Executive Condominiums and landed homes are excluded. Headline medians use the latest 18 complete months (January 2025–June 2026); 14 July 2026 partial-month rows remain flagged in the ledger only. Raw URA multiplicity is preserved because identical public attributes may describe different apartments.

Secondary EdgeProp matches provide bedroom labels. Project coordinates, school counts, and operational MRT coordinates come from the repository’s private-property geospatial outputs.

## Comparison Framework

The report keeps these factors visible: sale state, bedroom type, size, floor band, total quantum, PSF and P10–P90 range, tenure, observed period, straight-line MRT distance, nearby-primary-school count, and planning status.

Every transaction is compared with:

- District 27 calendar year × sale state × bedroom peers;
- its project × calendar year × bedroom median; and
- calendar year × sale state × 100-sqft size peers.

Subject-versus-peer table deltas require at least three rows on both sides. A cohort containing only one project is labelled launch-position evidence, not a market comparison. The six strategy workbooks narrow this broad audit to one confounder at a time.

## Controls & Outputs

Bedroom tabs switch the primary-peer table between all units and 1BR–4BR cohorts. The full ledger can be filtered by project, sale state, bedroom, year, percentile position, or free-text search. Outputs include launch bedroom/month/floor tables, primary-peer results, all-project market context, planning evidence, and a diagnostic for each official row.

## Interpretation Limits

URA caveats are voluntary and not exhaustive. Exact unit numbers, repeat-sale identity, view, facing, condition, discounts, and purchaser identity are unavailable. Launch-month movement is release-mix evidence, not appreciation. EdgeProp bedroom labels are secondary evidence. MRT distances are straight-line, school diagnostics are not official home-school measurements, and future plans are not booked returns.

## Rebuild

Run `make canberra-d27-analysis` or `python3 models/gen_canberra_crescent_d27_html.py`. See the [generator](../../models/gen_canberra_crescent_d27_html.py), [focused tests](../../tests/test_canberra_crescent_d27_html.py), and [URA input](../../data/raw/ura/pmi_d27_2021-2026.csv).
