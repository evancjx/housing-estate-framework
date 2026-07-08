#!/usr/bin/env python3
"""
OneMap MRT Geocoder  —  RUN THIS ON YOUR OWN MACHINE (needs internet)
=====================================================================
Converts the station list (Train Station names) into the lat,lon layer
that provision_model.py needs for the Connectivity + Infrastructure components.

The sandbox where the framework was built CANNOT reach onemap.gov.sg, so this
step runs locally. It needs only the Python standard library — no pip installs.

STEP 1 — get a fresh OneMap token (the one pasted in chat is expired):
    Register / log in at https://www.onemap.gov.sg/apidocs/
    Get a token (valid ~3 days). Paste it into TOKEN below, or set env var:
        export ONEMAP_TOKEN="your_token_here"

STEP 2 — make sure the station-names CSV is next to this script.
    Expected columns: stn_code, mrt_station_english, mrt_line_english
    (This is the TrainStationChineseNames.csv you already have.)

STEP 3 — run:
        python onemap_geocode_mrt.py

STEP 4 — upload the output  mrt_layer.csv  back to the chat.
    Columns produced: lat, lon, name, stn_code, line, operational
"""
import csv, json, os, sys, time, urllib.request, urllib.parse

TOKEN = os.environ.get("ONEMAP_TOKEN", "PASTE_FRESH_TOKEN_HERE")
INPUT  = os.path.join(os.path.dirname(__file__), "..", "data", "inputs", "mrt_layer_names.csv")
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "inputs", "mrt_layer.csv")
SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

def geocode(station_name, token):
    """Return (lat, lon) for an MRT station name, or None."""
    # OneMap matches "<Station> MRT STATION" well
    q = f"{station_name} MRT STATION"
    url = f"{SEARCH_URL}?searchVal={urllib.parse.quote(q)}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
    req = urllib.request.Request(url, headers={"Authorization": token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        results = data.get("results", [])
        if not results:
            # retry as LRT
            q2 = f"{station_name} LRT STATION"
            url2 = f"{SEARCH_URL}?searchVal={urllib.parse.quote(q2)}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
            req2 = urllib.request.Request(url2, headers={"Authorization": token})
            with urllib.request.urlopen(req2, timeout=20) as r2:
                data = json.load(r2)
            results = data.get("results", [])
        if results:
            top = results[0]
            return float(top["LATITUDE"]), float(top["LONGITUDE"])
    except Exception as e:
        print(f"  ! error on {station_name}: {e}", file=sys.stderr)
    return None

def main():
    if TOKEN == "PASTE_FRESH_TOKEN_HERE":
        sys.exit("Set ONEMAP_TOKEN env var or edit TOKEN in this file first.")
    if not os.path.exists(INPUT):
        sys.exit(f"Cannot find {INPUT} — put it next to this script (or edit INPUT).")

    rows_in = list(csv.DictReader(open(INPUT, encoding="utf-8-sig")))
    out = []
    seen = set()
    for i, r in enumerate(rows_in, 1):
        name = (r.get("mrt_station_english") or "").strip()
        code = (r.get("stn_code") or "").strip()
        line = (r.get("mrt_line_english") or "").strip()
        if not name or name in seen:   # dedupe interchange duplicates by name
            continue
        seen.add(name)
        coords = geocode(name, TOKEN)
        if coords:
            out.append({"lat": coords[0], "lon": coords[1], "name": name,
                        "stn_code": code, "line": line,
                        "operational": 1})   # all stations in this list are operational
            print(f"[{i}/{len(rows_in)}] {name:24} -> {coords[0]:.5f},{coords[1]:.5f}")
        else:
            print(f"[{i}/{len(rows_in)}] {name:24} -> NOT FOUND (add manually)")
        time.sleep(0.25)   # be polite to the API

    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lat","lon","name","stn_code","line","operational"])
        w.writeheader(); w.writerows(out)
    print(f"\nDone. {len(out)} stations geocoded -> {OUTPUT}")
    print("Upload mrt_layer.csv back to the chat.")
    print("NOTE: this list = operational stations only. For Future5Y / infra-readiness,")
    print("      add not-yet-open stations (e.g. JRL/Tengah) manually with operational=0.")

if __name__ == "__main__":
    main()
