# East Village — residential resale inventory, mixed-use risks and potential-quantum analysis

Research captured: **2026-07-30 22:58:07 SGT (UTC+08:00)**  
Property: **East Village, 430–432 Upper Changi Road, Singapore 487048/487049**  
Analysis type: **property resale inventory, valuation and investment analysis**  
Status: **point-in-time market snapshot**

## Decision

East Village has **format-specific potential**, not one project-wide bargain.
Its freehold tenure, low-ticket apartments and food/retail podium can support
tenant demand, but the same mixed-use setting creates noise, odour, access and
resale-pool risks.

Three current public sale cards produce very different conclusions:

1. The **409 sqft one-bedroom at S$738,000, or S$1,804 psf**, is the most
   credible low-ticket inspection lead. Its ask is below the S$758,000 caveat
   achieved by the same rounded area in July 2023, although that old row is not
   confirmed as the same unit and does not establish today's value.
2. The **506 sqft one-bedroom at S$950,000, or S$1,877 psf**, looks stretched.
   A 506 sqft unit achieved S$709,000, or S$1,401 psf, in February 2026.
   Condition and floor can differ, but a 34% quantum premium requires unusually
   strong evidence.
3. The **1,206 sqft two-bedroom near S$1.45m, or S$1,202 psf**, is broadly
   consistent with a 1,270 sqft S$1.449m April 2026 caveat, but above the
   S$1.33m achieved by the same rounded 1,206 sqft format in December 2025.
   An entry around S$1.32m–S$1.38m is more attractive.

Do not compare the large and compact units on PSF alone. The committed sample
shows a persistent size split: compact apartments carry higher PSF, while
1,001–1,300 sqft homes trade around a lower project sub-market.

For the 1,206 sqft family-sized candidate, the conditional entry ladder is:

- **At or below S$1.32m:** potentially compelling, subject to usable area and
  mixed-use due diligence.
- **S$1.32m–S$1.38m:** defensible.
- **S$1.38m–S$1.45m:** fair only for strong condition, quiet aspect and a clean
  plan.
- **Above S$1.45m:** weak investment entry without exceptional attributes.

Under a representative **S$1.35m** negotiated purchase, the acquisition basis
is about S$1.3936m after S$38,600 BSD and S$5,000 legal/technical allowance.
A S$500,000 capital-only profit requires a S$1.942m exit after 2.5% selling
friction—about 7.54% annual sale-price growth over five years or 4.65% over
eight. That is not a prudent base forecast.

The project therefore has **moderate selective potential**, strongest in a
verified S$738,000 compact lead or a negotiated large apartment. It does not
have high-confidence huge risk-adjusted quantum at the visible S$950,000
compact ask.

## Scope and evidence rules

This is a property analysis, not a factor audit, formal valuation or
cross-tenure ranking. It separates:

- **Residential sale asks** from achieved residential caveats;
- **commercial podium facts** from the residential investment thesis;
- **size-format sub-markets** rather than pooling compact and large units;
- **rental contracts** from net cash flow; and
- **underwriting scenarios** from predictions.

The official transaction starting point is
[URA Property Market Information](https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch).
The public window covers the latest 60 months. Caveats lodged with SLA are
voluntary and are not a complete deed or ownership ledger.
[URA REALIS coverage and methodology](https://eservice.ura.gov.sg/reis/coverageandMethodology)
sets out the broader basis.

## Project identity and mixed-use form

The
[current 99.co East Village page](https://www.99.co/singapore/condos-apartments/east-village)
reports:

| Attribute | Captured identity |
|---|---|
| Address | 430 and 432 Upper Changi Road |
| Tenure | Freehold |
| Completion / TOP | 2014 |
| Residential units | 90 |
| Residential bedroom formats | One to three bedrooms |
| Developer | World Class Developments (Bedok) Pte Ltd |
| District / segment | District 16 / OCR |

East Village is not a conventional all-residential condominium.
[EdgeProp's completed-project description](https://www.edgeprop.sg/property-news/east-village-comes-its-own-strata-owners-offer-bulk-sale-units-83-mil)
states that the freehold development has **108 strata-titled shops on the
first level and 90 apartments above**. A later
[2025 portfolio article](https://www.edgeprop.sg/property-news/portfolio-15-freehold-strata-units-east-village-market-718-mil)
also describes 90 homes above a 108-shop retail podium and completion in 2014.

The public sources differ on whether the overall building is described as four
or five storeys, likely because of podium/storey-count conventions. That
wording does not change the tenure or unit counts, but exact residential level,
access route and legal strata configuration must be checked from title and
approved plans.

This report covers only **residential** units. It does not blend commercial
shop transactions, commercial financing, GST or stamp-duty treatment into the
residential evidence.

## Live residential sale inventory

At capture, the
[dedicated 99.co residential sale result](https://www.99.co/singapore/sale/condos-apartments/east-village)
showed three cards, while the general project page said around five units were
being marketed. The dedicated result is:

| Reported format | Reported area | Asking price | Asking PSF | Nearest achieved context |
|---|---:|---:|---:|---|
| One-bedroom compact | 409 sqft | S$738,000 | S$1,804 | 409 sqft achieved S$758,000 / S$1,853 psf in Jul 2023 |
| One-bedroom | 506 sqft | S$950,000 | S$1,877 | 506 sqft achieved S$709,000 / S$1,401 psf in Feb 2026 |
| Two-bedroom large / penthouse-marketed | 1,206 sqft | S$1.45m | S$1,202 | 1,206 sqft achieved S$1.33m / S$1,103 psf in Dec 2025 |

The S$1.45m dedicated card was displayed as S$1.47m on the project summary at
one point in the same sweep. This illustrates why a portal result is a
timestamped advertisement, not an executable seller ledger.

Raw portal totals can include relists, co-broking cards, stale caches and the
same physical unit at different prices. Before calling any card “available”,
obtain:

- current written seller authority and viewing availability;
- block, level and stack;
- subsidiary strata lot and exact strata area;
- occupancy and tenancy status; and
- a dated asking-price confirmation.

## Captured achieved residential ledger

The repository's `data/inputs/ura_private.csv` was filtered to:

- project name exactly **EAST VILLAGE**;
- sale type exactly **Resale**;
- captured caveat month from **August 2021 through April 2026**; and
- residential non-landed observations only.

The result is **22 captured resale caveats**. Areas below are rounded after
conversion from URA sqm.

| Size segment | Caveats | Captured window | Achieved quantum range | Median achieved PSF |
|---|---:|---|---:|---:|
| Up to 600 sqft | 8 | Aug 2021–Feb 2026 | S$590k–S$758k | S$1,420 psf |
| 601–1,000 sqft | 5 | Nov 2021–Sep 2025 | S$875k–S$1.06m | S$1,442 psf |
| 1,001–1,300 sqft | 7 | Dec 2021–Apr 2026 | S$1.275m–S$1.525m | S$1,122 psf |
| 1,601–1,700 sqft | 2 | Sep 2021–Nov 2022 | S$1.495m–S$1.70m | S$958 psf |

The recent captured rows are:

| Caveat month | Rounded area | Achieved price | Achieved rate |
|---|---:|---:|---:|
| Sep 2025 | 883 sqft | S$1.060m | S$1,201 psf |
| Dec 2025 | 1,206 sqft | S$1.330m | S$1,103 psf |
| Feb 2026 | 506 sqft | S$709,000 | S$1,401 psf |
| Apr 2026 | 1,270 sqft | S$1,448,888 | S$1,141 psf |

The current
[public transaction display](https://www.99.co/singapore/condos-apartments/east-village)
shows the same rows. These achieved prices do not reveal view, ceiling height,
outdoor allocation, renovation, noise or tenancy.

A repeated rounded size is not necessarily a confirmed repeat-sale unit. One
captured 506 sqft observation was S$658,000 in September 2021, versus
S$709,000 for the same rounded area in February 2026, only about 1.7% gross
annualised. There was also a second September 2021 observation at S$690,000.
A 409 sqft cohort moved from S$590,000 in August 2021 to S$758,000 in July
2023. The divergence is a warning against applying one compact-unit growth
rate to every plan.

## Format-specific valuation

### Compact 409 sqft

The S$738,000 ask is below the July 2023 achieved quantum for the same rounded
area and approximately S$1,804 psf. It is the best apparent low-ticket lead,
but it can still be poor value if:

- the 409 sqft includes inefficient space;
- food, road or mechanical-plant noise is intrusive;
- mortgage valuation is below price;
- current rent or occupancy is overstated; or
- the card is stale.

### Standard compact 506 sqft

The current S$950,000 ask versus February 2026 achieved S$709,000 is a
S$241,000 gap. No project-level trend bridges that gap in five months. A
premium may exist for floor, renovation, quiet facing or tenancy, but the
seller must evidence it. An analytical negotiation range around
**S$720,000–S$790,000** is more consistent with captured caveats than
S$950,000, subject to unit specifics.

### Large 1,206 sqft

The large format trades at materially lower PSF. The December 2025 S$1.33m
and April 2026 1,270 sqft S$1.449m caveats bracket a useful current read. The
S$1.45m ask is not obviously irrational, but it leaves little entry discount.
Targeting **S$1.32m–S$1.38m** protects against plan inefficiency and mixed-use
resale friction.

## Rental fallback

The project's
[URA-derived rental display](https://www.99.co/singapore/condos-apartments/east-village)
shows substantial format dispersion:

| Recent broad format | Example 2026 observed rents | Analytical use |
|---|---:|---|
| 400–500 sqft one-bedroom | S$2,750–S$3,000 monthly | Proxy for 409 sqft, not 506 sqft automatically |
| 500–600 sqft one-bedroom | S$2,300–S$2,800 monthly | Proxy for 506 sqft |
| 1,200–1,300 sqft two-bedroom | S$3,300–S$3,700 monthly | Proxy for the large advertised unit |
| 1,600–1,700 sqft three-bedroom | S$4,200 monthly | Separate scarce format |

At S$738,000, S$2,750–S$3,000 implies approximately **4.47%–4.88% gross**
before all costs. At a S$1.35m large-unit entry, S$3,300–S$3,700 implies only
**2.93%–3.29% gross**. The low-ticket rental case is stronger, but tenant
turnover, furnishing and mixed-use environment can consume much of the
difference.

Neither range is net yield. Deduct vacancy, agent fees, maintenance, repairs,
property tax, insurance, furnishing and financing.

## Access and surrounding pipeline

A coordinate-to-coordinate screen places East Village approximately **0.51 km
in a straight line** from Tanah Merah MRT. It is not a gate-to-platform route
or walking-time claim. The current dedicated portal card displays about
504 m, while its search header has displayed a materially longer estimate.
Walk both blocks' actual residential entrances and crossings.

Locations can be checked through
[OneMap](https://www.onemap.gov.sg/) and its
[Tanah Merah MRT search endpoint](https://www.onemap.gov.sg/api/common/elastic/search?searchVal=Tanah%20Merah%20MRT&returnGeom=Y&getAddrDetails=Y&pageNum=1).

Catalysts include existing EWL access, nearby daily retail and the future
mid-2030s extension/conversion that will link Tanah Merah to TEL.
[LTA's official announcement](https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/7/news-releases/TELe_and_CRL_changi_airport_to_city_centre.html)
describes that long-horizon airport and city connection.

The competitive pipeline is substantial:

- URA
  [awarded the Bedok Rise residential site](https://www.ura.gov.sg/news/media/pr25-66/),
  which it
  [estimated could yield about 380 homes at tender launch](https://www.ura.gov.sg/news/media/pr25-48/);
- the
  [New Upper Changi Road site near Bedok MRT](https://www.ura.gov.sg/news/media/pr26-38/)
  can yield about 1,010 homes; and
- the
  [Bayshore Drive award](https://www.ura.gov.sg/news/media/pr26-55/)
  covers a mixed-use site
  [described at launch as a potential 1,280 homes integrated with Bedok South MRT, a bus interchange and retail](https://www.ura.gov.sg/news/media/pr26-23/).

The old Tanah Merah Kechil Link GLS page refers to the parcel developed as
Sceneca Residence, **not another future Kechil Link project**.

## Investment risks

- **Mixed-use externalities:** cooking exhaust, deliveries, refuse, late
  activity, plant equipment and visitor circulation are stack-specific.
- **Compact-unit valuation risk:** one-bedroom seller PSF can exceed what the
  bank or next buyer accepts.
- **Large-unit inefficiency risk:** low PSF is not value if much of the strata
  area has weak utility.
- **Small residential pool:** 90 apartments and thin matched transactions
  reduce price discovery.
- **Retail governance exposure:** commercial ownership and use can affect
  common-property priorities, access and levies; legal structure must be read,
  not assumed.
- **Portal inventory ambiguity:** three current cards and “around five”
  project-page inventory are not reconciled physical units.
- **Competing new supply:** efficient new plans can pressure an older mixed-use
  project's resale pool.

[URA's 2Q2026 statistics](https://www.ura.gov.sg/news/media/pr26-57/)
reported overall private prices up 0.5% quarter on quarter, but OCR non-landed
prices down 0.1%, OCR non-landed rents down 0.3%, completed-private-home
vacancy at 6.4% and about 60,600 units including ECs expected to complete over
coming years. Use the sub-market softness and supply as downside tests.

## Capital-only return test

The representative large-unit illustration assumes:

- purchase price: **S$1.350m**;
- **Singapore citizen (SC) buying a first residential property**, the SC
  first-property baseline with no ABSD;
- BSD: **S$38,600**, under
  [IRAS's current residential BSD tiers](https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-acquiring-property/buyer%27s-stamp-duty-%28bsd%29);
- acquisition legal/technical allowance: **S$5,000**;
- acquisition basis: **S$1.3936m**;
- 2.5% selling friction, leaving 97.5% of future sale price; and
- no financing, renovation, maintenance, property tax, vacancy or rent.

The scenario assumes dutiable value equals the S$1.350m entry price. Actual
BSD and ABSD are charged on the **higher of consideration or market value**,
so an apparently discounted purchase can attract duty on a higher value.

`capital-only profit = 0.975 × future sale price − S$1.3936m`

| Annual nominal sale-price change | Five-year exit / profit | Eight-year exit / profit |
|---:|---:|---:|
| 1% | S$1.419m / **−S$10k** | S$1.462m / **S$32k** |
| 3% | S$1.565m / **S$132k** | S$1.710m / **S$274k** |
| 5% | S$1.723m / **S$286k** | S$1.995m / **S$551k** |

Friction-only break-even is about **S$1.429m**. A S$500,000 capital-only
profit requires approximately **S$1.942m**. For a 1,206 sqft unit, that target
is about S$1,610 psf—well above the recent large-format achieved range even
though compact units have traded higher.

ABSD is decisive.
[Current IRAS ABSD rates](https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-acquiring-property/additional-buyer%27s-stamp-duty-%28absd%29)
impose 20% on a Singapore citizen buying a second residential property. The
additional S$270,000 would raise break-even to about **S$1.706m**, before
holding costs.

For a residential purchase on or after 4 July 2025,
[IRAS's SSD schedule](https://www.iras.gov.sg/taxes/stamp-duty/for-property/selling-or-disposing-property/seller%27s-stamp-duty-%28ssd%29-for-residential-property)
applies 16%, 12%, 8% and 4% within the first four holding years. These
five- and eight-year scenarios assume disposal after the exact fourth
anniversary, with no SSD under current rules.

## Due diligence before an offer

1. Confirm the card remains live, the seller appointment is current and each
   advertisement maps to one unique physical unit.
2. Reconcile block, floor, stack, bedrooms, subsidiary strata lot and area
   against the title, floor plan and option.
3. Separate enclosed internal area from balconies, terraces, voids and
   circulation; test furniture layouts.
4. Visit during breakfast, dinner, delivery and late-night periods to assess
   food odour, exhaust, refuse, plant, road and customer noise.
5. Read the strata plan, management-corporation structure, share values,
   by-laws and allocation of residential/commercial common costs.
6. Obtain AGM minutes, audited accounts, sinking and maintenance funds,
   insurance, arrears, litigation and planned special levies.
7. Verify residential access, security separation, loading/refuse routes and
   any fire-safety or use restrictions.
8. Check tenancy, deposits, inventory, vacant possession and actual recent rent
   for the exact size and condition.
9. Obtain an independent bank valuation and loan indication, particularly for
   a high-PSF compact unit.
10. Recompute BSD, ABSD, SSD, CPF and loan treatment for the actual buyers and
    contract date; model all holding and renovation costs separately.

## Final assessment

East Village's freehold mixed-use identity creates opportunity only when the
buyer chooses the right sub-market. Verify the S$738,000 409 sqft card first;
negotiate the 1,206 sqft home toward S$1.32m–S$1.38m; and require exceptional
evidence before approaching S$950,000 for 506 sqft. Selective upside and rental
fallback exist, but the current evidence does not establish high-confidence
huge investment quantum.
