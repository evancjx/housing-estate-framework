# Framework Architecture

> Visualizes how geospatial, judged, and transaction inputs flow through estate models into the master output.

## Purpose

Use [framework_diagram.html](../../framework_diagram.html) as a conceptual pipeline map. For the current machine-readable dependency map, also consult [FRAMEWORK_MAP.md](../FRAMEWORK_MAP.md).

## Data & Scope

This is a manually maintained static HTML artifact, not a page generated from live CSV schemas. It depicts geospatial layers, judged inputs, HDB resale, and URA private transactions feeding model cards and `data/outputs/master_output.csv`.

Its embedded snapshot labels currently say 32 estates, 4 models, 57 output columns, and a 13-component Provision design. Those counts lag the active 20-component Provision pipeline and current 35-estate comparison output.

## Comparison Framework

The diagram presents four model families:

- **Provision:** objective supply and disruption context.
- **Liveability Matrix:** four personas across T0/T5/T15, with certainty, veto, and gap concepts.
- **Value Residual:** price residuals segmented into HDB and private universes.
- **Life Paths:** cross-persona/horizon transitions such as forming a family, downsizing, settling single, ageing in place, and upgrading.

It then groups output fields into identity, Provision, Liveability, gaps, HDB Value, private Value, life paths, and flags.

## Controls & Outputs

The page has no filters or computed output. It is a responsive architecture diagram with model definitions, data-flow arrows, an output-schema summary, and invariant notes.

## Interpretation Limits

Treat the page as architectural orientation only until its embedded counts and component list are refreshed. The active [Provision](../../frameworks/1-provision-framework.md) and [Liveability](../../frameworks/2-liveability-matrix.md) documents are authoritative. Provision must not be merged with persona-relative Liveability into a unified verdict, and HDB/private Value must remain tenure-separated.

## Rebuild

There is no checked-in generator. Update `framework_diagram.html` manually when pipeline structure changes, verify claims against the active specs and `master_output.csv`, then run:

```bash
python3 scripts/build_pages_site.py
```
