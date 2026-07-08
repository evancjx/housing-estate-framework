# Singapore Estate — LIVEABILITY MATRIX (Document 2 of 2)

*Demand-side · person-relative · NON-comparable by design. The verdict for a life.*
*Companion: **Document 1 — Provision Framework**. This document takes Provision as an input.*

---

## 0. What this document is

**Liveability = what it's like for THIS person to live here, now and later.** Not a property of
the place — a *relationship* between the place and a life. It takes Provision (Document 1) as raw
material and adds the things provision cannot see: **fit** (does this provision match this life),
**cost** (what you pay for it), **trajectory** (how the fit changes over time), and
**private anchors** (work and care networks that only matter to this household).

**There is no single liveability number.** Liveability is a **matrix**: persona × time-horizon.
A universal liveability score would be an average over personas that describes no actual resident
— the error Document 1 was renamed to escape. This document is deliberately non-comparable across
its own cells: a "young-family/now" cell and a "retiree/future" cell are not meant to be ranked
against each other. They serve different people, or the same person at different times.

---

## 1. The matrix: 4 personas × 2 horizons (T0 / T5)

> The model now emits a **third horizon T15** (15-year) on top of this base matrix — see
> addendum L9.1. The committed `data/outputs/liveability_matrix.csv` carries all three (T0/T5/T15).

For each estate, up to 8 cells. **Reported as BANDS + life-path arrows, not a decimal grid**
(option 3 — full coverage without false precision; a decimal 8-grid would put ~6 of 8 cells
inside the ±0.3 noise floor).

|  | **LiveNow (T0)** | **Future5Y (T5)** |
|---|---|---|
| **Young family** | fit of present provision to family needs | + confirmed schools/transit/amenities by T5 |
| **Single professional** | present connectivity/value fit | + confirmed additions by T5 |
| **Retiree** | present healthcare/green/amenity fit | + ageing-in-place trajectory by T5 |
| **Lifestyle-seeker** | present character/F&B/transit fit | + scene/transit evolution by T5 |

### 1.1 How each cell is computed
```
Cell(estate, persona, horizon) =
    Σ [ w_persona(i) × S_i(horizon) ]  ×  D(estate)  ×  C_persona(estate)
    then expressed as a BAND, and adjusted by Value (§3) when a Value read is requested.
```
- `w_persona` = Document-1 weights + persona Δ (below), renormalised. Non-comparable across personas by design.
- `S_i(horizon)`: T0 uses present-state; T5 folds in confirmed additions, each discounted by
  Certainty × Time × SlipPremium (rail 0.85). Promises are NOT counted at face value.
- `C_persona`: persona-specific vetoes (e.g. Schools=1 caps young-family at C; Healthcare=1 caps retiree at C).
- Public CSV output stops at this base cell. User-specific decision reads may add job-anchor fit
  (§L9.3) and care-network proximity (§4.1), because those require private user-supplied anchors.

---

## 2. The four personas (signed Δ on Document-1 weights; each column sums to 0)

| Component | Young family | Single pro | Retiree | Lifestyle-seeker |
|-----------|----:|----:|----:|----:|
| 1 Connectivity | −7 | +8 | −3 | +6 |
| 2 Amenities | +1 | +2 | +4 | +3 |
| 3 Green/blue | +4 | −2 | +4 | −2 |
| 4 Schools | +7 | −9 | −9 | −10 |
| 5 Density/built form | 0 | −3 | +2 | +4 |
| 6 Healthcare | +1 | −4 | +12 | −6 |
| 7 Momentum | −5 | +3 | −5 | +2 |
| 8 Infra readiness | −2 | +1 | −2 | +1 |
| 9 Env comfort | +2 | +4 | −3 | +2 |
| (sums to 0 after minor calibration rounding) | | | | |

> **v2.0 note (20-component model):** The three new provision components fold into existing S-groups
> without adding new groups — `stewardship` → S8 (Infra readiness); `air_quality` and
> `jtc_industrial` → S9 (Env comfort). `PERSONA_DELTAS` remains a 9-group structure; no persona
> delta changes are required.

---

## 3. Value lives HERE, not in Provision (cost is demand-side)
Cost is what *you* pay — a relationship with a person, so it belongs in Liveability, not Provision.
```
Value(a,g) = Liveability_cell(a, persona, T0) × exp(−ValueResidual(a,g))
ValueResidual = regression residual: is this estate cheap/dear vs what its liveability predicts?
```
Regression-residual (not crude percentile), segmented by tenure (HDB resale / private resale /
private rental), with hierarchical shrinkage (transaction→project→subzone→town) so thin private
samples don't distort. Adjustment capped 0.75×–1.25× until calibrated.

**In small, broadly-liveable Singapore, Value is arguably the PRIMARY output** — provision is high
almost everywhere, so what varies most is price-for-equivalent-liveability and personal fit.

### 3.1 Employment-hub demand pressure — value context, not liveability

Living near a business / industrial hub has two different effects:

1. **Commute fit:** useful to the resident if their job anchor is that hub (§L9.3).
2. **Demand pressure:** more jobs can raise housing demand nearby and may support faster
   accommodation-value growth over time.

These are not the same score. Commute fit belongs in Liveability; demand pressure belongs beside
Value as an investment / market-context read. Do **not** blend expected appreciation into
Liveability, because "where should I live" and "what will appreciate fastest" can point to
different estates.

Judge employment-driven demand pressure as a thesis-strength tag, not a guaranteed return:

```
HubDemandSignal(estate, horizon) =
    job_growth_certainty
  × commute_catchment_gain
  × housing_supply_tightness
  × amenity_follow_through
  × nuisance_discount
```

| Input | High signal | Low signal |
|-------|-------------|------------|
| `job_growth_certainty` | confirmed / under-construction employment node | speculative or long-dated plan |
| `commute_catchment_gain` | many homes move into <=30-45 min access to the hub | hub remains hard to reach |
| `housing_supply_tightness` | limited nearby new housing relative to jobs | major housing supply absorbs demand |
| `amenity_follow_through` | retail, food, schools, parks and transport arrive with jobs | isolated workplace with weak daily amenities |
| `nuisance_discount` | office / research / light-business hub | heavy industrial, freight, air/noise/traffic drag |

Output tags:

| Tag | Meaning |
|-----|---------|
| `structural_uplift_thesis` | jobs + access + amenities are strong, and housing supply is constrained |
| `selective_uplift_thesis` | upside exists, but only for subzones/projects with good access and low nuisance |
| `priced_in_or_supply_absorbed` | benefits likely already capitalised or diluted by large new supply |
| `nuisance_discount_dominant` | job access exists, but industrial/environmental drag weakens residential desirability |

---

## 4. LIFE-PATHS — the answer for a real human (your "current and future life" point)
A person is not one persona frozen in time. Read the matrix as a **path**, not a cell:

| Life-path | Reads cells | Who |
|-----------|-------------|-----|
| **Forming family** | single-pro / T0 → young-family / T5 | couple planning kids |
| **Downsizing** | young-family / T0 → retiree / T5 | empty-nesters |
| **Settling single** | lifestyle / T0 → single-pro / T5 | career-focused, staying urban |
| **Ageing in place** | retiree / T0 → retiree / T5 | already retired, will they still cope |
| **Upgrader** | single-pro / T0 → lifestyle or family / T5 | trading up |

**The diagonal path across the matrix IS the liveability answer for an actual life** — something
neither a single Provision number nor a flat persona list could express. An estate great for
single-pro-now but weak for family-future is a *bad* "forming family" choice even if both cells
look individually fine, because the *path* matters.

### 4.1 Care-network proximity — user-supplied anchor overlay

Care-network proximity measures whether the household can realistically give or receive help from
its actual support network: parents, adult children, regular caregivers, co-parents, or relatives
who provide childcare / eldercare backup. It is **not** an estate component and **not** a proxy for
social mix. If no care anchor is supplied, the value is `N/A`, not a penalty.

```
CareFit(estate, horizon) =
    Σ [ priority(anchor) × time_score(travel_time_to_anchor) ] / Σ priority(anchor)
```

`travel_time_to_anchor` is door-to-door in the required direction and mode at the relevant care
window. Use the worse direction for reciprocal care. Use the household's stated mode: walk,
transit, taxi/car, or mixed.

| Travel time to anchor | `time_score` | Judgement |
|----------------------:|-------------:|-----------|
| <=15 min | 5 | daily care is realistic |
| >15-30 min | 4 | frequent care is realistic |
| >30-45 min | 3 | weekly/planned support is realistic |
| >45-60 min | 2 | fragile; care requires planning |
| >60 min | 1 | weak; emergency-only in practice |

Priority is not guessed from demographics. It is supplied by the user:

| Anchor role / frequency | Priority |
|-------------------------|---------:|
| daily primary care dependency | 1.00 |
| several-times-weekly support | 0.75 |
| weekly support | 0.45 |
| emergency / backup only | 0.25 |

Report the overlay as a tag:

| `CareFit` | Tag |
|----------:|-----|
| >=4.25 | `strong_care_fit` |
| 3.50-4.24 | `adequate_care_fit` |
| 2.50-3.49 | `fragile_care_fit` |
| <2.50 | `weak_care_fit` |

Critical-anchor cap: if a daily primary childcare or eldercare anchor scores <=2 (>45 min), the
relevant life-path is capped at C unless a documented substitute exists (e.g. paid care near home).
This cap is user-specific and never changes the estate's Provision score.

---

## 5. Worked illustration — Holland Village vs Tampines (bands, not decimals)

| | Provision (Doc 1) | Lifestyle/now | Young-family/now | Retiree/now | "Forming family" path |
|---|:--:|:--:|:--:|:--:|:--:|
| Holland Village (D) | B | **A-band** | C | C | weak (great now, poor family-future) |
| Tampines (A) | B+ | B | **A-band** | **A-band** | strong |

**The finding the split exists to produce:** Holland Village has *lower Provision* than Tampines
(true, objective) but *higher Lifestyle liveability* (true, person-relative). These don't
contradict — they triangulate. A single old "Core" number hid this; the two documents reveal it.
The **Provision–Liveability Gap** for Holland Village is large and POSITIVE for the lifestyle-seeker
(punches above its provision) and NEGATIVE for the young family (well-located but poor family fit).

---

## 6. How the two documents challenge each other (the point of splitting)
- Provision says **"well-equipped."** Liveability asks **"for whom, and at what price?"**
- When they AGREE (high provision + high persona fit) → unambiguous good choice for that life.
- When they DIVERGE → the gap is the signal, not an error:
  - High Provision, low Liveability → over-equipped for this person / overpriced / characterless.
  - Low Provision, high Liveability → the Holland Village case: lovable despite the checklist.
- Neither document can be "wrong" against the other — they measure different things. The
  *relationship between them* is the deliverable.

---

# APPENDIX A — Decision Log & Argument History (v0.1 → v0.9, shared across both documents)

*Preserves reasoning and rejected alternatives so a future review (~1yr) does not re-litigate or
silently reverse deliberate choices. Read "why rejected" before re-proposing anything.*

## A.0 The split (v0.9)
The framework was split into Provision (Doc 1) + Liveability Matrix (Doc 2) after the construct
question (A.14, prior version) forced a reckoning: "Core" was measuring provision but called
itself liveability, producing anomalies (Holland Village < Canberra while more preferred). User
chose two cross-referencing documents; the gap between them is now the headline output. The
Liveability side is a persona×horizon matrix because "current and future life matters to different
people" — a single score can't serve a couple-becoming-parents and a downsizing retiree at once.

## A.1 Locked decisions (carried; abbreviated — full text in prior versions)
Liveability not investment · past build-order NOT scored (only forward trajectory) · mature/
non-mature retired (Standard/Plus/Prime, Oct 2024) · two-tier spatial (compute subzone, report
town+enclave w/ dispersion flag) · sub-metrics are guidance not separate weights · cost split out
(now in Doc 2 as Value) · regression-residual Value · time-discounted trajectory · selective
vetoes · stewardship-not-social-mix (permanent ethical exclusion) · env-comfort component added ·
dual horizon LiveNow/Future5Y · S7 additions-only / D losses-only · schools trimmed · Estate Fill
Ratio desolation diagnostic · S8 kept full-weight, sharpened vs S1 · S8 timing: LiveNow=scoring-
date, Future5Y=move-in-horizon · promise-risk = Certainty×Time×SlipPremium (rail 0.85) · private
enclaves: car-mobility S11 conditional + cost-of-car-dependence drag · node-archetype flag (A–E)
interpretive-only · Core archetype-BLIND · lifestyle-seeker persona added · **Core renamed
Provision; framework split in two (v0.9).**

## A.2 Overrides of the USER (logged for honesty)
- Dover over-provision: user wanted a penalty; builder routed desolation through S2/5/9 instead,
  kept S8 clean (penalising infra-ahead-of-demand would invert the founding Canberra lesson).
- "Car → transit irrelevant": builder refused to zero S1; halved it + added dependence drag.
- "Differences worth PRECISE grading": builder downgraded to BANDS (differences real in ordering,
  sub-resolution in magnitude; 6/8 inside ±0.3 noise).
- "Absolute then-vs-now delta": builder demoted to context-only (it measures national rising tide,
  not planner execution); era-relative rank-shift is the real execution measure.
- Archetype-reweighted Core: builder showed it breaks comparability; reweighting moved to the
  Lifestyle persona instead.

## A.3 The big standing findings (preserve)
1. **Singapore-scale compression**: small city → real differences exist but are compressed;
   provision saturates; Value + persona-fit out-rank Provision for established estates.
2. **Provision ≠ Liveability**: what's *there* vs what it's *like for you*. The rename + split fix
   the central mislabel. Provision is universal/comparable BECAUSE it ignores the person;
   liveability fractures into the matrix because it doesn't.
3. **The gap is the product**: divergence between the two documents (esp. Holland Village positive
   gap, Tengah's now/future split) is the most decision-useful signal the system produces.
4. **Execution (then-vs-now)**: era-relative only; most estates "delivered as promised"; Tengah
   under-delivered but PENDING (read with Future5Y).

## A.4 Open challenges queued for v1.0
- SlipPremium 0.85 is from ~3 anecdotes, not a dataset — replace with delivery-variance data.
- Mobility tag/drag: does it solve the car-affluence problem or just label it?
- Matrix noise: 8 cells × N estates mostly inside ±0.3 — bands mitigate but don't eliminate.
- Does Provision deserve to be a HEADLINE at all, or only a scaffold under Value + personas?
- Reconstructed "promise" scores for old estates risk hindsight bias.
- **Re-verify all dated facts before any real scoring run — they decay.**

---

# v0.9 ADDENDUM (Liveability side)

## L9.1 Third horizon: Strategic15Y (the matrix becomes persona × THREE horizons)
Future5Y cannot hold multi-decade strategic shifts (JLD's 2040–2050 thesis; Woodlands RTS +
checkpoint redevelopment from 2029). Added horizon:
| Horizon | Question | Best for |
|---------|----------|----------|
| LiveNow (T0) | Where is liveable today? | renters, immediate movers |
| Future5Y (T5) | What improves within a BTO/resale holding period? | typical buyers |
| **Strategic15Y (T15)** | What structurally changes as a regional economy/major node? | long-horizon bets, JLD, Woodlands |
Strategic15Y carries the HEAVIEST promise-risk discount (15-yr targets slip most) and must always
be shown with an explicit "strategic bet — high uncertainty" tag. It is NOT comparable to LiveNow.

## L9.2 Execution split: Delivery Reliability × Promise Ambition (fixes the Canberra flaw)
The v0.7 single "delivered as promised" verdict let low ambition masquerade as good execution.
Replaced by a 2×2:
| | Low ambition | High ambition |
|---|---|---|
| **Reliable delivery** | Canberra (modest, delivered) | Tampines/Queenstown (ambitious, delivered) — the gold standard |
| **At-risk / pending** | — | **Tengah** (ambitious, execution-risk, PENDING) |
"Modest-but-reliable" (Canberra) and "ambitious-but-at-risk" (Tengah) are now DIFFERENT verdicts,
not points on one line. Promise ambition is sourced from announcement-era master plans (guards
hindsight bias); a low-ambition reliable delivery is NOT scored as a planning triumph.

## L9.3 Job-node fit is now a first-class Liveability axis
Per Document 1 P9.4, connectivity is anchor-relative. The Liveability matrix gains a job-anchor
dimension: a cell is read as (persona × horizon × job-anchor). A Pasir Ris/Changi-worker and a
Tengah/Jurong-worker are both rationally placed even where a CBD-centric score would punish them.
In practice: don't publish a single connectivity-driven liveability; publish it against the
reader's stated work location.

The production pipeline also publishes employment-accessibility context (`employment_scores_T0`,
`employment_scores_T5`, `employment_scores_T15`). Read it as commute opportunity and strategic
job-node fit, not as an automatic price-growth forecast. The price-growth thesis is handled by
§3.1's demand-pressure tag.

## L9.3A Care-network fit is a user-supplied anchor overlay
Care-network proximity is added as a Liveability overlay, parallel to job-anchor fit but never
folded into Provision. It is judged only from declared care anchors and travel-time practicality,
with `N/A` when no anchor is supplied. This prevents the factor from laundering family structure,
income, ethnicity, or estate demographics into a neutral-looking score.

## L9.4 Rank-or-Profile (mirrors Document 1)
Liveability defaults to a PROFILE, not a ranking. Rank two estates only when same archetype + same
horizon + same persona + same job-anchor + same care-anchor profile AND they differ beyond ±0.3.
Otherwise output the profile: "this place offers [provision] for [household] at [price] on
[horizon], best-fit for [job anchor], with [care-fit tag]."

## L9.5 The nine-estate verdict (profile-led, ranking only where defensible)
| Role | Estate(s) | Note |
|------|-----------|------|
| Best provision today | Bishan / Tampines / Toa Payoh | within noise of each other — DON'T rank among them |
| Best strategic 15Y upside | Jurong Lake / Tengah / Woodlands | high uncertainty, strategic tag |
| Best balanced upgrader | Pasir Ris | LiveNow solid + Future5Y CRL uplift |
| Best compact new-node | Woodleigh | modern integrated, less amenity depth |
| Modest-but-functional | Canberra | reliable delivery, low ambition |
| Most execution-risk | Tengah | ambitious, pending JRL/fill-in |
| Category-breaking | Jurong Lake | X-tag, not a residential estate |

## A.0 (append to decision log) — v0.9 decisions
| # | Decision | Why | Rejected |
|---|----------|-----|----------|
| 38 | Rank-or-Profile gate (default PROFILE) | 3 reviews + own run: one score can't rank the broadly-liveable cluster; differences are sub-noise. | Always-rank (false precision); always-profile (loses the genuine Tengah-vs-Bishan signal). |
| 39 | Strategic15Y added | Future5Y can't hold JLD/Woodlands multi-decade shifts. | Forcing 15-yr bets into a 5-yr window (produced JLD garbage). |
| 40 | Execution = Reliability × Ambition (2×2) | Single "delivered" verdict let Canberra's low ambition look like triumph. | v0.7 single-axis execution. |
| 41 | Job-node fit; S1 anchor-relative | Averaged commute hides the actual reason for estate choice. | Universal CBD-centric connectivity. |
| 42 | Fill Ratio = weighted component (transitional only) | Captures lived desolation penalty without the multiplier's high-provision-bias. | Reviewer's whole-grade multiplier; v0.4 unweighted diagnostic. |
| 43 | Archetype X = strategic district, NEVER ranked vs residential | JLD broke the framework as a scored "estate." | Scoring JLD as a residential estate (the 3.58 bug). |
| 44 | Output reframed: profile-first, rank-exception | The framework's best role is "what provision, for whom, at what price, on what horizon" — not "most liveable." | Headline universal liveability ranking. |
| 45 | Care-network proximity overlay | Actual childcare/eldercare support often dominates district choice, but only relative to a household's private anchors. | Adding family proximity to Provision; inferring support from estate demographics or social mix. |
| 46 | Employment-hub demand pressure separated from liveability | Job nodes improve commute fit and can support housing demand, but appreciation is an investment thesis, not resident liveability. | Folding expected price growth into Liveability or treating industrial proximity as purely positive. |
