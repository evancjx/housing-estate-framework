# Property Comparison and Floor-Plan Comparison Implementation Plan

**Status:** Backlog; do not start implementation until rights-cleared plan images are available for
a useful public comparison pilot. Metadata-only and bring-your-own-image experiences are not the
approved customer-facing MVP.

**Goal:** Deliver a rights-cleared, revision-safe floor-plan database and an accessible static-site
experience that lets a buyer find every disclosed variant in a pilot project and compare two to four
plans without implying unsupported scale or transaction precision.

**Architecture:** Keep public-safe reviewed metadata and executable contracts in the repository,
keep real source-terms/grant records in an access-controlled register, and keep licensed image
assets in hash-versioned object storage/CDN. A protected projector emits a minimal public
entitlement projection, small search manifest and on-demand metadata shards; separate library and
comparison pages publish through the existing GitHub Pages reporting system. Floor-plan evidence
stays outside the Provision scoring domain.

**Tech stack:** Python 3, pandas, `sg_estate.application`, `sg_estate.adapters`,
`sg_estate.reporting`, vanilla JavaScript, HTML/CSS, JSON metadata shards, object storage/CDN and
pytest/Playwright.

**Spec:** [Property Comparison and Floor-Plan Comparison — Design](../specs/2026-08-10-property-comparison-floor-plan-design.md)

**Publication policy:** [Floor-Plan Publication, Provenance and Calibration Policy](../../FLOOR_PLAN_PUBLICATION_POLICY.md)

**First delivery slice:** [Floor-Plan Comparison Safe-Pilot Plan](2026-08-10-floor-plan-comparison-safe-pilot.md)

**Controlled vocabulary:** [Floor-Plan Layout Glossary](../../FLOOR_PLAN_LAYOUT_GLOSSARY.md)

## Priority and delivery gates

The flagship feature is the **two-to-four-plan comparator**. Its prerequisite is the P0 trust layer:
rights, provenance, immutable identities, revisions and scale calibration.

| Milestone | Outcome | Exit gate |
|---|---|---|
| M0 — Trust foundation | Rights policy, identity registry, source-terms model, controlled vocabulary and schemas | Synthetic fixtures pass all contracts; seed-term coding meets its agreement gate; counsel clears the exact real-data workflow |
| M1 — Trusted pilot catalog | Reviewed metadata, coverage and public shards | Five to ten projects fully reconciled to named source revisions |
| M2 — Consumer MVP | Library, project coverage and two-to-four-plan comparison | Users can find and compare specified variants on desktop, mobile and keyboard |
| M3 — Evidence integration | Confidence-labelled transaction cohorts and explorer links | No candidate is presented as exact; match evidence and sample basis visible |
| M4 — Scale operations | Stack/site mapping, developer submissions and broader coverage | Rights, QA and ingestion effort remain within agreed operating targets |

Do not start real-project metadata, external-link or image publication before the relevant M0 legal
and source-terms gate. Synthetic records may exercise the whole interface. After counsel approves
the factual-use workflow, `metadata_only` records may validate coverage while image permissions are
pending. Add a source URL only when the exact target is separately `link_permitted`.

## Global constraints

- Do not scrape and republish portal floor-plan images.
- Do not acquire, retain or publish image bytes unless every intended operation is permitted.
- Treat source access/terms and copyright permission as separate gates; neither overrides the other.
- Do not store the image library, licence contracts or restricted exact-unit records in Git.
- Do not key a project or plan on a display name, bedroom count or area.
- Do not overwrite a brochure or plan revision.
- Do not claim common scale from total area. Require reviewed official scale or dimension
  calibration.
- Do not infer exact transaction-to-layout identity from public area/bedroom data.
- Do not publish free-text marketing adjectives as facts. Filters and comparator rows resolve to the
  versioned controlled vocabulary, with unknown and conflict visible.
- Keep Provision, Liveability and tenure-segmented Value separate. Do not create a universal plan or
  project score.
- Every committed `data/inputs/*` file must be registered in `data/catalog.json`.
- Root HTML is generated; canonical report code belongs under `sg_estate.reporting`.
- Keep coverage completeness separate from visual availability. All missing, partial, conflicting,
  metadata-only, link-permitted and hosted states must be explicit.

---

## Task 0: Set the asset-rights and pilot policy

**Files:**

- Review: `docs/FLOOR_PLAN_PUBLICATION_POLICY.md`
- Modify: `docs/DATA_GOVERNANCE.md`
- Create: a private, non-repository rights-grant template and rights register

**Decisions:**

- [ ] Select the object-storage/CDN provider, public origin, CORS policy, retention policy and
  takedown procedure.
- [ ] Define immutable rights grants plus ordered events. Project state deterministically as
  `withdrawn` > `disputed` > `expired` > `active` > `pending`; never reactivate a withdrawn grant.
- [ ] Define a validated operation vocabulary covering private storage, reproduction, public
  communication, hosting, CDN/cache, browser presentation, each transform, metadata extraction,
  OCR and vectorisation. Derive public disposition; do not store one overloaded `publish_mode`.
- [ ] Define a separate source-terms record for access method, terms version/fingerprint, lawful
  private retention, extraction, factual publication, exact-path linking and next review date.
- [ ] Require an asset junction so one grant can cover multiple exact hashes without implicitly
  covering a future source revision or derivative.
- [ ] Define who may approve a source, a rights grant, a scale calibration and a correction.
- [ ] Define how grant references are stored without committing the underlying contract.
- [ ] Select five to ten pilot condominium projects. Include at least one project with multiple
  same-bedroom, same-area variants; use Clavon only if publishing rights are obtained.
- [ ] Record the named brochure/source revision and expected variant count for each pilot project.

**Tests and evidence:**

- [ ] Walk active-hosted, link-permitted, metadata-only, expired, withdrawn and disputed records
  through the intended publication logic.
- [ ] Confirm that a takedown resolves a rights/asset ID to exact storage keys, removes every public
  URL and cache object, blocks re-publication of the hash and preserves only permitted audit data.
- [ ] Obtain legal review before any real-project metadata, external link or asset is published.

**Exit gate:** Counsel has approved the acquisition, factual-metadata, linking, storage and image-use
decision matrix. Synthetic fixtures exercise the complete schema. Real bytes remain blocked until
at least three pilot projects have grants covering every operation used by the product.

---

## Task 1: Establish immutable private-project identity

**Files:**

- Create: `data/inputs/private_project_registry.csv`
- Create: `data/inputs/private_project_assertions.csv` and `private_project_assertion_events.csv`
- Create: `data/inputs/private_project_events.csv`
- Create: `data/inputs/private_project_aliases.csv`
- Create: `data/inputs/private_project_legacy_ids.csv`
- Modify: `data/catalog.json`
- Create: `sg_estate/application/private_project_catalog.py`
- Create: `scripts/check_floor_plan_append_only.py`
- Modify: the current private-project and multi-condo builders to consume the registry
- Modify: `scripts/build_pages_site.py::build_project_catalog` to consume the same ID universe
- Later migrate: `data/inputs/project_unit_mix.csv` name/district keys to `project_id` if that input
  is restored
- Create: `tests/test_private_project_catalog.py`
- Create: `tests/test_floor_plan_history.py`

**Interface:**

```text
private_project_registry.csv:
project_id, created_at, creation_ref

private_project_assertions.csv:
assertion_id, project_id, predicate, value_json, source_id, asserted_at,
supersedes_assertion_id
```

- [ ] Extract the stable project preparation currently duplicated in report scripts into the
  application module.
- [ ] Preserve the existing transaction identity tuple `(project, street, district, planning_area)`.
- [ ] Allocate and store immutable opaque `project_id` values once; never regenerate them from a
  name, slug, district, address or input order.
- [ ] Store display/source names, normalized names, slugs, street, district, planning area and status
  as append-only assertions/events, never as mutable fields on the identity row.
- [ ] Keep aliases and historical report/query IDs in separate append-only maps. Namespace legacy
  IDs by producer, for example `condo-two:a`, `multi-condo:p` and `edgeprop:slug`.
- [ ] Reuse the repository's single-sourced alias strategy; do not add a floor-plan-local alias map.
- [ ] Fail on an ambiguous duplicate name or alias collision instead of merging heuristically.
- [ ] Backfill the registry for the pilot, private explorer, Pages project catalog and all current
  transaction reports; add tombstone/replacement events rather than deleting identities.
- [ ] Resolve legacy `?a=`, `?b=` and `?p=` IDs and canonicalize the URL without changing the
  selected project.
- [ ] Register every new CSV in the `research` zone of `data/catalog.json`.
- [ ] Add a merge-base CI check: protected identity/history rows may not change or disappear;
  corrections add a tombstone/superseding row. Configure `fetch-depth: 0`, pass the explicit base
  SHA, and compare primary keys plus immutable-field allowlists rather than CSV line positions.

**Tests:**

- [ ] ID stability across reordered inputs and regeneration.
- [ ] ID stability after a rename, address correction and newly discovered duplicate.
- [ ] Duplicate-name disambiguation and alias-collision failure.
- [ ] Legacy shared URLs resolve to the same project and update to the canonical ID.
- [ ] Split/merge/correction events never recycle an old ID.
- [ ] Exact join parity with existing private transactions.
- [ ] No report changes its project totals solely because identity moved to the shared registry.

**Exit gate:** Every pilot project and current project-explorer record resolves to exactly one stable
project ID; unresolved collisions are published as no-data, not guessed.

---

## Task 2: Add floor-plan contracts and relational validation

**Files:**

- Modify: `sg_estate/contracts.py`
- Create: `sg_estate/application/floor_plans.py`
- Create: `sg_estate/application/floor_plan_vocabulary.py`
- Create: `data/inputs/floor_plan_sources.csv`
- Create: `data/inputs/floor_plan_source_events.csv`
- Define private-register contracts for source-terms snapshots/events; add only synthetic rows under
  `tests/fixtures/floor_plans/private_register/`
- Create: `data/inputs/floor_plan_variants.csv`
- Create: `data/inputs/floor_plan_identity_events.csv`
- Create: `data/inputs/floor_plan_expected_variants.csv`
- Create: `data/inputs/floor_plan_assertions.csv` and `floor_plan_assertion_events.csv`
- Create: `data/inputs/floor_plan_predicates.csv`, `floor_plan_terms.csv`,
  `floor_plan_term_revisions.csv`, `floor_plan_term_events.csv`, `floor_plan_term_labels.csv`,
  `floor_plan_term_aliases.csv` and `floor_plan_term_relations.csv`
- Create: `data/inputs/floor_plan_revisions.csv`
- Create: `data/inputs/floor_plan_revision_events.csv`
- Create: `data/inputs/floor_plan_assets.csv` and `floor_plan_renditions.csv`
- Define private-register contracts for rights grants/events/asset bindings; add only synthetic rows
  under `tests/fixtures/floor_plans/private_register/`
- Create: `data/inputs/floor_plan_calibrations.csv` and `floor_plan_calibration_events.csv`
- Create: `data/inputs/floor_plan_stack_assignments.csv`
- Generate: content-addressed public vocabulary release JSON and this glossary from the accepted
  vocabulary projection
- Modify: `data/catalog.json`
- Create: `tests/test_floor_plan_contracts.py`
- Create: `tests/test_floor_plan_provenance.py`
- Create: `tests/test_floor_plan_vocabulary_contracts.py`
- Create: `tests/test_floor_plan_vocabulary_history.py`
- Create: `tests/test_floor_plan_vocabulary_logic.py`
- Create: `tests/test_floor_plan_vocabulary_publication.py`
- Create: `tests/test_floor_plan_rights.py`
- Create: `tests/test_floor_plan_calibration.py`

**Required contracts:**

Real terms snapshots, unapproved source URLs, grant/licensor/authority records, private-asset rows
and deletion obligations live in an access-controlled register outside Git. The repository contains
their executable schemas, synthetic fixtures and builder-generated public-safe entitlement
projections only. Every committed `data/inputs` row must already be safe for a public repository.

- [ ] Unique and non-null IDs for projects, sources, rights, plans, revisions and assets.
- [ ] Foreign-key validation across every identity, assertion, event, asset and calibration table.
- [ ] Enumerated source, source-terms, rights-operation, verification, revision, calibration and
  assignment states with deterministic event ordering.
- [ ] Immutable predicate/facet and controlled-value term IDs, selected append-only definition
  revisions, typed cardinality/value schemas, allowed evidence/absence rules, scoped aliases and
  acyclic logical/deprecation relationships.
- [ ] Bedroom/bathroom counts and source areas within declared ranges.
- [ ] Square-metre/square-foot reconciliation within an explicit conversion tolerance.
- [ ] Acyclic revision history and at most one reviewed publication head for each plan at an
  explicit analysis timestamp; no mutable `is_current` field.
- [ ] Immutable grant plus append-only activation/dispute/withdrawal event projection and expiry;
  grant renewal or scope change creates a new grant.
- [ ] Source/document revision separated from original asset, public rendition and calibration.
- [ ] Every rendition byte object has an asset row; parent/rendition foreign keys and transform
  graphs are acyclic. Crop/resize/re-encode creates a rendition, never a source revision.
- [ ] Calibration is bound to exact rendition bytes. Its authoritative pixel-to-metre affine matrix,
  coordinate-system version, anchor coordinates/real lengths, algorithm/tolerance versions and
  error metrics have append-only review events; X/Y rates are derived, not competing inputs.
- [ ] Stack/floor assignment validation with a disclosed confidence/source.

**Ingestion rules:**

- [ ] Preserve official type code, marketing family, bedroom family and variant label separately.
- [ ] Preserve both disclosed area units; derived conversions use separate fields.
- [ ] Treat internal/balcony/PES/void/roof/air-con-ledge areas as disclosed or null.
- [ ] Store every material displayed fact as a field-level assertion with predicate/value schema,
  source page/evidence locator, extraction method/version and confidence. Assertion events are
  ordered by `(effective_at, assertion_event_id)`; conflicts produce `conflict`.
- [ ] Store derived facts with every input assertion ID and the algorithm version.
- [ ] Resolve every public layout assertion to a stable `predicate_id`; controlled categorical
  values also pin `term_revision_id`. Reject unsupported subjective adjectives as facts while
  allowing reviewed, scope-aware aliases for search only.
- [ ] Emit `vocabulary_schema_version` and content-hashed `vocabulary_release_id` in every catalog
  generation; URLs use IDs, never localized labels.
- [ ] Hash source bytes only when lawful acquisition/retention permits it. Otherwise store a
  reviewed `hash_unavailable_basis` and weaker bibliographic fingerprint, not an illicit copy.
- [ ] Treat source-document facts as immutable and source verification as ordered review events.
- [ ] Validate the private-register adapter and public entitlement projection without exposing
  internal URLs, licensor identities, contract/reviewer references, object keys or deletion terms.
- [ ] Reconcile completeness against an expected-variant inventory for a named source revision.
- [ ] Store OCR and computer-vision output as review suggestions, never official facts.
- [ ] Record exact and perceptual hashes; queue possible duplicates for human resolution.
- [ ] Keep mirror/rotation relationships without collapsing distinct assignments.

**Exit gate:** The contracts represent every pilot variant, including same-area variants and
revisions, without overloaded fields or manual exceptions. The 12–20-term seed vocabulary has
definition/inclusion/exclusion rules, example/non-example fixtures and at least 90% double-coding
agreement or Cohen's kappa of at least 0.8 after adjudication.

---

## Task 3: Build rights-gated assets, coverage and deterministic shards

**Files:**

- Create: `sg_estate/adapters/floor_plan_assets.py`
- Extend: `sg_estate/application/floor_plans.py`
- Create: `data/outputs/floor_plan_coverage.csv`
- Generate: `site/assets/floor-plans/generations/<catalog_sha256>/manifest.json`
- Generate: `site/assets/floor-plans/generations/<catalog_sha256>/projects/<prefix>/<project_id>-<content_sha256>.json`
- Generate last: `site/assets/floor-plans/current.json`
- Create: `tests/test_floor_plan_publication.py`
- Create: `tests/test_floor_plan_determinism.py`

**Generation manifest contract:**

```json
{
  "schema_version": 1,
  "as_of": "YYYY-MM-DDTHH:MM:SS+08:00",
  "catalog_sha256": "...",
  "project_count": 0,
  "plan_count": 0,
  "project_shard_count": 0,
  "projects": []
}
```

`current.json` is a small pointer containing the schema version, active generation path and matching
catalog hash. It is written only after the entire immutable generation validates.

- [ ] Generate one content-addressed project shard, sorted by immutable IDs, using UTF-8 canonical
  JSON (`sort_keys=True`, compact separators, `ensure_ascii=False`, `allow_nan=False`, final newline).
- [ ] Put only lightweight project search and coverage fields in the manifest.
- [ ] Put variant/revision/rendition metadata and complete builder-approved CDN URLs in on-demand
  project shards.
- [ ] Generate the public entitlement projection in a protected job from the current private
  register; public PR CI uses synthetic fixtures and never receives production-register secrets.
- [ ] Use immutable CDN keys: `/<project_id>/<revision_id>/<rendition_id>/<sha256>.webp`.
- [ ] Emit a CDN URL only when source terms, active grants, exact asset binding, publication origin,
  service provider and every requested operation permit that rendition.
- [ ] Emit an ordinary source link but no copied asset for `link_permitted`; emit neither asset nor
  source URL for `metadata_only`.
- [ ] Check each operation separately: a hosting right does not imply thumbnail, browser resize,
  viewport crop, composite, opacity, calibration, annotation or overlay rights.
- [ ] Generate `coverage_status` as `complete`, `partial`, `missing` or `conflict`, reconciled to a
  named source revision. Separately generate per-rendition `public_disposition` as
  `hosted_original`, `hosted_derivative`, `link_permitted`, `metadata_only` or `withheld`; a
  project-level visual-availability summary may be `mixed`.
- [ ] Make generation fail when an exposed asset lacks provenance/hash, uses inactive rights or is
  an unexpected orphan; inactive records that are safely suppressed must still allow replacement.
- [ ] Build with an explicit analysis timestamp into
  `site/assets/floor-plans/generations/<catalog_sha256>/...`; validate every hash, count and
  allowlist, then write the small top-level `current.json` pointer last. Pages copies only the
  selected generation into its fresh deployment artifact.
- [ ] Compute the catalog hash over schema/as-of plus ordered shard hashes, excluding the catalog
  hash field itself. Reject stale/orphan shards.
- [ ] Emit a successful metadata-only replacement plus purge manifest for expired, withdrawn or
  disputed rights; fail if the replacement still exposes a prohibited URL.

**Tests:**

- [ ] Active/original, active/derivative, link-permitted, metadata-only, expired, withdrawn and
  disputed rights gates.
- [ ] Deterministic manifest and byte-identical shards from reordered inputs.
- [ ] One project per shard, canonical record order and byte-identical output for the same `--as-of`.
- [ ] Manifest counts reconcile to shards and coverage output.
- [ ] Per-shard digests reconcile; the active generation pointer cannot expose an incomplete set.
- [ ] No licence grant details, private source paths or exact-unit data enter public JSON.
- [ ] A source revision change creates a new revision and changes the catalog hash without deleting
  the old audit record.

**Exit gate:** Five to ten pilot projects have reviewed coverage, deterministic public metadata and
zero public asset URLs without active permission.

---

## Task 4: Build the searchable floor-plan library

**Files:**

- Create: `sg_estate/reporting/builders/floor_plan_library.py`
- Create: `sg_estate/reporting/templates/floor_plan_library.html`
- Create: `site/assets/floor-plan-library.js`
- Create: `site/assets/floor-plan-library.css`
- Generate: `floor_plan_library.html`
- Create: `docs/html-pages/floor_plan_library.md`
- Create: `tests/test_floor_plan_library_html.py`

**Required behavior:**

- [ ] Search projects by display/source name, alias, street, postal code and stable ID.
- [ ] Filter variants by bedrooms, bathrooms, area and reviewed feature flags.
- [ ] Load only the selected project's metadata shard and images.
- [ ] Display a source-revision coverage matrix by bedroom/family/type.
- [ ] Explain coverage status independently from per-rendition public disposition and calibration.
- [ ] Show source, page, retrieval date, verification, rights and revision status.
- [ ] Allow two to four variants to enter a comparison tray.
- [ ] Encode search, selected project and filters in URL parameters and restore them on reload.
- [ ] Provide an accessible table view and meaningful alt text.
- [ ] Add a correction/missing-plan link that pre-fills stable project/plan IDs without collecting
  private financial data.
- [ ] Lazy-load images and reserve their aspect-ratio boxes to avoid layout shift.

**Tests:**

- [ ] Static contract, manifest/schema version and no-inline-handler tests.
- [ ] Empty/partial/metadata-only/link-permitted/error states.
- [ ] URL round-trip, back/forward navigation and invalid-state normalization.
- [ ] Keyboard selection, focus visibility, screen-reader labels and mobile containment.
- [ ] No full-catalog image fetch on first page load.

**Exit gate:** A user can find every disclosed two-bedroom variant in a pilot project and identify
whether the project is complete to the named source revision.

---

## Task 5: Build the two-to-four-plan comparator

**Files:**

- Create: `sg_estate/reporting/builders/floor_plan_compare.py`
- Create: `sg_estate/reporting/templates/floor_plan_compare.html`
- Create: `site/assets/floor-plan-compare.js`
- Create: `site/assets/floor-plan-compare.css`
- Generate: `floor_plan_compare.html`
- Create: `docs/html-pages/floor_plan_compare.md`
- Create: `tests/test_floor_plan_compare_html.py`
- Create: `tests/test_floor_plan_compare_e2e.py`

**Display model:**

- [ ] Accept two to four ordered plan/revision pairs and pin `revision_id` by default so a saved
  comparison cannot silently change after a brochure correction.
- [ ] Render fit-to-card side-by-side by default with independent source/status badges.
- [ ] Implement synchronized zoom/pan with mouse, touch and keyboard controls.
- [ ] Enable common-scale mode only when every exact selected rendition hash has a reviewed
  calibration and permitted transforms.
- [ ] Apply the recorded affine pixel-to-metre transform, crop and rotation to a shared relative
  browser scale; never infer scale from total area or imply a physical printed 1:100 display.
- [ ] Enable overlay only when common-scale eligibility passes; otherwise disable it with the reason.
- [ ] Preserve rotation and mirror information in metadata when the display is transformed.
- [ ] Show a structured comparison table for type, bedrooms/baths, disclosed areas, study/flex,
  yard/store, kitchen, ventilation, private lift and dual key.
- [ ] Render glossary definitions, evidence class and unknown/absent distinction consistently in
  library filters, comparator rows, tooltips and accessible text.
- [ ] Distinguish `official_disclosed`, reviewed derived and unknown fields.
- [ ] Provide a drawing-independent table/text alternative and printable layout.
- [ ] Restore comparison order, zoom mode, scale mode and overlay state from a canonical URL.

**Tests:**

- [ ] Two-, three- and four-plan selection; removal and replacement.
- [ ] Reviewed common-relative-scale eligibility and explicit uncalibrated warning.
- [ ] Overlay denial when any plan is uncalibrated or transformation is not permitted.
- [ ] Scale math against fixed calibrated fixtures, including crop boxes and rotation.
- [ ] Reject calibration for different rendition bytes, insufficient/collinear anchors, excess
  error and a revision whose calibration has not been re-reviewed.
- [ ] Prevent URL state from bypassing common-scale or overlay eligibility.
- [ ] Reload/share URL parity and invalid/missing plan recovery.
- [ ] Keyboard zoom/pan, focus order, reduced motion, touch behavior and mobile overflow.
- [ ] No console errors, broken images or inaccessible comparison state.

**Exit gate:** Moderated users can find and compare a specified set of pilot variants within two
minutes; the same core task works with keyboard and on mobile.

---

## Task 6: Add confidence-labelled transaction matching

**Files:**

- Extend: `sg_estate/application/floor_plans.py`
- Create: `data/outputs/floor_plan_transaction_matches.csv`
- Modify: floor-plan public metadata shards
- Modify: library and comparison pages
- Create: `tests/test_floor_plan_transaction_matching.py`

**Match method:**

- [ ] Create a deterministic transaction ID from source, stable project identity, district, month,
  price, area and an occurrence index assigned only after deterministic grouping.
- [ ] Reuse the current bedroom-attribution provenance rather than trusting a raw bedroom value.
- [ ] Emit `exact` only with authorised exact unit/stack evidence and an official stack-to-plan map.
- [ ] Emit `probable_unique` only when project, sourced bedroom and area evidence leave exactly one
  compatible current plan.
- [ ] Emit `candidate_set` when multiple plan variants remain compatible; retain every candidate.
- [ ] Emit `bedroom_only`, `size_only`, `unmatched` or `conflict` when evidence is weaker.
- [ ] Persist match method, evidence fields, tolerances, candidate count and algorithm version.
- [ ] Prevent one transaction from silently fanning out into multiple exact or probable matches.
- [ ] If indistinguishable duplicate rows have conflicting secondary bedroom evidence and no shared
  source-row ID, downgrade them to ambiguity; never attach evidence by raw input order.
- [ ] Keep restricted exact-unit sources outside public shards.
- [ ] Display transaction sample size, window, sale state and match caveat beside each cohort.

**Tests:**

- [ ] Exact, unique candidate, ambiguous candidate, bedroom-only, size-only, unmatched and conflict.
- [ ] Multiple same-area variants remain a candidate set.
- [ ] Area tolerance boundaries and square-metre/square-foot consistency.
- [ ] Occurrence-safe duplicate transactions and stable IDs under reordering.
- [ ] No restricted exact-unit fields in public outputs.

**Exit gate:** Every transaction connection exposes its match method and evidence; no public record
can be mistaken for an exact layout match when exact evidence is unavailable.

---

## Task 7: Integrate with the existing research site

**Files:**

- Modify: `private_project_comparison_table.html` generator/template and its JavaScript
- Modify: `site/reports.json`
- Modify: `index.html` source/generator
- Modify: `README.md`
- Modify: `Makefile`
- Modify: `scripts/build_pages_site.py`
- Modify: `.github/workflows/pages.yml`
- Create: `.github/workflows/floor-plan-rights.yml`
- Modify: `tests/test_pages_site.py`

- [ ] Add floor-plan coverage and “compare layouts” actions to private-project rows without
  embedding the plan catalog in the existing large report.
- [ ] Register both `floor_plan_library.html` and `floor_plan_compare.html` in `site/reports.json`.
- [ ] Add discovery cards/links to the root index and README HTML-deliverables section.
- [ ] Add `make floor-plan-catalog`, `make floor-plan-reports` and an aggregate verification target.
- [ ] Package the manifest, shards, CSS and JavaScript in `_site/` and validate every local link.
- [ ] Add a dedicated public-JSON URL validator; require HTTPS, no credentials, an allowlisted
  publication/link origin and content-hash-shaped asset paths. The current Pages checker ignores
  remote URLs.
- [ ] Add a restrictive Content Security Policy for image, script, style and connection origins.
- [ ] Add Pages workflow path triggers for floor-plan inputs, application code, report code and
  assets.
- [ ] Decide whether generated root HTML/shards remain committed or are generated in Pages CI; use
  one model consistently and add a stale-artifact test.
- [ ] Add an enforced browser-test job with Playwright/Chromium for the comparator instead of an
- [ ] Install Playwright in the actual CI environment and run
  `playwright install --with-deps chromium`; a skipped browser suite is not a release gate.
- [ ] Add a scheduled daily rights and source-terms projection/rebuild plus 30/60/90-day grant
  expiry and `next_review_at` report, independent of the analytical pipeline.
- [ ] Bound CDN cache TTL by the remaining grant term and add emergency object deletion/CDN purge.
- [ ] Add a manual emergency-takedown workflow that accepts a rights or asset ID, resolves exact
  keys, supports dry-run, requires deployment-environment approval and records the purge result.
- [ ] Configure full Git history for the merge-base append-only check.

**Exit gate:** A project can be discovered in the existing explorer, opened in the floor-plan
library, compared, shared and returned to without a broken local or deployed link.

---

## Task 8: Pilot QA, release and measurement

**Files:**

- Create: `docs/FLOOR_PLAN_INGESTION_RUNBOOK.md`
- Create: an internal coverage/rights report generated from metadata
- Add: release checklist to the report guides

- [ ] Double-review all pilot project/plan identities, areas, revisions, calibration and rights.
- [ ] Reconcile every published variant to the named source-document revision.
- [ ] Test expired/withdrawn/disputed rights and emergency takedown in staging, including the direct
  object URL and blocked-hash re-upload path.
- [ ] Run moderated tasks with at least one mobile, one keyboard and one first-time property buyer
  cohort.
- [ ] Measure find-to-compare time, comparison completion, share/export, correction submissions and
  user-reported uncertainty.
- [ ] Verify p75 LCP target below 2.5 seconds on representative mobile conditions.
- [ ] Record ingestion analyst-hours separately from rights negotiation time.
- [ ] Publish scope honestly as a pilot; do not imply islandwide completeness.

**Release gate:**

- 100% published assets have active rights and provenance.
- 100% pilot variants reconcile to a named source revision.
- No common-scale claim lacks reviewed calibration.
- At least 80% of moderated users complete the specified comparison within two minutes.
- All unit, report, browser and Pages tests pass.

---

## Task 9: Post-MVP scale decisions

Proceed only after reviewing pilot evidence.

- [ ] Expand to 25–50 projects if coverage and QA effort remain sustainable.
- [ ] Add official stack/site-plan assignments and exposure/orientation context.
- [ ] Add a developer submission manifest and developer-verified status.
- [ ] Add household-relative layout lenses without a universal score.
- [ ] Link ownership economics and the condo loan timeline planner to selected layouts.
- [ ] Add saved comparisons only when an account/privacy architecture is justified.
- [ ] Consider a backend ingestion/review system only when static reviewed CSV workflows become the
  measured bottleneck.

Do not prioritise a live-listing marketplace, automatic OCR publication, 3D furnishing or
islandwide asset backfill ahead of data rights, variant completeness and comparison quality.

## Verification commands for implementation

Exact target names will be added with the implementation. The expected verification shape is:

```bash
rtk pytest -q tests/test_private_project_catalog.py tests/test_floor_plan_history.py
rtk pytest -q tests/test_floor_plan_contracts.py tests/test_floor_plan_provenance.py
rtk pytest -q tests/test_floor_plan_vocabulary_contracts.py tests/test_floor_plan_vocabulary_history.py
rtk pytest -q tests/test_floor_plan_vocabulary_logic.py tests/test_floor_plan_vocabulary_publication.py
rtk pytest -q tests/test_floor_plan_rights.py tests/test_floor_plan_calibration.py
rtk pytest -q tests/test_floor_plan_publication.py tests/test_floor_plan_determinism.py
rtk pytest -q tests/test_floor_plan_transaction_matching.py
rtk pytest -q tests/test_floor_plan_library_html.py tests/test_floor_plan_compare_html.py
rtk pytest -q tests/test_floor_plan_compare_e2e.py tests/test_pages_site.py
rtk make pages-check
rtk git diff --check
```

Run the full non-snapshot suite before release:

```bash
rtk pytest -q
```
