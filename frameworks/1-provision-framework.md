# Singapore Estate — PROVISION FRAMEWORK (Document 1 of 2)

*Supply-side · objective · universal · comparable. The scaffold, not the verdict.*
*Companion: **Document 2 — Liveability Matrix**. Read the §"Provision–Liveability Gap" in both.*

---

## 0. What this document is — and the word it stops misusing

This is the framework formerly called "Core Liveability" (v0.1–v0.8), **renamed to what it
actually measures: PROVISION.** The rename resolves the construct-validity problem that
surfaced repeatedly (Holland Village ranking below Canberra while being more preferred).

**Provision = what is here, and is it operational.** It is a property of the *place*, not a
relationship with a *person*. It answers *"is this estate well-equipped?"* — never *"is it good
for ME to live here?"* (that is Document 2's job).

| | Provision (this doc) | Liveability (Doc 2) |
|---|---|---|
| Measures | what's *there* | what it's *like to live there* |
| Side | supply | demand |
| Person? | none — universal | person-relative |
| Output | one comparable number + archetype tag | persona × horizon matrix (non-comparable by design) |
| Saturates? | yes (2nd polyclinic adds little) | no (fit/cost/character never saturate) |
| Role | necessary, not sufficient; the floor | the actual verdict for a life |

**Why split:** a single number cannot be both objective-and-comparable AND person-relevant.
Provision can be universal *precisely because it ignores the person*. The moment you ask "is it
liveable," a person enters and the universal number fractures into personas. Keeping them fused
forced "liveability" to mean "amenity-completeness / HDB-town-resemblance" — and then any place
liveable a *different* way (Holland Village) got marked down for non-conformity. Splitting frees
each to be honest.

---

## 1. The Provision score (the old Core, unchanged math, honest label)

```
Provision(a) = Σ (wᵢ × Sᵢ)        i = 1..20,  Sᵢ ∈ [1,5]
ProvisionFinal(a) = Provision(a) × D(a)      [D = losses/disruptions only; see §4]
```
Output range 1.0–5.0, reported as a BAND (A/B+/B/C/D/F), not a bare decimal (see §6).
**Archetype-BLIND**: every estate scored on the same yardstick so scores stay comparable.

### 1.1 Components and weights — `W` (20 components, sum = 1.000)

Sourced verbatim from `models/framework_config.py:PROVISION_WEIGHTS`. Do not edit here without updating that file.

| # | Key | Weight | Provenance | Notes |
|---|-----|------:|:----------:|-------|
| 1 | `conn` | 0.14 | MEASURED | Walk-time to rail/interchange, feeder freq, transfer penalty, redundancy, multi-node commute, first/last-mile shelter |
| 2 | `infra` | 0.14 | MEASURED | Trunk infra *operational now* (LiveNow horizon). Distinct from conn: conn = quality-when-present; infra = operational-at-horizon. |
| 3 | `amen` | 0.09 | MEASURED | Basics (wet market, supermarket, GP, pharmacy, library/CC) above lifestyle retail. Shops-not-yet-open = desolation signal. |
| 4 | `green` | 0.08 | MEASURED | *Usable* greenery: 400/800m network-walk, shade, size/facilities, PCN continuity, overcrowding |
| 5 | `dens` | 0.08 | PARTLY_MEASURED | Dwelling density yes; "feel" (block spacing, pavement quality) no |
| 6 | `sch` | 0.07 | MEASURED | Practical access (within 1/2km per MOE P1 distance), balloting pressure, preschool→JC reach |
| 7 | `childcare` | 0.05 | MEASURED | Licensed childcare / infant care centres within 800m |
| 8 | `hlth` | 0.04 | MEASURED | Primary-care-first: GP/CHAS/pharmacy + polyclinic access, THEN A&E time |
| 9 | `mom` | 0.04 | PARTLY_MEASURED | Confirmed *additions* only, time-discounted. HDB-side ingested from data.gov.sg NRP+LUP+SERS; private-side en-bloc / new-launch pipeline still JUDGED |
| 10 | `hawker` | 0.04 | PARTLY_MEASURED | Count, distance, stall-capacity and redundancy from `hawker_v2.csv`; fame/reputation remains approximate |
| 11 | `noise` | 0.03 | MEASURED | Expressway exposure: distance-weighted proximity to major expressways |
| 12 | `air_noise` | 0.03 | MEASURED | Geometric runway-centerline + 12 km approach/departure corridor proxy for Changi, Seletar, Paya Lebar (v1.2) |
| 13 | `eldercare` | 0.03 | MEASURED | Eldercare day-centres / AAC / nursing-home density (AIC Silver Pages / MOH registry; v1.3: carved from hlth) |
| 14 | `stewardship` | 0.03 | PARTLY_MEASURED | MND TCMR KPI bands (GREEN/AMBER/RED → 5/3/1). Observable upkeep only — NOT social mix. |
| 15 | `air_quality` | 0.03 | PARTLY_MEASURED | NEA PSI/PM2.5 climatology + expressway road-buffer. Climatology stub until live NEA fetch wired. |
| 16 | `community` | 0.02 | MEASURED | Community clubs, resident corner, active ageing centres (non-eldercare function) |
| 17 | `sport` | 0.02 | MEASURED | SportSG facilities + park connectors with fitness infrastructure within 1 km |
| 18 | `jtc_industrial` | 0.02 | MEASURED | Inverse-distance to JTC heavy-industrial zones; penalty for close proximity |
| 19 | `env` | 0.01 | PARTLY_MEASURED | Heat/shade only; air_noise + expressway noise split out as siblings (audit §2d) |
| 20 | `flood` | 0.01 | MEASURED | Flood-prone routes / PUB drainage risk overlay |

#### New component specs (v2.0)

**`air_quality` (PARTLY_MEASURED, w=0.03):** Scored from NEA PSI/PM2.5 long-run climatology per
planning area, penalised further for expressway road-buffer proximity (PM2.5 hotspot proxy). Marked
PARTLY_MEASURED because the climatology layer is a stub until live NEA API fetch is wired; the
road-buffer sub-component is MEASURED from the expressway layer already in the pipeline.

**`jtc_industrial` (MEASURED, w=0.02):** Inverse-distance score to JTC-designated heavy-industrial
zones (Jurong Island, Tuas, Senoko, Kranji). Closer proximity → lower score. Fully computable from
the public JTC zone polygons; marked MEASURED.

**`stewardship` (PARTLY_MEASURED, w=0.03):** MND Town Council Management Report (TCMR) KPI bands
mapped to a 1–5 scale (GREEN→5, AMBER→3, RED→1). Captures observable estate upkeep quality:
cleanliness, lighting, lift reliability, estate maintenance responsiveness. **This is explicitly NOT
social mix** — it measures observable physical upkeep, not resident demographics. PARTLY_MEASURED
because TCMR publication cadence is annual and band changes lag reality by up to 12 months.

**`hawker` (PARTLY_MEASURED, w=0.04):** The canonical pipeline uses `data/hawker_v2.csv`, generated
from NEA hawker-centre points plus embedded stall-count overrides. It measures access, capacity and
redundancy, not cultural fame; older `judged_inputs.csv` hawker values are fallback-only.

**DEFERRED — `ev_charging` (stub, NOT in live model):** EV charging infrastructure density was
identified as a future component but is deferred pending LTA token / data access. Weight is not
allocated; it does not appear in PROVISION_WEIGHTS. Do not include it in scoring runs.

#### `W_PRIVATE` — private (condo) segment weight variant (20 components, sum = 1.000)

Applied by `value_model.py` when scoring private transactions. Rationale: private buyers have
higher car ownership (conn ↓), use in-development amenities (green ↓, sport ↓), prioritise
school postal codes as a direct pricing driver (sch ↑), and skew younger/wealthier (eldercare ↓).
Sourced verbatim from `models/framework_config.py:PROVISION_WEIGHTS_PRIVATE`.

| Key | W (HDB) | W_PRIVATE | Delta | Rationale |
|-----|--------:|----------:|------:|-----------|
| `conn` | 0.14 | 0.11 | −0.03 | Car ownership higher; parking within development |
| `amen` | 0.09 | 0.12 | +0.03 | F&B cluster / mall access > hawker |
| `green` | 0.08 | 0.07 | −0.01 | Landscaped grounds within development reduce urgency |
| `dens` | 0.08 | 0.08 | 0 | — |
| `sch` | 0.07 | 0.11 | +0.04 | School postal code is a direct pricing driver |
| `childcare` | 0.05 | 0.05 | 0 | — |
| `hlth` | 0.04 | 0.04 | 0 | — |
| `mom` | 0.04 | 0.04 | 0 | — |
| `hawker` | 0.04 | 0.02 | −0.02 | Restaurant / delivery preference |
| `noise` | 0.03 | 0.04 | +0.01 | — |
| `air_noise` | 0.03 | 0.03 | 0 | — |
| `eldercare` | 0.03 | 0.02 | −0.01 | Private buyer cohort skews younger/wealthier |
| `stewardship` | 0.03 | 0.02 | −0.01 | — |
| `air_quality` | 0.03 | 0.03 | 0 | — |
| `community` | 0.02 | 0.03 | +0.01 | — |
| `sport` | 0.02 | 0.01 | −0.01 | Gym/pool within development |
| `jtc_industrial` | 0.02 | 0.02 | 0 | — |
| `infra` | 0.14 | 0.13 | −0.01 | — |
| `env` | 0.01 | 0.02 | +0.01 | — |
| `flood` | 0.01 | 0.01 | 0 | — |

### 1.2 S11 — conditional car-mobility (provision side)
For `car-primary` nodes only. Scores expressway access + multi-district drive time + congestion/
construction friction + parking + (dual-signed) industrial proximity. When active, transit S1 is
HALVED (not zeroed). Carries the **mandatory cost-of-car-dependence drag** so it cannot reward
car-affluence as provision. (Rationale in Appendix C — same laundering logic as the social-mix
exclusion.)

---

## 2. Node-archetype flag (interpretive metadata — changes NO weights)

| Tag | Archetype | Examples |
|-----|-----------|----------|
| A | Regional town centre | Tampines Central |
| B | Mature HDB town-centre node | Queenstown/Dawson, Bukit Panjang, Pasir Ris Central |
| C | Coastal / park-adjacent node | Marine Parade |
| D | Private / mixed-use lifestyle enclave | Holland Village, Bukit Timah belt |
| E | New-town early precinct | Tengah; Canberra = B/E hybrid |

**Rule:** never compare raw Provision across archetypes without stating tags. "Tampines (A) vs
Holland Village (D)" is a category comparison — more *provisioned*, not more *liveable*.
Cross-archetype "which is better to live in" is answered ONLY by Document 2.

---

## 3. D multiplier — losses/disruptions ONLY
```
D = max(0.70, 1 − Σ(severity × certainty × time_factor))
```
Severity: moderate 0.10 / major 0.20 / structural 0.30. Certainty: confirmed 1.00 / gazetted 0.75
/ under-study 0.40 / rumour 0.00. Time: 0–2y 1.00 / 2–5y 0.75 / 5–10y 0.40 / >10y 0.20.
**Positive additions do NOT go here** (they live in S7 / Document 2's Future horizon) — this
removes the v0.2–0.4 double-count.

---

## 4. Selective veto C(a) (present-day dealbreakers)
S1=1 AND S8≤2 → cap C · S2=1 → cap C · two+ of {S1,S2,S6,S8}=1 → cap D · (S6=1, S4=1 handled per
persona in Doc 2). S3/S5/S7/S9=1 → no cap.

---

## 5. Provision pilot scores (8 estates — illustrative, analyst judgement, NOT GIS)

> **Note:** §5 numbers predate the 20-component re-weight; regenerate from `data/provision_scores.csv` after a full pipeline run with the v2.0 weights.

| Estate | Archetype | Provision band | (pilot decimal — noise ±0.3) |
|--------|:--:|:--:|:--:|
| Queenstown | B | B+ | 4.20 |
| Pasir Ris | B→A | B+ | 4.04 |
| Woodleigh | B | B+ | 4.03 |
| Tampines | A | B+ | 4.00 |
| Holland Village | D | B | 3.95 |
| Marine Parade | C | B | 3.86 |
| Canberra | B/E | C | 3.44 |
| Tengah | E | D | 2.96 |

Six of eight inside a 0.34 spread — *inside the ±0.3 cross-grader noise.* This is the
**provision-saturation** effect: most established SG estates have crossed the provision
threshold, so provision stops discriminating among them. Provision's discriminating power is
greatest for NEW/transitional towns (Tengah, Canberra), weakest for the mature cluster.

---

## 6. Reporting rule — BANDS, not decimals
Provision is reported as a band until computed on real GIS data (clinic/ school/ network-walk
joins). The decimal is shown only with its ±band-width. 4.04 vs 4.00 is **not** a real
distinction. Precision is the goal, not yet delivered.

---

## 7. THE PROVISION–LIVEABILITY GAP (the cross-reference that makes the split worth it)
```
Gap(a, persona, horizon) = Liveability_cell(Doc2) − Provision_band(Doc1)
```
- **Large NEGATIVE gap** (Provision high, Liveability low) → "well-equipped but poor fit /
  overpriced / characterless for this person." A warning the provision is wasted on them.
- **Large POSITIVE gap** (Provision low, Liveability high) → "punches above its provision."
  **This is the Holland Village signal**: under-equipped on the checklist, but highly liveable
  for the lifestyle-seeker. The gap is the single most informative output — it is what
  "the two frameworks challenge each other" actually means, made concrete.

---

## Appendix C — provision-side standing notes
- **Component 10 / social-mix:** permanently excluded as a SCORED component. A "social mix" score
  launders class/income sorting under a neutral label. Stewardship (upkeep, lighting, neglect) is
  the only acceptable future filler, and only after observable measurement.
- **Care-network proximity:** excluded from Provision. It is real and decision-critical, but it
  depends on private user-supplied anchors (parents, adult children, caregivers, co-parents), so it
  belongs in Document 2 as a Liveability overlay.
- **Car-mobility drag:** without it, S11 rewards car-affluence as provision — same laundering trap.
- **Verified anchors (re-verify; decay):** mature/non-mature retired → Standard/Plus/Prime (Oct
  2024 BTO). CCL6 passenger service 12 Jul 2026. TEL4 (Marine Parade) operational 23 Jun 2024.
  JRL Stage 1 ~mid-2028. Tampines has TWO polyclinics (Tampines 1990, Tampines North Sep 2023).
  Canberra MRT opened 2019 (NS12 reserved decades; deliberately delayed). Woodleigh station built
  2003, opened 2011 (held shut for lack of development).
- Full v0.1–v0.8 decision log lives in **Document 2's Appendix A** (shared history).

---

# v0.9 ADDENDUM (Provision side)

## P9.1 Rank-or-Profile gate (the "both" rule, made non-optional)
Provision produces a RANKING **only** when ALL three hold; otherwise it produces a PROFILE only:
1. estates differ by **> ±0.3** (the cross-grader noise floor) on Provision band, AND
2. they share the **same archetype**, AND
3. they share the **same horizon**.
Default is **PROFILE**. Ranking is the rare exception, not the headline. This operationalises the
finding (three independent reviews + own run) that one score cannot answer "which is most liveable"
for the broadly-liveable mature cluster. Example: Tengah(D) vs Bishan(B+) → rankable. The six-way
B+ cluster → profile-only (within noise). Anything vs JLD → profile-only (no shared construct).

## P9.2 Estate Fill Ratio — now a WEIGHTED component for TRANSITIONAL estates only
Replaces the v0.4 unweighted diagnostic. Active ONLY while an estate is filling in; dormant once
settled (weight redistributes to the v0.9 vector when inactive).
```
FillRatio score (1–5) = f(occupied blocks, open retail, operational feeder buses,
                          operational civic/health nodes, inverse construction intensity)
```
Weight when active: ~0.10, drawn proportionally from S2/S5/S9 (which previously absorbed
desolation). **Rejected the reviewer's whole-grade multiplier** — a 0.90× factor strips more
absolute points from high-provision estates than low ones (same asymmetry we rejected for D). A
weighted component penalises the lived gap without that distortion. Applies now to: Tengah; parts
of Woodleigh/Bidadari and Pasir Ris during works; future JLD residential precincts.

## P9.3 Expanded archetypes (A–G) + non-residential gate
| Tag | Archetype | Examples |
|-----|-----------|----------|
| A | Regional town centre | Tampines, Woodlands(+gateway), Jurong East core |
| B | Central mature HDB town | Bishan, Toa Payoh |
| C | Coastal/recreational mature town | Pasir Ris |
| D | Private/mixed-use lifestyle enclave | Holland Village |
| E | New integrated central-edge estate | Woodleigh/Bidadari |
| F | Modest infill MRT node | Canberra |
| G | Early-stage new town | Tengah |
| **X** | **Strategic business/activity district — NOT a residential estate** | **Jurong Lake District** |
**X-tag rule:** an X-district is NOT scored on residential provision and NEVER ranked against A–G.
It exits the Provision pipeline with an explicit "N/R — out of residential construct" label. JLD's
last-turn 3.58 was the bug this gate fixes.

## P9.4 Job-node fit replaces single averaged commute (S1 becomes anchor-relative)
Connectivity (S1) is no longer one CBD-centric number. It is computed against the household's
JOB ANCHOR. Same estate scores differently per anchor:
| Anchor | Strong-fit estates | Weak-fit estates |
|--------|--------------------|--------------------|
| CBD/central | Bishan, Toa Payoh, Woodleigh | Tengah, Pasir Ris, Woodlands |
| Changi/airport-east | Pasir Ris, Tampines | Bishan, Toa Payoh, Woodlands |
| West/NTU/JID/Tuas | Jurong Lake, Tengah | Pasir Ris, Woodleigh |
| Cross-border/north | Woodlands | Pasir Ris, Toa Payoh |
A universal multi-node score averages away the actual reason someone picks an estate. S1 therefore
moves toward Document 2 (it is persona/anchor-relative); Provision keeps only the
anchor-blind network-quality residue.
