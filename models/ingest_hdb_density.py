#!/usr/bin/env python3
"""
HDB Property Information ingester  (Provision v2.0 §1.4)
=========================================================
Pulls the block-level HDB Property Information dataset, aggregates to per-
estate density metrics, and emits the data needed by score_dens to flip
PARTLY_MEASURED → MEASURED.

PROVENANCE: PARTLY_MEASURED.
  Dwelling counts + block ages are MEASURED (HDB Property Info).
  area_ha is APPROXIMATED: each block assumed 0.5 ha (brief Step 3
  default). HDB precincts are typically ~0.5 ha per 8-block superblock;
  using 0.5/block over-estimates area but matches the brief's stated
  baseline. OneMap building polygons would be a true MEASURED area, but
  that theme requires an auth token.

DATASET:
  d_17f5382f26140b1fdae0ba2ef6239d2f (HDB Property Information, block-level)
  Schema: blk_no, street, max_floor_lvl, year_completed, residential,
          commercial, market_hawker, miscellaneous, multistorey_carpark,
          precinct_pavilion, bldg_contract_town, total_dwelling_units, …

OUTPUT (data/hdb_density.csv):
  estate, total_dwelling_units, residents_per_net_hectare,
         units_per_gross_hectare, n_blocks, mean_storey,
         oldest_block_year, newest_block_year

ASSUMPTIONS:
  - household size = 3.0 (Singapore HDB average per SingStat 2023).
  - per-block footprint = 0.05 ha (proxy; documented above).
  - private/landed dwellings excluded — this is HDB density, not overall.

ALIASING (estate → HDB town):
  CANBERRA → SEMBAWANG  (Canberra BTOs share SB town code)
  BOON KENG / KALLANG → KWN town code directly
  WOODLEIGH → TOA PAYOH  (Bidadari/Woodleigh is under TP)
  DOVER → QUEENSTOWN
  TAMPINES WEST/EAST → TAMPINES
  LENTOR → ANG MO KIO  (private; proxy)
  TENGAH → TG town code directly
  Estates with NO mapping (e.g. PUNGGOL has its own PG code) use direct match.

INPUT CONTRACT:
  --estates  CSV with estate, lat, lon (UPPERCASE)
  --out      output CSV path
  --cache-dir  (optional) cache fetched CSV

RUN:
  python3 models/ingest_hdb_density.py \\
      --estates data/estates.csv \\
      --out data/hdb_density.csv
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.request
import urllib.error

import pandas as pd

from aliases import ESTATE_TOWN_ALIAS

DATASET_ID = "d_17f5382f26140b1fdae0ba2ef6239d2f"
POLL_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{ds}/poll-download"
_UA = "Mozilla/5.0 (housing-estate-framework/2.0)"

HOUSEHOLD_SIZE = 3.0
HA_PER_BLOCK = 0.5   # superblock-precinct footprint proxy per brief (8 blocks per ~0.5 ha precinct)

# 3-letter HDB town code → canonical estate name (estates.csv UPPERCASE)
TOWN_TO_ESTATE = {
    "AMK": "ANG MO KIO",
    "BB":  "BUKIT BATOK",
    "BD":  "BEDOK",
    "BH":  "BISHAN",
    "BM":  "BUKIT MERAH",
    "BP":  "BUKIT PANJANG",
    "BT":  "BUKIT TIMAH",
    "CCK": "CHOA CHU KANG",
    "CL":  "CLEMENTI",
    "CT":  "CENTRAL AREA",
    "GL":  "GEYLANG",
    "HG":  "HOUGANG",
    "JE":  "JURONG EAST",
    "JW":  "JURONG WEST",
    "KWN": ("BOON KENG", "KALLANG"),
    "MP":  "MARINE PARADE",
    "PG":  "PUNGGOL",
    "PRC": "PASIR RIS",
    "QT":  "QUEENSTOWN",
    "SB":  "SEMBAWANG",
    "SGN": "SERANGOON",
    "SK":  "SENGKANG",
    "TAP": "TAMPINES",
    "TG":  "TENGAH",
    "TP":  "TOA PAYOH",
    "WL":  "WOODLANDS",
    "YS":  "YISHUN",
}

# Estate→HDB-town alias is single-sourced in models/aliases.py (ESTATE_TOWN_ALIAS).
# When an estates.csv estate has no direct HDB town code, it inherits that town's density.
# Do NOT re-introduce a local copy — a stale local map here dropped HOLLAND VILLAGE→QUEENSTOWN,
# leaving Holland Village with zero density (CLAUDE.md alias single-sourcing invariant).


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                 "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def fetch_csv(cache_dir: str | None) -> str:
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{DATASET_ID}.csv")
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                return f.read()
    print(f"Fetching HDB Property Information ({DATASET_ID})…", file=sys.stderr)
    poll = _http_json(POLL_URL.format(ds=DATASET_ID))
    csv_url = poll["data"]["url"]
    raw = urllib.request.urlopen(
        urllib.request.Request(csv_url, headers={"User-Agent": _UA}),
        timeout=120
    ).read().decode("utf-8")
    print(f"  {len(raw)} bytes", file=sys.stderr)
    if cache_dir:
        with open(cache_path, "w") as f:
            f.write(raw)
    return raw


def aggregate_by_estate(csv_text: str) -> dict:
    """Aggregate block rows → per-canonical-estate metrics."""
    rdr = csv.DictReader(io.StringIO(csv_text))
    agg: dict[str, dict] = {}
    skipped_codes = set()
    for row in rdr:
        if row.get("residential", "").upper() != "Y":
            continue   # skip non-residential blocks (multistorey carpark only, etc.)
        town = (row.get("bldg_contract_town") or "").strip()
        estates = TOWN_TO_ESTATE.get(town)
        if estates is None:
            skipped_codes.add(town)
            continue
        if isinstance(estates, str):
            estates = (estates,)
        try:
            dus = int(row.get("total_dwelling_units") or 0)
            year = int(row.get("year_completed") or 0)
            storey = int(row.get("max_floor_lvl") or 0)
        except ValueError:
            continue
        for estate in estates:
            a = agg.setdefault(estate, {
                "dus": 0, "blocks": 0, "storeys": [], "years": [],
            })
            a["dus"] += dus
            a["blocks"] += 1
            if storey > 0:
                a["storeys"].append(storey)
            if 1960 <= year <= 2030:
                a["years"].append(year)
    if skipped_codes:
        print(f"  Skipped unmapped town codes: {sorted(skipped_codes)}",
              file=sys.stderr)
    return agg


def metrics_for(a: dict) -> dict:
    """Convert aggregate → output row fields."""
    blocks = a["blocks"]
    area_ha = blocks * HA_PER_BLOCK
    rphn = (a["dus"] * HOUSEHOLD_SIZE) / area_ha if area_ha > 0 else 0
    return {
        "total_dwelling_units": a["dus"],
        "residents_per_net_hectare": round(rphn, 1),
        "units_per_gross_hectare": round(a["dus"] / area_ha, 1) if area_ha > 0 else 0,
        "n_blocks": blocks,
        "mean_storey": round(sum(a["storeys"]) / len(a["storeys"]), 1)
                          if a["storeys"] else 0,
        "oldest_block_year": min(a["years"]) if a["years"] else 0,
        "newest_block_year": max(a["years"]) if a["years"] else 0,
    }


def empty_metrics() -> dict:
    return {
        "total_dwelling_units": 0,
        "residents_per_net_hectare": 0.0,
        "units_per_gross_hectare": 0.0,
        "n_blocks": 0,
        "mean_storey": 0,
        "oldest_block_year": 0,
        "newest_block_year": 0,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", help="cache fetched CSV")
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)

    csv_text = fetch_csv(args.cache_dir)
    by_estate = aggregate_by_estate(csv_text)
    print(f"Aggregated {len(by_estate)} estates "
          f"({sum(a['blocks'] for a in by_estate.values())} blocks total)",
          file=sys.stderr)

    rows = []
    for est in estates.itertuples():
        name = str(est.estate).upper()
        # Try direct first
        a = by_estate.get(name)
        # Then alias (single-sourced estate→town map)
        if a is None and name in ESTATE_TOWN_ALIAS:
            a = by_estate.get(ESTATE_TOWN_ALIAS[name])
        m = metrics_for(a) if a else empty_metrics()
        m["estate"] = name
        rows.append(m)

    out_df = pd.DataFrame(rows)[
        ["estate", "total_dwelling_units", "residents_per_net_hectare",
         "units_per_gross_hectare", "n_blocks", "mean_storey",
         "oldest_block_year", "newest_block_year"]
    ]
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {len(out_df)} rows → {args.out}", file=sys.stderr)

    # Spot-check (brief Step 4)
    print("\nSpot-check:", file=sys.stderr)
    for name in ["CENTRAL AREA", "BUKIT MERAH", "GEYLANG", "ANG MO KIO",
                 "TAMPINES", "PUNGGOL", "SENGKANG",
                 "TENGAH", "LENTOR", "CANBERRA", "BUKIT TIMAH"]:
        sel = out_df[out_df["estate"] == name]
        if not sel.empty:
            r = sel.iloc[0]
            print(f"  {name:15s}  DUs={int(r['total_dwelling_units']):6d}  "
                  f"blocks={int(r['n_blocks']):4d}  "
                  f"rphn={r['residents_per_net_hectare']:6.1f}  "
                  f"oldest={int(r['oldest_block_year']):4d}", file=sys.stderr)


if __name__ == "__main__":
    main()
