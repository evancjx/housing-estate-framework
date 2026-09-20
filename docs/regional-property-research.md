# September 2026 regional property research

The local research batch covers identified condominium, apartment and EC-origin
projects in Tampines, Bedok, Canberra, Lakeside / Jurong and Bukit Timah. The
authored conclusions are in
`property_analysis/2026-09-20-regional-condo-and-ec-comparison.md`; the generated
all-project evidence register uses the same publication contract. Neither
changes the estate Provision, Liveability or Value models.

## Frozen inputs and scope

Restore the committed `data/raw/property_research/2026-09-20.zip` archive to
`data/runs/regional-property-analysis/2026-09-20/` for an offline rebuild.
It contains the 13 original URA transaction exports, original-field ledger,
scope crosswalk, source notes, 553 main-scope project names and separate wider
Sembawang context. The working directory is ignored; the frozen source archive
is committed and published with a file-hash manifest.

Keep repeated public transaction rows: the public signature is not a unique
unit identity. Four bulk transactions are retained in the ledger and excluded
from single-home metrics. September 2026 is partial; the common comparison
window is September 2025 through August 2026.

The enrichment adds the committed official URA 2026Q2 project rental snapshot,
matched OneMap project points and a newly captured September 2025–August 2026
official developer-sales API extract. `enrichment/provenance.json` records
input hashes, source paths and assumptions. `enrichment/regional_context.json`
records dated primary-source infrastructure, supply and EC facts.

## Reproduction

Run from the research worktree containing those frozen inputs:

```sh
rtk proxy python3 models/build_regional_property_evidence.py
rtk proxy python3 -m pytest tests/test_regional_property_evidence.py tests/test_regional_research_economics.py tests/test_property_analysis_pages.py -q
rtk proxy python3 scripts/build_pages_site.py --out data/runs/regional-property-preview-site
```

The evidence builder does not fetch fresh data. It regenerates the quantitative
appendices and all-project register; it does not overwrite the authored
regional purchase analysis. Review narrative figures after changing inputs.

The output includes 864 separate sale cohorts with price/rent/cost evidence,
130 qualifying owner comparisons across 79 subject cohorts, monthly transaction
counts, official developer balances and 553 project assessments. The register
selects each project's most observed cohort, breaking count ties by sale type,
source tenure and size band; other cohorts remain available in the CSV.

## Analytical boundaries

Peer comparisons retain region, tenure group and EC origin. Resale and Sub Sale
controls stay separate. Both sides require five records within the same area
window around the subject cohort median, using the larger of 3 sqm or 5%.
The subject remains within its original size cohort. Known 99-year lease
commencements must be within ten years; known project distances must be at
most 2 km. Missing geometry is explicitly a regional comparison. Up to three
controls are selected by proximity, then sample depth when distance is missing.
Floor, facing, building age, layout, condition and incentives are not adjusted.

Rental yields are ratios of separate project-rent and sale-cohort aggregates,
not matched-unit achievable yields. Missing current-quarter rent remains
missing. Developer `units_avail` is total project units: unsold total, launched
unsold and unlaunched stock are separate calculations, always dated.

Purchase scenarios use historical medians as hypothetical entries, current
BSD, S$5,000 acquisition costs and 2.5% selling costs. They omit financing,
holding costs and rental receipts. Exits are conditional on applicable SSD,
EC MOP and eligibility rules; no exit date or price growth is forecast.

## Publication

The new Markdown reports are automatically discovered by the existing site
builder. `mixed market` describes a multi-project report spanning stages and
does not merge underlying transaction categories.

The canonical reports use permanent GitHub Pages URLs. The site build publishes
the frozen evidence and static CSV viewer alongside the reports. The individual
project directory is the primary deliverable; the regional report and register
are supporting comparisons. See `docs/individual-property-research.md` for
archive restoration and full reproduction commands.
