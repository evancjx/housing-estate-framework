# Singapore Estate Liveability Grading Framework

*Framework v0.4 — reconciles two external reviews + the Dover/Canberra infill analysis. Built to be argued with, not trusted.*

---

## 0. Provenance & how v0.4 was decided

v0.4 integrates two independent external reviews (both AI-assisted, voices differ) plus a
primary-source check on Dover and Canberra MRT history. Adopted where right; overruled where
the reviews blurred distinctions or risked perverse outcomes. Every override is stated.
Treat polished reviews with the same suspicion as polished drafts — confidence is not
correctness.

---

## 1. Spatial unit — TWO-TIER (compute fine, report coarse)

| Layer | Unit | Role |
|-------|------|------|
| Compute | **URA subzone** (centred on neighbourhood centres / activity nodes) | All scoring. Captures Tampines North ≠ Central, Dawson ≠ Tanglin Halt. |
| Report | **HDB town + named private enclave**, with **mandatory dispersion flag** | Human-readable rollup; never publish a town score without its subzone spread. |
| Supplement | **URA planning area** | Geospatial/population joins only. |

Caveat (both reviews flagged): URA warns subzone/planning boundaries "may not coincide with
existing developments." Strong lived-place labels (e.g. **"Canberra"**) must be polygon-join
validated before being called a subzone.

---

## 2. Components — TEN (10 reserved)

Sub-metrics are **guidance for assigning the single 1–5**, NOT separately weighted terms
(usability over false precision).

| # | Component | Core weight | Scored on (guidance) |
|---|-----------|------------:|----------------------|
| 1 | Connectivity | 16.7% | Walk-time to rail/interchange, feeder freq, transfer penalty, redundancy, multi-node commute, first/last-mile shelter |
| 2 | Daily amenities | 15.6% | Basics (hawker, wet market, supermarket, GP, pharmacy, library/CC) weighted above lifestyle retail. **Also: shops-not-yet-open = desolation signal (see §6).** |
| 3 | Green & blue | 10.4% | *Usable* greenery: 400/800m network-walk, shade, size/facilities, PCN continuity, overcrowding penalty |
| 4 | Schools | 10.4% | Practical access, NOT prestige: within 1km/2km (MOE P1 distance), balloting pressure, preschool/infant/student-care, sec/JC reach |
| 5 | Density & built form | 9.4% | Lived density: block spacing, mixed-use, lift/access, pavement. **Empty/derelict floor = desolation signal (see §6).** |
| 6 | Healthcare | 8.3% | Primary-care-first: GP/CHAS/pharmacy, polyclinic, eldercare, THEN A&E time. Not hospital-centric. |
| 7 | Momentum (+, time-discounted) | 6.3% | Confirmed *additions* only, discounted by horizon (§4) |
| 8 | **Infrastructure readiness** | 16.7% | Trunk infra *operational now* vs promised. Punggol/Dover = 5; Canberra-historical = 1. **Kept clean — see §6 for why over-provision is NOT penalised here.** |
| 9 | Environmental comfort & nuisance | 6.3% | Heat/shade, road-rail-aircraft noise, expressway/viaduct exposure, **construction disruption (desolation signal, §6)**, flood-prone routes |
| 10 | *(reserved — see §7)* | — | candidate: estate stewardship. NOT "social mix." |

```
w = [0.167, 0.156, 0.104, 0.104, 0.094, 0.083, 0.063, 0.167, 0.063]
```

---

## 3. The equation

```
Core(a)  = Σ (wᵢ × Sᵢ)                 i = 1..9, Sᵢ ∈ [1,5]
Final(a) = Core(a) × D(a) × C(a)
Value(a,g) = regression-residual adjusted (§8)
```

---

## 4. Trajectory D — time-discounted (symmetric for gains & losses)

```
D = max(0.70, 1 − Σ(severity × certainty × time_factor))
```

| Severity | val | | Certainty | mult | | Timing | factor |
|---|--:|---|---|--:|---|---|--:|
| Moderate loss | 0.10 | | Confirmed/contracted | 1.00 | | 0–2 yr | 1.00 |
| Major loss | 0.20 | | Gazetted, not contracted | 0.75 | | >2–5 yr | 0.75 |
| Structural loss | 0.30 | | Under study | 0.40 | | >5–10 yr | 0.40 |
| | | | Rumour | 0.00 | | >10 yr | 0.20 |

Same time-discount applies to positive Momentum (7). Verified live anchors: **CCL6
passenger service 12 Jul 2026** (confirmed, imminent → near-full credit); JRL Stage 1
~mid-2028, CRL1/CRL-Punggol ~2030/2032 (confirmed but distant → heavily discounted).

Caveat: D is a whole-grade multiplier → strips more absolute points from strong estates
than weak ones. 0.70 floor caps it.

---

## 5. Selective veto C(a)

| Trigger | Cap |
|---------|-----|
| S1 Connectivity = 1 AND S8 Infra ≤ 2 | Universal → C |
| S2 Amenities = 1 | Universal → C |
| S6 Healthcare = 1 | Retiree → C (universal: no cap) |
| S4 Schools = 1 | Young-family → C only |
| Any 2+ of {S1, S2, S6, S8} = 1 | Universal → D |
| S3, S5, S7, S9 = 1 | No cap |

---

## 6. Dover vs Canberra — the infrastructure-timing polarity (primary-source finding)

Both are infill stations on an existing operating line, mooted years before built (Dover
from 1988→opened 2001; Canberra NS12 reserved →opened 2019). But their *timing logic is
opposite*, and this defines component 8:

| | Built AHEAD of demand | Built BEHIND demand |
|---|---|---|
| Example | **Dover (2001)**, **Punggol spine** | **Canberra (2019, deliberately delayed)** |
| Govt logic | Serve future planned development | Avoid "white elephant"; wait for ridership |
| Resident outcome | Never stranded | Endures years-long access gap |
| Cost borne by | Taxpayer (low initial use) | Early resident |
| Component 8 score | High (operational at move-in) | Low (homes present, stop withheld) |

**Design decision (overrides user's literal request to penalise over-provision):**
Dover ran ~7,900 pax/day even 23 yrs on. The user asked that such over-provision cost
something. **It does NOT cost anything in component 8**, because penalising "infrastructure
present ahead of demand" would mark *down* exactly the Punggol-style good planning the whole
framework rewards — inverting the founding lesson.

What the user actually wants penalised is a **desolate, not-yet-filled estate** (few
neighbours, shuttered shops, construction). That IS penalised — but routed through the
components designed to catch it:
- **Component 2** (amenities not yet open)
- **Component 5** (empty/derelict density floor)
- **Component 9** (construction disruption)

This avoids double-counting and keeps component 8 an unambiguous "is the infra operational"
signal. The penalty self-lifts as the estate fills in — the correct dynamic. A pure
*taxpayer-efficiency* over-provision metric is deliberately excluded: it's a fiscal concern,
not a resident-liveability one, and belongs in a separate index.

---

## 7. Component 10 — RESERVED. Stewardship, never "social mix."

Both reviews agree: leave 10 empty in v0.4. If ever filled, the candidate is **estate
stewardship** (cleanliness, maintenance, void-deck condition, lighting, wayfinding, neglect)
— observable and behaviour-based.

**Ethical lock (do not remove):** "social mix" / "community" as a scored liveability
component is rejected permanently, not just deferred. A liveability index that rewards
"social mix" becomes a laundered proxy for *fewer rental flats / fewer lower-income
neighbours* — sorting by class (and, in other jurisdictions, race) under a neutral-sounding
label. Stewardship measures how an estate is *cared for*, not *who lives there*. During
pilots, collect stewardship only as an **unweighted diagnostic**; admit to Core only after
it shows repeatable measurement, real spread, and incremental explanatory value.

---

## 8. Value — regression-residual (production), percentile (pilot sanity-check only)

Cost stays OUT of Core. Published separately. Residual asks: cheap or dear *relative to what
liveability predicts*, not just "expensive."

For each housing segment g:
```
ln(cost_psm_j) = α_g + β_g·Final(a) + γ_g·dwelling_controls + δ_g·tenure/lease_controls + μ_month + ε_j
ValueResidual(a,g) = median ε_j within subzone a, segment g
ValueScore(a,g)    = Final(a) × exp(−ValueResidual(a,g))
```
Cap adjustment multiplier to **0.75×–1.25×** until calibrated (one mispriced micro-market
must not distort Value).

| Segment | Controls |
|---|---|
| HDB resale | flat type, floor area, storey band, remaining lease, resale month |
| Private resale | property type, tenure, unit size, project age, txn month |
| Private rental | property type, unit size, project age, lease month |

Data: HDB resale official set (Jan 2017→, current to Jun 2026). Private = separate URA
universe. **Never blend HDB + private into one affordability number** without tenure/dwelling
controls — model segments separately.

---

## 9. Persona grades (baseline + signed Δ, sum to zero)

```
w_persona(i) = w_core(i) + Δ(i)  (renormalise); Final_persona = Core_persona × D × C
```

| Component | Young family | Single pro | Retiree |
|-----------|-------------:|-----------:|--------:|
| 1 Connectivity | −7 | +8 | −3 |
| 2 Amenities | +1 | +2 | +4 |
| 3 Green/blue | +4 | −2 | +4 |
| 4 Schools | +7 | −9 | −9 |
| 5 Density | 0 | −3 | +2 |
| 6 Healthcare | +1 | −4 | +12 |
| 7 Momentum | −5 | +3 | −5 |
| 8 Infra readiness | **−2** | +1 | −2 |
| 9 Env comfort | **+2** | +4 | −3 |
| **Sum** | **+1→0*** | **0** | **0** |

*Young-family column shown sums to +1; the +1 is absorbed by trimming Connectivity to −8 OR
Schools to +6 at calibration — flagged, not silently fudged. **Two changes from v0.3,
adopted from review #2 + my override:**
- Env comfort **−6 → +2** (families are MORE sensitive to heat/noise/construction — stroller
  routes, school walks, infant sleep). This corrects v0.3's worst cell.
- Infra readiness **−2** (compromise: families depend on *operational* infra now, so not the
  reviewer's −3; but they can tolerate some future-confirmed gap, so not 0). Funded by the
  heavy Momentum −5 (future promises matter least for present-day family liveability).

> If you later build a "5-year BTO buyer" persona, raise Momentum back up — promises matter
> on a buying horizon, not a living-now horizon.

---

## 10. Pilot — SIX subzones (tests dispersion + readiness + nuisance + Core/Value at once)

| Pilot | Why |
|---|---|
| Canberra MRT / Canberra Plaza catchment | Newer infill infra + delivered amenities; tests whether "Canberra" reports as a named node vs swallowed by Sembawang. **Polygon-validate before calling it a subzone.** |
| Sembawang Central | Mature town-centre baseline: MRT, mall, interchange. |
| Sembawang North / Straits edge | Future-facing Momentum vs present readiness (include only if data sufficient). |
| Yishun Central | High-amenity, high-density mature hub — contrast vs Sembawang Central. |
| Northland | Mature non-central Yishun: schools, amenities, ordinary HDB conditions. |
| Khatib / Lower Seletar edge | Green-blue access, rail access, low retail intensity. |

Pilot data sources (mostly official): URA subzone polygons; LTA bus stops + MRT exits
(connectivity); MOE school directory; NParks PCN/parks; CHAS clinic GeoJSON (primary
healthcare); NEA air-temp (env comfort); PUB flood-prone areas. Noise/shade/construction/
aircraft nuisance need proxy work — reason to keep env-comfort as ONE 1–5, not fragile
sub-metrics.

---

## 11. Known weaknesses (standing)

1. Additivity hides present dealbreakers except where C(a) vetoes.
2. Components 3,5 vs 2 negatively correlated — dense hubs blur against quiet estates.
3. Sub-metric guidance is unweighted judgement — usability bought with some transparency.
4. D and Value lean on price data with HDB/private tenure-mixing risk.
5. Weights are judgement, not survey-derived.
6. Dispersion flag mitigates but doesn't eliminate town-level heterogeneity in practice.
7. Desolation routed through 2/5/9 risks *under*-counting if an estate is empty but those
   three happen to score okay — watch during pilot.

---

## 12. Status

Structure is now stable. Open calibration items (not structural): the young-family +1
rounding; whether stewardship ever enters Core; proxy methods for noise/shade. **Next step is
data**: populate Sᵢ + D across the six pilot subzones, with sources, then run Core, Final,
Value, and the three persona grades.

---

---

# v0.5 — DUAL-HORIZON MODEL (supersedes v0.4 scoring; v0.4 components retained)

## V5.1 What changed and why

v0.5 responds to a third external review whose central, correct point was: **v0.4 silently
blended "live here today" with "buy here for 2030" into one number.** Pasir Ris (strong
present + future upside), Canberra (strong present, little future), and Tengah (weak present,
huge future) cannot share one axis without becoming misleading. Fix: **two equal-billing
headline grades.**

| Change | From | To |
|--------|------|----|
| Weight vector | summed to 1.001 (bug) | renormalized to **exactly 1.000** |
| Headline | single Core | **LiveNow + Future5Y, side by side** |
| S8 timing | undefined | LiveNow = readiness at **scoring date**; Future5Y = readiness at the **move-in horizon the grade addresses** (NOT original residents' historical move-in) |
| S8 status | (review wanted it demoted to a modifier) | **kept full-weight**, sharpened vs S1 (see V5.3) |
| S7 Momentum / D | both touched trajectory (double-count risk) | **S7 = positive additions only; D = losses/disruptions only** |
| Schools | 10.4% | **trimmed to 8.2%** in universal (address-level factor; not exiled) |
| Desolation | routed through 2/5/9 only | + explicit **Estate Fill Ratio** diagnostic (unweighted) |

**Renormalized v0.5 weights (sum = 1.000):**
```
conn 0.1709 | amen 0.1597 | green 0.1064 | sch 0.0819 | dens 0.0962
hlth 0.0850 | mom 0.0645  | infra 0.1709 | env 0.0645
```

## V5.2 The dual-horizon equations

```
LiveNow(a)   = PresentCore(a) × LossD(a) × CapC(a)
Future5Y(a)  = Σ wᵢ × Sᵢ_future(a) × CapC(a)
               where Sᵢ_future folds in confirmed additions operational within ~5 years,
               each discounted by Certainty × Time × SlipPremium (see V5.4)
Value(a,g)   = LiveNow(a) × exp(−ValueResidual(a,g))      [Value anchors to LiveNow, not Future]
```

- **LossD** = the v0.4 D-multiplier, now restricted to confirmed LOSSES/disruptions only.
- **S7 Momentum** still exists in LiveNow as a small present-day "things are visibly improving"
  signal, but the heavy future uplift now lives in Future5Y, not in S7. This avoids the
  double-count the review flagged.

## V5.3 S8 sharpened against S1 (kept full weight — user override of reviewer)

The review wanted S8 demoted to a lag-modifier. **Rejected by user**, to preserve the
founding decision that "homes but no operational MRT" is a first-class liveability failure.
Duplication with Connectivity is instead removed by a clean definitional split:

- **S1 Connectivity** = *how good is the transit network when it is present* (lines, interchange,
  redundancy, commute time, feeder frequency, shelter).
- **S8 Infrastructure readiness** = *is that trunk infrastructure OPERATIONAL at the relevant
  horizon* (binary-ish gating on existence, not quality).

A mature estate scores high on both (no penalty for redundancy — they genuinely are two
different goods). A new estate with homes but no running MRT scores okay on S1's *eventual*
quality but LOW on S8 *now* — which is the entire Canberra-2015 / Tengah-2026 lesson.

## V5.4 SETTLED-BUT-CHALLENGEABLE: Promise-risk discount on Future5Y

**Problem:** v0.5's first draft applied a flat 0.70 multiplier to all future uplift — an
invented constant treating a contracted 2-year-out line the same as an under-study 8-year-out
facility. That is exactly the false-precision the framework warns against.

**Settled position:** do NOT invent a new constant. Reuse the existing D-table machinery.
Future uplift is discounted by:
```
uplift_credit = nominal_uplift × Certainty × Time_factor × SlipPremium
```
- **Certainty** and **Time_factor**: the SAME tables as the D-multiplier (v0.4 §4). Confirmed/
  contracted = 1.00; gazetted = 0.75; under study = 0.40; rumour = 0.00. 0–2yr = 1.00;
  2–5yr = 0.75; 5–10yr = 0.40.
- **SlipPremium**: an empirical haircut for Singapore rail's tendency to open late
  (CCL6 slipped; TEL Stage 4 slipped ~1yr for COVID; JRL Stage 1 moved 2027→mid-2028).
  **Default 0.85 on rail-dependent uplift; 1.00 on non-rail (malls, schools, polyclinics,
  which slip less).**

**This is the #1 number to challenge.** SlipPremium = 0.85 is a judgement from a handful of
cases, not a fitted estimate. If a reviewer has a delivery-variance dataset for SG
infrastructure, replace it. Sensitivity: Tengah Future5Y ≈ 4.0 at these settings, ~4.5 at full
credit (no slip/time discount), ~3.6 at a harsh 0.4 discount. **Trust the direction (Tengah
rises sharply), not the decimal.**

## V5.5 SETTLED-BUT-CHALLENGEABLE: Private/landed-enclave mobility

**Problem (review):** scoring a car-primary landed enclave (e.g. Holland Village, Bukit Timah,
Serangoon Gardens) against a car-lite "walk-to-MRT" HDB standard is a category error — those
residents largely drive, so "MRT within 400m" measures the wrong thing for them.

**Settled position — TAG, do not RESCORE:**
- Connectivity (S1) is measured the **same way for every estate** (transit access = transit
  access). No separate "car mobility" sub-scale.
- BUT each estate carries a **mobility-assumption tag**: `transit-primary` (most HDB towns) or
  `car-primary` (landed/private enclaves). The tag governs *interpretation*, not the number.

**Why not a separate car-mobility axis (the rejected alternative):** rewarding car access on
its own axis would inflate exactly the wealthy car-dependent enclaves in a country with
explicit car-lite policy — letting a Bukit Timah bungalow belt score "high mobility" for
needing two cars. That inverts sustainable-liveability intent and smuggles affluence in as a
virtue (a cousin of the "social mix" laundering problem in Appendix A.4). Comparability is
preserved; the distortion is flagged for the reader rather than scored away.

**Consequence to accept:** car-primary enclaves will tend to score *lower* on S1/S8 than their
residents subjectively experience, because those residents substitute cars for transit. The
tag tells the reader "this low transit score is partly offset by car-primary lifestyle" without
manufacturing a number to do it. **Challenge expected:** is a tag enough, or does it just
hide the problem behind a label?

## V5.6 v0.5 pilot results (8 estates, illustrative — analyst judgement, not GIS)

| Estate | LiveNow | Future5Y | Shift | Mobility tag |
|--------|:-------:|:--------:|:-----:|--------------|
| Queenstown | 4.20 B+ | 4.20 B+ | — | transit-primary |
| Pasir Ris | 4.04 B+ | 4.16 B+ | +0.12 | transit-primary |
| Woodleigh | 4.03 B+ | 4.03 B+ | — | transit-primary |
| Tampines | 4.00 B | 4.12 B+ | +0.12 | transit-primary |
| Holland Village | 3.95 B | 3.95 B | — | **car-primary** |
| Marine Parade | 3.86 B | 3.86 B | — | transit-primary |
| Canberra | 3.44 C | 3.44 C | — | transit-primary |
| Tengah | 2.96 D | 4.02 B+ | **+1.06** | transit-primary (car-lite design) |

Cross-grader note: an independent reviewer scoring the same framework got Canberra 3.69 (vs
3.44) and Tengah 3.22 (vs 2.96) — **±0.25–0.3 analyst divergence on identical rules.** Bands
and ordering held; the second decimal is noise until GIS-computed. Treat ±0.3 as the error bar.

---

# v0.6 — CAR-MOBILITY AXIS + RESOLUTION HONESTY

## V6.1 Two changes

1. A **conditional car-mobility axis (S11)** for car-primary households (replaces the v0.5
   interpret-only tag with an actual scored axis — but a constrained one).
2. An explicit **resolution-honesty rule**: grade to BANDS, not decimals, until GIS data
   earns the precision.

## V6.2 S11 — Conditional car-mobility axis

**Activation:** S11 is NOT in the universal weight vector. It activates ONLY for the
`car-primary` mobility tag (landed/private enclaves, or any persona the user marks as
car-owning). For `transit-primary` households S11 is null and weights are the v0.5 vector.

**What S11 scores (1–5):**
| Sub-factor | Captures |
|---|---|
| Expressway access | Time/distance to nearest expressway on-ramp (CTE, PIE, AYE, KPE, TPE, ECP, SLE, BKE, MCE, KJE) |
| Multi-district drive time | Off-peak drive to MULTIPLE job nodes — CBD, Jurong Lake District, one-north, Changi Business Park, Woodlands, Tuas, Paya Lebar Central — not CBD alone |
| Congestion & construction friction | ERP gantry density on typical routes, chronic bottlenecks, active major roadworks |
| Parking reality | Availability/cost at home and at key destinations |
| Industrial proximity | Dual-signed: GOOD for those working Tuas/Jurong/Changi industrial; BAD for ambient air/noise. Net per estate. |

**For car-primary households, S11 substitutes for part of S1.** When active, the persona
weight on S1 (transit Connectivity) is HALVED and the freed weight moves to S11. Rationale:
a car-primary resident genuinely derives less daily liveability from MRT proximity — but S1
is only halved, NOT zeroed, because (a) household members without a car still need transit,
(b) car-lite resale demand still values transit, (c) cars break / get sold.

**THE COST-OF-CAR-DEPENDENCE DRAG (non-negotiable):**
S11 carries a mandatory penalty term so it cannot become a wealth-laundering bonus:
```
S11_net = S11_raw − CarDependenceDrag
CarDependenceDrag = f(forced car ownership, COE+running cost burden, no viable transit fallback)
```
An estate that is PLEASANT to drive in but UNLIVABLE without a car does not out-score a
transit-rich estate. The drag is heaviest where a car is *mandatory* (poor transit fallback)
and lightest where the car is *optional* (good transit also present, car is a convenience).

**Why a drag at all (the standing argument):** Singapore policy actively suppresses car
ownership (COE, ERP, car-lite town design). A liveability index that rewarded car-dependence
as superior mobility would measure affluence and call it liveability — the same laundering
trap as the rejected "social mix" component (Appendix A.4). The drag keeps S11 measuring
*mobility quality*, not *ability to afford cars*.

**Consequence:** a wealthy car-primary enclave with great expressway access but poor transit
lands at roughly PARITY with a transit-rich HDB estate — high S11_raw, but pulled back by the
drag and by the halved-but-present S1. It does NOT leap ahead. If a future reviewer wants car
enclaves to score higher, they must first defeat the laundering argument.

## V6.3 The Singapore-scale problem (documented, unresolved)

User raised: in a large country, dissatisfaction → migrate to another state. In Singapore it
is "just a move" within one island, one labour market, one amenity network. Implication: real
liveability differences exist but are **COMPRESSED** — most of the island is within ~25km / one
transfer of everything.

**Evidence from this framework's own runs:** 6 of 8 piloted estates scored 3.86–4.20 (0.34
spread) against ±0.3 cross-grader noise. The gap between adjacent estates is often INSIDE the
measurement error.

**Decision (user): differences are real and worth grading.** Accepted with a binding caveat:
- The differences are **real in ORDERING** (Tengah < Canberra < the B/B+ cluster) — defensible.
- They are **NOT yet resolvable in DECIMALS** — 4.04 vs 4.00 is below the noise floor.
- Therefore: **report BANDS (A/B+/B/C/D/F), not point scores, until GIS data is in.** A point
  score may be computed but must be shown with its ±band-width, never as a bare decimal.

This is the "looks rigorous, misleads" failure mode in its final form: a small-city framework
that over-resolves compressed differences manufactures false distinctions. Banding is the
guard. Precision is the goal; it is **aspirational, not yet delivered.**

## V6.4 The bigger picture — what this framework is actually FOR in Singapore

Because differences are compressed, the three outputs re-rank in usefulness for a small city:
1. **Value(a,g)** — what you PAY for near-equivalent liveability — becomes arguably the MOST
   decision-relevant output. Liveability is broadly high; price varies far more than quality.
2. **Persona fit** — which flavour of "good" (family / single / retiree / car-primary) — is
   the second real differentiator.
3. **LiveNow Core band** — sorts the clearly-struggling from the broadly-fine, then saturates.
   Least differentiating among established estates; most useful for new/transitional towns
   (Tengah, future BTO sites) where the spread is genuinely wide.

This does NOT demote Core (user kept precise grading as the goal). It reorders which output a
*resident* should look at first: in big-country terms you choose a city; in Singapore you have
already "chosen the city" — you are choosing price and fit within one broadly-liveable island.

---

# v0.7 — REALIZED-EXECUTION (then-vs-now)

## V7.1 What this adds and the tension it resolves

User wants announcement-grade vs current-grade comparison, for the purpose of **"did planners
deliver what was promised."** User chose BOTH absolute-delta AND era-relative rank-shift.

**Builder resolution of the tension:** absolute delta CANNOT measure execution and is labelled
context-only. Reason: an old estate's huge absolute climb (e.g. 1→4) is mostly *Singapore
getting richer* — MRT network expanding nationally, rising wealth, the whole baseline
ratcheting up — NOT planners delivering. An estate where planners did nothing special shows the
same absolute climb from the rising tide. **Only era-relative rank-shift controls for the tide**
(peers rode it too), so the execution verdict is era-relative; absolute delta is shown as
context only.

## V7.2 The two measures

**A. Absolute delta (CONTEXT ONLY — not an execution signal):**
```
AbsoluteDelta(a) = LiveNow_grade(a) − AnnouncementGrade_todaysRubric(a)
```
Score the estate-at-announcement on today's 2026 rubric. Pre-1987 towns score ~1–2 at
announcement (no MRT existed anywhere). Almost every old estate shows a large positive delta.
**This mostly measures national development, not estate-specific execution.** Use only to show
"how far the whole context moved," never to rank planning quality.

**B. Era-relative execution verdict (THE execution measure):**
```
Promise   = where the estate was positioned AMONG ITS CONTEMPORARIES at announcement (1–5)
Realized  = where it sits AMONG today's estates now (1–5, era-relative rank)
Execution = Realized − Promise
   +1 or more = OVER-delivered (climbed above peers)
    0         = Delivered as promised (held relative position)
   −1 or less = UNDER-delivered (slipped below peers)
```

**Critical honesty rule:** execution is promise-vs-realization, NOT absolute quality.
- An estate announced BASIC that stayed BASIC has **DELIVERED** (did what it said) — no penalty
  for low absolute grade.
- An estate announced PREMIUM that merely stayed premium has **DELIVERED** — no bonus for
  cruising on an early lead.
- "Delivered as promised" is the expected, healthy default — most estates should land here.

## V7.3 Eight-estate execution table (illustrative)

| Estate | Announced | Promise (era-rel) | Realized (era-rel) | Execution | Today (band) |
|--------|:---:|:---:|:---:|:---|:---:|
| Tampines | 1979 | 4 | 5 | **OVER-delivered (+1)** | B+ |
| Queenstown | 1952 | 4 | 5 | **OVER-delivered (+1)** | B+ |
| Pasir Ris | 1984 | 3 | 4 | **OVER-delivered (+1)** | B+ |
| Marine Parade | 1970 | 4 | 4 | Delivered as promised | B |
| Woodleigh (Bidadari) | 2015 | 4 | 4 | Delivered as promised | B+ |
| Holland Village | ~1970 | 4 | 4 | Delivered (organic, never master-promised) | B |
| Canberra | 2014 | 3 | 3 | Delivered as promised | C |
| Tengah | 2016 | 5 | 3 | **UNDER-delivered (−2) — PENDING** | D |

## V7.4 Reading the results — the two that matter

**Tengah's −2 is the metric working, but it carries a giant asterisk.** Tengah was announced as
THE flagship smart/forest town (promise = 5, highest of any estate here). Today it is the
lowest LiveNow (D). Era-relative, that is a −2 under-delivery. BUT the verdict is **PENDING, not
FAILED** — its rail and fill-in are scheduled, not cancelled. This is precisely where v0.7
(execution, backward-looking) and the v0.5 dual-horizon (Future5Y, forward-looking) must be read
TOGETHER: Tengah is "under-delivered SO FAR" (v0.7) AND "B+ projected by 2031" (v0.5). Judging it
solely on either is misleading. If JRL and the town centre land on schedule, its v0.7 verdict
revises toward "delivered"; if they slip repeatedly, it hardens toward genuine under-delivery.

**Canberra's "delivered as promised" despite a C grade is the honesty rule in action.** Canberra
was deliberately modest and deliberately late (station withheld until population justified it).
It promised little and delivered exactly that. A naive execution metric would call a C-grade
estate a failure; the era-relative rule correctly calls it a SUCCESS at its own modest promise.
Low absolute quality ≠ poor execution.

## V7.5 Limits (bigger error bars than the present-day grade)

1. **Announcement grades are partly historical reconstruction** — weaker sourcing than
   present-day. The "Promise" score for a 1952 or 1970 estate is a judgement about era context,
   not a documented metric. Error bar is wider than the already-noisy current grade; the
   then-vs-now DELTA compounds both.
2. **Execution overlaps dual-horizon for NEW towns.** Tengah's 2016 "announcement" vs now is
   nearly the same comparison as its LiveNow-vs-Future5Y. v0.7 adds genuinely NEW information
   mainly for MATURE estates with a long realized history.
3. **"Promise" is reconstructed retrospectively** — risk of hindsight bias (reading the known
   outcome back into the original promise). Mitigate by sourcing promise from announcement-era
   master plans, not from how it turned out.
4. **Verdicts can be PENDING** — a young town under-delivering on schedule is not the same as a
   mature town that stagnated. Always tag pending vs settled.

---

# v0.8 — NODE ARCHETYPE FLAG + LIFESTYLE PERSONA (resolves the Holland Village problem)

## V8.1 The problem and the contradiction it exposed

A fourth review noted the framework keeps producing "technically defensible but semantically
awkward" comparisons because Tampines Central (regional town centre), Marine Parade (coastal
node), Queenstown/Dawson (mature HDB node), and Holland Village (private lifestyle enclave) are
"not the same species of place." It flagged that **Holland Village scores BELOW Canberra even
though many people would rather live there**, and defended this as "Core measures universal
liveability, not lifestyle desirability."

**Builder's challenge to that defense:** a "liveability" score ranking a place lower than one
people prefer to live in is a warning, not a clean result. Either (a) Core is really measuring
*amenity-completeness / HDB-town-resemblance* and mislabelling it "liveability", or (b)
"universal liveability" is an average over personas that describes nobody. The review treated
the anomaly as a feature; the builder treated it as a signal the construct is strained. This
connects to the user's earlier Singapore-is-small insight: Holland Village isn't *less liveable*,
it's a different "selection of life" — which universal Core cannot see.

**User decision:** Core measures PROVISION and that is acceptable (option a accepted, knowingly)
— BUT add archetype-aware reweighting. These two are contradictory IF reweighting touches Core
(archetype-relative Core is no longer comparable across archetypes — a Holland Village 4.0 and a
Tampines 4.0 would mean different things). 

**Resolution (user-confirmed):** Core stays **archetype-BLIND** (a pure, comparable provision
yardstick). The archetype flag is **interpretive metadata only**. The archetype-reweighting
intent is relocated to the **persona layer** as a new **Lifestyle-seeker persona** — the layer
explicitly allowed to be non-comparable, so reweighting there does not poison Core.

## V8.2 Node-archetype flag (non-scored metadata)

Every scored node carries one archetype tag. It changes NO weights in Core. It tells the reader
what *kind* of place a provision score describes, so a low score on a D-enclave is read as
"by-design different," not "deficient."

| Tag | Archetype | Examples |
|-----|-----------|----------|
| **A** | Regional town centre | Tampines Central, (Pasir Ris → A after CRL/ITH maturation) |
| **B** | Mature HDB town-centre node | Queenstown/Dawson, Bukit Panjang/Senja, Pasir Ris Central |
| **C** | Coastal / park-adjacent town node | Marine Parade, (Pasir Ris also park-adjacent) |
| **D** | Private / mixed-use lifestyle enclave | Holland Village, Bukit Timah belt, Serangoon Gardens |
| **E** | New-town early precinct | Tengah, (Canberra = B/E hybrid by catchment) |

**Rule:** never compare raw Core across archetypes without stating the tags. "Tampines (A) 4.30
vs Holland Village (D) 3.68" is a category comparison, not a verdict that Tampines is "more
liveable" — it is more *provisioned*. Cross-archetype ranking requires the Value score or a
persona, not raw Core.

## V8.3 NEW: Lifestyle-seeker persona (the archetype reweighting, relocated)

The fourth persona. Captures the buyer who values character, F&B, walkable vibrancy, transit to
social/work nodes, and rental flexibility OVER self-contained heartland provision (polyclinic,
wet market, public green mass, schools). This is the persona for whom Holland Village is
*correctly* a top choice — and now the framework can SAY so without distorting Core.

```
w_lifestyle(i) = w_core(i) + Δ_lifestyle(i)   (renormalise); non-comparable to Core by design
```

| Component | Lifestyle Δ | Rationale |
|-----------|------------:|-----------|
| 1 Connectivity | +6 | Transit to social/work/nightlife nodes is central |
| 2 Amenities | +3 | But weighted toward F&B/retail vibrancy (read via archetype) |
| 3 Green/blue | −2 | Pocket greenery acceptable; not a deal-driver |
| 4 Schools | −10 | Largely irrelevant to this persona |
| 5 Density/built form | +4 | Values character/built fabric, walkability |
| 6 Healthcare | −6 | GP access fine; polyclinic anchor not required |
| 7 Momentum | +2 | Cares about an improving scene |
| 8 Infra readiness | +1 | Wants it working, low patience for promises |
| 9 Env comfort | +2 | Nightlife/crowd trade-off accepted but not ignored |
| **Sum** | **0** | |

**Effect:** under the Lifestyle persona, Holland Village (D-enclave) rises sharply — its CCL
access (+CCL6 from 12 Jul 2026), F&B density, and character get rewarded; its missing polyclinic
and modest public green stop dragging. This is the correct home for "I'd rather live in Holland
Village" — a stated PREFERENCE, scored as a preference, not smuggled into universal Core.

## V8.4 Updated persona roster (now four)

| Persona | Maxes | Minimises | Best-fit archetype |
|---------|-------|-----------|--------------------|
| Young family | Schools, green, env-comfort | Cost-sensitivity, momentum | A, B |
| Single professional | Connectivity, cost-value | Schools | A, C, D |
| Retiree | Healthcare, green, amenities | Schools, momentum | B, C |
| **Lifestyle-seeker (NEW)** | Connectivity, character/density, F&B | Schools, healthcare-anchor | **D**, A |

## V8.5 What this does and does NOT fix

**Fixes:** the semantic awkwardness. Holland Village's low Core is now explicitly "low PROVISION,
high lifestyle-fit (D archetype)" rather than an implied verdict that it's a worse place to live.

**Does NOT fix:** the deeper question of whether universal Core *should* exist at all. The user
chose to keep it (as a provision measure). The builder's standing concern remains logged: a
single "universal liveability" number, in a small city where most estates are broadly liveable,
may describe nobody — and Value + persona-fit may be the only truly decision-relevant outputs.
The Lifestyle persona narrows this concern (Core is now honestly a provision index, not pretending
to be "desirability") but does not eliminate it. Revisit at v1.0.

# APPENDIX A — Decision Log & Argument History

*Purpose: preserve the reasoning, the rejected alternatives, and the open disagreements so a
future review (≈1 year out) does not re-litigate settled questions or silently reverse a
deliberate choice without knowing why it was made. Read the "why rejected" column before
proposing to add anything back.*

## A.1 How this framework was produced

Built iteratively (v0.1 → v0.4) through adversarial review: an initial framework, the user's
challenges, two independent external AI-assisted reviews, and one primary-source historical
check (Dover/Canberra MRT). Stance throughout: treat polished, confident input — from the
user, from reviewers, from any future agent — as something to stress-test, not adopt on
presentation quality.

## A.2 Locked decisions and the reasoning behind them

| # | Decision | Why | What was rejected, and why |
|---|----------|-----|----------------------------|
| 1 | Grade is for **liveability**, not investment | User's stated goal: "where should I live." | Investment timing — different weights entirely; would corrupt liveability weighting (e.g. capital appreciation, en-bloc potential). |
| 2 | **Past build chronology is NOT a scored axis** | User conceded nobody experiences the 1979 condo-vs-flat order; it's an *input* to today's state, not a component. | User's original request (announce→BTO→condo→landed sequence). Tested and dropped as primary axis. |
| 3 | Timeline survives only as **forward trajectory** (momentum + infra phasing) | A resident lives in the present state and its derivative, not its history. | Treating historical sequence as liveability-relevant. |
| 4 | **"Mature/non-mature" retired as an organising concept** | Officially abolished; mature/non-mature ran 1992–2024, replaced by Standard/Plus/Prime from the Oct 2024 BTO launches (verified). Anchoring a 2026 grade to a deleted category is unsound. | Building the grade around "estate maturity." |
| 5 | Spatial unit = **two-tier**: compute at URA subzone, report at HDB-town + named enclave, with mandatory dispersion flag | A person lives "near Canberra MRT," not in "Sembawang planning area" abstractly. | (a) URA planning areas alone — too coarse, hides intra-town variance. (b) HDB's 27 towns as the *public* unit (proposed by review #1) — silently drops ALL private/landed enclaves; wrong for a liveability (not public-housing) framework. |
| 6 | Sub-metrics are **scoring guidance**, not separately weighted terms | Usability: ~45 weighted sub-scores/subzone across ~150 subzones = unpopulatable. | Review #1's full sub-metric explosion (amenities×5, healthcare×5, connectivity×6, green×6). Rejected as rigorous-but-unusable; trade-off (less transparency) accepted and logged as weakness #3. |
| 7 | **Cost removed from Core**; published as separate Value score | Cost is downstream of liveability (good infra/schools → higher price); blending double-penalises good estates. | Cost as a normal weighted component (was 8% in v0.1–0.2). |
| 8 | Value = **regression-residual**, not percentile divisor | Asks "cheap/dear vs predicted liveability," not "expensive = bad." Percentile punishes good estates for being good. | Simple cost-percentile divisor (kept only as pilot sanity-check). Adjustment capped 0.75×–1.25×. |
| 9 | **Trajectory D is time-discounted**, symmetric for gains and losses | A polyclinic closing next year ≠ a possible consolidation in 2035; a station opening next month ≠ a line in 2032. | Binary loss tiers (v0.2). Replaced with severity×certainty×time_factor. |
| 10 | **Selective vetoes**, persona-conditional | A schools=1 isn't a universal dealbreaker (irrelevant to a retiree); a momentum=1 isn't a present failure at all. | (a) Blanket "any component=1 caps at C" — too crude. (b) Review #1's "healthcare=1 caps universal at B" — a B-cap isn't a veto, it's a fudge; cleaned to retiree→C, universal no-cap. |
| 11 | Component 10 stays **reserved**; if filled, **estate stewardship** | Stewardship (cleanliness, lighting, maintenance, neglect) is observable and behaviour-based. | See A.4 — the permanent rejection of "social mix." |
| 12 | Env comfort (heat/shade/noise/construction/flood) added as **component 9** | Singapore-specific; a shaded 700m beats an exposed 400m. Missed in v0.1–0.2 by both the user and the first builder. | Folding it entirely into green-space/density — judged insufficient. |
| 13 | Young-family env-comfort Δ = **+2** (was −6 in v0.3) | Families are MORE sensitive to heat/noise/construction (stroller routes, school walks, infant sleep), not less. | v0.3's −6 — logged at the time as "the weakest cell in the framework"; corrected via review #2. |

## A.3 The Dover/Canberra finding and the over-provision override

**User hypothesis (v0.4 turn):** "Dover is similar to Canberra."

**Finding (primary sources, LTA/Wikipedia/news):** Surface-similar (both infill stations on
an operating line, both mooted years before opening), but their *timing logic is opposite*:
- **Dover (2001)** — built AHEAD of demand into partly-undeveloped land; criticised for
  "taxpayers' money for one institution" and low catchment; LTA proceeded citing planned
  future residential development. Still ~7,900 pax/day in 2024. → the Punggol "infrastructure
  leads" pole.
- **Canberra (2019)** — corridor (NS12) reserved since the 1990s but the stop was
  *deliberately withheld* until enough housing existed, to avoid a "white elephant." → the
  "demand leads, infra lags, resident suffers the gap" pole.

Conclusion: Dover and Canberra are not similar — they are the **two opposite poles** of the
exact axis component 8 measures.

**OVERRIDE OF THE USER (logged explicitly):** The user then asked that Dover-style
over-provision carry "a small penalty" because it "signals an unfilled, desolate estate."
This was **not implemented as requested.** Reason: a penalty inside component 8 would mark
*down* infrastructure-built-ahead-of-demand — i.e. it would penalise Dover AND early Punggol,
inverting the founding lesson of the whole framework. The user's *actual intent* (penalise a
desolate, unfilled estate) was instead routed through components 2 (amenities not open), 5
(empty-density floor), and 9 (construction disruption), where it self-lifts as the estate
fills in. A pure taxpayer-efficiency over-provision metric was deliberately excluded as a
fiscal, not liveability, concern.
*If a future review wants to revisit:* the question to answer first is "does present-but-quiet
infrastructure reduce a current resident's quality of life?" If no, the override stands.

## A.4 Permanent ethical exclusion — "social mix" (do NOT reverse without reading this)

"Social mix" / "community composition" as a *scored* liveability component is **rejected
permanently, not deferred.** A liveability index that rewards "social mix" becomes a laundered
proxy for *fewer rental flats / fewer lower-income neighbours* — sorting by class, and in
other jurisdictions by race, under a neutral-sounding label. Both the human and the reviewing
agents converged on this. Estate **stewardship** (how an estate is *cared for*) is the
acceptable substitute because it measures upkeep, not *who lives there*. A future agent
proposing to add "social mix / diversity / community" to Core should treat this paragraph as a
standing objection to overcome, not an oversight to fix.

## A.5 Open disagreements / unresolved at v0.4 (revisit these first next year)

| Item | State | Notes for next review |
|------|-------|-----------------------|
| Young-family infra-readiness Δ | Set to **−2** (compromise) | Builder argued 0 (families need operational infra now); review #2 argued −3 (conflating readiness with future-promise momentum); user chose "−1 or −2." Genuine unresolved tension between "present-state" and "promise" framing. |
| Young-family Δ column sums to **+1**, not 0 | Flagged, absorbed at calibration | Trim Connectivity to −8 or Schools to +6. Not silently fixed — left visible. |
| Desolation under-counting (weakness #7) | Untested | Routing desolation through 2/5/9 may under-count if an empty estate scores okay on those three. Watch in pilot. |
| Whole-grade D multiplier asymmetry | Accepted, flagged | Strips more absolute points from strong estates than weak ones. May under-penalise losses hitting residents of weak estates who can least absorb them. User chose this knowingly. |
| Components 3,5 vs 2 negative correlation | Structural, unsolved | Additive model blurs dense-hub vs quiet-estate exactly where preferences diverge most. No fix in v0.4. |
| Stewardship into Core | Deferred | Admit only after repeatable measurement, real spread, incremental explanatory value shown in pilots. |
| Noise/shade/construction/aircraft proxies | Unbuilt | Env-comfort kept as one 1–5 precisely because these need proxy work; method TBD. |

## A.6 Facts verified during development (re-verify; these decay)

| Fact | As-of | Why it mattered |
|------|-------|-----------------|
| Mature/non-mature → Standard/Plus/Prime, effective Oct 2024 BTO launches; old system ran from 1992 | verified 2026 | Killed "maturity" as the organising concept (decision #4). |
| Canberra MRT: NS12 reserved 1990s, opened 2 Nov 2019, deliberately delayed to avoid white-elephant | verified | The founding infra-readiness example. |
| Dover MRT: first infill station, mooted 1988, opened 18 Oct 2001, built ahead of demand, low-catchment criticism | verified | The over-provision pole (§A.3). |
| CCL6 passenger service 12 Jul 2026 (3 stations, completes the Circle Line) | verified 2026 | Momentum time-discount anchor. |
| JRL Stage 1 ~mid-2028; CRL1 / CRL-Punggol ~2030/2032 | from review, NOT independently verified | Momentum anchors — **re-verify before relying on for scoring.** |
| HDB resale dataset current to ~Jun 2026; private = separate URA universe | from review | Value model segmentation. |

> **Standing instruction for the next review:** dates and "current holder of X" facts decay.
> Re-verify everything in A.6 before scoring. Do not trust this appendix's facts a year on
> without a fresh search.
## A.7 v0.5 decisions (added)

| # | Decision | Why | Rejected alternative |
|---|----------|-----|----------------------|
| 14 | Weights renormalized to exactly 1.000 | v0.4 vector summed to 1.001 (bug; inflated all Core ~0.1%, changed no grade) | Leaving it — sloppy for a bounded 1–5 claim. |
| 15 | **Two equal headline grades: LiveNow + Future5Y** | v0.4 blended "live today" with "buy for 2030" into one misleading axis. | Single horizon (user rejected); LiveNow-primary/Future-secondary (user chose equal billing). |
| 16 | S8 timing: LiveNow=scoring-date, Future5Y=move-in-horizon | Canberra's historical lag must NOT penalise its present score; Tengah's present lag must. | Literal "original residents' move-in" — produces nonsense (penalises Canberra in 2026 for a gap closed in 2019). Builder flagged and corrected. |
| 17 | S8 kept full-weight, sharpened vs S1 | User override of reviewer's demotion; preserves founding decision. Duplication removed by definition split (S1=quality-when-present, S8=operational-at-horizon). | Reviewer's lag-modifier demotion (user rejected). |
| 18 | S7=additions only; D=losses only | Removes Momentum/D double-count of the same future improvement. | Symmetric D (builder had argued FOR this in v0.2–0.4; now reversed as wrong). |
| 19 | Schools 10.4%→8.2% in universal | P1 priority is address-level; estate-coarse scoring overweighted it. | Reviewer's near-exile to family-persona only — rejected; childless buyers still value catchment via resale/character. |
| 20 | Promise-risk = Certainty×Time×SlipPremium, NOT a flat constant | Reuses existing D-table; only SlipPremium (0.85 rail) is new. | Builder's original flat 0.70 — invented constant, rejected by builder self-review. |
| 21 | Private enclaves: mobility TAG, not separate car-mobility axis | Preserves comparability; flags distortion without rewarding car-dependence. | Separate car-mobility scale — would inflate wealthy car-dependent enclaves against car-lite policy; laundering risk (cf. A.4). |

## A.8 Open challenges queued for v0.6 (user intends to contest)

- **SlipPremium = 0.85** is from ~3 anecdotes, not a delivery-variance dataset. Highest-priority
  number to replace with real data.
- **Mobility tag sufficiency:** does tagging car-primary enclaves actually solve the category
  error, or just hide it behind a label? Unresolved.
- **Future5Y promise risk on a per-line basis:** specific SG lines have specific slip histories;
  a single SlipPremium may be too blunt.
- **Cross-grader divergence (±0.3):** the framework is not yet reproducible to better than a
  third of a grade-band between analysts. Only GIS data closes this.
## A.9 v0.6 decisions (added)

| # | Decision | Why | Rejected alternative |
|---|----------|-----|----------------------|
| 22 | S11 conditional car-mobility axis (activates only for car-primary tag) | User: car-primary residents derive real mobility from expressways/multi-node drive, not MRT. | v0.5 interpret-only tag (user upgraded it to a scored axis). |
| 23 | When S11 active, S1 transit weight HALVED not zeroed | Household non-drivers, resale demand, car-loss all keep transit relevant. | Zeroing S1 (user's opening logic) — builder argued down: would let a 2-car bungalow out-score an MRT-side flat. |
| 24 | Mandatory cost-of-car-dependence DRAG on S11 | Without it, S11 rewards affluence (car ownership) as liveability — laundering trap, cousin of A.4 social-mix exclusion. | Pure car bonus (rejected; user agreed to drag). |
| 25 | Multi-district drive time, not CBD-only | Real SG job geography: JLD, one-north, Changi BP, Tuas, Woodlands, Paya Lebar. | CBD-centric mobility. |
| 26 | Industrial proximity scored dual-signed | Good for industrial-sector workers, bad for ambient quality — net per estate, tension preserved not resolved. | Treating industrial proximity as purely negative. |
| 27 | **Report BANDS not decimals until GIS data** | 6/8 estates within 0.34; cross-grader noise ±0.3. Decimals are below the noise floor = false precision. | User's "precise grading" taken literally now — builder pushed back: precision is the GOAL, not yet DELIVERED. Banding is the interim guard. |
| 28 | Singapore-scale compression documented as core limitation | Small city = compressed real differences; Value + persona-fit out-rank Core for established estates. | Treating Core point-scores as the primary resident output. |

## A.10 The Singapore-scale finding (preserve — reframes the whole framework)

In a large country, liveability grading answers "WHERE should I live" (which city/state —
people migrate across large distances to resolve dissatisfaction). In Singapore — one island,
one labour market, ~25km max, one amenity network — that question is mostly pre-answered: most
established estates are broadly liveable. The live questions become "where is liveable FOR ME,
at WHAT PRICE." Consequences locked in v0.6:
- Core differences among established estates are real in ordering but sub-resolution in
  magnitude → band, don't over-resolve.
- Value (price-for-equivalent-liveability) and persona-fit are the high-information outputs.
- Core's discriminating power is greatest for NEW/transitional towns (wide spread) and weakest
  for the mature cluster (saturated near "broadly good").
- Standing caution: a precise-looking small-city liveability score manufactures false
  distinctions unless disciplined by banding and by leading with Value + fit.
## A.11 v0.7 decisions (added)

| # | Decision | Why | Rejected alternative |
|---|----------|-----|----------------------|
| 29 | Then-vs-now added as REALIZED EXECUTION, not build-chronology | Loops back to v0.1's cut of "build order" — but this measures delivery-vs-promise, a different and useful thing. | Re-adding raw build sequence (still rejected per Appendix A.2 #2). |
| 30 | Absolute delta = CONTEXT ONLY; era-relative = the execution measure | Absolute climb mostly reflects national development (rising tide), not estate-specific delivery. Only era-relative controls for the tide. | Treating absolute delta as an execution signal (user picked "both"; builder demoted absolute to context to avoid measuring the wrong thing). |
| 31 | Execution = promise-vs-realization, NOT absolute quality | An estate that promised basic and stayed basic DELIVERED; one that promised premium and slipped UNDER-delivered despite high absolute grade. | Equating low current grade with poor execution (would mislabel Canberra a failure). |
| 32 | Verdicts can be PENDING for young towns | Tengah under-delivering on a still-scheduled timeline ≠ a mature town that stagnated. | Binary delivered/failed (would prematurely condemn Tengah). |
| 33 | Promise sourced from announcement-era master plans, not hindsight | Guards against reading known outcomes back into original promise. | Reconstructing promise from current state (hindsight bias). |

## A.12 The execution finding (preserve)

Then-vs-now, done honestly, measures whether PLANNERS DELIVERED relative to peers — controlling
for the national rising tide via era-relative ranking. Key results: most established estates
"delivered as promised" (the healthy default); a few over-delivered (Tampines, Queenstown,
Pasir Ris); Tengah is the only under-delivery and its verdict is PENDING, not failed. Execution
(backward) and Future5Y (forward) must be read together for new towns: Tengah is simultaneously
"under-delivered so far" and "B+ projected" — neither alone is the truth. Execution adds the most
NEW signal for MATURE estates, where a long realized history exists to judge and where the
forward dual-horizon adds little.
## A.13 v0.8 decisions (added)

| # | Decision | Why | Rejected alternative |
|---|----------|-----|----------------------|
| 34 | Node-archetype flag (A–E), non-scored | Different "species of place" need interpretive context so a D-enclave's low provision score isn't misread as a liveability verdict. | Forcing all node types into one comparable row with no tag (reviewer flagged this as producing awkward comparisons). |
| 35 | Core stays archetype-BLIND | Archetype-reweighted Core would lose cross-archetype comparability (a Holland Village 4.0 ≠ a Tampines 4.0). User confirmed after builder surfaced the contradiction. | Archetype-relative Core (user's initial 2nd answer; reversed after seeing it breaks comparability). |
| 36 | Archetype reweighting relocated to NEW Lifestyle-seeker persona | Personas are explicitly non-comparable, so reweighting there is safe; it's also the honest home for "lifestyle desirability." | Putting reweighting in Core (rejected, per #35). |
| 37 | Holland-Village-below-Canberra logged as a CONSTRUCT concern, not just resolved | Builder dissented from reviewer's "it's a feature" framing; a liveability score below a more-preferred place signals Core may measure provision/HDB-resemblance, not liveability. User kept Core as provision knowingly. | Accepting the anomaly silently as a clean result. |

## A.14 The construct-validity question (carry to v1.0 — do NOT consider closed)

Across v0.6 (Singapore-scale compression), v0.7 (execution), and v0.8 (archetypes/Holland
Village), one question keeps resurfacing and is NOT resolved: **does a single "universal
liveability" Core score measure a real thing, or is it a provision index wearing a liveability
label, averaging over personas in a way that describes no actual resident?** Decisions so far
(keep Core as an explicit PROVISION measure; push desirability into Value + four personas) make
Core *honest* about what it is, but do not prove it's the most decision-useful output. Standing
builder position: in small, broadly-liveable Singapore, **Value (price-for-equivalent-provision)
and persona-fit are likely the primary outputs; universal Core is a comparability scaffold, not
the headline a resident should read first.** Resolve explicitly at v1.0: keep Core as headline,
demote it to scaffold, or replace it with a "provision" label and stop calling it "liveability."
