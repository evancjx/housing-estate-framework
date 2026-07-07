"""
Generate per-district private property comparison pages (trend-focused).

Reads:
  data/ura_private.csv - canonical URA private transactions (2021+; owns 2021-2026)
  data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
                       - EdgeProp scrape; ONLY 2019-2020 rows used (condo/apartment backfill)
  data/ura_raw/pmi_d{NN}_landed_non_strata_2019-2026.csv   (optional per district)
  data/ura_raw/pmi_d{NN}_strata_landed_2019-2026.csv       (optional per district)
                       - raw URA PMI landed downloads; ONLY 2019-2020 rows used

Writes:
  private_project_comparison_D{NN}.html  (repo root; one per --district)

Run:
  python3 models/gen_district_private_comparison_html.py --district 17 --district 27

INPUT CONTRACT
  ura_private.csv columns: project_name, street_name, postal_district, property_type,
    tenure, sale_month (YYYY-MM), transacted_price, area_sqm, unit_price_psm, type_of_sale
  edgeprop csv columns: Project, Street, Postal District, Date of Sale (DD Mon YYYY),
    Type, Tenure, Sale Type, Price ($), Area (sqm), Area (sqft), Unit Price ($psf)
  ura_raw pmi csv columns: Project Name, Street Name, Postal District, Property Type,
    Tenure, Sale Date (Mon-YY), Transacted Price ($), Area (SQFT), Area (SQM),
    Unit Price ($ PSF), Type of Sale
  Backfill invariant: EdgeProp and ura_raw loaders never emit sale_year outside 2019-2020.
"""

from __future__ import annotations

import argparse
import html as html_mod
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
YEARS = list(range(2019, 2027))
SQM_TO_SQFT = 10.7639
MIN_YEAR_N = 3
UNIFIED_COLUMNS = [
    "project", "street", "property_type", "tenure", "sale_year",
    "price", "area_sqm", "psf", "sale_type", "source",
]
DISTRICT_NAMES = {
    "17": "Changi / Loyang / Pasir Ris",
    "27": "Yishun / Sembawang",
}
DEFAULT_PRIVATE = ROOT / "data/ura_private.csv"
DEFAULT_EDGEPROP = ROOT / "data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
DEFAULT_URA_RAW_DIR = ROOT / "data/ura_raw"


def normalise_district(value) -> str:
    text = str(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(2)[-2:] if digits else ""


def load_canonical(path: pathlib.Path, district: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"postal_district": str})
    df = df[df["postal_district"].map(normalise_district) == district].copy()
    out = pd.DataFrame({
        "project": df["project_name"].astype(str).str.strip().str.upper(),
        "street": df["street_name"].astype(str).str.strip().str.upper(),
        "property_type": df["property_type"].astype(str).str.strip(),
        "tenure": df["tenure"].astype(str).str.strip(),
        "sale_year": pd.to_numeric(df["sale_month"].astype(str).str[:4], errors="coerce"),
        "price": pd.to_numeric(df["transacted_price"], errors="coerce"),
        "area_sqm": pd.to_numeric(df["area_sqm"], errors="coerce"),
        "psf": pd.to_numeric(df["unit_price_psm"], errors="coerce") / SQM_TO_SQFT,
        "sale_type": df["type_of_sale"].astype(str).str.strip(),
        "source": "ura_private",
    })
    out = out.dropna(subset=["sale_year", "price", "area_sqm"])
    out = out[(out["price"] > 0) & (out["area_sqm"] > 0)]
    out["sale_year"] = out["sale_year"].astype(int)
    return out[UNIFIED_COLUMNS].reset_index(drop=True)


def _empty_unified() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIFIED_COLUMNS)


def load_edgeprop_backfill(path: pathlib.Path, district: str) -> pd.DataFrame:
    if not path.exists():
        return _empty_unified()
    df = pd.read_csv(path, dtype={"Postal District": str})
    df = df[df["Postal District"].map(normalise_district) == district].copy()
    df["sale_dt"] = pd.to_datetime(df["Date of Sale"], format="%d %b %Y", errors="coerce")
    df = df.dropna(subset=["sale_dt"])
    df["sale_year"] = df["sale_dt"].dt.year
    df = df[df["sale_year"].between(2019, 2020)]
    df["price"] = pd.to_numeric(df["Price ($)"], errors="coerce")
    df["area_sqm"] = pd.to_numeric(df["Area (sqm)"], errors="coerce")
    df["psf_raw"] = pd.to_numeric(df["Unit Price ($psf)"], errors="coerce")
    df = df.dropna(subset=["price", "area_sqm"])
    df = df[(df["price"] > 0) & (df["area_sqm"] > 0)]
    df = df.drop_duplicates(subset=["Project", "Date of Sale", "Price ($)", "Area (sqft)"])
    derived_psf = df["price"] / (df["area_sqm"] * SQM_TO_SQFT)
    out = pd.DataFrame({
        "project": df["Project"].astype(str).str.strip().str.upper(),
        "street": df["Street"].astype(str).str.strip().str.upper(),
        "property_type": df["Type"].astype(str).str.strip(),
        "tenure": df["Tenure"].astype(str).str.strip(),
        "sale_year": df["sale_year"].astype(int),
        "price": df["price"],
        "area_sqm": df["area_sqm"],
        "psf": df["psf_raw"].where(df["psf_raw"] > 0, derived_psf),
        "sale_type": df["Sale Type"].astype(str).str.strip(),
        "source": "edgeprop_backfill",
    })
    return out[UNIFIED_COLUMNS].reset_index(drop=True)


def _comma_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def load_ura_raw_backfill(raw_dir: pathlib.Path, district: str) -> pd.DataFrame:
    frames = []
    stems = (
        f"pmi_d{district}_landed_non_strata_2019-2026.csv",
        f"pmi_d{district}_strata_landed_2019-2026.csv",
    )
    for stem in stems:
        path = raw_dir / stem
        if not path.exists():
            print(f"WARN: {path} missing; skipping landed backfill file")
            continue
        df = pd.read_csv(path, dtype={"Postal District": str})
        df = df[df["Postal District"].map(normalise_district) == district].copy()
        df["sale_dt"] = pd.to_datetime(df["Sale Date"], format="%b-%y", errors="coerce")
        df = df.dropna(subset=["sale_dt"])
        df["sale_year"] = df["sale_dt"].dt.year
        df = df[df["sale_year"].between(2019, 2020)]
        if df.empty:
            continue
        out = pd.DataFrame({
            "project": df["Project Name"].astype(str).str.strip().str.upper(),
            "street": df["Street Name"].astype(str).str.strip().str.upper(),
            "property_type": df["Property Type"].astype(str).str.strip(),
            "tenure": df["Tenure"].astype(str).str.strip(),
            "sale_year": df["sale_year"].astype(int),
            "price": _comma_numeric(df["Transacted Price ($)"]),
            "area_sqm": _comma_numeric(df["Area (SQM)"]),
            "psf": _comma_numeric(df["Unit Price ($ PSF)"]),
            "sale_type": df["Type of Sale"].astype(str).str.strip(),
            "source": "ura_raw_backfill",
        })
        out = out.dropna(subset=["price", "area_sqm"])
        out = out[(out["price"] > 0) & (out["area_sqm"] > 0)]
        frames.append(out[UNIFIED_COLUMNS])
    if not frames:
        return _empty_unified()
    return pd.concat(frames, ignore_index=True)


def annualised_growth(year_stats: dict) -> tuple | None:
    qualifying = sorted(
        year for year, (median, n) in year_stats.items()
        if n >= MIN_YEAR_N and median is not None and median > 0
    )
    if len(qualifying) < 2:
        return None
    y0, y1 = qualifying[0], qualifying[-1]
    p0 = year_stats[y0][0]
    p1 = year_stats[y1][0]
    rate = (p1 / p0) ** (1.0 / (y1 - y0)) - 1.0
    return rate, y0, y1


GENERIC_LANDED_NAME = "LANDED HOUSING DEVELOPMENT"


def display_project(project: str, street: str) -> str:
    if project == GENERIC_LANDED_NAME:
        return f"{GENERIC_LANDED_NAME} ({street})"
    return project


def mode_text(series: pd.Series, default: str = "-") -> str:
    values = series.dropna()
    values = values[values.astype(str).str.strip() != ""]
    if values.empty:
        return default
    return str(values.mode().iloc[0])


def _year_stats(grp: pd.DataFrame) -> dict:
    stats = {}
    for year in YEARS:
        sub = grp[grp["sale_year"] == year]
        median = float(sub["psf"].median()) if len(sub) else None
        stats[year] = (median, int(len(sub)))
    return stats


def aggregate_projects(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["display_project"] = [
        display_project(p, s) for p, s in zip(df["project"], df["street"])
    ]
    rows = []
    for name, grp in df.groupby("display_project"):
        stats = _year_stats(grp)
        growth = annualised_growth(stats)
        active_years = [y for y in YEARS if stats[y][1] > 0]
        latest_year = active_years[-1] if active_years else None
        latest = grp[grp["sale_year"] == latest_year] if latest_year else grp.iloc[0:0]
        types = sorted(t for t in grp["property_type"].dropna().unique() if str(t).strip())
        rows.append({
            "project": name,
            "street": mode_text(grp["street"]),
            "property_types": " / ".join(types) if types else "-",
            "tenure": mode_text(grp["tenure"]),
            "n_total": int(len(grp)),
            "year_stats": stats,
            "growth_pct": growth[0] * 100.0 if growth else None,
            "growth_from": growth[1] if growth else None,
            "growth_to": growth[2] if growth else None,
            "latest_year": latest_year,
            "latest_median_psf": float(latest["psf"].median()) if len(latest) else None,
            "latest_median_price": float(latest["price"].median()) if len(latest) else None,
            "has_edgeprop_backfill": bool((grp["source"] == "edgeprop_backfill").any()),
        })
    rows.sort(key=lambda r: (-r["n_total"], r["project"]))
    return rows


def district_summary(df: pd.DataFrame, rows: list[dict]) -> dict:
    with_growth = [r for r in rows if r["growth_pct"] is not None]
    ranked = sorted(with_growth, key=lambda r: r["growth_pct"], reverse=True)
    return {
        "total_txns": int(len(df)),
        "yearly": _year_stats(df),
        "top_growth": ranked[:3],
        "bottom_growth": ranked[::-1][:3],
    }
