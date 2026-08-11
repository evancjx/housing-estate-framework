# Floor-Plan Layout Glossary and Controlled Vocabulary

**Date:** 2026-08-10
**Status:** Proposed vocabulary; legal, architectural and user-testing review required before the
first real-project release

**Related design:** [Property Comparison and Floor-Plan Comparison — Design](superpowers/specs/2026-08-10-property-comparison-floor-plan-design.md)

**Publication policy:** [Floor-Plan Publication, Provenance and Calibration Policy](FLOOR_PLAN_PUBLICATION_POLICY.md)

## Decision

Use a controlled glossary. Do not let analysts, source brochures or browser code invent free-text
layout labels.

The glossary has two jobs:

1. give buyers consistent, plain-language descriptions across projects; and
2. make every filterable claim testable against an explicit evidence rule.

It is not a layout-ranking system. Words such as “efficient”, “spacious”, “private” and “good” are
household-relative judgments unless a separately named, measurable fact supports them. The site
should expose those facts and let the buyer decide.

The glossary standardizes meaning; it is not evidence that a plan has a feature and it grants no
right to inspect, extract or publish a third-party plan. Each real assertion still needs its own
source/use basis and any required metadata-extraction, observation or geometry permission.

## Evidence basis

Official Singapore material supports several narrow terms. URA describes net internal area as
living space excluding voids, balconies, air-conditioner ledges and other external areas, and
describes a Private Enclosed Space as a semi-outdoor area adjacent to a strata unit. SCDF defines a
household shelter by its civil-defence purpose. URA's Form 3 guidance also expects individual spaces,
voids, balconies and air-conditioner ledges to be marked and the actual—not merely mirrored—unit
plan to be provided.

These are evidence references, not republication permissions. Until source-link review is complete,
retain them as non-clickable bibliography:

- URA, *Guidelines on Dwelling Units in Non-Landed Residential Developments*,
  `https://www.ura.gov.sg/guidelines/development-control/development-control-handbooks/residential/flats-condominiums/maximum-number-du/`;
- URA, *Balconies, Private Enclosed Spaces, Private Roof Terraces and Indoor Recreation Spaces*,
  `https://www.ura.gov.sg/guidelines/development-control/development-control-handbooks/residential/flats-condominiums/balconies-pes-prt/`;
- URA, *Guide for Preparation of Form 3*,
  `https://www.ura.gov.sg/-/media/User%20Defined/URA%20Online/Guidelines/Housing-Developers/Guide%20for%20Preparation%20of%20Form%203.pdf?la=en`;
- SCDF, *Technical Requirements for Household Shelters 2023*,
  `https://www.scdf.gov.sg/home/civil-defence-shelter/acts-and-requirements/technical-requirements-for-household-shelters-2023/`.

Marketing terms below are defined by this product only for consistent comparison. They must not be
presented as statutory or industry-standard definitions.

## Governed vocabulary records

Do not place mutable wording, translations and lifecycle state on an identity row. The executable
registry uses normalized append-only records:

| Dataset | Immutable grain and purpose |
|---|---|
| `floor_plan_predicates.csv` | `predicate_id`, stable canonical code, subject type, cardinality and value kind |
| `floor_plan_terms.csv` | Opaque controlled-value `term_id`, predicate ID, stable machine key and creation evidence only; numeric/text predicates need no artificial value term |
| `floor_plan_term_revisions.csv` | Definition, semantic class, inclusion/exclusion rules, allowed evidence bases, filter policy and example/non-example references |
| `floor_plan_term_events.csv` | Reviewed/selected/deselected/deprecated/rejected/disputed/withdrawn state at an effective time, with optional replacement term |
| `floor_plan_term_labels.csv` | Preferred/short/help labels by BCP-47 locale, such as `en-SG`; wording changes never rename an ID |
| `floor_plan_term_aliases.csv` | Search aliases by locale and source scope with `exact`, `context_required` or `manual_only` matching |
| `floor_plan_term_relations.csv` | Scoped `mutually_exclusive`, `requires`, `broader_than`, `related_to` and `replaced_by` relationships |

The tables below list predicate/facet machine keys. An assertion always pins `predicate_id` and
`value_json`; a controlled categorical value additionally pins `term_id` and `term_revision_id`.
It is never reinterpreted using a later definition. A wording clarification creates a revision. A
material change to the inclusion, exclusion or meaning creates a new `term_id`, deprecates the old
term and records a replacement relationship. IDs and machine keys are never reused.

Every generated catalog carries `vocabulary_schema_version` and a content-hashed
`vocabulary_release_id`. Saved filters use predicate/term IDs rather than labels; an old term stays
historical and is shown with a deprecation/replacement notice rather than silently adopting a new
meaning.

### Assertion basis classes

| Basis | Meaning | Public treatment |
|---|---|---|
| `official_disclosed` | Directly stated or labelled in an accepted official source | “Source labels …” |
| `observed_reviewed` | Visible in the accepted plan and confirmed by a reviewer | “Plan shows …” |
| `derived_reviewed` | Calculated from reviewed topology, geometry or disclosed inputs with a versioned method | “Reviewed analysis indicates …” plus method |
| `household_relative` | Depends on furniture, mobility, household routine or preference | Question/decision aid only; never a universal project fact |
| `unsupported` | Marketing adjective or inference without a rule | Do not publish or filter |

### Five-state values

Boolean-looking attributes use `present`, `absent`, `unknown`, `not_applicable` or `conflict`.

- `present` needs positive evidence.
- `absent` needs a complete, legible plan/revision and an evidence rule capable of proving absence.
- `unknown` is the default when the source is incomplete, illegible or silent.
- `not_applicable` means the term cannot apply to that plan, not that it was simply not found.
- `conflict` means current reviewed evidence disagrees; the system does not select a convenient
  answer.

The UI must never convert `unknown` into `absent`.

## MVP vocabulary

For compact tables, `official`, `observed` and `derived` below mean `official_disclosed`,
`observed_reviewed` and `derived_reviewed`. A slash lists bases permitted by the selected term
revision; the actual plan assertion records exactly one basis.

The recommended version-1 coding trial is limited to 18 high-consensus facets: official type code,
bedroom count, bathroom count, en-suite count, total strata area, source-disclosed internal area,
balcony area, PES area, void area, A/C-ledge area, study type, household shelter, yard, store,
kitchen configuration, unit-entry type, bathroom-access summary and bedroom-zone arrangement. The
larger tables are the candidate backlog, not permission to release every filter at once.

### Identity, counts and disclosed area

| Machine key | Public label | Value | Allowed basis | Definition and evidence boundary |
|---|---|---|---|---|
| `plan.official_type_code` | Official type code | string | official | Preserve exact source code and punctuation; it is a label, not the immutable plan identity |
| `plan.official_bedroom_label` | Official bedroom label | string | official | Preserve a source category such as “2 Bedroom + Study”; do not derive it from room shapes |
| `plan.marketing_family_label` | Source marketing family | string | official | Preserve labels such as Premium or Deluxe as source wording, not a quality conclusion |
| `plan.variant_label` | Official variant label | string | official | Preserve the source's distinct variant label within one revision; same area/type does not make plans identical |
| `plan.relationship_type` | Plan relationship | `mirror_related`, `rotation_related`, `alternate_configuration_of`, `related_not_equivalent`, `unknown` | official/observed | Relationship does not collapse IDs, stack exposure or revision history |
| `unit.bedrooms.count` | Bedrooms | integer | official | Count only spaces officially designated as bedrooms; a study/flex room is separate |
| `unit.bathrooms.count_total` | Bathrooms | integer | official | Source-disclosed bathrooms; do not infer a full bathroom from an unlabeled small room |
| `unit.bathrooms.count_ensuite` | En-suite bathrooms | integer | observed/official | Bathroom accessible directly from a bedroom; retain other doors in the access topology |
| `area.strata_total_sqm` | Total strata area | decimal sqm | official | Source-disclosed strata area; retain the original unit and conversion separately |
| `area.net_internal_sqm_official` | Net internal area | decimal sqm | official | Publish only when the source provides a compatible internal-area definition; do not subtract components and call the result official |
| `area.balcony_sqm_official` | Balcony area | decimal sqm | official | Source-disclosed balcony component only |
| `area.pes_sqm_official` | Private Enclosed Space area | decimal sqm | official | Source-disclosed PES component only |
| `area.roof_terrace_sqm_official` | Private roof terrace area | decimal sqm | official | Source-disclosed private roof-terrace component only |
| `area.void_sqm_official` | Void area | decimal sqm | official | Source-disclosed void component; do not treat as usable floor surface |
| `area.ac_ledge_sqm_official` | Air-conditioner ledge area | decimal sqm | official | Source-disclosed A/C ledge component only |
| `area.outdoor_share_reviewed` | Disclosed outdoor-area share | decimal percent | derived | Named included components divided by disclosed total; show formula and leave unavailable when components are incomplete |

Use “total strata area” rather than “usable area”. The latter has no single defensible meaning across
households and source documents.

### Rooms, service spaces and special configurations

| Machine key | Public label | Value | Allowed basis | Definition and evidence boundary |
|---|---|---|---|---|
| `space.study_type` | Study-space type | `open_nook`, `door_enclosed`, `source_label_unclassified`, `absent`, `unknown` | official/observed | Records label and enclosure without calling one a “proper study” |
| `space.flex` | Flex room/space | four-state | official | Use the source's flex label; do not claim bedroom suitability |
| `space.store` | Store room | four-state | official | Enclosed space labelled store/storage; cabinetry alone is not a store room |
| `space.household_shelter` | Household shelter | four-state | official | Space explicitly identified as HS/household shelter; do not relabel it merely as storage |
| `space.utility_room` | Utility room | four-state | official | Separately labelled utility/multipurpose service room; preserve the source term as an alias |
| `space.yard` | Yard | four-state | official | Service area labelled yard; do not infer from appliance symbols alone |
| `space.service_balcony` | Service balcony | four-state | official | Balcony identified for service access/use; keep distinct from the main balcony |
| `space.powder_room` | Powder room | four-state | official | Source labels a WC/powder room without bathing fixture; do not infer fixtures from size |
| `space.walk_in_wardrobe` | Walk-in wardrobe | four-state | official/observed | Bounded wardrobe/dressing space with circulation into it; a wardrobe bank is not enough |
| `living_dining.configuration` | Living/dining arrangement | `combined`, `separate`, `partially_separated`, `source_label_only`, `unknown` | official/observed | Neutral topology; do not translate “combined” into spacious or open-plan quality |
| `configuration.dual_key_official` | Dual-key configuration | four-state | official | Publish only when an accepted source identifies the unit as dual-key or an authorised plan explicitly establishes the configuration |
| `access.unit_entry_type` | Unit entry access | `common_corridor`, `direct_private_lift`, `private_lift_lobby`, `shared_private_lobby`, `unknown` | official | Requires source/stack evidence; a lift symbol alone does not establish exclusive use or ownership |
| `access.private_lift_lobby` | Private lift lobby shown | four-state | official | Separately bounded lobby associated with the unit; the label does not imply ownership of the lift |

“Dual-key” and “private lift” are source-dependent claims. Two entrances or a nearby lift symbol are
not sufficient by themselves.

### Kitchen and food-preparation layout

| Machine key | Public label | Value | Allowed basis | Definition and evidence boundary |
|---|---|---|---|---|
| `kitchen.configuration` | Kitchen configuration | `open_only`, `enclosed_only`, `mixed_open_and_enclosed`, `unknown` | official/observed | One categorical plan-level facet; a plan may have an open dry zone and enclosed wet zone, so separate booleans would be contradictory |
| `kitchen.dry_zone` | Dry-kitchen zone | four-state | official | Source explicitly labels a dry kitchen; an island counter alone is insufficient |
| `kitchen.wet_zone` | Wet-kitchen zone | four-state | official | Source explicitly labels a wet kitchen |
| `kitchen.external_opening_shown` | External kitchen opening shown | four-state | observed | Accepted plan shows a window/opening from kitchen directly to exterior or qualifying open service area |
| `kitchen.direct_yard_access` | Kitchen connects directly to yard | four-state | observed | Door/open connection joins kitchen and labelled yard without crossing another main room |
| `kitchen.island_or_peninsula_shown` | Island/peninsula shown | four-state | observed | Fixed plan symbol is shown; do not imply it is included in sale unless specifications confirm it |

Never replace `kitchen.external_opening_shown` with “well ventilated”. Airflow depends on opening
size, orientation, obstruction and use, which a marketing floor plan normally cannot establish.

### Bathroom access and sleeping-zone topology

| Machine key | Public label | Value | Allowed basis | Definition and evidence boundary |
|---|---|---|---|---|
| `bathroom.access_type` | Bathroom access | `ensuite`, `common`, `jack_and_jill`, `mixed`, `unknown` | observed | Derived from reviewed door-to-space topology, not bathroom position alone |
| `bathroom.external_opening_count` | Bathrooms with external opening shown | integer/unknown | observed | Plan-level count of bathrooms with a direct exterior window/opening; a ventilation shaft is separate |
| `bedroom.zones` | Bedroom-zone arrangement | `single_cluster`, `split_across_common_area`, `other`, `unknown` | derived | Reviewed adjacency graph; no quality judgment |
| `bedroom.door_to_main_living_count` | Bedrooms opening directly to main living/dining | integer/unknown | observed | Plan-level count of bedroom doors that connect directly to the primary living/dining space |
| `bedroom.external_opening_count` | Bedrooms with external opening shown | integer/unknown | observed | Plan-level count with a direct exterior window/opening; does not prove view or airflow quality |
| `entry.buffer_space` | Entrance buffer space | four-state | derived | A bounded circulation/foyer zone lies between the main entry and primary living space under the versioned topology rule |
| `entry.opens_to_main_living` | Entry opens directly to main living/dining | four-state | observed | Main entry connects directly without a separately bounded buffer; do not call this bad privacy |
| `circulation.internal_stair` | Internal stair | four-state | official/observed | Stair within the unit, generally for duplex/multi-level plans |

#### “Dumbbell”

Treat `dumbbell` as a searchable alias, not the canonical claim. The public label is **Split bedroom
zones** and the stored value is `bedroom.zones=split_across_common_area`: sleeping rooms occur in
two separated zones with the primary shared living/dining area between them in the reviewed
adjacency graph. This says nothing by itself about noise, childcare convenience or privacy.

The MVP uses plan-level counts and summaries. Per-bedroom or per-bathroom assertions are deferred
until the canonical model adds immutable `space_id` records and reviewed adjacency/door relations;
array position or room label is not a durable space identity.

### Outdoor, openings and plan relationships

| Machine key | Public label | Value | Allowed basis | Definition and evidence boundary |
|---|---|---|---|---|
| `outdoor.balcony` | Balcony | four-state | official | Space is labelled balcony; use the separately disclosed area when available |
| `outdoor.pes` | Private Enclosed Space | four-state | official | Space is labelled PES; do not collapse it into balcony |
| `outdoor.private_roof_terrace` | Private roof terrace | four-state | official | Source-labelled private roof terrace |
| `opening.ventilation_shaft` | Ventilation shaft shown | four-state | official/observed | Labelled shaft/opening shown; do not describe it as an external view |
| `plan.relationship_mirror` | Mirrored plan relationship | `exact_mirror`, `mirror_with_differences`, `not_mirror`, `unknown` | derived | Compare reviewed topology and exact revision; a source calling one plan “mirror” is evidence, not permission to substitute its image |
| `plan.level_count` | Internal levels | integer | official/observed | Count distinct levels belonging to the same plan; mezzanine status remains source-labelled |

## Later measured vocabulary

These terms require dimensioned or reviewed calibrated geometry and are not MVP filters:

| Machine key | Candidate public label | Requirement |
|---|---|---|
| `geometry.balcony.minimum_depth_m` | Minimum balcony depth | Authoritative dimension or reviewed exact-rendition calibration and boundary |
| `geometry.entry_path_length_m` | Entry-to-living path length | Reviewed doors/path graph and calibrated exact rendition |
| `geometry.internal_circulation_sqm` | Internal circulation area | Versioned segmentation rule, reviewed boundaries and calibration |
| `geometry.circulation_share` | Circulation-area share | Named numerator/denominator and complete reviewed geometry |
| `geometry.room_boundary_type` | Room boundary shape | Versioned categories such as rectangular, rectilinear-nonrectangular or curved; no “regular” score |
| `geometry.structural_intrusion_count` | Structural intrusions shown | Reviewed column/shaft boundary rule; plan completeness required |
| `accessibility.clear_door_width_mm` | Clear door width | Authoritative dimension; never estimated from an uncalibrated marketing plan |
| `accessibility.turning_space_mm` | Turning space shown | Authoritative or reviewed calibrated measurement plus applicable BCA rule version |

Do not claim furniture fit, wheelchair usability or renovation feasibility from apparent image scale.
Those are later scenario-specific checks with dimensions, assumptions and professional caveats.

## Terms that must not be stored as facts

| Avoid | Why | Show instead |
|---|---|---|
| Efficient layout | Undefined and household-relative | Disclosed internal/outdoor shares, circulation metrics and room topology |
| Spacious | Depends on dimensions, furniture and household | Disclosed areas and calibrated room dimensions when available |
| Regular/squarish | Ambiguous | Reviewed boundary type, corner count or intrusion count |
| Wasted space | Value judgment | Entry path/circulation area under a named method |
| Good privacy/private layout | Household-relative | Entry buffer, bedroom-door adjacency and bathroom access |
| Well ventilated/bright | Floor plan rarely proves performance | External openings shown, orientation/obstruction from separate evidence |
| Functional/practical | Undefined | Specific service, storage, access and topology facts |
| Premium/luxurious | Marketing language | Official type/family label shown as a source label only |
| Convertible bedroom | May require approvals and dimensions | Source-labelled flex space plus reviewed dimensions/constraints |
| Huge balcony | Relative adjective | Disclosed balcony area/share and calibrated depth |

Marketing aliases may remain searchable, but the result should route to the neutral canonical term
and show the product definition.

## UI rules

- Show a short definition tooltip and evidence badge beside every glossary term.
- Let users open the source assertion, revision date and assertion basis.
- Filters include only official or reviewed terms; `unknown` and `conflict` remain visible states.
- Comparator rows stay neutral and never add a hidden weighted layout score.
- Household questions may say “may suit people who prefer …” only after the user chooses that
  preference; they do not become project facts.
- Search accepts aliases such as `dumbbell`, `bomb shelter`, `granny room`, `junior master` and
  `private foyer`, but ambiguous aliases require context or manual selection and the result displays
  the canonical label and definition.
- A source's marketing name is shown in quotation marks or as “source label”; it never silently
  changes the canonical value.
- Translation changes labels, not `term_id`, evidence rules or allowed values.

## Implementation plan addition

1. Review a 12–20-term seed subset with one architect/QP, one conveyancing/property lawyer, two
   property analysts and at least five buyers before freezing version 1.
2. Create the normalized predicate, term, revision, event, label, alias and relation CSVs above in
   the `research` zone of `data/catalog.json`.
3. Generate this Markdown glossary and UI tooltips from the accepted vocabulary release so
   definitions cannot drift.
4. Extend field assertions with required `predicate_id` and `basis_type` = `source_disclosed`,
   `reviewed_observed`, `deterministic_derived` or `person_relative`. Categorical claims also pin
   `term_id` and `term_revision_id`; numeric/text claims keep typed `value_json`. Derived claims
   require input assertion IDs and method version.
5. Preserve raw marketing wording as a separate source claim. A source calling a plan “dumbbell”
   does not automatically establish the reviewed topology term.
6. Add contract/history/logic/publication tests for unique IDs/keys, cardinality, valid value types,
   locale+scope alias collisions, multiple selected revisions, self-relations, cycles in
   `requires`/`broader_than`/`replaced_by`, requires-versus-mutually-exclusive contradictions,
   multiple active values in single-valued facets, present-plus-absent conflicts, derived-assertion
   cycles, unknown-versus-absent handling and forbidden subjective predicates.
7. Start filters with the seed objective terms. Keep later measured and household-relative terms out
   until their evidence and user-testing gates pass. A person-relative claim requires household
   context and cannot become a global plan fact.

## Version-1 exit gate

- Every public comparison row resolves to one active `predicate_id` and valid value schema;
  categorical values also resolve to one selected term revision.
- Every categorical assertion pins the selected `term_revision_id`; an old shared URL cannot change
  meaning.
- Every `present` or `absent` value satisfies its evidence/absence rule.
- No unsupported adjective appears as a structured plan fact or filter.
- Historical assertions remain pinned to deprecated meanings. Current UI may show a replacement
  notice; only a true lexical alias may search-route without manual confirmation.
- Definitions, generated documentation and UI tooltips are byte-consistent with the registry.
- Two reviewers independently label the pilot sample with at least 90% agreement or Cohen's kappa
  of at least 0.8; disagreements are adjudicated before filter release.
- Only `en-SG` ships initially. Another locale uses an explicit fallback until a fluent reviewer
  approves its labels and help text.
- Filters show their known denominator plus `unknown` and `conflict` counts, and no vocabulary term
  enters Provision or a hidden/universal layout score.
- Vocabulary review records disagreements explicitly; lack of consensus produces `unknown` or a
  deferred term, not an improvised definition.
