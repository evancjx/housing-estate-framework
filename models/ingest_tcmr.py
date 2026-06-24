#!/usr/bin/env python3
"""
Town Council Management Report ingester  (Provision v2.0 §1.8)
==============================================================
Emits a hand-transcribed snapshot of the MND Town Council Management
Report KPIs, indexed by town council and mapped to constituent estates.
This feeds the new stewardship component (Task 2.4) — visible upkeep,
quantitatively measured by an external regulator.

PROVENANCE: PARTLY_MEASURED.
  KPI bands (GREEN/AMBER/RED) are transcribed from the most recent
  published MND TCMR. The four standard indicators are:
    - scc_arrears        Service & Conservancy Charges arrears
    - lift               Lift performance (escalator + lift uptime)
    - cleanliness        Estate cleanliness
    - estate_maintenance Estate maintenance
  oneservice_complaints_per_1k_units is null pending OneService API
  access (MSE/MEWR data-sharing not yet established) — flag
  provenance_note='tcmr_only' on the JSON.

USAGE: this script's primary job is to WRITE the hand-curated JSON to
disk (so the consuming code can re-load deterministically and the data
is version-controlled). Future iterations can replace the embedded
dictionary with a real PDF parser.

INPUT CONTRACT:
  --year YYYY   reporting year (also stamped into the JSON)
  --out PATH    JSON destination

RUN:
  python3 models/ingest_tcmr.py --year 2024 --out data/town_council_kpi.json
"""
import argparse
import json
import sys
from datetime import date

# ---------------------------------------------------------------------------
# Hand-curated TCMR snapshot
# ---------------------------------------------------------------------------
# Source: MND TCMR FY2023 (published 2024). Bands transcribed from the
# published summary table; OneService figures not yet available — null.
# Each TC's `estates` list uses canonical UPPERCASE names matching
# data/estates.csv. Mapping derived from public constituency/town-council
# boundary records (TC websites + Parliament constituency lists).

TOWN_COUNCILS = [
    {
        "name": "Aljunied-Hougang TC",
        "estates": ["HOUGANG", "SERANGOON"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Ang Mo Kio TC",
        "estates": ["ANG MO KIO", "LENTOR"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Bishan-Toa Payoh TC",
        "estates": ["BISHAN", "TOA PAYOH"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Chua Chu Kang TC",
        "estates": ["CHOA CHU KANG", "BUKIT BATOK", "TENGAH"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "AMBER",
    },
    {
        "name": "East Coast TC",
        "estates": ["BEDOK"],
        "scc_arrears": "GREEN", "lift": "AMBER",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Holland-Bukit Panjang TC",
        "estates": ["BUKIT PANJANG", "BUKIT TIMAH", "DOVER"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Jalan Besar TC",
        "estates": ["CENTRAL AREA", "BOON KENG", "KALLANG"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "AMBER", "estate_maintenance": "GREEN",
    },
    {
        "name": "Jurong-Clementi TC",
        "estates": ["JURONG EAST", "CLEMENTI", "JURONG WEST"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Marine Parade TC",
        "estates": ["MARINE PARADE", "GEYLANG", "WOODLEIGH"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Marsiling-Yew Tee TC",
        "estates": ["WOODLANDS"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Nee Soon TC",
        "estates": ["YISHUN"],
        "scc_arrears": "AMBER", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Pasir Ris-Punggol TC",
        "estates": ["PASIR RIS", "PUNGGOL"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Sembawang TC",
        "estates": ["SEMBAWANG", "CANBERRA"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Sengkang TC",
        "estates": ["SENGKANG"],
        "scc_arrears": "AMBER", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "AMBER",
    },
    {
        "name": "Tampines TC",
        "estates": ["TAMPINES", "TAMPINES EAST", "TAMPINES WEST"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
    {
        "name": "Tanjong Pagar TC",
        "estates": ["BUKIT MERAH", "QUEENSTOWN"],
        "scc_arrears": "GREEN", "lift": "GREEN",
        "cleanliness": "GREEN", "estate_maintenance": "GREEN",
    },
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Add OneService nulls + provenance flag uniformly
    tc_records = []
    for tc in TOWN_COUNCILS:
        rec = dict(tc)
        rec["oneservice_complaints_per_1k_units"] = None
        rec["oneservice_close_rate_pct"] = None
        rec["provenance_note"] = "tcmr_only"
        tc_records.append(rec)

    out = {
        "year": args.year,
        "source": f"MND Town Council Management Report FY{args.year - 1} "
                  "(published " + str(args.year) + ")",
        "transcribed_on": str(date.today()),
        "kpi_bands": ["GREEN", "AMBER", "RED"],
        "note": "OneService complaint figures pending MSE/MEWR API access; "
                "score_stewardship treats them as missing and renormalises.",
        "town_councils": tc_records,
    }

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(tc_records)} town councils → {args.out}",
          file=sys.stderr)

    # Spot-check: enumerate estate-coverage
    covered = set()
    for tc in tc_records:
        for e in tc["estates"]:
            covered.add(e)
    print(f"  estates covered: {len(covered)}", file=sys.stderr)
    print(f"  sample: {sorted(covered)[:8]}", file=sys.stderr)


if __name__ == "__main__":
    main()
