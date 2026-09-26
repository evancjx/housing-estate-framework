# Property Analysis Directory — Design

**Date:** 2026-09-26
**Status:** Approved design; implementation plan pending
**Scope:** GitHub Pages build (`scripts/build_pages_site.py`, `index.html`, `sg_estate/reporting/`)

## Problem

The Pages build injects one card for every latest property analysis into the home page's report
grid. There are now **563 cards**, and they sit in the same grid as the ~20 flagship reports: the
district comparisons, the Tampines guide and the loan planners. The flagship reports are buried,
and the page gets heavier with every new analysis.

## Who uses it and how

Readers usually **know the project name** they want (confirmed with the user on 2026-09-26).
Browsing by area is secondary.

The home page's "What are you researching?" finder already does name search. It suggests projects
from the public project index and offers "Dedicated project research is available" when an
analysis exists, because the generated routes are injected at
`/* GENERATED_PROPERTY_ANALYSIS_PROJECT_ROUTES */`. **No new search box is added to the home
page.**

## Goals

1. The home report grid shows the flagship reports plus **one** summary card for property analyses.
2. Finding a named project's analysis from the home page takes one search and one click.
3. Every latest analysis can be browsed by postal district on a dedicated directory page.
4. Existing analysis URLs (`property-analysis-<date>-<slug>.html`) do not change.

## Non-goals

- Planning-area grouping, price or size filters, and sorting controls.
- Changing the analysis pages, their markdown sources, or how they are generated.
- Retiring the existing "Individual property analyses" directory report (a mixed-market analysis
  page). It stays; the new page supersedes it in practice, and whether to remove it is decided
  separately.

## Design

### 1. Home page (`index.html`)

- `inject_property_library` stops generating the per-analysis cards. The
  `GENERATED_PROPERTY_ANALYSIS_CARDS` marker is replaced by **one card**:
  - tag "Property analyses";
  - heading "Browse N project analyses by district", where N is the number of latest analyses;
  - body text that includes the newest capture date, for example "Latest captured 26 Sep 2026.
    Each is a dated snapshot.";
  - the link `property-analyses.html`.
- The "Property analyses" filter chip (`data-filter="analysis"`) is removed, because one card
  does not need its own chip. The summary card keeps `data-kind="analysis project"`, so it still
  appears under the "Projects" chip, and its `data-search` includes "property analysis" so the
  library search still finds it.
- **The finder shows analyses directly.** The finder's project list gains an `analysis` field for
  projects that have a latest analysis: `{path, date_label}`.
  - A suggestion for such a project shows an "Analysis · <date>" badge.
  - Once a project with an analysis is chosen, the route note reads
    "<a>Open the <date> analysis</a>" first, followed by the existing report or explorer
    guidance.
  - Search matching, keyboard behaviour and the other routes are unchanged.
- **District tab.** When the chosen district has at least one analysis, the route note adds
  "<a>N property analyses in D<nn></a>", linking to `property-analyses.html#d<nn>`.

### 2. Directory page (`property-analyses.html`)

The page is generated at build time into the site output, in the same way as the analysis pages.
It is not a root file. It uses the shared `assets/research-shell.css` and
`assets/research-shell.js`.

- **Header:** "N property analyses", the latest capture date, and one sentence saying each
  analysis is a dated, point-in-time snapshot. The sentence links back to the home page.
- **Search input:** filters rows as the user types.
  - It matches the case-insensitive project name, the district code (`d27`, `27`) and the
    district name ("sembawang").
  - It shows "M of N analyses" and opens every district section that has a match.
  - It hides district sections and rows with no match.
  - Enter opens the analysis when exactly one row matches.
- **Stage chips:** one chip per distinct `market_stage` among the latest analyses, each labelled
  with its count (`Resale 383`, `New launch 27`, and so on). `unverified` is labelled
  "Stage not verified", never hidden. Chips combine with the search.
- **District sections:** one `<details id="dNN">` per postal district D01–D28 that has at least
  one analysis, in numeric order.
  - The summary shows the code, the district name and the count, for example
    `D27 · Sembawang · Yishun · 23`.
  - All sections start collapsed. A URL fragment `#dNN` opens that section on load.
  - A last section `<details id="unknown">`, "District not known", lists analyses with no district.
- **Rows:** one per latest analysis.
  - Contents: the project name as the link, the stage, and the capture date.
  - Rows are sorted by project name within a section. No summary text is shown.
- **Without JavaScript:** every section and link works. Search and chips are progressive
  enhancements.

### 3. Data

- **District** comes from the finder's public project index: `build_project_catalog()` plus
  `add_report_projects()`. An analysis joins it on the whitespace-normalised, upper-cased project
  name.
  - The finder and the directory therefore always show the same district.
  - Analyses with no joined district go to "District not known". On 2026-09-26 that is 14 of 563.
- **District names** move into a Python constant, `DISTRICT_NAMES` in
  `sg_estate/reporting/property_analysis.py`.
  - The home page keeps its existing JavaScript `DISTRICT_NAMES` object.
  - A test asserts the two are identical, following the repo's doc–code consistency approach, so
    they cannot drift apart.
- **Catalogue:** the directory page is added to the merged report catalogue, which the build
  already extends with analysis entries. It uses `kind: "property-analysis-directory"`, so the
  site's link validation and catalogue tests cover it.
- **Output name:** the build fails if `property-analyses.html` collides with an authored root file
  or a catalogue path, matching the existing collision checks for analysis pages.

## Error handling

- **A latest analysis whose name joins no district** is listed under "District not known". It is
  never dropped or given a guessed district.
- **Zero analyses:** the summary card and directory page are still produced. The card says
  "No project analyses published yet", and the page shows an empty state.
- **Missing or broken inputs** (the project list or the transactions CSV): the build fails, as it
  does today in `build_project_catalog`.

## Testing

The tests extend `tests/test_pages_site.py` and `tests/test_property_analysis_pages.py`, using the
existing fixture style.

1. The built `index.html` contains no per-analysis cards. It contains exactly one summary card, and
   that card's count equals the number of latest analyses.
2. The "Property analyses" filter chip is absent. The summary card is found by the library search
   term "property analysis".
3. `property-analyses.html` contains each latest analysis exactly once, linking to its existing
   `output_path`.
4. An analysis whose project has district 27 appears inside `<details id="d27">`. One with no
   district appears inside `<details id="unknown">`.
5. Section summaries show the correct counts, and sections appear in numeric order.
6. The Python `DISTRICT_NAMES` equals the JavaScript `DISTRICT_NAMES` object parsed out of
   `index.html`.
7. The finder's project list includes `analysis` for projects with a latest analysis, and omits it
   otherwise.
8. The existing site-link validation passes for the new page. Every analysis link resolves.

Run `make smoke` before and after.

## Risks

- **Search engines and bookmarks** that pointed at the home page's per-analysis cards lose those
  anchors. Analysis URLs themselves are unchanged, so no page 404s.
- **The directory page grows linearly** with analyses: one short row each, about 60 KB at 563
  rows. Rows stay compact; pagination is not needed at this scale.
