# Canberra Crescent Residences — sales timeline and Q4 2025 price-revision analysis

Research captured: **2026-08-13 11:08:08 SGT (UTC+08:00)**  
Property: **Canberra Crescent Residences, 51/53/55/57 Canberra Crescent, Singapore**  
Analysis type: **property new-launch sales timeline and price-revision analysis**  
Status: **point-in-time market snapshot**  
Market stage: **new launch**  
Summary: **The observable sales schedule rose by about 1.008% in early November 2025—S$21,688 per continuously available unit on average, or roughly S$20 psf—when the prior promotional current price was replaced by the prior listed price; this is a price-list and transaction inference, not an identified developer announcement.**

## Decision

**Canberra Crescent Residences had an effective price increase of approximately 1% in early November 2025, most plausibly implemented by withdrawing the initial promotional discount.** Across every one of the **95 units** that carried a current price in both the 13 September and 12 November Huttons-hosted price lists, the November current price equalled the September listed price. All 95 rose; none was unchanged or reduced.

The exhaustive continuously priced comparison produces an average increase of **S$21,688**, a median of **S$20,700**, and a range of **S$15,600–S$26,700**. The mean and median uplift were both approximately **S$20 psf**. The mean percentage increase was **1.008%**, with an exceptionally narrow unit-level range of about **1.005%–1.010%**.

The observed transaction sequence brackets the change more tightly than the two price-list dates. The last transaction captured at the former current-price tier was dated **1 November 2025**; the first captured at the former listed-price tier was dated **5 November 2025**. No transaction in the reviewed dataset is dated 2–4 November. The defensible conclusion is therefore that the revised tier was effective **after 1 November and by 5 November 2025**, not that a particular internal approval or announcement occurred on a known day.

This modest price step followed a very strong launch. The project sold 150 of 376 homes over its opening weekend and had 277 URA New Sale records by the end of October. Sales then moved into a slower, larger-unit tail: 13 in November, eight in December, 40 from January through May 2026, and two in June–July. That slowdown must not be attributed to the 1% increase alone; the launch burst had passed, cheaper layouts were depleted, and the remaining inventory was larger and higher-quantum.

## Source semantics

The sources answer different questions and are not interchangeable.

| Source | What it supports | What it does not prove |
| --- | --- | --- |
| [EdgeProp launch report](https://www.edgeprop.sg/property-news/canberra-crescent-residences-achieves-40-sales-launch-weekend-average-price-1974-psf) | 150 of 376 homes sold on 2–3 August 2025 at a reported average S$1,974 psf | Unit-level prices, later caveat months or current balance |
| [URA Property Market Information](https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch) snapshot through July 2026 | 340 official-source public New Sale rows, transaction month, area, price, PSF and floor band | Exact floor-stack unit, exact contract date, incentives or an executable developer balance |
| [13 September Huttons price list](https://portal.huttonsgroup.com/uploads/PriceList/697564dce09a4511a8d56e739ecdaabd/R070030E-20250913014538.pdf) and [12 November Huttons price list](https://portal.huttonsgroup.com/uploads/PriceList/697564dce09a4511a8d56e739ecdaabd/R070030E-20251112005006.pdf) | Time-stamped unit-level sales schedules; their legend defines `P` as Current Price and `UP` as Listed Price | An exercised sale, undisclosed incentive, or a formal developer explanation for the change |
| [PropertyNoob Week 45 tracker](https://propertynoob.com/blog/2025/11/05/launch-update-week-45) | Contemporaneous report of an average roughly S$22,000 / 1% increase across 97 units between 29 October and 5 November | Independent developer confirmation; its 97-unit snapshot is not the same comparison population as the 95 continuous units here |
| [Agent-managed unit chart](https://canberracrescent.projectdeveloper.info/units), captured 13 August 2026 | 342 units reported sold and 34 reported available, with floor-stack and marketing status dates | Contractual availability, legal proof of sale, or official URA unit identity |

The internal research table at `data/runs/canberra-unit-xref/2026-08-13/canberra_crescent_unit_transactions.csv` keeps the agent-reported sold date, portal transaction date and URA sale month in separate fields. It is noncanonical research data: URA's public record does not disclose exact unit numbers, and ambiguous matches are deliberately not forced.

## Sales timeline

### Phase anchors

| Phase | Incremental evidence | Cumulative read | Interpretation |
| --- | ---: | ---: | --- |
| Launch weekend, 2–3 Aug 2025 | **150 sold** | 150 / 376, **39.9%** | Strong opening; reported average S$1,974 psf |
| Full August URA month | **210 New Sales** | 210 / 376, **55.9%** | Launch month captured more than the weekend release |
| September–October follow-through | **67 New Sales** | 277 / 376, **73.7%** | Nearly three-quarters sold before the observed revision |
| November–December Q4 tail | **21 New Sales** | 298 / 376, **79.3%** | Repriced schedule and a shift toward larger remaining units |
| January–May 2026 | **40 New Sales** | 338 / 376, **89.9%** | Continued absorption at a much slower cadence |
| June–July 2026 | **2 New Sales** | 340 / 376, **90.4%** | Thin late-stage official-source tail |
| Agent chart through 13 Aug 2026 | **2 newer reported sales** | 342 / 376, **91.0%** | Marketing-source update beyond the local URA snapshot; not yet equivalent evidence |

The 150 launch-weekend sales are included within August's 210 URA records; they are not an additional 150 transactions.

### Monthly URA sequence

All rows below are New Sales in the reviewed URA-source snapshot. Transaction multiplicity is preserved, including rows with identical public fields.

| Sale month | New Sales | Cumulative | Sell-through of 376 |
| --- | ---: | ---: | ---: |
| Aug 2025 | 210 | 210 | 55.9% |
| Sep 2025 | 30 | 240 | 63.8% |
| Oct 2025 | 37 | 277 | 73.7% |
| Nov 2025 | 13 | 290 | 77.1% |
| Dec 2025 | 8 | 298 | 79.3% |
| Jan 2026 | 8 | 306 | 81.4% |
| Feb 2026 | 9 | 315 | 83.8% |
| Mar 2026 | 7 | 322 | 85.6% |
| Apr 2026 | 8 | 330 | 87.8% |
| May 2026 | 8 | 338 | 89.9% |
| Jun 2026 | 1 | 339 | 90.2% |
| Jul 2026 | 1 | 340 | 90.4% |

## Q4 2025 price-revision mechanism

The September price-list legend labels `P` as **Current Price** and `UP` as **Listed Price**. In the November document, the lower September current price disappears for the continuously available comparison set, while the former September listed price becomes the November current price.

The comparison is exhaustive within that definition:

- both PDFs contain the complete 376-unit tower chart;
- the September chart shows 225 as sold and 151 with a current price;
- the November chart shows 281 as sold and 95 with a current price;
- exactly 95 units have a current price in both snapshots; and
- for all 95, `November P = September UP > September P`.

This pattern is more consistent with removal of a roughly 1% promotional discount than with selective repricing by stack, floor or layout. It establishes the observable sales-schedule mechanism. It does **not** establish the developer's unpublished commercial rationale, and no cited developer circular or press release announces a 1% increase.

### Exhaustive 95-unit result

| Measure | Result |
| --- | ---: |
| Continuously priced units | **95** |
| Units increased / unchanged / reduced | **95 / 0 / 0** |
| Mean dollar increase | **S$21,688** |
| Median dollar increase | **S$20,700** |
| Minimum / maximum increase | **S$15,600 / S$26,700** |
| Mean percentage increase | **1.008%** |
| Unit-level percentage range | **1.005%–1.010%** |
| Mean / median equivalent increase | **S$20.01 / S$20.00 psf** |

### Increase by size and type

| Area / format | Comparable units | Mean increase | Median increase | Range | Mean increase per sqft |
| --- | ---: | ---: | ---: | ---: | ---: |
| 797 sqft 3BR Compact | 8 | S$16,012 | S$16,000 | S$15,600–S$16,200 | S$20.09 |
| 872 sqft 3BR Compact | 1 | S$17,300 | S$17,300 | S$17,300 | S$19.84 |
| 883 sqft 3BR Compact | 2 | S$17,500 | S$17,500 | S$17,300–S$17,700 | S$19.82 |
| 990 sqft 3BR Premium | 37 | S$20,119 | S$20,100 | S$19,600–S$20,700 | S$20.32 |
| 1,163 sqft 4BR Compact | 3 | S$22,267 | S$22,500 | S$21,800–S$22,500 | S$19.15 |
| 1,173 sqft 4BR Compact | 9 | S$23,111 | S$23,100 | S$22,700–S$23,400 | S$19.70 |
| 1,216 sqft 4BR Standard | 27 | S$24,107 | S$24,200 | S$23,400–S$24,800 | S$19.83 |
| 1,324 sqft 4BR Premium | 8 | S$26,238 | S$26,200 | S$26,000–S$26,700 | S$19.82 |
| **All continuous units** | **95** | **S$21,688** | **S$20,700** | **S$15,600–S$26,700** | **S$20.01** |

The 409, 570 and 667 sqft formats do not appear because none carried a current price in both snapshots. The larger absolute increases are therefore predominantly size arithmetic: the adjustment remained almost exactly 1% across formats.

### Unit examples

| Unit | Format | 13 Sep current price | 13 Sep listed price / 12 Nov current price | Increase |
| --- | --- | ---: | ---: | ---: |
| #01-16 | 797 sqft 3BR Compact | S$1,547,500 | S$1,563,100 | **S$15,600** |
| #02-03 | 990 sqft 3BR Premium | S$1,968,200 | S$1,988,000 | **S$19,800** |
| #04-22 | 1,216 sqft 4BR Standard | S$2,395,800 | S$2,420,000 | **S$24,200** |
| #12-27 | 1,324 sqft 4BR Premium | S$2,647,200 | S$2,673,900 | **S$26,700** |

These are offered-price-list comparisons, not four achieved paired transactions. Their value is demonstrating the uniform schedule change.

## Exact observed repricing window

Two corroborated transaction rows make the timing visible:

| Transaction date | Unit | Achieved price | Read against 13 Sep list |
| --- | --- | ---: | --- |
| **1 Nov 2025** | #08-14, 1,216 sqft | **S$2,361,000** | Equals the former `P` current price; former `UP` was S$2,384,800 |
| **5 Nov 2025** | #02-18, 1,173 sqft | **S$2,284,200** | Equals the former `UP` listed price; former `P` was S$2,261,400 |

The reviewed transaction ledger has no row dated 2–4 November. The price step is therefore bracketed to **2–5 November 2025**, with evidence that the new tier was in use by 5 November. The contemporaneous PropertyNoob tracker also places a roughly 1% change between 29 October and 5 November, but it is corroboration of the observable feed rather than a substitute for a developer announcement.

Marketing-reported sold dates, portal transaction dates and URA sale months can differ. The timing above uses the exact transaction-date field from the internal cross-reference, while URA provides the official-source public month and price attributes.

## Why the raw median suggests a false 23% jump

The monthly median transaction quantum rose from **S$1.610 million in October to S$1.986 million in November**, an apparent **23.4%** increase. That is not a like-for-like project price increase.

October contained 20 sales of 797 sqft units and three of 667 sqft units. November contained only four 797 sqft sales, no 667 sqft sales, and seven of its 13 sales were 990 sqft or larger. The median therefore moved to a more expensive layout cohort. Even the monthly median PSF—S$1,996 in October and S$2,016 in November—mixes floors, stacks and formats.

The continuous-unit price-list comparison controls this problem directly: it follows the same 95 exact floor-stack units across both lists. Its approximately 1.008% result is the relevant estimate of the schedule change; the 23.4% quantum movement is a composition artefact.

## Post-increase sales and remaining tail

URA records 13 New Sales in November and eight in December, taking cumulative sales to 298, or 79.3%. Another 40 were recorded from January through May 2026, followed by one each in June and July. The official-source snapshot therefore ends at **340 / 376**.

The agent-managed chart captured on 13 August 2026 reports **342 sold and 34 available**. The two additional reported sales are newer than the local URA and portal snapshots and remain pending official-source corroboration. Its 34 reported available homes are all larger layouts:

| Reported remaining format | Units |
| --- | ---: |
| 990 sqft 3BR Premium | 15 |
| 1,163 sqft 4BR Compact | 1 |
| 1,173 sqft 4BR Compact | 1 |
| 1,216 sqft 4BR Standard | 11 |
| 1,324 sqft 4BR Premium | 6 |
| **Total** | **34** |

This tail helps explain slower sales without a causal price claim. By then the 1BR, 2BR and compact 3BR choices were no longer represented in the reported balance; buyers were choosing among higher-quantum 990–1,324 sqft homes. Normal launch decay, depletion of lower tickets, stack and floor quality, macro conditions, buyer financing and the 1% revision can all affect cadence. The available data cannot isolate their individual effects.

## Conclusion and limitations

The strongest supported interpretation is narrow and clear:

1. Canberra Crescent Residences launched strongly and reached 277 URA New Sales by October 2025.
2. After 1 November and by 5 November, the observable current-price schedule moved up by approximately 1%.
3. Mechanically, the September promotional current price was replaced by the September listed price for all 95 continuously priced units.
4. The increase averaged S$21,688, had a S$20,700 median, and was roughly S$20 psf across sizes.
5. The much larger October-to-November median-quantum jump was caused primarily by unit mix, not a 23% repricing.
6. Sales slowed after the revision, but the evidence does not support saying that the revision caused the slowdown.

The URA public search does not disclose exact unit numbers or exact contract dates. Agent and portal sources can lag reservations, cancellations and legal completion; offered prices can omit incentives. The exact-unit cross-reference includes ambiguous and residual-inference rows and is not legal proof of a sale. Finally, no cited official developer announcement explains the Q4 change. This report documents the observable price schedule and transaction evidence, not an unpublished intention or causal claim.

This is a dated market analysis, not a valuation, developer representation, legal opinion or guarantee of inventory. A buyer should obtain a current developer-issued balance sheet and net price for the exact unit before acting.
