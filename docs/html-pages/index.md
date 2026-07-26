# Estate Research Hub

> Routes researchers from the broad project or estate explorers into narrower district, project, transaction, and method reports.

## Purpose

Use [index.html](../../index.html) as the publication landing page. It presents a short research
workflow, featured starting points, and the complete report library without introducing another
score or comparison result.

## Data & Scope

The page is maintained alongside the machine-readable [`site/reports.json`](../../site/reports.json)
catalog. During the Pages build, [`scripts/build_pages_site.py`](../../scripts/build_pages_site.py)
also derives `projects.json` from the committed EdgeProp project list and known transaction
districts. That lookup contains names, slugs, and districts only; it does not publish raw or
exact-unit transaction evidence.

## Comparison Framework

The hub recommends a three-stage workflow: identify the subject project or district, match like
with like using bedroom/size/floor/sale state, then add household context through separate
Provision, Liveability, and tenure-specific Value views. Report cards are grouped as project,
district, estate/household, or method resources. The hub itself performs no ranking.

## Controls & Outputs

Search report titles, summaries, and tags, or filter cards by report kind. “Find a condo” uses the
generated compact project lookup to route a known project into the private-project explorer.
Navigation links open the chosen generated report.

## Interpretation Limits

Catalog discovery does not establish that reports use identical periods, sources, cohorts, or
sample depth. Read the chosen report’s guide and in-page caveats before comparing values. Project
evidence must not be treated as an estate score, and Provision, persona-relative Liveability, HDB
Value, and private Value must remain separate views.

## Rebuild

```bash
make pages-check
make pages-build
```

Update the landing card and [`site/reports.json`](../../site/reports.json) together when publishing
or withdrawing a report.
