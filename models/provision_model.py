#!/usr/bin/env python3
"""
Singapore Estate PROVISION MODEL  (Document 1, v2.0)  — geospatial, real-data
=============================================================================
Computes the Provision score per estate from ACTUAL spatial data, instead of
analyst judgement. Emits the scores.csv that value_model.py consumes.

HONEST SCOPE (read this — the model enforces it in output):
  MEASURED        (14): connectivity, amenities, green, schools, healthcare,
                        infra, childcare, community, sport, flood_risk, noise,
                        air_noise (geometric corridor proxy — see note),
                        eldercare (v1.3: carved from healthcare — AIC/MOH facilities),
                        jtc_industrial (v2.0: industrial-buffer/nuisance proximity)
  PARTLY_MEASURED  (6): density (dwelling density yes; "feel" no),
                        env_comfort (heat/shade only; air-noise + expressway now
                        split out as siblings — see audit §2d),
                        momentum (HDB-side ingested from data.gov.sg NRP+LUP+SERS
                        via ingest_hdb_upgrading.py; private-side en-bloc / new
                        launches still JUDGED — see audit §2a),
                        air_quality (v2.0: PM2.5/NEA air-quality index proxy),
                        stewardship (v2.0: TC-KPI / estate maintenance quality),
                        hawker (v2.0: count/distance/stall proxy; fame not measured)
  JUDGED           (0): none in the canonical pipeline

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
import argparse, json, sys, math
import numpy as np, pandas as pd

# ----------------------------------------------------------------------
# Constants imported from framework_config (single source of truth).
# Module-level names W / W_PRIVATE / PROVENANCE are preserved so that
# existing tests (test_doc_consistency.py, test_invariants.py) and any
# downstream import of `provision_model.W` continue to work unchanged.
# ----------------------------------------------------------------------
from framework_config import (
    PROVISION_WEIGHTS as W,
    PROVISION_WEIGHTS_PRIVATE as W_PRIVATE,
    PROVENANCE,
    band_label as _fc_band_label,
)

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

def _safe_round_dist(d):
    """Return round(d) as int, or None when d is infinite (no POI in layer)."""
    return round(d) if math.isfinite(d) else None

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
# §1c: covered linkway polygon count within 800m (LTA DataMall, quarterly).
# Calibrated on 7,012 LTA Mar-2026 polygons: top tier ≥100 (Bukit Panjang 158,
# Bukit Batok 145), near-zero for new towns (Tengah 0, Punggol 0, Canberra 4).
C_SHELTER  = [(100,5),(50,4),(30,3),(15,2),(0,1)]
C_CHILDCARE= [(4,5),(2,4),(1,3),(0,1)]   # within 500m

# ----------------------------------------------------------------------
# Component scorers
# ----------------------------------------------------------------------
def score_connectivity(lat, lon, mrt, bus, mrt_operational, covered_linkway=None):
    d_mrt = nearest_m(lat, lon, pts_of(mrt))
    s_mrt = score_by_distance(d_mrt, A_MRT)
    if bus is not None and 'route_count' in bus.columns:
        rpts = list(zip(bus['lat'].astype(float), bus['lon'].astype(float), bus['route_count'].astype(int)))
        total_routes = sum(rc for la, lo, rc in rpts if haversine(lat, lon, la, lo) <= 800)
        s_bus = score_by_count(total_routes, C_BUS_ROUTES)
    else:
        s_bus = score_by_count(count_within(lat, lon, pts_of(bus), 800), C_BUS)
    if covered_linkway is not None:
        n_shelter = count_within(lat, lon, pts_of(covered_linkway), 800)
        s_shelter = score_by_count(n_shelter, C_SHELTER)
        return round(0.60*s_mrt + 0.25*s_bus + 0.15*s_shelter, 2), {
            'nearest_mrt_m': _safe_round_dist(d_mrt), 'covered_linkways_800m': n_shelter}
    return round(0.7*s_mrt + 0.3*s_bus, 2), {'nearest_mrt_m': _safe_round_dist(d_mrt)}

def score_amenities(lat, lon, markets, supers, clinics):
    s_mkt = score_by_count(count_within(lat, lon, pts_of(markets), 800), C_MARKET)
    s_sup = score_by_count(count_within(lat, lon, pts_of(supers), 800), C_SUPER)
    s_cli = score_by_count(count_within(lat, lon, pts_of(clinics), 800), C_CLINIC)
    return round(0.4*s_mkt + 0.35*s_sup + 0.25*s_cli, 2), {}

def score_green(lat, lon, parks, coastal_row=None):
    s_park = score_by_distance(nearest_m(lat, lon, pts_of(parks)), A_PARK)
    if coastal_row is not None:
        has_blue = coastal_row.get('has_blue_within_800m')
        if has_blue is True or has_blue == 1 or str(has_blue).lower() in ('true', '1', 'yes', 'y'):
            return float(round(min(5.0, s_park + 0.3), 2)), {}
    return float(s_park), {}

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
    return float(score_by_distance(d, A_MRT)), {'nearest_operational_mrt_m': _safe_round_dist(d)}

def score_childcare(lat, lon, childcare):
    n = count_within(lat, lon, pts_of(childcare), 500)
    return float(score_by_count(n, C_CHILDCARE)), {'childcare_within_500m': n}

def score_community(lat, lon, community):
    d = nearest_m(lat, lon, pts_of(community))
    return float(score_by_distance(d, A_CC)), {'nearest_cc_m': _safe_round_dist(d)}

def score_sport(lat, lon, sport):
    d = nearest_m(lat, lon, pts_of(sport))
    return float(score_by_distance(d, A_SPORT)), {'nearest_sport_m': _safe_round_dist(d)}

def score_flood_risk(lat, lon, flood_zones):
    d = nearest_m(lat, lon, pts_of(flood_zones))
    # inverted: farther from flood zone = higher score
    return float(score_by_distance(d, A_FLOOD)), {'nearest_flood_zone_m': _safe_round_dist(d)}

def score_noise(lat, lon, expressways):
    d = nearest_m(lat, lon, pts_of(expressways))
    # inverted: farther from expressway = quieter = higher score
    return float(score_by_distance(d, A_NOISE)), {'nearest_expressway_m': _safe_round_dist(d)}

def score_air_noise(lat, lon, air_noise_corridors):
    d = nearest_m(lat, lon, pts_of(air_noise_corridors))
    # inverted: farther from runway/approach corridor = quieter = higher score
    return float(score_by_distance(d, A_AIR_NOISE)), {'nearest_air_corridor_m': _safe_round_dist(d)}

def score_env(row):
    if row is None or not isinstance(row, dict):
        return np.nan
    canopy = row.get('canopy_cover_pct')
    uhi = row.get('uhi_delta_c')
    if pd.isna(canopy) or pd.isna(uhi):
        return np.nan
    try:
        score_canopy = score_by_count(float(canopy), [(30, 5), (20, 4), (10, 3), (5, 2), (0, 1)])
        score_uhi = score_by_distance(float(uhi), [(0.2, 5), (0.6, 4), (1.2, 3), (1.8, 2), (99, 1)])
        return round(0.5 * score_canopy + 0.5 * score_uhi, 2)
    except (ValueError, TypeError):
        return np.nan


def score_dens(row):
    if row is None or not isinstance(row, dict):
        return np.nan
    units = row.get('total_dwelling_units')
    density = row.get('residents_per_net_hectare')
    if pd.isna(units) or pd.isna(density):
        return np.nan
    try:
        if float(units) == 0:
            return np.nan
        score = score_by_distance(float(density), [(150, 5), (300, 4), (450, 3), (600, 2), (99999, 1)])
        return float(score)
    except (ValueError, TypeError):
        return np.nan


def score_hawker_v2(row):
    if row is None or not isinstance(row, dict):
        return np.nan
    dist = row.get('nearest_hawker_m')
    stalls = row.get('total_stalls_800m')
    cnt = row.get('n_hawker_centres_800m')
    if pd.isna(dist) or pd.isna(stalls) or pd.isna(cnt):
        return np.nan
    try:
        score_dist = score_by_distance(float(dist), [(400, 5), (800, 4), (1200, 3), (2000, 2), (99999, 1)])
        score_stalls = score_by_count(float(stalls), [(150, 5), (80, 4), (40, 3), (10, 2), (0, 1)])
        score_count = score_by_count(float(cnt), [(2, 5), (1, 3), (0, 1)])
        score_combined = 0.4 * score_dist + 0.4 * score_stalls + 0.2 * score_count
        
        redundancy = row.get('has_redundancy_dayoff')
        if redundancy is True or redundancy == 1 or str(redundancy).lower() in ('true', '1', 'yes', 'y'):
            score_combined += 0.2
        return round(min(5.0, score_combined), 2)
    except (ValueError, TypeError):
        return np.nan


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
    """PM2.5 with road-buffer correction."""
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
    """MND TCMR KPI bands → 1-5. PARTLY_MEASURED."""
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


# ----------------------------------------------------------------------
# Assemble
# ----------------------------------------------------------------------
def run(estates, layers, judged, tcmr_json=None):
    # Build per-estate lookup dicts from enrichment CSVs (keyed by UPPERCASE estate)
    jtc_lkp = {}
    if layers.get('jtc_industrial') is not None:
        for _, r in layers['jtc_industrial'].iterrows():
            jtc_lkp[str(r['estate']).upper()] = r.to_dict()
    aq_lkp = {}
    if layers.get('air_quality') is not None:
        for _, r in layers['air_quality'].iterrows():
            aq_lkp[str(r['estate']).upper()] = r.to_dict()
    canopy_lkp = {}
    if layers.get('tree_canopy') is not None:
        for _, r in layers['tree_canopy'].iterrows():
            canopy_lkp[str(r['estate']).upper()] = r.to_dict()
    density_lkp = {}
    if layers.get('hdb_density') is not None:
        for _, r in layers['hdb_density'].iterrows():
            density_lkp[str(r['estate']).upper()] = r.to_dict()
    hawker_lkp = {}
    if layers.get('hawker_v2') is not None:
        for _, r in layers['hawker_v2'].iterrows():
            hawker_lkp[str(r['estate']).upper()] = r.to_dict()
    coastal_lkp = {}
    if layers.get('coastal') is not None:
        for _, r in layers['coastal'].iterrows():
            coastal_lkp[str(r['estate']).upper()] = r.to_dict()

    rows = []
    for _, e in estates.iterrows():
        lat, lon = float(e['lat']), float(e['lon']); name = e['estate']
        s = {}
        s['conn'],_      = score_connectivity(lat, lon, layers['mrt'], layers['bus'], None,
                                             layers.get('covered_linkway'))
        s['amen'],_      = score_amenities(lat, lon, layers['markets'], layers['supermarkets'], layers['clinics'])
        
        coastal_row = coastal_lkp.get(name.upper()) if layers.get('coastal') is not None else None
        s['green'],_     = score_green(lat, lon, layers['parks'], coastal_row=coastal_row)
        
        s['sch'],_       = score_schools(lat, lon, layers['schools'])
        s['hlth'],_      = score_healthcare(lat, lon, layers['clinics'], layers['polyclinics'])
        s['eldercare'],_ = score_eldercare(lat, lon, layers['eldercare'])
        s['infra'],_     = score_infra(lat, lon, layers['mrt'], None)
        s['childcare'],_ = score_childcare(lat, lon, layers['childcare'])
        s['community'],_ = score_community(lat, lon, layers['community'])
        s['sport'],_     = score_sport(lat, lon, layers['sport'])
        s['flood'],_     = score_flood_risk(lat, lon, layers['flood'])
        s['noise'],_     = score_noise(lat, lon, layers['noise'])
        s['air_noise'],_ = score_air_noise(lat, lon, layers['air_noise'])

        # v2.0 per-estate enrichment components
        s['jtc_industrial'],_ = score_jtc_industrial(jtc_lkp.get(name.upper(), {}))
        s['air_quality'],_    = score_air_quality(aq_lkp.get(name.upper(), {}))
        s['stewardship'],_    = score_stewardship(name.upper(), tcmr_json)

        # PARTLY: prefer generated layers, then judged_inputs.csv, else NaN-flag
        jr = judged[judged['estate'] == name] if judged is not None else pd.DataFrame()
        
        # env
        if layers.get('tree_canopy') is not None:
            s['env'] = score_env(canopy_lkp.get(name.upper()))
        else:
            if not jr.empty and 'env' in jr.columns and not pd.isna(jr.iloc[0]['env']):
                s['env'] = float(jr.iloc[0]['env'])
            else:
                s['env'] = np.nan

        # dens
        if layers.get('hdb_density') is not None:
            s['dens'] = score_dens(density_lkp.get(name.upper()))
        else:
            if not jr.empty and 'dens' in jr.columns and not pd.isna(jr.iloc[0]['dens']):
                s['dens'] = float(jr.iloc[0]['dens'])
            else:
                s['dens'] = np.nan

        # mom
        if not jr.empty and 'mom' in jr.columns and not pd.isna(jr.iloc[0]['mom']):
            s['mom'] = float(jr.iloc[0]['mom'])
        else:
            s['mom'] = np.nan

        # hawker
        if layers.get('hawker_v2') is not None:
            s['hawker'] = score_hawker_v2(hawker_lkp.get(name.upper()))
        else:
            if not jr.empty and 'hawker' in jr.columns and not pd.isna(jr.iloc[0]['hawker']):
                s['hawker'] = float(jr.iloc[0]['hawker'])
            else:
                s['hawker'] = np.nan

        rows.append({'estate': name, **s})
    df = pd.DataFrame(rows)

    # provision = weighted sum; if a PARTLY input is missing, report
    # MEASURED-only subscore + a 'completeness' flag instead of inventing it.
    def provision(row):
        present = {k: row[k] for k in W if not pd.isna(row[k])}
        wsum = sum(W[k] for k in present)
        val = sum(W[k]*present[k] for k in present) / wsum   # renormalise over present
        return round(val, 2), round(wsum, 3)
    df[['provision','weight_covered']] = df.apply(lambda r: pd.Series(provision(r)), axis=1)
    df['score'] = df['provision']  # column name value_model.py expects

    # Private (condo) provision score — same components, W_PRIVATE weights
    def provision_p(row):
        present = {k: row[k] for k in W_PRIVATE if not pd.isna(row[k])}
        wsum = sum(W_PRIVATE[k] for k in present)
        val = sum(W_PRIVATE[k]*present[k] for k in present) / wsum
        return round(val, 2)
    df['provision_private'] = df.apply(provision_p, axis=1)
    df['score_private'] = df['provision_private']

    # Flag renormalisation over a missing PARTLY_MEASURED input. Derive the column list from
    # PROVENANCE so all 6 PARTLY components (incl. air_quality, stewardship) are covered and the
    # flag can't drift from the provenance split.
    _partly = [k for k, v in PROVENANCE.items() if v == "PARTLY_MEASURED"]
    df['measured_only'] = df[_partly].isna().any(axis=1)
    return df

# band() removed — use the canonical framework_config.band_label (imported as _fc_band_label).
# provision_model.main() calls it directly via _fc_band_label; no external callers used
# the local copy.

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--estates', required=True)
    for L in ['mrt','bus','clinics','polyclinics','schools','parks','markets',
              'supermarkets','childcare','community','sport','flood','noise',
              'air_noise','eldercare','covered_linkway','jtc_industrial','air_quality',
              'tree_canopy','hdb_density','hawker_v2','coastal']:
        ap.add_argument(f'--{L}')
    ap.add_argument('--tcmr', help='JSON path: town_council_kpi.json (for stewardship score)')
    ap.add_argument('--judged', help='CSV: estate,dens,env,mom,hawker (the 4 non-geospatial)')
    ap.add_argument('--out', default='provision_scores.csv')
    a = ap.parse_args()

    estates = pd.read_csv(a.estates)
    assert {'estate','lat','lon'} <= set(estates.columns), "estates.csv needs: estate,lat,lon"
    def load(p):
        import os
        if p and os.path.exists(p):
            return pd.read_csv(p)
        if p:
            sys.exit(f"provision_model: input file not found: {p}")
        return None
    layers = {L: load(getattr(a, L)) for L in
              ['mrt','bus','clinics','polyclinics','schools','parks','markets',
               'supermarkets','childcare','community','sport','flood','noise',
               'air_noise','eldercare','covered_linkway','jtc_industrial','air_quality',
               'tree_canopy','hdb_density','hawker_v2','coastal']}
    judged = load(a.judged)
    tcmr_json = None
    if a.tcmr:
        with open(a.tcmr) as fh:
            tcmr_json = json.load(fh)

    df = run(estates, layers, judged, tcmr_json=tcmr_json)
    df['band'] = df['provision'].apply(_fc_band_label)
    df.to_csv(a.out, index=False)

    cols = ['estate','conn','amen','green','sch','dens','hlth','eldercare','mom','hawker','infra','env',
            'childcare','community','sport','flood','noise','air_noise',
            'jtc_industrial','air_quality','stewardship',
            'provision','band','weight_covered','measured_only']
    print(df[cols].to_string(index=False))
    print("\nProvenance:", {k: PROVENANCE[k] for k in W})
    _partly = [k for k, v in PROVENANCE.items() if v == 'PARTLY_MEASURED']
    print(f"measured_only=True  -> a PARTLY input ({'/'.join(_partly)}) was MISSING;")
    print("provision was renormalised over present components. Supply --judged and derived layer flags to complete it.")
    print(f"\nWritten {a.out}  -> feed directly to value_model.py as --scores")

if __name__ == '__main__':
    main()

# ======================================================================
# INPUT CONTRACT — provision_model.py v2.0
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
#   --covered_linkway covered_linkway.csv  lat,lon  (LTA DataMall static shapefile,
#                              converted polygon centroids; 7,012 features, Mar 2026,
#                              quarterly. OPTIONAL — if absent, conn falls back to
#                              0.7*s_mrt + 0.3*s_bus. If present, sub-weights become
#                              0.60*s_mrt + 0.25*s_bus + 0.15*s_shelter; top-level
#                              conn weight (0.14) is unchanged. MEASURED provenance.)
#
# PER-ESTATE ENRICHMENT LAYERS:
#   --tree_canopy tree_canopy.csv  columns: estate,canopy_cover_pct,uhi_delta_c
#       Supplies env. If omitted, env falls back to judged_inputs.csv.
#   --hdb_density hdb_density.csv  columns: estate,total_dwelling_units,residents_per_net_hectare
#       Supplies dens. If omitted, dens falls back to judged_inputs.csv.
#   --hawker_v2 hawker_v2.csv      columns: estate,nearest_hawker_m,total_stalls_800m,
#                                  n_hawker_centres_800m,has_redundancy_dayoff
#       Supplies hawker. If omitted, hawker falls back to judged_inputs.csv.
#   --coastal coastal.csv          columns: estate,has_blue_within_800m
#       Adds a small blue-infrastructure bonus to green.
#
# PARTLY MEASURED INPUTS:
#   --judged judged.csv       columns: estate,dens,env,mom,hawker   (each 1-5)
#       The canonical pipeline still uses mom from judged_inputs.csv. dens/env/hawker
#       are used only when their generated layers are omitted. Missing PARTLY inputs
#       are left NaN and provision is renormalised over present components.
#
# WEIGHTS (v2.0, 20 components, sum=1.000):
#   Authoritative source: framework_config.PROVISION_WEIGHTS (imported as W above).
#   conn 14%, infra 14%, amen 9%, green 8%, dens 8%, sch 7%, childcare 5%,
#   hlth 4%, mom 4%, hawker 4%, noise 3%, air_noise 3%, eldercare 3%,
#   stewardship 3%, air_quality 3%, community 2%, sport 2%, jtc_industrial 2%,
#   env 1%, flood 1%
#
# PIPELINE:
#   python provision_model.py --estates e.csv --mrt mrt.csv ... \
#       --childcare childcare.csv --community community.csv \
#       --sport sport.csv --flood flood_risk.csv --noise expressways.csv \
#       --air_noise air_noise_corridors.csv --eldercare eldercare.csv \
#       --tree_canopy tree_canopy.csv --hdb_density hdb_density.csv \
#       --hawker_v2 hawker_v2.csv --coastal coastal.csv \
#       --judged judged_inputs.csv --out provision_scores.csv
#   python value_model.py --scores provision_scores.csv --hdb hdb.csv
# ======================================================================
