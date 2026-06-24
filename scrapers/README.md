# URA PMI Scrapers

Downloads private residential transaction data from URA for use in the estate value model.

## Files

| File | Purpose |
|------|---------|
| `ura_pmi_playwright.py` | **Primary scraper** — Playwright browser automation against the URA PMI portal |
| `ura_pmi_api.py` | Fallback — URA Data Service API client (requires `URA_ACCESS_KEY` env var) |
| `ingest_ura_raw.py` | Converts raw downloaded CSVs to `ura_private.csv` schema for `value_model.py` |
| `run_download.py` | Orchestrator — runs Playwright first, falls back to API |

## Setup

```bash
pip install playwright --break-system-packages
playwright install chromium
```

## Quick start — download missing districts

```bash
# Download Marine Parade (D15) and Bedok (D16) — still missing from ura_private.csv
python scrapers/ura_pmi_playwright.py \
    --districts 15 16 \
    --year_from 2021 --year_to 2026 \
    --out_dir data/ura_raw/

# Ingest into ura_private.csv
python scrapers/ingest_ura_raw.py \
    --raw_dir data/ura_raw/ \
    --out data/ura_private.csv \
    --merge

# Re-run value model
python models/value_model.py \
    --scores data/provision_scores.csv \
    --hdb data/hdb_resale.csv \
    --private data/ura_private.csv \
    --out data/value_private.csv
```

## District → Estate mapping

| District | Label | Estate(s) in framework |
|----------|-------|------------------------|
| 03 | Queenstown, Tiong Bahru | QUEENSTOWN / DOVER / HOLLAND VILLAGE |
| 04 | Telok Blangah, Harbourfront | BUKIT MERAH |
| 05 | Clementi New Town | CLEMENTI |
| 07 | Middle Road, Golden Mile | KALLANG |
| 08 | Little India | BOON KENG |
| 10 | Ardmore, Bukit Timah, Holland Rd | BUKIT TIMAH (D10 luxury belt) |
| 14 | Geylang, Eunos | GEYLANG |
| **15** | **Katong, Joo Chiat, Amber Road** | **MARINE PARADE** ← still missing |
| **16** | **Bedok, Upper East Coast** | **BEDOK** ← still missing |
| 18 | Tampines, Pasir Ris | TAMPINES / PASIR RIS |
| 19 | Serangoon Garden, Hougang, Punggol | SERANGOON / HOUGANG / PUNGGOL |
| 20 | Bishan, Ang Mo Kio | BISHAN / ANG MO KIO |
| 21 | Upper Bukit Timah | BUKIT TIMAH |
| 22 | Jurong | JURONG EAST / JURONG WEST |
| 23 | Hillview, Bukit Panjang, CCK | BUKIT PANJANG / CHOA CHU KANG |
| 24 | Tengah | TENGAH |
| 25 | Kranji, Woodgrove | WOODLANDS |
| 26 | Upper Thomson, Springleaf | LENTOR (AMK town) |
| 27 | Yishun, Sembawang | YISHUN / SEMBAWANG / CANBERRA |

Districts 01/02/06/09/11/17/28 are excluded (Central Area, industrial, or minimal residential).

## Notes on the URA API (fallback)

The URA Data Service API (`uraDataService/invokeUraDS`) is protected by an L7 WAF
that blocks non-browser HTTP clients. The Playwright scraper uses a real Chromium
browser and bypasses this. The API client (`ura_pmi_api.py`) is included as a
template; it may work if you have a pre-generated token or the WAF rules change.

Access key must be set as `URA_ACCESS_KEY` environment variable — **never hardcode it**.
