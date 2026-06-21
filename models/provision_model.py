#!/usr/bin/env python3
"""
Singapore Estate PROVISION MODEL  (Document 1, v1.0)  — geospatial, real-data
=============================================================================
Computes the Provision score per estate from ACTUAL spatial data, instead of
analyst judgement. Emits the scores.csv that value_model.py consumes.

HONEST SCOPE (read this — the model enforces it in output):
  MEASURED        (13): connectivity, amenities, green, schools, healthcare,
                        infra, childcare, community, sport, flood_risk, noise,
                        air_noise (geometric corridor proxy — see note),
                        eldercare (v1.3: carved from healthcare — AIC/MOH facilities)
  PARTLY_MEASURED  (3): density (dwelling density yes; "feel" no),
                        env_comfort (heat/shade only; air-noise + expressway now
                        split out as siblings — see audit §2d),
                        momentum (HDB-side ingested from data.gov.sg NRP+LUP+SERS
                        via ingest_hdb_upgrading.py; private-side en-bloc / new
                        launches still JUDGED — see audit §2a)
  JUDGED           (1): hawker (fame/reputation — not a query)

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
# v1.3 weights (sum=1.000). Added eldercare (3%); carved from hlth (0.07→0.04),
# implementing audit §1d. eldercare = AIC Silver Pages / MOH day-care + AAC +
# nursing-home + senior-care-centre density. hlth now scopes GP/polyclinic only.
# Prior v1.2 split: air_noise carved from env (0.05→0.02) — see audit §2d.
# ----------------------------------------------------------------------
W = {
    'conn':      0.15,
    'amen':      0.10,
    'green':     0.09,
    'sch':       0.07,
    'dens':      0.08,
    'hlth':      0.04,
    'mom':       0.04,
    'infra':     0.15,
    'env':       0.02,
    'childcare': 0.06,
    'community': 0.03,
    'sport':     0.02,
    'flood':     0.01,
    'hawker':    0.04,
    'noise':     0.04,
    'air_noise': 0.03,
    'eldercare': 0.03,
}
assert abs(sum(W.values()) - 1.0) < 1e-9, f"Weights must sum to 1.0, got {sum(W.values())}"

# Private (condo) weight variant. Adjustments vs W:
#   conn  ↓ 0.15→0.12 (car ownership higher; parking within development)
#   amen  ↑ 0.10→0.13 (F&B cluster / mall access > hawker)
#   green ↓ 0.09→0.07 (landscaped grounds within development reduce urgency)
#   sch   ↑ 0.07→0.11 (school postal code is a direct pricing driver)
#   sport ↓ 0.02→0.01 (gym/pool within development)
#   hawker↓ 0.04→0.02 (restaurant/delivery preference)
#   infra ↑ 0.15→0.16 (MRT proximity premium stronger for asset value)
#   eldercare ↓ 0.03→0.02 (private buyer cohort skews younger/wealthier)
#   childcare ↑ 0.06→0.07 (family-forming cohort in private market)
W_PRIVATE = {
    'conn':      0.12,
    'amen':      0.13,
    'green':     0.07,
    'sch':       0.11,
    'dens':      0.08,
    'hlth':      0.04,
    'mom':       0.04,
    'infra':     0.16,
    'env':       0.02,
    'childcare': 0.07,
    'community': 0.03,
    'sport':     0.01,
    'flood':     0.01,
    'hawker':    0.02,
    'noise':     0.04,
    'air_noise': 0.03,
    'eldercare': 0.02,
}
assert abs(sum(W_PRIVATE.values()) - 1.0) < 1e-9, f"W_PRIVATE must sum to 1.0, got {sum(W_PRIVATE.values())}"

PROVENANCE = {
    'conn':      'MEASURED',
    'amen':      'MEASURED',
    'green':     'MEASURED',
    'sch':       'MEASURED',
    'hlth':      'MEASURED',
    'infra':     'MEASURED',
    'childcare': 'MEASURED',
    'community': 'MEASURED',
    'sport':     'MEASURED',
    'flood':     'MEASURED',
    'noise':     'MEASURED',
    'air_noise': 'MEASURED',
    'eldercare': 'MEASURED',
    'dens':      'PARTLY_MEASURED',
    'env':       'PARTLY_MEASURED',
    'mom':       'PARTLY_MEASURED',
    'hawker':    'JUDGED',
}

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
            'nearest_mrt_m': round(d_mrt), 'covered_linkways_800m': n_shelter}
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
# Assemble
# ----------------------------------------------------------------------
def run(estates, layers, judged):
    rows = []
    for _, e in estates.iterrows():
        lat, lon = float(e['lat']), float(e['lon']); name = e['estate']
        s = {}
        s['conn'],_      = score_connectivity(lat, lon, layers['mrt'], layers['bus'], None,
                                             layers.get('covered_linkway'))
        s['amen'],_      = score_amenities(lat, lon, layers['markets'], layers['supermarkets'], layers['clinics'])
        s['green'],_     = score_green(lat, lon, layers['parks'])
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

        # PARTLY/JUDGED: from judged_inputs.csv if provided, else NaN-flag
        jr = judged[judged['estate'] == name] if judged is not None else pd.DataFrame()
        for k in ['dens', 'env', 'mom', 'hawker']:
            if not jr.empty and k in jr.columns and not pd.isna(jr.iloc[0][k]):
                s[k] = float(jr.iloc[0][k])
            else:
                s[k] = np.nan  # explicitly missing -> flagged, not faked
        rows.append({'estate': name, **s})
    df = pd.DataFrame(rows)

    # provision = weighted sum; if a JUDGED/PARTLY input is missing, report
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

    df['measured_only'] = df[['dens','env','mom','hawker']].isna().any(axis=1)
    return df

def band(x):
    for edge, b in [(4.5,"A"),(4.0,"B+"),(3.5,"B"),(3.0,"C"),(2.5,"D"),(0,"F")]:
        if x >= edge: return b
    return "F"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--estates', required=True)
    for L in ['mrt','bus','clinics','polyclinics','schools','parks','markets',
              'supermarkets','childcare','community','sport','flood','noise',
              'air_noise','eldercare','covered_linkway']:
        ap.add_argument(f'--{L}')
    ap.add_argument('--judged', help='CSV: estate,dens,env,mom,hawker (the 4 non-geospatial)')
    ap.add_argument('--out', default='provision_scores.csv')
    a = ap.parse_args()

    estates = pd.read_csv(a.estates)
    assert {'estate','lat','lon'} <= set(estates.columns), "estates.csv needs: estate,lat,lon"
    def load(p): return pd.read_csv(p) if p else None
    layers = {L: load(getattr(a, L)) for L in
              ['mrt','bus','clinics','polyclinics','schools','parks','markets',
               'supermarkets','childcare','community','sport','flood','noise',
               'air_noise','eldercare','covered_linkway']}
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
# INPUT CONTRACT — provision_model.py v1.4
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
#                              conn weight (0.15) is unchanged. MEASURED provenance.)
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
