# Bedroom-Count Tabs for District Private Comparison Pages — Design

**Date:** 2026-07-07
**Status:** Approved
**Builds on:** `2026-07-07-district-size-band-breakdown-design.md` (size tabs + ≈nBR labels, shipped)

## Problem

Size bands are area proxies. The user wants a first-class breakdown by number of bedrooms:
tabs 1BR · 2BR · 3BR · 4BR · 5BR+ · Unknown, each with the same per-project trend table as the
size tabs.

## Bedroom assignment (inference)

- The EdgeProp label loader is refactored: `load_edgeprop_bedroom_counts(path, district) ->
  dict[tuple[str, str], int]` — same learning rule as before (per (display_project, band_key):
  n ≥ 2 EdgeProp rows, modal share ≥ 0.6 (relaxed 2026-07-08)) but returns the **integer** modal bedroom count.
  The `≈nBR` display string is built at render time (`f"≈{n}BR"`). The two existing label tests
  update their assertions from `"≈3BR"` to `3`.
- Every merged transaction gets a bedroom class from its `(display_project, band_of(area_sqm))`
  key via that dict:
  - count 1–4 → `br1`…`br4`; count ≥ 5 → `br5plus`; no confident label (incl. all landed) → `brunknown`.
- Constants: `BEDROOM_ORDER = ["br1","br2","br3","br4","br5plus","brunknown"]`,
  `BEDROOM_LABELS = {"br1":"1BR","br2":"2BR","br3":"3BR","br4":"4BR","br5plus":"5BR+","brunknown":"Unknown"}`,
  helper `bedroom_class(count: int | None) -> str`.

## Page structure

- The tab bar becomes **two labelled rows**, all tabs mutually exclusive (one active section):
  - `Size:` All · ≤50 · 50–70 · 70–100 · 100–130 · >130 sqm (unchanged behaviour)
  - `Bedrooms:` 1BR · 2BR · 3BR · 4BR · 5BR+ · Unknown
- Each bedroom tab = same structure as a size tab: band meta line, summary strip
  (`district_summary` on the class subset), per-project table (`aggregate_projects` on the
  subset). Section ids `band-br1` … `band-brunknown`; same JS tab switching and sorting.
- The `Bedrooms` (≈nBR) column appears ONLY on size-band tabs (not `all`, not bedroom tabs —
  redundant there).
- Empty bedroom classes still render (empty table), same as empty size bands.
- Caveat banner gains: bedroom classes are inferred per project + size band from EdgeProp
  listings; atypical units can be misclassified; Unknown collects unlabelled transactions,
  including all landed.

## Code changes

All in `models/gen_district_private_comparison_html.py`:

- Rename/refactor `load_edgeprop_bedroom_labels` → `load_edgeprop_bedroom_counts` (int values).
- New `BEDROOM_ORDER`, `BEDROOM_LABELS`, `bedroom_class()`.
- `generate()`: assigns each merged row a bedroom class, adds one `per_band` entry per
  `BEDROOM_ORDER` key; passes the counts dict to `render_html`.
- `render_html(district, per_band, bedroom_counts)`: two labelled tab rows; sections iterate
  `BAND_ORDER + BEDROOM_ORDER` (keys present in `per_band`); `_render_project_table` shows the
  ≈nBR column only for size-band keys.

## Testing

- `bedroom_class` mapping (1→br1, 4→br4, 5/7→br5plus, None→brunknown).
- Assignment: labelled project+band txns land in the right bedroom section; landed/unlabelled
  txns appear only in `band-brunknown`.
- Refactored loader returns ints; existing mode-share tests updated.
- Render: both tab rows present; `≈nBR` column absent in bedroom sections.
- Integration (real D17/D27): bedroom tab labels and `id="band-brunknown"` present.

## Out of scope

- No bedroom inference beyond the existing project+band label mapping.
- No changes to loaders' price windows or the size-band logic.
