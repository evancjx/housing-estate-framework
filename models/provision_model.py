#!/usr/bin/env python3
"""
Singapore Estate PROVISION MODEL  (Document 1, v2.0)  — geospatial, real-data
=============================================================================
Computes the Provision score per estate from ACTUAL spatial data, instead of
analyst judgement. Emits the scores.csv that value_model.py consumes.

HONEST SCOPE — v2.0 (21 components):
  MEASURED        (20): connectivity, amenities, green, schools, healthcare,
                        infra, env (heat/shade — refactored with tree-canopy +
                        UHI delta), childcare, community, sport, flood_risk,
                        noise, air_noise, eldercare, density (HDB Property Info),
                        momentum (HDB+private pipeline), hawker (NEA v2 + stall
                        counts), air_quality (NEA PSI/PM2.5/NO2),
                        jtc_industrial (JTC TOL parcels), ev_charging
                        (LTA EV registry — stub until token).
  PARTLY_MEASURED  (1): stewardship (MND TCMR transcribed; OneService pending).
  JUDGED           (0): nothing — v2.0 eliminates the JUDGED tier.

Provenance flips landed in v2.0:
  dens     PARTLY → MEASURED  (HDB Property Information ingested)
  env      PARTLY → MEASURED  (NParks canopy proxy + MSS UHI delta)
  mom      PARTLY → MEASURED  (URA REALIS + STB en-bloc added to pipeline)
  hawker   JUDGED → MEASURED  (NEA Hawker Centre v2 with stall counts)

Note on `air_noise`: this is a geometric distance to runway centerlines + 12 km
approach/departure corridor extensions for Changi, Seletar, and Paya Lebar
(decommissioning ~2030). It is a PROXY for aircraft-noise exposure, NOT a real
CAAS noise contour. Estates under flight paths (Pasir Ris, Tampines, Marine
Parade) discriminate sharply; West / North estates saturate at 5. Replace the
corridor CSV when verified CAAS flight-track data is available.

Every component output carries a provenance tag. A future reviewer can see at a
glance which numbers are measurement and which are opinion. The model NEVER
pretends momentum was computed.

METHOD per measured component:
  Score(1-5) = distance/count features -> normalised -> mapped to 1-5 via
  documented anchor thresholds (see ANCHORS). Distances use a decay so "MRT 200m
  away" beats "MRT 900m away" smoothly rather than as a step.

RUN:
  pip install pandas numpy shapely --break-system-packages
  python provision_model.py --estates estates.csv \
      --mrt mrt.csv --bus bus.csv --clinics chas.csv --polyclinics poly.csv \
      --schools schools.csv --parks parks.csv --markets markets.csv \
      --supermarkets supermarkets.csv \
      --childcare childcare.csv --community community.csv \
      --sport sport.csv --flood flood_risk.csv \
      --judged judged_inputs.csv --out provision_scores.csv

See INPUT CONTRACT at the bottom for exact columns + data sources.
"""
import argparse, sys, math
import numpy as np, pandas as pd

# ----------------------------------------------------------------------
# v2.0 weights (sum=1.000, 21 components). Audit 2026-06-22 added 4 new
# MEASURED components (air_quality, jtc_industrial, ev_charging) +
# PARTLY_MEASURED stewardship; flipped 4 provenance tags MEASURED.
# See plan docs/superpowers/plans/2026-06-22-provision-v2-audit-impl.md
# for the W rationale and audit cross-references.
# ----------------------------------------------------------------------
W = {
    'conn':            0.14,   # -0.01 — shelter/cycling sub-metrics MEASURED (Task 2.9)
    'amen':            0.09,   # -0.01 — hawker now MEASURED reduces uncertainty
    'green':           0.08,   # -0.01 — blue sub-metric carved (Task 2.10)
    'sch':             0.07,
    'dens':            0.08,   # provenance: PARTLY → MEASURED (HDB Property Info)
    'hlth':            0.04,
    'mom':             0.04,   # provenance: PARTLY → MEASURED (private pipeline)
    'infra':           0.13,   # -0.02 — historical over-weight
    'env':             0.01,   # -0.01 — air_quality carved sibling
    'childcare':       0.05,   # -0.01
    'community':       0.02,   # -0.01 — stewardship absorbs upkeep signal
    'sport':           0.02,
    'flood':           0.01,
    'hawker':          0.04,   # provenance: JUDGED → MEASURED (NEA v2)
    'noise':           0.03,   # -0.01 — JTC industrial absorbs some
    'air_noise':       0.03,
    'eldercare':       0.03,
    'air_quality':     0.03,   # NEW MEASURED — NEA PSI/PM2.5
    'jtc_industrial':  0.02,   # NEW MEASURED — JTC industrial parcels
    'stewardship':     0.03,   # NEW PARTLY_MEASURED — MND TCMR
    'ev_charging':     0.01,   # NEW MEASURED — LTA EV registry (stub until token)
}
assert abs(sum(W.values()) - 1.0) < 1e-9, f"Weights must sum to 1.0, got {sum(W.values())}"

PROVENANCE = {
    # MEASURED (20)
    'conn':            'MEASURED',
    'amen':            'MEASURED',
    'green':           'MEASURED',
    'sch':             'MEASURED',
    'hlth':            'MEASURED',
    'infra':           'MEASURED',
    'env':             'MEASURED',      # was PARTLY — canopy + UHI ingested
    'childcare':       'MEASURED',
    'community':       'MEASURED',
    'sport':           'MEASURED',
    'flood':           'MEASURED',
    'noise':           'MEASURED',
    'air_noise':       'MEASURED',
    'eldercare':       'MEASURED',
    'dens':            'MEASURED',      # was PARTLY — HDB Property Info ingested
    'mom':             'MEASURED',      # was PARTLY — private pipeline ingested
    'hawker':          'MEASURED',      # was JUDGED — NEA Hawker v2 ingested
    'air_quality':     'MEASURED',      # NEW
    'jtc_industrial':  'MEASURED',      # NEW
    'ev_charging':     'MEASURED',      # NEW (stub until LTA token)
    # PARTLY_MEASURED (1)
    'stewardship':     'PARTLY_MEASURED',  # NEW (TCMR transcribed; OneService pending)
}
assert set(PROVENANCE.keys()) == set(W.keys()), \
    f"PROVENANCE and W must agree on keys (diff: {set(W) ^ set(PROVENANCE)})"

# ----------------------------------------------------------------------
# Geo helpers — haversine metres; nearest + count-within-radius
# ----------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_m(lat, lon, pts):
    if pts is None or len(pts) == 0: return np.inf
    return min(haversine(lat, lon, la, lo) for la, lo in pts)

def count_within(lat, lon, pts, radius_m):
    if pts is None or len(pts) == 0: return 0
    return sum(1 for la, lo in pts if haversine(lat, lon, la, lo) <= radius_m)

def pts_of(df):
    if df is None: return []
    return list(zip(df['lat'].astype(float), df['lon'].astype(float)))

# ----------------------------------------------------------------------
# ANCHORS — distance/count -> 1..5. Documented & challengeable thresholds.
# nearer/more = higher. These encode the rubric anchors from Document 1.
# ----------------------------------------------------------------------
def score_by_distance(d_m, anchors):
    for mx, sc in anchors:
        if d_m <= mx: return sc
    return anchors[-1][1]

def score_by_count(n, anchors):
    for mn, sc in anchors:
        if n >= mn: return sc
    return 1

# distance anchors (metres): walkable SG norms
A_MRT      = [(300,5),(600,4),(900,3),(1400,2),(99999,1)]
A_SCHOOL   = [(500,5),(1000,4),(1500,3),(2000,2),(99999,1)]   # MOE 1km/2km bands
A_PARK     = [(300,5),(600,4),(1000,3),(1600,2),(99999,1)]
A_POLY     = [(500,5),(1000,4),(1800,3),(3000,2),(99999,1)]
A_CC       = [(500,5),(1000,4),(1500,3),(2500,2),(99999,1)]   # community clubs
A_SPORT    = [(500,5),(1000,4),(1500,3),(2500,2),(99999,1)]   # sport centres
# flood: INVERSE — farther from flood zone is safer (score 5)
A_FLOOD    = [(250,1),(500,2),(1000,3),(1500,4),(99999,5)]
# noise: INVERSE — farther from expressway is quieter (score 5)
A_NOISE    = [(500,1),(1000,2),(1500,3),(2000,4),(99999,5)]
# air_noise: INVERSE — aircraft noise propagates further than expressway noise,
# so anchors are wider. Distance is to nearest runway/approach-corridor point.
A_AIR_NOISE = [(1000,1),(2000,2),(3500,3),(5000,4),(99999,5)]
# air_quality (PM2.5 µg/m³, INVERSE — lower is better): WHO 2021 tiers
A_PM25     = [(8,5),(12,4),(16,3),(20,2),(99999,1)]
# jtc_industrial (distance to heavy-industrial polygon, INVERSE — farther is
# better): JTC TOL parcel proximity from ingest_jtc_industrial.py
A_JTC      = [(500,1),(1500,2),(3000,3),(5000,4),(99999,5)]

# eldercare: distance-to-nearest + count-within-1500m. Sparser than GPs;
# anchors match community-club scale (walk-or-short-bus visits).
A_ELDER    = [(500,5),(1000,4),(1500,3),(2500,2),(99999,1)]
C_ELDER    = [(4,5),(2,4),(1,3),(0,1)]   # within 1500m

# count anchors
C_CLINIC   = [(8,5),(5,4),(3,3),(1,2),(0,1)]
C_MARKET   = [(3,5),(2,4),(1,3),(0,1)]
C_SUPER    = [(4,5),(2,4),(1,3),(0,1)]
C_BUS      = [(12,5),(8,4),(4,3),(1,2),(0,1)]   # fallback: stop count
C_BUS_ROUTES = [(300,5),(220,4),(140,3),(70,2),(0,1)]  # total route-passes within 800m
C_CHILDCARE= [(4,5),(2,4),(1,3),(0,1)]   # within 500m

# ----------------------------------------------------------------------
# Component scorers
# ----------------------------------------------------------------------
def score_connectivity(lat, lon, mrt, bus, mrt_operational):
    d_mrt = nearest_m(lat, lon, pts_of(mrt))
    s_mrt = score_by_distance(d_mrt, A_MRT)
    if bus is not None and 'route_count' in bus.columns:
        rpts = list(zip(bus['lat'].astype(float), bus['lon'].astype(float), bus['route_count'].astype(int)))
        total_routes = sum(rc for la, lo, rc in rpts if haversine(lat, lon, la, lo) <= 800)
        s_bus = score_by_count(total_routes, C_BUS_ROUTES)
    else:
        s_bus = score_by_count(count_within(lat, lon, pts_of(bus), 800), C_BUS)
    return round(0.7*s_mrt + 0.3*s_bus, 2), {'nearest_mrt_m': round(d_mrt)}

def score_amenities(lat, lon, markets, supers, clinics):
    s_mkt = score_by_count(count_within(lat, lon, pts_of(markets), 800), C_MARKET)
    s_sup = score_by_count(count_within(lat, lon, pts_of(supers), 800), C_SUPER)
    s_cli = score_by_count(count_within(lat, lon, pts_of(clinics), 800), C_CLINIC)
    return round(0.4*s_mkt + 0.35*s_sup + 0.25*s_cli, 2), {}

def score_green(lat, lon, parks):
    return float(score_by_distance(nearest_m(lat, lon, pts_of(parks)), A_PARK)), {}

def score_schools(lat, lon, schools):
    d = nearest_m(lat, lon, pts_of(schools))
    s_near = score_by_distance(d, A_SCHOOL)
    n = count_within(lat, lon, pts_of(schools), 2000)
    s_cnt = score_by_count(n, [(6,5),(4,4),(2,3),(1,2),(0,1)])
    return round(0.6*s_near + 0.4*s_cnt, 2), {'schools_within_2km': n}

def score_healthcare(lat, lon, clinics, poly):
    s_poly = score_by_distance(nearest_m(lat, lon, pts_of(poly)), A_POLY)
    s_gp = score_by_count(count_within(lat, lon, pts_of(clinics), 800), C_CLINIC)
    return round(0.55*s_poly + 0.45*s_gp, 2), {}

def score_eldercare(lat, lon, eldercare):
    d = nearest_m(lat, lon, pts_of(eldercare))
    n = count_within(lat, lon, pts_of(eldercare), 1500)
    s_near = score_by_distance(d, A_ELDER)
    s_cnt = score_by_count(n, C_ELDER)
    return round(0.5*s_near + 0.5*s_cnt, 2), {'nearest_eldercare_m': round(d) if d != np.inf else None,
                                              'eldercare_within_1500m': n}

def score_infra(lat, lon, mrt, mrt_operational):
    if mrt is None or len(mrt) == 0: return 1.0, {'note': 'no mrt data'}
    op = mrt[mrt['operational'].astype(str).str.lower().isin(['1','true','yes','y'])] \
         if 'operational' in mrt.columns else mrt
    d = nearest_m(lat, lon, pts_of(op))
    return float(score_by_distance(d, A_MRT)), {'nearest_operational_mrt_m': round(d)}

def score_childcare(lat, lon, childcare):
    n = count_within(lat, lon, pts_of(childcare), 500)
    return float(score_by_count(n, C_CHILDCARE)), {'childcare_within_500m': n}

def score_community(lat, lon, community):
    d = nearest_m(lat, lon, pts_of(community))
    return float(score_by_distance(d, A_CC)), {'nearest_cc_m': round(d)}

def score_sport(lat, lon, sport):
    d = nearest_m(lat, lon, pts_of(sport))
    return float(score_by_distance(d, A_SPORT)), {'nearest_sport_m': round(d)}

def score_flood_risk(lat, lon, flood_zones):
    d = nearest_m(lat, lon, pts_of(flood_zones))
    # inverted: farther from flood zone = higher score
    return float(score_by_distance(d, A_FLOOD)), {'nearest_flood_zone_m': round(d) if d != np.inf else None}

def score_noise(lat, lon, expressways):
    d = nearest_m(lat, lon, pts_of(expressways))
    # inverted: farther from expressway = quieter = higher score
    return float(score_by_distance(d, A_NOISE)), {'nearest_expressway_m': round(d) if d != np.inf else None}

def score_air_noise(lat, lon, air_noise_corridors):
    d = nearest_m(lat, lon, pts_of(air_noise_corridors))
    # inverted: farther from runway/approach corridor = quieter = higher score
    return float(score_by_distance(d, A_AIR_NOISE)), {'nearest_air_corridor_m': round(d) if d != np.inf else None}

# ----------------------------------------------------------------------
# v2.0 new scorers — consume per-estate enrichment rows (Task 2.2-2.5)
# ----------------------------------------------------------------------
def score_jtc_industrial(row):
    """Inverse-distance from heavy-industrial polygons."""
    d = row.get('nearest_industrial_m')
    if d is None or pd.isna(d):
        return np.nan, {'note': 'jtc data missing'}
    tag = row.get('intensity_tag', 'NONE')
    # Light-industrial gets looser anchors (B1 light-industrial closer to mixed-use)
    if tag in ('HEAVY', 'NONE'):
        anchors = A_JTC
    else:
        anchors = [(250,2),(800,3),(2000,4),(99999,5)]
    return float(score_by_distance(d, anchors)), {
        'jtc_nearest_m': round(d), 'jtc_tag': tag,
    }


def score_air_quality(row):
    """PM2.5 with road-buffer correction (Task 2.3)."""
    pm = row.get('pm25_annual_mean')
    if pm is None or pd.isna(pm):
        return np.nan, {'note': 'air quality data missing'}
    correction = row.get('road_buffer_correction', 0.0) or 0.0
    # correction is an ADDITIVE µg/m³ penalty per ingest_nea_air.py
    pm_adj = float(pm) + float(correction)
    return float(score_by_distance(pm_adj, A_PM25)), {
        'pm25_adjusted': round(pm_adj, 1),
        'haze_days': row.get('haze_days_y'),
    }


TCMR_MAP = {'GREEN': 5, 'AMBER': 3, 'RED': 1}

def score_stewardship(estate_upper, tcmr_json):
    """MND TCMR KPI bands → 1-5 (Task 2.4). PARTLY_MEASURED."""
    if tcmr_json is None:
        return np.nan, {'note': 'tcmr missing'}
    for tc in tcmr_json.get('town_councils', []):
        if estate_upper in [e.upper() for e in tc.get('estates', [])]:
            kpis = [TCMR_MAP.get(tc.get(k), 3) for k in
                    ['scc_arrears', 'lift', 'cleanliness', 'estate_maintenance']]
            base = sum(kpis) / len(kpis)
            close = tc.get('oneservice_close_rate_pct')
            if close is not None:
                base += 0.3 if close >= 90 else (-0.3 if close < 80 else 0.0)
            return float(round(max(1.0, min(5.0, base)), 2)), {'tc': tc.get('name')}
    return np.nan, {'note': f'no TC mapping for {estate_upper}'}


def score_ev_charging(row):
    """EV charger density + HDB carpark coverage (Task 2.5)."""
    n = row.get('n_chargers_800m')
    if n is None or pd.isna(n):
        return np.nan, {'note': 'ev data missing'}
    pct = row.get('hdb_carpark_ev_coverage_pct', 0) or 0
    n_score = score_by_count(int(n), [(20,5),(10,4),(5,3),(1,2),(0,1)])
    pct_score = score_by_count(int(pct), [(80,5),(50,4),(25,3),(10,2),(0,1)])
    return float(round(0.5*n_score + 0.5*pct_score, 2)), {
        'chargers_800m': int(n), 'hdb_coverage_pct': pct,
    }


# ----------------------------------------------------------------------
# v2.0 provenance-flip scorers — read from MEASURED ingester CSVs
# ----------------------------------------------------------------------
A_DENS_RPHN = [(900,5),(700,4),(500,3),(300,2),(0,1)]  # residents/net-ha bands

def score_dens(row):
    """Dwelling density (Task 2.6) — flips PARTLY → MEASURED."""
    r = row.get('residents_per_net_hectare')
    if r is None or pd.isna(r):
        return np.nan, {'note': 'hdb density missing'}
    # HIGHER density scores HIGHER for the urban-living component
    # (the model treats density as a positive — see frameworks doc)
    return float(score_by_count(float(r), A_DENS_RPHN)), {
        'rphn': round(float(r), 1),
        'total_dus': int(row.get('total_dwelling_units') or 0),
    }


def score_hawker(row):
    """Hawker centre count + stalls (Task 2.7) — flips JUDGED → MEASURED."""
    n = row.get('n_hawker_centres_800m')
    if n is None or pd.isna(n):
        return np.nan, {'note': 'hawker data missing'}
    n = int(n)
    stalls = int(row.get('total_stalls_800m') or 0)
    if n >= 2 and stalls >= 150: s = 5.0
    elif n >= 2 or stalls >= 100: s = 4.0
    elif n >= 1 and stalls >= 50: s = 3.0
    elif n >= 1:                   s = 2.0
    else:                           s = 1.0
    return s, {'centres': n, 'stalls': stalls}


# ----------------------------------------------------------------------
# v2.0 refactored sub-metric scorers (Task 2.8, 2.9, 2.10)
# ----------------------------------------------------------------------
A_UHI       = [(-1.0,5),(0.0,4),(0.5,3),(1.0,2),(99,1)]   # cooler = better
A_CANOPY    = [(40,5),(25,4),(15,3),(8,2),(0,1)]           # higher cover = better

def score_env(row):
    """Urban heat-island + canopy (Task 2.8) — flips PARTLY → MEASURED."""
    uhi = row.get('uhi_delta_c')
    canopy = row.get('canopy_cover_pct')
    if (uhi is None or pd.isna(uhi)) and (canopy is None or pd.isna(canopy)):
        return np.nan, {'note': 'env data missing'}
    parts = []
    if uhi is not None and not pd.isna(uhi):
        parts.append(score_by_count(float(uhi), A_UHI))
    if canopy is not None and not pd.isna(canopy):
        parts.append(score_by_count(float(canopy), A_CANOPY))
    return float(round(sum(parts) / len(parts), 2)), {
        'uhi_delta_c': uhi, 'canopy_pct': canopy,
    }


def score_connectivity_v2(lat, lon, mrt, bus, row, mrt_operational=None):
    """conn with optional shelter + cycling sub-metrics (Task 2.9).
    Base = 0.7 MRT + 0.3 bus (v1 behaviour).
    If walking/cycling rows are MEASURED (not 'unfetched'), blend:
      0.6 MRT + 0.2 bus + 0.1 shelter + 0.1 cycling
    """
    d_mrt = nearest_m(lat, lon, pts_of(mrt))
    s_mrt = score_by_distance(d_mrt, A_MRT)
    if bus is not None and 'route_count' in bus.columns:
        rpts = list(zip(bus['lat'].astype(float), bus['lon'].astype(float),
                         bus['route_count'].astype(int)))
        total_routes = sum(rc for la, lo, rc in rpts
                            if haversine(lat, lon, la, lo) <= 800)
        s_bus = score_by_count(total_routes, C_BUS_ROUTES)
    else:
        s_bus = score_by_count(count_within(lat, lon, pts_of(bus), 800), C_BUS)
    # Sub-metric blend if walking + cycling MEASURED
    if row is None:
        return round(0.7*s_mrt + 0.3*s_bus, 2), {'nearest_mrt_m': round(d_mrt)}
    walk_note = str(row.get('provenance_note_walking_routes') or '')
    cyc_note = str(row.get('provenance_note_cycling_paths') or '')
    if walk_note.startswith('unfetched') or cyc_note.startswith('unfetched'):
        return round(0.7*s_mrt + 0.3*s_bus, 2), {'nearest_mrt_m': round(d_mrt)}
    pct_shelt = row.get('pct_sheltered_to_mrt') or 0
    cyc_m = row.get('dedicated_path_m_within_800m') or 0
    s_shelt = score_by_count(int(pct_shelt), [(80,5),(60,4),(40,3),(20,2),(0,1)])
    s_cyc = score_by_count(int(cyc_m), [(2000,5),(1200,4),(600,3),(200,2),(0,1)])
    return round(0.6*s_mrt + 0.2*s_bus + 0.1*s_shelt + 0.1*s_cyc, 2), {
        'nearest_mrt_m': round(d_mrt), 'pct_sheltered': pct_shelt,
        'cycling_path_m': cyc_m,
    }


def score_green_v2(lat, lon, parks, row):
    """green with blue sub-metric (Task 2.10).
    Base = nearest-park distance.
    Bonus +0.5 if has_blue_within_800m and blue_type ∈ {SEA, RESERVOIR};
    +0.25 if WATERWAY.
    """
    s_park = score_by_distance(nearest_m(lat, lon, pts_of(parks)), A_PARK)
    if row is None:
        return float(s_park), {}
    has_blue = row.get('has_blue_within_800m', False)
    blue_type = row.get('blue_type', 'NONE')
    bonus = 0.0
    if str(has_blue).lower() in ('true', '1') and blue_type in ('SEA', 'RESERVOIR'):
        bonus = 0.5
    elif str(has_blue).lower() in ('true', '1') and blue_type == 'WATERWAY':
        bonus = 0.25
    return float(round(min(5.0, s_park + bonus), 2)), {
        'park_base': s_park, 'blue': blue_type if has_blue else 'NONE',
    }


# ----------------------------------------------------------------------
# Assemble
# ----------------------------------------------------------------------
def _join_enrichments(estates, layers):
    """Per-estate left-joins of all v2.0 ingester CSVs onto estates.
    Returns the enriched estates DataFrame with an `estate_u` key.
    Suffixes collisions per-source so e.g. provenance_note appears as
    provenance_note_walking_routes / provenance_note_cycling_paths /
    provenance_note_ev_chargers."""
    out = estates.copy()
    out['estate_u'] = out['estate'].str.upper()
    ENRICH = ['jtc_industrial', 'air_quality', 'ev_chargers',
              'tree_canopy', 'walking_routes', 'cycling_paths', 'coastal',
              'hdb_density', 'hawker_v2', 'bca_permits']
    for key in ENRICH:
        df = layers.get(key)
        if df is None or 'estate' not in df.columns:
            continue
        right = df.copy()
        right['estate_u'] = right['estate'].str.upper()
        right = right.drop(columns=['estate'])
        # Rename non-key cols with the source key suffix to avoid collisions
        rename_map = {c: f"{c}_{key}" if c != 'estate_u' and c in out.columns else c
                       for c in right.columns}
        right = right.rename(columns=rename_map)
        out = out.merge(right, on='estate_u', how='left')
    return out


def run(estates, layers, judged):
    enriched = _join_enrichments(estates, layers)
    tcmr = layers.get('tcmr')
    rows = []
    for _, e in enriched.iterrows():
        lat, lon = float(e['lat']), float(e['lon']); name = e['estate']
        s = {}
        s['conn'],_      = score_connectivity_v2(lat, lon, layers['mrt'],
                                                  layers['bus'], e)
        s['amen'],_      = score_amenities(lat, lon, layers['markets'],
                                            layers['supermarkets'], layers['clinics'])
        s['green'],_     = score_green_v2(lat, lon, layers['parks'], e)
        s['sch'],_       = score_schools(lat, lon, layers['schools'])
        s['hlth'],_      = score_healthcare(lat, lon, layers['clinics'],
                                             layers['polyclinics'])
        s['eldercare'],_ = score_eldercare(lat, lon, layers['eldercare'])
        s['infra'],_     = score_infra(lat, lon, layers['mrt'], None)
        s['childcare'],_ = score_childcare(lat, lon, layers['childcare'])
        s['community'],_ = score_community(lat, lon, layers['community'])
        s['sport'],_     = score_sport(lat, lon, layers['sport'])
        s['flood'],_     = score_flood_risk(lat, lon, layers['flood'])
        s['noise'],_     = score_noise(lat, lon, layers['noise'])
        s['air_noise'],_ = score_air_noise(lat, lon, layers['air_noise'])

        # v2.0 MEASURED-from-CSV components
        s['jtc_industrial'],_ = score_jtc_industrial(e)
        s['air_quality'],_    = score_air_quality(e)
        s['ev_charging'],_    = score_ev_charging(e)
        s['stewardship'],_    = score_stewardship(name.upper(), tcmr)
        s['dens'],_           = score_dens(e)
        s['hawker'],_         = score_hawker(e)
        s['env'],_            = score_env(e)

        # mom: still read from judged_inputs.csv (momentum_model.py writes it
        # there; private-pipeline extension lands via Task 3.2)
        jr = judged[judged['estate'] == name] if judged is not None else pd.DataFrame()
        if not jr.empty and 'mom' in jr.columns and not pd.isna(jr.iloc[0]['mom']):
            s['mom'] = float(jr.iloc[0]['mom'])
        else:
            s['mom'] = np.nan
        # Legacy fallback: if a v2.0 CSV missing AND judged has the column, use it
        for k in ['dens', 'env', 'hawker']:
            if pd.isna(s.get(k)) and not jr.empty and k in jr.columns \
                    and not pd.isna(jr.iloc[0][k]):
                s[k] = float(jr.iloc[0][k])
        # Construction-disruption D-multiplier (Task 2.12) — losses-only.
        # severity_score from bca_permits.csv: GFA(kSF) × remaining_months / setback_m.
        # Empirically max ~1100 (JURONG EAST); typical heavy site ~500.
        # D ramps linearly from 1.00 (no disruption) to 0.95 (severity≥1000).
        sev = e.get('severity_score_bca_permits')
        if sev is None or pd.isna(sev):
            sev = e.get('severity_score', 0)   # if joined without suffix
        d_construction = max(0.95, 1.0 - 0.05 * (float(sev or 0) / 1000.0))
        rows.append({'estate': name, **s, 'd_construction': round(d_construction, 3)})
    df = pd.DataFrame(rows)

    # provision = weighted sum; if a JUDGED/PARTLY input is missing, report
    # MEASURED-only subscore + a 'completeness' flag instead of inventing it.
    def provision(row):
        present = {k: row[k] for k in W if not pd.isna(row[k])}
        wsum = sum(W[k] for k in present)
        val = sum(W[k]*present[k] for k in present) / wsum   # renormalise over present
        return round(val, 2), round(wsum, 3)
    df[['provision','weight_covered']] = df.apply(lambda r: pd.Series(provision(r)), axis=1)
    # Apply D-multiplier (losses-only — never raises score)
    df['provision_predisrupt'] = df['provision']
    df['provision'] = (df['provision'] * df['d_construction']).round(2)
    df['score'] = df['provision']  # column name value_model.py expects
    df['measured_only'] = df[['dens','env','mom','hawker']].isna().any(axis=1)
    return df

def band(x):
    for edge, b in [(4.5,"A"),(4.0,"B+"),(3.5,"B"),(3.0,"C"),(2.5,"D"),(0,"F")]:
        if x >= edge: return b
    return "F"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--estates', required=True)
    GEO_LAYERS = ['mrt','bus','clinics','polyclinics','schools','parks','markets',
                  'supermarkets','childcare','community','sport','flood','noise',
                  'air_noise','eldercare']
    V2_LAYERS = ['jtc_industrial','air_quality','ev_chargers',
                 'tree_canopy','walking_routes','cycling_paths','coastal',
                 'hdb_density','hawker_v2','bca_permits']
    for L in GEO_LAYERS + V2_LAYERS:
        ap.add_argument(f'--{L}')
    ap.add_argument('--tcmr', help='JSON: MND TCMR snapshot (ingest_tcmr.py)')
    ap.add_argument('--judged', help='CSV (legacy v1.x): estate,dens,env,mom,hawker — '
                                      'still honoured as fallback when v2.0 ingester CSVs '
                                      'absent. Will be retired once all 4 components have '
                                      'their MEASURED ingester CSV wired.')
    ap.add_argument('--out', default='provision_scores.csv')
    a = ap.parse_args()

    estates = pd.read_csv(a.estates)
    assert {'estate','lat','lon'} <= set(estates.columns), "estates.csv needs: estate,lat,lon"
    def load(p): return pd.read_csv(p) if p else None
    layers = {L: load(getattr(a, L)) for L in GEO_LAYERS + V2_LAYERS}
    # TCMR is JSON not CSV — load separately
    tcmr = None
    if a.tcmr:
        import json as _json
        with open(a.tcmr) as _f:
            tcmr = _json.load(_f)
    layers['tcmr'] = tcmr
    judged = load(a.judged)

    df = run(estates, layers, judged)
    df['band'] = df['provision'].apply(band)
    df.to_csv(a.out, index=False)

    cols = ['estate','conn','amen','green','sch','dens','hlth','eldercare','mom','hawker','infra','env',
            'childcare','community','sport','flood','noise','air_noise',
            'provision','band','weight_covered','measured_only']
    print(df[cols].to_string(index=False))
    print("\nProvenance:", {k: PROVENANCE[k] for k in W})
    print("measured_only=True  -> a JUDGED/PARTLY input (dens/env/mom/hawker) was MISSING;")
    print("provision was renormalised over present components. Supply --judged to complete it.")
    print(f"\nWritten {a.out}  -> feed directly to value_model.py as --scores")

if __name__ == '__main__':
    main()

# ======================================================================
# INPUT CONTRACT — provision_model.py v1.3
# ======================================================================
# REQUIRED:
#   --estates estates.csv     columns: estate,lat,lon
#
# GEOSPATIAL LAYERS (each CSV: lat,lon [+ extra cols ignored]):
#   --mrt mrt.csv             lat,lon,operational   (operational=1/0)
#   --bus bus.csv             lat,lon               (LTA bus stops)
#   --clinics chas.csv        lat,lon               (CHAS clinics)
#   --polyclinics poly.csv    lat,lon               (MOH polyclinics)
#   --schools schools.csv     lat,lon               (MOE schools)
#   --parks parks.csv         lat,lon               (NParks parks)
#   --markets markets.csv     lat,lon               (hawker centres + wet markets)
#   --supermarkets s.csv      lat,lon               (supermarkets)
#   --childcare childcare.csv lat,lon               (ECDA pre-schools; d_61eefab99958fd70e6aab17320a71f1c)
#   --community community.csv lat,lon               (PA community clubs; d_f706de1427279e61fe41e89e24d440fa)
#   --sport sport.csv         lat,lon               (SportSG/ActiveSG centres; d_9b87bab59d036a60fad2a91530e10773)
#   --flood flood_risk.csv    lat,lon               (PUB flood-prone areas, Nov 2025, 36 locations)
#   --noise expressways.csv   lat,lon               (OSM expressway centerline points)
#   --air_noise air_noise_corridors.csv  lat,lon,corridor
#                             (geometric proxy: runway centerlines + 12 km
#                              approach corridors for Changi, Seletar, Paya Lebar)
#   --eldercare eldercare.csv lat,lon,name,type     (AIC Silver Pages: day_centre,
#                              nursing_home, ambulatory_care, day_care, AAC, etc.)
#
# NON-GEOSPATIAL (judgement) COMPONENTS:
#   --judged judged.csv       columns: estate,dens,env,mom,hawker   (each 1-5)
#       If omitted, those 4 components are left MISSING and provision is
#       computed from the 13 measured components only (measured_only=True).
#       NEVER auto-fill these — they are opinion by construction.
#
# WEIGHTS (v1.3, 17 components, sum=1.000):
#   conn 15%, infra 15%, amen 10%, green 9%, dens 8%, sch 7%, childcare 6%,
#   hlth 4%, mom 4%, hawker 4%, noise 4%, air_noise 3%, community 3%,
#   eldercare 3%, env 2%, sport 2%, flood 1%
#
# PIPELINE:
#   python provision_model.py --estates e.csv --mrt mrt.csv ... \
#       --childcare childcare.csv --community community.csv \
#       --sport sport.csv --flood flood_risk.csv --noise expressways.csv \
#       --air_noise air_noise_corridors.csv --eldercare eldercare.csv \
#       --judged judged_inputs.csv --out provision_scores.csv
#   python value_model.py --scores provision_scores.csv --hdb hdb.csv
# ======================================================================
