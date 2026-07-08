#!/usr/bin/env python3
"""
URA REALIS + STB en-bloc pipeline ingester  (Provision v2.0 §1.10)
===================================================================
Adds private-side pipeline items (new launches + en-bloc tenders) to
pipeline_data.json, feeding the momentum extension (Task 2.11).

PROVENANCE: PARTLY_MEASURED.
  Item list is hand-curated from EdgeProp Singapore monthly summaries
  + URA REALIS public dashboard screenshots (2025-2026). Live scraping
  of URA REALIS is fragile (form-based AJAX, no public API), so we
  transcribe and commit a static snapshot. STB en-bloc registry is
  similarly scraped manually.

  Re-running this script REPLACES existing PRIVATE_NEW_LAUNCH and
  EN_BLOC_TENDER items in pipeline_data.json (mirrors the type-prefix
  filter pattern from ingest_hdb_upgrading.py:merge_into_pipeline).

INPUT CONTRACT:
  --pipeline  data/inputs/pipeline_data.json (existing pipeline file)
  --out       output JSON path (can be same as --pipeline)

RUN:
  python3 models/ingest_private_pipeline.py \\
      --pipeline data/inputs/pipeline_data.json \\
      --out data/inputs/pipeline_data.json
"""
import argparse
import json
import sys
from datetime import date

# ---------------------------------------------------------------------------
# Hand-curated private pipeline (2025-2026 launches + recent en-bloc tenders)
# Source: EdgeProp Singapore monthly market wraps + URA REALIS dashboard.
# ---------------------------------------------------------------------------
PRIVATE_LAUNCHES = [
    # 2025 launches
    {"name": "The Continuum",       "estate": "GEYLANG",       "units": 816,  "year": 2027, "note": "Thiam Siew Ave freehold; Hoi Hup + Sunway"},
    {"name": "Lentor Hills Residences", "estate": "LENTOR",    "units": 598,  "year": 2026, "note": "Lentor Hills 99-yr"},
    {"name": "Hillock Green",       "estate": "LENTOR",        "units": 474,  "year": 2027, "note": "Lentor Central 99-yr"},
    {"name": "Lentoria",            "estate": "LENTOR",        "units": 267,  "year": 2027, "note": "Lentor Hills Rd"},
    {"name": "Lentor Mansion",      "estate": "LENTOR",        "units": 533,  "year": 2027, "note": "GuocoLand"},
    {"name": "Pinetree Hill",       "estate": "BUKIT TIMAH",   "units": 520,  "year": 2027, "note": "Pine Grove A site; UOL"},
    {"name": "Watten House",        "estate": "BUKIT TIMAH",   "units": 180,  "year": 2027, "note": "Shelford freehold; UOL"},
    {"name": "Tembusu Grand",       "estate": "GEYLANG",       "units": 638,  "year": 2027, "note": "Jalan Tembusu 99-yr; CDL"},
    {"name": "Hillhaven",           "estate": "BUKIT PANJANG", "units": 341,  "year": 2027, "note": "Hillview Rise; Far East + Sekisui"},
    {"name": "J'den",               "estate": "JURONG EAST",   "units": 368,  "year": 2027, "note": "JE Central; CapitaLand"},
    {"name": "Hillshore",           "estate": "PASIR PANJANG", "units":  59,  "year": 2027, "note": "Pasir Panjang Rd FH"},
    {"name": "Sora",                "estate": "JURONG EAST",   "units": 440,  "year": 2028, "note": "Yuan Ching Rd; CSC Land"},
    {"name": "The Hill@One-North",  "estate": "DOVER",         "units": 142,  "year": 2027, "note": "Slim Barracks Rise; Kingsford"},
    {"name": "Lentor Modern",       "estate": "LENTOR",        "units": 605,  "year": 2026, "note": "Lentor Central; GuocoLand"},
    # 2026 launches (announced/confirmed)
    {"name": "Parktown Residence",  "estate": "TAMPINES",      "units": 1193, "year": 2028, "note": "Tampines N integrated; CapitaLand/UOL/SingHaiyi"},
    {"name": "Bagnall Haus",        "estate": "BEDOK",         "units": 113,  "year": 2027, "note": "Upp East Coast Rd FH; Roxy-Pacific"},
    {"name": "Emerald of Katong",   "estate": "MARINE PARADE", "units": 846,  "year": 2027, "note": "Jln Tembusu 99-yr; Sim Lian"},
    {"name": "The Chuan Park",      "estate": "SERANGOON",     "units": 916,  "year": 2028, "note": "Lor Chuan; Kingsford+MCC"},
    {"name": "Union Square Residences","estate": "CENTRAL AREA","units": 366, "year": 2028, "note": "Havelock Rd; CDL"},
    {"name": "Norwood Grand",       "estate": "WOODLANDS",     "units": 348,  "year": 2027, "note": "Champions Way; CDL"},
    {"name": "Nava Grove",          "estate": "BUKIT TIMAH",   "units": 552,  "year": 2027, "note": "Pine Grove B; SingHaiyi"},
    {"name": "The Orie",            "estate": "TOA PAYOH",     "units": 777,  "year": 2028, "note": "Lor 1 TP; CDL"},
    {"name": "Aurelle of Tampines", "estate": "TAMPINES",      "units": 760,  "year": 2028, "note": "Tampines St 62 EC; Sim Lian"},
    {"name": "Novo Place",          "estate": "TENGAH",        "units": 504,  "year": 2027, "note": "Tengah Plantation EC; Hoi Hup+Sunway"},
    {"name": "Lentor Central Resi", "estate": "LENTOR",        "units": 477,  "year": 2028, "note": "Lentor Gardens; Hong Leong/GuocoLand"},
]

EN_BLOC_TENDERS = [
    # Recent en-bloc successes 2024-2026 (signal: redevelopment incoming)
    {"name": "Pine Grove",          "estate": "BUKIT TIMAH",   "units": 660,  "year": 2027, "note": "GLS site sold to UOL/SingHaiyi; 2 plots"},
    {"name": "Park View Mansions",  "estate": "JURONG EAST",   "units": 440,  "year": 2027, "note": "Yuan Ching Rd; CSC Land Sora"},
    {"name": "Bagnall Court",       "estate": "BEDOK",         "units": 113,  "year": 2027, "note": "Becomes Bagnall Haus"},
    {"name": "Chuan Park",          "estate": "SERANGOON",     "units": 916,  "year": 2028, "note": "Sold collective sale; redevelopment underway"},
    {"name": "Thiam Siew Ave plots","estate": "GEYLANG",       "units": 816,  "year": 2027, "note": "Becomes The Continuum"},
    {"name": "Watten Estate",       "estate": "BUKIT TIMAH",   "units": 180,  "year": 2027, "note": "Watten House redevelopment"},
    {"name": "Maxwell House",       "estate": "CENTRAL AREA",  "units": 322,  "year": 2028, "note": "CBD residential conversion"},
]


def make_launch_item(rec: dict) -> dict:
    return {
        "description": f"{rec['name']} new launch — {rec['units']} units",
        "benefiting_estates": [rec["estate"].upper()],
        "type": "PRIVATE_NEW_LAUNCH",
        "significance": "MEDIUM" if rec["units"] < 500 else "HIGH",
        "certainty": "CONFIRMED",
        "expected_year": rec["year"],
        "notes": f"URA REALIS pipeline entry — {rec.get('note', '')}"
                 f" (transcribed {date.today()})",
    }


def make_enbloc_item(rec: dict) -> dict:
    return {
        "description": f"{rec['name']} en-bloc redevelopment — {rec['units']} units",
        "benefiting_estates": [rec["estate"].upper()],
        "type": "EN_BLOC_TENDER",
        "significance": "MEDIUM",
        "certainty": "CONFIRMED",
        "expected_year": rec["year"],
        "notes": f"STB / EdgeProp en-bloc tender — {rec.get('note', '')}"
                 f" (transcribed {date.today()})",
    }


def merge_into_pipeline(pipeline_path, new_items, out_path):
    """Replace any existing PRIVATE_NEW_LAUNCH / EN_BLOC_TENDER items."""
    with open(pipeline_path) as f:
        data = json.load(f)
    existing = data.get("pipeline_items", [])
    kept = [it for it in existing
            if it.get("type") not in {"PRIVATE_NEW_LAUNCH", "EN_BLOC_TENDER"}]
    data["pipeline_items"] = kept + new_items
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pipeline", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    launches = [make_launch_item(r) for r in PRIVATE_LAUNCHES]
    enblocs = [make_enbloc_item(r) for r in EN_BLOC_TENDERS]
    new_items = launches + enblocs

    merge_into_pipeline(args.pipeline, new_items, args.out)
    print(f"Merged {len(launches)} launches + {len(enblocs)} en-blocs "
          f"into {args.out}", file=sys.stderr)

    # Spot-check per estate
    by_estate = {}
    for it in new_items:
        for e in it["benefiting_estates"]:
            by_estate.setdefault(e, 0)
            by_estate[e] += 1
    print("\nPrivate-pipeline per-estate counts:", file=sys.stderr)
    for est in sorted(by_estate, key=lambda x: -by_estate[x]):
        print(f"  {est:15s}  {by_estate[est]:2d} items", file=sys.stderr)


if __name__ == "__main__":
    main()
