# Floor-Plan Comparison Safe-Pilot Plan

**Status:** Backlog; retained as a possible execution sequence after a viable rights-cleared
image-comparison pilot can be assembled. Its synthetic and metadata-only modes are validation gates,
not standalone customer-facing releases.

**Goal:** Introduce useful floor-plan comparison and visualisation in small, reversible releases
without publishing an unlicensed drawing, losing provenance, changing an existing identity or
claiming an unsupported common-relative scale.

**Policy:** [Floor-Plan Publication, Provenance and Calibration Policy](../../FLOOR_PLAN_PUBLICATION_POLICY.md)

**Full roadmap:** [Property Comparison and Floor-Plan Comparison Implementation Plan](2026-08-10-property-comparison-floor-plan.md)

**Design:** [Property Comparison and Floor-Plan Comparison — Design](../specs/2026-08-10-property-comparison-floor-plan-design.md)

**Controlled vocabulary:** [Floor-Plan Layout Glossary](../../FLOOR_PLAN_LAYOUT_GLOSSARY.md)

## Safe release strategy

Build the comparator in four progressively more permissive modes. The first deployed UI is
synthetic-only; no real-project fact, outbound source link or third-party byte is needed to prove the
interaction design.

| Mode | Real project metadata | Hosted drawing | Common scale | Purpose |
|---|---:|---:|---:|---|
| Synthetic UI preview | No | Repository-owned fixture only | Fixture calibration only | Ship and test the complete interaction without third-party rights |
| Lawful-basis metadata pilot | Yes, field reviewed | No | No | Validate identity, coverage and filters after counsel/source-terms approval |
| Link-permitted pilot | Yes, field reviewed | No | No | Add only exact outbound targets covered by current terms or permission |
| Rights-cleared visual pilot | Yes, field reviewed | Only exact allowed hashes/renditions | Per exact calibrated rendition | Public two-to-four-plan comparison |

The modes share the same contracts and UI. Moving a record forward changes its reviewed rights and
calibration state; it does not require a second permissive code path.

### PR boundary rules

- Each change package below is one reviewable PR; do not combine adjacent packages to accelerate a
  public pilot.
- A PR contains its contracts, fixtures, negative tests, operator note and rollback path. Its exit
  gate must pass before the next package starts.
- Packages 1 and 2 are synthetic-only and may be built while package 0 legal/terms work is pending.
  Package 3 and every later use of real-project facts, links or bytes is blocked on package 0.
- No PR changes an existing public project-analysis score or mixes floor-plan evidence into the
  Provision/Liveability models.
- A public preview remains synthetic until a separate release review approves the exact records in
  the next mode.

### Keep coverage separate from visual availability

These are independent public dimensions and must never be collapsed into one badge:

- **Variant coverage** compares reviewed captured variants with the expected variants in one named
  source-document revision. It is `missing`, `partial`, `complete` or `conflict`.
- **Public disposition** describes what this site may currently show for one exact rendition:
  `withheld`, `metadata_only`, `link_permitted`, `hosted_original` or `hosted_derivative`.
  Calibration is a third independent status; a project-level availability summary may be `mixed`.

A project can have complete metadata coverage and no publishable drawing, or partial coverage with
one rights-cleared drawing. Image availability must not increase the coverage result, and missing
image rights must not erase lawfully publishable factual coverage.

## Initial visualisation scope

### Ship in the pilot

1. **Coverage matrix** — which bedroom/family/type variants are expected, captured, missing or in
   conflict for a named source-document revision, independently of image rights.
2. **Side-by-side plan cards** — two to four ordered plans with source, revision and status badges.
3. **Visual-availability state** — no image, permitted external link, hosted unscaled rendition or
   hosted calibrated rendition, without changing the coverage result.
4. **Synchronized zoom and pan** — only when the exact hosted rendition is licensed for those
   client-side operations; it does not imply common scale.
5. **Common-relative-scale view** — only when every selected exact rendition hash passes reviewed
   calibration and is rendered through the shared pixels-per-metre transform. This compares
   relative footprint size; it is not a construction measurement.
6. **Overlay with opacity control** — only when common-relative-scale and explicit compositing,
   opacity and overlay rights pass.
7. **Structured difference matrix** — official type, beds/baths, disclosed total/area components and
   reviewed layout features.
8. **Area-composition bars** — only from officially disclosed area components; unknown remains
   visually distinct and is never estimated to fill 100%.
9. **Transaction cohort panel** — exact, probable-unique, candidate, bedroom-only or size-only
   status with sample basis and date range.
10. **Shareable state** — ordered plan IDs, exact revision/rendition IDs and visual mode in the URL.

### Defer until after the pilot

- automatic room segmentation or dimension extraction;
- traced/redrawn plans;
- furniture placement or renovation simulation;
- 3D views;
- public uploads without a reviewed submission/rights workflow;
- stack/site-plan overlays without official mapping evidence;
- a universal layout-efficiency or “best plan” score.

## Change package 0: Adopt the fail-closed policy

**Files:**

- Review: `docs/FLOOR_PLAN_PUBLICATION_POLICY.md`
- Modify: `docs/DATA_GOVERNANCE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: the full floor-plan implementation plan

- [ ] Obtain written Singapore-counsel review of the grant template, factual-metadata extraction,
  source-access/website terms, exact outbound-link treatment, private byte retention, browser and
  server transformations, attribution/moral-rights treatment and takedown process.
- [ ] Record a go/no-go decision separately for (a) real factual metadata, (b) each source link and
  (c) each acquired/stored/served byte. Approval of one category does not approve another.
- [ ] Define a versioned private source-terms register with the terms URL, retrieved timestamp,
  terms hash/version, permitted access/extraction/link/storage operations, exact target/path scope,
  reviewer, effective/expiry date and `review_due_at`.
- [ ] Require the source-terms record before any real-project source is opened by an automated
  ingester, downloaded, hashed, retained, linked or converted into public metadata.
- [ ] Assign operational owners for source, rights, calibration and QA review.
- [ ] Select private storage for grants/contracts and object storage for assets.
- [ ] Choose the public CDN origin and define CORS, cache and purge behavior.
- [ ] Agree the public labels for source, rights, revision and scale status.
- [ ] Define the emergency deny/purge route independently of the normal site build and run a paper
  exercise from `active` to origin-denied, pointer-replaced, CDN-purged and verified unavailable.
- [ ] Define scheduled source-terms and grant revalidation, including fail-closed treatment when
  review is overdue, permission expires or terms change.

**Exit gate:** Counsel and the named reviewers approve the precise real-metadata, link and byte
methods; the source-terms register and emergency runbook exist; and no production path bypasses the
decision tables. Until this gate passes, every deployed record, image, URL and test fixture is
repository-owned synthetic material.

## Change package 1: Contracts, registry and synthetic fixtures

**Files:**

- Create: `data/inputs/private_project_registry.csv`
- Create: project alias and legacy-ID maps
- Create: immutable floor-plan source, variant, expected-variant, assertion, revision, asset,
  rendition, source-terms, rights-grant, allowed-operation and calibration inputs plus append-only
  event tables
- Create: versioned controlled-term registry with aliases, evidence/absence rules and deprecations
- Modify: `data/catalog.json`
- Modify: `sg_estate/contracts.py`
- Create: `sg_estate/application/private_project_catalog.py`
- Create: `sg_estate/application/floor_plans.py`
- Create: `sg_estate/application/floor_plan_vocabulary.py`
- Create: `scripts/check_floor_plan_append_only.py`
- Create: `tests/fixtures/floor_plans/` with original synthetic plans and grants
- Create: contract/identity/revision tests

Real source-terms, unapproved source locators, grants/licensor evidence, private original records,
deletion obligations and blocked hashes are not committed to this public repository. Package 1 adds
their contracts and repository-owned synthetic fixtures; later protected jobs read real rows from
the access-controlled register and emit only the minimal public entitlement projection.

- [ ] Use four intentionally different synthetic plans: same-area variants, a mirror relation, a
  superseded revision and an uncalibrated plan.
- [ ] Give every synthetic asset an explicit repository-owned test licence and `synthetic` badge.
- [ ] Keep identity, assertion, source, revision, asset, rendition, terms, grant and calibration base
  records immutable. `supersedes_revision_id` owns the acyclic revision topology; activation,
  review, selection, conflict, withdrawal, dispute and tombstone are append-only events materialised
  at an explicit `--as-of` time. Expiry is derived from immutable dates. There are no mutable
  `is_current`, `status` or `superseded_at` shortcuts.
- [ ] Validate stored opaque project/plan/revision/source/asset/rendition/rights/calibration IDs and
  foreign keys.
- [ ] Bind every grant to the exact source-document ID, source asset SHA-256 and covered plan
  revision. Bind each permitted derivative to its parent hash and exact rendition hash.
- [ ] Represent rights as granular scoped operations with no umbrella transformation permission:
  acquire, hash, store privately, retain privately, host original, thumbnail, crop, resize,
  compress, convert format, client zoom/pan, annotate, composite/overlay, extract factual metadata,
  vectorise, serve through the named CDN and emit the exact external link.
- [ ] Store the licensor separately from the asserted rights holder, authority-basis reference,
  permitted origin/domain/channel/territory, commercial scope, attribution/notice requirements,
  effective/expiry/review dates and private-byte deletion obligation. Public disposition is derived
  from these records; it is never a manually looser flag.
- [ ] Prove ID stability after input reordering, display-name changes and alias additions.
- [ ] Prove that same-bedroom/same-area variants remain separate.
- [ ] Prove append-only revision resolution for a selected analysis date.
- [ ] Prove that a crop/resize creates a rendition rather than a plan revision.
- [ ] Prove every displayed factual field resolves to a reviewed assertion and conflicts fail closed.
- [ ] Prove every structured layout assertion resolves to one active predicate and valid value;
  categorical values also resolve to one selected term revision. Subjective marketing adjectives
  cannot become filters or plan facts.
- [ ] Pin `vocabulary_schema_version` and content-hashed `vocabulary_release_id`; categorical
  assertions pin term revision IDs, while numeric/text predicates keep typed values.
- [ ] Double-code the 12–20 seed facets on synthetic examples/non-examples, adjudicate every
  disagreement and require at least 90% agreement or Cohen's kappa of at least 0.8.
- [ ] Prove protected historical rows cannot be edited/deleted relative to the merge base.
- [ ] Prove that a missing/overdue source-terms or lawful-use basis cannot emit a real fact or link,
  and an inactive/missing grant cannot emit a hosted asset or rights-dependent extraction. Do not
  manufacture a rights grant for independently reviewed metadata-only facts.
- [ ] Prove that withdrawal cannot be “reinstated” without a new documented grant; resolution of a
  dispute is a separate event on a still-effective grant.

**Exit gate:** The data model handles every identity/revision edge case using only repository-owned
fixtures, and operation-level negative tests fail closed. No real fact, link or drawing is required.

## Change package 2: Synthetic-only library and comparator preview

**Files:**

- Create: `sg_estate/reporting/builders/floor_plan_library.py`
- Create: `sg_estate/reporting/templates/floor_plan_library.html`
- Create: `sg_estate/reporting/builders/floor_plan_compare.py`
- Create: `sg_estate/reporting/templates/floor_plan_compare.html`
- Create: `site/assets/floor-plan-library.js`
- Create: `site/assets/floor-plan-library.css`
- Create: `site/assets/floor-plan-compare.js`
- Create: `site/assets/floor-plan-compare.css`
- Generate: `floor_plan_library.html`
- Generate: `floor_plan_compare.html`
- Create: `scripts/validate_floor_plan_public_urls.py`
- Create: `scripts/assert_playwright_junit.py`
- Generate: deterministic release manifest, content-addressed synthetic shards and a small current
  release pointer
- Modify: `requirements-dev.txt`
- Modify: `.github/workflows/ci.yml`
- Add: report, Pages and non-skipped Playwright tests

- [ ] Use only the repository-owned synthetic records and images from package 1. Add a hard build
  assertion that `source_kind != synthetic` is forbidden in this preview mode.
- [ ] Show variant coverage independently from visual availability.
- [ ] Support project, bedroom, bathroom, area and reviewed-feature filters.
- [ ] Show the exact source document/revision used to claim completeness.
- [ ] Generate comparison labels/tooltips from the controlled vocabulary and preserve
  `present`/`absent`/`unknown`/`not_applicable` as distinct values.
- [ ] Add a two-to-four-item comparison tray, unscaled plan cards, independent/synchronised zoom and
  the structured difference table. Every operation is checked against the synthetic grant.
- [ ] Pin ordered plan, revision and rendition IDs in the URL; support reload, back/forward and an
  invalid/withdrawn-ID fallback.
- [ ] Add accessible tabular output and correction links.
- [ ] Generate sorted canonical JSON at an explicit analysis time with no uncontrolled wall-clock,
  random-order or absolute-path fields. Write it to a temporary release directory, validate schema,
  hashes, counts and origins, publish immutable digest-addressed shards/manifest, and only then
  replace the small `current.json` pointer. Do not depend on a directory rename/swap as the
  publication guarantee. Rebuilding identical inputs must be byte-identical.
- [ ] Make `scripts/validate_floor_plan_public_urls.py` mandatory in CI. It validates every emitted
  URL against the public disposition and exact-origin/path allowlist; it performs a live request
  only where the source-terms record permits automated checking.
- [ ] Add the pinned Playwright Python dependency to the development environment. In PR CI run
  `python -m playwright install --with-deps chromium` before the dedicated local-fixture browser
  suite, emit JUnit XML and make `scripts/assert_playwright_junit.py` reject zero collected tests,
  `skip`, `xfail` or browser-start failure. None is a green fallback.

**Exit gate:** A public synthetic preview supports selection, comparison, URL restoration and
accessibility; generation is byte-deterministic; the URL validator and Playwright suite are
non-skipped required checks. The release contains zero real-project facts, links or bytes.

## Change package 3: Lawful-basis real metadata, no links or bytes

**Files:**

- Populate: source-terms, source-description, expected-variant and field-assertion inputs for at
  most three counsel-approved pilot projects
- Extend: floor-plan application materialiser and public-safe metadata shards
- Add: lawful-basis, coverage/availability separation and private-data-leak tests

- [ ] Attach every factual assertion to a reviewed source-terms record and explicit lawful-basis
  reference covering the actual access and extraction method. “It is a fact” or “it was on the
  internet” is not a sufficient recorded basis.
- [ ] Do not automate source access, download a document, calculate a full-document hash or retain a
  byte unless those exact operations are allowed. When lawful copying is unavailable, retain only
  the counsel-approved bibliographic/fingerprint fields.
- [ ] Publish only accepted factual assertions that do not reproduce protected visual expression.
  Anything uncertain, inferred, conflicting or overdue for terms review remains private/no-data.
- [ ] Emit a non-linked public source description only. Public JSON contains no `source_url`, image,
  asset key, reconstructable object path or contract/grant reference.
- [ ] Derive `missing`/`partial`/`complete`/`conflict` coverage for the named source revision without
  considering whether a visual is available. Set public disposition to `metadata_only` for every
  lawfully publishable record and `withheld` otherwise.
- [ ] Re-run deterministic generation, mandatory URL validation and non-skipped Playwright tests
  from package 2 with mixed synthetic/metadata-only fixtures.

**Exit gate:** The three reviewed projects expose only counsel-approved factual metadata and source
descriptions. Each public field has a current lawful-basis reference; no public link or real byte is
present, and visual availability remains independent from coverage.

## Change package 4: Exact link-permitted disposition

**Files:**

- Extend: source-terms/public-disposition materialiser
- Extend: library source treatment
- Add: exact-target, terms-expiry and remote-URL-validator tests

- [ ] Add a link only when a current reviewed terms/permission record allows hyperlinking to that
  exact origin and target path. Permission for a domain, access or metadata extraction alone is not
  link permission.
- [ ] Emit an ordinary external anchor only: no embed, iframe, hotlink, proxy, cached preview,
  screenshot, open-graph image or service-worker copy.
- [ ] Record terms evidence, review/expiry dates and the precise target internally; expose only the
  approved URL and public-safe source label.
- [ ] Remove a link automatically when permission expires, review becomes overdue, target scope
  changes or a dispute event is effective. Coverage metadata remains only if its separate lawful
  basis remains active.
- [ ] Make the URL validator prove exact disposition/origin/path approval in every PR. Any live
  availability request is separately gated by permission for automated checking.

**Exit gate:** At least one expressly permitted link can be added and then removed by an event/date
without changing code, while metadata coverage remains stable and no third-party byte is hosted.

## Change package 5: Rights adapter and private asset staging

**Files:**

- Create: `sg_estate/adapters/floor_plan_assets.py`
- Extend: floor-plan application builder
- Add: storage/CDN integration configuration through environment variables
- Create: emergency deny/purge command and operator runbook
- Create: scheduled rights/source-terms revalidation workflow
- Add: operation-rights, terms/grant revalidation, attribution, expiry and purge tests

- [ ] Acquire or upload a byte only when both the source-access record and exact asset-bound grant
  permit acquisition and private storage. Use immutable content-addressed staging keys and honour
  private retention/deletion deadlines.
- [ ] Verify the byte against the grant's exact source asset SHA-256, source-document ID and covered
  revision before retaining it. A filename, project name or visually similar plan never binds a
  grant.
- [ ] Generate only the exact operations permitted for that asset: thumbnail, crop, resize,
  compression, format conversion, annotation, overlay and vectorisation are independent operation
  permissions within a grant.
  Record parent and rendition hashes for every operation.
- [ ] Require explicit CDN/vendor serving rights and licensed public origins before promotion.
  Browser resize, zoom/pan, opacity and compositing also require the corresponding client-operation
  rights; hosting the original does not imply them.
- [ ] Keep OCR/factual extraction and public visual rights independent. No automatic extraction or
  vectorisation runs merely because private storage is allowed.
- [ ] Ensure the browser receives a full approved URL, not enough information to construct one.
- [ ] Run scheduled and pre-release projection of source terms, grant scope, expiry, withdrawal,
  dispute and `review_due_at`. Produce 30/60/90-day reports and fail closed on an overdue review.
- [ ] Generate a safe replacement release/pointer plus an exact CDN origin-deny and purge manifest.
- [ ] Add allowlisted CDN/source origins and a restrictive Content Security Policy.
- [ ] Exercise an emergency kill by asset hash, rendition hash, grant ID and project/revision. Deny
  the object at origin without waiting for the normal build, purge CDN caches, point the site to the
  safe metadata-only release, add the blocked hash and verify old direct URLs fail.
- [ ] Exercise expiry, overdue terms review, dispute and licensor withdrawal separately. Withdrawal
  cannot be reversed without a new documented grant; private bytes are deleted when retention is no
  longer permitted while hashes/audit events remain.

**Exit gate:** An exactly bound staged asset can move active → origin-denied → pointer-replaced →
purged without a code change or normal-build dependency. Direct URLs fail, the old hash is blocked,
and no unpermitted private byte or derived operation remains.

## Change package 6: First rights-cleared project

**Files:**

- Populate: reviewed metadata for one licensed project
- Populate: private rights register and public-safe rights rows
- Generate: public metadata shard and coverage output
- Add: a project-specific reconciliation fixture

- [ ] Reconcile every source variant, not only every bedroom category.
- [ ] Record official codes, marketing families, areas and source pages separately.
- [ ] Double-review lawful basis, exact source/rendition hashes, grant authority, operation scope,
  attribution, revision, source-terms status, rights dates and private-storage permission.
- [ ] Keep unlicensed variants as metadata-only/missing instead of replacing them from another
  portal. Add an external link only through the current exact `link_permitted` disposition from
  package 4.
- [ ] Publish coverage as `partial` unless all expected variants for the named source revision are
  reconciled. Report visual availability separately for each captured revision.
- [ ] Promote only the exact grant-bound rendition URLs approved by the rights projection; no URL
  construction or “similar type” substitution is allowed.
- [ ] Perform the live emergency deny/pointer/purge exercise against the pilot staging origin before
  public release and verify the recovery materialisation remains useful.

**Exit gate:** One real project publishes only exactly licensed rendition hashes, every operation
has current terms/grant evidence, emergency removal is proven and its independent coverage and
visual-availability labels are defensible.

## Change package 7: First real-image comparator without scale claims

**Files:**

- Extend: comparator builder/template/assets created in package 2
- Extend: exact rendition/public-disposition JSON
- Add: real-image rights-negative, static and non-skipped Playwright tests

- [ ] Compare two to four ordered plan/revision/rendition tuples and pin all three IDs in shared
  URLs by default.
- [ ] Render fit-to-card images with an always-visible “not shown to common-relative scale” status
  by default.
- [ ] Add independent and synchronized zoom/pan only for exact renditions licensed for those client
  operations, without changing the scale label.
- [ ] Add the structured difference matrix and disclosed-area bars.
- [ ] Keep unknown values empty/unknown rather than inferred.
- [ ] Preserve source, rights, revision, rendition and visual-availability badges on every card.
- [ ] Support print, mobile, keyboard and reduced-motion users.
- [ ] Keep the URL validator and Playwright suite mandatory and non-skipped with a withdrawn-asset
  fixture proving that a shared old URL falls back safely.

**Exit gate:** The visual comparison is useful even when none of the drawings is scale-calibrated,
every client operation is licensed for the exact rendition, and no UI control can imply common
relative scale.

## Change package 8: Reviewed common-relative-scale and overlay modes

**Files:**

- Add: calibration input/contract and calibration fixtures
- Extend: public metadata shard with reviewed calibration fields
- Extend: comparator scale and overlay controls
- Add: calibration math and browser visual-state tests

- [ ] Define **common-relative-scale** precisely: every selected plan is rendered using one declared
  pixels-per-metre coordinate system so relative footprint sizes are comparable. It is not an
  engineering, construction or room-dimension warranty.
- [ ] Establish an affine pixel-to-metre transform from an authoritative scale/dimension basis for
  the exact published rendition SHA-256, pixel dimensions, crop and rotation.
- [ ] Store machine-readable anchor coordinates/real lengths plus RMS and maximum error. Keep crop,
  rotation and parent-to-child coordinate transforms in the versioned rendition transform chain;
  the calibration references that exact rendition. Use two orthogonal anchors for an isotropic
  raster or at least three non-collinear anchors for a skewed scan.
- [ ] Set and document the pilot acceptance tolerance before calibration; test both RMS and maximum
  error with an independent check dimension rather than accepting a zero-residual fitted anchor.
- [ ] Use a second reviewer for calibration QA.
- [ ] Show an on-screen scale bar and review date.
- [ ] Enable common-relative-scale only when every selected exact rendition passes the same current
  calibration, source-terms and operation-right eligibility rules.
- [ ] Enable overlay only when all exact renditions pass calibration and explicit
  compositing/opacity/overlay rights checks.
- [ ] Disable the control with a specific explanation when any requirement fails.
- [ ] A byte, crop, pixel-dimension, rotation or transform-chain change creates a new rendition and
  calibration, not a plan revision; calibration never transfers by filename or plan ID.
- [ ] A new source revision starts uncalibrated until its exact rendition passes review.
- [ ] Keep mandatory Playwright negative cases for mixed calibration states, expired rights,
  mismatched rendition hashes and URL attempts to force common-relative-scale/overlay.

**Exit gate:** Exact-rendition fixture measurements remain within the agreed tolerance and all
negative eligibility tests prove that common-relative-scale/overlay fail closed without changing
the unscaled comparator.

## Change package 9: Confidence-labelled transaction evidence

**Files:**

- Generate: `data/outputs/floor_plan_transaction_matches.csv`
- Extend: floor-plan application matching service
- Extend: library/comparator transaction panel
- Add: ambiguity and public-data-leak tests

- [ ] Reuse stable project IDs and current bedroom provenance.
- [ ] Attach public transactions to a cohort, not a plan, unless the required evidence is available.
- [ ] Keep same-area multi-variant matches as a candidate set.
- [ ] Assign duplicate occurrence indices only after deterministic grouping. If indistinguishable
  rows have conflicting secondary bedroom evidence and no shared source-row ID, publish ambiguity
  instead of attaching evidence by input order.
- [ ] Display sample size, time window, sale state and match method.
- [ ] Keep restricted exact-unit inputs outside public shards.
- [ ] Version the matching algorithm and retain previous generated results for reproducibility.

**Exit gate:** No layout price claim can be read as exact when the underlying match is probable,
ambiguous, bedroom-only or size-only.

## Change package 10: Research-site integration and pilot expansion

**Files:**

- Modify: private-project explorer generator/template/assets
- Modify: `site/reports.json`
- Modify: root index/report discovery
- Modify: `README.md`
- Modify: Pages builder/workflow and tests

- [ ] Add a coverage badge and floor-plan link to existing private-project rows.
- [ ] Keep the plan catalog in on-demand shards instead of expanding the explorer's embedded payload.
- [ ] Register library and comparator reports and their page guides.
- [ ] Keep Chromium installation, non-skipped Playwright/JUnit enforcement and the public-URL
  validator as required CI checks for selection, URLs, rights/scale gates, keyboard and mobile
  behavior; Pages deployment depends on them.
- [ ] Keep scheduled source-terms/grant revalidation and emergency origin-deny/purge independent of
  the analytical pipeline and Pages build. Alert the named operator on overdue review or failure.
- [ ] Add four more rights-cleared projects only after the first-project audit is clean.
- [ ] Measure ingestion time, corrections, comparison completion and asset/takedown incidents.

**Exit gate:** Five to ten complete pilot projects, zero publicly served unlicensed assets and a
documented go/no-go decision for broader coverage.

## How this sequence avoids the named risks

| Risk | Preventive control | Detection | Recovery |
|---|---|---|---|
| Publishing rights | Asset-level active grant and permitted rendition | Projection strips inactive assets; build rejects any exposed prohibited URL | State withdrawal, safe rebuild and purge CDN |
| Unpermitted source link | Metadata-only default; explicit `link_permitted` disposition | Source-origin/terms validator | Remove link while retaining reviewed non-link metadata |
| Provenance | Field assertions plus source page/revision/hash | FK/assertion/hash/attribution reconciliation | Correct with a superseding assertion or revision |
| Mutable identity | Stored opaque IDs; aliases/legacy IDs are separate | Merge-base, collision and reorder-stability tests | Tombstone/supersede; never recycle or rewrite |
| Revision drift | Append-only source revisions and content-addressed renditions | Revision-head, exact-hash and stale-artifact tests | Resolve by date and pin revision in URL |
| False common-relative scale | Reviewed affine calibration bound to exact rendition bytes | Anchor/error/hash/negative eligibility tests | Fall back to fit-to-card unscaled mode |
| Rights/terms expiry outage | Scheduled terms/grant revalidation and metadata-only fallback | Pre-build plus 30/60/90-day review/expiry checks | Withhold the affected fact, link or image according to its independent basis |
| Incorrect exact transaction match | Evidence-ranked match states | Ambiguity/no-fanout tests | Downgrade to candidate/cohort and show reason |

## Pilot verification command shape

The implementation should expose focused commands similar to:

```bash
rtk pytest -q tests/test_private_project_catalog.py tests/test_floor_plan_history.py
rtk pytest -q tests/test_floor_plan_contracts.py tests/test_floor_plan_provenance.py
rtk pytest -q tests/test_floor_plan_vocabulary_contracts.py tests/test_floor_plan_vocabulary_history.py
rtk pytest -q tests/test_floor_plan_vocabulary_logic.py tests/test_floor_plan_vocabulary_publication.py
rtk pytest -q tests/test_floor_plan_rights.py tests/test_floor_plan_calibration.py
rtk pytest -q tests/test_floor_plan_publication.py tests/test_floor_plan_determinism.py
rtk pytest -q tests/test_floor_plan_library_html.py tests/test_floor_plan_compare_html.py
rtk pytest -q tests/test_floor_plan_compare_e2e.py tests/test_pages_site.py
rtk make floor-plan-catalog
rtk make floor-plan-reports
rtk make pages-check
rtk git diff --check
```

The first deployed preview is synthetic-only. Real metadata, permitted links and real images are
three separate later release decisions after their respective counsel/source-terms, rights,
provenance, calibration and emergency-takedown gates pass.
