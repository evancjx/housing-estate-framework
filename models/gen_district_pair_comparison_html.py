"""
Generate a two-district private property comparison page (condo/apartment ONLY).

Compares transactions between two postal districts along three axes:
  1. distance from project to nearest OPERATIONAL MRT station (banded)
  2. number of bedrooms (per transaction, from the EdgeProp scrape)
  3. property size (sqft bands)

Landed property types (*House) are excluded. Bedrooms come from the EdgeProp
scrape because URA PMI transaction rows carry no bedroom column; EdgeProp's
public tables label their source as URA, so rows are per-transaction URA data
with bedrooms attached (source_quality=not_clean caveat applies).

Reads:
  data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
  data/outputs/private_project_locations.csv  - reviewed OneMap geocodes
  data/inputs/mrt_layer.csv                   - stations (operational flag)

Writes:
  district_pair_comparison_D{A}_D{B}.html  (repo root)

Run:
  python3 models/gen_district_pair_comparison_html.py --district-a 18 --district-b 26 \
      --label-a "Pasir Ris / Tampines" --label-b "Lentor / Upper Thomson"

INPUT CONTRACT
  edgeprop csv columns: Project, Postal District, Date of Sale (DD Mon YYYY),
    Bedrooms, Price ($), Area (sqft), Area (sqm), Unit Price ($psf), Type
  locations csv columns: project_name, lat, lon
  mrt csv columns: lat, lon, name, stn_code, line, operational (1/0)
"""

from __future__ import annotations

import argparse
import html as html_mod
import math
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_EDGEPROP = ROOT / "data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
DEFAULT_LOCATIONS = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_MRT = ROOT / "data/inputs/mrt_layer.csv"

SIZE_BANDS = [(0, 600), (600, 800), (800, 1000), (1000, 1300), (1300, math.inf)]
MRT_BANDS = [(0, 400), (400, 800), (800, 1200), (1200, math.inf)]


def normalise_district(value) -> str:
    text = str(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(2)[-2:] if digits else ""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def band_label(bands: list[tuple], value: float, unit: str) -> str:
    for lo, hi in bands:
        if lo <= value < hi:
            if hi == math.inf:
                return f"{lo:,.0f}+ {unit}"
            if lo == 0:
                return f"under {hi:,.0f} {unit}"
            return f"{lo:,.0f}–{hi:,.0f} {unit}"
    return "unknown"


def load_transactions(path: pathlib.Path, district: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"Postal District": str}, low_memory=False)
    df = df[df["Postal District"].map(normalise_district) == district].copy()
    df = df[~df["Type"].astype(str).str.contains("House", case=False, na=False)]
    df["sale_dt"] = pd.to_datetime(df["Date of Sale"], format="%d %b %Y", errors="coerce")
    df["price"] = pd.to_numeric(df["Price ($)"], errors="coerce")
    df["sqft"] = pd.to_numeric(df["Area (sqft)"], errors="coerce")
    df["psf"] = pd.to_numeric(df["Unit Price ($psf)"], errors="coerce")
    df["bedrooms"] = pd.to_numeric(df["Bedrooms"], errors="coerce")
    df = df.dropna(subset=["sale_dt", "price", "sqft"])
    df = df[(df["price"] > 0) & (df["sqft"] > 0)]
    derived_psf = df["price"] / df["sqft"]
    df["psf"] = df["psf"].where(df["psf"] > 0, derived_psf)
    df = df.drop_duplicates(subset=["Project", "Date of Sale", "Price ($)", "Area (sqft)"])
    df["project"] = df["Project"].astype(str).str.strip().str.upper()
    df["sale_year"] = df["sale_dt"].dt.year.astype(int)
    return df[["project", "sale_year", "price", "sqft", "psf", "bedrooms", "Type"]].reset_index(drop=True)


def nearest_station_by_project(projects: list[str], locations: pd.DataFrame,
                               mrt: pd.DataFrame) -> dict[str, dict]:
    stations = mrt[pd.to_numeric(mrt["operational"], errors="coerce").fillna(1) == 1]
    stations = stations.dropna(subset=["lat", "lon"])
    loc = locations.copy()
    loc["project"] = loc["project_name"].astype(str).str.strip().str.upper()
    loc = loc.dropna(subset=["lat", "lon"]).drop_duplicates(subset=["project"])
    coords = loc.set_index("project")[["lat", "lon"]]
    out: dict[str, dict] = {}
    for project in projects:
        if project not in coords.index:
            continue
        plat, plon = float(coords.loc[project, "lat"]), float(coords.loc[project, "lon"])
        best, best_d = None, math.inf
        for row in stations.itertuples():
            d = haversine_m(plat, plon, float(row.lat), float(row.lon))
            if d < best_d:
                best, best_d = row, d
        out[project] = {
            "distance_m": best_d,
            "station": str(best.name).strip(),
            "line": str(best.line).strip(),
        }
    return out


def cell_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0, "psf": None, "price": None, "sqft": None}
    return {
        "n": int(len(df)),
        "psf": float(df["psf"].median()),
        "price": float(df["price"].median()),
        "sqft": float(df["sqft"].median()),
    }


def _fmt(value, digits=0):
    return "—" if value is None else f"{value:,.{digits}f}"


def _esc(value) -> str:
    return html_mod.escape(str(value))


def _stat_cells(s: dict) -> str:
    return (f"<td class='num'>{s['n']:,}</td><td class='num'>${_fmt(s['psf'])}</td>"
            f"<td class='num'>${_fmt(s['price'])}</td><td class='num'>{_fmt(s['sqft'])}</td>")


def comparison_table(title: str, note: str, row_labels: list[str],
                     cells_a: list[dict], cells_b: list[dict],
                     label_a: str, label_b: str, row_head: str) -> str:
    head = (f"<tr><th rowspan='2'>{_esc(row_head)}</th>"
            f"<th colspan='4'>{_esc(label_a)}</th><th colspan='4'>{_esc(label_b)}</th></tr>"
            "<tr>" + "<th>Txns</th><th>Median PSF</th><th>Median price</th><th>Median sqft</th>" * 2 + "</tr>")
    body = []
    for label, sa, sb in zip(row_labels, cells_a, cells_b):
        body.append(f"<tr><td>{_esc(label)}</td>{_stat_cells(sa)}{_stat_cells(sb)}</tr>")
    return (f"<section><h2>{_esc(title)}</h2><p class='note'>{_esc(note)}</p>"
            f"<table>{head}{''.join(body)}</table></section>")


def project_mrt_table(df: pd.DataFrame, mrt_info: dict[str, dict], label: str) -> str:
    rows = []
    for project, grp in sorted(df.groupby("project"), key=lambda kv: -len(kv[1])):
        info = mrt_info.get(project)
        dist = f"{info['distance_m']:,.0f}" if info else "—"
        station = f"{info['station']} ({info['line']})" if info else "no geocode"
        rows.append(f"<tr><td>{_esc(project)}</td><td>{_esc(station)}</td>"
                    f"<td class='num'>{dist}</td><td class='num'>{len(grp):,}</td>"
                    f"<td class='num'>${_fmt(float(grp['psf'].median()))}</td></tr>")
    return (f"<h3>{_esc(label)} — projects</h3>"
            "<table><tr><th>Project</th><th>Nearest open MRT</th><th>Distance (m)</th>"
            "<th>Txns</th><th>Median PSF</th></tr>" + "".join(rows) + "</table>")


def build_page(da: str, db: str, label_a: str, label_b: str,
               ta: pd.DataFrame, tb: pd.DataFrame,
               mrt_a: dict, mrt_b: dict) -> str:
    def overview(label, d, df, mrt_info):
        geocoded = df["project"].isin(mrt_info).mean() * 100 if len(df) else 0
        return (f"<div class='card'><h3>{_esc(label)} (D{d})</h3>"
                f"<p><b>{len(df):,}</b> condo/apartment transactions · "
                f"<b>{df['project'].nunique()}</b> projects · "
                f"{int(df['sale_year'].min())}–{int(df['sale_year'].max())}</p>"
                f"<p>Median PSF <b>${_fmt(float(df['psf'].median()))}</b> · "
                f"median price <b>${_fmt(float(df['price'].median()))}</b> · "
                f"median size <b>{_fmt(float(df['sqft'].median()))} sqft</b></p>"
                f"<p class='note'>{geocoded:.0f}% of transactions geocoded for MRT distance</p></div>")

    sections = [f"<div class='cards'>{overview(label_a, da, ta, mrt_a)}{overview(label_b, db, tb, mrt_b)}</div>"]

    bed_rows = ["1", "2", "3", "4", "5+"]
    def bed_cells(df):
        cells = []
        for b in bed_rows:
            if b == "5+":
                cells.append(cell_stats(df[df["bedrooms"] >= 5]))
            else:
                cells.append(cell_stats(df[df["bedrooms"] == int(b)]))
        return cells
    n_nobed_a = int(ta["bedrooms"].isna().sum())
    n_nobed_b = int(tb["bedrooms"].isna().sum())
    sections.append(comparison_table(
        "By number of bedrooms",
        f"Per-transaction bedroom counts from the EdgeProp scrape (URA-sourced). "
        f"Rows without a bedroom value are excluded here: {n_nobed_a} in D{da}, {n_nobed_b} in D{db}.",
        [f"{b} bedroom" + ("s" if b != "1" else "") for b in bed_rows],
        bed_cells(ta), bed_cells(tb), label_a, label_b, "Bedrooms"))

    size_labels = [band_label(SIZE_BANDS, lo, "sqft") for lo, _ in SIZE_BANDS]
    def size_cells(df):
        return [cell_stats(df[(df["sqft"] >= lo) & (df["sqft"] < hi)]) for lo, hi in SIZE_BANDS]
    sections.append(comparison_table(
        "By property size", "Strata floor area as scraped (sqft).",
        size_labels, size_cells(ta), size_cells(tb), label_a, label_b, "Size band"))

    mrt_labels = [band_label(MRT_BANDS, lo, "m") for lo, _ in MRT_BANDS]
    def mrt_cells(df, mrt_info):
        dist = df["project"].map(lambda p: mrt_info.get(p, {}).get("distance_m"))
        cells = []
        for lo, hi in MRT_BANDS:
            cells.append(cell_stats(df[(dist >= lo) & (dist < hi)]))
        return cells
    sections.append(comparison_table(
        "By walking distance to nearest open MRT station",
        "Straight-line distance from the geocoded project location to the nearest "
        "OPERATIONAL station in data/inputs/mrt_layer.csv; every transaction in a "
        "project inherits its project's distance. Ungeocoded projects are excluded.",
        mrt_labels, mrt_cells(ta, mrt_a), mrt_cells(tb, mrt_b), label_a, label_b, "MRT distance"))

    sections.append(f"<section><h2>Project detail</h2>{project_mrt_table(ta, mrt_a, f'{label_a} (D{da})')}"
                    f"{project_mrt_table(tb, mrt_b, f'{label_b} (D{db})')}</section>")

    style = """
    body{font-family:-apple-system,Segoe UI,sans-serif;margin:24px;color:#1a1a1a;max-width:1100px}
    h1{font-size:22px} h2{font-size:17px;margin-top:28px} h3{font-size:14px}
    table{border-collapse:collapse;width:100%;margin:8px 0 20px;font-size:13px}
    th,td{border:1px solid #d5d5d5;padding:5px 8px;text-align:left}
    th{background:#f2f2f2} td.num{text-align:right;font-variant-numeric:tabular-nums}
    .cards{display:flex;gap:16px;flex-wrap:wrap} .card{border:1px solid #d5d5d5;border-radius:8px;padding:4px 16px;flex:1;min-width:320px}
    .note{color:#666;font-size:12px}
    @media (prefers-color-scheme: dark){body{background:#111;color:#eee}th{background:#222}th,td,.card{border-color:#444}.note{color:#aaa}}
    """
    caveat = ("Source: EdgeProp public transaction tables (labelled URA), source_quality=not_clean; "
              "condo/apartment/EC only, landed excluded. Medians only — no mix adjustment; "
              "compare like-for-like rows (same bedroom count or size band), not headline medians.")
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>D{da} vs D{db} private comparison</title><style>{style}</style></head><body>"
            f"<h1>{_esc(label_a)} (D{da}) vs {_esc(label_b)} (D{db}) — condo/apartment transactions</h1>"
            f"<p class='note'>{caveat}</p>" + "".join(sections) + "</body></html>")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate two-district private comparison HTML")
    ap.add_argument("--district-a", required=True)
    ap.add_argument("--district-b", required=True)
    ap.add_argument("--label-a", default="")
    ap.add_argument("--label-b", default="")
    ap.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    ap.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    ap.add_argument("--mrt", default=str(DEFAULT_MRT))
    ap.add_argument("--out-dir", default=str(ROOT))
    args = ap.parse_args()

    da, db = normalise_district(args.district_a), normalise_district(args.district_b)
    label_a = args.label_a or f"District {da}"
    label_b = args.label_b or f"District {db}"

    ta = load_transactions(pathlib.Path(args.edgeprop), da)
    tb = load_transactions(pathlib.Path(args.edgeprop), db)
    if ta.empty or tb.empty:
        raise SystemExit(f"ERROR: no condo/apartment rows for D{da} ({len(ta)}) or D{db} ({len(tb)})")

    locations = pd.read_csv(args.locations)
    mrt = pd.read_csv(args.mrt)
    mrt_a = nearest_station_by_project(sorted(ta["project"].unique()), locations, mrt)
    mrt_b = nearest_station_by_project(sorted(tb["project"].unique()), locations, mrt)

    html = build_page(da, db, label_a, label_b, ta, tb, mrt_a, mrt_b)
    out = pathlib.Path(args.out_dir) / f"district_pair_comparison_D{da}_D{db}.html"
    out.write_text(html, encoding="utf-8")
    print(f"Written: {out} ({len(ta):,} D{da} rows, {len(tb):,} D{db} rows)")


if __name__ == "__main__":
    main()
