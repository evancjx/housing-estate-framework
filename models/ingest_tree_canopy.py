#!/usr/bin/env python3
"""
NParks tree-canopy + MSS temperature ingester  (Provision v2.0 §1.5)
=====================================================================
Builds per-estate canopy/UHI metrics for score_env (UHI + canopy refactor).

PROVENANCE: PARTLY_MEASURED.
  - annual_mean_temp_c / uhi_delta_c are MEASURED from MSS air-temperature
    samples (12 monthly readings via data.gov.sg).
  - canopy_cover_pct / ndvi_proxy are APPROXIMATED: the NParks full
    tree-census layer is gated, and OSM landuse=forest polygons are sparse
    over Singapore HDB estates. We use the existing data/inputs/parks.csv layer
    as a green-area proxy: % of 1km circle around estate centroid that
    falls within 250m of any park point. This systematically under-counts
    street-tree canopy (which NParks does not publish), so the figure is a
    relative comparator only, not an absolute %.

OUTPUT (data/inputs/tree_canopy.csv):
  estate, ndvi_proxy, canopy_cover_pct, mss_station,
         annual_mean_temp_c, uhi_delta_c

DATA SOURCES:
  - MSS: api.data.gov.sg/v1/environment/air-temperature?date=YYYY-MM-DD
    (15 stations; we sample 12 monthly noon readings and average).
  - Parks: data/inputs/parks.csv (already ingested NParks layer).

REFERENCE STATION: Changi-area S24 (Upper Changi Road North) — coastal,
  typically the coolest. uhi_delta_c = estate_mean - changi_mean.

INPUT CONTRACT:
  --estates  CSV with estate, lat, lon (UPPERCASE)
  --parks    NParks parks.csv (lat, lon, name)
  --out      output CSV path
  --cache-dir  (optional) cache fetched MSS responses
  --mss-fallback  (optional) existing tree_canopy.csv to preserve MSS fields

RUN:
  python3 models/ingest_tree_canopy.py \\
      --estates data/inputs/estates.csv \\
      --parks data/inputs/parks.csv \\
      --out data/inputs/tree_canopy.csv
"""
import argparse
import json
import math
import os
import sys
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

MSS_URL = "https://api.data.gov.sg/v1/environment/air-temperature?date={d}"
_UA = "Mozilla/5.0 (housing-estate-framework/2.0)"
REFERENCE_STATION = "S24"   # Upper Changi Road North (coastal cool baseline)
N_MONTHS = 12
GREEN_RADIUS_M = 250        # park-point influence radius (each point counts a circle)
SAMPLE_RADIUS_M = 1000      # canopy sample circle around estate centroid


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def monthly_sample_dates(n_months=12):
    """Return list of YYYY-MM-15 strings, working backward from today."""
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(n_months):
        out.append(f"{y:04d}-{m:02d}-15")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    return out


def fetch_station_means(cache_dir):
    """Sample MSS noon readings monthly; return {station_id: (lat, lon, mean_c)}."""
    samples = {}    # station_id -> [readings]
    stations = {}   # station_id -> (lat, lon, name)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    for d in monthly_sample_dates(N_MONTHS):
        cache = os.path.join(cache_dir, f"mss_{d}.json") if cache_dir else None
        try:
            if cache and os.path.exists(cache):
                with open(cache) as f:
                    payload = json.load(f)
            else:
                print(f"  MSS {d}…", file=sys.stderr)
                payload = _http_json(MSS_URL.format(d=d))
                if cache:
                    with open(cache, "w") as f:
                        json.dump(payload, f)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  MSS {d} failed: {e}", file=sys.stderr)
            continue

        for s in payload.get("metadata", {}).get("stations", []):
            loc = s.get("location", {})
            stations[s["id"]] = (loc.get("latitude"), loc.get("longitude"),
                                  s.get("name"))

        items = payload.get("items", []) or []
        if not items:
            continue
        # Average ALL readings across the day per station — captures the
        # daily-mean signal (annual UHI is a daily-mean property; noon-only
        # samples invert because Changi sea-breeze sites are warmest at noon
        # while urban canyons peak after sunset).
        per_day = {}   # sid -> [vals]
        for it in items:
            for r in it.get("readings", []):
                per_day.setdefault(r["station_id"], []).append(r["value"])
        for sid, vals in per_day.items():
            if vals:
                samples.setdefault(sid, []).append(sum(vals) / len(vals))

    result = {}
    for sid, vals in samples.items():
        if not vals or sid not in stations:
            continue
        lat, lon, name = stations[sid]
        if lat is None or lon is None:
            continue
        result[sid] = (lat, lon, name, sum(vals) / len(vals))
    return result


def load_mss_fallback(path):
    """Load previously committed MSS fields for offline pipeline runs."""
    path = Path(path)
    if not path.exists():
        return {}

    df = pd.read_csv(path)
    required = {"estate", "mss_station", "annual_mean_temp_c", "uhi_delta_c"}
    if not required <= set(df.columns):
        return {}

    fallback = {}
    for _, row in df.iterrows():
        if pd.isna(row["annual_mean_temp_c"]) or pd.isna(row["uhi_delta_c"]):
            continue
        estate = str(row["estate"]).upper().strip()
        station = "" if pd.isna(row["mss_station"]) else str(row["mss_station"])
        fallback[estate] = {
            "mss_station": station,
            "annual_mean_temp_c": float(row["annual_mean_temp_c"]),
            "uhi_delta_c": float(row["uhi_delta_c"]),
        }
    return fallback


def nearest_station(estate_lat, estate_lon, stations):
    best_id, best_d = None, float("inf")
    for sid, (lat, lon, _name, _mean) in stations.items():
        d = haversine_m(estate_lat, estate_lon, lat, lon)
        if d < best_d:
            best_d, best_id = d, sid
    return best_id, best_d


def canopy_proxy(estate_lat, estate_lon, parks_df, n_grid=21):
    """Sample an n_grid × n_grid lattice inside the SAMPLE_RADIUS_M circle;
    count cells within GREEN_RADIUS_M of any park point.
    Returns (ndvi_proxy ∈ [0,1], cover_pct)."""
    # ~1 deg ≈ 111km; build a grid centered on estate
    deg_per_m_lat = 1 / 111_000
    deg_per_m_lon = 1 / (111_000 * math.cos(math.radians(estate_lat)))
    half = SAMPLE_RADIUS_M
    in_circle = 0
    green = 0
    parks = parks_df[["lat", "lon"]].to_numpy()
    for i in range(n_grid):
        for j in range(n_grid):
            dy = (i - n_grid // 2) * (2 * half / (n_grid - 1))  # metres N
            dx = (j - n_grid // 2) * (2 * half / (n_grid - 1))  # metres E
            if dx * dx + dy * dy > half * half:
                continue
            in_circle += 1
            lat = estate_lat + dy * deg_per_m_lat
            lon = estate_lon + dx * deg_per_m_lon
            for plat, plon in parks:
                if haversine_m(lat, lon, plat, plon) <= GREEN_RADIUS_M:
                    green += 1
                    break
    cover = green / in_circle if in_circle else 0.0
    return round(cover, 3), round(100 * cover, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--parks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", help="cache MSS responses")
    ap.add_argument(
        "--mss-fallback",
        help="existing tree_canopy.csv whose MSS fields are preserved if station fetches fail",
    )
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    parks = pd.read_csv(args.parks)
    assert {"estate", "lat", "lon"} <= set(estates.columns)
    assert {"lat", "lon"} <= set(parks.columns)

    print(f"Sampling {N_MONTHS} monthly MSS readings…", file=sys.stderr)
    stations = fetch_station_means(args.cache_dir)
    print(f"  {len(stations)} stations with valid means", file=sys.stderr)

    use_mss_fallback = not stations
    mss_fallback = {}
    if use_mss_fallback:
        fallback_path = args.mss_fallback or args.out
        mss_fallback = load_mss_fallback(fallback_path)
        estate_names = [str(e).upper().strip() for e in estates["estate"]]
        missing = [e for e in estate_names if e not in mss_fallback]
        if missing:
            preview = ", ".join(missing[:5])
            suffix = "..." if len(missing) > 5 else ""
            sys.exit(
                "ERROR: no MSS station data retrieved and fallback "
                f"{fallback_path} lacks usable rows for: {preview}{suffix}"
            )
        print(
            f"WARNING: no MSS station data; preserving MSS fields from {fallback_path}",
            file=sys.stderr,
        )
    elif REFERENCE_STATION not in stations:
        print(f"WARNING: reference station {REFERENCE_STATION} missing; "
              f"using min-mean station as cool baseline", file=sys.stderr)
        ref_mean = min(m for _, _, _, m in stations.values())
    else:
        ref_mean = stations[REFERENCE_STATION][3]
    if not use_mss_fallback:
        print(f"  reference mean = {ref_mean:.2f}°C", file=sys.stderr)

    rows = []
    for est in estates.itertuples():
        estate = str(est.estate).upper().strip()
        elat, elon = float(est.lat), float(est.lon)
        cover, pct = canopy_proxy(elat, elon, parks)
        if use_mss_fallback:
            cached = mss_fallback[estate]
            sid = cached["mss_station"]
            mean_c = cached["annual_mean_temp_c"]
            uhi_delta = cached["uhi_delta_c"]
        else:
            sid, _ = nearest_station(elat, elon, stations)
            mean_c = stations[sid][3] if sid else 0.0
            uhi_delta = mean_c - ref_mean
        rows.append({
            "estate": estate,
            "ndvi_proxy": cover,
            "canopy_cover_pct": pct,
            "mss_station": sid or "",
            "annual_mean_temp_c": round(mean_c, 2),
            "uhi_delta_c": round(uhi_delta, 2),
        })

    out_df = pd.DataFrame(rows)[
        ["estate", "ndvi_proxy", "canopy_cover_pct",
         "mss_station", "annual_mean_temp_c", "uhi_delta_c"]
    ]
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {len(out_df)} rows → {args.out}", file=sys.stderr)

    # Spot-check (brief Step 5): GEYLANG / TOA PAYOH +UHI;
    # MARINE PARADE / BUKIT TIMAH near-zero or negative.
    print("\nSpot-check:", file=sys.stderr)
    for name in ["CENTRAL AREA", "GEYLANG", "TOA PAYOH", "BUKIT MERAH",
                 "ANG MO KIO", "MARINE PARADE", "BUKIT TIMAH",
                 "WOODLANDS", "TENGAH", "PUNGGOL"]:
        sel = out_df[out_df["estate"] == name]
        if not sel.empty:
            r = sel.iloc[0]
            print(f"  {name:15s}  canopy={r['canopy_cover_pct']:5.1f}%  "
                  f"sta={r['mss_station']:5s}  "
                  f"T={r['annual_mean_temp_c']:5.2f}°C  "
                  f"ΔUHI={r['uhi_delta_c']:+.2f}°C", file=sys.stderr)


if __name__ == "__main__":
    main()
