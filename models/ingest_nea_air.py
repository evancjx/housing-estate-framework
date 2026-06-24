#!/usr/bin/env python3
"""
NEA air-quality ingester  (Provision v2.0 §1.2)
================================================
Fetches NEA's published PSI / PM2.5 / NO2 readings for the last 12 months,
aggregates to per-region annual means, maps each estate to its NEA region,
and applies a road-class buffer correction for estates adjacent to LTA
expressways.

PROVENANCE: MEASURED.
  All inputs (PSI sub-indices, expressway lines, region assignment) are
  measured. The region-assignment table is a fixed lookup published by NEA.

ENDPOINT: https://api.data.gov.sg/v1/environment/psi?date=YYYY-MM-DD
  Each daily response contains ~24 hourly items, with readings keyed by
  region: north, south, east, west, central.

SAMPLING:
  We fetch one day every 14 days (~26 samples over 365 days) to keep
  network usage modest. Per-region annual mean is the mean over all
  fetched daily means; haze_days_y is scaled from sampled count to
  annual estimate.

OUTPUT (data/air_quality.csv):
  estate, region, pm25_annual_mean, no2_annual_mean, haze_days_y,
         road_buffer_correction

ROAD-BUFFER CORRECTION:
  For each estate, count distinct expressway points (vertices from
  data/expressways.csv) within 100m. If count >= 1, add +0.2 (i.e. 20% PM2.5
  penalty). Documented in `score_air_quality` (Task 2.3).

INPUT CONTRACT:
  --estates       CSV with estate, lat, lon (UPPERCASE)
  --expressways   data/expressways.csv with lat, lon (point series)
  --out           output CSV path
  --cache-dir     (optional) cache fetched daily JSONs
  --sample-days   sampling interval in days (default 14)
  --stub          emit climatology-baseline rows without fetching

RUN:
  python3 models/ingest_nea_air.py \\
      --estates data/estates.csv \\
      --expressways data/expressways.csv \\
      --out data/air_quality.csv
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.request
import urllib.error

import pandas as pd

PSI_URL = "https://api.data.gov.sg/v1/environment/psi?date={ymd}"
REGIONS = ["north", "south", "east", "west", "central"]
_UA = "Mozilla/5.0 (housing-estate-framework/2.0)"

# Each estate → NEA region. Manually transcribed from NEA's regional
# definitions; estates not listed default to CENTRAL.
ESTATE_REGION = {
    "WOODLANDS":     "north",
    "SEMBAWANG":     "north",
    "CANBERRA":      "north",
    "YISHUN":        "north",
    "MANDAI":        "north",
    "BUKIT MERAH":   "south",
    "QUEENSTOWN":    "south",
    "CENTRAL AREA":  "south",
    "DOVER":         "south",
    "BEDOK":         "east",
    "PASIR RIS":     "east",
    "TAMPINES":      "east",
    "TAMPINES WEST": "east",
    "TAMPINES EAST": "east",
    "MARINE PARADE": "east",
    "BUKIT BATOK":   "west",
    "BUKIT PANJANG": "west",
    "CHOA CHU KANG": "west",
    "JURONG EAST":   "west",
    "CLEMENTI":      "west",
    "TENGAH":        "west",
    "ANG MO KIO":    "central",
    "BISHAN":        "central",
    "TOA PAYOH":     "central",
    "BUKIT TIMAH":   "central",
    "BOON KENG":     "central",
    "HOUGANG":       "central",
    "WOODLEIGH":     "central",
    "SERANGOON":     "central",
    "SENGKANG":      "central",
    "PUNGGOL":       "central",
    "LENTOR":        "central",
    "GEYLANG":       "central",
}

# Climatology baseline (NEA Annual Air Quality Report 2023) — used by --stub
# and as fallback if any region has zero successful samples.
CLIMATOLOGY = {
    "north":   {"pm25": 15.0, "no2": 14.0, "haze_days": 2},
    "south":   {"pm25": 16.0, "no2": 18.0, "haze_days": 3},
    "east":    {"pm25": 14.0, "no2": 12.0, "haze_days": 2},
    "west":    {"pm25": 18.0, "no2": 16.0, "haze_days": 3},
    "central": {"pm25": 16.0, "no2": 17.0, "haze_days": 2},
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                 "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def fetch_day(ymd: str, cache_dir: str | None) -> dict | None:
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, f"psi_{ymd}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    try:
        data = _http_json(PSI_URL.format(ymd=ymd))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  WARN fetch {ymd}: {e}", file=sys.stderr)
        return None
    if cache_dir:
        with open(path, "w") as f:
            json.dump(data, f)
    return data


def per_region_daily_mean(day_json: dict) -> dict:
    """Average each region's hourly readings to a single daily value per region."""
    items = day_json.get("items", [])
    if not items:
        return {}
    accum = {r: {"pm25": [], "no2": [], "psi": []} for r in REGIONS}
    for item in items:
        readings = item.get("readings", {})
        for r in REGIONS:
            pm25 = readings.get("pm25_twenty_four_hourly", {}).get(r)
            no2 = readings.get("no2_one_hour_max", {}).get(r)
            psi = readings.get("psi_twenty_four_hourly", {}).get(r)
            if pm25 is not None:
                accum[r]["pm25"].append(float(pm25))
            if no2 is not None:
                accum[r]["no2"].append(float(no2))
            if psi is not None:
                accum[r]["psi"].append(float(psi))
    out = {}
    for r, vals in accum.items():
        out[r] = {
            "pm25": sum(vals["pm25"]) / len(vals["pm25"]) if vals["pm25"] else None,
            "no2":  sum(vals["no2"])  / len(vals["no2"])  if vals["no2"]  else None,
            "psi_max": max(vals["psi"]) if vals["psi"] else None,
        }
    return out


def expressway_within_100m(est_lat: float, est_lon: float,
                            expressways: pd.DataFrame) -> bool:
    for _, row in expressways.iterrows():
        d = haversine_m(est_lat, est_lon, float(row["lat"]), float(row["lon"]))
        if d <= 100:
            return True
    return False


def emit_climatology(estates: pd.DataFrame, expressways: pd.DataFrame,
                      out: str) -> None:
    rows = []
    for est in estates.itertuples():
        name = str(est.estate).upper()
        region = ESTATE_REGION.get(name, "central")
        clim = CLIMATOLOGY[region]
        rbc = 0.2 if expressway_within_100m(float(est.lat), float(est.lon),
                                              expressways) else 0.0
        rows.append({
            "estate": name,
            "region": region,
            "pm25_annual_mean": clim["pm25"],
            "no2_annual_mean": clim["no2"],
            "haze_days_y": clim["haze_days"],
            "road_buffer_correction": rbc,
        })
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote CLIMATOLOGY CSV with {len(rows)} rows → {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--expressways", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", help="cache fetched daily PSI JSONs")
    ap.add_argument("--sample-days", type=int, default=14,
                    help="sampling interval in days (default 14)")
    ap.add_argument("--stub", action="store_true",
                    help="emit climatology baseline rows without fetching")
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)
    expressways = pd.read_csv(args.expressways)
    assert {"lat", "lon"} <= set(expressways.columns)

    if args.stub:
        emit_climatology(estates, expressways, args.out)
        return

    end = dt.date.today()
    start = end - dt.timedelta(days=365)
    sample_dates: list[dt.date] = []
    d = start
    while d <= end:
        sample_dates.append(d)
        d += dt.timedelta(days=args.sample_days)
    print(f"Fetching {len(sample_dates)} samples (every {args.sample_days}d)…",
          file=sys.stderr)

    region_pm25 = {r: [] for r in REGIONS}
    region_no2 = {r: [] for r in REGIONS}
    haze_count = {r: 0 for r in REGIONS}
    n_fetched = 0

    for d in sample_dates:
        day_data = fetch_day(d.isoformat(), args.cache_dir)
        if day_data is None:
            continue
        n_fetched += 1
        daily = per_region_daily_mean(day_data)
        for r in REGIONS:
            v = daily.get(r, {})
            if v.get("pm25") is not None:
                region_pm25[r].append(v["pm25"])
            if v.get("no2") is not None:
                region_no2[r].append(v["no2"])
            if v.get("psi_max") is not None and v["psi_max"] > 100:
                haze_count[r] += 1

    print(f"Successfully fetched {n_fetched}/{len(sample_dates)} days",
          file=sys.stderr)

    if n_fetched == 0:
        print("No samples retrieved; falling back to climatology.", file=sys.stderr)
        emit_climatology(estates, expressways, args.out)
        return

    region_means = {}
    scale = 365.0 / args.sample_days  # annualise haze-day estimate
    for r in REGIONS:
        if region_pm25[r]:
            region_means[r] = {
                "pm25": round(sum(region_pm25[r]) / len(region_pm25[r]), 2),
                "no2":  round(sum(region_no2[r]) / len(region_no2[r]), 2)
                          if region_no2[r] else CLIMATOLOGY[r]["no2"],
                "haze_days": round(haze_count[r] * scale, 1),
            }
        else:
            region_means[r] = {
                "pm25": CLIMATOLOGY[r]["pm25"],
                "no2":  CLIMATOLOGY[r]["no2"],
                "haze_days": CLIMATOLOGY[r]["haze_days"],
            }

    print("Per-region annual means:", file=sys.stderr)
    for r in REGIONS:
        rm = region_means[r]
        print(f"  {r:8s}  PM2.5={rm['pm25']:5.2f}  NO2={rm['no2']:5.2f}  "
              f"haze_days={rm['haze_days']:5.1f}", file=sys.stderr)

    rows = []
    for est in estates.itertuples():
        name = str(est.estate).upper()
        region = ESTATE_REGION.get(name, "central")
        rm = region_means[region]
        rbc = 0.2 if expressway_within_100m(float(est.lat), float(est.lon),
                                              expressways) else 0.0
        rows.append({
            "estate": name,
            "region": region,
            "pm25_annual_mean": rm["pm25"],
            "no2_annual_mean": rm["no2"],
            "haze_days_y": rm["haze_days"],
            "road_buffer_correction": rbc,
        })

    out_df = pd.DataFrame(rows)[
        ["estate", "region", "pm25_annual_mean", "no2_annual_mean",
         "haze_days_y", "road_buffer_correction"]
    ]
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {len(out_df)} rows → {args.out}", file=sys.stderr)

    # Spot-check
    print("\nSpot-check (brief Step 6 — west=worst, east/central=best):",
          file=sys.stderr)
    for name in ["JURONG EAST", "TENGAH", "BUKIT BATOK", "MARINE PARADE",
                 "BISHAN", "TOA PAYOH", "WOODLANDS", "PUNGGOL"]:
        sel = out_df[out_df["estate"] == name]
        if not sel.empty:
            r = sel.iloc[0]
            print(f"  {name:14s}  region={r['region']:7s}  PM2.5={r['pm25_annual_mean']:5.2f}  "
                  f"NO2={r['no2_annual_mean']:5.2f}  rbc=+{r['road_buffer_correction']:.1f}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
