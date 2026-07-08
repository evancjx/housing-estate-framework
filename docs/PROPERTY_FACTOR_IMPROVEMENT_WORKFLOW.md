# Property Factor Improvement Workflow

This workflow is for adding a new estate or buyer-choice improvement without
breaking the repository's core split:

- Provision answers "what is objectively here?" and remains comparable across
  estates.
- Liveability answers "does this work for this person?" and remains
  persona-relative.
- Value answers "is this priced well for the relevant tenure segment?" and never
  blends HDB and private markets.

The default next improvement is **buyer-requirements intake**: a profile-first
layer that captures real household constraints before presenting Provision,
Liveability, and Value results. It should sit on the Liveability/Value side, not
inside the universal Provision score.

## 1. Orchestrator Intake

Every proposed factor starts as a short proposal before code or weights change.

Required fields:

| Field | Question |
|---|---|
| Factor name | What buyer choice does this explain? |
| Buyer decision | Is it a hard filter, soft preference, risk, future upside, or cost issue? |
| Geography | Estate-level, project-level, block-level, unit-level, or person-specific? |
| Tenure scope | HDB, private, rental, EC, landed, or all segments separately? |
| Time horizon | T0, T5, T15, lease horizon, or exit-liquidity horizon? |
| Data source | Which source produces repeatable data, and how often can it refresh? |
| Evidence | Why should this matter to a real buyer choosing a property? |
| Guardrails | Could this proxy class, status, ethnicity, school ranking, or tenure prestige? |
| Expected output | CSV column, model score, profile filter, audit-only diagnostic, or HTML view? |

Reject or defer factors that cannot answer these fields cleanly.

## 2. Routing Decision

Pick exactly one primary route. Do not duplicate the same factor across multiple
scores unless there is a documented reason.

| Route | Use when | Primary files |
|---|---|---|
| Provision component | Universal, objective, supply-side estate condition | `models/provision_model.py`, `models/framework_config.py`, `frameworks/1-provision-framework.md` |
| Provision sub-metric | Refines an existing component without new top-level weight | `models/provision_model.py`, relevant `models/ingest_*.py`, Provision doc anchors |
| Liveability profile | Depends on household, persona, anchor location, or tolerance | `models/liveability_model.py`, `frameworks/2-liveability-matrix.md`, `data/outputs/life_paths.csv` |
| Buyer intake/filter | Hard constraints before scoring, such as affordability, layout, lease tolerance, school/in-law/care proximity | new profile module, `frameworks/2-liveability-matrix.md`, comparison UI |
| Value segment | Price, affordability, rental fallback, exit liquidity, or tenure economics | `models/value_model.py`, transaction data, segment-specific output columns |
| Momentum/future upside | Confirmed or planned public additions | `data/inputs/pipeline_data.json`, `models/momentum_model.py`, Liveability T5/T15 boosts |
| Temporary disruption | Active construction or temporary inconvenience | D multiplier in `models/liveability_model.py`, `data/inputs/bca_permits.csv` |
| Employment/access | Job-node access or commute opportunity | `models/employment_model.py` |
| Lease risk | Remaining lease and tenure decay | `models/lease_risk_model.py` |
| Project/unit diagnostic | Project, block, floor, facing, layout, view, sun, privacy | private-project tooling or separate diagnostics, not estate Provision |
| Audit-only | Useful context but too narrow, noisy, or not model-ready | `factor_audit_reports/` |

Routing examples:

- Distance to a buyer's parents is Liveability or buyer intake, not Provision.
- Monthly payment comfort is buyer intake or Value, not Provision.
- A new public transport node is momentum/T5/T15, not the D multiplier.
- Construction next door is D multiplier, not positive momentum.
- Floor level, view, and afternoon sun are unit/project diagnostics, not estate
  scores.

## 3. Importance Test

A factor is important enough to include only if it passes all five tests below.

1. Buyer relevance: it changes a realistic buy/no-buy, shortlist, or trade-off
   decision for at least one common household profile.
2. Independent signal: it is not already captured by an existing component, or it
   clearly improves an existing component as a sub-metric.
3. Measurable coverage: data covers most estates or has an honest `no_data`
   path. Missing data must not be silently imputed.
4. Discrimination: it creates meaningful estate differences, not a national
   constant or a near-flat score.
5. Guardrail compliance: it does not launder prestige, income, class, ethnicity,
   school ranking, or tenure-mix bias into the model.

Suggested quantitative thresholds for a prototype:

| Check | Pass signal |
|---|---|
| Coverage | At least 90% of relevant estates, or explicit `no_data` handling |
| Spread | Interquartile range of at least 0.4 on a 1-5 score, or clear tail separation |
| Score movement | At least five estates move by 0.15+ after weight redistribution, or the factor stays as a diagnostic |
| Redundancy | Spearman correlation below 0.75 versus the closest existing component, unless it is intentionally a sub-metric |
| Stability | Same broad result under reasonable anchor or weight sensitivity checks |
| Segment honesty | HDB/private/rental effects reported separately where price or tenure is involved |

For Value-side factors, treat transaction-model lift as evidence, not as a
reason to blend tenure segments. Useful diagnostics include held-out residual
error, transaction coverage by segment, and whether the factor explains price
residuals after property controls.

## 4. Implementation Workflow

1. Write a factor proposal.
   Place the proposal in `factor_audit_reports/YYYY-MM-DD-<factor>.md`.

2. Choose the route.
   Use the routing table above. If the route is ambiguous, prefer a diagnostic
   or buyer-intake layer until evidence is stronger.

3. Define the input contract.
   For a new CSV, specify exact columns, key casing, units, refresh cadence, and
   missing-data behavior before writing model code.

4. Build or update the ingester.
   Use `models/ingest_*.py` for repeatable layer generation. Keep raw external
   access isolated from the scoring model.

5. Prototype scoring anchors.
   Add transparent 1-5 anchors or filter rules. Keep anchors documented and easy
   to challenge.

6. Run a before/after impact review.
   Compare the current output to the prototype output. Report estates with the
   largest movements, band shifts, persona changes, and Value segment changes.

7. Validate importance.
   Apply the importance tests above. If the factor fails, keep the audit report
   and do not wire it into the headline pipeline.

8. Update single sources of truth.
   If weights, S-groups, persona deltas, bands, or provenance change, update
   `models/framework_config.py` and the active framework document in the same
   change.

9. Add tests.
   Cover schema, scorer behavior, doc-code consistency, routing guardrails, and
   any new generated columns. Add snapshot or integration coverage when outputs
   intentionally change.

10. Regenerate outputs intentionally.
    Run `make smoke` first, then `make pipeline` if model outputs should change.
    Explain any CSV changes in the change note.

## 5. Where To Improve This Project

### Highest product-value improvement: buyer-requirements intake

This is the strongest next workflow because real property choices begin with
constraints before scoring:

- monthly payment comfort and affordability buffer
- tenure and lease-risk tolerance
- minimum layout needs, work-from-home space, storage, and kitchen format
- school, in-law, childcare, eldercare, and care-network proximity
- commute anchors to actual workplaces, not just generic connectivity
- lifestyle preferences such as quietness, parks, cycling, beach access, and
  neighbourhood familiarity
- exit liquidity, resale competition, and rental fallback

Recommended route:

- Hard filters constrain the accessible estate/project set.
- Soft preferences adjust Liveability overlays by persona and horizon.
- Cost and liquidity stay in Value, segmented by tenure.
- Condo and landed profiles inherit estate liveability, but their Value evidence
  stays segment-specific instead of borrowing a blended private score.
- Unit-level facts remain diagnostics, not estate Provision.

Implemented first-slice artifacts:

- `data/inputs/buyer_profiles.example.json`
- `models/buyer_profile_model.py`
- `data/outputs/buyer_profile_output.csv`
- `tests/test_buyer_profile_model.py`
- multi-profile JSON support for comparing several household scenarios in one
  run
- `models/private_segment_value_model.py` and `data/outputs/private_segment_value.csv`
  for separate condo and landed private Value evidence
- `models/gen_buyer_profile_html.py` and `buyer_profile_table.html` for a
  filterable profile evaluation table

Remaining product work:

- anchor-specific distance filters for workplaces, schools, in-laws, childcare,
  and eldercare

### Best data-quality upgrades

These improve trust without changing the conceptual model:

- Refresh `pipeline_data.json` through networked ingesters and review S7
  momentum shifts.
- Upgrade remaining PARTLY_MEASURED inputs where possible: `mom`, `dens`, `env`,
  `air_quality`, `stewardship`, and `hawker`.
- Replace aircraft-noise corridor proxy with verified CAAS or official contour
  data if it becomes available.
- Refresh private transaction coverage and separate additional tenure segments
  such as rental, EC, landed resale, and landed rental.

### Best model-quality upgrades

- Add an impact report that prints before/after score movements for any
  candidate factor.
- Add a factor redundancy report against existing Provision components.
- Add profile-level sensitivity checks so a small weight edit cannot quietly
  change buyer recommendations.
- Resolve the known divergence between `framework_config.build_persona_weights`
  and `liveability_model._build_persona_weights` before changing persona
  calibration.

### Best output/product upgrades

- Make `life_paths.csv` and `master_output.csv` easier to query by buyer profile.
- Add profile filters to `comparison_table.html`.
- Surface `no_data`, `not_covered`, and `N/R` explanations in the HTML tables.
- Keep private project diagnostics separate from estate-level scores, but make
  them easier to inspect for project buyers.

## 6. Validation Checklist

Before merging a factor into the pipeline:

- [ ] The route is documented and respects Provision vs Liveability vs Value.
- [ ] The factor has an input contract and provenance tag.
- [ ] Missing or partial data is handled honestly.
- [ ] It passes the five importance tests.
- [ ] Weight changes, if any, sum to 1.0 for public and private weights.
- [ ] Framework docs and model docstrings match code.
- [ ] HDB and private tenure segments remain separate.
- [ ] The D multiplier contains losses only.
- [ ] `make smoke` passes.
- [ ] Regenerated CSV diffs are reviewed and explained.
