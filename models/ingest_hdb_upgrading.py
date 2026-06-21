#!/usr/bin/env python3
"""
HDB upgrading-programme ingester  (Provision §2a, audit-driven)
================================================================
Fetches HDB Neighbourhood Renewal Programme (NRP) and Lift Upgrading
Programme (LUP) GeoJSONs from data.gov.sg, assigns each polygon to its
nearest estate, aggregates to one pipeline item per (estate, programme,
certainty), and merges the result into pipeline_data.json.

Implements audit §2a — replaces the JUDGED HDB-side momentum signal with
a MEASURED one drawn directly from the HDB upgrading-programme block
lists. Private-side momentum (en-bloc, new launches) is unaffected and
remains JUDGED, so the final `mom` PROVENANCE is PARTLY_MEASURED.

DATASETS:
  NRP: d_156a38dc024d2b20a6c1d0c0179e797c (103 precincts)
  LUP: d_9b5886a025c8db1192a8fada42bd4330 (41 block-clusters)

OUTPUT ITEM SHAPE (matches pipeline_data.json schema):
  {
    "description":         "NRP — N precincts in <ESTATE>",
    "benefiting_estates":  ["<ESTATE>"],
    "type":                "NRP" | "LUP",
    "significance":        "HIGH" | "MEDIUM" | "LOW",   # scaled by count
    "certainty":           "CONFIRMED" | "PLANNED",     # U/C → CONFIRMED
    "expected_year":       int,                         # mode of U/C years; 2030 default for Proposed
    "notes":               "NRP confirmed (N sites): NAME1; NAME2; …"
  }

SIGNIFICANCE SCALING (count of precincts/blocks per estate, per certainty):
  NRP: >=6 → HIGH, >=3 → MEDIUM, else LOW
  LUP: >=8 → HIGH, >=4 → MEDIUM, else LOW

RUN:
  python3 models/ingest_hdb_upgrading.py \\
      --estates data/estates.csv \\
      --pipeline data/pipeline_data.json \\
      --out data/pipeline_data.json
  python3 models/momentum_model.py \\
      --pipeline data/pipeline_data.json \\
      --judged data/judged_inputs.csv \\
      --out data/judged_inputs.csv
"""
import argparse
import json
import math
import re
import sys
import urllib.request
from collections import Counter
from typing import Iterable

import pandas as pd

NRP_DATASET = "d_156a38dc024d2b20a6c1d0c0179e797c"
LUP_DATASET = "d_9b5886a025c8db1192a8fada42bd4330"
POLL_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{ds}/poll-download"

PROPOSED_HORIZON_YEAR = 2030   # placeholder horizon for "2999" entries

# Per-programme significance thresholds (count → sig)
SIG_THRESHOLDS = {
    "NRP": [(6, "HIGH"), (3, "MEDIUM")],
    "LUP": [(8, "HIGH"), (4, "MEDIUM")],
}

# Estate-name aliases — pipeline planning-area names → canonical estates.csv names.
# Kept here to avoid coupling to momentum_model.py at import time. Mirror its ALIAS_MAP.
ALIAS_MAP = {
    "BIDADARI":        "WOODLEIGH",
    "MARSILING":       "WOODLANDS",
    "KAKI BUKIT":      "BEDOK",
    "EAST COAST":      "MARINE PARADE",
    "BOON LAY":        "JURONG EAST",
    "TAMAN JURONG":    "JURONG EAST",
    "JURONG WEST":     "JURONG EAST",
    "BUONA VISTA":     "QUEENSTOWN",
    "NOVENA":          "TOA PAYOH",
    "KALLANG":         "BOON KENG",
    "WEST COAST":      "CLEMENTI",
    "TAMPINES NORTH":  "TAMPINES",
    "YEW TEE":         "CHOA CHU KANG",
}

# NAME-substring → canonical-estate map. Longest substring wins so multi-word
# matches beat short ones ("BT PANJANG RING" matches "BT PANJANG" before any
# stray "RING" token). HDB NAMEs in NRP/LUP GeoJSONs use street- or precinct-
# level labels that often disagree with polygon centroid — old precincts on
# the Jurong West / Tengah border would centroid into TENGAH otherwise.
NAME_HINTS = [
    ("BUKIT PANJANG",     "BUKIT PANJANG"),
    ("BT PANJANG",        "BUKIT PANJANG"),
    ("BUKIT BATOK",       "BUKIT BATOK"),
    ("BUKIT MERAH",       "BUKIT MERAH"),
    ("BUKIT TIMAH",       "BUKIT TIMAH"),
    ("JLN BT MERAH",      "BUKIT MERAH"),
    ("JALAN BUKIT MERAH", "BUKIT MERAH"),
    ("JLN BUKIT MERAH",   "BUKIT MERAH"),
    ("TELOK BLANGAH",     "BUKIT MERAH"),
    ("HENDERSON",         "BUKIT MERAH"),
    ("KIM TIAN",          "BUKIT MERAH"),
    ("REDHILL",           "BUKIT MERAH"),
    ("TIONG BAHRU",       "BUKIT MERAH"),
    ("SPOTTISWOODE",      "BUKIT MERAH"),
    ("ALJUNIED",          "GEYLANG"),
    ("EUNOS",             "GEYLANG"),
    ("DAKOTA",            "GEYLANG"),
    ("SIMS",              "GEYLANG"),
    ("KAKI BUKIT",        "BEDOK"),
    ("BEDOK RESERVOIR",   "BEDOK"),
    ("BEDOK",             "BEDOK"),
    ("CHAI CHEE",         "BEDOK"),
    ("NEW UPPER CHANGI",  "BEDOK"),
    ("CHOA CHU KANG",     "CHOA CHU KANG"),
    ("YEW TEE",           "CHOA CHU KANG"),
    ("HOUGANG",           "HOUGANG"),
    ("SERANGOON",         "SERANGOON"),
    ("WOODLANDS",         "WOODLANDS"),
    ("MARSILING",         "WOODLANDS"),
    ("JURONG WEST",       "JURONG EAST"),
    ("JURONG EAST",       "JURONG EAST"),
    ("BOON LAY",          "JURONG EAST"),
    ("TAMAN JURONG",      "JURONG EAST"),
    ("TEBAN",             "JURONG EAST"),
    ("YUNG",              "JURONG EAST"),
    ("HOLLAND",           "QUEENSTOWN"),
    ("COMMONWEALTH",      "QUEENSTOWN"),
    ("MEI LING",          "QUEENSTOWN"),
    ("BUONA VISTA",       "QUEENSTOWN"),
    ("QUEEN",             "QUEENSTOWN"),
    ("TOA PAYOH",         "TOA PAYOH"),
    ("NOVENA",            "TOA PAYOH"),
    ("BISHAN",            "BISHAN"),
    ("ANG MO KIO",        "ANG MO KIO"),
    ("YISHUN",            "YISHUN"),
    ("SEMBAWANG",         "SEMBAWANG"),
    ("TAMPINES",          "TAMPINES"),
    ("PASIR RIS",         "PASIR RIS"),
    ("WHAMPOA",           "CENTRAL AREA"),
    ("BENDEMEER",         "BOON KENG"),
    ("KALLANG",           "BOON KENG"),
    ("BOON KENG",         "BOON KENG"),
    ("SMITH",             "CENTRAL AREA"),
    ("RACE COURSE",       "CENTRAL AREA"),
    ("MARINE PARADE",     "MARINE PARADE"),
    ("EAST COAST",        "MARINE PARADE"),
    ("JOO CHIAT",         "MARINE PARADE"),
    ("CLEMENTI",          "CLEMENTI"),
    ("WEST COAST",        "CLEMENTI"),
    ("WOODLEIGH",         "WOODLEIGH"),
    ("BIDADARI",          "WOODLEIGH"),
    ("PUNGGOL",           "PUNGGOL"),
    ("SENGKANG",          "SENGKANG"),
    ("CENTRAL AREA",      "CENTRAL AREA"),
    ("CANBERRA",          "CANBERRA"),
    ("DOVER",             "DOVER"),
    ("TENGAH",            "TENGAH"),
    ("LENTOR",            "LENTOR"),
]
# Longest match wins.
_NAME_HINTS_SORTED = sorted(NAME_HINTS, key=lambda kv: -len(kv[0]))


def name_to_estate(name: str) -> str | None:
    """Find the longest NAME_HINTS substring inside `name`; return its estate."""
    u = name.upper()
    for hint, estate in _NAME_HINTS_SORTED:
        if hint in u:
            return estate
    return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


_UA = "housing-estate-framework/1.4 (provision §2a HDB upgrading ingester)"


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def fetch_geojson(dataset_id: str) -> dict:
    """data.gov.sg async download flow: poll-download → presigned S3 URL."""
    poll = _http_json(POLL_URL.format(ds=dataset_id), timeout=30)
    return _http_json(poll["data"]["url"], timeout=60)


def centroid(geometry: dict) -> tuple[float, float] | None:
    """Return (lat, lon) — mean of all vertex coords across all rings.

    Approximate but adequate at SG scale; precise centroid would need Shapely.
    """
    coords: list[tuple[float, float]] = []

    def walk(node):
        if isinstance(node, (list, tuple)) and node and isinstance(node[0], (int, float)) and len(node) >= 2:
            coords.append((node[0], node[1]))   # [lon, lat] in GeoJSON
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(geometry.get("coordinates"))
    if not coords:
        return None
    mean_lon = sum(c[0] for c in coords) / len(coords)
    mean_lat = sum(c[1] for c in coords) / len(coords)
    return (mean_lat, mean_lon)


def nearest_estate(lat: float, lon: float, estates: pd.DataFrame) -> str:
    best, best_d = None, float("inf")
    for _, row in estates.iterrows():
        d = haversine_m(lat, lon, float(row["lat"]), float(row["lon"]))
        if d < best_d:
            best, best_d = str(row["estate"]).upper(), d
    return ALIAS_MAP.get(best, best)


_YEAR_RE = re.compile(r"(\d{4})")


def parse_completion_year(s) -> int | None:
    """Parse 'NQ YYYY' strings; return None for missing or sentinel ('2999')."""
    if not s:
        return None
    m = _YEAR_RE.search(str(s))
    if not m:
        return None
    y = int(m.group(1))
    return None if y >= 2999 else y


def significance(programme: str, count: int) -> str:
    for threshold, label in SIG_THRESHOLDS[programme]:
        if count >= threshold:
            return label
    return "LOW"


def aggregate(features: list, programme: str, estates: pd.DataFrame) -> list[dict]:
    """Bucket by (estate, certainty), emit one pipeline item per bucket."""
    buckets: dict[tuple[str, str], dict] = {}

    for f in features:
        props = f.get("properties") or {}
        name = (props.get("NAME") or "(unnamed)").strip()
        # Resolve estate: NAME-substring hint wins (handles JURONG WEST → JURONG
        # EAST cleanly), centroid is the fallback for unrecognised names.
        est = name_to_estate(name)
        if est is None:
            c = centroid(f.get("geometry") or {})
            if c is None:
                continue
            est = nearest_estate(*c, estates)
        status = (props.get("STATUS") or "").strip()
        year = parse_completion_year(props.get("ESTMT_CNSTRN_CMPLTN"))

        if status == "U/C":
            certainty = "CONFIRMED"
            resolved_year = year   # may be None; resolved at emission via mode
        else:
            certainty = "PLANNED"
            resolved_year = year   # often None for Proposed (placeholder 2999)

        key = (est, certainty)
        b = buckets.setdefault(key, {"years": [], "names": []})
        if resolved_year is not None:
            b["years"].append(resolved_year)
        b["names"].append(name)

    items: list[dict] = []
    for (est, certainty), b in sorted(buckets.items()):
        n = len(b["names"])
        if b["years"]:
            expected = Counter(b["years"]).most_common(1)[0][0]   # mode
        else:
            expected = PROPOSED_HORIZON_YEAR
        sig = significance(programme, n)
        note_names = "; ".join(b["names"][:5]) + ("…" if n > 5 else "")
        unit = "precinct" if programme == "NRP" else "block-cluster"
        items.append({
            "description": f"{programme} — {n} {unit}{'s' if n != 1 else ''} in {est} ({certainty.lower()})",
            "benefiting_estates": [est],
            "type": programme,
            "significance": sig,
            "certainty": certainty,
            "expected_year": expected,
            "notes": f"{programme} {certainty.lower()} ({n} site{'s' if n != 1 else ''}): {note_names}"
                     + ("  [year=mode of U/C completions]" if b["years"] else
                        f"  [no firm date — default horizon {PROPOSED_HORIZON_YEAR}]"),
        })
    return items


def merge_into_pipeline(pipeline_path: str, new_items: list[dict], out_path: str) -> None:
    """Replace any existing NRP/LUP items in pipeline_data.json with the new set."""
    with open(pipeline_path) as f:
        data = json.load(f)
    existing = data.get("pipeline_items", [])
    kept = [it for it in existing if it.get("type") not in {"NRP", "LUP"}]
    data["pipeline_items"] = kept + new_items
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True, help="estates.csv with estate,lat,lon")
    ap.add_argument("--pipeline", required=True, help="pipeline_data.json to merge into")
    ap.add_argument("--out", required=True, help="output JSON (can be same as --pipeline)")
    ap.add_argument("--cache-dir", help="optional dir to cache fetched GeoJSONs")
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)

    print("Fetching NRP …", file=sys.stderr)
    nrp = fetch_geojson(NRP_DATASET)
    print(f"  {len(nrp['features'])} precincts", file=sys.stderr)
    print("Fetching LUP …", file=sys.stderr)
    lup = fetch_geojson(LUP_DATASET)
    print(f"  {len(lup['features'])} block-clusters", file=sys.stderr)

    nrp_items = aggregate(nrp["features"], "NRP", estates)
    lup_items = aggregate(lup["features"], "LUP", estates)
    print(f"Emitted {len(nrp_items)} NRP + {len(lup_items)} LUP pipeline items", file=sys.stderr)

    merge_into_pipeline(args.pipeline, nrp_items + lup_items, args.out)
    print(f"Merged into {args.out}", file=sys.stderr)

    # Quick per-estate summary
    summary: dict[str, dict[str, int]] = {}
    for it in nrp_items + lup_items:
        est = it["benefiting_estates"][0]
        summary.setdefault(est, {"NRP": 0, "LUP": 0})
        summary[est][it["type"]] += 1
    print("\nPer-estate item count:")
    for est in sorted(summary):
        print(f"  {est:18s}  NRP={summary[est]['NRP']}  LUP={summary[est]['LUP']}")


if __name__ == "__main__":
    main()
