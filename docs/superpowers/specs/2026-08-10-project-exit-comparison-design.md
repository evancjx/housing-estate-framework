# Project Exit Comparison — Design and Evidence Decision

**Date:** 2026-08-10  
**Status:** Phase 1 implemented; later official-data enrichments remain staged  
**Public page:** [Project exit comparison](../../../project_exit_comparison.html)  
**Page guide:** [Project Exit Comparison](../../html-pages/project_exit_comparison.md)  
**Related backlog:** [Property Comparison and Floor-Plan Comparison — Design](2026-08-10-property-comparison-floor-plan-design.md)

## Executive decision

The next public comparison capability is a **rights-light project exit scenario tool built on achieved URA transaction evidence**, not a floor-plan substitute and not another listing portal.

This decision separates two conclusions:

- **Observed fact:** URA exposes official private-residential transactions, developer sales, rental contracts and project-pipeline data through documented services. Transaction records contain project, contract month, area, price, sale type, tenure, floor band and district fields. The official transaction service covers the latest 60 months, and URA states that its API is updated at the end of Tuesday and Friday. See the [URA API reference](https://eservice.ura.gov.sg/maps/api/) and [URA Property Market Information transaction notes](https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch).
- **Product inference:** The repository can deliver a useful same-size exit comparison now because it already has a committed canonical transaction layer and reusable project shards. This meets a real ownership question without acquiring floor-plan drawings, listings or new image rights. It does not establish future saleability or price.

Image-based floor-plan comparison remains a separate, deferred product. No exit-tool milestone relaxes its immutable identity, provenance, revision, calibration or publishing-rights gates.

## Research conclusion

The official-data audit found a technically feasible sequence:

1. Use achieved transaction facts for a transparent same-size cohort and user-controlled exit scenario.
2. Add official project-pipeline and developer-sales context after building authenticated, reviewed ingesters and stable project matching.
3. Add official rental evidence as a separate holding-income lens.
4. Add verified walking, school and financing context without blending these dimensions into one verdict.

The Phase-1 comparison is the flagship because it has the best combination of decision relevance, committed evidence, reproducibility and low publishing-rights risk. This priority is a product judgment, not a measured claim that it is the most-requested feature on the internet.

## Evidence classes and hierarchy

Every published statement must identify which class it belongs to. A value from a lower class must not be presented as though it came from a higher class.

| Level | Claim class | Example | UI treatment |
|---:|---|---|---|
| 1 | Official observed record | URA project, contract month, achieved price, recorded area, sale state | “Recorded transaction”; retain source and coverage date |
| 2 | Deterministic achieved aggregate | cohort median, Q1/Q3, sample count, resale activity count | “Achieved cohort”; display match rules and `n` |
| 3 | Official contextual aggregate | pipeline units, developer launch/sales totals, rental-contract quartiles | Separate lens with source period and denominator |
| 4 | Reviewed spatial derivation | straight-line distance or a OneMap walking route from reviewed points | Label method, endpoint and refresh date |
| 5 | User scenario | entry override, annual growth, holding dates and selling costs | “Assumption” or “scenario”; editable and shareable |
| 6 | Product inference | a caution about evidence depth or supply exposure | Explain rule and limitations; never style as an official fact |

### Conflict and absence rules

- Missing evidence stays missing. Do not substitute a district median for a project cohort without a separate, explicit control.
- An achieved aggregate is valid only for its displayed project, area interval, sale-state filter and analysis window.
- Official contextual data with different grains must remain separate. District pipeline units cannot be treated as a subject project's future competition without an explicit geographic matching method.
- A resale count is transaction flow. Without complete listing inventory and time-on-market data, it is not a sale-probability or marketing-duration measure.
- Current and future evidence are never blended. A planned project or expected TOP is context, not booked value growth.

## Phase 1: implemented scope

The checked-in `project_exit_comparison.html` is a static shell with a compact project catalog. Its external JavaScript fetches only committed transaction shards under `site/assets/condo-transactions/`.

### Canonical evidence window

- Core price metrics use canonical URA rows only.
- The analysis window is the latest 60 **complete** months ending at `source_metadata.canonical.complete_end` in the shard manifest.
- A currently partial month is excluded from the complete-month window.
- The incomplete 2019–2020 EdgeProp backfill remains labelled and is not blended into core metrics.
- The known January–May 2021 gap remains explicit and is not filled.

The generated payload records source reconciliation counts and the exact complete-end month. The page must show the source vintage rather than implying live data.

### Comparable cohort

For target area `A` square feet and tolerance `t` expressed as a decimal, the inclusive area interval is:

```text
area_min = A × (1 − t)
area_max = A × (1 + t)
```

Canonical rows qualify when their project is selected, recorded area is within that interval, contract month is in the 60-complete-month window and sale state matches the selected price cohort. “All sale states” admits the documented URA New Sale, Sub Sale and Resale values.

For each qualifying cohort the page reports:

- achieved total-price median, Q1 and Q3;
- achieved PSF median, Q1 and Q3; and
- transaction count `n`.

These are distribution summaries, not confidence intervals. Same recorded area does not prove the same bedroom count, layout, floor, facing, stack, condition or view.

### Entry baseline and holding period

Each project starts with its achieved cohort median as the entry baseline. The user can override the entry price for that project. The override is a scenario input and does not alter the transaction cohort.

The selected purchase and sale months are converted to the first day of their respective months. Holding years are:

```text
hold_years = (planned_sale_date − purchase_date).calendar_days / 365.2425
```

The planned sale month must follow the purchase month. Using the first day gives deterministic month-input arithmetic; it does not assert an actual completion date.

### Sale and cost scenario

For entry baseline `E`, annual growth input `g` as a decimal, holding years `h`, percentage selling-cost rate `r` and fixed sale costs `C`:

```text
projected_sale = E × (1 + g)^h
selling_allowance = projected_sale × r
scenario_proceeds_before_financing_CPF_and_SSD = projected_sale − selling_allowance − C
scenario_margin_before_holding_financing_CPF_and_SSD = scenario_proceeds_before_financing_CPF_and_SSD − E
```

The three stress rows use `g − 0.03`, `g`, and `g + 0.03`. They are sensitivity cases, not probability bounds.

Break-even metrics are:

```text
break_even_sale = (E + C) / (1 − r)
break_even_CAGR = (break_even_sale / E)^(1 / h) − 1
```

These formulas require `E > 0`, `h > 0`, `g > −1` and `0 ≤ r < 1`. They do not deduct SSD; SSD depends on exact legal dates, while this comparison accepts months. The linked planner receives first-of-month placeholders plus a `datePrecision=month` marker and requires the user to replace them with exact legal dates before relying on its SSD estimate. The browser further constrains the public input ranges. Rounding is presentation-only; calculations retain numeric precision until formatting.

### Recorded resale activity

The activity panel deliberately uses **Resale rows only**, even when the price cohort uses another sale state. It shows:

- recorded resale caveat count in the trailing 12 complete months;
- recorded resale caveat count in the trailing 24 complete months;
- distinct active resale months;
- last recorded resale month; and
- median calendar gap between successive active resale months.

This is a transaction-flow proxy. It has no listing-stock denominator, does not observe failed listings and cannot estimate time to sell. Safe wording is “recorded resale activity”, “active months” and “last recorded resale”; avoid “liquidity”, “demand”, “days on market” and “easy to sell” as factual labels.

### Explicit exclusions

Phase 1 does not calculate:

- BSD, ABSD, SSD or other purchase/sale taxes;
- bank financing, interest, outstanding principal or redemption costs;
- CPF usage, accrued interest or refund allocation;
- maintenance, property tax, insurance, renovation or furnishing;
- rent, vacancy or rental-agent costs; or
- floor-plan, bedroom, stack, facing, view, condition or exact-unit identity.

The net-sale and margin outputs therefore say **before financing and CPF**. A deep-link may hand scenario inputs to the full condo timeline planner, but the exit page must not imply that its simpler margin equals distributable cash or economic profit.

## Wording and interaction constraints

### Use

- achieved / recorded transaction;
- same-size recorded cohort;
- median and interquartile range;
- user-assumed annual change;
- projected scenario value;
- recorded resale activity;
- evidence unavailable or no matching records; and
- before financing, CPF and excluded ownership costs.

### Do not use as output claims

- valuation, fair value or target price;
- predicted, expected or guaranteed sale price;
- guaranteed profit or return;
- liquidity score, buyer demand or time to sell;
- best project, investment grade, recommendation or a universal ordinal position; or
- “same unit” when only recorded area was matched.

Project cards remain in the user's selected A–E order. Do not sort by scenario margin and do not add a single composite score. Copy-view state must preserve inputs, not freeze generated outputs as facts.

## Official-source feasibility and constraints

### Transactions: available now

**Observed official fact.** The [URA API reference](https://eservice.ura.gov.sg/maps/api/) documents a private-residential transaction service returning the past five years in four district batches. Its fields include project, contract date, area, price, property type, tenure, floor range, sale type, district and coordinates. URA recommends retaining the latest five years because older records may be changed or aborted and states a Tuesday/Friday update cadence.

**Coverage constraint.** URA's [transaction-search notes](https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch) state that resale and sub-sale information is based on lodged caveats, caveat lodgement is not mandatory, and some transactions may therefore be absent. New-sale records from 25 May 2015 are based on developer-issued Options to Purchase.

**Licence constraint.** URA's [Singapore Open Data Licence page](https://www.ura.gov.sg/eservices-info/maps/acceptance-grant-licence/) permits use and derived applications subject to conditions, including conspicuous source/licence attribution, no implied agency endorsement and no grant of third-party rights. Public pages must retain attribution and access dates. This licence does not grant rights to unrelated floor-plan drawings or portal content.

### Project pipeline: feasible next phase

**Observed official fact.** The URA API documents `PMI_Resi_Pipeline`, which returns the latest quarter with project, street, district, developer, total units, property-type counts and expected TOP year. It is updated quarterly. URA notes that `expectedTOPYear` may be `na` where developer consent for release was not given. A separate [quarterly national pipeline series on data.gov.sg](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view) provides longer-run aggregate context but is not project-grained.

**Product inference.** Project-level pipeline records can support a labelled “future supply context” view after canonical project matching. District or national supply totals should remain contextual; they cannot become a subject-project penalty without a reviewed catchment definition and denominator.

### Developer sales: feasible after pipeline identity

**Observed official fact.** The URA API documents `PMI_Resi_Developer_Sales` for the past three years, updated monthly. Fields include project, developer, district, total units available, units launched and sold in the month/to date, plus monthly PSF median/low/high.

**Product inference.** The data can show launch inventory and recorded developer-sales absorption as a separate new-sale lens. A sell-through fraction needs its numerator, denominator and reference month displayed. It must not be compared directly with resale caveat activity or treated as future resale demand.

### Rental evidence: feasible as a separate holding lens

**Observed official fact.** The URA API documents five years of rental contracts submitted to IRAS for stamp-duty assessment, with monthly refresh. It includes project, lease month, rent, area band and—where supplied for non-landed property—bedroom count. The official [quarterly project rental summary](https://data.gov.sg/datasets/d_149ac00a2734bb0a03867bbe2ec0e7b0/view) covers major non-landed projects with at least 100 units and at least 10 rental contracts in a quarter and reports rental quartiles and count.

**Product inference.** Rental evidence can support observed rent ranges and a user-defined gross-yield scenario. It cannot establish occupancy, vacancy duration, furnishing condition, net yield or an exact layout match.

### Access and schools: feasible, with boundary cautions

**Observed official fact.** SLA describes [OneMap](https://www.onemap.gov.sg/apidocs/) as Singapore's authoritative national map and documents [walk routing](https://www.onemap.gov.sg/apidocs/routing). Its Barrier-Free Access service is available only by request and only in stated coverage areas, so ordinary walking results must not be labelled wheelchair-accessible. MOE publishes a [school directory dataset](https://data.gov.sg/datasets/d_688b934f82c1059ed0a6993d2a829089/view) with school addresses and levels.

**Product inference.** Reviewed project and station/school points can support straight-line or routed-access diagnostics when method and endpoints are visible. A centroid radius is not official Primary 1 home-school-distance eligibility; that claim must use the applicable official SchoolQuery/boundary method and current registration rules.

## Delivery phases

### Phase 1 — shipped contract

- Static generated shell and external CSS/JavaScript.
- Two to five project selections.
- Canonical 60-complete-month same-size cohorts.
- Achieved price/PSF quartiles and sample counts.
- Editable entry baselines, growth/cost scenario, break-even and ±3 percentage-point sensitivity.
- Resale-only recorded activity diagnostics.
- Shareable URL state, reset, explicit no-data states and full caveats.

### Phase 2 — automated canonical URA refresh

- Build an authenticated four-batch URA ingester outside the browser.
- Store retrieval timestamp, source period, raw-response hash, schema version, row reconciliation and Open Data Licence attribution.
- Replace the rolling five-year canonical snapshot atomically; never append a partial refresh to a complete snapshot.
- Stop on schema, batch, date-coverage, duplicate or reconciliation drift for review.
- Generate the page and shards only from a promoted canonical snapshot.

### Phase 3 — pipeline and developer-sales context

- Ingest the latest project pipeline and monthly developer-sales series with their own source manifests.
- Map records through stable canonical project IDs plus reviewed aliases; unresolved names remain unmapped.
- Display expected TOP only when supplied, with `na` retained as unavailable.
- Keep future supply, launch inventory and resale evidence in separate panels.

### Phase 4 — rental and ownership economics

- Add project/area-band rental-contract evidence with its own coverage rules.
- Add user-controlled rent/vacancy/expense scenarios without labelling them observed net yield.
- Deep-link exact entry, sale and cost assumptions into the condo timeline planner for financing and CPF treatment.
- Do not duplicate the full planner's owner-level loan and CPF waterfall inside the comparison page.

### Phase 5 — reviewed spatial context

- Refresh project geocodes, operational station entrances and school locations from reviewed official sources.
- Add OneMap walking routes with endpoints, retrieval date and fallback states.
- Keep Primary 1 eligibility and barrier-free claims fail-closed unless the exact official method and coverage support them.

## Acceptance gates

- Every headline metric can be reproduced from a named shard, manifest vintage and visible filter state.
- A no-data cohort renders an explanation; it never borrows another project or sale state.
- Project order stays user-controlled and no composite project score is emitted.
- The incomplete backfill and known gap cannot enter canonical metrics.
- Activity wording cannot imply listing stock, time to sell or sale probability.
- Scenario margin is always qualified as before financing, CPF and excluded ownership costs.
- Official-source attribution and licence link are present in the deployed evidence note.
- No floor-plan image, copied listing content or plan-derived fact enters this feature.
