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
Provision(a) = Σ (wᵢ × Sᵢ)        i = 1..9,  Sᵢ ∈ [1,5]
ProvisionFinal(a) = Provision(a) × D(a)      [D = losses/disruptions only; see §4]
```
Output range 1.0–5.0, reported as a BAND (A/B+/B/C/D/F), not a bare decimal (see §6).
**Archetype-BLIND**: every estate scored on the same yardstick so scores stay comparable.

### 1.1 Components and weights (v2.0: 21 components, sum = 1.000)

v2.0 changes (audit response to `factor_audit_reports/2026-06-19.md`):
- **Component 10 unreserved:** `stewardship` populated (PARTLY_MEASURED — MND TCMR KPI bands).
  Not social mix — observable upkeep proxies (lift breakdowns, arrears, cleanliness).
- **New components:** `air_quality` (NEA PSI annual mean), `jtc_industrial` (heavy-industry
  setback), `ev_charging` (LTA station registry density), `hawker` carved from S2 (NEA hawker
  stalls per 1k pop), `noise` carved from S9 (expressway buffer).
- **Provenance:** 20 MEASURED + 1 PARTLY_MEASURED. The four legacy JUDGED inputs
  (dens/env/mom/hawker) all promoted to MEASURED via dedicated ingester CSVs.
- **D-multiplier extension:** construction-disruption now sourced from `bca_permits.csv`
  (`d_construction = max(0.95, 1 − 0.05 × severity/1000)`), routed through D not as a new
  component (G2: D is losses-only).

| # | Component | Code | Weight | Scored on |
|---|-----------|------|------:|-----------|
| 1 | Connectivity | `conn` | 0.14 | Walk-time to rail, bus routes 800m, **pedestrian shelter %, dedicated cycling-path metres** (v2.0 sub-metrics, weighted blend) |
| 2 | Daily amenities | `amen` | 0.09 | Markets / supermarkets / clinics density |
| 2b | Hawker centres | `hawker` | 0.04 | NEA stalls per 1k residents in 800m (was JUDGED in v1.x) |
| 2c | Community facilities | `community` | 0.02 | CCs, libraries |
| 3 | Green | `green` | 0.08 | Park network-walk + **blue-infrastructure bonus** (sea/reservoir/waterway 800m) |
| 3b | Sport | `sport` | 0.02 | Sports halls / pools |
| 4 | Schools | `sch` | 0.07 | MOE P1 distance bands |
| 4b | Childcare | `childcare` | 0.05 | ECDA-licensed centres |
| 5 | Density & built form | `dens` | 0.08 | **HDB dwellings/ha (block-resolution)** + URA GPR (was PARTLY in v1.x) |
| 6a | Healthcare | `hlth` | 0.04 | CHAS GP + polyclinic distance |
| 6b | Eldercare | `eldercare` | 0.03 | AIC/MOH day-centres + nursing homes |
| 7 | Momentum (+) | `mom` | 0.04 | Confirmed additions (HDB NRP/LUP + **URA REALIS private launches + en-bloc**, v2.0) |
| 8 | Infrastructure readiness | `infra` | 0.13 | MRT operational; trunk utilities |
| 9a | Environmental comfort | `env` | 0.01 | **UHI temp anomaly + tree-canopy %** (v2.0 — was JUDGED) |
| 9b | Flood-prone routes | `flood` | 0.01 | Flood-risk overlay |
| 9c | Expressway noise | `noise` | 0.03 | Expressway 200m buffer (split from S9 in v2.0) |
| 9d | Air-corridor noise | `air_noise` | 0.03 | Changi / Seletar / Paya Lebar approach corridors |
| 9e | Air quality | `air_quality` | 0.03 | **PM2.5 annual mean (NEA PSI)** + road-buffer correction |
| 9f | Industrial proximity | `jtc_industrial` | 0.02 | **Heavy-industry setback distance** (B2/B3 stricter than B1) |
|10 | Stewardship | `stewardship` | 0.03 | **MND TCMR KPI bands** (arrears, lift, cleanliness, maintenance) + OneService close-rate. NOT "social mix" — observable upkeep only. |
|11 | EV charging | `ev_charging` | 0.01 | **LTA charger density + HDB carpark coverage %** |

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
D = max(0.70, 1 − Σ(severity × certainty × time_factor))           # framework formula (general)
d_construction = max(0.95, 1 − 0.05 × severity_score/1000)          # v2.0 explicit construction sub-channel
```
Severity: moderate 0.10 / major 0.20 / structural 0.30. Certainty: confirmed 1.00 / gazetted 0.75
/ under-study 0.40 / rumour 0.00. Time: 0–2y 1.00 / 2–5y 0.75 / 5–10y 0.40 / >10y 0.20.

**v2.0 construction-disruption channel:** active BCA-permitted construction sites within 500m,
severity = `GFA(kSF) × remaining_months / setback_m` (sourced from
`data/bca_permits.csv` via `ingest_bca_permits.py`, with pipeline-fallback while the official BCA
Permit Search API remains gated). Penalty caps at 5% per the framework's "D never dominates"
principle. JURONG EAST / SEMBAWANG / CLEMENTI presently absorb the heaviest hit.

**Positive additions do NOT go here** (they live in S7 / Document 2's Future horizon) — this
removes the v0.2–0.4 double-count.

---

## 4. Selective veto C(a) (present-day dealbreakers)
S1=1 AND S8≤2 → cap C · S2=1 → cap C · two+ of {S1,S2,S6,S8}=1 → cap D · (S6=1, S4=1 handled per
persona in Doc 2). S3/S5/S7/S9=1 → no cap.

---

## 5. Provision scores (v2.0 — 32 estates, real-data pipeline)

Top / mid / bottom of the v2.0 distribution; full ranking in `data/provision_scores.csv`.
"Pilot decimal" replaced by the actual model output (post-D-multiplier).

| Estate | Archetype | Provision band | Decimal |
|--------|:--:|:--:|:--:|
| Central Area | A (urban core) | A | 4.56 |
| Toa Payoh | B | B+ | 4.42 |
| Bedok | A | B+ | 4.38 |
| Bukit Merah | B+ | B+ | 4.23 |
| Yishun | B | B+ | 4.13 |
| Bukit Timah | D | B | 3.97 |
| Ang Mo Kio | B | B | 3.96 |
| Marine Parade | C | C | 3.13 |
| Woodlands | B | C | 3.29 |
| **Tengah** | **E** | **F** | **2.45** |

**TENGAH at F is a legitimate v2.0 outcome, not a bug.** As an early new-town precinct with most
infrastructure still pipeline-only, it scores 1-3 on connectivity, amenities, hawker (no centres
built yet), childcare, community, infra, and stewardship. The momentum (mom=5) and flood (3) +
eldercare (5) components keep it above 2.0, but the present-day provision is genuinely thin.
Its T5/T15 trajectory in Document 2 tells the *different* story (forward momentum is highest
in SG). This is exactly the split the two-document architecture was built to express — a low
Provision-now estate can still have high Liveability-future for the right life-path.

Most established estates cluster in B / B+ (provision-saturation effect). Discriminating power
is greatest for new / transitional towns (Tengah F, Marine Parade C) and the highest-end
(Central A); weakest for the mature cluster (~3.6–4.2 band).

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
