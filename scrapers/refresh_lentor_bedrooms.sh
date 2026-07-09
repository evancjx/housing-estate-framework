#!/usr/bin/env bash
#
# Fetch bedroom-per-transaction data for the Lentor / Upper Thomson (D26) condo
# projects that the committed EdgeProp feed is missing, then regenerate the
# D18-vs-D26 comparison so its bedroom coverage improves.
#
# WHY THIS IS A LOCAL SCRIPT: EdgeProp (and every external host) is blocked by the
# egress policy of the Claude Code *web* environment, so scraping cannot run there.
# Run this on a machine with normal internet access.
#
# Missing D26 projects (URA transactions with no EdgeProp bedroom rows):
#   Springleaf Residence (759), Lentor Hills Residences (580), Lentoria (240),
#   Meadows @ Peirce (68), The Calrose (40), The Brooks II (5).
# D18 Pasir Ris already has ~100% bedroom coverage; nothing to scrape there.
#
# Usage:
#   pip install playwright --break-system-packages && playwright install chromium
#   bash scrapers/refresh_lentor_bedrooms.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
PROJECTS=data/edgeprop_lentor_discovered.csv

echo ">> 1/4  Discovering EdgeProp project links (Lentor / Springleaf / Meadows / Calrose / Brooks)"
# discover writes name,url,slug; --match filters the index by substring.
: > "$PROJECTS.tmp"
for kw in lentor springleaf meadows calrose brooks; do
  python3 scrapers/edgeprop_condo_apartment_playwright.py discover \
      --match "$kw" --out "data/_disc_${kw}.csv" || true
  # append (skip header after the first file)
  if [ -s "data/_disc_${kw}.csv" ]; then
    tail -n +2 "data/_disc_${kw}.csv" >> "$PROJECTS.tmp" || true
  fi
  rm -f "data/_disc_${kw}.csv"
done
echo "name,url,slug" > "$PROJECTS"
sort -u "$PROJECTS.tmp" >> "$PROJECTS" || true
rm -f "$PROJECTS.tmp"
DISCN=$(($(wc -l < "$PROJECTS") - 1))
echo "   discovered $DISCN project link(s) -> $PROJECTS"

# Fallback: if discover found nothing (new launches are sometimes not on the
# public index), use the hand-built target list of direct project URLs.
if [ "$DISCN" -le 0 ]; then
  echo "   discover returned 0; falling back to scrapers/lentor_bedroom_targets.csv"
  echo "   (verify/adjust those URLs if any 404 — EdgeProp slugs can differ)"
  PROJECTS=scrapers/lentor_bedroom_targets.csv
fi

echo ">> 2/4  Scraping transaction tables (bedrooms included), appending to the committed feed"
# --resume skips project URLs already present in OUT, so existing rows are untouched.
python3 scrapers/edgeprop_condo_apartment_playwright.py scrape \
    --input "$PROJECTS" \
    --out "$OUT" \
    --from-year 2019 \
    --resume

echo ">> 3/4  Regenerating the D18 vs D26 comparison (bedroom coverage should rise for D26)"
python3 models/gen_two_district_comparison_html.py --district 18 --district 26

echo ">> 4/4  Running the comparison test suite"
python3 -m pytest tests/test_two_district_comparison.py -q

echo
echo "Done. Review the new bedroom coverage in two_district_comparison_D18_D26.html,"
echo "then commit the updated feed + HTML:"
echo "  git add $OUT two_district_comparison_D18_D26.html"
echo "  git commit -m 'Add Lentor condo bedroom transactions from EdgeProp'"
