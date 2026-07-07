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


def _fmt(value, digits=0):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _esc(value) -> str:
    return html_mod.escape(str(value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-district private comparison HTML")
    parser.add_argument("--district", action="append", required=True,
                        help="Postal district (repeatable), e.g. --district 17 --district 27")
    parser.add_argument("--private", default=str(DEFAULT_PRIVATE))
    parser.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    parser.add_argument("--ura-raw-dir", default=str(DEFAULT_URA_RAW_DIR))
    parser.add_argument("--out-dir", default=str(ROOT))
    args = parser.parse_args()
    for district in args.district:
        out_path, n_rows = generate(
            district,
            pathlib.Path(args.private),
            pathlib.Path(args.edgeprop),
            pathlib.Path(args.ura_raw_dir),
            pathlib.Path(args.out_dir),
        )
        print(f"Written: {out_path} ({out_path.stat().st_size // 1024} KB, {n_rows} projects)")




AREA_BANDS = [
    ("le50", "≤50 sqm", 0.0, 50.0),
    ("50to70", "50–70 sqm", 50.0, 70.0),
    ("70to100", "70–100 sqm", 70.0, 100.0),
    ("100to130", "100–130 sqm", 100.0, 130.0),
    ("gt130", ">130 sqm", 130.0, float("inf")),
]
BAND_ORDER = ["all"] + [key for key, _, _, _ in AREA_BANDS]
BAND_LABELS = {"all": "All", **{key: label for key, label, _, _ in AREA_BANDS}}


def band_of(area_sqm: float) -> str:
    for key, _, lo, hi in AREA_BANDS:
        if lo < area_sqm <= hi:
            return key
    return AREA_BANDS[0][0]  # loaders guarantee area > 0; defensive default


def load_edgeprop_bedroom_labels(path: pathlib.Path, district: str) -> dict:
    """(display_project, band_key) -> '≈nBR'. Labels only; prices never merged from here."""
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
    project = df["Project"].astype(str).str.strip().str.upper()
    street = df["Street"].astype(str).str.strip().str.upper()
    df["display_project"] = [display_project(p, s) for p, s in zip(project, street)]
    df["band"] = df["area_sqm"].map(band_of)
    labels = {}
    for (proj, band), grp in df.groupby(["display_project", "band"]):
        if len(grp) < 3:
            continue
        counts = grp["bedrooms"].value_counts()
        if counts.iloc[0] / len(grp) >= 0.7:
            labels[(proj, band)] = f"≈{counts.index[0]}BR"
    return labels


def _render_summary_cards(summary: dict, growth_list_fn) -> str:
    yearly_cells = "".join(
        f"<td class='num'>{_fmt(summary['yearly'][y][0])}"
        f"<div class='n'>n={summary['yearly'][y][1]}</div></td>"
        for y in YEARS
    )
    yearly_heads = "".join(f"<th class='num'>{y}</th>" for y in YEARS)
    return (
        "<div class=\"summary\">"
        "<div class=\"card\"><h3>Median PSF by year</h3>"
        f"<table><tr>{yearly_heads}</tr><tr>{yearly_cells}</tr></table></div>"
        f"<div class=\"card\"><h3>Top growth</h3><ul>{growth_list_fn(summary['top_growth'])}</ul></div>"
        f"<div class=\"card\"><h3>Bottom growth</h3><ul>{growth_list_fn(summary['bottom_growth'])}</ul></div>"
        "</div>"
    )


def _render_project_table(band_key: str, rows: list[dict], bedroom_labels: dict) -> str:
    show_bedrooms = band_key != "all"
    year_heads = "".join(f"<th class='num sortable'>{y}</th>" for y in YEARS)
    bedroom_head = "<th class='sortable'>Bedrooms</th>" if show_bedrooms else ""
    body_rows = []
    for r in rows:
        year_cells = []
        for y in YEARS:
            median, n = r["year_stats"][y]
            if n >= MIN_YEAR_N and median is not None:
                year_cells.append(
                    f"<td class='num' data-v='{median:.0f}' title='n={n}'>{_fmt(median)}</td>"
                )
            else:
                year_cells.append(f"<td class='num muted' data-v='' title='n={n}'>—</td>")
        growth = r["growth_pct"]
        if growth is None:
            growth_cell = "<td class='num muted' data-v=''>—</td>"
        else:
            cls = "pos" if growth >= 0 else "neg"
            growth_cell = (
                f"<td class='num {cls}' data-v='{growth:.2f}' "
                f"title='{r['growth_from']}&rarr;{r['growth_to']}'>{growth:+.1f}%/yr</td>"
            )
        badge = (
            " <span class='badge' title='includes EdgeProp 2019&ndash;2020 backfill rows"
            " (incomplete coverage)'>backfill</span>"
            if r["has_edgeprop_backfill"] else ""
        )
        bedroom_cell = ""
        if show_bedrooms:
            label = bedroom_labels.get((r["project"], band_key), "")
            v = _esc(label) if label else ""
            bedroom_cell = f"<td data-v='{v}'>{v or '&mdash;'}</td>"
        psf_v = "" if r["latest_median_psf"] is None else f"{r['latest_median_psf']:.0f}"
        price_v = "" if r["latest_median_price"] is None else f"{r['latest_median_price']:.0f}"
        body_rows.append(
            "<tr>"
            f"<td data-v='{_esc(r['project'])}'>{_esc(r['project'])}{badge}</td>"
            f"<td data-v='{_esc(r['property_types'])}'>{_esc(r['property_types'])}</td>"
            f"<td data-v='{_esc(r['tenure'])}'>{_esc(r['tenure'])}</td>"
            + bedroom_cell
            + f"<td class='num' data-v='{r['n_total']}'>{r['n_total']}</td>"
            + "".join(year_cells)
            + growth_cell
            + f"<td class='num' data-v='{psf_v}'>{_fmt(r['latest_median_psf'])}</td>"
            + f"<td class='num' data-v='{price_v}'>{_fmt(r['latest_median_price'])}</td>"
            "</tr>"
        )
    return (
        "<table class=\"ptable\">"
        "<thead><tr>"
        "<th class=\"sortable\">Project</th><th class=\"sortable\">Type</th>"
        "<th class=\"sortable\">Tenure</th>"
        + bedroom_head +
        "<th class=\"num sortable\">Txns</th>" + year_heads +
        "<th class=\"num sortable\">Growth %/yr</th>"
        "<th class=\"num sortable\">Latest median PSF</th>"
        "<th class=\"num sortable\">Latest median price</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def render_html(district: str, per_band: dict, bedroom_labels: dict) -> str:
    district_name = DISTRICT_NAMES.get(district, f"District {district}")

    def _growth_list(items):
        if not items:
            return "<li class='muted'>—</li>"
        return "".join(
            f"<li>{_esc(i['project'])} <span class='{'pos' if i['growth_pct'] >= 0 else 'neg'}'>"
            f"{i['growth_pct']:+.1f}%/yr</span></li>"
            for i in items
        )

    band_keys = [k for k in BAND_ORDER if k in per_band]
    tab_buttons = "".join(
        f"<button class=\"tab{' active' if key == band_keys[0] else ''}\" "
        f"data-band=\"{key}\">{BAND_LABELS[key]}</button>"
        for key in band_keys
    )
    sections = []
    for key in band_keys:
        rows, summary = per_band[key]
        active = " active" if key == band_keys[0] else ""
        sections.append(
            f"<section id=\"band-{key}\" class=\"band{active}\">"
            f"<div class=\"bandmeta\">{BAND_LABELS[key]} &middot; "
            f"{summary['total_txns']:,} transactions &middot; {len(rows)} projects</div>"
            + _render_summary_cards(summary, _growth_list)
            + _render_project_table(key, rows, bedroom_labels)
            + "</section>"
        )
    total_txns = per_band[band_keys[0]][1]["total_txns"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>D{district} Private Property Comparison ({district_name})</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 24px; color: #1a1a2e; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .caveat {{ background: #fff7e0; border: 1px solid #e8c96a; border-radius: 8px;
             padding: 10px 14px; margin: 12px 0 20px; font-size: 13px; max-width: 900px; }}
  .tabs {{ margin: 0 0 16px; display: flex; gap: 6px; flex-wrap: wrap; }}
  .tab {{ border: 1px solid #ccd; background: #f4f4fa; border-radius: 6px 6px 0 0;
          padding: 6px 14px; font-size: 13px; cursor: pointer; }}
  .tab.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}
  section.band {{ display: none; }}
  section.band.active {{ display: block; }}
  .bandmeta {{ font-size: 13px; color: #555; margin-bottom: 10px; }}
  .summary {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 20px; }}
  .summary .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .summary h3 {{ margin: 0 0 6px; font-size: 13px; }}
  .summary ul {{ margin: 0; padding-left: 18px; }}
  table {{ border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 5px 9px; border-bottom: 1px solid #e4e4ee; text-align: left; white-space: nowrap; }}
  th {{ background: #f4f4fa; position: sticky; top: 0; cursor: pointer; user-select: none; }}
  td.num, th.num {{ text-align: right; }}
  .muted {{ color: #9a9ab0; }}
  .pos {{ color: #0a7a3d; }}
  .neg {{ color: #b02a2a; }}
  .badge {{ background: #fdecc8; color: #8a6100; border-radius: 4px; padding: 1px 5px; font-size: 11px; }}
  .n {{ font-size: 10px; color: #9a9ab0; }}
</style>
</head>
<body>
<h1>District {district} &mdash; {_esc(district_name)}: Private Property Comparison</h1>
<div>Window: 2019&ndash;2026 &middot; median PSF (S$) by sale year &middot; {total_txns:,} transactions</div>
<div class="caveat">&#9888; 2019&ndash;2020 condo/apartment rows are backfilled from an incomplete EdgeProp scrape
(the canonical URA feed only reaches back to 2021). Pre-2021 medians are indicative only &mdash;
projects using that data carry a <span class="badge">backfill</span> badge. Landed 2019&ndash;2020 rows
come from raw URA PMI downloads. Year cells show &mdash; when the year has fewer than {MIN_YEAR_N} transactions.
Bedroom labels (&asymp;nBR) are estimates derived from EdgeProp unit listings per size band, shown only when
at least 3 units agree &ge;70%.</div>
<div class="tabs">{tab_buttons}</div>
{"".join(sections)}
<script>
document.querySelectorAll('.tab').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    document.querySelectorAll('.tab').forEach(function (b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('section.band').forEach(function (s) {{ s.classList.remove('active'); }});
    btn.classList.add('active');
    document.getElementById('band-' + btn.dataset.band).classList.add('active');
  }});
}});
document.querySelectorAll('.ptable').forEach(function (table) {{
  var tbody = table.querySelector('tbody');
  table.querySelectorAll('th').forEach(function (th, idx) {{
    th.addEventListener('click', function () {{
      var rows = Array.from(tbody.rows);
      var dir = th.dataset.dir === 'asc' ? -1 : 1;
      table.querySelectorAll('th').forEach(function (h) {{ delete h.dataset.dir; }});
      th.dataset.dir = dir === 1 ? 'asc' : 'desc';
      rows.sort(function (a, b) {{
        var av = a.cells[idx].dataset.v, bv = b.cells[idx].dataset.v;
        if (av === '' && bv === '') return 0;
        if (av === '') return 1;
        if (bv === '') return -1;
        var an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return (an - bn) * dir;
        return av.localeCompare(bv) * dir;
      }});
      rows.forEach(function (r) {{ tbody.appendChild(r); }});
    }});
  }});
}});
</script>
</body>
</html>
"""


def generate(district, private_path, edgeprop_path, raw_dir, out_dir):
    district = normalise_district(district)
    frames = [
        load_canonical(private_path, district),
        load_edgeprop_backfill(edgeprop_path, district),
        load_ura_raw_backfill(raw_dir, district),
    ]
    non_empty = [f for f in frames if not f.empty]
    merged = pd.concat(non_empty, ignore_index=True) if non_empty else _empty_unified()
    bedroom_labels = load_edgeprop_bedroom_labels(edgeprop_path, district)
    per_band = {}
    all_rows = aggregate_projects(merged)
    per_band["all"] = (all_rows, district_summary(merged, all_rows))
    for key, _, lo, hi in AREA_BANDS:
        sub = merged[(merged["area_sqm"] > lo) & (merged["area_sqm"] <= hi)]
        band_rows = aggregate_projects(sub)
        per_band[key] = (band_rows, district_summary(sub, band_rows))
    out_path = pathlib.Path(out_dir) / f"private_project_comparison_D{district}.html"
    out_path.write_text(render_html(district, per_band, bedroom_labels), encoding="utf-8")
    return out_path, len(all_rows)


if __name__ == "__main__":
    main()
