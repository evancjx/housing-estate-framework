# Source catalog — pre-curated for the three sweeps

A starting catalogue so each audit doesn't re-discover the same sources. Add to this file as new sources prove themselves; do NOT remove proven ones without noting why.

**Trust convention.** Dataset IDs marked `[verify]` need a fresh check against the live catalogue before any ingester is wired up — IDs in this file are from the last audit and may have rotated. URLs and API endpoints are more stable than dataset IDs.

---

## Section A — International / academic neighborhood-quality frameworks (Sweep A)

Each entry: name + published indicator structure + what dimension it tests that this framework might miss.

### Liveability / quality-of-life indices

- **Mercer Quality of Living Index** — 39 factors across 10 categories: political environment, socio-cultural, economic, medical/health, schools/education, public services/transport, recreation, consumer goods, housing, natural environment. National-scope, but indicator list is a useful checklist.
- **EIU Global Liveability Index** — 30 indicators across stability, healthcare, culture/environment, education, infrastructure.
- **OECD How's Life / Better Life Index** — 11 dimensions (income, jobs, housing, health, education, community, civic engagement, environment, safety, work-life, life satisfaction). **OECD How's Life *regional* edition** has subnational granularity worth surveying.
- **CLC Singapore Liveability Framework** — Centre for Liveable Cities own SG-specific framework: "competitive economy, sustainable environment, high quality of life", organised around integrated planning + dynamic governance. PDFs on clc.gov.sg. Useful for SG-context calibration of weights even if not directly an indicator list.

### Deprivation / vulnerability indices (good for what NOT to copy verbatim — they encode policy values)

- **UK English Indices of Deprivation (IMD 2019)** — LSOA-level, 7 domains: income, employment, education, health, crime, barriers to housing & services, living environment. Many domains map cleanly to Singapore's "social mix" rejection — useful as a *negative reference* for what the framework excludes by principle.
- **Australian SEIFA / AURIN Liveability Index** — University-of-Melbourne-led; subdomains include walkability, public open space, food, transport, education, social infrastructure. The walkability sub-index is the cleanest external reference for upgrading SG's `conn`.
- **US CDC Social Vulnerability Index** — 16 variables across socio-economic, household composition, minority/language, housing/transport. Mostly Axiom-2 territory; included for awareness.
- **US EPA EJScreen** — 13 environmental indicators (PM2.5, ozone, diesel PM, air toxics, lead paint, Superfund proximity, RMP facility proximity, etc.). Good external reference for *air-quality and industrial-proximity* components.

### Place-quality / streetscape research

- **MIT Place Pulse** (Naik, Salesses et al.) — CV-on-Street-View scoring on six axes: safety, lively, beauty, wealth, depression, boring. Worth surveying but the "wealth" axis is the laundering trap.
- **Ewing & Handy urban-design qualities** — imageability, enclosure, human scale, transparency, complexity. Cleaner than Place Pulse because it scores design, not affluence.
- **WHO Healthy Cities Phase VII core indicators** — air quality, water, food security, green space access, active mobility, mental health support. Useful for *air quality* as a separate axis from noise.
- **15-minute city literature** (Moreno 2021; Weng et al. 2019 on Shanghai operationalisations) — operationalises access-to-six-functions as a single metric. The framework already does this fragmented across `conn`, `amen`, `green`, `sch`, `hlth`; a unified 15-min score might add discrimination.

### Sources to look up live each time (not pre-cached)

- Recent CLC publications (clc.gov.sg/research-publications)
- NUS LKYSPP / Centre on Asia and Globalisation papers on housing & neighbourhood quality
- MND research papers (mnd.gov.sg)

---

## Section B — Singapore open data sources (Sweep B)

Each entry: provider + dataset name + ID/endpoint + what it could feed + access caveat.

### Already ingested (DO NOT re-suggest)

`data.gov.sg`: NParks parks (`d_0542d48f0991541706b58059381a6eca`), NEA hawker centres (`d_4a086da0a5553be1d89383cd90d07ecd`), MOE schools (`d_688b934f82c1059ed0a6993d2a829089`), HDB resale prices, MOH polyclinics, ECDA childcare (`d_61eefab99958fd70e6aab17320a71f1c`), PA community clubs (`d_f706de1427279e61fe41e89e24d440fa`), SportSG sport centres (`d_9b87bab59d036a60fad2a91530e10773`), PUB flood-prone areas, MSF eldercare (current `eldercare.csv`). Plus OneMap-geocoded MRT, LTA bus stops/routes, CHAS clinics, URA private caveats, OSM expressways.

### NOT-yet-ingested — high value (run sweep B against this list FIRST)

| # | Provider | Dataset | Access | Could feed |
|---|---|---|---|---|
| B1 | NEA | Real-time air quality: `/v1/environment/psi`, `/v1/environment/pm25` | data.gov.sg REST, no key | NEW: air-quality exposure component |
| B2 | NEA | Dengue clusters (active GeoJSON) `d_dbfabf16158d1b0e1c420627c0819168` [verify] | data.gov.sg poll | NEW: vector-borne disease pressure |
| B3 | NEA | Hawker Centre v2 GeoJSON (`d_ccca3a7c2bbf5089e6789aab2120e198` [verify]) — adds stall counts & completion dates | data.gov.sg poll | Upgrades JUDGED `hawker` → MEASURED |
| B4 | URA | Master Plan 2019 Land Use Layer (LU_DESC + GPR) | data.gov.sg KML/SHP | Upgrades PARTLY_MEASURED `dens`; NEW: mixed-use share |
| B5 | URA | Master Plan Conservation Area Layer + Historic Sites | data.gov.sg SHP/KML | NEW: heritage/character |
| B6 | HDB | Upgrading Programme block-lists (HIP, NRP, LUP, EUP, HIP II) | data.gov.sg + HDB PDF | Upgrades JUDGED `mom` → MEASURED for HDB blocks |
| B7 | HDB | Property Information (`d_17f5382f26140b1fdae0ba2ef6239d2f` — block-level year/storey/dwelling-units) | data.gov.sg | Upgrades PARTLY_MEASURED `dens` → MEASURED |
| B8 | OneMap (NParks) | Theme `parkconnectorloop` — PCN polylines | OneMap themes, free token | Upgrades `green` PCN-continuity sub-metric |
| B9 | OneMap (SLA) | Theme `hdb_existing_building` [verify] — block polygons with storeys | OneMap themes | Real dwelling-units/ha (with B7) |
| B10 | OneMap (LTA) | Themes `walking_routes`, `cycling_path_network` — sheltered/covered linkways | OneMap themes | Upgrades `conn` first/last-mile shelter |
| B11 | OneMap (NLB) | Theme `libraries` | OneMap themes | Adds library sub-metric to `amen` |
| B12 | OneMap (MOE) | Theme `kindergartens` (MOE-run, separate from ECDA) | OneMap themes | Refines `childcare` / `sch` |
| B13 | OneMap (MOH) | Theme `moh_hospitals` (incl. A&E flag) | OneMap themes | Upgrades `hlth` A&E sub-metric |
| B14 | OneMap (SportSG) | Theme `sports_facilities` (ActiveSG fields, pools) | OneMap themes | Refines `sport` |
| B15 | OneMap (NHB) | Themes `historicsites`, `monuments` | OneMap themes | NEW: heritage/character |
| B16 | LTA DataMall | `BusServices`, `BusRoutes`, `PV/Bus`, `PV/Train` (passenger volumes), `CarParkAvailability`, `HDBCarparkInformation` (`d_23f946fa557947f93a8043bbef41dd09`) | DataMall, free `AccountKey` | Upgrades `conn` frequency sub-metric; NEW: carpark provision |
| B17 | SingStat | Resident population by subzone × age × dwelling type | data.gov.sg + SingStat Table Builder | Demographic denominator; informs but does NOT enter Provision (Axiom 2) |
| B18 | NParks | Heritage trees (open); full tree census (gated) | data.gov.sg | Shade/heat sub-metric for `env` |
| B19 | PUB | Drainage catchments, ABC Waters sites | PUB + data.gov.sg mix | Flood resilience refinement |
| B20 | CAAS | Flight track / noise-contour data around Changi, Seletar, Paya Lebar | CAAS (limited public), NEA noise zones | NEW: aircraft noise — distinct from `noise` (expressway) |
| B21 | BCA | Building permits / construction sites | BCA + data.gov.sg | NEW: construction-disruption horizon |
| B22 | NEA | Hygiene grading (Eating Establishment Search) | Scrape only; no clean dataset | Marginal refinement to `hawker`; licence-restricted |

### Sources to skip / flag

- Live LTA bus arrival API → demo-only, not scoring
- SLA cadastre parcels → licence not open
- CLC / ULI / Surbana / MND reports → narratives, not datasets — useful for *weight calibration*, not as ingest inputs

---

## Section C — Singapore home-buyer priority sources (Sweep C)

For Sweep C the agent surveys what real buyers say they prioritise — to find Provision-side gaps and to surface candidates that fail Axiom 1 (so they get routed to Liveability).

### Industry buyer-sentiment publications

- **PropertyGuru Consumer Sentiment Study (CSS)** — semiannual (H1 / H2). Top concerns + drivers per wave. propertyguru.com.sg
- **99.co Insider** — buyer guides, area-specific posts. 99.co/blog
- **Stacked Homes** — analytical buyer-focused content (stackedhomes.com). Strong on unit-level pick logic, useful for Axiom-4 (unit-level) reject-routing.
- **EdgeProp Singapore** — market commentary, regulatory analysis. edgeprop.sg
- **ERA / OrangeTee / Huttons / Knight Frank** — annual buyer surveys, periodic outlook reports.

### Policy / research surveys

- **IPS (Institute of Policy Studies, NUS LKYSPP)** — residential preferences, family-formation, ageing-in-place studies. lkyspp.nus.edu.sg/ips
- **CLC reports on neighbourhood quality** — clc.gov.sg
- **Our SG Conversation / OURS** outputs — government dialogue series.

### Discussion / qualitative

- **r/singapore** housing megathreads and "best estate for X" threads — for casual buyer language. Use as a *sentiment proxy*, not a survey. Tag findings clearly as qualitative.
- **HardwareZone EDMW property threads** — same caveat.

### Expected outputs from Sweep C

The agent classifies every buyer-cited factor as one of:

- **Provision-side gap** → goes into report §1 / §2 / §3
- **Liveability-side person-relationship** → goes into report §5
- **Value-side cost factor** → goes into report §5 (with note "handled by value_model.py")
- **Unit-level** → goes into report §5 (out of scope)
- **Axiom-2 status laundering** → goes into report §4 (principled rejection)

Sweep C's *primary* contribution is not novel factors — it's catching what the buyers care about that the framework currently doesn't explain, and surfacing class-laundering attempts in their natural buyer language so future audits recognise them faster.
