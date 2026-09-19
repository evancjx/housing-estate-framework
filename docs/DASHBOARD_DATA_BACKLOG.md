# Dashboard and Data Reliability Backlog

**Prepared:** 13 August 2026  
**Capacity assumption:** one engineer, ten working days per two-week block  
**Product boundary:** preserve separate Provision, persona-relative Liveability,
and tenure-segmented Value views. Do not introduce a universal estate or project
ranking.

This backlog starts after the August 2026 dashboard audit and its first
implementation slice. The repository already has a shared browser JSON loader,
visible project-index fallback and retry, capability-aware landing routes,
responsive shared report navigation, a generated data-status summary, bounded
HTTP retries in the main first-party ingesters, and build-time transaction-shard
reconciliation. The items below deliberately do not repeat that completed work.

## Delivery rules

- Treat one day as one focused engineering day, including focused tests and
  documentation. Estimates are planning sizes, not deadlines.
- GitHub issues are the interrupt lane described below. Planned work displaced
  by an issue rolls forward in priority order; the sprint does not silently add
  overtime or skip verification.
- Keep external refreshes staged. Network retrieval does not authorize automatic
  promotion of changed model inputs or outputs; reviewed framework and data
  gates still apply.
- Never infer a retrieval date from a file modification time or a report build
  date. Unknown provenance stays unknown.
- Keep all browser data same-origin. Do not make the public dashboard call URA,
  data.gov.sg, OneMap, LTA, or EdgeProp directly.
- Every ticket is complete only when `make pages-check` and its focused tests
  pass. Run `make smoke` at the end of each week and both two-week blocks.

## Daily GitHub issue interrupt lane

This lane has priority over every ticket in both blocks. At the start of each
Singapore calendar day, and again before declaring that day's work complete:

1. Query open issues in `evancjx/housing-estate-framework`, newest or most
   recently updated first, and compare their creation/update times with the last
   completed sweep.
2. Triage new or materially updated issues in this order: security, privacy,
   provenance, model correctness, or data-loss risk; broken publication or CI;
   user-blocking dashboard/data retrieval; then other reproducible defects.
3. Take the highest actionable issue through reproduction, a minimal safe fix,
   focused regression coverage, and the applicable repository gates before
   returning to planned work. Keep only one non-critical issue in progress at a
   time.
4. Target same-day completion. If credentials, missing evidence, an external
   service, an ambiguous product decision, or a required review makes that
   unsafe, update the issue the same day with the evidence, exact blocker, next
   action, and owner; do not mark it resolved or fabricate a workaround.
5. Resume the displaced backlog ticket after the issue is closed or has a clear
   externally owned blocker. Critical issues may pre-empt an issue already in
   progress.

Issue fixes must preserve the framework boundaries above. A GitHub report does
not authorize blending Provision and Liveability, mixing HDB/private Value, or
promoting unreviewed refreshed data. Record the sweep time, issues inspected,
action taken, and verification result in the daily work update so the next run
has an auditable checkpoint.

**Daily checkpoint (13 August 2026):** the 01:43 opening query and the 02:26,
02:58, 03:33, 05:05, 06:01, 07:02, and 07:11 follow-up/closing queries all returned no
open issues. No issue work was required. Both two-week blocks and the
end-of-block repository gates are complete with evidence recorded below.

## Block 1 — committed first two weeks

### Week 1: make freshness and transaction acquisition trustworthy

#### DASH-101 — Source receipt and freshness contract v2 (2 days)

**Status:** Complete — 13 August 2026. Source-receipt schema v2, staged producer
sidecars, optional canonical-source aggregation, schema-v3 review-gated run
manifests, honest `data-status.json` mapping, catalog corrections, and explicit
staging destinations are implemented. Unknown historical evidence remains
null; no live source refresh or unreviewed data promotion was performed.

**Verification:** `make smoke` (540 passed, 62 skipped, 1 deselected), `make
pages-check`, `make pages-build`, and `python3 -m pytest -m integration` (5
passed) all passed on 13 August 2026.

**Outcome:** every refreshed dataset can say when and how it was retrieved,
what period it covers, whether cache/fallback data was used, and what bytes were
accepted.

**Work**

- Add a versioned source-receipt schema under `sg_estate/contracts.py` with
  `dataset_id`, authority, source URL, retrieved time, coverage start/end, row
  count, SHA-256, cache state, fallback state, and validation status.
- Have networked ingesters write receipts beside staged outputs; do not backfill
  unknown historical timestamps.
- Aggregate receipts into the transactional pipeline run manifest and generated
  `data-status.json`.
- Correct any `data/catalog.json` producer/authority entries discovered while
  wiring the receipts.

**Acceptance**

- A fresh, cached, fallback, and offline run are distinguishable in machine data.
- Missing coverage or retrieval fields serialize as `null`, never as the current
  date.
- Malformed receipts fail staging before promotion.
- Tests cover schema validation, manifest aggregation, and the unknown-date case.

#### DASH-102 — Report-to-data-family mapping and freshness UI (1 day)

**Depends on:** DASH-101 contract shape.

**Status:** Complete — 13 August 2026. All 26 authored reports and 28 generated
property analyses have validated evidence-family mappings. The shared shell
renders build-injected, source-specific currency under HTTP and `file://`, with
separate estate-model, canonical private-transaction, rail, finance-assumption,
and point-in-time market-research families. Private data uses the last complete
month, rail coverage is not mislabeled as `Data through`, report generation is
accepted only from an explicit label, and unknown evidence stays `Unknown`.

**Verification:** `make smoke` (552 passed, 64 skipped, 1 deselected), `make
pages-check`, `make pages-build`, and `python3 -m pytest -m integration` (5
passed) all passed on 13 August 2026. The focused browser/responsive matrix also
passed 113 tests with 4 environment skips.

**Outcome:** each report exposes the currency of the evidence it actually uses,
instead of showing only a page-generation date.

**Work**

- Add validated `data_families` to each base entry in `site/reports.json` and to
  generated property-analysis catalog entries where applicable.
- Render compact `Data through`, `Last checked`, and `Generated` labels in the
  shared report shell or canonical templates.
- Link the labels to the relevant entries in `data-status.json`; show `Unknown`
  where no receipt exists.

**Acceptance**

- The estate, private-project, rail, and finance report families each display
  the correct distinct status.
- A build date cannot appear under a `Data through` label.
- Catalog validation rejects unknown family identifiers.

#### DATA-103 — Fail-closed URA acquisition and completeness manifest (2 days)

**Status:** Complete — 13 August 2026. Both download paths now write exact-scope
partition attempt manifests, including explicit confirmed-empty versus failed
states. Ingestion reconciles and independently re-observes district, property
type, month, row, null, duplicate, invalid-row, hash, and receipt evidence into
a run-scoped candidate. Canonical replacement is an explicit reviewed,
rollback-safe CSV/receipt/acquisition-manifest promotion; the manifest is the
last commit marker. Direct canonical legacy writes are rejected, and missing
sale dates or project ages remain null under the executable Value model
contract.

**Evidence:** the focused acquisition/downloader/ingestion/pipeline/Value matrix
passed (130 tests in the final contract audit; 122 in the combined local gate),
including missing-partition, source-scope, tamper, equal-sum falsification,
rollback, orphan-sidecar, and null-control fixtures. `make smoke` passed with
618 tests and 64 optional skips; the integration marker passed 5 tests;
`make pages-check` validated 54 reports, 28 dated analyses, 3,477 projects, and
37 datasets. Python compilation and `git diff --check` passed. No live URA
acquisition was run and no refreshed data was promoted.

**Network/manual review:** implementation and fixture tests are offline; a live
URA run is network-dependent and its results require review before promotion.

**Outcome:** a partial district, property-type, or month download cannot silently
replace the canonical private-transaction layer.

**Work**

- Make API and Playwright download paths emit structured attempt results for
  every requested district/property-type partition.
- Add expected-versus-observed district, type, month, row-count, duplicate, and
  invalid-row checks before `scrapers/ingest_ura_raw.py` can publish.
- Remove synthetic fallbacks for missing sale dates or project ages; preserve
  missing values and explicit status instead.
- Stage the merged CSV and acquisition manifest, then promote them together only
  after reconciliation succeeds.

**Acceptance**

- A fixture with one missing district exits non-zero and leaves the prior
  canonical CSV unchanged.
- Unknown dates/ages remain null and are excluded or handled according to the
  executable model contract.
- Complete fixtures reconcile by district, property type, month, and total rows.

### Week 2: make publication atomic, lighter, and failure-tolerant

#### DATA-104 — Versioned, atomic transaction-shard publication (2 days)

**Depends on:** DATA-103 for authoritative source completeness metadata.

**Status:** Complete — 13 August 2026. The transaction manifest and all 64
shards now carry one deterministic SHA-256 dataset revision and publish under an
immutable revision directory. Generation stages and rereads the complete
bundle, validates exact schema, enumerations, membership, counts, paths, and
revision, then atomically promotes the directory and switches the root manifest
last. Prior revisions and legacy assets remain readable. The multi-project and
project-exit consumers request revisioned URLs, enforce the same exact contract,
and withhold all transaction results behind a reload action if generations do
not match.

**Evidence:** generator publication and failure-injection coverage passed 14
tests; the combined static DATA-104 matrix passed 68 tests; the two consumer
Playwright suites passed 7 tests. `make pages-check` validated the full 64-shard
bundle and the independently recomputed committed revision is
`349d8d2f29c8db4dfc6508f39767805d0d56158ce7774b2515b1e9c802f967ec`.
The full `make smoke` gate passed 642 tests with 66 optional skips and one
deselection. `git diff --check` and JavaScript syntax checks passed. No live data
refresh or canonical model promotion was performed.

**Outcome:** HTML and transaction shards cannot silently mix generations in a
browser cache or after an interrupted build.

**Work**

- Derive a deterministic dataset revision from the normalized manifest and
  shard contents.
- Store the revision in the manifest and every shard; have consumers request and
  validate it.
- Build shards in a staging directory, validate schema, membership, counts, and
  revision, then promote the complete set atomically.
- Keep the previous complete generation intact when generation or validation
  fails.

**Acceptance**

- Changing one transaction changes the revision deterministically.
- Old-page/new-shard and new-page/old-shard fixtures show a reload-required error
  rather than results.
- An injected write failure leaves the previous manifest and all shards usable.

#### PERF-105 — Externalize duplicated project catalogs and set budgets (2 days)

**Depends on:** DATA-104 revision support for cache-safe URLs.

**Status:** Complete — 13 August 2026. One immutable, deterministic project
catalog now unifies all 2,400 private-explorer records, the 2,307 named
comparison/transaction records, explicit per-tool capabilities, deduplicated
framework contexts, and the selected transaction revision. It publishes from a
validated staging directory and switches its root manifest last. The private,
two-project, multi-project, and exit tools inline only usable bootstrap records,
hydrate the same revisioned URL through the shared success cache, retain their
defaults on failure, and expose accessible Retry and local-HTTP guidance.
Explorer-only generic records cannot claim comparison or transaction evidence.

**Evidence:** initial HTML is 249,113 bytes for the private explorer, 38,051
bytes for the two-project comparison, 86,405 bytes for multi-project, and 22,877
bytes for project exit. The catalog contract/atomicity matrix passed 39 tests;
the combined static contract gate passed 105 tests; focused browser suites
passed 17 private, 2 two-project, and 8 multi/exit tests. `make pages-check`
validated all catalog and consumer references plus HTML/bootstrap/option budgets.
The full `make smoke` gate passed 687 tests with 70 optional skips and one
deselection. JavaScript syntax and `git diff --check` passed.

**Outcome:** interactive reports paint quickly without parsing multiple megabytes
of duplicate project records and `<datalist>` options.

**Work**

- Publish one compact, versioned project catalog used by the private explorer,
  two-project, multi-project, and exit tools.
- Inline only bootstrap metadata and default selections; load full project data
  through the shared browser loader.
- Remove duplicate datalist/project JSON payloads and render selection options on
  demand.
- Add build tests for raw HTML size and initial DOM-row budgets.

**Acceptance**

- Initial HTML is at most 750 KiB for the private explorer and 500 KiB for the
  multi-project and exit tools.
- Default selections remain usable while the full catalog loads, and a failed
  catalog request produces an accessible Retry state.
- The same catalog response is reused across tools under normal HTTP caching.

#### QA-106 — Runtime failure and accessibility release matrix (1 day)

**Depends on:** DATA-104 and PERF-105.

**Status:** Complete — 13 August 2026. The release matrix now covers malformed
embedded JSON, per-source manual retry, transaction revision mismatch, partial
source failure, overlapping stale requests, catalog failure, and `file://`
guidance. Busy regions always settle, successful sources stay visible, and
unavailable evidence is labelled rather than converted to zero. A manifest-
driven Chromium sweep builds the real Pages catalog and exercises all 54
authored/generated reports at 390×844 for document overflow, skip targets,
visible focus, mobile menu behavior, browser errors, and accessible table
scrolling.

**Evidence:** the focused injected-failure matrix passed 21 browser tests; the
embedded-data and canonical interaction matrix passed 31 tests; the shared
shell/static regression gate passed 166 tests with 4 optional skips. The mobile
sweep found and fixed a 406 px Katong overflow and upgraded 15 actual legacy
table scrollers with labelled keyboard-focusable regions; all 54 reports then
passed. The full `make smoke` gate passed 687 tests with 83 optional skips and
one deselection. JavaScript syntax and `git diff --check` passed.

**Outcome:** canonical reports have repeatable browser evidence for slow,
partial, malformed, and unavailable data at desktop and mobile widths.

**Work**

- Add Playwright cases for project-exit manual retry, corrupt embedded JSON,
  revision mismatch, delayed stale requests, and `file://` guidance.
- Add a manifest-driven 390×844 sweep for horizontal overflow, skip-link target,
  visible focus, mobile navigation, console errors, and table scroll containers.
- Ensure partial sources remain labelled and usable; unavailable data must never
  render as zero.

**Acceptance**

- Each injected failure ends with `aria-busy="false"` and an actionable message.
- Successful projects remain visible when another source fails.
- No canonical page has document-level horizontal overflow at 390 px.

## Block 2 — reserve next two weeks

Pull this block forward only after Block 1 acceptance is clean. The ordering
below is dependency-aware but tickets remain independently reviewable.

### Week 3: unify identities and harden the remaining source edges

#### DATA-201 — Canonical project identity and capability registry (2 days)

**Status:** Complete — 13 August 2026. A strict immutable identity registry now
reconciles all 2,400 full URA/project-tool identities, all 3,477 exact EdgeProp
source keys, reviewed geocodes, the 2,307-project transaction generation, and
authored/generated report histories into 3,609 stable records. The 1,209
name-only/report-only records cannot inherit achieved evidence. All three
reviewed URA↔EdgeProp aliases are single-sourced, and same-name projects use
distinct street/district routes. Landing search selects by registry ID, requires
explicit disambiguation, prefers the newest dedicated report, and otherwise
opens an exact achieved-evidence route or explains why none exists. Legacy
`projects.json` and name-keyed report maps are removed.

**Evidence:** the 28-test registry mutation/publication suite and the combined
landing/Pages suite (58 tests, 6 optional browser skips) passed. `make
pages-check` validated 54 reports, 28 dated analyses, and all 3,609 identities;
the 54-report 390×844 mobile sweep passed. The current immutable registry
revision is `771a82ca0e5c234ac04b4d6e26a0f7cdb41c24b651eec1794cb47692bb68a49f`.
No source data, geocode decision, or transaction generation was refreshed.

**Outcome:** EdgeProp names, URA projects, geocodes, transaction shards, and
dedicated reports resolve through one stable project identity without name-only
records masquerading as evidence.

**Work**

- Build a union registry with stable IDs, source aliases, district/street
  disambiguation, and explicit `explorer`, `comparison`, `exit`, and
  `dedicated_report` capabilities.
- Replace name-only routing maps and duplicated alias logic with the registry.
- Publish an honest route or `name_only` explanation for every indexed record.

**Acceptance**

- Every landing suggestion resolves to a supported destination or an explicit
  no-evidence state.
- Duplicate names in different streets/districts remain distinct.
- Registry aliases and capability coverage reconcile against every consumer.

#### DATA-202 — Transactional OneMap geocode cache (2 days)

**Status:** Complete — 13 August 2026. The OneMap checkpoint now merges the
complete existing identity map before each validated same-directory atomic
replacement, records acquisition/review hashes and retry state, uses the shared
bounded HTTP adapter, supports cache age, zero-network offline inspection, and
transient-only retry, and never replaces prior valid evidence after a failed
refresh. A single review gate now protects the explorer, school metrics,
Katong, Poiz, Canberra, district-pair, and identity-registry consumers.

**Evidence:** crash, serialization, fsync, replace, timeout, HTTP, schema,
offline, stale-cache, changed-match, review-hash, duplicate-identity, and
consumer-gating regressions passed. The final focused matrix passed 103 tests;
the broader affected consumer matrix passed 125 tests. The committed legacy
snapshot has 2,223 usable reviewed matches, 174 weak matches withheld, and
three missing identities. A read-only registry rebuild remained byte-equivalent
at revision `771a82ca0e5c234ac04b4d6e26a0f7cdb41c24b651eec1794cb47692bb68a49f`.
No network request, canonical CSV rewrite, dependent catalog regeneration, or
unreviewed promotion was performed.

**Network/manual review:** live geocoding is network-dependent; changed matches
must be reviewed before dependent reports are regenerated.

**Outcome:** an interrupted or rate-limited geocode run cannot truncate a valid
checkpoint or make transient failures permanent.

**Work**

- Merge existing and new results before each atomic checkpoint write.
- Record query, retrieved time, match score/status, response hash, retry state,
  and review status.
- Add bounded retries, cache age, explicit offline mode, and targeted retry of
  transient failures.

**Acceptance**

- Crash-injection tests preserve every pre-existing valid row.
- Offline mode performs no requests and reports stale/missing entries.
- Low-confidence or changed matches remain review-gated.

#### DATA-203 — Complete first-party HTTP/cache adoption (1 day)

**Status:** Complete — 13 August 2026. MOH hospitals, URA land use, LTA rail,
and the project geocoder now route individual requests through the shared
bounded adapter. MOH and URA land use have validated same-directory atomic
caches, configurable age limits, and strict zero-network offline modes. LTA
preserves its source-specific poll flow and pinned SHA-256 checks, while its
offline mode requires all four reviewed local inputs. An AST regression gate
now rejects direct transport clients anywhere under production `models/` and
`sg_estate/`; the remaining direct clients are explicitly scraper-scoped under
`SCRAPE-204`.

**Evidence:** the combined adapter, wiring, geocoder, MOH, URA, LTA, related
ingester, receipt, and architecture matrix passed 106 tests. Invalid refreshes,
cache write/replace failures, checksum mismatches, missing offline inputs, and
429/5xx/timeout behavior all have deterministic coverage. Direct CLI help,
Python compilation, and whitespace checks passed. No remote retrieval ran and
no canonical input or output was replaced.

**Outcome:** remaining MOH, URA-land-use, LTA-rail, and geocode downloads follow
one bounded policy while retaining source-specific checksum and review gates.

**Work**

- Migrate remaining direct `urlopen` calls to the shared adapter.
- Add atomic validated caches, maximum cache ages, and `--offline` behavior where
  an ingester owns cache files.
- Preserve LTA/URA pinned-byte verification; retries must not bypass checksum
  review.

**Acceptance**

- Repository search finds no first-party ingester bypass of the shared adapter.
- Timeout, 429/`Retry-After`, 5xx, stale-cache, offline, and checksum-mismatch
  paths have deterministic tests.

**Adjacent cache-policy debt (not part of this one-day transport-adoption
ticket):** HDB density, NEA air, and tree-canopy ingestion already use the
shared HTTP adapter, but their legacy cache writers still need atomic
validation, maximum-age controls, and explicit offline behavior. HDB upgrading
already validates and atomically replaces its cache, but still needs a maximum
age and explicit offline CLI contract. Track these as a separate cache-hardening
slice rather than silently expanding DATA-203.

### Week 4: make scrapes recoverable and heavy reports consistently fast

#### SCRAPE-204 — Recoverable EdgeProp and URA scraper generations (2 days)

**Status:** Complete — 13 August 2026. An exact `scrape-generation.v1`
contract now binds generation ID, requested scope, timezone-aware attempt
history, terminal status, immutable artifact hashes/counts, selected
partitions, and the reconciled candidate. Condo and landed scrapers use
URL-derived partition IDs, retry only pending failures, keep crash-orphaned
artifacts immutable, and accept positive rows only after a proved terminal
page/year boundary. URA adapts its existing exact DATA-103 partition evidence
into the same append-only checkpoint without weakening the four-batch,
confirmed-empty, reconciliation, or manual-review gates. Legacy output and
attempt-log files are never resume evidence.

**Evidence:** the shared contract/source-receipt/architecture matrix passed 127
tests; condo and landed workflow matrices passed 63 and 64 tests; the combined
URA generation/downloader/ingest/acquisition matrix passed 109 tests. Tests
cover zero/error/max-page partials, failed retry, crash after artifact write,
scope mismatch, tamper, mixed generation, deterministic candidate
reconciliation, and URA generic-to-DATA-103 evidence equality. Direct and
outside-working-directory CLI help, Python compilation, and whitespace checks
passed. No network/Playwright run occurred and no scraper output was promoted.

**Network/manual review:** implementation is offline-testable; live scraping
depends on site access and source terms and must not auto-promote results.

**Outcome:** empty/error attempts are never recorded as complete, and resume
cannot skip failed work or append incompatible generations.

**Work**

- Add generation IDs, retrieval timestamps, attempt status, requested scope,
  and content hashes to checkpoints.
- Resume only successful partitions; retry failures explicitly.
- Reconcile one complete generation before merging or promoting scraper output.

**Acceptance**

- Empty and failed fixture pages remain pending/failed, not complete.
- Resuming retries failures without duplicating successful rows.
- Mixed-generation input is rejected before canonical ingestion.

#### PERF-205 — Paginate or virtualize eager legacy ledgers (2 days)

**Status:** Complete — 13 August 2026. Katong, Canberra, Poiz unit-growth, and
landed dashboards now mount at most 100 relevant rows initially, reveal the
next 100 with focus transfer, reset paging when filters change, announce
visible/filtered totals, export the complete filtered set, and expand/restore
for print. Katong and Canberra keep all transaction rows in inert templates;
Poiz keeps all nine project ledgers in inert JSON and mounts only the active
project. D17, D18, D27, and D18–D26 were audited rather than needlessly
virtualized: their largest tables are small project summaries of 29–46 rows,
not eager transaction ledgers.

**Evidence:** the combined focused performance matrix passed 15 tests,
including real Chromium fixtures above 200 rows for focus, filters, full CSV
export, and print restoration. Real Katong and Canberra reports show 100 of
2,879 and 100 of 2,884 rows; Poiz holds 1,757 records across nine projects with
only 100 active rows; landed starts with 100 of 607 dashboard rows. The
district audit passed 23 tests and produced byte-identical offline
regenerations. All report dates were explicitly preserved (Katong/Canberra 8
August, Poiz 25 July, landed 8 July 2026); no source refresh occurred. Python
and JavaScript syntax and scoped whitespace checks passed.

**Outcome:** Katong, Canberra, Poiz, landed, and district research pages no
longer create thousands of table rows on first paint.

**Work**

- Move ledgers behind paginated or batched rendering while retaining complete
  filtered access and CSV export.
- Keep table headers, captions, provenance, sample counts, and print behavior
  accessible.
- Add initial DOM-node, interaction-latency, and mobile overflow budgets.

**Acceptance**

- No report initially renders more than 200 transaction rows.
- Filtering and showing the next batch preserve focus and announce result counts.
- The full filtered ledger remains downloadable and count-reconciled.

#### PUB-206 — Catalog-driven library history and URL-backed discovery (1 day)

**Depends on:** DATA-201 identity registry and DASH-102 data-family metadata.

**Status:** Complete — 13 August 2026. The merged catalog now generates the
whole landing library, category choices, evidence-family metadata, exact
report-capture date state, and dedicated single-district routes at build time.
Twenty-six authored reports and 28 dated analyses render as 52 primary cards
plus two older-snapshot history links, with every one of the 54 paths represented
exactly once. Only generated analyses sharing an exact `project_slug` are
grouped; authored research remains independently discoverable. Search,
category, explicit capture-date, and evidence-family state are shareable in the
URL, preserve unrelated query/hash state, and restore through Back/Forward
without fetching or reloading the catalog. `file://` continues to work because
the validated library is build-injected.

**Evidence:** the Pages/library contract suite passed 45 tests, including
wrong-latest/duplicate/timestamp failures, nested safe paths, catalog-only
addition, byte-idempotent injection, exact 52+2 path reconciliation, and a
registry route-ownership swap mutation. The landing browser suites passed 11
tests with no skips, covering URL Back/Forward, invalid queries, older-history
search, exact filters, static/file preview, focus, mobile overflow, and project
registry failure/retry. `make pages-check` and `make pages-build` validated 54
reports, 28 analyses, 3,609 identities, and 37 datasets. Two committed-index
injections produced identical SHA-256
`a6be618d7ca9f2c6aeef62dccb59c1eb01e44cdf8c4d93764113138bf5b4b4e8`.
JavaScript/Python syntax and whitespace checks passed.

**Outcome:** `site/reports.json` becomes the real publication source of truth,
including historical property snapshots, freshness filters, and shareable
library state.

**Work**

- Generate landing cards, route maps, categories, and grouped analysis history
  from the merged catalog rather than duplicated HTML constants.
- Keep every dated snapshot reachable while making the newest project capture
  the default.
- Persist report query/category/freshness filters in the URL.

**Acceptance**

- Every merged catalog entry has a discoverable card or grouped-history link.
- Adding a valid catalog entry requires no manual landing-page card edit.
- Back/forward navigation restores filters and search without reloading data.

## End-of-block verification

**Status:** Complete — 13 August 2026.

**Recorded final gate:** `make smoke` passed with 883 tests, 93 optional skips,
one snapshot deselection, and one existing pandas future warning. `make
pages-check` validated 54 reports, 28 dated analyses, 3,609 project identities,
and source status for 37 datasets. `make pages-build` produced the complete
54-report `_site`; the integration marker passed five tests. A final real-
Chromium canonical sweep passed all 54 reports at 390×844. Full whitespace
validation passed. The first smoke attempt exposed and then closed two
reproducibility regressions: the project-exit artifact was regenerated with its
unchanged 11 August as-of date, and a legacy analysis-only landing test was
migrated to the catalog-driven publication contract.

Commands recorded:

```bash
make smoke
make pages-check
make pages-build
python3 -m pytest -m integration
```

For network-dependent tickets, also attach the staged acquisition/source
manifest, reviewed input/output diffs, and the exact command used. Do not treat a
successful fetch as approval to promote model or scoring changes.

## Explicitly outside these four weeks

- A combined Provision/Liveability ranking or blended HDB/private Value score.
- Live third-party API calls from public report pages.
- Automatic promotion of refreshed infrastructure, transaction, or geocode data.
- Floor-plan image comparison without the rights-cleared pilot required by
  `TODO.md` and the floor-plan publication policy.
