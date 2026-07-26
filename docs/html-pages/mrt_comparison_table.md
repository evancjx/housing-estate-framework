# MRT Station Comparison

> Compares MRT/LRT station records and attaches disclosed nearest-estate framework context.

## Purpose

Use [mrt_comparison_table.html](../../mrt_comparison_table.html) to research open and future rail stations by line, location, centroid catchment, and nearby estate-model signals.

## Data & Scope

The [generator](../../models/gen_mrt_comparison_html.py) reads [mrt_layer.csv](../../data/inputs/mrt_layer.csv), estate centroids, and [master_output.csv](../../data/outputs/master_output.csv). For each station it calculates straight-line distance to every framework estate centroid and selects the nearest. The committed build contains 183 station records (179 open and 4 future) and was generated on 25 July 2026.

## Comparison Framework

- **Station:** name, code, line badge, operational status, and full line name.
- **Nearest-estate context:** estate, centroid distance, distance band, and numbers of estate centroids within 800m and 1.4km. Bands are `core` ≤600m, `near` ≤1,000m, `edge` ≤1,400m, then `outside`.
- **Estate signals:** Provision band/score, Lifestyle Liveability T0→T5→T15, and separate HDB/private Value bands.
- **Employment/risk:** current employment band and HDB lease-risk band.

## Controls & Outputs

Filter by All/Open/Future status and by rail line. Search station name, code, line, or nearest estate. Click a heading to sort the 17-column table.

## Interpretation Limits

Nearest estate is a centroid-distance diagnostic, not formal station assignment, walking distance, route time, or station catchment. Every model field describes that estate context—not the station itself. Provision and persona-relative Liveability retain different meanings; HDB and private Value remain separate. Future status does not imply a project delivery guarantee beyond the committed source layer.

## Rebuild

After changing rail or estate outputs, run:

```bash
python3 models/gen_mrt_comparison_html.py
```

Use `make pipeline` first when framework outputs require regeneration.
