# TODO

## Deferred Product Backlog

### Image-based floor-plan library and comparison

**Decision date:** 2026-08-10

**Status:** Deferred; research and implementation design are retained, but delivery is not scheduled.

The intended feature is a public, evidence-backed library that lets users visually compare two to
four actual floor-plan images. A metadata-only catalogue, text-only comparison, abstract diagram or
bring-your-own local-image tool does not deliver the complete user value and must not be presented
as the floor-plan comparison MVP.

Resume this backlog item only when:

- written permission has been obtained from the relevant developer, architect or other authorised
  rightsholder for a useful pilot set of projects;
- the permission covers public hosting, CDN/cache delivery, thumbnails, resizing, synchronized
  zoom/pan and every comparison or overlay operation that will be offered;
- exact project, plan, revision, rendition and rights records can be published with provenance and
  a tested withdrawal/takedown path; and
- the resulting pilot has enough real plan variants to test whether image comparison is valuable
  to users, rather than demonstrating only a synthetic or incomplete experience.

Do not scrape, screenshot, hotlink, trace or AI-redraw floor plans from property portals or public
brochures as a substitute for permission. Metadata and controlled vocabulary work may be retained
as supporting research, but should only be implemented when it directly supports the rights-cleared
visual comparator.

Retained backlog documentation:

- `docs/superpowers/specs/2026-08-10-property-comparison-floor-plan-design.md`
- `docs/superpowers/plans/2026-08-10-property-comparison-floor-plan.md`
- `docs/superpowers/plans/2026-08-10-floor-plan-comparison-safe-pilot.md`
- `docs/FLOOR_PLAN_PUBLICATION_POLICY.md`
- `docs/FLOOR_PLAN_LAYOUT_GLOSSARY.md`

## Buyer-Requirements Intake

- [ ] Add a decision-profile intake for real buyer criteria observed in Stacked Homes articles.
  Keep this on the Liveability/Value side: hard filters constrain the accessible set, soft criteria
  weight persona/horizon overlays, and tenure segments remain separate.

Hard filters:
- Monthly-payment comfort, affordability buffer, and cash-over-valuation tolerance.
- Minimum usable layout: bedrooms, work-from-home space, storage, yard, enclosed kitchen, WC/helper bathroom.
- Tenure and lease-risk tolerance.
- School, in-law, and care-network proximity.

Scored preferences:
- Daily commute fit, including transfers and travel time to specific anchors.
- Unit micro-positioning: floor, facing, afternoon sun, privacy, view, road noise, expressway/MRT noise.
- Facilities fit for household stage.
- Lifestyle fit: parks, cycling, beach access, hosting, neighbourhood familiarity, quietness.
- Master-plan upside and future amenities.
- Exit liquidity: future buyer pool, resale competition, rental fallback, and upgrader affordability.

Research references:
- `https://stackedhomes.com/bedok-south-million-dollar-hdb-buyer-case-study/`
- `https://stackedhomes.com/hillington-green-upgrader-case-study/`
- `https://stackedhomes.com/hundred-palms-riverfront-residences-tampines-trilliant-2/`
- `https://stackedhomes.com/the-gardens-at-bishan-or-amo-residence-growing-family/`
- `https://stackedhomes.com/vela-bay-condo-review/`
- `https://stackedhomes.com/new-launch-condo-resale-exit-strategy-risk/`
