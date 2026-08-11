# Floor-Plan Publication, Provenance and Calibration Policy

**Date:** 2026-08-10
**Status:** Proposed engineering policy; legal review required before any real-project metadata,
external link or asset publication
**Applies to:** floor-plan images, PDFs, thumbnails, transformed derivatives, metadata, source links,
scale calibration and project/plan identity

**Controlled vocabulary:** [Floor-Plan Layout Glossary and Controlled Vocabulary](FLOOR_PLAN_LAYOUT_GLOSSARY.md)

## Purpose

This policy makes floor-plan publication **fail closed**. A floor plan may be useful and its source
may be authoritative, but neither fact proves that this project may copy, transform or publish it.
The system therefore treats five questions independently:

1. What project and logical plan does the record represent?
2. Where did each fact and asset come from?
3. What may this site legally and contractually do with the asset?
4. Which revision is current for the selected analysis date?
5. Is the drawing calibrated well enough for a common-relative-scale visual comparison?

If any required answer is missing, the site withholds the affected image or capability while keeping
safe metadata and, where separately permitted, source links available.

This is a software and data-governance policy, not legal advice. Singapore counsel should review the
rights template and the first public pilot. The policy deliberately uses a stricter operational rule
than attempting to decide fair use asset by asset.

## Official basis

- Singapore's Copyright Act defines a drawing to include a diagram, map, chart or plan. See
  [Copyright Act 2021, section 20](https://sso.agc.gov.sg/Act/CA2021?ProvIds=P12-).
- IPOS explains that drawings may be copyright-protected artistic works and that internet
  availability does not itself grant permission. It recommends permission and a written licence
  stating the scope of use. See [Introduction to Copyright](https://www.ipos.gov.sg/about-ip/copyright/introduction-copyright/)
  and [Ownership and Commercialisation](https://www.ipos.gov.sg/about-ip/copyright/ownership-and-commercialisation/).
- Cropping, tracing or simplifying a plan is not an automatic workaround: IPOS notes that copying
  significant visual elements of an artistic work may still matter. See its [information note on
  designs and copyright](https://www.ipos.gov.sg/docs/default-source/resources-library/design/guidelines-and-useful-information/information-note-on-the-interface-between-registered-designs-and-copyright57c21a77c2d0635fa1cdff0000abd271.pdf).
- URA requires developer-displayed unit plans to be drawn to scale, tied to approved building-plan
  references and to disclose strata-area components. This makes them valuable evidence, but the
  guidance is not a redistribution licence. Bibliographic references: URA, *Housing Developers
  (Show Unit) Rules — Items to Note*,
  `https://www.ura.gov.sg/-/media/Corporate/Guidelines/Developers/HDSUR--Guidelines_Mar-2018.pdf`;
  URA, *Buying Property*,
  `https://www.ura.gov.sg/guidelines/property-and-business-owners/property/buying-property/`.
- BCA limits plan-purchase applications to owners, authorised representatives and specified
  organisations. Access or purchase must not be treated as permission to republish. Bibliographic
  references: BCA, *Plan Purchase System*, `https://www.bca.gov.sg/pps/`; BCA, *Types of applicants
  who can apply to view and purchase the approved building and structural plans*,
  `https://www.bca.gov.sg/pps/Doc/Eligibility%20and%20Supporting%20Documents%20Required.pdf`.
- Even an ordinary external link may be governed by the source site's terms. URA and BCA currently
  require prior permission for links to their websites. Bibliographic references: URA, *Terms of
  Use*, `https://www.ura.gov.sg/terms-of-use/`; BCA, *Terms of Use*,
  `https://www1.bca.gov.sg/terms-of-use/`.

## Non-negotiable rules

1. **No portal copying.** Do not scrape or republish floor-plan assets from 99.co, PropertyGuru,
   EdgeProp, Stacked or another portal without a written licence from the relevant rights holder.
2. **No fair-use default.** Public production assets require an express licence or a reviewed open
   licence. A fair-use argument may only be considered by counsel for a defined case.
3. **No implied submission rights.** A file supplied by an owner, agent or user remains `pending`
   until the submitter's authority and grant are verified.
4. **No access-equals-publication assumption.** A brochure download, BCA plan purchase, viewing
   access or official-source status does not establish hosting or transformation rights.
5. **No silent fallback.** Missing or expired rights produce metadata-only UI, not a copied image
   or unreviewed external link from another source.
6. **No destructive correction.** IDs and revisions are append-only. A correction supersedes; it
   never rewrites the historical record.
7. **No area-based scale claim.** Equal stated floor area is not a scale calibration.
8. **No link-by-default assumption.** A URL is kept internal unless the exact target and any
   redirects pass a current source-terms or written-permission review.
9. **No unlicensed private archive.** Downloading or retaining a source privately requires its own
   lawful basis and, where applicable, the explicit `store_private` operation and retention term.

## Independent evidence records

Every public plan record needs source and field-assertion evidence. Any external link or hosted
asset additionally needs rights/terms evidence. The builder materialises an explicit public
disposition from those independent records.

### Source record: is the information traceable?

Required fields:

```text
source_id
project_id
source_kind
publisher
document_title
document_revision
document_date
source_url_internal
retrieved_at
source_sha256
hash_status
hash_unavailable_basis
```

`source_sha256` is required only when acquisition and private retention are permitted. Otherwise
`hash_status=unavailable` and a reviewed `hash_unavailable_basis` records why no protected copy was
made; the source can still have a weaker bibliographic fingerprint. Page/evidence locators belong on
revision/assertion rows, not on the document-grain source row.

Source verification is an append-only event rather than mutable fields on the source document:

```text
source_event_id
source_id
event_type
effective_at
recorded_at
review_ref
```

`event_type` is one of `official_verified`, `publisher_verified`, `analyst_verified`,
`verification_disputed`, `verification_withdrawn` or `conflict_recorded`. Events are ordered by
`(effective_at, source_event_id)`. A withdrawn verification is not edited back into force; a new
review event with new evidence is required. The derived public status is one of:

- `official_verified` — reconciled to an official developer/authority document;
- `publisher_verified` — confirmed by the developer, architect or appointed project team;
- `analyst_verified` — independently reviewed against the named source;
- `submitted_unverified` — received but not independently confirmed;
- `inferred` — machine or analyst suggestion, never displayed as an official fact;
- `conflict` — sources disagree; public claim withheld pending resolution.

### Source-terms record: may the source be accessed, retained, extracted or linked?

Authority and linkability are separate. Each reviewed terms snapshot is immutable:

```text
source_terms_id
source_id
access_method
terms_url_internal
terms_document_sha256
terms_hash_status
terms_hash_unavailable_basis
observed_at
terms_effective_at
access_policy
automated_access_policy
metadata_extraction_policy
private_retention_policy
external_link_policy
redirect_scope_json
next_review_at
created_at
supersedes_source_terms_id
```

`terms_url_internal` is evidence, not a public link. `external_link_policy` is one of `prohibited`,
`permission_required`, `permitted_exact_target` or `unknown`; `unknown` fails closed. A permitted
link is bound to its exact HTTPS target and reviewed redirect scope, and does not imply permission
to embed, hotlink, proxy, cache, frame or reproduce the target.

Terms review is also append-only:

```text
source_terms_event_id
source_terms_id
event_type
effective_at
recorded_at
review_ref
```

`event_type` is `reviewed`, `rejected`, `disputed` or `withdrawn`. The latest accepted terms
snapshot effective at the build timestamp governs access, private retention, extraction and links.
At or after `next_review_at`, the affected operation fails closed until a new accepted snapshot is
recorded; continued accessibility is not evidence that the old terms still apply.
If terms cannot lawfully be retained or hashed, the reviewed unavailable basis is recorded instead
of downloading a protected copy merely to improve reproducibility. Withdrawal is final for that
snapshot; later terms are represented by a new immutable snapshot, never a reinstatement event.

### Field assertion: which source supports this fact?

A single source row is not sufficient provenance for every bedroom, bathroom, area and feature
field. Store each material claim as an append-only assertion:

```text
assertion_id
subject_type
subject_id
predicate_id
value_json
term_id
term_revision_id
unit
basis_type
source_id
source_page
evidence_locator
extraction_method
method_version
confidence
input_assertion_ids_json
asserted_at
supersedes_assertion_id
```

`subject_type`, `predicate_id`, `unit`, `basis_type`, `extraction_method` and the JSON value shape use
versioned registries rather than free text. `term_id` and `term_revision_id` are required together
for a controlled categorical value and null for a typed numeric/text value. A directly transcribed
fact leaves `input_assertion_ids_json` empty. A derived fact records every upstream assertion ID
plus the deterministic method version; confidence never upgrades an unreviewed inference into an
official fact.

Every public layout assertion must resolve to an immutable active `predicate_id` in the controlled
glossary; a categorical value also pins its selected `term_revision_id`. Marketing aliases are
search aids, not assertion predicates. Unsupported subjective terms such as “efficient”,
“spacious”, “private” or “good layout” cannot enter the structured catalog.

Assertion review is an append-only event rather than a mutable status column:

```text
assertion_event_id
assertion_id
event_type
effective_at
recorded_at
review_ref
```

`event_type` is `reviewed`, `rejected`, `disputed` or `withdrawn`. Events are ordered by
`(effective_at, assertion_event_id)`. Published flat plan records are deterministic
materialisations of accepted assertions effective at the explicit build timestamp. Conflicting
current assertions produce a public conflict/no-data state instead of a guessed value.

### Rights record: what may the site do?

The grant row is immutable:

```text
rights_id
source_id
copyright_owner
licensor_identity
licensor_authority_basis
grant_ref
grant_document_sha256
covered_scope
allowed_operations_json
attribution_text
author_modification_consent_ref
permitted_publication_origins_json
permitted_service_providers_json
permitted_external_link_targets_json
territory
channel_scope
commercial_scope
private_retention_until
deletion_obligations
effective_at
expires_at
created_at
```

Use an immutable junction to bind a grant to one or more exact assets:

```text
rights_asset_binding_id
rights_id
asset_id
asset_sha256
created_at
```

`asset_id` and `asset_sha256` must resolve to the same byte object. A grant does not cover a later
brochure revision or derivative unless its written scope and operation set say so. Private storage
is allowed only while `store_private` and `private_retention_until` remain effective; reaching the
retention deadline produces a deletion obligation, not an implied archive exception.

`allowed_operations_json` is a validated set, not free text. Its initial vocabulary is:

```text
store_private, reproduce, publish, communicate_public,
host_original, host_derivative, cdn_cache,
link_exact_target,
thumbnail, crop, resize, reencode,
browser_resize, viewport_crop, calibrate,
annotate, composite, change_opacity, overlay,
extract_metadata, ocr, vectorize
```

This operation set allows one grant to permit the original and selected derivatives together. A
coarse mutually exclusive `publish_mode` is not a grant field.

Changes in rights state are append-only events:

```text
rights_event_id
rights_id
event_type
effective_at
recorded_at
review_ref
```

`event_type` includes `activated`, `disputed`, `dispute_resolved` and `withdrawn`. Events are ordered
by `(effective_at, rights_event_id)`. `withdrawn` is final for that grant; a scope extension,
renewal or replacement after withdrawal requires a new written grant. `expired` is derived from
`expires_at` and the build date. Projected state precedence is `withdrawn` > `disputed` > `expired`
> `active` > `pending`.

`grant_ref` points to a private contract/register entry. The contract, personal contact information
and negotiation history do not belong in the public repository.

### Private register versus public projection

The schemas above describe the authoritative operational records; they do not imply that real rows
belong in Git. This repository may contain schema definitions and repository-owned synthetic test
fixtures. Real source URLs that are not link-permitted, terms snapshots, licensor identity and
authority evidence, grant hashes/references, private object keys, retention obligations, reviewer
references and blocked hashes stay in access-controlled storage outside the public repository.

A protected publication job reads that register and emits only a minimal public entitlement
projection into the content-addressed project shard:

```text
entitlement_projection_id
asset_id
rendition_id
public_disposition
allowed_client_operations_json
attribution_text
effective_at
expires_at
projected_as_of
projection_schema_version
```

The projection contains no licensor identity, contract reference, internal URL, private storage key
or deletion instruction. Public PR CI exercises the same projector with synthetic fixtures; it does
not receive production-register secrets. A protected deployment or scheduled revocation job must
regenerate the projection from the current private register and refuse stale projection timestamps.

## Rights-state decision table

| Projected state | Derived public disposition | Minimum basis | Public behavior |
|---|---|---|---|
| `active` | `hosted_original` | Exact asset binding plus reproduce/publish/communicate/host-original, origin and provider scope | Serve the approved original hash; browser treatments still need their named operations |
| `active` | `hosted_derivative` | Original basis plus host-derivative and every applied transform operation | Serve only the approved rendition hashes |
| any | `link_permitted` | Current source-terms or written link permission for the exact target path | Ordinary link only; no embed, proxy, cache, frame or hotlink |
| missing or inactive | `metadata_only` | Counsel-approved lawful access/use basis and reviewed factual assertions that reproduce no protected expression | Facts and source description only; no image or source URL |
| `pending` | `withheld` | Review incomplete | No public link or asset |
| `expired` | `metadata_only` or `withheld` | Safe projection plus purge manifest | Remove public asset URL and cached object |
| `withdrawn` | `withheld` | Final grant withdrawal | Immediate takedown and private audit event |
| `disputed` | `withheld` | Credible dispute unresolved | Immediate suppression and cache purge |

The publication builder must derive disposition from the grants, operation set, source terms and
events. Report templates and browser code must never make their own looser rights decision.

### Coverage and public availability are separate

Do not overload one status with both catalog completeness and publication rights. Compute these
orthogonal axes independently:

- `coverage_status` = `complete`, `partial`, `missing` or `conflict`, reconciled against a named
  expected-variant inventory;
- `public_disposition` per exact rendition = `hosted_original`, `hosted_derivative`,
  `link_permitted`, `metadata_only` or `withheld`;
- `calibration_status` per exact rendition = `unscaled`, `calibrated_reviewed` or
  `calibrated_verified`.

A project can therefore be complete but metadata-only, or partial while some captured plans have
hosted derivatives. A project-level visual-availability summary may be `mixed`, but it never
replaces the per-rendition disposition.

## Minimum written-grant checklist

The private rights-grant template should identify:

- the rights holder and their authority to grant the licence, including authority obtained from the
  architect, artist or design agency where the developer is not the copyright owner;
- the covered documents/assets, ideally by title, revision and hash;
- permitted domains and whether a CDN/object-storage provider may serve the files;
- permission to reproduce, publish and communicate the asset to the public;
- whether the original may be hosted;
- permitted derivatives: thumbnail, crop, format conversion, compression, calibration crop,
  annotation, overlay, OCR/metadata extraction and vectorisation;
- required attribution, logo, watermark and notice treatment;
- any author attribution, moral-rights consent or modification approval required for transformed
  versions;
- duration, territory, renewal, withdrawal and takedown process;
- whether historical revisions may remain privately archived for audit;
- whether the grant covers future brochure revisions or requires a new grant;
- a rights-holder contact and escalation route.

Do not remove a source watermark or create a derivative merely because it improves the interface.
The relevant permission must be explicit.

## Source eligibility

| Source situation | Metadata use | Image publication |
|---|---|---|
| Official developer/architect asset with written grant | Yes, after verification | According to the grant |
| Developer/project-team upload with verified authority and grant | Yes | According to the grant |
| Compatible Creative Commons or open licence | Yes, after licence review | According to licence terms and attribution |
| Official brochure available on the internet, no grant | Yes as independently reviewed metadata where lawful | `metadata_only`; add a link only if the terms or written permission allow it |
| Portal-hosted plan, no separate grant | Use only as a research lead | No |
| BCA/URA plan obtained through controlled access | Verification only, subject to access terms | No unless separately authorised |
| Owner/agent/community submission without verified authority | `submitted_unverified` | No |
| Synthetic plan created specifically for UI tests | Yes, labelled synthetic | Yes under the repository's own licence |

Metadata extraction can itself raise contractual or copyright questions when it reproduces a
substantial protected expression. The pilot should capture factual fields conservatively, retain
the source reference internally, publish an ordinary link only when separately permitted, and
obtain counsel review for any bulk source-ingestion arrangement.

## Immutable identities

### Project IDs

- Assign an opaque, immutable `project_id` from the reviewed project registry.
- Allocate the ID once and store it; never regenerate it from a slug, name, district or address.
- Keep the identity registry intentionally minimal:

  ```text
  project_id
  created_at
  creation_ref
  ```

- Store display names, source names, street, district, planning area and other correctable project
  facts as append-only field assertions. Store slugs and name aliases in a separate append-only
  alias map rather than editing the identity row.
- Resolve using project name, street, postal district and planning area; do not resolve by name alone.
- Never recycle an ID after a merger, rename, cancellation or correction.
- Reject ambiguous aliases and duplicate registry keys for human review.
- Preserve old report/query IDs in an append-only legacy-ID map and redirect them to the canonical
  stored ID.

Alias and backwards-compatibility rows use exact namespaces so equal strings from different reports
cannot collide:

```text
project_alias_id
project_id
alias_namespace
alias_value
normalized_value
context_json
source_id
effective_at
created_at
supersedes_alias_id
```

```text
project_legacy_id
project_id
legacy_namespace
legacy_value
created_at
```

Examples of `legacy_namespace` are `two_condo:a`, `two_condo:b`, `multi_condo:p` and
`edgeprop_project_slug`. A legacy value is never reassigned to another project. Alias withdrawal,
identity retirement, split and merge are append-only events:

```text
identity_event_id
subject_type
subject_id
event_type
effective_at
recorded_at
replacement_id
reason_ref
```

`event_type` is `alias_withdrawn`, `identity_retired`, `identity_split` or `identity_merged`, ordered
by `(effective_at, identity_event_id)`. A retired identity remains resolvable; replacement IDs are
additional relationships, not permission to rewrite old URLs or historical assertions.

### Plan IDs

- Assign an opaque, immutable `plan_id` to the logical variant.
- Keep the plan identity row minimal (`plan_id`, `project_id`, `created_at`, `creation_ref`); official
  codes, room counts, areas, labels and relationships are sourced assertions.
- Keep official type code, marketing family, bedrooms, bathrooms and area as separate attributes.
- Never derive the ID from mutable labels or area.
- Same-bedroom, same-area variants receive different IDs.
- Mirror/rotation relationships link records but do not collapse stack or exposure identity.
- A plan split or mistaken merge creates new IDs plus explicit `replaces`/`related_to` links; old IDs
  remain resolvable as superseded.
- Retirement is a tombstone event with reason and optional replacement; an old ID is never deleted
  or recycled.

IDs should look meaningless enough that users do not infer facts from them. Slugs remain convenient
URLs but resolve to IDs and may redirect after a rename.

CI compares protected identity/history rows with an explicit merge-base SHA. Existing primary keys
and protected immutable fields may not be changed or removed; input line reordering is harmless, and
a correction must add a superseding record or event. The workflow therefore needs full base history
(`fetch-depth: 0`) and a table-specific immutable-field allowlist rather than a raw text diff.

## Append-only revisions, assets and renditions

A corrected or newly issued source/document representation of the same built layout creates a new
revision. A materially different room topology, strata boundary or stack applicability creates a
new `plan_id`, even if a publisher reuses the old type code. A crop, resize, compression or format
conversion creates a rendition, not another plan revision.

Immutable revision fields:

```text
revision_id
plan_id
source_id
source_page
source_asset_id
source_asset_sha256
created_at
change_reason
supersedes_revision_id
```

`source_asset_id` and `source_asset_sha256` are required together only when acquisition and private
retention of the source bytes are permitted. A metadata-only revision may leave both null and rely
on the accepted source fingerprint plus page/evidence locator; it cannot produce a rendition or
hosted disposition.

Every original or derived byte object has one immutable asset row:

```text
asset_id
sha256
byte_length
mime_type
storage_class
created_at
```

`storage_class` is a reviewed enum such as `private_original`, `private_derivative` or
`public_rendition`; it is not itself a permission. A private asset still requires effective private
retention authority, while a public asset requires the complete publication disposition.

Immutable rendition fields reference actual asset IDs rather than hashes without foreign keys:

```text
rendition_id
revision_id
parent_asset_id
rendition_asset_id
rendition_sha256
width_px
height_px
transform_schema_version
transform_chain_json
created_at
```

`parent_asset_id` and `rendition_asset_id` must exist in the asset table, and
`rendition_asset_id.sha256` must equal `rendition_sha256`. The versioned transform chain owns crop,
rotation, resize, re-encoding and parent-to-child coordinate transforms. A rendition graph must be
acyclic.

Review and publication selection are append-only events:

```text
revision_event_id
revision_id
event_type
effective_at
recorded_at
review_ref
```

`event_type` is `reviewed`, `selected`, `deselected`, `rejected`, `disputed` or `withdrawn`.
Events are ordered by `(effective_at, revision_event_id)`. The immutable
`supersedes_revision_id` owns revision-graph topology; events own review and publication selection,
so “supersession” is not duplicated as a second mutable state. Do not persist mutable `is_current`,
`review_status` or `superseded_at` fields.

Rules:

- Original assets and public renditions are content-addressed and immutable.
- The current revision is derived from reviewed effective dates; it is not an overwritten file.
- One plan may have brochure, approved-plan and corrected-document revisions simultaneously, each
  retaining source authority and selection status.
- A correction creates a new revision and `change_reason`; it does not edit the old hash.
- Public comparison URLs pin the selected `plan_id` and may optionally pin `revision_id`. If no
  revision is pinned, the UI states which current revision was resolved and on what date.
- A historical comparison must warn when revisions are not contemporaneous.
- A comparison URL pins `revision_id` by default so a saved view does not silently change after a
  brochure correction.
- The revision graph must be acyclic and may resolve to no more than one reviewed publication head
  per plan at an analysis timestamp.
- A revision without one selected, reviewed publication head can remain in the audit catalog but
  cannot emit a hosted asset or be resolved implicitly by a comparison URL.

## Scale-calibration policy

Three public states are allowed:

| State | Requirement | Allowed visualization |
|---|---|---|
| `unscaled` | No defensible pixel-to-distance calibration | Fit-to-card only; explicit not-to-common-relative-scale notice |
| `calibrated_reviewed` | Recorded rendition transform, sufficient independent anchors, tolerance and reviewer | Common-relative-scale side by side and synchronized zoom |
| `calibrated_verified` | Reviewed calibration plus authoritative scale/dimension basis and independent QA | Common relative scale and overlay, subject to transformation rights |

An official printed scale such as 1:100 is evidence, but a resized raster can destroy the original
pixel relationship. The stored calibration must still explain how the pixel-to-distance transform
was established for the published rendition.

Required calibration fields:

```text
calibration_id
revision_id
rendition_id
rendition_sha256
scale_basis
coordinate_system_version
pixel_to_metre_matrix_json
anchors_json
algorithm_version
rms_relative_error
maximum_relative_error
tolerance_policy_version
created_at
```

The affine `pixel_to_metre_matrix_json` is authoritative; X/Y pixels-per-metre summaries are derived
for display and cannot disagree with it. `anchors_json` uses a versioned machine-readable schema
containing pixel coordinates, corresponding real lengths or points, units and anchor IDs—not prose
descriptions. Crop and rotation live in the rendition transform chain rather than being duplicated
on the calibration.

Calibration review is append-only:

```text
calibration_event_id
calibration_id
event_type
effective_at
recorded_at
review_ref
```

`event_type` is `reviewed`, `verified`, `rejected`, `disputed` or `withdrawn`, ordered by
`(effective_at, calibration_event_id)`. The calibration is valid only for the exact
`rendition_sha256`; changing bytes or the rendition transform requires a new calibration record.
A new record may be deterministically derived from a reviewed parent transform, but it still needs
the required review event before publication.

Controls:

- Never infer scale from total floor area, image bounds or matching bedroom count.
- Require at least two independent orthogonal anchors for an isotropic raster. A skewed scan needs
  at least three non-collinear anchors and an affine fit.
- Reject common-relative-scale mode when RMS or maximum relative error exceeds the versioned pilot
  tolerance.
- Reject or explicitly correct source distortion when X/Y calibration differs beyond tolerance;
  never silently stretch one axis to make plans align.
- Preserve the crop in the rendition transform because whitespace and legends affect visual
  alignment.
- Create a calibration for every derivative whose pixel dimensions or crop changes; do not create a
  plan revision for that transformation.
- A new source revision starts uncalibrated until its exact published rendition passes review.
- Require every applied operation—such as `crop`, `calibrate`, `composite`, `change_opacity` and
  `overlay`—in `allowed_operations_json`; no coarse transform flag substitutes for them.
- Disable overlay if any selected revision is unscaled, insufficiently reviewed or rights-ineligible.
- Always show a scale bar and calibration status in common-relative-scale mode. “Common relative
  scale” means the drawings share a defensible ratio to one another in the browser; it does not
  promise a physical printed scale such as 1:100.

## Metadata and visualisation before rights clearance

Development does not need to wait for real images:

1. Build all contracts and browser interactions against original synthetic fixtures that are clearly
   labelled and unlike a copied commercial plan.
2. Ingest real-project variant names and conservative factual metadata only after source review.
3. Publish real projects initially as `metadata_only`; upgrade to `link_permitted` only after the
   source terms or written permission allow that specific link.
4. Add licensed assets one project at a time after the asset hash and rights record pass.
5. Enable calibrated comparison independently for each reviewed revision.

Do not manually trace or redraw a protected commercial floor plan for the prototype unless the
licence expressly permits derivative works. A traced redraw can still create rights risk.

## Build-time publication gate

The builder first projects every record to its safe public state at an explicit `--as-of` timestamp.
An expired, withdrawn or disputed grant must produce a successful metadata-only replacement plus a
mandatory purge manifest; failing the whole replacement build could leave the old deployed asset
live. The build fails if the serialized replacement still violates one of these checks:

- no stable project, plan, revision or source ID for a displayed record;
- no effective rights ID and exact asset binding when a hosted asset or rights-dependent extraction
  is emitted, or no effective `source_terms_id`/written-permission record when an external link is
  emitted; independently reviewed metadata-only facts do not require a synthetic rights record, but
  they do require the reviewed lawful-use basis specified above;
- a required source, hosted asset or public rendition hash missing; a reviewed metadata-only source
  may instead carry `hash_status=unavailable` and its unavailable basis;
- an image/embed URL remains when rights are not active on the build date;
- public origin not permitted;
- requested original, rendition or browser treatment lacks every named operation in the grant;
- external link emitted without a reviewed exact-target `link_permitted` disposition;
- a public URL is not HTTPS, contains credentials, resolves outside its reviewed redirect scope or
  uses an unallowlisted host;
- OCR/metadata extraction or vectorisation performed where the source terms/grant require and do
  not provide that permission;
- attribution required but missing;
- source/revision foreign key missing or conflicting;
- multiple current reviewed revisions without an explicit selection rule;
- common-relative-scale or overlay flag without reviewed calibration;
- public metadata contains a private grant reference, local path or restricted exact-unit field.

The static HTML/JavaScript consumes only builder-approved public JSON. It cannot construct a CDN URL
from an asset ID or bypass the gate.

All event projections use timezone-aware instants normalized to UTC, with the event-specific ID as
the deterministic tie-breaker after `effective_at`. `recorded_at` records audit arrival and does not
silently replace effective-time ordering.

Public JSON is generated deterministically and promoted atomically:

- one project-addressed shard path contains a content digest;
- manifest and shard records are sorted by immutable IDs and serialized as UTF-8 with
  `sort_keys=true`, compact separators, `allow_nan=false` and exactly one final newline;
- the manifest records every shard path, SHA-256, count and schema version;
- the build uses an explicit analysis timestamp rather than uncontrolled wall-clock time;
- `catalog_sha256` is calculated from the schema version, normalized analysis timestamp and ordered
  list of project shard paths/hashes/counts; it excludes itself and any volatile generation time;
- generation occurs in a new content-addressed generation directory, all hashes, counts and
  allowlists are validated, and the atomic `current.json` pointer is written last. A fresh GitHub
  Pages artifact deployment may provide the same all-or-nothing boundary. Do not assume that
  `os.replace` can replace a non-empty directory;
- only files reachable from the accepted manifest are published; stale/orphan shards are rejected
  and omitted from the promoted generation;
- CDN and permitted-source origins use an explicit allowlist, and the new pages use a restrictive
  Content Security Policy.

For a filesystem publication, the stable `current.json` is only a canonical pointer:

```json
{
  "schema_version": 1,
  "catalog_sha256": "...",
  "generation_manifest": "generations/<catalog_sha256>/manifest.json",
  "generation_manifest_sha256": "..."
}
```

The generation manifest owns the ordered project-shard inventory and reconciliation counts. The
builder writes and validates the complete `generations/<catalog_sha256>/` tree first, verifies the
generation-manifest hash, then atomically writes the small pointer file with the shared
`atomic_write_text` pattern. Readers verify both hashes before accepting the generation. Garbage
collection never removes the currently referenced generation; a fresh Pages artifact includes only
the accepted pointer and its reachable generation.

The existing Pages link checker ignores remote URLs, so floor-plan JSON requires a dedicated remote
origin validator. It validates the final target as well as configured redirects and rejects
`javascript:`, `data:`, `blob:`, credential-bearing and non-HTTPS public URLs. Browser code receives
only complete builder-approved URLs. Hosted drawings use reviewed inert raster formats; SVG, HTML
or PDF content is not embedded as an image unless a separate active-content security review allows
it.

## Review workflow

Use separation of duties:

- **Ingest reviewer:** confirms project, source page, variant and factual fields.
- **Rights reviewer:** confirms grant authority, scope, dates and public rendition.
- **Calibration reviewer:** records scale basis, anchors, crop and error.
- **Independent QA reviewer:** checks the published metadata and visual result.

For the pilot, the same person may perform ingest and calibration, but rights approval and final QA
must be performed by someone else. The public record shows status and dates, not reviewer personal
details.

## Expiry, correction and takedown

- Run daily or pre-build rights-expiry and source-terms `next_review_at` checks, plus a weekly
  30/60/90-day grant-expiry/terms-review report.
- Run a scheduled daily rights/source-terms projection and safe rebuild independently of the
  analytical pipeline.
- Bound CDN cache TTL by the remaining grant term so an expiry cannot outlive a cached response.
- Provide an emergency takedown workflow that resolves a reviewed `rights_id` or `asset_id` to exact
  immutable object keys, shows a dry run, requires protected-environment approval, and can purge
  without waiting for unrelated model/report tests. It must not accept an arbitrary bucket prefix.
- On withdrawal or credible dispute, append a `withdrawn` or `disputed` event, rebuild public
  metadata, purge CDN paths and verify that direct asset URLs no longer resolve.
- Add every disputed/withdrawn asset hash to a private blocked-hash registry until documented
  resolution prevents accidental re-upload.
- Withdrawal is final for that grant. Do not add a reinstatement event; renewed authority is a new
  grant and new exact asset binding.
- Enforce private-retention deadlines and deletion obligations separately from public CDN purge;
  audit storage deletion without committing the protected binary or contract.
- Keep the old hash and audit event privately; do not leave the binary in Pages history.
- Corrections create new metadata/revision records and link to the superseded record.
- Test the takedown procedure before the first launch and at least quarterly thereafter.
- Publish a correction/contact route that accepts stable project/plan/revision IDs.
- Treat voluntary suppression and takedown as risk controls only. They do not retrospectively
  authorise an earlier publication or guarantee that any statutory safe-harbour regime applies.

## Public status language

Use precise labels:

- **Official source verified** — source authority, not ownership by this site.
- **Rights-cleared rendition** — an active grant from a reviewed authorised licensor covers the
  exact displayed hash, publication origins, service providers and applied operations.
- **Permitted source link** — an ordinary link is allowed; the site does not host or embed the
  drawing.
- **Metadata only** — the database records the variant but publishes neither drawing nor source URL.
- **Revision current as of DATE** — never simply “latest”.
- **Not shown to a common relative scale** — default for uncalibrated plans.
- **Common relative scale, reviewed DATE** — eligible calibrated comparison; not a promise of a
  physical printed scale.
- **Candidate transaction cohort** — not an exact layout match.

Do not use “verified” without naming whether it refers to source, rights, calibration or transaction
matching.

## Required automated and CI controls

- Source, assertion, revision, rights and calibration event projection, including deterministic
  same-time ordering, time-zone boundaries and final withdrawals.
- Source-terms exact-target/redirect policy, private-retention authority and prohibited/unknown link
  states.
- Rights-state and public-disposition decision table; coverage status remains orthogonal.
- Expired/withdrawn assets disappear from public JSON and appear in mandatory CDN purge manifests.
- `link_permitted` never exposes an embed, proxy, hotlink, cached copy or image URL.
- `metadata_only` never exposes a source URL or enough asset information to reconstruct one.
- IDs remain stable under source reordering, aliases and display-name changes.
- PR CI checks out full Git history and passes an explicit base SHA to the merge-base history check;
  protected-field comparison rejects a changed/deleted immutable row but accepts input reordering
  and a superseding event.
- Legacy shared IDs resolve to the same project and canonicalize without breaking the URL.
- Duplicate identities and aliases fail closed.
- Revisions are append-only and exactly one current reviewed revision is resolved.
- Revision graphs reject cycles and multiple reviewed publication heads.
- Source and rights foreign keys, hashes and attribution reconcile.
- Every displayed material field resolves to a reviewed assertion; conflicts render no-data.
- Asset/rendition foreign keys, hashes, byte lengths, acyclic transform chains and private-storage
  permission reconcile.
- Calibration affine math, coordinate/anchor schema, two-anchor minimum, tolerance and
  transformed-rendition calibration.
- Calibration cannot attach to a different rendition hash; skewed/collinear anchor fixtures fail.
- Uncalibrated or rights-ineligible selections cannot activate common-relative-scale/overlay mode.
- URL parameters cannot bypass scale, rights or overlay eligibility.
- Canonical project shards are byte-identical after input permutation for the same normalized
  `--as-of`; serializer, per-shard hashes, catalog hash and manifest-pointer promotion reconcile.
- Only allowlisted CDN/source origins pass; Content Security Policy blocks other image origins.
- Public shards contain no contract references, local paths or exact-unit data.
- A complete takedown fixture proves metadata rebuild, blocked-hash behavior and that the revoked
  object is no longer directly reachable.
- The emergency takedown workflow accepts only reviewed IDs, resolves exact object keys, supports a
  dry run and requires protected-environment approval.
- Comparator browser tests install and launch Chromium in an enforced CI job; a missing Playwright
  dependency or browser is a failure, not an `importorskip` success.

## Questions for Singapore IP counsel

Before the first real-project release—including metadata-only—obtain written advice on:

- the licence template and proof that a developer/publisher may license architect-created plans;
- independent schematic redraws and whether the proposed method creates a derivative work;
- OCR/computer-vision extraction and which factual metadata may be published;
- user, owner and agent submissions and the evidence needed to verify grant authority;
- deep-linking to common government, developer, agency and portal sources under their terms;
- author attribution, moral-rights treatment and consent for crop, annotation and overlay;
- the dispute/takedown process and whether any additional statutory process applies.

## Governance review cadence

- Review policy and licence template before the first public pilot.
- Review rights and calibration status before every release.
- Audit a random sample of published plans monthly during the pilot.
- Revisit the policy whenever the hosting origin, commercial model, submission flow or asset source
  changes.
- Stop new publication if the rights register, expiry check or takedown mechanism is unavailable.
