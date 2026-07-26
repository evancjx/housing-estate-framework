# Two-Condominium Framework Comparison

> Compares two named condominiums using project evidence first and the same separately labeled estate-context factors as the estate table.

## Purpose

Use [condo_framework_comparison.html](../../condo_framework_comparison.html) for a focused A-versus-B review without manufacturing an overall score or winner.

## Data & Scope

The [generator](../../models/gen_condo_framework_comparison_html.py) aggregates canonical URA private transactions, then enriches projects with reviewed coordinates, nearest rail, school metrics, and estate outputs. The committed page contains 2,307 named records and transaction evidence through July 2026; the canonical transaction layer begins in June 2021. Planning areas outside framework rows use disclosed context proxies.

## Comparison Framework

Seven factor groups are shown:

1. **Project market evidence:** median achieved price/PSF/area, sample period/depth, sale-state mix, recent-vs-all median, and tenure.
2. **Access and education:** nearest MRT, primary schools within 1km, best recorded primary proximity, and location source.
3. **Identity and Provision context:** context estate/basis, archetype, T0 disruption, Provision band/score.
4. **Liveability and trajectory:** four T0 persona bands plus Lifestyle T0→T5→T15.
5. **Liveability−Provision gaps:** YF, SP, Retiree, and Lifestyle.
6. **Value context:** private band/multiplier/sample; HDB Value is explicitly excluded.
7. **Employment, risk, and life paths:** employment T0/T5/T15, project tenure, noise, best/worst paths, and flags.

## Controls & Outputs

Select recognized Project A and B records, swap their order, and compare. The fourth column shows descriptive A−B differences. Copy a stable `?a=…&b=…` link or print/save the result as PDF. Links open each project in the broad transaction explorer.

## Interpretation Limits

Project histories may cover different periods, sale states, unit sizes, and sample depths. Recent-vs-all is not appreciation. Estate fields describe planning-area context or a proxy—not a condo, block, stack, or unit. Provision is objective; Liveability remains persona-relative; Value remains tenure-separated. HDB Value and HDB lease risk do not apply to private projects.

## Rebuild

```bash
make condo-framework-comparison
```

Refresh and review project locations and school metrics first when those source layers change.
