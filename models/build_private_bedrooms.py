"""
Per-transaction bedroom attribution for the private condo/apartment sector.

URA PMI transaction rows carry no bedroom column; the EdgeProp scrape (whose
public tables label their source as URA) carries per-row Bedrooms. This model
joins the two and emits one row per transaction with a bedrooms value and an
explicit provenance tag — provenance is never faked:

  edgeprop_exact       row-level match on project + month + price + area
  edgeprop_band_label  project + size-band modal label (MIN_LABEL_N / MIN_LABEL_SHARE
                       rule imported from gen_district_private_comparison_html)
  research_unit_mix    curated per-project bedroom<->sqft ranges (data/inputs/
                       project_unit_mix.csv), applied via the row's exact area
  unknown              no honest attribution possible; bedrooms left empty

Scope: URA condo/apartment transactions (2021-06+) plus EdgeProp-only 2019-2020
rows (data_source=edgeprop_backfill — output rows sourced from EdgeProp only
ever carry sale_month in 2019-2020, mirroring the district-page backfill
invariant). Landed (*House) and Executive Condominium rows are excluded.

Run:
  python3 models/build_private_bedrooms.py            # writes the dataset
  python3 models/build_private_bedrooms.py --report   # + gap report for research

INPUT CONTRACT
  --private   data/inputs/ura_private.csv
      project_name, street_name, postal_district, property_type, tenure,
      sale_month (YYYY-MM), transacted_price, area_sqm, planning_area,
      floor_level, type_of_sale
  --edgeprop  data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
      Project, planning_area, Postal District, Date of Sale (DD Mon YYYY),
      Bedrooms, Price ($), Area (sqft), Area (sqm), Type, Tenure, Sale Type,
      Address
  --unit-mix  data/inputs/project_unit_mix.csv (OPTIONAL; tier 3 skipped if absent)
      project_name_norm, postal_district, bedrooms, min_sqft, max_sqft,
      source_url, retrieved_date, note
  --out       data/outputs/private_transactions_bedrooms.csv
      project_name, project_name_norm, postal_district, planning_area,
      property_type, tenure, sale_month, type_of_sale, transacted_price,
      area_sqm, floor_level, data_source, bedrooms, bedroom_source
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import unicodedata

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from aliases import URA_EDGEPROP_PROJECT_ALIAS  # noqa: E402  single-sourced alias map
from gen_district_private_comparison_html import (  # noqa: E402  single-sourced band/label rule
    MIN_LABEL_N,
    MIN_LABEL_SHARE,
    band_of,
    normalise_district,
)

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_PRIVATE = ROOT / "data/inputs/ura_private.csv"
DEFAULT_EDGEPROP = ROOT / "data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
DEFAULT_UNIT_MIX = ROOT / "data/inputs/project_unit_mix.csv"
DEFAULT_OUT = ROOT / "data/outputs/private_transactions_bedrooms.csv"
DEFAULT_REPORT = ROOT / "data/outputs/private_bedrooms_gap_report.csv"

SQM_TO_SQFT = 10.7639
SQM_TOLERANCE = 0.55        # EdgeProp sqm is sqft-derived; URA sqm is 1-dp
SQFT_EPS = 1e-6             # absorbs float/CSV round-trip noise at range bounds
PLACEHOLDER_NAMES = {"RESIDENTIAL APARTMENTS"}  # URA placeholder; never matchable
DEDUP_KEY = ["Project", "Date of Sale", "Price ($)", "Area (sqft)", "Address"]

_ROMAN = {"II": "2", "III": "3", "IV": "4"}
_AGGRESSIVE_SUFFIXES = ("RESIDENCES", "RESIDENCE", "CONDOMINIUM", "APARTMENTS")


def normalise_project_name(name) -> str:
    """Conservative, deterministic project-name key. Never strips suffixes."""
    text = unicodedata.normalize("NFKD", str(name))          # É -> E + combining accent
    text = text.encode("ascii", "ignore").decode("ascii")     # drop the accent, keep the letter
    text = text.upper().strip()
    text = text.replace("'", "")
    text = text.replace("@", " AT ").replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    tokens = [_ROMAN.get(t, t) for t in text.split()]
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    return " ".join(tokens)


def aggressive_key(name) -> str:
    """normalise_project_name plus trailing-suffix strip. Fallback key only —
    a match requires the key to be unique within the postal district."""
    tokens = normalise_project_name(name).split()
    if len(tokens) > 1 and tokens[-1] in _AGGRESSIVE_SUFFIXES:
        tokens = tokens[:-1]
    return " ".join(tokens)


def load_ura(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"postal_district": str}, low_memory=False)
    df = df[~df["property_type"].astype(str).str.contains("House", case=False, na=False)].copy()
    df["project_name"] = df["project_name"].astype(str).str.strip().str.upper()
    df["district"] = df["postal_district"].map(normalise_district)
    df["name_norm"] = df["project_name"].map(normalise_project_name)
    df["price_int"] = pd.to_numeric(df["transacted_price"], errors="coerce").round().astype("Int64")
    df["area_sqm"] = pd.to_numeric(df["area_sqm"], errors="coerce")
    df = df.dropna(subset=["price_int", "area_sqm", "sale_month"])
    df = df[df["area_sqm"] > 0].reset_index(drop=True)
    return df


def load_edgeprop(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"Postal District": str, "Bedrooms": str}, low_memory=False)
    df = df[~df["Type"].astype(str).str.contains("Executive Condominium", case=False, na=False)]
    df = df[~df["Type"].astype(str).str.contains("House", case=False, na=False)].copy()
    df["sale_dt"] = pd.to_datetime(df["Date of Sale"], format="%d %b %Y", errors="coerce")
    df["price_int"] = pd.to_numeric(df["Price ($)"], errors="coerce").round().astype("Int64")
    df["ep_sqm"] = pd.to_numeric(df["Area (sqm)"], errors="coerce")
    df["bedrooms"] = pd.to_numeric(df["Bedrooms"], errors="coerce")  # '-' -> NaN
    df.loc[df["bedrooms"] <= 0, "bedrooms"] = pd.NA
    df = df.dropna(subset=["sale_dt", "price_int", "ep_sqm"])
    df = df[df["ep_sqm"] > 0]
    df = df.drop_duplicates(subset=DEDUP_KEY).copy()
    df["sale_month"] = df["sale_dt"].dt.strftime("%Y-%m")
    df["sale_year"] = df["sale_dt"].dt.year
    df["project_upper"] = df["Project"].astype(str).str.strip().str.upper()
    df["district"] = df["Postal District"].map(normalise_district)
    df["name_norm"] = df["project_upper"].map(normalise_project_name)
    return df.reset_index(drop=True)


def build_name_mapping(ura: pd.DataFrame, ep: pd.DataFrame) -> dict:
    """(URA name_norm, district) -> EdgeProp name_norm. Identity when the name
    already exists in EdgeProp; aggressive fallback only when unambiguous."""
    ep_keys = set(zip(ep["name_norm"], ep["district"]))
    # aggressive key -> set of EP name_norms, per district
    ep_agg: dict = {}
    for name, district in ep_keys:
        ep_agg.setdefault((aggressive_key(name), district), set()).add(name)

    mapping = {}
    for name, district in set(zip(ura["name_norm"], ura["district"])):
        if (name, district) in URA_EDGEPROP_PROJECT_ALIAS:
            mapping[(name, district)] = URA_EDGEPROP_PROJECT_ALIAS[(name, district)]
        elif (name, district) in ep_keys:
            mapping[(name, district)] = name
        else:
            candidates = ep_agg.get((aggressive_key(name), district), set())
            if len(candidates) == 1:
                mapping[(name, district)] = next(iter(candidates))
    return mapping


def _modal_or_none(series: pd.Series):
    counts = series.value_counts()
    if len(counts) == 0:
        return None
    if len(counts) > 1 and counts.iloc[0] == counts.iloc[1]:
        return None  # tie -> refuse to guess
    return int(counts.index[0])


def tier1_exact(ura: pd.DataFrame, pool: pd.DataFrame, month_shift: int = 0) -> pd.Series:
    """Row-level match on (match_name, district, month±shift, price) with sqm
    tolerance. Returns bedrooms indexed like `ura` (NaN where unmatched)."""
    left = ura.loc[ura["bedrooms"].isna() & ura["match_name"].notna(),
                   ["match_name", "district", "sale_month", "price_int", "area_sqm"]].copy()
    if left.empty:
        return pd.Series(dtype="Float64")
    if month_shift:
        months = pd.to_datetime(left["sale_month"], format="%Y-%m") + pd.DateOffset(months=month_shift)
        left = left.assign(sale_month=months.dt.strftime("%Y-%m"))
    cand = left.reset_index().merge(
        pool[["name_norm", "district", "sale_month", "price_int", "ep_sqm", "bedrooms"]],
        left_on=["match_name", "district", "sale_month", "price_int"],
        right_on=["name_norm", "district", "sale_month", "price_int"],
        how="inner", suffixes=("", "_ep"),
    )
    cand = cand[(cand["area_sqm"] - cand["ep_sqm"]).abs() <= SQM_TOLERANCE]
    if cand.empty:
        return pd.Series(dtype="Float64")
    if month_shift:
        # shifted months are speculative: accept only a unanimous bedroom value
        agg = cand.groupby("index")["bedrooms"].agg(
            lambda s: int(s.iloc[0]) if s.nunique() == 1 else None)
    else:
        agg = cand.groupby("index")["bedrooms"].agg(_modal_or_none)
    return agg.dropna()


def tier2_band_labels(ep: pd.DataFrame) -> dict:
    """(name_norm, district, band) -> modal bedrooms, per the district-page rule."""
    pool = ep[ep["bedrooms"].notna()]
    labels = {}
    for (name, district, band), grp in pool.groupby(
            [pool["name_norm"], pool["district"], pool["ep_sqm"].map(band_of)]):
        if len(grp) < MIN_LABEL_N:
            continue
        counts = grp["bedrooms"].value_counts()
        if counts.iloc[0] / len(grp) >= MIN_LABEL_SHARE:
            labels[(name, district, band)] = int(counts.index[0])
    return labels


def tier3_unit_mix(ura: pd.DataFrame, mix: pd.DataFrame) -> pd.Series:
    """Curated (project, district) bedroom<->sqft ranges; ambiguity -> no match."""
    left = ura.loc[ura["bedrooms"].isna(), ["name_norm", "district", "area_sqm"]].copy()
    if left.empty or mix.empty:
        return pd.Series(dtype="Float64")
    left["sqft"] = left["area_sqm"] * SQM_TO_SQFT
    cand = left.reset_index().merge(
        mix, left_on=["name_norm", "district"],
        right_on=["project_name_norm", "postal_district"], how="inner")
    cand = cand[(cand["sqft"] >= cand["min_sqft"] - SQFT_EPS)
                & (cand["sqft"] <= cand["max_sqft"] + SQFT_EPS)]
    if cand.empty:
        return pd.Series(dtype="Float64")
    agg = cand.groupby("index")["bedrooms_mix"].agg(
        lambda s: int(s.iloc[0]) if s.nunique() == 1 else None)
    return agg.dropna()


def load_unit_mix(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["project_name_norm", "postal_district", "bedrooms_mix",
                                     "min_sqft", "max_sqft"])
    mix = pd.read_csv(path, dtype={"postal_district": str})
    mix["postal_district"] = mix["postal_district"].map(normalise_district)
    mix = mix.rename(columns={"bedrooms": "bedrooms_mix"})
    return mix[["project_name_norm", "postal_district", "bedrooms_mix", "min_sqft", "max_sqft"]]


def build(private_path: pathlib.Path, edgeprop_path: pathlib.Path,
          unit_mix_path: pathlib.Path) -> pd.DataFrame:
    ura = load_ura(private_path)
    ep = load_edgeprop(edgeprop_path)
    mix = load_unit_mix(unit_mix_path)

    mapping = build_name_mapping(ura, ep)
    ura["match_name"] = [mapping.get(k) for k in zip(ura["name_norm"], ura["district"])]
    ura.loc[ura["project_name"].isin(PLACEHOLDER_NAMES), "match_name"] = None

    ura["bedrooms"] = pd.array([pd.NA] * len(ura), dtype="Float64")
    ura["bedroom_source"] = "unknown"
    n_input = len(ura)

    pool = ep[ep["bedrooms"].notna()]

    def _apply(matched: pd.Series, source: str) -> None:
        if matched.empty:
            return
        idx = matched.index
        ura.loc[idx, "bedrooms"] = matched.astype("Float64")
        ura.loc[idx, "bedroom_source"] = source

    _apply(tier1_exact(ura, pool, month_shift=0), "edgeprop_exact")
    for shift in (-1, 1):
        _apply(tier1_exact(ura, pool, month_shift=shift), "edgeprop_exact")

    labels = tier2_band_labels(ep)
    unmatched = ura["bedrooms"].isna() & ura["match_name"].notna()
    band_keys = list(zip(ura.loc[unmatched, "match_name"], ura.loc[unmatched, "district"],
                         ura.loc[unmatched, "area_sqm"].map(band_of)))
    band_values = pd.Series([labels.get(k) for k in band_keys],
                            index=ura.index[unmatched], dtype="Float64").dropna()
    _apply(band_values, "edgeprop_band_label")

    _apply(tier3_unit_mix(ura, mix), "research_unit_mix")
    placeholder = ura["project_name"].isin(PLACEHOLDER_NAMES)
    ura.loc[placeholder, "bedrooms"] = pd.NA
    ura.loc[placeholder, "bedroom_source"] = "unknown"
    assert len(ura) == n_input, "URA rows fanned out during matching"

    # EdgeProp-only 2019-2020 backfill rows (URA file starts 2021-06)
    bf = ep[ep["sale_year"].between(2019, 2020)].copy()
    bf["bedroom_source"] = bf["bedrooms"].notna().map(
        {True: "edgeprop_exact", False: "unknown"})
    still = bf["bedrooms"].isna()
    bf_band_keys = list(zip(bf.loc[still, "name_norm"], bf.loc[still, "district"],
                            bf.loc[still, "ep_sqm"].map(band_of)))
    bf_band = pd.Series([labels.get(k) for k in bf_band_keys],
                        index=bf.index[still], dtype="Float64").dropna()
    bf.loc[bf_band.index, "bedrooms"] = bf_band
    bf.loc[bf_band.index, "bedroom_source"] = "edgeprop_band_label"
    if not mix.empty and bf["bedrooms"].isna().any():
        bf_mix_in = bf.loc[bf["bedrooms"].isna(), ["name_norm", "district", "ep_sqm"]].rename(
            columns={"ep_sqm": "area_sqm"}).assign(bedrooms=pd.NA)
        bf_mix = tier3_unit_mix(bf_mix_in, mix)
        bf.loc[bf_mix.index, "bedrooms"] = bf_mix.astype("Float64")
        bf.loc[bf_mix.index, "bedroom_source"] = "research_unit_mix"

    ura_out = pd.DataFrame({
        "project_name": ura["project_name"],
        "project_name_norm": ura["name_norm"],
        "postal_district": ura["district"],
        "planning_area": ura.get("planning_area", ""),
        "property_type": ura["property_type"],
        "tenure": ura["tenure"],
        "sale_month": ura["sale_month"],
        "type_of_sale": ura["type_of_sale"],
        "transacted_price": ura["price_int"],
        "area_sqm": ura["area_sqm"],
        "floor_level": ura.get("floor_level", ""),
        "data_source": "ura_private",
        "bedrooms": ura["bedrooms"],
        "bedroom_source": ura["bedroom_source"],
    })
    bf_out = pd.DataFrame({
        "project_name": bf["project_upper"],
        "project_name_norm": bf["name_norm"],
        "postal_district": bf["district"],
        "planning_area": bf["planning_area"],
        "property_type": bf["Type"],
        "tenure": bf["Tenure"],
        "sale_month": bf["sale_month"],
        "type_of_sale": bf["Sale Type"],
        "transacted_price": bf["price_int"],
        "area_sqm": bf["ep_sqm"].round(1),
        "floor_level": "",
        "data_source": "edgeprop_backfill",
        "bedrooms": bf["bedrooms"],
        "bedroom_source": bf["bedroom_source"],
    })
    out = pd.concat([ura_out, bf_out], ignore_index=True)
    out["bedrooms"] = out["bedrooms"].astype("Float64").round().astype("Int64")
    out = out.sort_values(
        ["data_source", "postal_district", "project_name", "sale_month",
         "transacted_price", "area_sqm"], kind="stable").reset_index(drop=True)
    return out


def summarise(out: pd.DataFrame) -> float:
    total = len(out)
    print(f"\n{total:,} transactions ({(out['data_source'] == 'ura_private').sum():,} URA + "
          f"{(out['data_source'] == 'edgeprop_backfill').sum():,} EdgeProp 2019-20 backfill)")
    print("\nAttribution by source:")
    for source, n in out["bedroom_source"].value_counts().items():
        print(f"  {source:20s} {n:7,}  ({n / total * 100:5.1f}%)")
    attributed = (out["bedroom_source"] != "unknown").mean()
    worst = (out.assign(known=out["bedroom_source"] != "unknown")
             .groupby("postal_district")["known"].mean().sort_values())
    print("\nLowest-attribution districts:")
    for d, share in worst.head(5).items():
        print(f"  D{d}: {share * 100:.1f}%")
    print(f"\nOverall attributed: {attributed * 100:.2f}%")
    if attributed < 0.95:
        print("WARNING: below the 95% attribution target")
    return attributed


def write_gap_report(out: pd.DataFrame, ep: pd.DataFrame, path: pathlib.Path) -> None:
    ep_projects = set(zip(ep["name_norm"], ep["district"]))
    rows = []
    for (name, norm, district), grp in out.groupby(
            ["project_name", "project_name_norm", "postal_district"]):
        n_unknown = int((grp["bedroom_source"] == "unknown").sum())
        if n_unknown == 0:
            continue
        in_ep = (norm, district) in ep_projects
        reason = ("placeholder" if name in PLACEHOLDER_NAMES
                  else "partial_match" if in_ep else "no_edgeprop_project")
        rows.append({"project_name": name, "project_name_norm": norm,
                     "postal_district": district, "total_txns": len(grp),
                     "unattributed_txns": n_unknown, "in_edgeprop": in_ep,
                     "reason": reason})
    report = pd.DataFrame(rows).sort_values(
        ["unattributed_txns", "project_name"], ascending=[False, True], kind="stable")
    report.to_csv(path, index=False)
    print(f"\nGap report: {path} ({len(report)} projects, "
          f"{report['unattributed_txns'].sum():,} unattributed txns)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Attribute bedrooms to private condo/apt transactions")
    ap.add_argument("--private", default=str(DEFAULT_PRIVATE))
    ap.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    ap.add_argument("--unit-mix", default=str(DEFAULT_UNIT_MIX))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--report", action="store_true",
                    help="also write the per-project gap report (research queue)")
    args = ap.parse_args()

    out = build(pathlib.Path(args.private), pathlib.Path(args.edgeprop),
                pathlib.Path(args.unit_mix))
    out.to_csv(args.out, index=False)
    print(f"Written: {args.out}")
    summarise(out)
    if args.report:
        ep = load_edgeprop(pathlib.Path(args.edgeprop))
        write_gap_report(out, ep, DEFAULT_REPORT)


if __name__ == "__main__":
    main()
