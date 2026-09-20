# Individual project property analyses

The requested deliverable is one analysis per project, not a regional report.
The September 2026 publication contains 553 separate project targets, including
20 EC-origin developments, plus four separate future land-site assessments.
The canonical directory is
`property_analysis/2026-09-20-individual-project-analyses.md`.

Each report uses the existing property-analysis renderer and automatic catalog.
It contains the subject's evidence and a purchase conclusion: achieved formats,
exact registered areas, historical and monthly activity, developer returns,
qualified owner comparisons, rental evidence, purchase/exit arithmetic,
location, supply context, risks and conditions for proceeding. Sparse and
no-transaction projects receive an explicit evidence-limit assessment; historical
redevelopment predecessors do not receive a fictitious current buying case.

## Sources and generation

The frozen batch is committed as `data/raw/property_research/2026-09-20.zip`.
It includes the original URA exports, scope decisions, derived ledgers,
editorial notes, individual project CSVs and a file-hash manifest. Source rows,
including identical masked transaction signatures, are retained. No full unit
identity or bedroom count is inferred from URA area.

Restore the evidence to the ignored working directory and reproduce offline:

```sh
rtk proxy python3 -m zipfile -e data/raw/property_research/2026-09-20.zip data/runs/regional-property-analysis/2026-09-20
rtk proxy python3 models/build_regional_transaction_batch.py
rtk proxy python3 models/build_regional_property_evidence.py
rtk proxy python3 models/build_individual_project_profiles.py
rtk proxy python3 models/build_individual_property_analyses.py
rtk proxy python3 scripts/package_property_research.py
rtk proxy python3 scripts/build_pages_site.py --out data/runs/regional-property-preview-site
```

The site build itself only needs the committed Markdown, source archive and
assets; it never depends on `data/runs/` or network credentials. It publishes the
archive under `research/2026-09-20/source.zip`, extracts its evidence beside it,
and provides `research-data.html?path=research/2026-09-20/<file>.csv` as a static,
searchable table. Localhost links are not used by published reports.

`enrichment/individual_editorial_notes.json` contains separately authored
project-specific judgments for 55 projects: the union of developer-return
projects, EC-origin developments and previous dossiers, plus Forett. Remaining
project conclusions use their own transaction depth, formats, cost hurdles,
qualifying peer evidence and source limitations. The generated narrative does
not claim manual inspections, current executable quotations or personalized
investment suitability.

`individual_report_manifest.json` reconciles all 553 project names to unique
source files and permanent publication URLs. The report generator also exports each project's
transactions, cohorts, owner comparisons, developer returns and rental series
under `individual/<project-slug>/`. Generated rows preserve source occurrences.

Existing project names and slugs remain stable. The authored same-day Canberra
Crescent report is preserved byte-for-byte, giving 552 new project pages plus
that existing page. Older snapshots remain at their permanent URLs and are
linked from the new reports. Four additional future sites receive separate
pages; final project names, licensed unit counts, home prices and TOP remain
unverified unless officially announced.

## Material analytical controls

- New Sale, Sub Sale and Resale remain distinct, as do exact source tenures and
  EC/private groups. Bulk disposals are excluded from individual-home metrics.
- Qualified owner comparisons require five observations on each side of the
  same narrow area window; known lease starts and project distances have
  explicit limits. Missing geometry is not represented as a nearby peer.
- Current rental yield is never filled with stale rent. Project rental and
  sale-cohort aggregates are not represented as matched-unit achievable yield.
- Official developer totals, launched unsold homes and unreleased homes are
  distinct. A no-sales zero price is displayed as not published, not S$0 psf.
- The inverse entry-cost test uses the subject's median area at a peer's
  current achieved PSF as a hypothetical exit. It is not a valuation or a
  promise that either entry or exit can be executed.
- Verified EC block TOP dates can identify a restricted stage; exceptional
  transactions do not establish unrestricted resale or rental availability.
- Rail distances use dated station snapshots and representative project
  points. They are straight-line distances, not walking routes or school
  admission distances. Regional plans receive no automatic price uplift.

## Publication and validation

The directory is published at
`https://evancjx.github.io/housing-estate-framework/property-analysis-2026-09-20-individual-project-analyses.html`.
The earlier regional comparison remains supporting material and does not
substitute for the individual reports. CI builds the complete static artifact
and rejects missing same-site report links or evidence selected by viewer URLs.
