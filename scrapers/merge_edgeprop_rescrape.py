"""
Merge a rescrape batch into the canonical EdgeProp condo/apartment transactions
CSV, deduplicating on the standard 5-column key. Existing rows keep their
position; genuinely new rows are appended. Refuses to write when nothing new.

Run:
  python3 scrapers/merge_edgeprop_rescrape.py --new data/raw/edgeprop/<rescrape>.csv

INPUT CONTRACT
  Both CSVs must share the exact scraper schema, incl. the dedup key columns:
  Project, Date of Sale, Price ($), Area (sqft), Address
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_MAIN = ROOT / "data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
DEDUP_KEY = ["Project", "Date of Sale", "Price ($)", "Area (sqft)", "Address"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge an EdgeProp rescrape into the canonical CSV")
    ap.add_argument("--main", default=str(DEFAULT_MAIN))
    ap.add_argument("--new", required=True)
    args = ap.parse_args()

    main_df = pd.read_csv(args.main, dtype=str, low_memory=False)
    new_df = pd.read_csv(args.new, dtype=str, low_memory=False)
    if list(main_df.columns) != list(new_df.columns):
        sys.exit(f"ERROR: schema mismatch\n  main: {list(main_df.columns)}\n  new:  {list(new_df.columns)}")

    before = len(main_df)
    merged = pd.concat([main_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=DEDUP_KEY, keep="first")
    added = len(merged) - before
    print(f"main {before:,} + new {len(new_df):,} -> {len(merged):,} "
          f"(+{added:,} added, {len(new_df) - added:,} duplicates dropped)")
    if added <= 0:
        sys.exit("ERROR: nothing new to merge — refusing to rewrite the canonical CSV")
    merged.to_csv(args.main, index=False)
    print(f"Written: {args.main}")


if __name__ == "__main__":
    main()
