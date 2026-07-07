# Size-Band Breakdown for District Private Comparison Pages — Design

**Date:** 2026-07-07
**Status:** Approved
**Builds on:** `2026-07-07-district-private-comparison-design.md` (D17/D27 pages, shipped)

## Problem

The per-district pages aggregate each project across all unit sizes, so a project's PSF trend
mixes 1-bedders with penthouses. The user wants a room-size breakdown for like-for-like
comparison across projects.

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Size basis | **Both**: floor-area bands for all rows + bedroom labels where EdgeProp provides them |
| Layout | **Size tabs above the table** — each tab is a pre-computed per-band project table |

## Area bands

Applied to `area_sqm` of every unified-schema row (all three sources, landed included):

| Band key | Range |
|---|---|
| `le50` | area ≤ 50 |
| `50to70` | 50 < area ≤ 70 |
| `70to100` | 70 < area ≤ 100 |
| `100to130` | 100 < area ≤ 130 |
| `gt130` | area > 130 |

Plus the pseudo-band `all` (no filter). Band boundaries live in one constant
`AREA_BANDS: list[tuple[key, label, lo, hi]]` with a `band_of(area_sqm) -> key` helper.
Display labels: `≤50 sqm`, `50–70 sqm`, `70–100 sqm`, `100–130 sqm`, `>130 sqm`.

## Bedroom labels

- Source: the EdgeProp scrape (`Bedrooms` column), **all years 2019–2026**, for the target
  district. Labels only — prices/areas from these rows are NEVER merged into the transaction
  dataset (the 2019–2020-only backfill rule from the parent spec is unchanged).
- Learning rule, per (display_project, band): collect EdgeProp rows with a parseable integer
  `Bedrooms`, band their `Area (sqm)`; if the group has **n ≥ 2** rows and the modal bedroom
  count has **≥ 60% share** (relaxed 2026-07-08 from n ≥ 3 / 70% to lift coverage), the label is `≈{mode}BR`. Otherwise: no label (blank cell).
- `load_edgeprop_bedroom_labels(path, district) -> dict[tuple[str, str], str]`
  keyed by (display_project, band_key). Projects are display-grouped with the same
  `display_project()` rule as transactions (generic landed split by street; in practice
  landed projects won't appear in EdgeProp condo data).

## Page structure (per district)

Unchanged: header, caveat banner (gains one sentence explaining bedroom labels are
EdgeProp-derived estimates).

New: a tab bar with 6 tabs — `All · ≤50 · 50–70 · 70–100 · 100–130 · >130 sqm`. Each tab is a
`<section>` containing:

1. That band's **summary strip** (district median PSF by year within the band, top-3 /
   bottom-3 growth among that band's projects) — same `district_summary` logic on the band
   subset.
2. That band's **project table** — identical columns to the current table, computed only from
   the band's transactions, with one extra `Bedrooms` column (band tabs only, not `All`)
   showing the `≈nBR` label or blank. Projects with 0 transactions in the band are omitted.

Tab switching is plain JS show/hide (all tabs pre-rendered; page stays self-contained).
Default active tab: `All`. Per-tab tables keep click-to-sort.

## Code changes

All in `models/gen_district_private_comparison_html.py` (existing functions unchanged unless
listed):

- New constants `AREA_BANDS`, and helper `band_of(area_sqm) -> str`.
- New `load_edgeprop_bedroom_labels(path, district) -> dict`.
- `generate()`: loads bedroom labels; builds `per_band = {key: (rows, summary)}` by filtering
  the merged DataFrame per band and reusing `aggregate_projects` + `district_summary`;
  passes `per_band` and labels to `render_html`.
- `render_html(district, per_band, bedroom_labels) -> str` — signature changes (the old
  `(district, rows, summary)` form is replaced; its callers are `generate()` and tests).
- Missing/empty EdgeProp file → empty label dict; pages still render (blank bedroom cells).

## Testing

Extend `tests/test_gen_district_private_comparison.py`:

- `band_of` boundary cases (50 → `le50`, 50.1 → `50to70`, 130 → `100to130`, 130.5 → `gt130`).
- Label learning: ≥3 rows with ≥70% modal share → `≈3BR`; 2 rows → no label; 3-way split → no label;
  unparseable `Bedrooms` values ignored.
- `generate` produces tabs: output contains all 6 tab labels; a project appearing only in one
  band is present in that band's section and absent from another band's section; bedroom label
  appears in the band table.
- Existing render test updated to the new `render_html` signature.
- Integration test (D17/D27 real data) extended: asserts band tab labels present.

## Out of scope

- No changes to loaders' price/area behaviour or the backfill window rule.
- No bedroom inference beyond the mode-share rule (no area-based guessing).
- No per-band pages or cross-district views.
