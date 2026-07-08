#!/usr/bin/env python3
"""
JTC industrial-land ingester  (Provision v2.0 §1.1)
====================================================
Computes per-estate industrial-proximity metrics for the new
`jtc_industrial` component, using the published JTC industrial-estates
map (https://www.jtc.gov.sg/find-space) as the canonical zone inventory.

PROVENANCE: PARTLY_MEASURED.
  Zone centroids + intensity tags are sourced from JTC's published
  industrial estate map (a stable public list, refreshed annually). The
  per-estate distances + area-shares are MEASURED outputs of that input.
  Promotion to MEASURED would require the URA Master Plan B1/B2/B3 zoning
  GeoJSON — which is not directly downloadable from data.gov.sg.

OUTPUT (data/inputs/jtc_industrial.csv):
  estate, nearest_industrial_m, area_share_800m, area_share_1500m,
         area_share_3km, intensity_tag

  intensity_tag ∈ {HEAVY, LIGHT, NONE}
    HEAVY  = any HEAVY-tagged zone within 1500m
    LIGHT  = otherwise, any LIGHT-tagged zone within 1500m
    NONE   = no industrial zone within 1500m

NOTES:
  Each zone is a (lat, lon, name, intensity, footprint_m2) tuple. Footprint
  values are the rough JTC-published parcel sizes (km² × 1e6); we use them
  to weight `area_share_*` (a fraction of disc area πr²) so that estates
  near large heavy-industrial zones (Jurong Island, Tuas) score high while
  estates near small light-industrial pockets (Defu, Tai Seng) score lower.

INPUT CONTRACT:
  --estates  CSV with columns: estate, lat, lon  (UPPERCASE estate names)
  --out      output CSV path
  --stub     emit sentinel rows (-1, UNKNOWN) without computing

RUN:
  python3 models/ingest_jtc_industrial.py \\
      --estates data/inputs/estates.csv \\
      --out data/inputs/jtc_industrial.csv
"""
import argparse
import math
import sys

import pandas as pd

# JTC industrial-estates inventory. Manually transcribed from JTC's "Find Space"
# directory (https://www.jtc.gov.sg/find-space) cross-referenced with URA
# Master Plan 2019 land-use map. Each tuple: (name, lat, lon, intensity,
# footprint_m2). HEAVY = B2/B3-equivalent (general / special industry);
# LIGHT = B1-equivalent (light industry, business park, wafer fab).
JTC_ZONES = [
    # ── HEAVY (B2/B3 equivalents) ──
    ("Jurong Island",            1.2650, 103.7000, "HEAVY", 32_000_000),
    ("Tuas South",               1.2620, 103.6360, "HEAVY", 11_000_000),
    ("Tuas West",                1.3192, 103.6390, "HEAVY",  8_000_000),
    ("Tuas Biomedical Park",     1.3023, 103.6489, "HEAVY",  3_000_000),
    ("Tuas North",               1.3411, 103.6489, "HEAVY",  4_000_000),
    ("Pioneer",                  1.3266, 103.6730, "HEAVY",  6_000_000),
    ("Joo Koon",                 1.3275, 103.6750, "HEAVY",  4_500_000),
    ("Benoi",                    1.3220, 103.6800, "HEAVY",  3_200_000),
    ("Boon Lay (Industrial)",    1.3370, 103.6920, "HEAVY",  2_500_000),
    ("Jurong Port",              1.3140, 103.7250, "HEAVY",  2_800_000),
    ("Sungei Kadut",             1.4180, 103.7530, "HEAVY",  3_700_000),
    ("Senoko Industrial",        1.4419, 103.7866, "HEAVY",  4_200_000),
    ("Kranji Industrial",        1.4302, 103.7421, "HEAVY",  2_400_000),
    ("Pasir Panjang Terminal",   1.2733, 103.7800, "HEAVY",  3_000_000),
    ("Pulau Bukom",              1.2306, 103.7700, "HEAVY",  5_000_000),
    # ── LIGHT (B1 equivalents, business parks, wafer fabs) ──
    ("Ang Mo Kio Industrial Pk", 1.3672, 103.8489, "LIGHT",  1_900_000),
    ("Yishun Industrial Park",   1.4395, 103.8261, "LIGHT",  1_600_000),
    ("Woodlands East Industrial",1.4324, 103.7984, "LIGHT",  1_200_000),
    ("Woodlands Wafer Fab Park", 1.4395, 103.7826, "LIGHT",  1_000_000),
    ("Tampines Industrial Pk",   1.3678, 103.9325, "LIGHT",  1_400_000),
    ("Tampines Wafer Fab Park",  1.3711, 103.9483, "LIGHT",  1_500_000),
    ("Changi Business Park",     1.3340, 103.9620, "LIGHT",  1_100_000),
    ("Loyang Industrial",        1.3700, 103.9710, "LIGHT",  1_300_000),
    ("Seletar Aerospace Park",   1.4181, 103.8675, "LIGHT",  3_300_000),
    ("Defu Industrial",          1.3520, 103.8800, "LIGHT",  1_500_000),
    ("Tai Seng Industrial",      1.3370, 103.8870, "LIGHT",    800_000),
    ("Kallang Way",              1.3320, 103.8770, "LIGHT",  1_000_000),
    ("Kallang Bahru",            1.3239, 103.8636, "LIGHT",    700_000),
    ("Geylang Bahru Industrial", 1.3210, 103.8722, "LIGHT",    500_000),
    ("Bedok Food City",          1.3271, 103.9241, "LIGHT",    900_000),
    ("Toa Payoh North Indl",     1.3403, 103.8556, "LIGHT",    600_000),
    ("Bukit Batok Industrial",   1.3460, 103.7490, "LIGHT",  1_000_000),
    ("Jurong East Light Indl",   1.3360, 103.7460, "LIGHT",    800_000),
    ("Bukit Merah Industrial",   1.2790, 103.8230, "LIGHT",    500_000),
    ("Bukit Timah (Sime) Indl",  1.3310, 103.7960, "LIGHT",    400_000),
    ("Punggol Industrial",       1.4111, 103.9120, "LIGHT",    300_000),
    ("Sengkang West Industrial", 1.3984, 103.8731, "LIGHT",    400_000),
    ("Hougang Industrial",       1.3700, 103.8836, "LIGHT",    400_000),
    ("Choa Chu Kang Industrial", 1.3886, 103.7445, "LIGHT",    500_000),
    ("Bukit Panjang Light Indl", 1.3833, 103.7625, "LIGHT",    250_000),
]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def per_estate_metrics(est_lat: float, est_lon: float) -> dict:
    nearest = float("inf")
    area_800 = 0.0
    area_1500 = 0.0
    area_3000 = 0.0
    has_heavy_1500 = False
    has_light_1500 = False
    for name, zlat, zlon, intensity, footprint in JTC_ZONES:
        d = haversine_m(est_lat, est_lon, zlat, zlon)
        if d < nearest:
            nearest = d
        if d <= 800:
            area_800 += footprint
        if d <= 1500:
            area_1500 += footprint
            if intensity == "HEAVY":
                has_heavy_1500 = True
            else:
                has_light_1500 = True
        if d <= 3000:
            area_3000 += footprint
    if math.isinf(nearest):
        nearest_out, tag = -1.0, "NONE"
    elif has_heavy_1500:
        nearest_out, tag = nearest, "HEAVY"
    elif has_light_1500:
        nearest_out, tag = nearest, "LIGHT"
    else:
        nearest_out, tag = nearest, "NONE"

    def share(area_m2: float, radius_m: float) -> float:
        disc = math.pi * radius_m * radius_m
        return area_m2 / disc if disc > 0 else 0.0

    return {
        "nearest_industrial_m": round(nearest_out, 1),
        "area_share_800m": round(share(area_800, 800), 4),
        "area_share_1500m": round(share(area_1500, 1500), 4),
        "area_share_3km": round(share(area_3000, 3000), 4),
        "intensity_tag": tag,
    }


def emit_stub(estates: pd.DataFrame, out: str) -> None:
    rows = [{
        "estate": str(r.estate).upper(),
        "nearest_industrial_m": -1.0,
        "area_share_800m": 0.0,
        "area_share_1500m": 0.0,
        "area_share_3km": 0.0,
        "intensity_tag": "UNKNOWN",
    } for r in estates.itertuples()]
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote STUB CSV with {len(rows)} rows → {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stub", action="store_true",
                    help="emit sentinel rows without computing")
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)

    if args.stub:
        emit_stub(estates, args.out)
        return

    zone_counts = {"HEAVY": 0, "LIGHT": 0}
    for _, _, _, intensity, _ in JTC_ZONES:
        zone_counts[intensity] += 1
    print(f"Loaded {len(JTC_ZONES)} JTC zones: "
          f"{zone_counts['HEAVY']} HEAVY, {zone_counts['LIGHT']} LIGHT",
          file=sys.stderr)

    rows = []
    for est in estates.itertuples():
        m = per_estate_metrics(float(est.lat), float(est.lon))
        m["estate"] = str(est.estate).upper()
        rows.append(m)

    out_df = pd.DataFrame(rows)[
        ["estate", "nearest_industrial_m", "area_share_800m",
         "area_share_1500m", "area_share_3km", "intensity_tag"]
    ]
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {len(out_df)} rows → {args.out}", file=sys.stderr)

    # Spot-check (brief Step 6): expect HEAVY near JURONG EAST / BUKIT BATOK
    # west-side estates and NONE for MARINE PARADE, BUKIT TIMAH.
    print("\nSpot-check:", file=sys.stderr)
    for name in ["JURONG EAST", "BUKIT BATOK", "WOODLANDS", "SEMBAWANG",
                 "PASIR RIS", "TAMPINES", "MARINE PARADE", "BUKIT TIMAH",
                 "QUEENSTOWN", "BEDOK"]:
        sel = out_df[out_df["estate"] == name]
        if not sel.empty:
            r = sel.iloc[0]
            print(f"  {name:18s}  nearest={r['nearest_industrial_m']:7.1f}m  "
                  f"share_1500m={r['area_share_1500m']:.3f}  tag={r['intensity_tag']}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
