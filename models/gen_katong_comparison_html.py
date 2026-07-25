#!/usr/bin/env python3
"""
Generate the Katong condominium comparison and transaction explorer.

This is a project diagnostic on the Liveability/Value side of the framework.
It does not create a unified project ranking or feed project facts into the
estate-level Provision score.

Reads:
  data/inputs/katong_project_profiles.csv
      name,url,slug,cohort,role,official_units,completion_label,
      tenure_profile,micro_market,official_source_url,why_compare,best_fit,
      key_risk,future_context
  data/outputs/private_transactions_bedrooms.csv
      project_name,planning_area,property_type,tenure,sale_month,type_of_sale,
      transacted_price,area_sqm,floor_level,data_source,bedrooms,
      bedroom_source
  data/outputs/private_project_locations.csv
      project_name,lat,lon
  data/outputs/private_project_school_metrics.csv
      project_name,primary_1km_count,primary_1km_schools
  data/inputs/mrt_layer.csv
      name,stn_code,line,lat,lon,operational
  data/raw/edgeprop/edgeprop_condo_unit_transactions.csv (optional)
      Project,Date of Sale,Address,unit_number,unit_floor,unit_stack,
      unit_number_status,unit_number_source,Bedrooms,Unit Price ($psf),
      Price ($),Sale Type,Area (sqft),source_url

Writes:
  katong_condo_comparison.html

Method:
  - Headline distributions use the latest 18 complete calendar months.
  - Growth compares the latest and preceding 12 complete months and is shown
    only when both samples contain at least three transactions.
  - Liquidity is latest-12-month caveats divided by official project units,
    not unique sellers.
  - New sale, sub-sale and resale evidence remains selectable and is never
    silently pooled.
  - Exact-unit analysis accepts only rows explicitly tagged ``exact`` with
    one unmasked published unit token. Masked unit numbers are never inferred.
"""

from __future__ import annotations

import argparse
import html
import math
import pathlib
import re
from datetime import date
from typing import Any

import pandas as pd


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_PROFILES = ROOT / "data/inputs/katong_project_profiles.csv"
DEFAULT_TRANSACTIONS = ROOT / "data/outputs/private_transactions_bedrooms.csv"
DEFAULT_LOCATIONS = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_SCHOOLS = ROOT / "data/outputs/private_project_school_metrics.csv"
DEFAULT_MRT = ROOT / "data/inputs/mrt_layer.csv"
DEFAULT_UNITS = ROOT / "data/raw/edgeprop/edgeprop_condo_unit_transactions.csv"
DEFAULT_OUT = ROOT / "katong_condo_comparison.html"

SQM_TO_SQFT = 10.7639
MIN_GROWTH_SAMPLE = 3
PROFILE_COLUMNS = {
    "name",
    "url",
    "slug",
    "cohort",
    "role",
    "official_units",
    "completion_label",
    "tenure_profile",
    "micro_market",
    "official_source_url",
    "why_compare",
    "best_fit",
    "key_risk",
    "future_context",
}
SALE_STATES = {
    "all": "All caveats",
    "new-sale": "New sale",
    "sub-sale": "Sub-sale",
    "resale": "Resale",
}
BEDROOMS = {
    "all": "All bedrooms",
    "1": "1 bedroom",
    "2": "2 bedrooms",
    "3": "3 bedrooms",
    "4": "4 bedrooms",
    "5-plus": "5+ bedrooms",
}
UNIT_NUMBER_RE = re.compile(
    r"^#(?P<floor>(?![X*?]+$)[A-Z0-9]{1,4})-"
    r"(?P<stack>(?![X*?]+$)[A-Z0-9]{1,6})$",
    re.I,
)


def normalise_project(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def clean_text(value: Any, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    value = str(value).strip()
    return value if value and value.casefold() not in {"nan", "none"} else default


def esc(value: Any) -> str:
    return html.escape(clean_text(value), quote=True)


def load_profiles(path: pathlib.Path) -> pd.DataFrame:
    profiles = pd.read_csv(path)
    missing = sorted(PROFILE_COLUMNS - set(profiles.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    profiles = profiles.copy()
    profiles["project"] = profiles["name"].map(normalise_project)
    if profiles["project"].duplicated().any():
        duplicate = sorted(profiles.loc[profiles["project"].duplicated(), "project"].unique())
        raise SystemExit(f"{path} has duplicate projects: {duplicate}")
    profiles["official_units"] = pd.to_numeric(profiles["official_units"], errors="coerce")
    if profiles["official_units"].isna().any() or (profiles["official_units"] <= 0).any():
        raise SystemExit(f"{path} has invalid official_units")
    return profiles


def _sale_state(value: Any) -> str:
    value = clean_text(value, "").casefold().replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    if value in {"new sale", "new"}:
        return "new-sale"
    if value in {"sub sale", "subsale"}:
        return "sub-sale"
    if value == "resale":
        return "resale"
    return "other"


def _bedroom_bucket(value: Any) -> str:
    if value is None or pd.isna(value):
        return "unknown"
    number = float(value)
    if number >= 5:
        return "5-plus"
    if number in {1, 2, 3, 4}:
        return str(int(number))
    return "unknown"


def load_transactions(path: pathlib.Path, projects: set[str]) -> pd.DataFrame:
    txns = pd.read_csv(path, dtype={"postal_district": str}, low_memory=False)
    required = {
        "project_name",
        "planning_area",
        "property_type",
        "tenure",
        "sale_month",
        "type_of_sale",
        "transacted_price",
        "area_sqm",
        "floor_level",
        "data_source",
        "bedrooms",
        "bedroom_source",
    }
    missing = sorted(required - set(txns.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    txns = txns.copy()
    txns["project"] = txns["project_name"].map(normalise_project)
    txns = txns[txns["project"].isin(projects)]
    txns = txns[
        ~txns["property_type"].astype(str).str.contains(
            "House|Executive Condominium", case=False, na=False
        )
    ]
    txns["sale_state"] = txns["type_of_sale"].map(_sale_state)
    txns = txns[txns["sale_state"].isin(set(SALE_STATES) - {"all"})]
    txns["sale_period"] = pd.to_datetime(txns["sale_month"], errors="coerce").dt.to_period("M")
    txns["price"] = pd.to_numeric(txns["transacted_price"], errors="coerce")
    txns["area_sqm"] = pd.to_numeric(txns["area_sqm"], errors="coerce")
    txns["bedrooms"] = pd.to_numeric(txns["bedrooms"], errors="coerce")
    txns = txns.dropna(subset=["sale_period", "price", "area_sqm"])
    txns = txns[(txns["price"] > 0) & (txns["area_sqm"] > 0)]
    txns["sqft"] = txns["area_sqm"] * SQM_TO_SQFT
    txns["psf"] = txns["price"] / txns["sqft"]
    txns["bedroom_bucket"] = txns["bedrooms"].map(_bedroom_bucket)
    txns["floor_level"] = txns["floor_level"].map(lambda value: clean_text(value, "Unknown"))
    return txns.reset_index(drop=True)


def analysis_periods(txns: pd.DataFrame, as_of: date) -> dict[str, pd.Period | None]:
    if txns.empty:
        raise ValueError("no transactions")
    latest = txns["sale_period"].max()
    current = pd.Period(as_of.strftime("%Y-%m"), freq="M")
    if latest >= current:
        full_end = current - 1
        partial = latest
    else:
        full_end = latest
        partial = None
    return {
        "full_end": full_end,
        "headline_start": full_end - 17,
        "recent_start": full_end - 11,
        "prior_start": full_end - 23,
        "prior_end": full_end - 12,
        "partial": partial,
    }


def _select(
    txns: pd.DataFrame,
    sale_state: str,
    bedroom: str,
    start: pd.Period,
    end: pd.Period,
) -> pd.DataFrame:
    selected = txns[txns["sale_period"].between(start, end)]
    if sale_state != "all":
        selected = selected[selected["sale_state"].eq(sale_state)]
    if bedroom != "all":
        selected = selected[selected["bedroom_bucket"].eq(bedroom)]
    return selected


def describe(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {
            "n": 0,
            "median_price": None,
            "price_p10": None,
            "price_p90": None,
            "median_psf": None,
            "median_sqft": None,
            "known_bedroom_share": None,
        }
    return {
        "n": int(len(group)),
        "median_price": float(group["price"].median()),
        "price_p10": float(group["price"].quantile(0.10)),
        "price_p90": float(group["price"].quantile(0.90)),
        "median_psf": float(group["psf"].median()),
        "median_sqft": float(group["sqft"].median()),
        "known_bedroom_share": float(group["bedrooms"].notna().mean()),
    }


def growth_stats(
    txns: pd.DataFrame,
    sale_state: str,
    bedroom: str,
    periods: dict[str, pd.Period | None],
) -> dict[str, Any]:
    recent = _select(
        txns,
        sale_state,
        bedroom,
        periods["recent_start"],  # type: ignore[arg-type]
        periods["full_end"],  # type: ignore[arg-type]
    )
    prior = _select(
        txns,
        sale_state,
        bedroom,
        periods["prior_start"],  # type: ignore[arg-type]
        periods["prior_end"],  # type: ignore[arg-type]
    )
    recent_psf = float(recent["psf"].median()) if not recent.empty else None
    prior_psf = float(prior["psf"].median()) if not prior.empty else None
    eligible = len(recent) >= MIN_GROWTH_SAMPLE and len(prior) >= MIN_GROWTH_SAMPLE
    growth = (
        (recent_psf / prior_psf - 1.0) * 100.0
        if eligible and recent_psf is not None and prior_psf
        else None
    )
    return {
        "recent_n": int(len(recent)),
        "prior_n": int(len(prior)),
        "recent_psf": recent_psf,
        "prior_psf": prior_psf,
        "growth_pct": growth,
    }


def _lookup(path: pathlib.Path, columns: list[str]) -> dict[str, dict[str, Any]]:
    frame = pd.read_csv(path)
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    frame = frame.copy()
    frame["project"] = frame["project_name"].map(normalise_project)
    return {
        row["project"]: row.to_dict()
        for _, row in frame.drop_duplicates("project", keep="last").iterrows()
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_operational_mrt(
    lat: float | None, lon: float | None, mrt: pd.DataFrame
) -> tuple[str, float | None]:
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return "Location unavailable", None
    stations = mrt.copy()
    if "operational" in stations:
        operational = stations["operational"].astype(str).str.casefold()
        stations = stations[operational.isin({"true", "1", "yes", "y"})]
    stations["lat"] = pd.to_numeric(stations["lat"], errors="coerce")
    stations["lon"] = pd.to_numeric(stations["lon"], errors="coerce")
    stations = stations.dropna(subset=["lat", "lon"])
    if stations.empty:
        return "Station data unavailable", None
    distances = stations.apply(
        lambda row: haversine_m(float(lat), float(lon), float(row["lat"]), float(row["lon"])),
        axis=1,
    )
    nearest = stations.loc[distances.idxmin()]
    name = f"{clean_text(nearest['name'])} {clean_text(nearest.get('stn_code'), '')}".strip()
    return name, float(distances.min())


def load_unit_transactions(path: pathlib.Path, projects: set[str]) -> pd.DataFrame:
    columns = [
        "project",
        "sale_date",
        "sale_period",
        "address",
        "unit_number",
        "unit_floor",
        "unit_stack",
        "unit_number_status",
        "unit_number_source",
        "bedrooms",
        "psf",
        "price",
        "sale_state",
        "sqft",
        "source_url",
        "is_exact",
    ]
    if not path.is_file():
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path, low_memory=False)
    required = {"Project", "Date of Sale", "unit_number_status"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    rename = {
        "Project": "project_name",
        "Date of Sale": "sale_date",
        "Address": "address",
        "Bedrooms": "bedrooms",
        "Unit Price ($psf)": "psf",
        "Price ($)": "price",
        "Sale Type": "sale_type",
        "Area (sqft)": "sqft",
    }
    units = raw.rename(columns=rename).copy()
    for column in {
        "address",
        "unit_number",
        "unit_floor",
        "unit_stack",
        "unit_number_source",
        "bedrooms",
        "psf",
        "price",
        "sale_type",
        "sqft",
        "source_url",
    }:
        if column not in units:
            units[column] = pd.NA
    units["project"] = units["project_name"].map(normalise_project)
    units = units[units["project"].isin(projects)]
    units["sale_date"] = pd.to_datetime(units["sale_date"], errors="coerce", dayfirst=True)
    units["sale_period"] = units["sale_date"].dt.to_period("M")
    units["sale_state"] = units["sale_type"].map(_sale_state)
    for column in {"bedrooms", "psf", "price", "sqft"}:
        units[column] = pd.to_numeric(units[column], errors="coerce")
    status_exact = units["unit_number_status"].astype(str).str.casefold().eq("exact")
    token_exact = units["unit_number"].fillna("").astype(str).str.match(UNIT_NUMBER_RE)
    units["is_exact"] = status_exact & token_exact
    return units[columns].reset_index(drop=True)


def _money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}m"
    return f"${value:,.0f}"


def _number(value: float | None, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.0f}{suffix}"


def _percent(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Insufficient sample"
    return f"{value:+.1f}%"


def build_rows(
    profiles: pd.DataFrame,
    txns: pd.DataFrame,
    locations: dict[str, dict[str, Any]],
    schools: dict[str, dict[str, Any]],
    mrt: pd.DataFrame,
    periods: dict[str, pd.Period | None],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, profile in profiles.iterrows():
        project = profile["project"]
        project_txns = txns[txns["project"].eq(project)]
        location = locations.get(project, {})
        school = schools.get(project, {})
        lat = pd.to_numeric(pd.Series([location.get("lat")]), errors="coerce").iloc[0]
        lon = pd.to_numeric(pd.Series([location.get("lon")]), errors="coerce").iloc[0]
        lat_value = None if pd.isna(lat) else float(lat)
        lon_value = None if pd.isna(lon) else float(lon)
        station, station_m = nearest_operational_mrt(lat_value, lon_value, mrt)
        combinations: dict[tuple[str, str], dict[str, Any]] = {}
        for sale_state in SALE_STATES:
            for bedroom in BEDROOMS:
                window = _select(
                    project_txns,
                    sale_state,
                    bedroom,
                    periods["headline_start"],  # type: ignore[arg-type]
                    periods["full_end"],  # type: ignore[arg-type]
                )
                ttm = _select(
                    project_txns,
                    sale_state,
                    bedroom,
                    periods["recent_start"],  # type: ignore[arg-type]
                    periods["full_end"],  # type: ignore[arg-type]
                )
                stats = describe(window)
                stats["turnover_pct"] = (
                    len(ttm) / float(profile["official_units"]) * 100.0
                )
                stats.update(growth_stats(project_txns, sale_state, bedroom, periods))
                combinations[(sale_state, bedroom)] = stats
        row = profile.to_dict()
        row.update(
            {
                "lat": lat_value,
                "lon": lon_value,
                "nearest_mrt": station,
                "nearest_mrt_m": station_m,
                "primary_1km_count": int(
                    pd.to_numeric(
                        pd.Series([school.get("primary_1km_count")]), errors="coerce"
                    ).fillna(0).iloc[0]
                ),
                "primary_1km_schools": clean_text(
                    school.get("primary_1km_schools"), "None in project diagnostic"
                ),
                "combinations": combinations,
            }
        )
        rows.append(row)
    return rows


def _headline_rows(rows: list[dict[str, Any]]) -> str:
    output = []
    for row in rows:
        for (sale_state, bedroom), stats in row["combinations"].items():
            bedroom_coverage = (
                f"{stats['known_bedroom_share'] * 100:.0f}% bedroom-labelled"
                if stats["known_bedroom_share"] is not None
                else "No matching caveats"
            )
            growth_class = (
                "positive"
                if stats["growth_pct"] is not None and stats["growth_pct"] > 0
                else "negative"
                if stats["growth_pct"] is not None and stats["growth_pct"] < 0
                else ""
            )
            output.append(
                f"""<tr data-project="{esc(row['slug'])}" data-cohort="{esc(row['cohort'])}"
                    data-sale="{sale_state}" data-bed="{bedroom}">
                  <td><a href="{esc(row['url'])}"><b>{esc(row['name'])}</b></a>
                    <small>{esc(row['role'])} · {esc(row['micro_market'])}</small></td>
                  <td>{esc(row['tenure_profile'])}<small>{esc(row['completion_label'])}</small></td>
                  <td>{stats['n']:,}<small>{bedroom_coverage}</small></td>
                  <td><b>{_money(stats['median_price'])}</b><small>P10–P90 {_money(stats['price_p10'])}–{_money(stats['price_p90'])}</small></td>
                  <td><b>{_number(stats['median_psf'], ' psf')}</b><small>{_number(stats['median_sqft'], ' sqft')} median</small></td>
                  <td class="{growth_class}"><b>{_percent(stats['growth_pct'])}</b>
                    <small>n={stats['prior_n']} → n={stats['recent_n']}</small></td>
                  <td><b>{stats['turnover_pct']:.1f}%</b><small>12m caveats / {int(row['official_units']):,} units</small></td>
                  <td><b>{esc(row['nearest_mrt'])}</b><small>{_number(row['nearest_mrt_m'], 'm straight-line')} · {row['primary_1km_count']} primary within 1km</small></td>
                </tr>"""
            )
    return "".join(output)


def _project_buttons(rows: list[dict[str, Any]]) -> str:
    return "".join(
        f'<button class="project-toggle active" data-project="{esc(row["slug"])}" '
        f'aria-pressed="true">{esc(row["name"].title())}</button>'
        for row in rows
    )


def _profile_cards(rows: list[dict[str, Any]]) -> str:
    return "".join(
        f"""<article class="profile">
          <div class="profile-top"><span class="tag">{esc(row['cohort'])}</span><span>{int(row['official_units']):,} units</span></div>
          <h3>{esc(row['name'].title())}</h3>
          <p><b>{esc(row['role'])}.</b> {esc(row['why_compare'])}</p>
          <dl><dt>Buyer fit</dt><dd>{esc(row['best_fit'])}</dd>
              <dt>Control before comparing</dt><dd>{esc(row['key_risk'])}</dd></dl>
        </article>"""
        for row in rows
    )


def _locator_map(rows: list[dict[str, Any]]) -> str:
    located = [row for row in rows if row["lat"] is not None and row["lon"] is not None]
    if not located:
        return '<div class="empty">Project coordinates are unavailable.</div>'
    min_lat = min(row["lat"] for row in located)
    max_lat = max(row["lat"] for row in located)
    min_lon = min(row["lon"] for row in located)
    max_lon = max(row["lon"] for row in located)
    lat_span = max(max_lat - min_lat, 0.001)
    lon_span = max(max_lon - min_lon, 0.001)
    colours = {"Current launches": "#e86a47", "Completed controls": "#386f78"}
    marks = []
    for index, row in enumerate(located, start=1):
        x = 70 + (row["lon"] - min_lon) / lon_span * 760
        y = 410 - (row["lat"] - min_lat) / lat_span * 330
        colour = colours.get(row["cohort"], "#665c4e")
        marks.append(
            f"""<g><circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{colour}"/>
            <text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" class="map-number">{index}</text>
            <text x="{x + 20:.1f}" y="{y - 17:.1f}" class="map-label">{esc(row['name'].title())}</text></g>"""
        )
    key = "".join(
        f"<span><i style=\"background:{colours.get(row['cohort'], '#665c4e')}\">{index}</i>{esc(row['name'].title())}</span>"
        for index, row in enumerate(located, start=1)
    )
    return f"""<div class="map-wrap"><svg viewBox="0 0 900 470" role="img" aria-label="Coordinate-derived Katong project locator">
      <rect width="900" height="470" rx="22" fill="#f4f0e8"/>
      <path d="M40 380 C180 330 270 410 410 362 S700 345 860 285" fill="none" stroke="#b8d9de" stroke-width="26" opacity=".8"/>
      <text x="50" y="440" class="water-label">South / East Coast</text>{''.join(marks)}
    </svg><div class="map-key">{key}</div></div>"""


def _floor_table(rows: list[dict[str, Any]], txns: pd.DataFrame, periods: dict[str, pd.Period | None]) -> str:
    frame = txns[
        txns["sale_period"].between(
            periods["headline_start"], periods["full_end"]  # type: ignore[arg-type]
        )
    ]
    project_order = {row["project"]: index for index, row in enumerate(rows)}
    grouped = (
        frame.groupby(["project", "floor_level"], dropna=False)
        .agg(n=("psf", "size"), median_psf=("psf", "median"), median_price=("price", "median"))
        .reset_index()
    )
    grouped = grouped[grouped["n"] >= MIN_GROWTH_SAMPLE]
    grouped["order"] = grouped["project"].map(project_order)
    grouped = grouped.sort_values(["order", "floor_level"])
    body = "".join(
        f"<tr><td>{esc(record.project.title())}</td><td>{esc(record.floor_level)}</td>"
        f"<td>{int(record.n)}</td><td>{_number(record.median_psf, ' psf')}</td>"
        f"<td>{_money(record.median_price)}</td></tr>"
        for record in grouped.itertuples()
    )
    return (
        "<table><thead><tr><th>Project</th><th>URA floor band</th><th>n</th>"
        "<th>Median achieved PSF</th><th>Median quantum</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _unit_section(units: pd.DataFrame, rows: list[dict[str, Any]]) -> str:
    if units.empty:
        return """<div class="unit-gate">
          <span class="status unavailable">Exact-unit file not supplied</span>
          <h3>No exact apartment claims are being made</h3>
          <p>Public EdgeProp rows usually mask addresses. Add an authorised
          <code>data/raw/edgeprop/edgeprop_condo_unit_transactions.csv</code>
          generated by the repository scraper to activate exact-unit coverage,
          repeat-sale and stack analysis. Masked rows remain coverage evidence only.</p>
        </div>"""
    exact = units[units["is_exact"]].copy()
    counts = units["unit_number_status"].fillna("not_present").astype(str).value_counts()
    summary = " · ".join(f"{esc(status)} {count:,}" for status, count in counts.items())
    coverage = "".join(
        f"""<article class="metric"><span>{esc(row['name'].title())}</span>
            <b>{int(exact['project'].eq(row['project']).sum()):,}</b>
            <small>exact of {int(units['project'].eq(row['project']).sum()):,} supplied rows</small></article>"""
        for row in rows
    )
    repeats = []
    for (project, unit_number), group in exact.dropna(subset=["sale_date"]).groupby(
        ["project", "unit_number"]
    ):
        if len(group) < 2:
            continue
        group = group.sort_values("sale_date")
        first, latest = group.iloc[0], group.iloc[-1]
        psf_change = (
            (latest["psf"] / first["psf"] - 1) * 100
            if pd.notna(first["psf"]) and first["psf"] > 0 and pd.notna(latest["psf"])
            else None
        )
        repeats.append(
            f"<tr><td>{esc(project.title())}</td><td><b>{esc(unit_number)}</b></td>"
            f"<td>{first['sale_date']:%d %b %Y}<small>{_money(first['price'])} · {_number(first['psf'], ' psf')}</small></td>"
            f"<td>{latest['sale_date']:%d %b %Y}<small>{_money(latest['price'])} · {_number(latest['psf'], ' psf')}</small></td>"
            f"<td>{_percent(psf_change)}</td><td>{len(group)}</td></tr>"
        )
    repeat_table = (
        "<table><thead><tr><th>Project</th><th>Exact unit</th><th>First supplied sale</th>"
        "<th>Latest supplied sale</th><th>PSF change</th><th>Records</th></tr></thead>"
        f"<tbody>{''.join(repeats)}</tbody></table>"
        if repeats
        else '<div class="empty">No verified exact unit has two supplied transactions, so repeat-sale growth is unavailable.</div>'
    )
    return f"""<div class="unit-gate"><span class="status available">Authorised unit file supplied</span>
      <p>{summary}. Only verified, unmasked <code>#floor-stack</code> tokens enter exact-unit analysis.</p></div>
      <div class="metrics unit-metrics">{coverage}</div>
      <h3>Verified repeat sales</h3>{repeat_table}"""


def _ledger(txns: pd.DataFrame, profiles: pd.DataFrame) -> str:
    urls = profiles.set_index("project")["url"].to_dict()
    cohorts = profiles.set_index("project")["cohort"].to_dict()
    slugs = profiles.set_index("project")["slug"].to_dict()
    frame = txns.sort_values(["sale_period", "project"], ascending=[False, True])
    output = []
    for row in frame.itertuples():
        bedrooms = (
            f"{int(row.bedrooms)}"
            if pd.notna(row.bedrooms) and float(row.bedrooms).is_integer()
            else "Unknown"
        )
        output.append(
            f"""<tr data-project="{esc(slugs[row.project])}" data-cohort="{esc(cohorts[row.project])}"
                    data-sale="{row.sale_state}" data-bed="{row.bedroom_bucket}"
                    data-search="{esc(row.project)} {esc(row.floor_level)} {bedrooms}">
              <td>{row.sale_period.strftime('%b %Y')}</td>
              <td><a href="{esc(urls[row.project])}">{esc(row.project.title())}</a></td>
              <td>{esc(SALE_STATES[row.sale_state])}</td><td>{bedrooms}</td>
              <td>{esc(row.floor_level)}</td><td>{_number(row.sqft, ' sqft')}</td>
              <td>{_money(row.price)}</td><td>{_number(row.psf, ' psf')}</td>
              <td>{esc(row.data_source)}<small>{esc(row.bedroom_source)}</small></td>
            </tr>"""
        )
    return "".join(output)


def _source_register(rows: list[dict[str, Any]], periods: dict[str, pd.Period | None]) -> str:
    project_sources = "".join(
        f'<li><a href="{esc(row["official_source_url"])}">{esc(row["name"].title())} project facts</a> '
        f'— {esc(row["tenure_profile"])}, {int(row["official_units"]):,} units, {esc(row["completion_label"])}.</li>'
        for row in rows
    )
    return f"""<div class="source-grid"><div><h3>Transaction and method sources</h3><ul>
      <li><a href="https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch">URA private residential transaction search</a> — achieved caveats, latest 60 months.</li>
      <li><a href="https://eservice.ura.gov.sg/reis/coverageandMethodology">URA REALIS coverage and methodology</a> — caveat coverage limitations.</li>
      <li>Headline window: {periods['headline_start']}–{periods['full_end']}; growth windows:
        {periods['prior_start']}–{periods['prior_end']} and {periods['recent_start']}–{periods['full_end']}.</li>
      <li>Bedroom labels retain their source field. MRT and school diagnostics are coordinate-derived and not official walking or home-school distances.</li>
      </ul></div><div><h3>Project fact sources</h3><ul>{project_sources}</ul></div></div>"""


def render_html(
    rows: list[dict[str, Any]],
    profiles: pd.DataFrame,
    txns: pd.DataFrame,
    units: pd.DataFrame,
    periods: dict[str, pd.Period | None],
    as_of: date,
) -> str:
    partial_note = (
        f"The source contains {periods['partial']}; it is treated as partial and excluded from headline statistics."
        if periods["partial"] is not None
        else "No partial source month was detected."
    )
    state_options = "".join(
        f'<option value="{key}">{label}</option>' for key, label in SALE_STATES.items()
    )
    bed_options = "".join(
        f'<option value="{key}">{label}</option>' for key, label in BEDROOMS.items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Katong condominium comparison</title>
<meta name="description" content="Compare Katong condominium transactions by project, sale state, bedroom, floor, size, tenure and exact-unit evidence.">
<link rel="stylesheet" href="assets/research-shell.css">
<style>
:root{{--ink:#242724;--muted:#68706a;--paper:#fbfaf6;--line:#d9d8cf;--warm:#e86a47;--cool:#386f78;--pale:#f0ece3;--green:#23735b;--red:#a0443c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;line-height:1.5}}
main{{max-width:1500px;margin:auto;padding:28px clamp(18px,4vw,64px) 80px}}a{{color:inherit}}h1{{font:700 clamp(2.7rem,7vw,6.2rem)/.94 Georgia,serif;letter-spacing:-.055em;max-width:1000px;margin:.2em 0}}
h2{{font:700 clamp(1.8rem,3vw,3rem)/1.05 Georgia,serif;margin:70px 0 10px}}h3{{margin:.25em 0}}p{{max-width:78ch}}small{{display:block;color:var(--muted);font-weight:400;margin-top:3px}}
.eyebrow,.tag,.status{{font-size:.74rem;letter-spacing:.11em;text-transform:uppercase;font-weight:800}}.hero{{border-bottom:1px solid var(--line);padding:45px 0 42px}}
.hero-copy{{font-size:1.13rem;color:var(--muted)}}.hero-meta,.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:28px}}
.metric{{padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff}}.metric span{{display:block;color:var(--muted);font-size:.78rem}}.metric b{{display:block;font-size:1.35rem;margin-top:4px}}
.method-note,.caveat,.unit-gate{{padding:18px 20px;border-radius:15px;background:var(--pale);border-left:4px solid var(--cool);margin:20px 0}}
.profiles{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.profile{{border:1px solid var(--line);border-radius:18px;padding:20px;background:#fff}}.profile-top{{display:flex;justify-content:space-between;color:var(--muted);font-size:.78rem}}
.profile dl{{font-size:.88rem}}.profile dt{{font-weight:750;margin-top:12px}}.profile dd{{margin:2px 0;color:var(--muted)}}.controls{{position:sticky;top:0;z-index:20;background:rgba(251,250,246,.96);backdrop-filter:blur(12px);padding:14px 0;border-bottom:1px solid var(--line)}}
.control-row{{display:flex;gap:8px;align-items:end;flex-wrap:wrap}}label{{font-size:.74rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}select,input,button{{font:inherit}}select,input{{display:block;margin-top:4px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff}}
button{{padding:9px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;cursor:pointer}}button.active{{background:var(--ink);color:#fff;border-color:var(--ink)}}.project-buttons{{display:flex;gap:6px;overflow:auto;padding:10px 0 0}}
.project-toggle{{white-space:nowrap;font-size:.78rem}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:16px;background:#fff;margin-top:16px}}table{{border-collapse:collapse;width:100%;min-width:980px}}th,td{{padding:13px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
th{{position:sticky;top:0;background:#f5f2eb;z-index:2;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}}tbody tr:hover{{background:#fbf7ef}}.positive{{color:var(--green)}}.negative{{color:var(--red)}}.empty{{padding:22px;color:var(--muted);border:1px dashed var(--line);border-radius:14px}}
.map-wrap{{max-width:1100px}}.map-wrap svg{{width:100%;height:auto;border:1px solid var(--line);border-radius:22px}}.map-number{{fill:white;font-weight:800;font-size:12px}}.map-label{{fill:#353834;font-size:12px;font-weight:700;paint-order:stroke;stroke:#f4f0e8;stroke-width:4px}}.water-label{{fill:#5c8990;font:italic 15px Georgia,serif}}
.map-key{{display:flex;gap:10px 18px;flex-wrap:wrap;margin-top:10px;font-size:.78rem}}.map-key i{{display:inline-grid;place-items:center;width:22px;height:22px;color:#fff;border-radius:50%;font-style:normal;margin-right:5px}}
.unit-gate .status{{display:inline-block;padding:5px 8px;border-radius:6px;background:#fff}}.status.available{{color:var(--green)}}.status.unavailable{{color:var(--red)}}.unit-metrics{{grid-template-columns:repeat(4,minmax(0,1fr))}}
.source-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}.source-grid>div{{border:1px solid var(--line);border-radius:16px;padding:18px;background:#fff}}.source-grid li{{margin:.55em 0}}code{{font-size:.85em;background:#fff;padding:2px 5px;border-radius:5px}}
.ledger-meta{{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}}.hidden{{display:none!important}}.top-link{{display:inline-block;margin-bottom:20px;color:var(--muted);text-decoration:none}}
@media(max-width:1050px){{.profiles{{grid-template-columns:repeat(2,1fr)}}.hero-meta,.metrics{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:680px){{main{{padding-inline:14px}}.profiles,.source-grid{{grid-template-columns:1fr}}.hero-meta,.metrics{{grid-template-columns:1fr 1fr}}h1{{font-size:3.25rem}}.controls{{position:static}}}}
</style></head><body><main>
<a class="top-link" href="index.html">← Research home</a>
<header class="hero"><div class="eyebrow">Katong project diagnostic · updated {as_of:%d %b %Y}</div>
<h1>Compare the apartment, not just the postcode.</h1>
<p class="hero-copy">Eight Katong-area projects, separated by sale state, bedroom, size, floor, tenure and evidence depth. Use the controls to keep the comparison like-for-like.</p>
<div class="hero-meta">
  <article class="metric"><span>Profiled projects</span><b>{len(rows)}</b><small>4 launch benchmarks · 4 completed controls</small></article>
  <article class="metric"><span>Headline evidence</span><b>{periods['headline_start']}–{periods['full_end']}</b><small>latest 18 complete months</small></article>
  <article class="metric"><span>Growth threshold</span><b>n ≥ {MIN_GROWTH_SAMPLE} + {MIN_GROWTH_SAMPLE}</b><small>both rolling 12-month windows</small></article>
  <article class="metric"><span>Underlying caveats</span><b>{len(txns):,}</b><small>full profiled-project ledger below</small></article>
</div></header>

<section><h2>Start with the comparison set</h2>
<p>“Katong” is a lived neighbourhood, not a clean transaction field. Postal District 15 is too broad, so this page uses a reviewed project list and keeps each micro-market visible.</p>
<div class="profiles">{_profile_cards(rows)}</div></section>

<section><h2>Micro-location locator</h2>
<p>The locator uses reviewed project coordinates. It is orientation only—not a parcel boundary, walking route or distance-to-amenity map.</p>
{_locator_map(rows)}</section>

<section id="comparison"><h2>Like-for-like achieved prices</h2>
<div class="controls" id="controls">
  <div class="control-row">
    <div><label for="sale-state">Sale state</label><select id="sale-state">{state_options}</select></div>
    <div><label for="bedroom">Bedroom type</label><select id="bedroom">{bed_options}</select></div>
    <div><label for="cohort">Comparison cohort</label><select id="cohort"><option value="all">All cohorts</option><option>Current launches</option><option>Completed controls</option></select></div>
    <button id="share-view" type="button">Copy filtered link</button>
  </div>
  <div class="project-buttons" aria-label="Toggle projects">{_project_buttons(rows)}</div>
</div>
<div class="method-note"><b>How to read this table.</b> Prices and PSF are achieved caveats, not listings. Growth is median PSF change between adjacent 12-month windows and is withheld below the sample threshold. Turnover is caveats divided by official unit stock. {esc(partial_note)}</div>
<div class="table-wrap"><table id="headline-table"><thead><tr>
  <th>Project / role</th><th>Tenure / status</th><th>18m sample</th><th>Median quantum</th>
  <th>Median PSF / size</th><th>12m PSF change</th><th>12m stock turnover</th><th>Access context</th>
</tr></thead><tbody>{_headline_rows(rows)}</tbody></table></div>
<div class="empty hidden" id="headline-empty">No transaction sample matches these controls. Change sale state, bedroom or project selection.</div>
</section>

<section><h2>Floor-band sensitivity</h2>
<p>URA publishes floor bands rather than exact floors in the committed transaction layer. Rows below require at least {MIN_GROWTH_SAMPLE} caveats in the headline window.</p>
<div class="table-wrap">{_floor_table(rows, txns, periods)}</div></section>

<section id="exact-units"><h2>Exact-unit evidence gate</h2>
<p>Unit number is a separate evidence dimension. Floor band, area and bedroom are never used to guess an apartment identifier.</p>
{_unit_section(units, rows)}</section>

<section id="ledger"><h2>Full transaction ledger</h2>
<div class="ledger-meta"><p>Every valid caveat for the eight reviewed projects in the committed input. The comparison controls above also filter this ledger.</p>
<div class="control-row"><div><label for="ledger-search">Search ledger</label><input id="ledger-search" type="search" placeholder="Project or floor band"></div>
<button id="export-ledger" type="button">Export visible CSV</button></div></div>
<div class="table-wrap"><table id="ledger-table"><thead><tr><th>Sale month</th><th>Project</th><th>Sale state</th><th>Beds</th><th>Floor band</th><th>Area</th><th>Price</th><th>PSF</th><th>Provenance</th></tr></thead>
<tbody>{_ledger(txns, profiles)}</tbody></table></div>
<div class="empty hidden" id="ledger-empty">No ledger rows match the active controls.</div></section>

<section><h2>Planning, fit and risk register</h2>
<div class="table-wrap"><table><thead><tr><th>Project</th><th>Buyer fit</th><th>Comparison risk</th><th>Future context</th></tr></thead><tbody>
{''.join(f"<tr><td><b>{esc(row['name'].title())}</b><small>{esc(row['role'])}</small></td><td>{esc(row['best_fit'])}</td><td>{esc(row['key_risk'])}</td><td>{esc(row['future_context'])}</td></tr>" for row in rows)}
</tbody></table></div></section>

<section><h2>Sources and calculation register</h2>{_source_register(rows, periods)}</section>
<div class="caveat"><b>Research limitations.</b> URA caveats are voluntary and not exhaustive. Bedroom labels use a secondary row-match layer because the public URA transaction extract does not publish bedrooms. Project coordinates, MRT distance and school counts are diagnostics, not official eligibility measurements. New sale, sub-sale and resale have different price-setting conditions. No asking prices, rental yields or estate-level Provision scores are blended into a project ranking.</div>
</main><script src="assets/research-shell.js"></script>
<script>
(() => {{
  const sale = document.getElementById("sale-state");
  const bed = document.getElementById("bedroom");
  const cohort = document.getElementById("cohort");
  const search = document.getElementById("ledger-search");
  const toggles = [...document.querySelectorAll(".project-toggle")];
  const headlineRows = [...document.querySelectorAll("#headline-table tbody tr")];
  const ledgerRows = [...document.querySelectorAll("#ledger-table tbody tr")];
  const activeProjects = new Set(toggles.map(button => button.dataset.project));

  function apply() {{
    let headlineVisible = 0;
    headlineRows.forEach(row => {{
      const visible = activeProjects.has(row.dataset.project)
        && row.dataset.sale === sale.value && row.dataset.bed === bed.value
        && (cohort.value === "all" || row.dataset.cohort === cohort.value);
      row.classList.toggle("hidden", !visible);
      if (visible) headlineVisible += 1;
    }});
    document.getElementById("headline-empty").classList.toggle("hidden", headlineVisible > 0);
    const term = search.value.trim().toUpperCase();
    let ledgerVisible = 0;
    ledgerRows.forEach(row => {{
      const stateMatch = sale.value === "all" || row.dataset.sale === sale.value;
      const bedMatch = bed.value === "all" || row.dataset.bed === bed.value;
      const visible = activeProjects.has(row.dataset.project) && stateMatch && bedMatch
        && (cohort.value === "all" || row.dataset.cohort === cohort.value)
        && (!term || row.dataset.search.includes(term));
      row.classList.toggle("hidden", !visible);
      if (visible) ledgerVisible += 1;
    }});
    document.getElementById("ledger-empty").classList.toggle("hidden", ledgerVisible > 0);
  }}

  toggles.forEach(button => button.addEventListener("click", () => {{
    const project = button.dataset.project;
    if (activeProjects.has(project) && activeProjects.size > 1) activeProjects.delete(project);
    else activeProjects.add(project);
    button.classList.toggle("active", activeProjects.has(project));
    button.setAttribute("aria-pressed", activeProjects.has(project));
    apply();
  }}));
  [sale, bed, cohort].forEach(control => control.addEventListener("change", apply));
  search.addEventListener("input", apply);

  const query = new URLSearchParams(location.search);
  if (query.has("sale") && [...sale.options].some(option => option.value === query.get("sale"))) sale.value = query.get("sale");
  if (query.has("bed") && [...bed.options].some(option => option.value === query.get("bed"))) bed.value = query.get("bed");
  if (query.has("cohort") && [...cohort.options].some(option => option.value === query.get("cohort"))) cohort.value = query.get("cohort");
  if (query.has("projects")) {{
    const requested = new Set(query.get("projects").split(","));
    const valid = toggles.map(button => button.dataset.project).filter(project => requested.has(project));
    if (valid.length) {{
      activeProjects.clear(); valid.forEach(project => activeProjects.add(project));
      toggles.forEach(button => {{
        button.classList.toggle("active", activeProjects.has(button.dataset.project));
        button.setAttribute("aria-pressed", activeProjects.has(button.dataset.project));
      }});
    }}
  }}

  document.getElementById("share-view").addEventListener("click", async event => {{
    const params = new URLSearchParams({{
      sale: sale.value, bed: bed.value, cohort: cohort.value,
      projects: [...activeProjects].join(",")
    }});
    const url = `${{location.origin}}${{location.pathname}}?${{params}}#comparison`;
    try {{ await navigator.clipboard.writeText(url); event.currentTarget.textContent = "Link copied"; }}
    catch (_) {{ window.prompt("Copy this filtered link", url); }}
  }});

  document.getElementById("export-ledger").addEventListener("click", () => {{
    const visible = ledgerRows.filter(row => !row.classList.contains("hidden"));
    const headers = [...document.querySelectorAll("#ledger-table thead th")].map(cell => cell.textContent.trim());
    const lines = [headers, ...visible.map(row => [...row.cells].map(cell => cell.textContent.trim().replace(/\\s+/g, " ")))]
      .map(values => values.map(value => `"${{value.replaceAll('"', '""')}}"`).join(","));
    const blob = new Blob([lines.join("\\n")], {{type:"text/csv;charset=utf-8"}});
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
    link.download = "katong-visible-transactions.csv"; link.click(); URL.revokeObjectURL(link.href);
  }});
  apply();
}})();
</script></body></html>"""


def generate(
    profiles_path: pathlib.Path = DEFAULT_PROFILES,
    transactions_path: pathlib.Path = DEFAULT_TRANSACTIONS,
    locations_path: pathlib.Path = DEFAULT_LOCATIONS,
    schools_path: pathlib.Path = DEFAULT_SCHOOLS,
    mrt_path: pathlib.Path = DEFAULT_MRT,
    units_path: pathlib.Path = DEFAULT_UNITS,
    out_path: pathlib.Path = DEFAULT_OUT,
    as_of: date | None = None,
) -> tuple[pathlib.Path, list[dict[str, Any]], dict[str, pd.Period | None]]:
    as_of = as_of or date.today()
    profiles = load_profiles(profiles_path)
    projects = set(profiles["project"])
    txns = load_transactions(transactions_path, projects)
    missing = sorted(projects - set(txns["project"]))
    if missing:
        raise SystemExit(f"no transaction rows for profiled projects: {missing}")
    periods = analysis_periods(txns, as_of)
    complete_txns = txns[txns["sale_period"] <= periods["full_end"]].copy()
    locations = _lookup(locations_path, ["project_name", "lat", "lon"])
    schools = _lookup(
        schools_path,
        ["project_name", "primary_1km_count", "primary_1km_schools"],
    )
    mrt = pd.read_csv(mrt_path)
    rows = build_rows(profiles, complete_txns, locations, schools, mrt, periods)
    units = load_unit_transactions(units_path, projects)
    out_path.write_text(
        render_html(rows, profiles, txns, units, periods, as_of), encoding="utf-8"
    )
    return out_path, rows, periods


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Katong condominium comparison")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES))
    parser.add_argument("--transactions", default=str(DEFAULT_TRANSACTIONS))
    parser.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    parser.add_argument("--schools", default=str(DEFAULT_SCHOOLS))
    parser.add_argument("--mrt", default=str(DEFAULT_MRT))
    parser.add_argument("--units", default=str(DEFAULT_UNITS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path, rows, periods = generate(
        pathlib.Path(args.profiles),
        pathlib.Path(args.transactions),
        pathlib.Path(args.locations),
        pathlib.Path(args.schools),
        pathlib.Path(args.mrt),
        pathlib.Path(args.units),
        pathlib.Path(args.out),
    )
    print(
        f"Written: {out_path} ({len(rows)} projects, "
        f"headline window {periods['headline_start']}–{periods['full_end']})"
    )


if __name__ == "__main__":
    main()
