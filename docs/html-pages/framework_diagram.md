# Framework Architecture

> Visualizes how normalized, reviewed, and transaction inputs flow through the versioned pipeline into the master output.

## Purpose

Use [framework_diagram.html](../../framework_diagram.html) as a conceptual pipeline map. For the current machine-readable dependency map, also consult [FRAMEWORK_MAP.md](../FRAMEWORK_MAP.md).

## Data & Scope

The checked-in template is rendered against current canonical CSV metadata. It
depicts geospatial layers, reviewed inputs, HDB resale, and URA private
transactions feeding model cards and `data/outputs/master_output.csv`. Estate,
column, transaction, life-path, and model-version labels are generated rather
than manually copied.

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

Treat the page as architectural orientation. The active
[Provision](../../frameworks/1-provision-framework.md) and
[Liveability](../../frameworks/2-liveability-matrix.md) documents are
authoritative. Provision must not be merged with persona-relative Liveability
into a unified verdict, and HDB/private Value must remain tenure-separated.

## Rebuild

Update the checked-in template and builder together when pipeline structure
changes, then run:

```bash
make framework-diagram
make pages-check
```
