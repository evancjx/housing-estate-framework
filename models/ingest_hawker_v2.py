#!/usr/bin/env python3
"""
NEA Hawker Centre v2 ingester  (Provision v2.0 §1.3)
=====================================================
Enriches the existing NEA hawker centre point dataset (already ingested
to data/inputs/markets.csv as a Provision §2 input) with per-estate aggregates
needed by score_hawker: count + nearest + stall-total + redundancy.

The richer NEA Hawker Centre v2 schema (NO_OF_STALLS, completion year)
referenced in the audit brief is not exposed by data.gov.sg — the public
GeoJSON layer carries only name/address. We supplement with a small embedded
stall-count lookup for the ~30 largest centres (NEA's published top list)
and default the remainder to 40 stalls (NEA's mean for non-flagship sites).

PROVENANCE: PARTLY_MEASURED.
  count / distance / redundancy are MEASURED (from data.gov.sg geometry).
  total_stalls_800m is APPROXIMATED: known overrides + default 40/centre.
  oldest_completion_y is omitted (NEA does not publish a clean dataset).

OUTPUT (data/inputs/hawker_v2.csv):
  estate, n_hawker_centres_800m, total_stalls_800m, nearest_hawker_m,
         has_redundancy_dayoff

INPUT CONTRACT:
  --estates    CSV with estate, lat, lon (UPPERCASE)
  --markets    data/inputs/markets.csv (existing NEA hawker centre points)
  --out        output CSV path

RUN:
  python3 models/ingest_hawker_v2.py \\
      --estates data/inputs/estates.csv \\
      --markets data/inputs/markets.csv \\
      --out data/inputs/hawker_v2.csv
"""
import argparse
import math
import sys

import pandas as pd

# Hand-curated stall counts for major NEA hawker centres (NEA published
# directory + Wikipedia cross-ref). Keyed by lowercase name-substring.
STALL_OVERRIDES = {
    "chinatown complex":    287,
    "newton food":          83,
    "maxwell food":         100,
    "tiong bahru market":   83,
    "old airport road":     150,
    "amoy street":          72,
    "lau pa sat":           120,   # private but listed
    "people's park complex":62,
    "tekka market":         71,
    "ghim moh":             56,
    "ang mo kio 226":       70,
    "bedok 207":            70,
    "bukit timah market":   77,
    "geylang serai":        81,
    "marsiling":            64,
    "telok blangah crescent": 60,
    "berseh food":          55,
    "block 22 toa payoh":   70,
    "havelock road food":   70,
    "hong lim":             80,
    "kovan 209":            65,
    "kovan 210":            65,
    "pek kio":              70,
    "redhill":              60,
    "serangoon garden":     55,
    "toa payoh lor 1":      60,
    "yuhua market":         70,
    "marine parade":        62,
    "marine terrace":       60,
    "blk 51 old airport":  150,
    "alexandra village":    60,
    "albert centre":        70,
    "bukit merah view":     60,
    "clementi 448":         55,
    "yishun park":          40,
    "ci yuan":              40,
    "fengshan":             40,
    "kampung admiralty":    40,
    "pasir ris central":    40,
    "anchorvale village":   40,
    "our tampines hub":     40,
}
DEFAULT_STALLS_PER_CENTRE = 40


def lookup_stalls(name: str) -> int:
    n = (name or "").lower()
    for needle, count in STALL_OVERRIDES.items():
        if needle in n:
            return count
    return DEFAULT_STALLS_PER_CENTRE


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--markets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)
    markets = pd.read_csv(args.markets)
    assert {"lat", "lon", "name"} <= set(markets.columns)

    # Pre-compute per-centre stall count
    markets = markets.copy()
    markets["stalls"] = markets["name"].apply(lookup_stalls)

    n_overrides = sum(1 for n in markets["name"]
                      if any(k in (n or "").lower() for k in STALL_OVERRIDES))
    print(f"Loaded {len(markets)} hawker centres, "
          f"{n_overrides} matched embedded stall-count overrides "
          f"(rest default to {DEFAULT_STALLS_PER_CENTRE})", file=sys.stderr)

    rows = []
    for est in estates.itertuples():
        elat, elon = float(est.lat), float(est.lon)
        n_800 = 0
        stalls_800 = 0
        nearest = float("inf")
        for _, m in markets.iterrows():
            d = haversine_m(elat, elon, float(m["lat"]), float(m["lon"]))
            if d < nearest:
                nearest = d
            if d <= 800:
                n_800 += 1
                stalls_800 += int(m["stalls"])
        rows.append({
            "estate": str(est.estate).upper(),
            "n_hawker_centres_800m": n_800,
            "total_stalls_800m": stalls_800,
            "nearest_hawker_m": round(nearest, 1) if not math.isinf(nearest) else -1.0,
            "has_redundancy_dayoff": n_800 >= 2,
        })

    out_df = pd.DataFrame(rows)[
        ["estate", "n_hawker_centres_800m", "total_stalls_800m",
         "nearest_hawker_m", "has_redundancy_dayoff"]
    ]
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {len(out_df)} rows → {args.out}", file=sys.stderr)

    # Spot-check (brief Step 4): CENTRAL AREA / TOA PAYOH should be high;
    # LENTOR / TENGAH should be low.
    print("\nSpot-check:", file=sys.stderr)
    for name in ["CENTRAL AREA", "TOA PAYOH", "BUKIT MERAH", "GEYLANG",
                 "ANG MO KIO", "BEDOK", "MARINE PARADE",
                 "TENGAH", "LENTOR", "CANBERRA", "PUNGGOL"]:
        sel = out_df[out_df["estate"] == name]
        if not sel.empty:
            r = sel.iloc[0]
            print(f"  {name:15s}  n_800={r['n_hawker_centres_800m']:2d}  "
                  f"stalls={r['total_stalls_800m']:4d}  "
                  f"nearest={r['nearest_hawker_m']:7.1f}m  "
                  f"redundancy={r['has_redundancy_dayoff']}", file=sys.stderr)


if __name__ == "__main__":
    main()
