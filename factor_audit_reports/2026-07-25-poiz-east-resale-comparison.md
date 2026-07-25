# Poiz Residences vs East-side resale condos

Date: 2026-07-25  
Route: project/unit diagnostic plus private Value evidence  
Status: implemented as a comparison view; not wired into Provision

## Decision

Profile **The Poiz Residences** as a city-fringe, integrated transit-and-retail
benchmark with healthy resale liquidity. It is not an obvious value bargain:
its compact units and direct Potong Pasir MRT/Poiz Centre access support a
repeatable PSF premium, while its 2014 lease and newer integrated competition
limit the long-horizon case.

The most informative East-side comparisons are:

1. **Park Place Residences at PLQ** — closest city-fringe integrated match.
2. **Bedok Residences** — closest mature-town integrated match.
3. **Parc Esta** and **Treasure at Tampines** — high-liquidity statistical
   controls.
4. **The Glades** and **Grandeur Park Residences** — near-MRT controls that
   separate rail proximity from full mixed-use integration.
5. **Seaside Residences** — coastal/TEL lifestyle sensitivity.
6. **Katong Regency** — qualitative freehold sensitivity only. Do not pool its
   prices with leasehold projects without a tenure control.

No unified project score or rank is produced. The comparison keeps tenure,
size, bedroom mix, achieved price, liquidity, access and data provenance
visible.

## Data refresh

On 25 July 2026, the URA PMI portal was queried again for apartment and
condominium transactions in Postal Districts 13, 14, 15, 16 and 18, covering
January 2024 through July 2026.

- The refresh added **312 official caveat rows** absent from the committed
  canonical input, including 160 July rows.
- `data/inputs/ura_private.csv` increased from **113,136 to 113,448 rows**.
- Target project tables were re-scraped separately to recover exact sale dates
  and bedroom labels. The nine-project batch returned 719 rows; **26 new rows**
  were added after transaction-key deduplication.
- The rebuilt condo/apartment bedroom layer contains **119,056 transactions**:
  113,532 exact row matches, 3,964 modal size-band labels and 1,560 unknown.
  Overall bedroom attribution is **98.69%**.
- Repeated rendered table headings had leaked into the old backfill as
  fabricated projects named `TENURE`. The loader now excludes rows with no
  valid postal district and repeated header markers.

Primary transaction source:
[URA Property Market Information](https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch).
URA caveats are voluntary and are not exhaustive; see the
[URA REALIS coverage and methodology](https://eservice.ura.gov.sg/reis/coverageandMethodology).
Bedroom labels are a secondary field matched from public EdgeProp tables, whose
rows identify URA as their source. URA itself does not publish bedrooms.

## Method

Headline price distributions use resale transactions in the latest 18
**complete** calendar months, January 2025 through June 2026. July 2026 is a
partial month and is disclosed but excluded from headline medians.

Liquidity is:

```text
resale transactions from Jul 2025 through Jun 2026 / official project units
```

It is transaction-to-stock turnover, not unique sellers. PSF is recomputed as
`price / (area_sqm × 10.7639)`. Price ranges in the HTML are P10–P90 rather
than min–max. MRT and school diagnostics use reviewed OneMap project geocodes
and straight-line haversine distance; they are not walking routes or official
Primary 1 address-distance determinations.

## Current evidence

All-project medians below use January 2025 through June 2026. Liquidity uses
the latest 12 complete months.

| Project | Role | 12m resales / stock | Turnover | Median PSF | Median quantum | Nearest open MRT |
|---|---|---:|---:|---:|---:|---|
| The Poiz Residences | Benchmark | 36 / 731 | 4.9% | S$2,048 | S$1.19m | Potong Pasir, 114m |
| Park Place Residences at PLQ | Primary integrated match | 27 / 429 | 6.3% | S$2,268 | S$1.57m | Paya Lebar, 166m |
| Parc Esta | High-liquidity control | 112 / 1,399 | 8.0% | S$2,289 | S$1.68m | Eunos, 229m |
| Seaside Residences | Coastal lifestyle control | 34 / 843 | 4.0% | S$2,311 | S$1.83m | Siglap, 471m |
| Katong Regency | Freehold sensitivity | 5 / 244 | 2.0% | S$1,944 | S$1.20m | Paya Lebar, 371m |
| Bedok Residences | Primary integrated match | 17 / 583 | 2.9% | S$1,886 | S$1.62m | Bedok, 163m |
| The Glades | Near-MRT control | 44 / 726 | 6.1% | S$1,740 | S$1.21m | Tanah Merah, 287m |
| Grandeur Park Residences | Near-MRT control | 33 / 720 | 4.6% | S$2,005 | S$1.30m | Tanah Merah, 220m |
| Treasure at Tampines | High-liquidity control | 135 / 2,203 | 6.1% | S$1,781 | S$1.54m | Simei, 639m |

The all-project medians are descriptive only; compact-unit share makes them
mix-sensitive. The bedroom-matched comparison is the decision-grade view.

### Closest pair: Poiz vs Park Place at PLQ

| Type | Poiz n / median price / PSF / size | Park Place n / median price / PSF / size | Park Place PSF vs Poiz |
|---|---|---|---:|
| 1BR | 26 / S$0.860m / S$1,963 / 441 sqft | 7 / S$1.075m / S$2,219 / 484 sqft | +13.1% |
| 2BR | 10 / S$1.250m / S$2,151 / 581 sqft | 24 / S$1.545m / S$2,300 / 667 sqft | +6.9% |
| 3BR | 13 / S$2.000m / S$2,219 / 840 sqft | 10 / S$2.470m / S$2,254 / 1,087 sqft | +1.5% |

Park Place reproduces Poiz's mixed-use/direct-rail proposition, but its units
are larger and PLQ carries a dual-line business-hub premium. The narrowing PSF
gap at 3BR suggests that quantum and floor area explain much of the apparent
family-unit difference.

Official project facts:
[MCC Singapore — Poiz](https://www.mcc.sg/project-detail?id=Poiz) and
[Lendlease — Paya Lebar Quarter](https://www.lendlease.com/projects/paya-lebar-quarter/).
Lendlease identifies PLQ as a 2019-completed mixed-use development directly
integrated with the EWL/CCL interchange and Park Place as 429 apartments.

### Closest mature-town pair: Poiz vs Bedok Residences

| Type | Poiz n / median price / PSF / size | Bedok Residences n / median price / PSF / size | Bedok PSF vs Poiz |
|---|---|---|---:|
| 1BR | 26 / S$0.860m / S$1,963 / 441 sqft | 10 / S$1.060m / S$1,842 / 581 sqft | -6.2% |
| 2BR | 10 / S$1.250m / S$2,151 / 581 sqft | 10 / S$1.669m / S$1,881 / 931 sqft | -12.6% |
| 3BR | 13 / S$2.000m / S$2,219 / 840 sqft | 3 / S$2.200m / S$1,997 / 1,098 sqft | -10.0% |
| 4BR | 3 / S$3.340m / S$2,260 / 1,507 sqft | 5 / S$2.849m / S$1,918 / 1,485 sqft | -15.1% |

Bedok Residences is cheaper per square foot but not necessarily cheaper by
quantum because its typical units are much larger. This is exactly why a
bedroom-only comparison is insufficient: bedroom, size and tenure must remain
visible together.

Official project source:
[CapitaLand — Bedok Residences](https://www.capitaland.com/en/find-a-property/global-property-listing/residential/bedok-residences.html).

## Poiz profile

- **Project:** 731-home, 99-year mixed-use development by MCC Land, completed
  in 2018. The land parcel was awarded in August 2014.
- **Unit mix:** approximately 44.7% one-bedroom/one-plus-study, 20.0%
  two-bedroom/two-plus-study, 27.6% three-bedroom, 7.1% four-bedroom and four
  penthouses. This high compact-unit share materially affects project medians.
- **Liquidity:** 36 resales in the latest 12 complete months, 4.9% of stock.
- **Access:** 114m straight-line to Potong Pasir MRT in the reviewed geocode;
  integration with Poiz Centre is a stronger proposition than generic
  "near-MRT" distance alone.
- **Schools:** the project diagnostic finds St Andrew's School (Junior) and
  Cedar Primary within 1km. St Andrew's Junior is boys-only. Verify eligibility
  against the exact block/address through
  [MOE SchoolFinder](https://www.moe.gov.sg/schoolfinder?journey=Primary+school).
- **Best fit:** car-lite singles/couples, landlords valuing a broad tenant pool,
  and families prioritising NEL access over freehold tenure or maximum space.
- **Main risks:** compact-unit resale competition, retail/transport activity,
  a finite 2014 lease, and newer integrated-NEL supply such as The Woodleigh
  Residences.

Most of the old "future Bidadari" narrative is now realised rather than fresh
upside. Remaining dated items include Bidadari Polyclinic, scheduled by 2027,
and proposed waterfront/public-space improvements:
[MOH healthcare capacity update](https://www.moh.gov.sg/newsroom/enhancing-quality-and-coordination-of-care/)
and
[URA Kallang River plans](https://www.ura.gov.sg/land-planning/shaping-our-city/identity-corridors/kallang-river/).
Planning ideas without committed delivery dates are context, not bankable
uplift.

## East-side sensitivities and catalysts

- **Paya Lebar Air Base:** relocation from the 2030s can eventually free about
  800 hectares. It is strategic context for Park Place/Parc Esta/Katong
  Regency, not a near-term price input.
  [URA source](https://www.ura.gov.sg/news/media/pr22-25/).
- **Bayshore:** current plans add a mixed-use, car-lite neighbourhood,
  integrated transport hub and community facilities. This improves the long-run
  amenity story but also creates future supply competition for existing
  Bayshore/Upper East Coast stock.
  [URA East plans](https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/east/transforming-towns-for-tomorrow/).
- **TEL5/DTL extension:** as of this report date, the opening remained expected
  in the second half of 2026 and was not treated as delivered.
  [LTA April 2026 update](https://www.lta.gov.sg/content/ltagov/en/newsroom/2026/4/news-releases/train-service-adjustments-tel-and-dtl-to-facilitate-rail-expansion-works.html).
- **Tampines controls:** Treasure provides exceptional liquidity but is neither
  mixed-use nor directly rail-integrated. It measures mass-market family
  quantum and resale competition, not the value of Poiz-style integration.

## Implementation outcome

The new `poiz_east_resale_comparison.html`:

- uses achieved resale prices only;
- excludes the latest partial month from headline statistics;
- provides all-resale and 1BR/2BR/3BR/4BR tabs;
- reports median price, P10–P90, PSF, size and Poiz-relative deltas;
- reports exact bedroom-provenance coverage;
- reports transaction-to-stock liquidity;
- exposes completion, tenure/estimated lease remaining, integration, access,
  school counts, comparison role and key risks;
- omits estate Provision/Value bands because they are not project scores; and
- does not mix asking listings, rental yield or qualitative catalysts into
  achieved-sale evidence.
