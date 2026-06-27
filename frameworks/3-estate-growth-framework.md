# 3 — Estate Growth & Liveability Framework (v0.3)

> **Purpose:** Grade the liveability of Singapore residential estates for people deciding where to live — not for investment ranking, not for planning analytics.
> **Status:** Framework locked. Data slots marked `[TBD]`.

---

## 1. Geographic Units

| Layer | Unit | Used for |
|---|---|---|
| Public-facing output | HDB town / estate (27) | Rankings, comparisons |
| Analytical layer | URA subzone / block catchment | Per-precinct scoring, dispersion |
| Private supplement | URA planning area / project cluster | Private-housing value layer |

**Why two layers:** A person does not live in "Sembawang planning area" abstractly. They live near Canberra MRT, or Admiralty Road West, or Sun Plaza. Whole-town scores averaged without a dispersion indicator mislead for large, internally varied towns (Bedok, Jurong West, Sembawang, Woodlands, Yishun).

**N/R (Not Rated) exclusions:** Planning areas with no meaningful residential population are excluded from all output tables and labelled `N/R — not a residential estate`. They do not receive an F grade.

Excluded: Changi Airport zone, Western Water Catchment, Tuas industrial corridor, port zones, military/utility reserves, reservoir catchments.

**Central Area:** Treated as special-case. Score at precinct level (Tanjong Pagar, Chinatown, Rochor, Bugis, Marina Bay fringe) not as a unified estate.

---

## 2. Framework Equation

### 2.1 Core Liveability

```
Core(a) = Σ (wᵢ × Sᵢ)    for components i = 1..9
```

- `Sᵢ` = component score, 1.0–5.0
- `wᵢ` = component weight (sum to 1.0)
- Cost is excluded from Core

### 2.2 Final Liveability

```
Final(a) = Core(a) × D(a) × C(a)
```

- `D(a)` = time-discounted negative trajectory multiplier (§4)
- `C(a)` = selective veto / cap function (§5)

### 2.3 Value Score

```
Value(a) = Final(a) × exp(−price_residual(a))
```

Cost is kept entirely separate from liveability. The Value score answers "how much liveability per dollar?" — Core answers "how good is it to live here?" These must never be merged into a single number.

See `2-liveability-matrix.md` and `value_model.py` for the price-residual regression methodology. HDB and private housing are separate value segments — never blended.

### 2.4 Persona Scores

Three persona lenses applied as weight overrides on Core:

| Persona | Key weight shifts |
|---|---|
| Young family | S4 Schools ↑, S6 Healthcare ↑, S2 Amenities (basics) ↑ |
| Single professional | S1 Connectivity ↑, S7 Momentum ↑, S3 Green ↓ |
| Retiree | S6 Healthcare ↑↑, S3 Green ↑, S1 Connectivity (accessibility) ↑, S9 Infra readiness stability ↑ |

Persona scores are non-comparable across personas by design. Do not rank Ang Mo Kio (retiree) against Punggol (young family).

---

## 3. Component Scores

### Weights (Core — cost excluded, normalised to 100%)

| # | Component | Weight | Type |
|---|---|---|---|
| S1 | Connectivity | 18.3% | Measured |
| S2 | Daily amenities | 17.2% | Measured |
| S3 | Green & blue space | 11.8% | Measured |
| S4 | Schools | 11.8% | Measured |
| S5 | Density & built form | 9.7% | Measured |
| S6 | Healthcare | 8.6% | Measured |
| S7 | Momentum (positive pipeline) | 6.5% | Judged + time-discounted |
| S8 | Infrastructure readiness | 16.1% | Measured + judged |
| | **Total** | **100%** | |

> **S8 is the renamed and expanded version of the former S9 (Infrastructure readiness).** It absorbs what was previously included under Connectivity as a separate readiness/sequencing dimension.

---

### S1 — Connectivity (18.3%)

Measures practical door-to-door mobility using a network-based model, not straight-line distances.

| Sub-metric | Notes |
|---|---|
| Walk time to nearest MRT / bus interchange | Network walk, not Euclidean |
| Feeder bus frequency (peak / off-peak) | Critical for large towns with MRT at periphery |
| Transfer penalty | LRT → MRT and bus → MRT friction counted |
| Commute to multiple job nodes | CBD + Jurong Lake District + one-north at minimum |
| First/last-mile shelter | Covered walkways; Singapore heat and rain context |
| Line redundancy | Interchange estate > single-line-dependent estate |

**Score guide:**
- 5: Multiple lines / interchange, <10 min walk, high-frequency feeders, sheltered routes
- 4: Single MRT line, <15 min walk, adequate feeders
- 3: MRT accessible but transfer required (LRT) or walk >15 min
- 2: Bus-dependent; MRT >20 min or requires 1+ transfer
- 1: No practical public transport spine; car-dependent

---

### S2 — Daily Amenities (17.2%)

Separated into tiers to prevent lifestyle retail masking absence of basic services.

| Tier | Examples | Weight within S2 |
|---|---|---|
| Basic food | Hawker centre, kopitiam, wet market | High |
| Groceries | Supermarket, minimart, market | High |
| Public services | Library, community club, post office, service centre | Medium |
| Healthcare-lite | GP, CHAS clinic, dental, pharmacy | Medium |
| Retail / lifestyle | Mall, gym, café, enrichment | Low |

A private mall-heavy estate without a hawker centre does not score the same as a self-sufficient HDB estate with affordable daily services.

---

### S3 — Green & Blue Space (11.8%)

Measures usable green access, not merely mapped park presence.

| Sub-metric | Notes |
|---|---|
| 400m / 800m network-walk to park | Practical daily use |
| Shade along walking route | Singapore-specific; canopy over path, not just park area |
| Park size and facilities | Pocket park ≠ regional park |
| Park Connector Network continuity | Cycling / jogging loop usefulness |
| Blue-space access | Reservoir, canal, coastal frontage |
| Biodiversity / nature reserve adjacency | Quality signal beyond area |

**Environmental comfort sub-metrics (folded into S3):**
- Tree canopy density along key pedestrian corridors
- Sheltered walkways to MRT / bus / amenity nodes
- Flood-prone or ponding-prone routes (negative)

---

### S4 — Schools (11.8%)

Measures practical school access. Brand-name presence is not a liveability metric.

| Sub-metric | Notes |
|---|---|
| Primary schools within 1km | MOE P1 registration priority zone |
| Primary schools within 2km | Secondary priority zone |
| Historical balloting pressure | Proxy for actual demand vs supply |
| Preschool / infant care / student care | Often the first bottleneck for young families |
| Secondary school access | Distance + range of offerings |
| JC / polytechnic access | Public transport reachable, not walking distance |
| Special education / support access | SPED schools, inclusion support |

---

### S5 — Density & Built Form (9.7%)

High density is not inherently bad. Good density enables amenities and transit. Score the lived experience.

| Sub-metric | Notes |
|---|---|
| Residential floor-area intensity | More precise than population/km² |
| Block spacing / sky-view factor | Perceived openness |
| Lift and vertical access design | Elderly and family usability |
| Pavement width / cycling conflict points | Daily comfort |
| Mixed-use convenience ratio | Density that enables amenities scores higher |
| Active construction intensity (negative) | New towns and renewal zones carry temporary friction |

**Environmental comfort sub-metrics (folded into S5):**
- Urban heat island exposure / lack of shade
- Road / rail / flight path / construction noise
- Expressway or viaduct proximity (negative)

---

### S6 — Healthcare (8.6%)

Does not overweight hospitals. Most residents' daily healthcare experience is primary care.

| Layer | Metric |
|---|---|
| Everyday care | GP density, CHAS clinic count, pharmacy access |
| Subsidised care | Polyclinic within 15-min public transport |
| Elderly care | Active Ageing Centre, day rehabilitation, nursing home proximity |
| Urgent care | A&E / acute hospital travel time |
| Capacity proxy | Population per polyclinic catchment |

**Persona override:** For retiree persona, S6 weight escalates significantly. Hospital and A&E access matters more. Nursing home proximity is a positive, not a negative signal.

---

### S7 — Momentum (6.5%)

Captures positive future pipeline. Applies the same time-discount logic as D (§4) but in the positive direction. A station opening next month is not equivalent to a line planned for 2032.

```
S7 = f( Σ significance_i × certainty_i × time_factor_i )
     normalised to 1–5
```

| Positive event | Significance |
|---|---|
| New MRT station operational | High |
| New town centre / integrated hub | High |
| New polyclinic / hospital | High |
| New school / JC opening | Medium |
| Park / PCN extension | Medium |
| Commercial / mall opening | Low |

**Certainty and time-factor values:** Same table as D multiplier (§4.2).

**Current pipeline examples (as at June 2026):**

| Project | Status | Time factor |
|---|---|---|
| CCL6 (Keppel, Cantonment, Prince Edward Rd) | Passenger service 12 Jul 2026 | 1.00 |
| JRL Stage 1 (Jurong / Tengah) | ~mid-2028 | 0.75 |
| CRL Phase 1 (Ang Mo Kio to Jurong Lake District) | ~2030 | 0.40 |
| CRL Punggol Extension | ~2032 | 0.20 |

Momentum is never a veto component. A high S7 does not compensate for a failing S8 (Infrastructure readiness). S7 scores the future; S8 scores what residents experience today.

---

### S8 — Infrastructure Readiness (16.1%)

Second-highest weight. Captures the transport-housing sequencing question: **was infrastructure ready for residents, or did residents wait for infrastructure?**

This is distinct from S1 (Connectivity), which measures current mobility quality. S8 measures the structural readiness of the estate's transport spine relative to its residential density.

**Scoring rubric:**

| Score | Condition | Example |
|---|---|---|
| 5 | MRT operational before or concurrent with meaningful housing density (>10k units). Integrated transport spine from move-in. | Punggol (NEL opened 2003; town developed around it) |
| 4 | MRT operational, lag of 1–3 years after density threshold | — |
| 3 | Corridor reserved / gazetted; stop withheld pending demand. Now operational. Historical lag resolved. | Canberra (NS12 reserved 1996, station opened 2019) |
| 2 | Dense estate, bus-dependent, MRT confirmed but >3 years away | Tengah (JRL ~2028) |
| 1 | Dense estate, no operational rail, no near-term confirmed opening | — |

**Modal integration penalty:** Mixed-tenure estates (HDB + condo + landed) with no MRT spine are penalised more than single-tenure estates, because the diversity of residents creates higher mobility demand that buses alone cannot satisfy.

**Current vs historical:** Score reflects **current operational state**, not historical grievance. Canberra scores 3 today (historical lag resolved) — not 1 (historical maximum lag). The D multiplier handles any current degradation.

---

## 4. D — Negative Trajectory Multiplier

Captures confirmed future losses. Applied as a whole-grade multiplier that drags Final(a) down regardless of which component the loss affects.

**Rationale:** A well-provisioned estate losing a polyclinic is a betrayal of expectations baked into its price. A whole-grade multiplier reflects that residents — who paid for that standard — bear the full liveability cost. *(Known limitation: this penalises high-scoring estates harder in absolute terms. See §7.1.)*

### 4.1 Formula

```
D(a) = max(0.70, 1 − Σ (severity_i × certainty_i × time_factor_i))
```

Floor of 0.70 is a hard floor, consistent with `provision_model.py`. When multiple confirmed major losses compound, the Σ term can exceed 0.30 — the floor prevents runaway decay but means a third and fourth concurrent confirmed loss add zero incremental penalty. This is intentional: the floor represents the practical minimum liveability of an estate still functioning as a residential area.

### 4.2 Parameters

**Severity:**

| Loss type | Severity |
|---|---|
| Moderate: school closure, amenity downgrade, facility consolidation | 0.10 |
| Major: polyclinic closure, hospital/A&E removal, major trunk-bus reduction | 0.20 |
| Structural: multiple major losses, or removal of core transport spine | 0.30 |

**Certainty:**

| Status | Certainty multiplier |
|---|---|
| Operationally confirmed / contracted / formal agency announcement | 1.00 |
| Gazetted or officially planned, not yet contracted | 0.75 |
| Under study / indicative only | 0.40 |
| Speculation / market rumour | 0.00 |

**Time factor:**

| Loss timing | Time factor |
|---|---|
| 0–2 years | 1.00 |
| >2–5 years | 0.75 |
| >5–10 years | 0.40 |
| >10 years | 0.20 |

### 4.3 Positive pipeline: same logic, opposite direction

The same time-discounting applies to S7 (Momentum). A station opening in one month is not equivalent to a line confirmed for 2032. The time_factor table above applies to both losses (D) and gains (S7).

---

## 5. C — Selective Veto / Cap Function

A blanket veto (any S = 1 caps the grade) is too crude because some components are persona-dependent. A score of 1 for schools is not a dealbreaker for a single professional. A score of 1 for momentum is not a present liveability failure.

### 5.1 Veto table

| Trigger | Grade cap applied |
|---|---|
| S1 Connectivity = 1 **AND** S8 Infra readiness ≤ 2 | Universal ≤ C |
| S2 Daily amenities = 1 | Universal ≤ C |
| S6 Healthcare = 1 | Retiree ≤ C; Universal ≤ B |
| S4 Schools = 1 | Young-family persona ≤ C only |
| ≥ 2 of {S1, S2, S6, S8} = 1 simultaneously | Universal ≤ D |
| S3, S5, S7 = 1 | No automatic cap |

### 5.2 Conflict resolution

If multiple rules trigger simultaneously, the more restrictive cap applies.

**Example:** S1 = 1 AND S8 = 1 triggers both the first rule (cap at C) and the fifth rule (two of {S1, S8} equal 1 → cap at D). D cap wins.

### 5.3 Soft floor

To prevent mathematical collapse from compounding D and C interactions:

```
Final(a) ≥ 1.5   (hard floor, regardless of multipliers)
```

An estate still functioning as a residential area cannot score below 1.5. This is not a veto override — it is a mathematical sanity bound.

---

## 6. Output Format

### 6.1 National table (all HDB towns)

Scale: 1.0–5.0, half-point allowance. Band labels:

| Score | Band |
|---|---|
| 4.5–5.0 | A |
| 4.0–4.4 | B+ |
| 3.5–3.9 | B |
| 3.0–3.4 | C |
| 2.5–2.9 | D |
| 1.0–2.4 | F |

Published outputs per estate:
1. **Core Liveability** — "How good is it to live here?"
2. **Value** — "How much liveability per dollar?"
3. **Persona scores** — Family / Single professional / Retiree (non-comparable across personas)

### 6.2 Shortlist / subzone comparison

Scale: 1.0–10.0 or decimal, at URA subzone or block-catchment level. Used when comparing 2–4 specific estates or precincts within the same town (e.g. Canberra vs Yishun Ring vs Sembawang Central).

Do not mix resolutions. A 1–5 national score and a 1–10 subzone score for the same estate are different products.

---

## 7. Known Limitations and Open Issues

### 7.1 Whole-grade D multiplier asymmetry

A confirmed polyclinic closure with D = 0.9 removes:
- 0.46 points from an A-grade estate (4.6 → 4.14)
- 0.20 points from an F-grade estate (2.0 → 1.80)

The same event costs a strong estate more than twice as much in absolute terms. The counter-argument is that residents of strong estates paid a premium for that standard, so the loss is a proportionally larger betrayal. This is defensible but declared — it should be made explicit in any public output.

**If this asymmetry becomes a problem:** Replace the whole-grade multiplier with a component-level penalty applied only to the affected component (e.g. D affects only S6 for a healthcare closure). This reduces blast radius but loses the systemic signal.

### 7.2 D floor behaviour with multiple losses

When ≥ 2 major confirmed near-term losses apply, Σ(severity × certainty × time_factor) > 0.30, and D floors at 0.70. Additional losses beyond the second add zero incremental penalty. This is the correct engineering choice (prevents collapse) but means the floor is doing significant work in multi-loss scenarios.

### 7.3 Subzone data availability

Scoring at subzone level requires geospatial layers at block-cluster resolution. Current pipeline has only CHAS clinic geodata at this resolution. MRT, bus, school, park layers are aggregated or pending. National HDB-town scores carry ±0.3 noise until layers are complete.

### 7.4 Private vs HDB value segments

HDB resale and private residential are scored separately. Value(a) for a mixed tenure planning area requires two separate value calculations — one per segment. Never blend HDB and private prices into a single affordability metric.

---

## 8. Estate-Level Framework Risks

Using the HDB public town/estate list as the resident-facing universe. These are not scores — they are warnings about where the framework may produce misleading results if applied without subzone decomposition.

| HDB town | Main framework risk |
|---|---|
| Ang Mo Kio | Town-centre, Mayflower, Kebun Baru, Cheng San, and Lentor-edge differ materially. Whole-town average conceals subzone variation. |
| Bedok | Very large. Bedok Central, Bedok Reservoir, Tanah Merah-side, and East Coast-side should not share one score without a dispersion indicator. |
| Bishan | Likely strong on centrality, schools, parks. Cost separation essential. Do not let prestige overstate universal liveability. |
| Bukit Batok | Connectivity differs sharply by east/west/north/Hillview-edge. Feeder-bus and walking gradients matter more than the town-level MRT label. |
| Bukit Merah | Extremely heterogeneous: Redhill, Tiong Bahru, Telok Blangah, Alexandra, Bukit Ho Swee, HarbourFront-edge are different liveability products. Whole-town score will mislead. |
| Bukit Panjang | LRT dependence requires transfer / reliability penalty. Raw MRT-proximity score overstates convenience. |
| Bukit Timah | Low density, greenery, schools score high. HDB relevance limited. Separate private-housing liveability from HDB-town scoring. |
| Central Area | Not a normal estate. Score at precinct level or mark special-case. |
| Choa Chu Kang | Large-town averaging hides differences between CCK Central, Yew Tee, Teck Whye, Keat Hong, CCK North. |
| Clementi | Strong connectivity and schools may mask old-stock issues, high prices, and subzone differences (Central, West Coast, Sunset Way, Dover). |
| Geylang | Boundary and externality problem. Aljunied, Eunos, Paya Lebar, MacPherson-edge, and Geylang proper differ in noise, traffic, amenity type, housing stock. |
| Hougang | Do not score only by NEL access. Off-line areas need bus-transfer modelling. CRL benefits must be time-discounted. |
| Jurong East | Regional-centre status inflates amenities and connectivity. Separate residents near Jurong East Central from industrial-edge areas. |
| Jurong West | Too large. Boon Lay, Pioneer, Nanyang, Lakeside, Jurong West Central have different transport, school, amenity realities. |
| Kallang / Whampoa | Centrality is high but noise, construction, older stock, and precinct fragmentation matter. Bendemeer, Boon Keng, Whampoa, Kallang riverside should be separated. |
| Marine Parade | New CCL operational access changes historical picture. Old lease profiles, coastal exposure, elderly needs should be explicit. |
| Pasir Ris | Green/blue access is a strength. Commute time and CRL uplift (~2030) must be time-discounted. |
| Punggol | Strong case for S8 readiness premium. Avoid over-rewarding planned-town status. Amenity capacity, crowding, construction, school demand must be checked. |
| Queenstown | Dawson, Commonwealth, Tanglin Halt, Alexandra, Mei Ling are distinct. Renewal trajectory and older-resident needs must be visible. |
| Sembawang | Must split Canberra, Sembawang Central, Admiralty-side, and north-coast areas. Canberra: S8 = 3 (historical lag resolved — NS12 reserved 1996, operational 2019). Score current operational reality, not historical grievance. |
| Sengkang | LRT / feeder dependence, young-family demand, school pressure, high-density new-town conditions need explicit treatment. |
| Serangoon | Serangoon Central / interchange differs from Serangoon North and landed enclaves. Schools and amenities should not be averaged blindly. |
| Tampines | Regional-centre strengths are real. Tampines North is a different liveability stage from Tampines Central. |
| Tengah | S8 = 2 currently (dense pipeline housing, JRL ~2028 confirmed but not operational). S7 should score JRL with time_factor = 0.75. Promised amenities discounted until operational. |
| Toa Payoh | Mature-town amenities strong. Older blocks, Bidadari differences, density, and ageing-population healthcare needs should be separated. |
| Woodlands | Regional-centre and cross-border gateway effects distort ordinary resident scoring. Score Woodlands Central, Admiralty, Marsiling, Woodlands North separately. |
| Yishun | Khatib, Yishun Central, Yishun East, Yishun Ring, and Canberra-adjacent pockets should not share one undifferentiated score. |

---

## 9. Relationship to Other Framework Documents

| Document | Role |
|---|---|
| `1-provision-framework.md` | Supply-side checklist: what is objectively present. Feeds S1–S8 component inputs. |
| `2-liveability-matrix.md` | Demand-side: 4 personas × 3 time horizons. This document (v0.3) replaces its scoring equation with the trajectory-adjusted model. |
| `3-estate-growth-framework.md` | **This document.** Trajectory-adjusted liveability grade with D multiplier, C veto, and Value separation. |
| `provision_model.py` | Implements provision scoring. Component scores here are computed from its geospatial outputs. |
| `value_model.py` | Implements Value = Provision × exp(−price_residual). Value(a) in §2.3 uses this directly. |

---

## Appendix A — Chronological Sequencing Principle

The order of infrastructure development relative to housing density is a scored liveability variable, not background context.

**The principle:** Estates where transport infrastructure was operational before or concurrent with residential density have structurally higher baseline liveability than estates where residents moved in first and waited for infrastructure.

**Why it matters for scoring:**
- A Punggol-pattern estate (spine first) never forced residents into car-dependence. That shapes estate culture, retail viability, and daily liveability permanently.
- A Canberra-pattern estate (corridor reserved, stop withheld for decades) imposed transport poverty on early residents and shaped the estate around car use until the station opened.
- The variable of interest is not the corridor or the gazettement — it is **years between meaningful residential density and first operational MRT stop**.

**What is not in scope:** The exact sequence of events before residents moved in (when a town was gazetted, when the first pile was driven) is not a liveability input. Residents do not experience history — they experience the current operational state plus the forward pipeline. S8 scores the current state; D and S7 score the trajectory.

---

*Framework version: v0.3 | Last updated: 2026-06-14 | Data to be populated from deep-research workflow output and pipeline runs.*
