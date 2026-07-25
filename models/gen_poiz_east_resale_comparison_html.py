#!/usr/bin/env python3
"""
Generate a buyer-oriented Poiz-versus-East resale condo comparison.

This is a project diagnostic on the Liveability/Value side of the framework.
It does not create a unified project ranking or feed project facts into the
estate-level Provision score.

Reads:
  data/inputs/poiz_east_project_profiles.csv
      name,url,slug,region,role,official_units,completion_year,
      tenure_profile,integration,official_source_url,why_compare,best_fit,
      key_risk,future_context
  data/outputs/private_transactions_bedrooms.csv
      project_name,planning_area,property_type,tenure,sale_month,type_of_sale,
      transacted_price,area_sqm,data_source,bedrooms,bedroom_source
  data/outputs/private_project_locations.csv
      project_name,lat,lon
  data/outputs/private_project_school_metrics.csv
      project_name,primary_1km_count,primary_1km_schools
  data/inputs/mrt_layer.csv
      name,stn_code,line,lat,lon,operational

Writes:
  poiz_east_resale_comparison.html

Method:
  - Resale transactions only.
  - Headline price tables use the latest 18 complete calendar months.
  - Liquidity uses the latest 12 complete calendar months divided by official
    project units. It is transaction-to-stock turnover, not unique sellers.
  - A current partial month is disclosed but excluded from headline medians.
  - Bedroom labels retain their explicit secondary-source provenance.
  - MRT and school distances are straight-line project diagnostics.
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
DEFAULT_PROFILES = ROOT / "data/inputs/poiz_east_project_profiles.csv"
DEFAULT_TRANSACTIONS = ROOT / "data/outputs/private_transactions_bedrooms.csv"
DEFAULT_LOCATIONS = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_SCHOOLS = ROOT / "data/outputs/private_project_school_metrics.csv"
DEFAULT_MRT = ROOT / "data/inputs/mrt_layer.csv"
DEFAULT_OUT = ROOT / "poiz_east_resale_comparison.html"

SQM_TO_SQFT = 10.7639
PROFILE_COLUMNS = {
    "name",
    "url",
    "slug",
    "region",
    "role",
    "official_units",
    "completion_year",
    "tenure_profile",
    "integration",
    "official_source_url",
    "why_compare",
    "best_fit",
    "key_risk",
    "future_context",
}
TAB_KEYS = ("all", "1", "2", "3", "4")
TAB_LABELS = {
    "all": "All resales",
    "1": "1 bedroom",
    "2": "2 bedrooms",
    "3": "3 bedrooms",
    "4": "4 bedrooms",
}


def normalise_project(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def normalise_text(value: Any, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none"} else default


def mode_text(series: pd.Series, default: str = "—") -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values.ne("") & values.str.lower().ne("nan")]
    return str(values.mode().iloc[0]) if not values.empty else default


def load_profiles(path: pathlib.Path) -> pd.DataFrame:
    profiles = pd.read_csv(path)
    missing = sorted(PROFILE_COLUMNS - set(profiles.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    profiles = profiles.copy()
    profiles["project"] = profiles["name"].map(normalise_project)
    if profiles["project"].duplicated().any():
        duplicates = sorted(profiles.loc[profiles["project"].duplicated(), "project"].unique())
        raise SystemExit(f"{path} has duplicate projects: {duplicates}")
    profiles["official_units"] = pd.to_numeric(profiles["official_units"], errors="coerce")
    profiles["completion_year"] = pd.to_numeric(profiles["completion_year"], errors="coerce")
    if profiles[["official_units", "completion_year"]].isna().any().any():
        raise SystemExit(f"{path} has invalid official_units or completion_year")
    return profiles


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
    txns = txns[txns["type_of_sale"].astype(str).str.strip().str.casefold().eq("resale")]
    txns = txns[~txns["property_type"].astype(str).str.contains("House|Executive Condominium", case=False, na=False)]
    txns["sale_period"] = pd.to_datetime(txns["sale_month"], errors="coerce").dt.to_period("M")
    txns["price"] = pd.to_numeric(txns["transacted_price"], errors="coerce")
    txns["area_sqm"] = pd.to_numeric(txns["area_sqm"], errors="coerce")
    txns["bedrooms"] = pd.to_numeric(txns["bedrooms"], errors="coerce")
    txns = txns.dropna(subset=["sale_period", "price", "area_sqm"])
    txns = txns[(txns["price"] > 0) & (txns["area_sqm"] > 0)]
    txns["sqft"] = txns["area_sqm"] * SQM_TO_SQFT
    txns["psf"] = txns["price"] / txns["sqft"]
    return txns.reset_index(drop=True)


def latest_complete_month(txns: pd.DataFrame, as_of: date) -> tuple[pd.Period, pd.Period | None]:
    if txns.empty:
        raise ValueError("no transactions")
    latest = txns["sale_period"].max()
    current = pd.Period(as_of.strftime("%Y-%m"), freq="M")
    if latest >= current:
        return current - 1, latest
    return latest, None


def describe(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {
            "n": 0,
            "median_price": None,
            "price_p10": None,
            "price_p90": None,
            "median_psf": None,
            "psf_p10": None,
            "psf_p90": None,
            "median_sqft": None,
            "bedroom_exact_share": None,
            "poiz_price_delta_pct": None,
            "poiz_psf_delta_pct": None,
            "poiz_size_delta_pct": None,
        }
    known = group["bedrooms"].notna()
    exact = group["bedroom_source"].eq("edgeprop_exact")
    return {
        "n": int(len(group)),
        "median_price": float(group["price"].median()),
        "price_p10": float(group["price"].quantile(0.10)),
        "price_p90": float(group["price"].quantile(0.90)),
        "median_psf": float(group["psf"].median()),
        "psf_p10": float(group["psf"].quantile(0.10)),
        "psf_p90": float(group["psf"].quantile(0.90)),
        "median_sqft": float(group["sqft"].median()),
        "bedroom_exact_share": float(exact.sum() / known.sum()) if known.any() else None,
        "poiz_price_delta_pct": None,
        "poiz_psf_delta_pct": None,
        "poiz_size_delta_pct": None,
    }


def pct_delta(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base <= 0:
        return None
    return (value / base - 1.0) * 100.0


def lease_remaining(tenure_profile: str, as_of: date) -> float | None:
    match = re.search(r"99-year lease from (\d{4})", str(tenure_profile), re.I)
    if not match:
        return None
    elapsed = as_of.year + (as_of.timetuple().tm_yday - 1) / 365.25 - int(match.group(1))
    return max(0.0, 99.0 - elapsed)


def load_location_lookup(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    locations = pd.read_csv(path)
    locations["project"] = locations["project_name"].map(normalise_project)
    locations["lat"] = pd.to_numeric(locations["lat"], errors="coerce")
    locations["lon"] = pd.to_numeric(locations["lon"], errors="coerce")
    locations = locations.dropna(subset=["lat", "lon"]).drop_duplicates("project")
    return locations.set_index("project").to_dict("index")


def load_school_lookup(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    schools = pd.read_csv(path)
    schools["project"] = schools["project_name"].map(normalise_project)
    schools = schools.drop_duplicates("project")
    return schools.set_index("project").to_dict("index")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def nearest_open_station(
    project: str,
    locations: dict[str, dict[str, Any]],
    mrt: pd.DataFrame,
) -> dict[str, Any]:
    location = locations.get(project)
    if not location:
        return {"station": "—", "station_distance_m": None}
    stations = mrt.copy()
    stations["operational"] = pd.to_numeric(stations["operational"], errors="coerce").fillna(1)
    stations["lat"] = pd.to_numeric(stations["lat"], errors="coerce")
    stations["lon"] = pd.to_numeric(stations["lon"], errors="coerce")
    stations = stations[(stations["operational"] == 1) & stations["lat"].notna() & stations["lon"].notna()]
    if stations.empty:
        return {"station": "—", "station_distance_m": None}
    lat, lon = float(location["lat"]), float(location["lon"])
    distances = stations.apply(
        lambda row: haversine_m(lat, lon, float(row["lat"]), float(row["lon"])),
        axis=1,
    )
    station = stations.loc[distances.idxmin()]
    code = normalise_text(station.get("stn_code"), "")
    name = normalise_text(station.get("name"))
    return {
        "station": f"{name} ({code})" if code else name,
        "station_distance_m": int(round(float(distances.min()))),
    }


def build_rows(
    profiles: pd.DataFrame,
    txns: pd.DataFrame,
    locations: dict[str, dict[str, Any]],
    schools: dict[str, dict[str, Any]],
    mrt: pd.DataFrame,
    as_of: date,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    full_end, partial_month = latest_complete_month(txns, as_of)
    current_start = full_end - 17
    ttm_start = full_end - 11
    rows: list[dict[str, Any]] = []

    for profile in profiles.to_dict("records"):
        project = profile["project"]
        group = txns[txns["project"].eq(project)]
        if group.empty:
            raise ValueError(f"no resale transactions for profiled project: {project}")
        current = group[group["sale_period"].between(current_start, full_end)]
        ttm = group[group["sale_period"].between(ttm_start, full_end)]
        partial = (
            group[group["sale_period"].gt(full_end)]
            if partial_month is not None
            else group.iloc[0:0]
        )
        stats = {"all": describe(current)}
        for bedrooms in range(1, 5):
            stats[str(bedrooms)] = describe(current[current["bedrooms"].eq(bedrooms)])

        station = nearest_open_station(project, locations, mrt)
        school = schools.get(project, {})
        primary_count = pd.to_numeric(
            pd.Series([school.get("primary_1km_count")]), errors="coerce"
        ).iloc[0]
        units = int(profile["official_units"])
        rows.append(
            {
                **profile,
                "planning_area": mode_text(group["planning_area"]),
                "tenure_observed": mode_text(group["tenure"]),
                "lease_remaining_years": lease_remaining(profile["tenure_profile"], as_of),
                "resale_12m_n": int(len(ttm)),
                "turnover_pct": len(ttm) / units * 100.0,
                "partial_n": int(len(partial)),
                "last_sale_month": str(group["sale_period"].max()),
                "primary_1km_count": int(primary_count) if pd.notna(primary_count) else None,
                "primary_1km_schools": normalise_text(school.get("primary_1km_schools")),
                "stats": stats,
                **station,
            }
        )

    benchmark = next((row for row in rows if row["project"] == "THE POIZ RESIDENCES"), None)
    if benchmark is None:
        raise ValueError("profiles must include THE POIZ RESIDENCES")
    for row in rows:
        if row is benchmark:
            continue
        for key in ("1", "2", "3", "4"):
            stat = row["stats"][key]
            base = benchmark["stats"][key]
            if stat["n"] >= 3 and base["n"] >= 3:
                stat["poiz_price_delta_pct"] = pct_delta(stat["median_price"], base["median_price"])
                stat["poiz_psf_delta_pct"] = pct_delta(stat["median_psf"], base["median_psf"])
                stat["poiz_size_delta_pct"] = pct_delta(stat["median_sqft"], base["median_sqft"])

    window = {
        "current_start": str(current_start),
        "full_end": str(full_end),
        "ttm_start": str(ttm_start),
        "partial_month": str(partial_month) if partial_month is not None else "none",
    }
    return rows, window


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"S${value / 1_000_000:.3g}m"
    return f"S${value / 1_000:.0f}k"


def _num(value: float | None, prefix: str = "", suffix: str = "", digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{prefix}{value:,.{digits}f}{suffix}"


def _delta(value: float | None) -> str:
    if value is None:
        return "—"
    css = "up" if value > 1 else "down" if value < -1 else "flat"
    return f"<span class='{css}'>{value:+.1f}%</span>"


def _sample_label(n: int) -> str:
    if n >= 10:
        return "strong"
    if n >= 5:
        return "usable"
    if n >= 3:
        return "thin"
    return "insufficient"


def _profile_cards(rows: list[dict[str, Any]]) -> str:
    cards = []
    for row in rows:
        lease = (
            f"{row['lease_remaining_years']:.1f} years estimated remaining"
            if row["lease_remaining_years"] is not None
            else row["tenure_profile"]
        )
        source = _esc(row["official_source_url"])
        cards.append(
            "<article class='profile-card'>"
            f"<div class='card-top'><span class='region'>{_esc(row['region'])}</span>"
            f"<span class='role'>{_esc(row['role'])}</span></div>"
            f"<h3><a href='{source}'>{_esc(row['project'])}</a></h3>"
            f"<p class='integration'>{_esc(row['integration'])}</p>"
            "<dl>"
            f"<div><dt>Stock</dt><dd>{int(row['official_units']):,} units</dd></div>"
            f"<div><dt>Completed</dt><dd>{int(row['completion_year'])}</dd></div>"
            f"<div><dt>Tenure</dt><dd>{_esc(lease)}</dd></div>"
            f"<div><dt>12m resale</dt><dd>{row['resale_12m_n']} ({row['turnover_pct']:.1f}%)</dd></div>"
            f"<div><dt>Nearest open MRT</dt><dd>{_esc(row['station'])}, {_num(row['station_distance_m'], suffix='m')}</dd></div>"
            f"<div><dt>Primary ≤1km</dt><dd>{row['primary_1km_count'] if row['primary_1km_count'] is not None else '—'}</dd></div>"
            "</dl>"
            f"<p><b>Use:</b> {_esc(row['why_compare'])}</p>"
            f"<p><b>Best fit:</b> {_esc(row['best_fit'])}</p>"
            f"<p><b>Watch:</b> {_esc(row['key_risk'])}</p>"
            f"<p><b>Future:</b> {_esc(row['future_context'])}</p>"
            "</article>"
        )
    return "".join(cards)


def _finding_cards(rows: list[dict[str, Any]]) -> str:
    def matched_bedroom(
        row: dict[str, Any],
        preferred: tuple[str, ...] = ("2", "1", "3", "4"),
    ) -> tuple[str | None, dict[str, Any] | None]:
        for key in preferred:
            stat = row["stats"][key]
            if (
                stat["poiz_psf_delta_pct"] is not None
                and stat["poiz_size_delta_pct"] is not None
            ):
                return key, stat
        return None, None

    by_project = {row["project"]: row for row in rows}
    findings = []
    park = by_project.get("PARK PLACE RESIDENCES AT PLQ")
    if park:
        park_key, park_stat = matched_bedroom(park)
        if park_key and park_stat:
            findings.append(
                (
                    "Closest integrated match",
                    f"Park Place is {park_stat['poiz_psf_delta_pct']:+.1f}% versus Poiz on "
                    f"{park_key}BR PSF, with a {park_stat['poiz_size_delta_pct']:+.1f}% "
                    f"difference in median {park_key}BR size. Its dual-line PLQ setting is "
                    "the cleanest East-side test of integration value.",
                )
            )
        else:
            findings.append(
                (
                    "Closest integrated match",
                    "Park Place's dual-line PLQ setting is the cleanest East-side test of "
                    "integration value, although this data window lacks a qualifying "
                    "bedroom-matched sample against Poiz.",
                )
            )
    bedok = by_project.get("BEDOK RESIDENCES")
    if bedok:
        bedok_key, bedok_stat = matched_bedroom(bedok)
        if bedok_key and bedok_stat:
            findings.append(
                (
                    "Space changes the quantum read",
                    f"Bedok Residences is {bedok_stat['poiz_psf_delta_pct']:+.1f}% versus "
                    f"Poiz on {bedok_key}BR PSF, while its median {bedok_key}BR is "
                    f"{bedok_stat['poiz_size_delta_pct']:+.1f}% different in size. "
                    "A cheaper PSF can still produce a higher purchase quantum.",
                )
            )
        else:
            findings.append(
                (
                    "Space changes the quantum read",
                    "Bedok Residences generally tests larger-unit economics against Poiz. "
                    "Compare both PSF and total purchase quantum once a qualifying matched "
                    "bedroom sample is available.",
                )
            )
    parc = by_project.get("PARC ESTA")
    treasure = by_project.get("TREASURE AT TAMPINES")
    if parc and treasure:
        findings.append(
            (
                "Liquidity leaders",
                f"Parc Esta recorded {parc['resale_12m_n']} latest-12-month resales "
                f"({parc['turnover_pct']:.1f}% of stock); Treasure recorded "
                f"{treasure['resale_12m_n']} ({treasure['turnover_pct']:.1f}%). "
                "They are statistical controls, not direct mixed-use matches.",
            )
        )
    seaside = by_project.get("SEASIDE RESIDENCES")
    if seaside:
        findings.append(
            (
                "Coastal premium is not one thing",
                f"Seaside's 18-month all-resale median is "
                f"{_num(seaside['stats']['all']['median_psf'], prefix='S$', digits=0)} PSF. "
                "View, floor and facing can dominate project-level averages, so its bedroom tabs "
                "must still be size- and unit-position checked.",
            )
        )
    katong = by_project.get("KATONG REGENCY")
    if katong:
        findings.append(
            (
                "Freehold sensitivity is thin",
                f"Katong Regency has only {katong['resale_12m_n']} latest-12-month resales "
                f"({katong['turnover_pct']:.1f}% of stock). It is useful for tenure sensitivity "
                "but too thin and structurally different for a pooled Poiz benchmark.",
            )
        )
    findings.append(
        (
            "Poiz is liquid, not obviously cheap",
            "Poiz's compact units, direct NEL access and daily retail support a repeatable "
            "premium. Its healthy exit evidence does not prove underpricing; newer integrated "
            "projects and finite lease duration remain the counterweight.",
        )
    )
    return "".join(
        f"<article class='finding'><span>{index:02d}</span><h3>{_esc(title)}</h3><p>{text}</p></article>"
        for index, (title, text) in enumerate(findings, 1)
    )


def _decision_matrix(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td><b>{_esc(row['project'])}</b><small>{_esc(row['region'])}</small></td>"
            f"<td>{_esc(row['role'])}</td>"
            f"<td>{_esc(row['best_fit'])}</td>"
            f"<td>{_esc(row['why_compare'])}</td>"
            f"<td>{_esc(row['key_risk'])}</td>"
            f"<td>{_esc(row['future_context'])}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap decision-wrap'><table class='decision-table'><thead><tr>"
        "<th>Project</th><th>Comparison role</th><th>Best fit</th>"
        "<th>What it tests</th><th>Main risk</th><th>Planning context</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _planning_matrix() -> str:
    rows = [
        (
            "Bidadari / Potong Pasir",
            "Poiz",
            "Mostly realised; remaining items dated or proposed",
            "Bidadari's park, housing and transport story is largely delivered. Treat the "
            "polyclinic target and Kallang River public-space proposals as context, not a second launch premium.",
            "https://www.ura.gov.sg/land-planning/shaping-our-city/identity-corridors/kallang-river/",
            "URA",
        ),
        (
            "Paya Lebar Air Base",
            "Park Place, Parc Esta, Katong Regency",
            "Strategic, from the 2030s",
            "The relocation can free about 800 hectares, but its horizon is too long for a near-term project uplift assumption.",
            "https://www.ura.gov.sg/news/media/pr22-25/",
            "URA",
        ),
        (
            "Bayshore",
            "Seaside and Bedok-area projects",
            "Phased future neighbourhood",
            "New transport, retail, parks and housing can improve amenities while creating competing resale and rental supply.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/east/transforming-towns-for-tomorrow/",
            "URA",
        ),
        (
            "TEL5 / DTL extension",
            "Bedok, Tanah Merah and coastal controls",
            "Expected in 2H 2026 as of research date",
            "Do not label the access benefit as delivered before passenger service opens.",
            "https://www.lta.gov.sg/content/ltagov/en/newsroom/2026/4/news-releases/train-service-adjustments-tel-and-dtl-to-facilitate-rail-expansion-works.html",
            "LTA",
        ),
        (
            "Tampines Regional Centre / CRL",
            "Treasure at Tampines",
            "Area-level, multi-stage",
            "Useful employment and connectivity context, but Treasure remains outside direct station integration.",
            "https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/cross_island_line.html/1000",
            "LTA",
        ),
    ]
    body = "".join(
        "<tr>"
        f"<td><b>{_esc(topic)}</b></td><td>{_esc(projects)}</td><td>{_esc(horizon)}</td>"
        f"<td>{_esc(treatment)}</td><td><a href='{_esc(url)}'>{_esc(label)} source</a></td>"
        "</tr>"
        for topic, projects, horizon, treatment, url, label in rows
    )
    return (
        "<div class='table-wrap planning-wrap'><table class='planning-table'><thead><tr>"
        "<th>Plan / catalyst</th><th>Relevant projects</th><th>Horizon</th>"
        f"<th>How the comparison treats it</th><th>Primary source</th></tr></thead><tbody>{body}</tbody></table></div>"
    )


def _source_register(rows: list[dict[str, Any]], window: dict[str, str]) -> str:
    project_sources = "".join(
        f"<li><a href='{_esc(row['official_source_url'])}'>{_esc(row['project'])} official facts</a> "
        f"· <a href='{_esc(row['url'])}'>transaction detail table</a></li>"
        for row in rows
    )
    return (
        "<div class='source-grid'>"
        "<article><h3>Transaction evidence</h3><ul>"
        "<li><a href='https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch'>URA Property Market Information</a>: achieved caveat prices.</li>"
        "<li><a href='https://eservice.ura.gov.sg/reis/coverageandMethodology'>URA REALIS methodology</a>: coverage and caveat limitations.</li>"
        f"<li>Headline window: {_esc(window['current_start'])}–{_esc(window['full_end'])}; "
        f"liquidity window: {_esc(window['ttm_start'])}–{_esc(window['full_end'])}.</li>"
        "<li>Bedrooms are secondary EdgeProp labels joined to URA rows with explicit row-level provenance.</li>"
        "</ul></article>"
        "<article><h3>Spatial evidence</h3><ul>"
        "<li><a href='https://www.onemap.gov.sg/home/'>OneMap</a>: reviewed project coordinates.</li>"
        "<li><a href='https://www.lta.gov.sg/content/ltagov/en/map/train.html'>LTA rail map</a>: station network and operating context.</li>"
        "<li><a href='https://www.moe.gov.sg/schoolfinder?journey=Primary+school'>MOE SchoolFinder</a>: final address-specific school checks.</li>"
        "<li>Displayed MRT and school diagnostics are straight-line, not routed walking distances.</li>"
        "</ul></article>"
        f"<article><h3>Project source register</h3><ul>{project_sources}</ul></article>"
        "</div>"
    )


def _comparison_section(key: str, rows: list[dict[str, Any]], active: bool) -> str:
    table_rows = []
    for row in rows:
        stat = row["stats"][key]
        sample = _sample_label(stat["n"])
        price_range = (
            f"{_money(stat['price_p10'])}–{_money(stat['price_p90'])}"
            if stat["n"]
            else "—"
        )
        exact = (
            _num(stat["bedroom_exact_share"] * 100, suffix="%", digits=0)
            if key != "all" and stat["bedroom_exact_share"] is not None
            else "—"
        )
        table_rows.append(
            f"<tr class='region-{_esc(row['region'].split()[0].lower())}'>"
            f"<td><b>{_esc(row['project'])}</b><small>{_esc(row['role'])}</small></td>"
            f"<td>{_esc(row['region'])}</td>"
            f"<td class='num'><span class='sample {sample}'>{stat['n']}</span></td>"
            f"<td class='num'>{_money(stat['median_price'])}<small>{price_range}</small></td>"
            f"<td class='num'>{_num(stat['median_psf'], prefix='S$', digits=0)}</td>"
            f"<td class='num'>{_delta(stat['poiz_psf_delta_pct'])}</td>"
            f"<td class='num'>{_num(stat['median_sqft'], suffix=' sqft', digits=0)}</td>"
            f"<td class='num'>{_delta(stat['poiz_size_delta_pct'])}</td>"
            f"<td class='num'>{exact}</td>"
            f"<td class='num'>{row['resale_12m_n']}<small>{row['turnover_pct']:.1f}% of stock</small></td>"
            f"<td>{_esc(row['station'])}<small>{_num(row['station_distance_m'], suffix='m')}</small></td>"
            f"<td class='num'>{row['primary_1km_count'] if row['primary_1km_count'] is not None else '—'}</td>"
            "</tr>"
        )
    active_class = " active" if active else ""
    return (
        f"<section id='tab-{key}' class='comparison{active_class}'>"
        f"<div class='section-meta'>{_esc(TAB_LABELS[key])}. Price range is P10–P90; "
        "Poiz deltas appear only where both projects have at least three matched transactions.</div>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Project / role</th><th>Region</th><th class='num'>n</th>"
        "<th class='num'>Median quantum<small>P10–P90</small></th>"
        "<th class='num'>Median PSF</th><th class='num'>PSF vs Poiz</th>"
        "<th class='num'>Median size</th><th class='num'>Size vs Poiz</th>"
        "<th class='num'>Exact BR provenance</th><th class='num'>12m liquidity</th>"
        "<th>MRT diagnostic</th><th class='num'>Primary ≤1km</th>"
        f"</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div></section>"
    )


def render_html(rows: list[dict[str, Any]], window: dict[str, str], as_of: date) -> str:
    benchmark = next(row for row in rows if row["project"] == "THE POIZ RESIDENCES")
    tabs = "".join(
        f"<button class='tab{' active' if key == 'all' else ''}' data-tab='{key}'>{_esc(TAB_LABELS[key])}</button>"
        for key in TAB_KEYS
    )
    sections = "".join(
        _comparison_section(key, rows, key == "all")
        for key in TAB_KEYS
    )
    partial_total = sum(row["partial_n"] for row in rows)
    partial_note = (
        f"{partial_total} profiled-project transactions in {window['partial_month']} are disclosed "
        "in the refreshed source but excluded from headline medians."
        if window["partial_month"] != "none"
        else "The source has no newer partial month beyond the completed comparison window."
    )
    benchmark_psf = benchmark["stats"]["all"]["median_psf"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Poiz vs East Resale Condo Comparison</title>
<style>
  :root {{
    --ink:#17212b; --muted:#617080; --line:#d9e1e8; --paper:#f5f7f8;
    --card:#fff; --accent:#0f766e; --accent-soft:#dff4f0; --warm:#9a5b13;
    --warm-soft:#fff1d6; --down:#0b7a42; --up:#b4412f;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  main {{ max-width:1500px; margin:0 auto; padding:42px 28px 72px; }}
  h1 {{ font-size:clamp(28px,4vw,48px); line-height:1.03; max-width:850px; margin:0 0 10px; letter-spacing:-.035em; }}
  .lede {{ max-width:900px; color:var(--muted); font-size:16px; line-height:1.55; }}
  .companion {{ display:inline-flex; margin:4px 0 0; color:var(--accent); font-size:12px; font-weight:800; }}
  .eyebrow {{ text-transform:uppercase; letter-spacing:.14em; color:var(--accent); font-weight:800; font-size:11px; }}
  .method {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:26px 0; }}
  .metric {{ background:var(--ink); color:white; border-radius:14px; padding:18px; }}
  .metric b {{ display:block; font-size:24px; margin-bottom:5px; }}
  .metric span {{ color:#cbd5df; font-size:12px; line-height:1.4; }}
  .verdict {{ background:var(--accent-soft); border:1px solid #a7dacf; border-radius:14px; padding:18px 20px; line-height:1.55; margin:20px 0 30px; }}
  .verdict b {{ color:var(--accent); }}
  h2 {{ font-size:22px; margin:38px 0 14px; letter-spacing:-.02em; }}
  .findings {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
  .finding {{ background:var(--ink); color:white; border-radius:14px; padding:18px; }}
  .finding span {{ color:#79d5c9; font-weight:900; font-size:10px; letter-spacing:.12em; }}
  .finding h3 {{ margin:9px 0 7px; font-size:15px; }}
  .finding p {{ margin:0; color:#cdd7df; font-size:11px; line-height:1.55; }}
  .profiles {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
  .profile-card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:17px; box-shadow:0 6px 18px rgba(23,33,43,.04); }}
  .card-top {{ display:flex; gap:6px; justify-content:space-between; align-items:flex-start; }}
  .region,.role {{ display:inline-block; border-radius:99px; padding:4px 8px; font-size:10px; font-weight:800; }}
  .region {{ background:#e8edf2; color:#43515e; }} .role {{ background:var(--accent-soft); color:var(--accent); text-align:right; }}
  .profile-card h3 {{ margin:13px 0 5px; font-size:16px; }}
  a {{ color:inherit; text-decoration-color:#84bdb6; text-underline-offset:3px; }}
  .integration {{ min-height:38px; color:var(--accent); font-weight:700; font-size:12px; }}
  dl {{ display:grid; grid-template-columns:1fr 1fr; gap:7px 12px; margin:13px 0; }}
  dl div {{ border-top:1px solid #edf1f4; padding-top:6px; }}
  dt {{ color:var(--muted); font-size:9px; text-transform:uppercase; letter-spacing:.08em; }}
  dd {{ margin:2px 0 0; font-size:11px; font-weight:700; }}
  .profile-card p {{ color:#465563; font-size:11px; line-height:1.45; margin:7px 0; }}
  .tabs {{ display:flex; gap:7px; flex-wrap:wrap; margin:12px 0; }}
  .tab {{ border:1px solid var(--line); background:white; color:var(--ink); border-radius:9px; padding:9px 13px; cursor:pointer; font-weight:750; }}
  .tab.active {{ background:var(--ink); color:white; border-color:var(--ink); }}
  .comparison {{ display:none; }} .comparison.active {{ display:block; }}
  .section-meta,.caveat {{ color:var(--muted); font-size:12px; line-height:1.55; margin:10px 0; }}
  .table-wrap {{ overflow:auto; background:white; border:1px solid var(--line); border-radius:14px; }}
  table {{ width:100%; border-collapse:collapse; min-width:1320px; font-size:11px; }}
  th,td {{ padding:10px 9px; border-bottom:1px solid #e8edf1; text-align:left; vertical-align:top; }}
  th {{ position:sticky; top:0; background:#edf2f4; color:#52616e; text-transform:uppercase; letter-spacing:.04em; font-size:9px; }}
  th small,td small {{ display:block; color:#7a8895; font-size:9px; margin-top:3px; font-weight:500; text-transform:none; letter-spacing:0; }}
  td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  tbody tr:hover {{ background:#f7faf9; }}
  .sample {{ display:inline-flex; min-width:28px; justify-content:center; border-radius:99px; padding:3px 7px; font-weight:800; }}
  .sample.strong {{ background:#dff4e9; color:#17633d; }}
  .sample.usable {{ background:#e6effa; color:#285985; }}
  .sample.thin {{ background:var(--warm-soft); color:var(--warm); }}
  .sample.insufficient {{ background:#f1f2f3; color:#7a8188; }}
  .up {{ color:var(--up); font-weight:800; }} .down {{ color:var(--down); font-weight:800; }} .flat {{ color:var(--muted); }}
  .decision-table {{ min-width:1500px; }} .decision-table td {{ line-height:1.5; max-width:290px; white-space:normal; }}
  .planning-table {{ min-width:1050px; }} .planning-table td {{ line-height:1.5; max-width:420px; white-space:normal; }}
  .source-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
  .source-grid article {{ background:white; border:1px solid var(--line); border-radius:14px; padding:17px; }}
  .source-grid h3 {{ margin:0 0 9px; font-size:14px; }}
  .source-grid ul {{ margin:0; padding-left:18px; }}
  .source-grid li {{ color:#4e5e6b; font-size:11px; line-height:1.5; margin:5px 0; }}
  .caveat {{ background:#fff; border-left:4px solid var(--warm); padding:15px 17px; margin-top:24px; }}
  @media(max-width:1000px) {{ .profiles,.findings {{ grid-template-columns:repeat(2,1fr); }} .method {{ grid-template-columns:repeat(2,1fr); }} .source-grid {{ grid-template-columns:1fr; }} }}
  @media(max-width:650px) {{ main {{ padding:28px 15px 50px; }} .profiles,.findings,.method {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><main>
<div class="eyebrow">Project diagnostic · resale only · generated {_esc(as_of.isoformat())}</div>
<h1>The price of integration: Poiz versus East-side resale condos</h1>
<p class="lede">A like-for-like project profile for Katong/Eunos and Bedok/Tampines. It keeps achieved resale prices, bedroom mix, unit size, lease, liquidity and access visible instead of collapsing them into one ranking.</p>
<a class="companion" href="poiz_east_unit_growth_transactions.html">Open unit-type growth and every resale transaction →</a>
<div class="method">
  <div class="metric"><b>9</b><span>profiled projects selected for comparability and resale depth</span></div>
  <div class="metric"><b>{window['current_start']}–{window['full_end']}</b><span>latest 18 complete months used for price distributions</span></div>
  <div class="metric"><b>{_num(benchmark_psf, prefix='S$', digits=0)}</b><span>Poiz all-resale median PSF in the comparison window</span></div>
  <div class="metric"><b>{benchmark['resale_12m_n']} / {int(benchmark['official_units'])}</b><span>Poiz latest-12-complete-month resales / official stock ({benchmark['turnover_pct']:.1f}%)</span></div>
</div>
<div class="verdict"><b>Decision read:</b> Park Place Residences at PLQ is the closest city-fringe integrated match; Bedok Residences is the closest mature-town integrated match. Parc Esta and Treasure are liquidity controls, The Glades and Grandeur Park isolate MRT proximity, Seaside tests the coastal/TEL premium, and Katong Regency is a freehold sensitivity—not a pooled leasehold comparable.</div>
<h2>Research findings</h2>
<div class="findings">{_finding_cards(rows)}</div>
<h2>Why each project is here</h2>
<div class="profiles">{_profile_cards(rows)}</div>
<h2>Buyer decision comparison</h2>
<p class="section-meta">Use this matrix to select the relevant trade-off before opening the price tabs. Future plans remain context and are not added to achieved prices.</p>
{_decision_matrix(rows)}
<h2>Achieved resale evidence</h2>
<div class="tabs">{tabs}</div>
{sections}
<h2>Planning and catalyst comparison</h2>
<p class="section-meta">Plans are separated by horizon and evidence status so long-dated announcements do not masquerade as present-day project value.</p>
{_planning_matrix()}
<h2>Sources and calculation register</h2>
{_source_register(rows, window)}
<div class="caveat"><b>Read before comparing.</b> Source prices are URA caveats; caveats are voluntary and not exhaustive. Bedrooms come from an EdgeProp row-match layer because URA does not publish bedrooms; exact-match coverage is shown in the table. Straight-line MRT and school diagnostics are not walking routes or official Primary 1 home-school measurements. 12-month liquidity is transaction count divided by units, not unique sellers. { _esc(partial_note) } Estate Provision/Value bands are deliberately omitted because they are not project scores. No asking listings or rental yield estimates are mixed into achieved-sale evidence.</div>
</main>
<script>
document.querySelectorAll(".tab").forEach(function(button) {{
  button.addEventListener("click", function() {{
    document.querySelectorAll(".tab").forEach(function(item) {{ item.classList.remove("active"); }});
    document.querySelectorAll(".comparison").forEach(function(item) {{ item.classList.remove("active"); }});
    button.classList.add("active");
    document.getElementById("tab-" + button.dataset.tab).classList.add("active");
  }});
}});
</script>
</body></html>"""


def generate(
    profiles_path: pathlib.Path = DEFAULT_PROFILES,
    transactions_path: pathlib.Path = DEFAULT_TRANSACTIONS,
    locations_path: pathlib.Path = DEFAULT_LOCATIONS,
    schools_path: pathlib.Path = DEFAULT_SCHOOLS,
    mrt_path: pathlib.Path = DEFAULT_MRT,
    out_path: pathlib.Path = DEFAULT_OUT,
    as_of: date | None = None,
) -> tuple[pathlib.Path, list[dict[str, Any]], dict[str, str]]:
    as_of = as_of or date.today()
    profiles = load_profiles(profiles_path)
    txns = load_transactions(transactions_path, set(profiles["project"]))
    missing = sorted(set(profiles["project"]) - set(txns["project"]))
    if missing:
        raise SystemExit(f"no resale rows for profiled projects: {missing}")
    locations = load_location_lookup(locations_path)
    schools = load_school_lookup(schools_path)
    mrt = pd.read_csv(mrt_path)
    rows, window = build_rows(profiles, txns, locations, schools, mrt, as_of)
    out_path.write_text(render_html(rows, window, as_of), encoding="utf-8")
    return out_path, rows, window


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Poiz-versus-East resale condo comparison")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES))
    parser.add_argument("--transactions", default=str(DEFAULT_TRANSACTIONS))
    parser.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    parser.add_argument("--schools", default=str(DEFAULT_SCHOOLS))
    parser.add_argument("--mrt", default=str(DEFAULT_MRT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path, rows, window = generate(
        pathlib.Path(args.profiles),
        pathlib.Path(args.transactions),
        pathlib.Path(args.locations),
        pathlib.Path(args.schools),
        pathlib.Path(args.mrt),
        pathlib.Path(args.out),
    )
    print(
        f"Written: {out_path} ({len(rows)} projects, "
        f"price window {window['current_start']}–{window['full_end']})"
    )


if __name__ == "__main__":
    main()
