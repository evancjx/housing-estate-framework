#!/usr/bin/env python3
"""
Compare private condo/apartment transactions between EXACTLY TWO postal districts.

Scope: condominium / apartment / executive condominium ONLY - landed property
types (*House) are excluded (same convention as gen_district_private_comparison_html:
rows whose property_type contains "House" are dropped by the shared loaders).

Three comparison axes, presented as aggregated side-by-side tables (District A | District B):
  1. Size        - median PSF / median price / n per floor-area band (sqm).
  2. Bedrooms    - median PSF / median price / n per bedroom count. URA has no bedroom
                   field; bedroom counts come ONLY from the EdgeProp "not_clean" feed. Since
                   that feed carries the same exact unit size, each URA transaction is labelled
                   by matching on (project + exact area_sqm), falling back to a per-(project,
                   size-band) modal label (gen_district_private_comparison_html.load_edgeprop_bedroom_counts).
                   Labels only - prices are never merged. Reported coverage % shows how many
                   transactions received a bedroom label.
  3. MRT distance- distribution of each project's straight-line distance to its nearest
                   MRT station. Reported twice: nearest OPERATIONAL station, and nearest
                   INCLUDING future/under-construction stations (mrt_layer operational=0),
                   flagged separately. Per-project coordinates come from the committed
                   OneMap geocode layer (data/private_project_locations.csv); projects
                   without a geocode are excluded from the distance stats and their count
                   is surfaced as coverage, rather than imputed to a shared centroid.

Reads:
  data/ura_private.csv                                   - canonical URA private txns (2021+)
  data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv  - 2019-2020 backfill + bedrooms
  data/private_project_locations.csv                     - OneMap project lat/lon
  data/mrt_layer.csv                                     - station coords + operational flag

Writes:
  two_district_comparison_D{A}_D{B}.html  (repo root)

Run:
  python3 models/gen_two_district_comparison_html.py --district 18 --district 26
  # Lentor = District 26, Pasir Ris = District 18

INPUT CONTRACT
  ura_private.csv:   project_name, street_name, postal_district, property_type, tenure,
                     sale_month (YYYY-MM), transacted_price, area_sqm, unit_price_psm, type_of_sale
  edgeprop csv:      Project, Street, Postal District, Date of Sale, Type, Tenure, Sale Type,
                     Price ($), Area (sqm), Area (sqft), Unit Price ($psf), Bedrooms
  private_project_locations.csv: project_name, street_name, postal_district, planning_area,
                     lat, lon, match_status, match_score
  mrt_layer.csv:     lat, lon, name, stn_code, line, operational (1=open, 0=future)
"""

from __future__ import annotations

import argparse
import html as html_mod
import pathlib

import pandas as pd

# Reuse the vetted condo/apartment loaders + size/bedroom logic.
from gen_district_private_comparison_html import (
    AREA_BANDS,
    BAND_LABELS,
    BAND_ORDER,
    BEDROOM_LABELS,
    BEDROOM_ORDER,
    DEFAULT_EDGEPROP,
    DEFAULT_PRIVATE,
    band_of,
    bedroom_class,
    load_canonical,
    load_edgeprop_backfill,
    load_edgeprop_bedroom_counts,
    normalise_district,
)

# Reuse the vetted nearest-station / haversine logic.
from gen_private_project_comparison_html import nearest_station

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_LOCATIONS = ROOT / "data/private_project_locations.csv"
DEFAULT_MRT = ROOT / "data/mrt_layer.csv"

# Distance bands for the MRT-distance distribution (metres).
MRT_BANDS = [
    ("le400", "≤400 m", 0.0, 400.0),
    ("400to800", "400–800 m", 400.0, 800.0),
    ("800to1200", "800–1200 m", 800.0, 1200.0),
    ("gt1200", ">1200 m", 1200.0, float("inf")),
]
MRT_BAND_ORDER = [key for key, _, _, _ in MRT_BANDS]
MRT_BAND_LABELS = {key: label for key, label, _, _ in MRT_BANDS}

DISTRICT_NAMES = {
    "18": "Tampines / Pasir Ris",
    "26": "Upper Thomson / Springleaf / Lentor",
    "17": "Changi / Loyang / Pasir Ris",
    "27": "Yishun / Sembawang",
}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_unified(private_path: pathlib.Path, edgeprop_path: pathlib.Path, district: str) -> pd.DataFrame:
    """Condo/apartment transactions for one district: URA (2021+) + EdgeProp 2019-2020 backfill.

    Returns the shared UNIFIED_COLUMNS frame; landed already excluded by the loaders.
    """
    frames = [load_canonical(private_path, district)]
    backfill = load_edgeprop_backfill(edgeprop_path, district)
    if not backfill.empty:
        frames.append(backfill)
    df = pd.concat(frames, ignore_index=True)
    return df


def load_edgeprop_bedroom_by_size(path: pathlib.Path, district: str,
                                  min_n: int = 2, min_share: float = 0.6) -> dict:
    """(PROJECT_UPPER, round(area_sqm)) -> modal bedroom count.

    Bedrooms live only in the EdgeProp feed, but that feed carries the SAME exact
    floor area as the URA rows, so a bedroom count can be transferred onto a URA
    transaction by matching on (project, exact unit size) instead of a coarse size
    band. Same conservative guard as the band labeller (>=min_n units, >=min_share
    modal agreement); prices are never merged, only the bedroom label.
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"Postal District": str, "Bedrooms": str})
    df = df[df["Postal District"].map(normalise_district) == district].copy()
    df["bedrooms"] = pd.to_numeric(df["Bedrooms"], errors="coerce")
    df["area_sqm"] = pd.to_numeric(df["Area (sqm)"], errors="coerce")
    df = df.dropna(subset=["bedrooms", "area_sqm"])
    df = df[(df["bedrooms"] > 0) & (df["area_sqm"] > 0)]
    if df.empty:
        return {}
    df["bedrooms"] = df["bedrooms"].astype(int)
    df["project_u"] = df["Project"].astype(str).str.strip().str.upper()
    df["area_r"] = df["area_sqm"].round(0).astype(int)
    labels = {}
    for (proj, area_r), grp in df.groupby(["project_u", "area_r"]):
        if len(grp) < min_n:
            continue
        counts = grp["bedrooms"].value_counts()
        if counts.iloc[0] / len(grp) >= min_share:
            labels[(proj, int(area_r))] = int(counts.index[0])
    return labels


def load_project_coords(path: pathlib.Path, district: str) -> dict[str, dict]:
    """{PROJECT_NAME_UPPER: {lat, lon, match_status}} for one district.

    Keyed by project name alone (project names are effectively unique within a district),
    so the geocode layer joins to load_canonical's uppercased project column without
    needing an exact street/area match.
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"postal_district": str})
    df = df[df["postal_district"].map(normalise_district) == district].copy()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        key = str(row["project_name"]).strip().upper()
        if key in out:
            continue  # first geocode wins; names are unique enough within a district
        out[key] = {
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "match_status": str(row.get("match_status", "")).strip() or "-",
        }
    return out


def load_stations(path: pathlib.Path) -> tuple[list[dict], list[dict]]:
    """Return (all_stations, operational_only) as record lists for nearest_station()."""
    mrt = pd.read_csv(path)
    all_stations = mrt.to_dict("records")
    operational = mrt[pd.to_numeric(mrt["operational"], errors="coerce").fillna(1) == 1]
    return all_stations, operational.to_dict("records")


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _stats(sub: pd.DataFrame) -> dict:
    return {
        "n": int(len(sub)),
        "median_psf": float(sub["psf"].median()) if len(sub) else None,
        "median_price": float(sub["price"].median()) if len(sub) else None,
        "median_sqm": float(sub["area_sqm"].median()) if len(sub) else None,
    }


def size_breakdown(df: pd.DataFrame) -> dict:
    """band_key -> stats, plus 'all'."""
    out = {"all": _stats(df)}
    band = df["area_sqm"].map(band_of)
    for key, _, _, _ in AREA_BANDS:
        out[key] = _stats(df[band == key])
    return out


def resolve_bedroom(project: str, area_sqm: float, size_labels: dict, band_labels: dict):
    """Bedroom count for a URA transaction: exact-size EdgeProp label first, band fallback."""
    exact = size_labels.get((project, int(round(area_sqm))))
    if exact is not None:
        return exact
    return band_labels.get((project, band_of(area_sqm)))


def bedroom_breakdown(df: pd.DataFrame, size_labels: dict, band_labels: dict) -> dict:
    """bedroom_class -> stats. Bedrooms come from EdgeProp, matched to each URA txn by
    exact unit size (project + rounded area_sqm), falling back to the per-(project, band)
    modal label when the exact size has no confident label."""
    df = df.copy()
    # Compute the bedroom class directly so pandas never coerces missing labels to NaN
    # (bedroom_class expects None, not float NaN, for the Unknown bucket).
    df["bedroom_class"] = [
        bedroom_class(resolve_bedroom(proj, area, size_labels, band_labels))
        for proj, area in zip(df["project"], df["area_sqm"])
    ]
    out = {}
    for key in BEDROOM_ORDER:
        out[key] = _stats(df[df["bedroom_class"] == key])
    return out


def mrt_breakdown(df: pd.DataFrame, coords: dict, all_stations: list, op_stations: list) -> dict:
    """Per-district nearest-MRT distance distribution over geocoded, transacting projects."""
    projects = sorted(df["project"].dropna().unique())
    per_project = []
    for proj in projects:
        loc = coords.get(proj)
        if not loc:
            per_project.append({"project": proj, "geocoded": False})
            continue
        op = nearest_station(loc["lat"], loc["lon"], op_stations)
        anyst = nearest_station(loc["lat"], loc["lon"], all_stations)
        per_project.append({
            "project": proj,
            "geocoded": True,
            "op_station": op["station_display"],
            "op_dist_m": op["station_distance_m"],
            "any_station": anyst["station_display"],
            "any_dist_m": anyst["station_distance_m"],
            "any_status": anyst["station_status"],
        })
    geocoded = [p for p in per_project if p["geocoded"]]
    op_dists = sorted(p["op_dist_m"] for p in geocoded)
    any_dists = sorted(p["any_dist_m"] for p in geocoded)

    def _median(xs):
        if not xs:
            return None
        m = len(xs) // 2
        return float(xs[m]) if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0

    band_counts = {key: 0 for key in MRT_BAND_ORDER}
    for d in op_dists:
        for key, _, lo, hi in MRT_BANDS:
            if lo < d <= hi or (lo == 0.0 and d <= hi):
                band_counts[key] += 1
                break

    # Does including future stations change any project's nearest station?
    future_improves = [p for p in geocoded if p["any_dist_m"] < p["op_dist_m"]]

    return {
        "n_projects_total": len(projects),
        "n_projects_geocoded": len(geocoded),
        "op_median_m": _median(op_dists),
        "op_min_m": op_dists[0] if op_dists else None,
        "op_max_m": op_dists[-1] if op_dists else None,
        "any_median_m": _median(any_dists),
        "within_400m": sum(1 for d in op_dists if d <= 400),
        "within_800m": sum(1 for d in op_dists if d <= 800),
        "band_counts": band_counts,
        "future_improves": [
            {"project": p["project"], "op": p["op_station"], "op_m": p["op_dist_m"],
             "future": p["any_station"], "future_m": p["any_dist_m"]}
            for p in future_improves
        ],
        "per_project": sorted(geocoded, key=lambda p: p["op_dist_m"]),
    }


def build_district(private_path, edgeprop_path, locations_path, all_stations, op_stations,
                   district) -> dict:
    df = load_unified(private_path, edgeprop_path, district)
    size_labels = load_edgeprop_bedroom_by_size(edgeprop_path, district)
    band_labels = load_edgeprop_bedroom_counts(edgeprop_path, district)
    coords = load_project_coords(locations_path, district)
    bedrooms = bedroom_breakdown(df, size_labels, band_labels)
    n_known = int(len(df)) - bedrooms["brunknown"]["n"]
    return {
        "district": district,
        "name": DISTRICT_NAMES.get(district, ""),
        "n_txns": int(len(df)),
        "n_projects": int(df["project"].nunique()),
        "headline": _stats(df),
        "size": size_breakdown(df),
        "bedrooms": bedrooms,
        "bedroom_coverage_pct": round(100.0 * n_known / len(df), 1) if len(df) else 0.0,
        "mrt": mrt_breakdown(df, coords, all_stations, op_stations),
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _fmt(value, digits=0):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _esc(value) -> str:
    return html_mod.escape(str(value))


def _stat_cells(s: dict) -> str:
    return (
        f"<td class='num'>{_fmt(s['median_psf'])}</td>"
        f"<td class='num'>{_fmt(s['median_price'])}</td>"
        f"<td class='num'>{_fmt(s['median_sqm'])}</td>"
        f"<td class='num n'>{s['n']}</td>"
    )


def _paired_table(caption, row_order, row_labels, a_map, b_map, a, b) -> str:
    heads = (
        "<tr><th rowspan='2'>Band</th>"
        f"<th colspan='4'>D{a['district']} · {_esc(a['name'])}</th>"
        f"<th colspan='4'>D{b['district']} · {_esc(b['name'])}</th></tr>"
        "<tr>"
        + "<th class='num'>PSF</th><th class='num'>Price</th><th class='num'>Size m²</th><th class='num'>n</th>" * 2
        + "</tr>"
    )
    body = []
    for key in row_order:
        sa, sb = a_map.get(key), b_map.get(key)
        if (not sa or sa["n"] == 0) and (not sb or sb["n"] == 0):
            continue
        label = row_labels.get(key, key)
        body.append(
            f"<tr><td class='band'>{_esc(label)}</td>"
            f"{_stat_cells(sa or {'median_psf': None, 'median_price': None, 'median_sqm': None, 'n': 0})}"
            f"{_stat_cells(sb or {'median_psf': None, 'median_price': None, 'median_sqm': None, 'n': 0})}</tr>"
        )
    return (
        f"<h2>{_esc(caption)}</h2>"
        f"<table class='cmp'>{heads}{''.join(body)}</table>"
    )


def _mrt_section(a, b) -> str:
    ma, mb = a["mrt"], b["mrt"]

    def summary_card(d, m):
        future_note = ""
        if m["future_improves"]:
            items = "".join(
                f"<li>{_esc(p['project'])}: {_esc(p['op'])} {p['op_m']:,} m "
                f"&rarr; {_esc(p['future'])} {p['future_m']:,} m (future)</li>"
                for p in m["future_improves"]
            )
            future_note = f"<div class='future'><b>Future stations bring closer:</b><ul>{items}</ul></div>"
        else:
            future_note = "<div class='future muted'>No future/under-construction station is nearer than the operational one.</div>"
        return (
            f"<div class='card'><h3>D{d['district']} · {_esc(d['name'])}</h3>"
            f"<table class='kv'>"
            f"<tr><td>Projects (geocoded / total)</td><td class='num'>{m['n_projects_geocoded']} / {m['n_projects_total']}</td></tr>"
            f"<tr><td>Median nearest MRT (operational)</td><td class='num'>{_fmt(m['op_median_m'])} m</td></tr>"
            f"<tr><td>Closest / farthest project</td><td class='num'>{_fmt(m['op_min_m'])} / {_fmt(m['op_max_m'])} m</td></tr>"
            f"<tr><td>Projects ≤400 m</td><td class='num'>{m['within_400m']}</td></tr>"
            f"<tr><td>Projects ≤800 m</td><td class='num'>{m['within_800m']}</td></tr>"
            f"<tr><td>Median nearest MRT (incl. future)</td><td class='num'>{_fmt(m['any_median_m'])} m</td></tr>"
            f"</table>{future_note}</div>"
        )

    # Distance-band distribution, side by side.
    dist_rows = []
    for key in MRT_BAND_ORDER:
        ca, cb = ma["band_counts"][key], mb["band_counts"][key]
        if ca == 0 and cb == 0:
            continue
        dist_rows.append(
            f"<tr><td class='band'>{_esc(MRT_BAND_LABELS[key])}</td>"
            f"<td class='num'>{ca}</td><td class='num'>{cb}</td></tr>"
        )
    dist_table = (
        "<table class='cmp'><tr><th>Nearest operational MRT</th>"
        f"<th class='num'>D{a['district']} projects</th>"
        f"<th class='num'>D{b['district']} projects</th></tr>"
        f"{''.join(dist_rows)}</table>"
    )
    return (
        "<h2>MRT distance</h2>"
        f"<div class='cards'>{summary_card(a, ma)}{summary_card(b, mb)}</div>"
        f"{dist_table}"
        "<p class='note'>Distance is straight-line (haversine) from each project's OneMap "
        "geocode to the nearest station. Projects without a committed geocode are excluded "
        "from these stats (see geocoded / total counts).</p>"
    )


def _headline_row(a, b) -> str:
    def cells(d):
        h = d["headline"]
        return (
            f"<td class='num'>{d['n_txns']:,}</td><td class='num'>{d['n_projects']:,}</td>"
            f"<td class='num'>{_fmt(h['median_psf'])}</td><td class='num'>{_fmt(h['median_price'])}</td>"
            f"<td class='num'>{_fmt(h['median_sqm'])}</td>"
        )
    return (
        "<table class='cmp'><tr><th>District</th><th class='num'>Txns</th><th class='num'>Projects</th>"
        "<th class='num'>Median PSF</th><th class='num'>Median Price</th><th class='num'>Median m²</th></tr>"
        f"<tr><td class='band'>D{a['district']} · {_esc(a['name'])}</td>{cells(a)}</tr>"
        f"<tr><td class='band'>D{b['district']} · {_esc(b['name'])}</td>{cells(b)}</tr>"
        "</table>"
    )


CSS = """
:root{color-scheme:light dark;}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px;
     line-height:1.4;color:#1a1a1a;background:#fff;}
h1{font-size:1.5rem;margin:0 0 4px;}
h2{font-size:1.15rem;margin:28px 0 8px;border-bottom:2px solid #e2e2e2;padding-bottom:4px;}
h3{font-size:1rem;margin:0 0 8px;}
.sub{color:#666;margin:0 0 16px;}
table{border-collapse:collapse;width:100%;margin:8px 0 4px;font-size:0.86rem;}
th,td{border:1px solid #ddd;padding:5px 8px;text-align:left;}
th{background:#f4f4f6;font-weight:600;}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;}
td.band{font-weight:600;}
td.n{color:#777;}
table.cmp th:nth-child(6),table.cmp td:nth-child(6){border-left:2px solid #bbb;}
.cards{display:flex;gap:16px;flex-wrap:wrap;}
.card{flex:1 1 320px;border:1px solid #e0e0e0;border-radius:8px;padding:12px 14px;background:#fafafa;}
table.kv td:first-child{border:none;padding:2px 8px 2px 0;}
table.kv td:last-child{border:none;padding:2px 0;}
table.kv{width:auto;}
.future{margin-top:8px;font-size:0.82rem;}
.future ul{margin:4px 0 0;padding-left:18px;}
.muted{color:#888;}
.note{color:#666;font-size:0.8rem;margin:6px 0 0;}
.caveats{background:#fff8e1;border:1px solid #ffe0a3;border-radius:8px;padding:10px 14px;
         font-size:0.82rem;margin:16px 0;}
@media(prefers-color-scheme:dark){
 body{background:#161616;color:#e8e8e8;}
 th{background:#242424;}th,td{border-color:#333;}
 .card{background:#1e1e1e;border-color:#333;}
 h2{border-color:#333;}
 .caveats{background:#2a2410;border-color:#5a4a1a;}
}
"""


def render_html(a: dict, b: dict) -> str:
    title = f"D{a['district']} vs D{b['district']} — private condo/apartment comparison"
    caveats = (
        "<div class='caveats'><b>Scope & caveats.</b> Condominium / apartment / EC only; "
        "landed excluded. Prices from URA (2021+) plus EdgeProp 2019–2020 backfill. "
        "<b>Bedroom counts</b> come only from the EdgeProp <code>not_clean</code> feed (URA has no "
        "bedroom field). Because that feed carries the same exact unit size, each URA transaction "
        "is labelled by matching on (project + exact area), falling back to a per-(project, size-band) "
        "modal label; prices are never merged. Remaining <em>Unknown</em> rows are projects EdgeProp "
        "has not scraped bedrooms for (typically the newest launches). <b>MRT distance</b> uses "
        "committed OneMap project geocodes; ungeocoded projects are excluded from distance stats.</div>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(title)}</title><style>{CSS}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f"<p class='sub'>Aggregated side-by-side. D{a['district']} = {_esc(a['name'])} · "
        f"D{b['district']} = {_esc(b['name'])}.</p>"
        f"{caveats}"
        "<h2>Headline</h2>" + _headline_row(a, b)
        + _paired_table("Size (floor-area bands)", BAND_ORDER, BAND_LABELS, a["size"], b["size"], a, b)
        + _paired_table(
            f"Bedrooms (EdgeProp, matched by unit size) — coverage "
            f"D{a['district']} {a['bedroom_coverage_pct']:.0f}% · "
            f"D{b['district']} {b['bedroom_coverage_pct']:.0f}%",
            BEDROOM_ORDER, BEDROOM_LABELS, a["bedrooms"], b["bedrooms"], a, b)
        + _mrt_section(a, b)
        + "</body></html>"
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def generate(district_a, district_b, private_path, edgeprop_path, locations_path,
             mrt_path, out_dir) -> tuple[pathlib.Path, dict, dict]:
    all_stations, op_stations = load_stations(mrt_path)
    a = build_district(private_path, edgeprop_path, locations_path, all_stations, op_stations, district_a)
    b = build_district(private_path, edgeprop_path, locations_path, all_stations, op_stations, district_b)
    out_path = pathlib.Path(out_dir) / f"two_district_comparison_D{district_a}_D{district_b}.html"
    out_path.write_text(render_html(a, b), encoding="utf-8")
    return out_path, a, b


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare private condo/apartment transactions between exactly two districts")
    parser.add_argument("--district", action="append", required=True,
                        help="Postal district (give EXACTLY two), e.g. --district 18 --district 26")
    parser.add_argument("--private", default=str(DEFAULT_PRIVATE))
    parser.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    parser.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    parser.add_argument("--mrt", default=str(DEFAULT_MRT))
    parser.add_argument("--out-dir", default=str(ROOT))
    args = parser.parse_args()

    districts = [normalise_district(d) for d in args.district]
    if len(districts) != 2:
        parser.error(f"exactly two --district values required, got {len(districts)}: {districts}")
    if districts[0] == districts[1]:
        parser.error(f"the two districts must differ, got {districts[0]} twice")

    out_path, a, b = generate(
        districts[0], districts[1],
        pathlib.Path(args.private), pathlib.Path(args.edgeprop),
        pathlib.Path(args.locations), pathlib.Path(args.mrt), args.out_dir,
    )
    print(f"Written: {out_path} ({out_path.stat().st_size // 1024} KB)")
    print(f"  D{a['district']}: {a['n_txns']:,} txns, {a['n_projects']} projects, "
          f"median PSF {_fmt(a['headline']['median_psf'])}, "
          f"median nearest MRT {_fmt(a['mrt']['op_median_m'])} m")
    print(f"  D{b['district']}: {b['n_txns']:,} txns, {b['n_projects']} projects, "
          f"median PSF {_fmt(b['headline']['median_psf'])}, "
          f"median nearest MRT {_fmt(b['mrt']['op_median_m'])} m")


if __name__ == "__main__":
    main()
