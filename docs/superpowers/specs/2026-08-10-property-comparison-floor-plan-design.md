# Property Comparison and Floor-Plan Comparison — Design

**Date:** 2026-08-10
**Status:** Backlog; research complete, implementation deferred pending a viable rights-cleared image-comparison pilot
**Builds on:** `private_project_comparison_table.html` and the existing project-transaction reports
**Implementation plan:** [Property Comparison and Floor-Plan Comparison Implementation Plan](../plans/2026-08-10-property-comparison-floor-plan.md)
**Publication policy:** [Floor-Plan Publication, Provenance and Calibration Policy](../../FLOOR_PLAN_PUBLICATION_POLICY.md)
**Safe pilot:** [Floor-Plan Comparison Safe-Pilot Plan](../plans/2026-08-10-floor-plan-comparison-safe-pilot.md)

**Controlled vocabulary:** [Floor-Plan Layout Glossary](../../FLOOR_PLAN_LAYOUT_GLOSSARY.md)

## Executive decision

The product should not try to become another general-purpose property-listing portal. Its strongest
position is a **provenance-backed Singapore project intelligence database** whose flagship feature is
a **verified, variant-complete floor-plan library with two-to-four-plan comparison**.

There are two priorities at different layers:

1. **P0 delivery gate — trusted data and publishing rights.** Establish immutable project and plan
   identities, field provenance, controlled layout vocabulary, source-terms authority, revision
   history, scale calibration and granular image-use rights.
2. **P1 customer-facing feature — floor-plan comparison.** Let a buyer find every disclosed layout
   variant, compare two to four variants, understand material differences and reach appropriately
   matched transaction evidence.

The synthetic P1 interface may be built in parallel, but P0 must precede any public real-project
metadata, outbound source link or image. It is not acceptable to build a polished viewer on copied
portal images, uncertain plan identities or assets whose acquisition, storage, hosting and exact
browser transformations have not been recorded as permitted.

## Problem

The current private-project explorer is useful for discovering projects and comparing Access,
Schools, Price, Transactions and Estate Context. Its row grain is still one project, so it necessarily
mixes bedroom types, layout variants, floors and sale states. That is appropriate for discovery but
insufficient for answering unit-level questions such as:

- Does this two-bedroom have one or two bathrooms?
- Is the kitchen enclosed and ventilated?
- How much of the stated strata area is balcony, private-enclosed space or void?
- Are two plans with the same bedroom count and area actually different?
- Which achieved transactions are valid candidates for this layout?
- Can two drawings be compared at a reviewed common-relative scale?

The main Singapore portals already cover most broad discovery needs. Reproducing those features
would add operating cost without creating a clear reason to use this site. Structured, comparable
and fully sourced floor-plan evidence is the largest missing layer and unlocks later layout-aware
transaction, household-fit and ownership-economics features.

## Research method and limitations

The research reviewed publicly accessible pages as at 2026-08-10 from 99.co, PropertyGuru,
EdgeProp and Stacked Homes; official Singapore guidance from URA, BCA, CEA and IPOS; broader buyer
research; and qualitative Singapore user discussions.

The findings have four important limits:

- Portal pages and commercial entitlements change. The matrix records observed public capabilities,
  not a permanent feature guarantee.
- Stacked topic frequency is an editorial-pattern review, not measured traffic or search demand.
- Reddit and PropertyGuru questions expose concrete pain points but are not representative surveys.
- The NAR buyer survey is a United States baseline. It is directional evidence for the importance of
  property details and floor plans, not Singapore-specific demand measurement.

Product priorities below therefore combine evidence with an explicit product judgment. They should
be updated after moderated prototype testing and real usage analytics.

## What property-comparison users are trying to decide

| Decision question | Evidence users look for | Product response |
|---|---|---|
| Is the record real and current? | Verified project facts, source date, revision and correction path | Display provenance and freshness at field or record level |
| Can I compare like with like? | Same project/type/size, recent transactions, tenure, floor and sale state | Publish match basis, sample size and unresolved differences |
| Does the home work for us? | Exact layout, room relationships, outdoor/non-living area, storage, kitchen and ventilation | Preserve every plan variant and expose structured layout attributes |
| Is the location suitable? | MRT, primary schools, amenities, commute and future changes | Link to the existing Access, Schools and Estate Context lenses |
| Can we afford and exit it? | Quantum, PSF, loan, CPF, duties, fees, rental and resale evidence | Link layouts to transaction cohorts and the existing loan timeline planner |
| What is uncertain? | Missing plans, small samples, inferred fields and conflicting sources | Use explicit status, confidence and no-data states; never silently fill gaps |

A broader 2025 buyer survey found that photos, detailed property information and floor plans were
among the most useful website features. Floor plans were useful to 57% of internet-using buyers in
that study. This supports their importance, while the survey's United States scope means it should
not be treated as a Singapore market-size estimate. See the [NAR 2025 Home Buyers and Sellers
Generational Trends Report](https://cms.nar.realtor/sites/default/files/2025-03/2025-home-buyers-and-sellers-generational-trends-report-04-01-2025.pdf).

The qualitative Singapore signal is consistent: buyers describe missing floor plans as a reason to
discard a listing and ask for recent, physically comparable transactions rather than a district-wide
average. See the [PropertyGuru buyer question on missing floor plans](https://www.propertyguru.com.sg/question/351308/dear-agents-why-do-so-many-hdb-resale-listings-not-have-a-floor-plan-why-do-so-many-listings-not-have-a-proper-video-not-a-photo-collage-but-actual-walk-through-why-do-some-listings-not-have-even-proper-photos-or-no-photos-at-all-we-buyers-are-paying-6-digits-for-a-property-and-you-are-getting-4-5-digits-worth-of-commission-please-post-listings-that-have-a-higher-standard-than-the-ones-on-carousell-floor-plans-are-the-basic-information-when-i-wish-to-buy-an-apartment-if-it-s-not-even-present-i-just-close-the-ad-immediately-regards-sincere-but-annoyed-buyer)
and a [SingaporeFi discussion of condo comparables](https://www.reddit.com/r/singaporefi/comments/17o53bw/what_formula_or_strategy_do_you_use_to_determine/).

Accuracy is a trust feature, not a cosmetic detail. CEA has taken enforcement action where property
details sourced from a third party were not verified; the project should preserve the evidence used
for every material fact. See [CEA's case on failure to verify property details](https://www.cea.gov.sg/docs/default-source/module/dcCases/failure-to-verify-accuracy-of-information-obtained-from-third-party-property-listing-portal-failure-to-conduct-title-search-to-verify-ownership-of-property-%28pdf-355kb%29.pdf).

## Common Stacked Homes topics

Stacked's recurring subject matter is a useful map of the questions that remain after a buyer has
found a listing:

| Topic | Recurring decision need | Implication for this product |
|---|---|---|
| New-launch, condo, HDB/BTO and landed reviews | Understand a project in context rather than read brochure claims | Provide a project evidence page with sources and caveats |
| Property picks by budget or constraint | Find the cheapest, largest or best-located options that meet a real constraint | Support transparent filters, not a universal rank |
| Profitability, rental yield and exit analysis | Judge performance by bedroom/type and holding period | Link exact or candidate layouts to defensible transaction cohorts |
| New launch versus resale; old versus new | Understand trade-offs beyond headline PSF | Keep age, tenure, sale state and layout efficiency visible |
| Buyer case studies and advisory questions | Decide whether to buy, sell, hold, upgrade or right-size | Add household-relative lenses and ownership economics later |
| Homeowner stories and lived experience | Surface noise, maintenance, usability and regret that structured data misses | Add sourced qualitative evidence as a separate future layer |
| Policy and finance | Understand CPF, BSD/ABSD/SSD, loans, lease decay and affordability | Deep-link to the loan timeline planner and dated policy notes |
| Floor-plan and layout critique | Understand wasted space, ventilation, privacy, storage and room relationships | Make structured plan comparison the flagship feature |

Relevant entry points include [Stacked Homes](https://stackedhomes.com/),
[Property Picks](https://stackedhomes.com/category/property-picks/),
[Homeowner Stories](https://stackedhomes.com/category/homeowner-stories/),
[Stacked Pro](https://stackedhomes.com/category/pro/) and the
[new-launch directory](https://new-launches.stackedhomes.com/). The new-launch directory already
uses layout concepts such as dumbbell, dual-key, study, yard, store, private lift, ventilated rooms
and enclosed kitchens. That vocabulary is a useful starting taxonomy, but each attribute still needs
a defined evidence and review rule.

## Common features across 99.co, PropertyGuru and EdgeProp

The following is a capability-level comparison, not a quality score:

| Capability | 99.co | PropertyGuru | EdgeProp | Product consequence |
|---|---|---|---|---|
| Sale/rent discovery, filters and maps | Present | Present | Present | Commodity; do not rebuild listing operations first |
| Project facts and unit mix | Present | Present | Present | Use as a usability benchmark, not an unsourced input |
| Floor plans and site/elevation material | Present with variable project coverage | Present with variable project coverage | Present with variable project coverage | Coverage and variant completeness remain an opportunity |
| Transaction history and price trends | Present | Present | Present | Differentiate through explicit cohort/match basis |
| MRT, schools and nearby amenities | Present | Present | Present | Existing project explorer already covers the core need |
| Mortgage/affordability and valuation tools | Present | Present | Present | Maintain and link the existing planner; not the next flagship |
| Saved searches, alerts and favourites | Present | Present | Present | Useful later, but requires accounts and ongoing listing operations |
| New-launch/editorial content | Present | Present | Present | Research content supports the evidence layer but is not the database |
| Side-by-side project/unit analytics | Available, often through research or agent tooling | Available through Unit & Project Insights | Available through Compare/Pro tooling | Consumer-grade exact-layout comparison is still not the default experience |

Examples reviewed include [99.co sale search](https://www.99.co/singapore/sale),
[99.co Researcher](https://www.99.co/singapore/property-agent-hub/researcher),
[PropertyGuru Unit & Project Insights](https://www.agentofferings.propertyguru.com.sg/help-centre/elevate-your-strategy-with-data-insights/data-and-insights-tools/unit-project-insights/)
and [EdgeProp Compare Projects](https://www.edgeprop.sg/analytic/compare).

The important gap is not whether a portal can display a floor-plan image. It is whether a buyer can
establish that all variants are present, distinguish same-area variants, compare drawings on a valid
scale, inspect source/revision status and understand which transactions may belong to each variant.

### Why project + bedroom count + area is not an identity

The [99.co Clavon project page](https://www.99.co/singapore/condos-apartments/clavon) illustrates
the problem clearly. It lists BP1, BP2 and BP3 as separate two-bedroom Premium plans, each at 764
sq ft. It also distinguishes CP1 and CP2 at the same bedroom count and area. A record keyed only by
project, bedrooms and area would collapse real variants and could attach a transaction to the wrong
layout.

The minimum durable hierarchy is:

```text
Project
└── bedroom category
    └── marketing family
        └── exact plan variant
            └── document revision
                └── block / stack / floor assignment
                    └── exact, probable or candidate transaction links
```

## Feature priority

This prioritisation uses buyer decision impact (30%), differentiation (25%), gap in the current
product (20%), feasibility/readiness (15%) and future reuse (10%). Scores are product judgments,
not survey results.

| Candidate | Weighted score / 5 | Priority decision |
|---|---:|---|
| Verified floor-plan library and comparator | 4.55 | P1 flagship after the P0 trust gate |
| Layout-linked achieved transactions | 4.15 | P2; depends on canonical plan identities |
| Household-specific fit and shortlist | 3.90 | P3; keep persona-relative |
| Qualitative lived-experience evidence | 3.80 | Later research layer |
| Ownership-economics integration | 3.40 | P3; much of the calculator foundation exists |
| Live listings and alerts | 3.40 | Later; commoditised and operationally costly |
| More MRT/school comparison | 3.05 | Maintain; already substantially covered |

The immediate product sequence is therefore:

1. Synthetic-only contracts and two-to-four-plan interaction prototype.
2. Counsel-approved access, metadata, link and rights workflow plus immutable identities.
3. Real metadata coverage matrix, followed by separately licensed images and calibrated views.
4. Confidence-labelled transaction cohorts.
5. Household fit, ownership economics, stack/site mapping and broader coverage.

## Product boundaries

- The private-project explorer remains the broad project-discovery surface.
- Floor-plan pages are project/unit diagnostics. They are not a Provision component.
- Layout suitability is household-relative and must not become one universal “best layout” score.
- Estate-level Provision, persona-relative Liveability and private Value remain separate evidence
  lenses. HDB and private Value universes remain separate.
- The public product must not expose access-controlled exact-unit records.
- Absence is explicit, but orthogonal concepts are not collapsed: coverage is complete, partial,
  missing or conflicting; visual availability is hosted, link-permitted, metadata-only or mixed.

## Floor-plan comparison experience

### 1. Library and project coverage

`floor_plan_library.html` should support:

- search by project, street, postal code and stable project ID;
- filters for bedroom count, bathroom count, area band and reviewed layout attributes;
- a project coverage matrix showing expected and captured variants by bedroom/family;
- source document, revision, verification and rights status;
- a “compare layouts” action from each compatible plan and from the private-project explorer;
- a missing-plan/correction route with the affected project, variant and source prefilled.

“Complete” must mean reconciled to a named source-document revision, not merely that at least one
plan exists for each bedroom count.

### 2. Comparator

`floor_plan_compare.html` should compare two to four plan variants and provide:

- side-by-side cards with synchronized pan and zoom;
- a common-scale mode only when all selected revisions are reviewed and calibrated;
- optional overlay only when common-scale eligibility passes;
- rotation and mirror controls without collapsing the underlying variant identities;
- a structured difference table for type, bedrooms, bathrooms, total area, disclosed area
  components, study/flex space, yard, store, kitchen, ventilation, private lift and dual key;
- definitions and evidence tooltips from the versioned floor-plan glossary rather than free-text
  marketing adjectives;
- source, revision, verification and calibration badges on every plan;
- an accessible text/table alternative to the drawings;
- a canonical, shareable URL that pins ordered plan/revision pairs so a brochure correction cannot
  silently change a saved comparison.

Total stated floor area alone must never be used to claim architectural same scale. Common-scale
and overlay modes require a reviewed affine pixel-to-metre calibration bound to each exact published
rendition hash, machine-readable anchors/error metrics and permitted transformations. A crop,
resize or new source revision invalidates eligibility until its rendition is calibrated. An
uncalibrated selection remains useful side by side but must say “not shown to a common scale”.

### 3. Transaction evidence

Public URA transactions normally do not reveal enough exact-unit information to identify a single
layout. The interface must persist and display the match method rather than silently promoting a
candidate:

| Match status | Required evidence | Public wording |
|---|---|---|
| `exact` | Authorised exact unit/stack, official stack-to-plan assignment and compatible revision/area | Exact layout match |
| `probable_unique` | Stable project, sourced bedrooms and compatible area leave one current plan | Unique candidate, not exact |
| `candidate_set` | Two or more current variants remain compatible | Candidate layouts |
| `bedroom_only` | Only bedroom evidence is defensible | Bedroom cohort only |
| `size_only` | Only area evidence is defensible | Size cohort only |
| `unmatched` | No compatible plan | No layout match |
| `conflict` | Sources disagree or violate a contract | Withheld pending review |

The first public release should link to bedroom-and-area cohorts. Exact matching is a later feature
and must not bypass the restricted-data rules in `scrapers/README.md`.

## Canonical data model

### Stable identity

Add a reviewed `private_project_registry.csv` before the floor-plan tables. Its immutable row stores
only the opaque ID and creation evidence. Source names, normalized names, slugs, street, district,
planning area and status are append-only assertions/events because they can change. Keep aliases
and namespaced legacy report/query IDs in separate append-only maps. Layouts must never be keyed on
a raw project name or on bedroom count plus area.

The registry should reuse the existing transaction identity tuple `(project, street, district,
planning_area)` and the repository's single-sourced alias strategy. Ambiguous duplicate names must
fail review rather than be merged heuristically.

### Research inputs

All committed inputs belong in the `research` zone of `data/catalog.json` and receive executable
contracts in `sg_estate/contracts.py`. The following is a logical data model, not a direction to
commit confidential rows: real source-terms snapshots, non-public source locators, licensor and
authority evidence, grants, private object records, deletion obligations and blocked hashes remain
in an access-controlled register outside Git. The repository holds their schemas, synthetic test
fixtures and public-safe projections only.

| Dataset | Purpose | Essential fields |
|---|---|---|
| `private_project_registry.csv` | Stable project identity | stored `project_id`, created date and immutable creation reference only |
| `private_project_assertions.csv` plus project events | Mutable project description | names, slug, street, district, planning area and status as sourced assertions/tombstones |
| `private_project_aliases.csv` / `private_project_legacy_ids.csv` | Alternate names and backwards-compatible shared URLs | alias or producer-namespaced legacy ID, project ID, source, effective date and superseding link |
| `floor_plan_sources.csv` plus source events | Source-document provenance | immutable source/project/publisher/document/retrieval/fingerprint fields and append-only verification events; page locators belong on evidence rows |
| Private source-terms snapshots plus terms events | Lawful acquisition/use gate separate from copyright | access method, terms version/fingerprint, storage/extraction/factual-use/link permissions, target path scope and next review date |
| `floor_plan_variants.csv` plus identity events | Logical plan identity | stored `plan_id`, project ID, created date and immutable creation reference only; sourced relationships and retirement/split/merge events live separately |
| `floor_plan_assertions.csv` plus assertion events | Field-level provenance | subject, predicate ID, typed value or selected term revision, assertion basis, source/page/evidence locator, extraction method/version, confidence, superseding assertion and ordered review events |
| Predicate, term, revision, event, label, alias and relation CSVs | Controlled comparison vocabulary | stable facet IDs, controlled-value term IDs, selected definition revisions, cardinality/value schema, allowed assertion bases, evidence/absence rules and scoped aliases |
| `floor_plan_expected_variants.csv` | Defensible completeness denominator | source revision, expected plan/type code and reconciliation state |
| `floor_plan_revisions.csv` plus revision events | Immutable source/document history | revision, plan, source/page/source-asset ID+hash, creation, superseding revision, change reason and review/selection events |
| Public-safe `floor_plan_assets.csv` / `floor_plan_renditions.csv`; private originals stay outside Git | Separate bytes from transformations | content-addressed asset rows plus parent/rendition asset IDs, exact hashes, dimensions, versioned transform chain and acyclic graph |
| Private rights grants, asset junction and rights events | Publication authority | owner/licensor/authority, grant hash, granular operations, origins/providers/scope/term and ordered activation/dispute/withdrawal events |
| `floor_plan_calibrations.csv` plus calibration events | Scale evidence for exact rendition bytes | authoritative pixel-to-metre affine matrix, coordinate system, real/pixel anchors, algorithm/tolerance versions, error and ordered review events |
| `floor_plan_stack_assignments.csv` | Official applicability | project, block, stack, floors, plan, mirror/rotation, source and confidence |

Generated outputs are:

- `data/outputs/floor_plan_coverage.csv` — expected/captured counts and independent coverage status;
- `data/outputs/floor_plan_transaction_matches.csv` — transaction candidate sets, match method,
  evidence and algorithm version;
- deterministic public search manifest and metadata shards under `site/assets/floor-plans/`;
- a minimal public entitlement projection containing disposition, permitted client operations,
  attribution and effective dates, but no licensor, contract, internal URL, private key or reviewer
  reference.

### Data invariants

- `project_id`, `plan_id`, `revision_id`, `source_id`, `asset_id`, `rendition_id`, `rights_id` and
  `calibration_id` are stored opaque identities, immutable and unique.
- Existing identity, source, assertion, revision, grant and event rows cannot be changed/deleted;
  CI compares primary keys and immutable-field allowlists with an explicit merge-base SHA.
  Corrections add a superseding row or event.
- A logical plan variant may have many revisions; revisions are never overwritten.
- The acyclic revision graph uses `supersedes_revision_id` for topology; ordered revision events
  select no more than one reviewed publication head for a plan at an explicit timestamp. There is
  no mutable `is_current` flag or duplicate supersession event.
- Every material displayed field resolves to at least one reviewed field-level assertion. Conflicts
  render `conflict`, not an arbitrary winner.
- Vocabulary definitions constrain meaning but never prove that a plan has a feature. Assertions
  pin stable predicate IDs and, for categorical values, the selected term revision plus their own
  evidence basis.
- “Complete” reconciles captured plans against a named expected-variant source inventory.
- Official type code, marketing family, bedrooms and bathroom counts remain separate fields.
- Source square metres and square feet are preserved. Conversion is derived and must stay within a
  declared tolerance; it never overwrites a disclosed source value.
- Internal, balcony, PES, void, roof and air-con-ledge areas are `official_disclosed` or null in the
  first release. OCR does not publish inferred area components automatically.
- Mirror and rotation relationships may link plans but do not erase distinct stack/exposure records.
- Exact and perceptual hashes identify duplicate assets; potential duplicates require human review.
- Crop/resize/format changes create a rendition, not a plan revision. Calibration binds to the exact
  rendition hash and is invalidated when those bytes or transforms change.
- Derived layout features carry their input assertion IDs, algorithm version, confidence and
  reviewer status.
- Public catalog generations pin a content-hashed vocabulary release. Labels/translations never
  enter joins or shared URLs, and deprecated meanings never reinterpret historical assertions.
- A public asset requires lawful source access/retention, an active grant bound to the exact asset,
  and permission for every storage, publication, provider, browser and transform operation used.
- `metadata_only` records may prove that a variant exists without publishing an image or source URL.
  `link_permitted` adds only an approved ordinary source link and never an embed, proxy or cached
  copy.

## Source and rights strategy

Copyright permission and source access/portal terms are independent. A licence from a copyright
owner does not override the terms governing acquisition, storage or linking, and access to a source
does not grant reproduction rights. Full source-document hashing is performed only when lawful
acquisition and private retention permit keeping the bytes; otherwise the record contains a
reviewed reason and weaker bibliographic fingerprint.

Preferred evidence order:

1. rights-cleared official developer brochure or architect/developer submission;
2. rights-cleared developer or appointed project-team upload;
3. authorised official-plan access where the permission permits the intended publication;
4. agent/community submission with a rights declaration and human review;
5. OCR or inferred suggestions, withheld from official status until verified.

Do not scrape and republish floor-plan images from 99.co, PropertyGuru, EdgeProp or other portals.
Their pages are research benchmarks, not a licence. IPOS explains that internet availability does
not itself grant permission and recommends recording the scope of a licence in writing; see
[IPOS copyright ownership and commercialisation](https://www.ipos.gov.sg/about-ip/copyright/ownership-and-commercialisation/).

URA's show-unit guidance makes official plans valuable verification evidence: unit plans must be
drawn to scale, tied to approved building-plan references and include strata-area breakdowns. It
does not grant this project republication rights. Bibliographic reference: URA, *Housing Developers
(Show Unit) Rules — Items to Note*,
`https://www.ura.gov.sg/-/media/Corporate/Guidelines/Developers/HDSUR--Guidelines_Mar-2018.pdf`.

BCA's Plan Purchase System is eligibility-controlled and fee-based. Purchasing access is not
assumed to include a public redistribution licence. Rights authority and data authority must
therefore be tracked separately for every source. Bibliographic reference:
`https://www.bca.gov.sg/pps/`.

An ordinary source link is not automatically allowed either: the current URA and BCA Terms of Use
require prior permission to link. Use `metadata_only` until the source's terms or written permission
support `link_permitted`. Bibliographic references: `https://www.ura.gov.sg/terms-of-use/` and
`https://www1.bca.gov.sg/terms-of-use/`.

## Storage and publication architecture

The database is metadata-first and static-site compatible:

```text
reviewed CSV metadata + contracts
              │
              ▼
floor-plan catalog builder ──► coverage + transaction-match outputs
              │
              ├──► small public manifest + project metadata shards in Git/Pages
              └──► rights-gated, hash-versioned image derivatives in object storage/CDN
                                      │
                                      ▼
                    library / project view / 2–4-plan comparator
```

- Canonical validation and matching orchestration belongs in `sg_estate.application`; source and
  object-storage access belongs in `sg_estate.adapters`; report generation belongs in
  `sg_estate.reporting`.
- Root HTML remains a generated artifact. Shared JavaScript and CSS live under `site/assets/`.
- The public generation manifest contains lightweight search and coverage fields. Per-project
  metadata is loaded on demand from content-addressed project JSON under
  `site/assets/floor-plans/generations/<catalog_sha256>/projects/<prefix>/<project_id>-<content_sha256>.json`
  rather than embedding the entire database in one HTML file.
- Every shard uses UTF-8 canonical JSON sorted by immutable IDs: sorted keys, compact separators,
  no NaN, and a final newline. The catalog hash covers schema/as-of plus the ordered shard hashes
  and excludes itself.
- A build writes `site/assets/floor-plans/generations/<catalog_sha256>/...`, validates the complete
  generation and writes a small top-level `current.json` pointer last. The Pages builder copies
  only the selected generation into a fresh deployment artifact, avoiding unreliable replacement
  of a non-empty directory.
- Licensed originals and derivatives use immutable object keys such as
  `/<project_id>/<revision_id>/<rendition_id>/<sha256>.webp`. CORS is restricted to the site origin.
- Browser code receives complete builder-approved URLs. It cannot construct asset paths. CDN and
  source-link origins are allowlisted and the new pages use a restrictive Content Security Policy.
- The repository keeps checksums and metadata, not the large image library or licence contracts.
- Permission is operation-specific. Hosting does not imply browser resizing, viewport cropping,
  thumbnailing, re-encoding, calibration, compositing, opacity changes, annotation or overlay.

GitHub Pages has a recommended 1 GB source/published-site limit and Git LFS objects are not served
by Pages. An image database should therefore use object storage/CDN rather than grow the repository.
See [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
and [Git LFS limitations](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage).

## MVP

First validate the interface with original synthetic plans. Then pilot five to ten current-launch
condominium projects only after counsel approves the factual metadata workflow and the required
source/access terms and asset rights are obtained. Include at least one complex project with
multiple same-area variants.

The MVP must provide:

- every distinct plan in a named brochure revision;
- stable IDs, exact type codes, bedroom/marketing families, areas, baths and reviewed attributes;
- source, page, revision, retrieval date, lawful fingerprint/hash state, rights and verification
  status;
- project-level completeness status;
- search and filters for project, bedroom, area and basic attributes;
- two-to-four-plan comparison, calibrated common-scale mode where eligible, and shareable URLs;
- source badges, accessible tabular fallback and mobile/keyboard completion;
- missing-plan/correction reporting;
- links to bedroom-and-area transaction cohorts without claiming exact layout identity.

### MVP non-goals

- Islandwide completeness.
- Copying competitor assets or creating a live-listing/agent-lead marketplace.
- A universal project or layout score.
- Exact transaction-to-layout inference from area alone.
- Automatic publication of OCR measurements or AI-generated room dimensions.
- 3D furnishing, renovation simulation or user accounts.
- Public exposure of exact-unit data without a separate rights and privacy review.

## Success and release measures

### Data and trust

- 100% of published images have active hosting rights and recorded provenance.
- 100% of pilot variants reconcile to a named source-document revision.
- 100% of variants have stable unique IDs; revisions never overwrite history.
- No common-scale claim appears without a reviewed calibration basis.
- No inferred field is labelled official.
- At least 99% metadata accuracy in a double-reviewed field sample.

### Usability and performance

- At least 80% of moderated pilot users can find and compare specified variants within two minutes.
- Mobile and keyboard users can complete the same core comparison task.
- Images are lazy-loaded; public pages target p75 LCP below 2.5 seconds.
- Comparison URLs survive reload and reproduce order, selected variants and display mode.
- Usage analytics measure project search, second-plan selection, completed comparison, share/export
  and correction submission without collecting sensitive financial inputs.

### Operations

- By the tenth pilot project, median full-project ingestion is at most four analyst-hours,
  excluding rights negotiation.
- Coverage, rights expiry, revision status, corrections and ingestion time are visible internally.
- A correction is acknowledged within one business day and resolved or explicitly status-labelled
  within two business days.

## Decision after the pilot

Scale to 25–50 projects only if the pilot demonstrates complete source acquisition, manageable QA,
valid asset rights, acceptable performance and clear comparison usage. The next investments should
then be stack/site-plan assignments, developer submissions, household-specific fit and ownership
economics—not a generic listing marketplace.
