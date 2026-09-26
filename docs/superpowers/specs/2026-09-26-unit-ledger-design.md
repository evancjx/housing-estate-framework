# Project Unit Ledger — Design

**Date:** 2026-09-26
**Status:** Approved design; implementation plan pending
**Builds on:** the Canberra Crescent Residences transaction page built interactively on 2026-09-26
(`canberra_crescent_transactions.html`, scratch build script) and the
`data/runs/canberra-unit-xref/2026-09-20/` research snapshot.

## Purpose

Given one private residential project name, produce a local, provenance-labelled record of every
transaction with an exact date and, where evidence allows, a unit number. Present it as:

1. a sortable, filterable transaction table; and
2. a site sales view: a grid for each block, with floors as rows and stacks as columns, showing each
   unit's achieved prices.

The user runs this one project at a time through the assistant to research units. It is research
output. It is not a Provision or Liveability input and must not be wired into any scoring pipeline.

## Requirements

- Works for **new launches** (mostly New Sales, often with a public agent unit chart) and **completed
  or resale projects** (many units sold more than once, usually with no unit chart).
- **URA Data Service `PMI_Resi_Transaction` is the backbone** for the last five years. The run fails
  if URA is unavailable.
- **Full history:** transactions older than URA's five-year API window are included from EdgeProp
  and PropertyNoob, and flagged `not verified against URA API`.
- **Unit layout:** taken from a supported unit chart when one is given. Otherwise it is derived from
  every unit identified in sales, and units that never transacted appear as unknown gaps.
- **Site-view cell:** latest sale price, $psf, sale type and year, with a sale count (`x3`). Hovering
  lists every sale for the unit. A toggle switches the grid between the latest and the first price.
- Every unit number, date and price carries its source and how it was matched. Nothing is guessed
  silently. Anything unresolved is labelled `Ambiguous: <candidates>` or `Not found`.

## Success criteria

1. Re-running on Canberra Crescent Residences from the 2026-09-26 captures reproduces **all 348 unit
   and exact-date assignments** of the interactively built page. Any intended difference is listed
   and approved.
2. A run on The Poiz Residences, a resale-heavy project with existing PropertyNoob captures, completes.
   Its README reports coverage: rows with dates, rows with units, pre-window rows, and ambiguous rows.
3. `make smoke` passes. New unit tests cover every matching rule without network access.

## Non-goals

- Landed property, HDB, and projects without URA private transaction records.
- Chart templates other than the singmap-hosted agent-site template used by
  `canberracrescent.isaacyee.com`.
- Asking prices, rental data, nett prices, and floor-plan images. Plan type codes are text labels
  only; no images are copied, which is consistent with `docs/FLOOR_PLAN_PUBLICATION_POLICY.md`.
- Publishing. Outputs never go to GitHub Pages or any hosted location.

## Architecture

A new package, `scrapers/unit_ledger/`, split into three stages.

```text
scrapers/unit_ledger/
├── __main__.py      CLI: run | rebuild
├── fetch.py         network acquisition; writes raw captures only
├── sources.py       parse raw captures into normalised transaction/unit frames
├── match.py         pure matching; no I/O, no network
├── layout.py        units.csv from chart or derived from matched sales
├── render.py        index.html from transactions.csv + units.csv
└── template.html
scrapers/propertynoob_sales.py   moved from data/runs/propertynoob-sales/2026-09-20/ (with its tests)
```

Reuse, without changing behaviour:
- `scrapers/ura_pmi_api.py`: token, `fetch_transactions`, `flatten_project_transactions`.
- `scrapers/edgeprop_condo_apartment_playwright.py`: `scrape` for one project (`--match <slug>`),
  and `discover` when the project is missing from `data/raw/edgeprop/edgeprop_condo_apartment_projects.csv`.
- `propertynoob_sales.parse_sales_html`, which fails loudly when the table schema changes.

Following `docs/ARCHITECTURE.md`, nothing in `sg_estate/domain` may import this package, and the
package does not write to `data/inputs/` or `data/outputs/`.

## Command line and run directory

```text
python3 -m scrapers.unit_ledger run --project "<URA project name>" \
    [--chart-url URL] [--recent-sales FILE.csv]
python3 -m scrapers.unit_ledger rebuild <run_dir>      # offline, from raw/ only

data/runs/unit-ledger/<project-slug>/<YYYY-MM-DD>/
├── raw/             fetch.json, ura.json, edgeprop*.csv, propertynoob.html, chart.html, recent_sales.csv
├── logs/            EdgeProp scraper attempt logs and discovery output (never read by rebuild)
├── transactions.csv one row per transaction (schema below)
├── units.csv        one row per physical unit (schema below)
├── provenance.json  source URLs, capture UTC times, SHA-256 of each raw file, counts, warnings
├── README.md        coverage summary and warnings, in plain language
└── index.html       self-contained page (table + site view)
```

`data/runs/` is ignored by Git, so unit-level third-party records are never committed. This follows
`docs/DATA_GOVERNANCE.md`, which says not to commit licensed exact-unit records. Running `run` twice
on the same day replaces that day's directory only after the new run completes successfully.

`raw/fetch.json` records the project name, capture time, the URL and status of each source, and any
fetch warnings. `rebuild` reads it, so a run can be rebuilt with no network access.

`raw/` may hold several EdgeProp captures (`edgeprop.csv`, `edgeprop_<label>.csv`). They are combined
as a **multiset union**: a row value seen k times in one capture and j times in another counts
max(k, j) times. This is needed because EdgeProp pagination drops different rows on different passes.
For Canberra, the three available captures (341, 340 and 336 rows) combine to exactly URA's 348.

`--recent-sales` is a CSV with the columns `date,unit`. It holds a developer's recently sold list
that the user pasted. It carries dates and unit numbers only, never prices.

### Migration of the Canberra page

`canberra_crescent_transactions.html` in the repository root is untracked and never committed. Root
HTML is the GitHub Pages publication surface, so after the regression run succeeds the file is
deleted and replaced by
`data/runs/unit-ledger/canberra-crescent-residences/2026-09-26/index.html`.

## Normalised records

`transactions.csv` (one row per transaction):

| column | meaning |
| --- | --- |
| `txn_id` | stable id: `ura-<n>`, `ep-<n>` (pre-window EdgeProp), or `pn-<n>` (PropertyNoob only) |
| `origin` | `URA` or `Pre-window` |
| `sale_date` | exact date, `YYYY-MM-DD`; blank if unknown |
| `sale_month` | `YYYY-MM` (always present) |
| `block`, `unit` | e.g. `57`, `#05-30`; blank if unresolved |
| `floor_level` | URA floor band, e.g. `01-05` |
| `area_sqm`, `area_sqft`, `bedrooms`, `unit_type` | size and layout; `unit_type` comes from the chart only |
| `price`, `psf` | gross transacted price in SGD, and price ÷ sqft |
| `type_of_sale` | `New Sale`, `Sub Sale`, or `Resale` |
| `tenure` | as published |
| `unit_source` | how the unit was matched (see rules below) |
| `date_source` | the sources behind the date, plus any conflicting values |
| `conflict` | free-text description of any disagreement between sources; blank if none |

`units.csv` (one row per physical unit): `block`, `unit`, `floor`, `stack`, `area_sqft`, `bedrooms`,
`unit_type`, `layout_source` (`chart` or `derived`), `status` (`sold` / `sold_pre_window_only` /
`sold_pending_ura` / `available` / `unknown`), `sale_count`, `first_txn_id`, `latest_txn_id`, `note`.
Cells that are empty in the grid (such as Canberra's Blk 51 level 1) are absent from `units.csv`;
the renderer draws them as "no unit".

## Matching rules

Matching works per transaction, not per unit, so a unit may have any number of sales. The rules run
in this order. Each row records the rule that resolved it.

1. **URA → EdgeProp.** Match on price, area, month and floor band. For area, EdgeProp's sqm (three
   decimals, e.g. 112.97) is rounded to the precision URA publishes for the project (whole sqm for
   Canberra: 113). The match gives the exact date, block and floor.
   - EdgeProp rows dated before URA's earliest month in this pull become `Pre-window` rows.
   - When several EdgeProp rows match one URA row, use them as a set if they are identical, otherwise
     record them as a conflict.
2. **→ PropertyNoob.** Match on exact date, price, sqft and floor from the unit token. The match gives
   the stack.
   - PropertyNoob has no block numbers, so the block comes from EdgeProp.
   - The stack must exist in that block according to the layout. In derived layout mode, block and
     stack pairs are learned from rows where both sources agree.
   - A date mismatch of up to 3 days between EdgeProp and PropertyNoob is allowed only when price,
     sqft and floor all agree exactly and the result is unique. Such rows are labelled
     `Published (date ±N days)`.
   Within step 2, **identical sales are matched as a set**: N rows identical on date, price, sqft,
   floor and block share exactly N free PropertyNoob candidates.
   **Rows EdgeProp missed.** EdgeProp pagination drops rows on busy launch days: Springleaf
   Residence lost 213 of its 876 launch-month sales. A URA row with no EdgeProp record takes
   PropertyNoob's unit and exact date when month, price, sqft and floor band agree, the stack exists
   in exactly one block, and the group of identical URA rows has exactly as many PropertyNoob
   candidates. It is labelled `Published (PropertyNoob; no EdgeProp record…)` with date source
   `PropertyNoob (no EdgeProp record)`. Groups with more candidates than sales stay unresolved.
3. **Leftovers.** The rules below are applied repeatedly until no further progress. Elimination runs
   only when no stronger rule makes progress.
   - **Determined by block, floor and size** (chart only, any sale type). Only one chart unit on
     EdgeProp's block and floor has this size. This is the strongest leftover rule because it rests
     on URA's own record.
   - **Unit chart sold date + EdgeProp block/floor** (chart only, New Sale). Exactly one chart-sold
     unit on that block and floor, of that size, has a chart sold date within 7 days of the sale date
     and no New Sale matched yet. This generalises the 2026-09-20 masked-listing inference.
   - **Recent-sales list + EdgeProp block/floor** (New Sale). Match on month, sqft, block and floor.
     The block comes from the layout. A unit token that exists in more than one block is skipped.
   - **By elimination.** Only for `New Sale` rows, and only when a chart exists. Exactly one
     chart-sold unit of that size is still without a New Sale: on the same block and floor when
     EdgeProp gave them, otherwise in the same floor band. Never used for resales or sub-sales.
4. **Unresolved.** The row is labelled `Ambiguous: <candidates>` or `Not found`.

The 2026-09-20 PropertyStory "masked listing" inference is **not** carried over. If the Canberra
regression shows that any assignment depended on it, implementation stops and the evidence goes back
to the user before any rule changes.

**Source precedence** for conflicting values: URA > EdgeProp > PropertyNoob > chart > recent-sales
list. Conflicts are shown, never dropped. If the chart says a unit is available but a URA sale is
matched to it, the unit is sold, with a note (as with Canberra's 55 #04-23).

**Built-in check:** for each run, count the rows whose URA-derived block, floor and size leave exactly
one possible unit in the layout. The count is reported in the README and on the page, so the user can
see how much rests on third-party stack numbers.

## Layout

- **With a chart:** the chart grid gives block, floor, stack, sqft, bedrooms, plan type and status.
  Bedrooms for each transaction come from the chart by size.
- **Without a chart:**
  - Units come from every matched transaction, with blocks, floors and stacks taken from those matches.
  - Bedrooms come from EdgeProp.
  - The grid spans the lowest to highest floor observed in each block. Floor and stack slots never
    seen in any sale are drawn as `unknown`, and the README says so.
  - Unit types are blank.
- A unit's `status` is `sold` if any URA-origin transaction is matched to it, and
  `sold_pre_window_only` if only pre-window transactions are.

## Output page

A single self-contained HTML file with no network dependencies. It supports dark mode and must not
cause horizontal page scroll at phone width. It keeps the current Canberra page's behaviour and adds
the following.

- **Table:**
  - New columns: `Sale type` and `Origin`. Pre-window rows are shaded.
  - Filters: bedrooms, size, and sale type (New / Sub / Resale).
  - Clicking a column header sorts by it.
  - Summary line: count, median price and median $psf of the rows currently shown.
- **Site view:**
  - One grid per block.
  - Each cell shows the plan type (when a chart exists), sqft, the price shown, $psf, sale type and
    year, and `xN` when N > 1. Hovering lists each sale.
  - A toggle switches the whole grid between latest and first price.
  - Colours: sold (URA price) / sold (pre-window price only) / sold, pending URA / available /
    unknown (derived layout only) / no unit.
- **Banner:** any source that failed or was skipped, and how many rows lost dates or units as a result.

## Error handling

| Condition | Behaviour |
| --- | --- |
| `URA_ACCESS_KEY` missing, or the token or any batch fails | Exit non-zero; no run directory is kept |
| Project not found in the URA result | Exit non-zero; print the five closest URA project names |
| EdgeProp project URL unknown | Try `discover --match`; if still unknown, continue without EdgeProp and warn |
| EdgeProp, PropertyNoob or chart fetch fails | Continue; record a warning in `provenance.json`, the README and the page banner |
| `--chart-url` returns a page that is not the supported template | Exit non-zero with a message saying the template is unsupported |
| A parser meets an unexpected schema | Exit non-zero; parsers never return partial data |
| A URA row has no EdgeProp size, and its sqm maps to several chart sizes | Exit non-zero with the conflicting values |

Secrets: the URA key is read only from the environment and is never printed or written to the run
directory. Captured HTML contains no credentials, and no EdgeProp login state is used.

## Testing

All tests in the default `make smoke` gate run without network access.

1. `tests/test_unit_ledger_match.py` uses small synthetic frames and covers each rule:
   - a single New Sale;
   - a resale of an already matched unit (two transactions, one unit);
   - a lapsed booking resold at a different price;
   - identical sales matched as a set;
   - elimination refused for a resale;
   - ambiguous and not-found outcomes;
   - pre-window rows;
   - a ±N-day PropertyNoob date tolerance that is unique, and one that is not.
2. `tests/test_unit_ledger_sources.py` covers the chart parser and the EdgeProp and URA
   normalisers, using minimal synthetic HTML and CSV that contain no real unit records.
3. The existing PropertyNoob parser tests move with the module to `tests/test_propertynoob_sales.py`.
4. `tests/test_unit_ledger_canberra_regression.py` rebuilds from
   `data/runs/unit-ledger-regression/canberra-crescent-residences/raw/`, a location that a live `run`
   can never overwrite. It asserts that the 348
   (unit, sale_date, price) triples equal a golden CSV stored next to the raw captures. The test
   **skips** when those local files are absent, as they will be in CI, so the regression runs only
   on the user's machine.
5. `tests/test_unit_ledger_render.py` renders a synthetic run and asserts: the row count, the sale
   count in a cell, the latest/first toggle data, the banner for a missing source, and that no
   `__PLACEHOLDER__` token is left in the page.

## Risks

- **Source drift:** EdgeProp, PropertyNoob and the chart template can change without notice. Parsers
  fail loudly instead of degrading, and the raw captures in each run allow offline diagnosis.
- **PropertyNoob freshness:** for Canberra, the page stopped at 2026-04-03. Recent resales may
  therefore rely on EdgeProp block and floor without a stack, and show as `Ambiguous`. That is
  reported, not hidden.
- **Terms of use:** fetching is limited to the pages a logged-out browser can see, at the existing
  scrapers' rate. Outputs stay local.
