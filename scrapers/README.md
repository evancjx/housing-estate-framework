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
python -m sg_estate.domain.value \
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

## Exact EdgeProp condo/apartment unit numbers

Public EdgeProp pages publish masked addresses such as `#06-XX`. Exact unit numbers are a
login/Pro feature. The scraper does not bypass that access control and never fills masked digits.
Its dedicated unit schema records:

- `unit_number`, `unit_floor`, `unit_stack`: populated only from one published, unmasked
  `#floor-stack` token (including legitimate values such as `#PH-01` or `#B1-01`);
- `unit_number_status`: `exact`, `masked`, `not_present`, or `unparseable`;
- `unit_number_source`: `edgeprop_address` when an address unit fragment was present.

Parse a copied or saved table you are authorised to view:

```bash
python3 scrapers/edgeprop_condo_apartment_playwright.py parse-transactions \
  --html-file /path/to/saved-project.html \
  --project-name "PROJECT NAME" --planning-area NOVENA --postal-district 11 \
  --source-url https://www.edgeprop.sg/condo-apartment/project-slug \
  --out data/raw/edgeprop/project_unit_transactions.csv
```

Alternatively, use a Playwright storage-state file for your own authorised session. Keep the state
file outside the repository because it contains login credentials:

```bash
python3 scrapers/edgeprop_condo_apartment_playwright.py scrape \
  --storage-state /secure/path/edgeprop-storage-state.json \
  --unit-out data/raw/edgeprop/edgeprop_condo_unit_transactions.csv \
  --resume
```

`--out` retains the legacy transaction schema; `--unit-out` writes the dedicated unit schema and
prints exact/masked coverage. The unit output is a history of published transactions, not a complete
inventory of every physical unit. Missing and never-transacted units cannot be recovered from the
sales table. Review access and redistribution terms before committing paid-source extracts.

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

## EdgeProp condo/apartment zero-row re-scrape runbook

Projects scraped before the lazy-load scroll fix (commit 69b7775) bailed with
0 rows. To find and re-scrape them:

```bash
# 1. Derive the zero-row list (projects CSV minus slugs present in the transactions CSV)
python3 scrapers/derive_zero_row_projects.py

# 2. Scrape in resumable batches (NOTE: --start/--limit slice BEFORE the resume
#    filter, so always run batches against the dedicated zero-row input file)
python3 scrapers/edgeprop_condo_apartment_playwright.py scrape \
  --input data/raw/edgeprop/edgeprop_zero_row_projects.csv \
  --out   data/raw/edgeprop/edgeprop_zero_row_rescrape_transactions.csv \
  --log   data/raw/edgeprop/edgeprop_zero_row_rescrape_attempts.csv \
  --resume --resume-attempts --delay 0.5 --from-year 2019 \
  --start 0 --limit 300          # repeat with --start 300/600/900/1200/1500

# 3. Retry error rows: rename the attempts log first (--resume-attempts skips
#    everything ATTEMPTED, not just succeeded), then re-run without --start/--limit.

# 4. Diagnose stubborn zero-row slugs (writes stage snapshots to data/raw/edgeprop/probe/)
python3 scrapers/probe_zero_row.py <slug>

# 5. Merge into the canonical CSV (dedup on Project/Date/Price/Area/Address; refuses no-op)
python3 scrapers/merge_edgeprop_rescrape.py --new data/raw/edgeprop/edgeprop_zero_row_rescrape_transactions.csv

# 6. Rebuild the bedroom attribution dataset + gap report
make private-bedrooms
```

Zero-row slugs that never appear in `ura_private.csv` are acceptable: they are
pre-2019-sales or rental-only projects with no transactions to recover.
