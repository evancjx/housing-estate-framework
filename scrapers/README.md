# URA PMI Scrapers

Downloads private residential transaction data from URA for use in the estate value model.

## Files

| File | Purpose |
|------|---------|
| `ura_pmi_playwright.py` | **Primary scraper** — Playwright browser automation against the URA PMI portal |
| `ura_pmi_api.py` | Fallback — URA Data Service API client (requires `URA_ACCESS_KEY` env var) |
| `ingest_ura_raw.py` | Converts raw downloaded CSVs to `ura_private.csv` schema for `value_model.py` |
| `run_download.py` | Orchestrator — runs Playwright first, falls back to API |
| `edgeprop_landed.py` | EdgeProp landed directory scraper and EdgeProp sales-table parser |

## Setup

```bash
pip install playwright --break-system-packages
playwright install chromium
```

## Quick start — apartment/condo transactions

```bash
# Download apartment/condo transactions for selected districts.
python scrapers/ura_pmi_playwright.py \
    --districts 15 16 \
    --year_from 2021 --year_to 2026 \
    --out_dir data/raw/ura/

# Ingest into ura_private.csv
python scrapers/ingest_ura_raw.py \
    --raw_dir data/raw/ura/ \
    --out data/inputs/ura_private.csv \
    --merge

# Re-run value model
python models/value_model.py \
    --scores data/outputs/provision_scores.csv \
    --hdb data/inputs/hdb_resale.csv \
    --private data/inputs/ura_private.csv \
    --out data/outputs/value_output_private.csv
```

## Quick start — landed private transactions

URA's PMI portal exposes landed data as two residential property groups:

- `Landed Properties (Non-Strata)` — scraper value `landed` or `1`
- `Strata Landed` — scraper value `strata_landed` or `2`

Download both groups without overwriting the existing apartment/condo raw CSVs:

```bash
python scrapers/ura_pmi_playwright.py \
    --districts 15 16 \
    --prop_types landed strata_landed \
    --year_from 2021 --year_to 2026 \
    --out_dir data/raw/ura/
```

Or use the orchestrator shortcut:

```bash
python scrapers/run_download.py \
    --landed \
    --districts 15 16 \
    --year_from 2021 --year_to 2026 \
    --out_dir data/raw/ura/
```

New landed raw files are written with property-type slugs, for example
`pmi_d15_landed_non_strata_2021-2026.csv` and `pmi_d15_strata_landed_2021-2026.csv`.
After downloading, run `ingest_ura_raw.py --merge`; the ingestor preserves `property_type` and the
value model treats it as a private-resale control.

## EdgeProp landed project metadata and saved transaction tables

EdgeProp's public landed pages expose project metadata and directory links. Full sales rows can be
login/Pro-gated, so `edgeprop_landed.py` does not bypass authentication; it either scrapes public
metadata or parses saved/copied transaction text that you are authorised to view.

```bash
# Discover public landed project links.
python scrapers/edgeprop_landed.py discover \
    --out data/raw/edgeprop/edgeprop_landed_projects.csv

# Fetch public metadata from discovered project pages.
python scrapers/edgeprop_landed.py details \
    --input data/raw/edgeprop/edgeprop_landed_projects.csv \
    --out data/raw/edgeprop/edgeprop_landed_project_details.csv \
    --limit 25

# Parse copied/saved EdgeProp sales-table text into a raw CSV.
python scrapers/edgeprop_landed.py parse-transactions \
    --text-file data/edgeprop_raw/kembangan.txt \
    --project-name "KEMBANGAN ESTATE" \
    --planning-area BEDOK \
    --postal-district 14 \
    --out data/raw/ura/edgeprop_kembangan.csv

# Merge parsed EdgeProp rows into the private transaction input.
python scrapers/ingest_ura_raw.py \
    --files data/raw/ura/edgeprop_kembangan.csv \
    --out data/inputs/ura_private.csv \
    --merge \
    --source_quality not_clean
```

The parser writes `Area (sqm)` from EdgeProp's sqft value, and the ingestor keeps `type_of_area`,
`unit_price_psf`, `purchaser_address`, `source`, and `source_quality` when present.

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
