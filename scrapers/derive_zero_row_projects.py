"""
Derive the list of discovered EdgeProp condo/apartment projects that have ZERO
rows in the committed transactions CSV, in the name,url,slug format consumed by
edgeprop_condo_apartment_playwright.py scrape --input.

Run:
  python3 scrapers/derive_zero_row_projects.py

INPUT CONTRACT
  projects csv columns: name, url, slug
  transactions csv: must have a source_slug column
"""

from __future__ import annotations

import argparse
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_PROJECTS = ROOT / "data/raw/edgeprop/edgeprop_condo_apartment_projects.csv"
DEFAULT_TRANSACTIONS = ROOT / "data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
DEFAULT_OUT = ROOT / "data/raw/edgeprop/edgeprop_zero_row_projects.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description="List discovered projects with zero scraped rows")
    ap.add_argument("--projects", default=str(DEFAULT_PROJECTS))
    ap.add_argument("--transactions", default=str(DEFAULT_TRANSACTIONS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    projects = pd.read_csv(args.projects)
    scraped = set(pd.read_csv(args.transactions, usecols=["source_slug"])["source_slug"].dropna().unique())
    zero = projects[~projects["slug"].isin(scraped)]
    zero.to_csv(args.out, index=False)
    print(f"{len(projects)} discovered, {len(scraped)} with rows, "
          f"{len(zero)} zero-row -> {args.out}")


if __name__ == "__main__":
    main()
