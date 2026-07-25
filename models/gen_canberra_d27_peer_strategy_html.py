#!/usr/bin/env python3
"""
Generate three complementary Canberra Crescent / District 27 strategy pages.

These are private-project diagnostics on the Liveability/Value side of the
framework. They deliberately do not produce a unified condominium ranking and
do not feed project facts into estate-level Provision scores.

Reads:
  data/raw/ura/pmi_d27_2021-2026.csv
      Official URA PMI Apartment/Condominium transactions.
  data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
      Secondary bedroom labels, conservatively attributed by the shared D27
      loader in gen_canberra_crescent_d27_html.py.
  data/outputs/private_project_locations.csv
      Project coordinates derived from the project's geospatial pipeline.
  data/inputs/mrt_layer.csv
      Operational rail station coordinates.

Writes:
  canberra_strategy_1_micro_location.html
  canberra_strategy_2_newness.html
  canberra_strategy_3_integration.html

Method:
  - Apartment and condominium transactions only.
  - Current month is treated as partial and excluded from all medians.
  - The micro-location and newness pages use the exact common period beginning
    with Canberra Crescent's first observed complete-month transaction.
  - Bedroom, quantum, floor area and sale state remain visible together.
  - Monthly/period differences are transaction-mix evidence, not appreciation.
  - MRT distances are straight-line spatial diagnostics, not walking routes.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
from datetime import date
from typing import Any

import pandas as pd

from gen_canberra_crescent_d27_html import (
    DEFAULT_EDGEPROP,
    DEFAULT_LOCATIONS,
    DEFAULT_MRT,
    DEFAULT_RAW,
    SUBJECT,
    clean_text,
    comparison_window,
    load_district_transactions,
    load_lookup,
    nearest_station,
)

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_MICRO_OUT = ROOT / "canberra_strategy_1_micro_location.html"
DEFAULT_NEWNESS_OUT = ROOT / "canberra_strategy_2_newness.html"
DEFAULT_INTEGRATION_OUT = ROOT / "canberra_strategy_3_integration.html"

TAB_KEYS = ("all", "1", "2", "3", "4")
TAB_LABELS = {
    "all": "All unit types",
    "1": "1 bedroom",
    "2": "2 bedrooms",
    "3": "3 bedrooms",
    "4": "4 bedrooms",
}
MICRO_PROJECTS = (
    SUBJECT,
    "THE WATERGARDENS AT CANBERRA",
    "THE COMMODORE",
    "CANBERRA RESIDENCES",
)
INTEGRATION_PROJECTS = (
    SUBJECT,
    "NORTH PARK RESIDENCES",
    "THE WISTERIA",
    "NINE RESIDENCES",
    "THE WATERGARDENS AT CANBERRA",
    "THE COMMODORE",
    "CANBERRA RESIDENCES",
)
PROJECT_SHORT = {
    SUBJECT: "Canberra Crescent",
    "THE WATERGARDENS AT CANBERRA": "Watergardens",
    "THE COMMODORE": "The Commodore",
    "CANBERRA RESIDENCES": "Canberra Residences",
    "NORTH PARK RESIDENCES": "North Park",
    "THE WISTERIA": "The Wisteria",
    "NINE RESIDENCES": "Nine Residences",
}
MICRO_ROLE = {
    SUBJECT: "Subject · developer New Sale",
    "THE WATERGARDENS AT CANBERRA": "Recent same-precinct control",
    "THE COMMODORE": "Recent same-precinct exit control",
    "CANBERRA RESIDENCES": "Older same-precinct resale control",
}
RETAIL_PROFILE = {
    SUBJECT: {
        "format": "Residential project",
        "tradeoff": "Canberra neighbourhood access; no integrated mall premise is priced in.",
        "evidence": "Transaction and straight-line access diagnostic only.",
        "url": "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch",
    },
    "NORTH PARK RESIDENCES": {
        "format": "Integrated town-centre development",
        "tradeoff": "Direct retail and transport-hub proposition; older 2015 lease clock.",
        "evidence": "North Park is part of the Northpoint City integrated development.",
        "url": (
            "https://www.frasersproperty.com/content/dam/frasersproperty/feature/"
            "project/newsroom/press-releases/singapore/2015/april/"
            "press-release-home-buyers-affirm-strong-interest-in-north-park-residences.pdf"
        ),
    },
    "THE WISTERIA": {
        "format": "Mixed-use retail podium",
        "tradeoff": "Daily retail at the project; not a rail interchange integration control.",
        "evidence": "Builder portfolio records 216 homes over a commercial podium.",
        "url": "https://bbr.com.sg/our_portfolio/the-wisteria-wisteria-mall-condominium/",
    },
    "NINE RESIDENCES": {
        "format": "Mixed-use neighbourhood mall",
        "tradeoff": "Retail at the project; farther from the nearest operational station.",
        "evidence": "Junction Nine identifies Nine Residences within the mall development.",
        "url": "https://junctionnine.sg/about-us/",
    },
    "THE WATERGARDENS AT CANBERRA": {
        "format": "Near-rail residential peer",
        "tradeoff": "Closer location/newness control without an integrated-mall premise.",
        "evidence": "URA transactions plus straight-line operational-station distance.",
        "url": "https://watergardencanberra.com.sg/stupulri/The_Watergardens_at_Canberra_eBrochure.pdf",
    },
    "THE COMMODORE": {
        "format": "Near-rail residential peer",
        "tradeoff": "Recent Canberra exit evidence without a town-centre mall proposition.",
        "evidence": "URA transactions plus straight-line operational-station distance.",
        "url": "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch",
    },
    "CANBERRA RESIDENCES": {
        "format": "Near-rail older residential peer",
        "tradeoff": "Older lease and larger-layout control near Canberra rail access.",
        "evidence": "URA transactions plus straight-line operational-station distance.",
        "url": "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch",
    },
}


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    if value >= 1_000_000:
        return f"S${value / 1_000_000:.3g}m"
    return f"S${value / 1_000:.0f}k"


def _num(
    value: float | None,
    *,
    prefix: str = "",
    suffix: str = "",
    digits: int = 0,
) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{prefix}{value:,.{digits}f}{suffix}"


def _range(low: float | None, high: float | None, formatter) -> str:
    if low is None or high is None:
        return "—"
    return f"{formatter(low)}–{formatter(high)}"


def _describe(group: pd.DataFrame) -> dict[str, Any]:
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
            "states": "No observations",
        }
    counts = group["type_of_sale"].value_counts()
    return {
        "n": int(len(group)),
        "median_price": float(group["price"].median()),
        "price_p10": float(group["price"].quantile(0.10)),
        "price_p90": float(group["price"].quantile(0.90)),
        "median_psf": float(group["psf"].median()),
        "psf_p10": float(group["psf"].quantile(0.10)),
        "psf_p90": float(group["psf"].quantile(0.90)),
        "median_sqft": float(group["sqft"].median()),
        "states": " · ".join(f"{name} {count}" for name, count in counts.items()),
    }


def _stats_by_tab(group: pd.DataFrame) -> dict[str, dict[str, Any]]:
    stats = {"all": _describe(group)}
    for key in TAB_KEYS[1:]:
        stats[key] = _describe(group[group["unit_key"].eq(key)])
    return stats


def _lease_start(tenure: Any) -> int | None:
    match = re.search(r"(?:from|commencing from)\s+(\d{4})", str(tenure), re.I)
    return int(match.group(1)) if match else None


def _sale_states(group: pd.DataFrame) -> str:
    if group.empty:
        return "No observations"
    counts = group["type_of_sale"].value_counts()
    return " / ".join(f"{name} {count}" for name, count in counts.items())


def strategy_windows(
    txns: pd.DataFrame,
    as_of: date,
) -> dict[str, pd.Period | None]:
    """Return complete and subject-active matched periods."""
    window = comparison_window(txns, as_of)
    subject_complete = txns[
        txns["project_name"].eq(SUBJECT)
        & txns["sale_period"].le(window["full_end"])
    ]
    if subject_complete.empty:
        raise ValueError(f"{SUBJECT} has no complete-month observations")
    return {
        **window,
        "matched_start": max(
            window["current_start"],
            subject_complete["sale_period"].min(),
        ),
    }


def build_project_stats(
    txns: pd.DataFrame,
    projects: tuple[str, ...],
    start: pd.Period,
    end: pd.Period,
) -> list[dict[str, Any]]:
    frame = txns[
        txns["project_name"].isin(projects)
        & txns["sale_period"].between(start, end)
    ]
    rows = []
    for project in projects:
        group = frame[frame["project_name"].eq(project)]
        history = txns[
            txns["project_name"].eq(project)
            & txns["sale_period"].le(end)
        ]
        tenure = clean_text(history["tenure"].mode().iloc[0]) if not history.empty else "—"
        rows.append(
            {
                "project": project,
                "short": PROJECT_SHORT[project],
                "n": int(len(group)),
                "states": _sale_states(group),
                "tenure": tenure,
                "lease_start": _lease_start(tenure),
                "stats": _stats_by_tab(group),
            }
        )
    return rows


def build_time_rows(
    txns: pd.DataFrame,
    projects: tuple[str, ...],
    matched_start: pd.Period,
    full_end: pd.Period,
) -> list[dict[str, Any]]:
    split = pd.Period("2026-01", freq="M")
    periods = [
        ("Launch-era H2 2025", matched_start, min(full_end, split - 1)),
        ("H1 2026", max(matched_start, split), full_end),
    ]
    rows = []
    for label, start, end in periods:
        if start > end:
            continue
        subset = txns[txns["sale_period"].between(start, end)]
        for project in projects:
            group = subset[subset["project_name"].eq(project)]
            rows.append(
                {
                    "period": label,
                    "start": str(start),
                    "end": str(end),
                    "project": project,
                    "short": PROJECT_SHORT[project],
                    "states": _sale_states(group),
                    "stats": _stats_by_tab(group),
                }
            )
    return rows


def build_vintage_rows(
    txns: pd.DataFrame,
    projects: tuple[str, ...],
    full_end: pd.Period,
    as_of: date,
) -> list[dict[str, Any]]:
    rows = []
    for project in projects:
        group = txns[
            txns["project_name"].eq(project)
            & txns["sale_period"].le(full_end)
        ]
        tenure = clean_text(group["tenure"].mode().iloc[0]) if not group.empty else "—"
        lease_start = _lease_start(tenure)
        new_sales = group[group["type_of_sale"].eq("New Sale")]
        resale = group[group["type_of_sale"].eq("Resale")]
        sub_sale = group[group["type_of_sale"].eq("Sub Sale")]
        rows.append(
            {
                "project": project,
                "short": PROJECT_SHORT[project],
                "lease_start": lease_start,
                "lease_age": as_of.year - lease_start if lease_start else None,
                "first_observed_new_sale": (
                    str(new_sales["sale_period"].min()) if not new_sales.empty else None
                ),
                "first_observed_exit": (
                    str(pd.concat([resale, sub_sale])["sale_period"].min())
                    if not resale.empty or not sub_sale.empty
                    else None
                ),
                "all_states": _sale_states(group),
            }
        )
    return rows


def build_spatial_rows(
    project_rows: list[dict[str, Any]],
    locations_path: pathlib.Path,
    mrt_path: pathlib.Path,
) -> list[dict[str, Any]]:
    locations = load_lookup(locations_path)
    mrt = pd.read_csv(mrt_path)
    out = []
    for row in project_rows:
        station = nearest_station(row["project"], locations, mrt)
        profile = RETAIL_PROFILE[row["project"]]
        out.append({**row, **station, **profile})
    return out


def _tab_buttons() -> str:
    return "".join(
        f"<button class='tab{' active' if key == 'all' else ''}' "
        f"data-switch='{key}'>{_esc(label)}</button>"
        for key, label in TAB_LABELS.items()
    )


def _comparison_tables(
    rows: list[dict[str, Any]],
    role_map: dict[str, str] | None = None,
    *,
    show_access: bool = False,
) -> str:
    panels = []
    for key in TAB_KEYS:
        body = []
        for row in rows:
            stat = row["stats"][key]
            access = ""
            if show_access:
                distance = _num(row.get("station_distance_m"), suffix="m")
                access = (
                    f"<td><b>{_esc(row.get('station', '—'))}</b>"
                    f"<small>{distance} straight-line</small></td>"
                )
            role = role_map.get(row["project"], "") if role_map else ""
            body.append(
                "<tr>"
                f"<td><b>{_esc(row['short'])}</b><small>{_esc(role)}</small></td>"
                f"<td class='num'><b>{stat['n']}</b><small>{_esc(stat['states'])}</small></td>"
                f"<td class='num'><b>{_money(stat['median_price'])}</b><small>"
                f"{_range(stat['price_p10'], stat['price_p90'], _money)} P10–P90</small></td>"
                f"<td class='num'><b>{_num(stat['median_psf'], prefix='S$')}</b><small>"
                f"{_range(stat['psf_p10'], stat['psf_p90'], lambda x: _num(x, prefix='S$'))} P10–P90</small></td>"
                f"<td class='num'><b>{_num(stat['median_sqft'], suffix=' sqft')}</b></td>"
                f"{access}</tr>"
            )
        access_head = "<th>Operational rail</th>" if show_access else ""
        panels.append(
            f"<div class='tab-panel{' active' if key == 'all' else ''}' data-tab='{key}'>"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Project / diagnostic role</th><th>Transactions / states</th>"
            "<th>Median quantum</th><th>Median PSF</th><th>Median size</th>"
            f"{access_head}</tr></thead><tbody>{''.join(body)}</tbody></table></div></div>"
        )
    return "".join(panels)


def _time_tables(rows: list[dict[str, Any]]) -> str:
    panels = []
    for key in TAB_KEYS:
        body = []
        for row in rows:
            stat = row["stats"][key]
            body.append(
                "<tr>"
                f"<td><b>{_esc(row['period'])}</b><small>{row['start']} to {row['end']}</small></td>"
                f"<td><b>{_esc(row['short'])}</b></td>"
                f"<td class='num'><b>{stat['n']}</b><small>{_esc(stat['states'])}</small></td>"
                f"<td class='num'><b>{_money(stat['median_price'])}</b></td>"
                f"<td class='num'><b>{_num(stat['median_psf'], prefix='S$')}</b></td>"
                f"<td class='num'><b>{_num(stat['median_sqft'], suffix=' sqft')}</b></td>"
                "</tr>"
            )
        panels.append(
            f"<div class='tab-panel{' active' if key == 'all' else ''}' data-tab='{key}'>"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Observed period</th><th>Project</th><th>n / states</th>"
            "<th>Median quantum</th><th>Median PSF</th><th>Median size</th>"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table></div></div>"
        )
    return "".join(panels)


def _nav() -> str:
    return (
        "<nav class='report-nav' aria-label='Canberra strategy reports'>"
        "<a href='canberra_crescent_d27_deep_analysis.html'>Deep transaction ledger</a>"
        "<a href='canberra_strategy_1_micro_location.html'>01 Micro-location</a>"
        "<a href='canberra_strategy_2_newness.html'>02 Newness controls</a>"
        "<a href='canberra_strategy_3_integration.html'>03 Integration</a>"
        "<a href='canberra_strategy_4_unit_matching.html'>04 Unit matching</a>"
        "<a href='canberra_strategy_5_sale_state.html'>05 Sale states</a>"
        "<a href='canberra_strategy_6_planning_context.html'>06 Planning context</a>"
        "<a href='index.html'>All reports</a></nav>"
    )


def _sources(extra: list[tuple[str, str, str]] | None = None) -> str:
    rows = [
        (
            "URA Property Market Information",
            "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch",
            "Official transaction price, month, area, floor band, tenure and sale state. "
            "URA notes that resale/subsale rows are caveats and caveat lodgement is not mandatory.",
        ),
        (
            "URA transaction API reference",
            "https://eservice.ura.gov.sg/maps/api/",
            "Official field definitions and five-year API coverage.",
        ),
        (
            "OneMap",
            "https://www.onemap.gov.sg/home/index.html",
            "Authoritative national geospatial reference used by the project location pipeline.",
        ),
        (
            "LTA rail network",
            "https://www.lta.gov.sg/content/ltagov/en/getting_around/public_transport/rail_network.html",
            "Operational rail context. Distances on these pages are computed straight-line, not routes.",
        ),
    ]
    if extra:
        rows.extend(extra)
    return "".join(
        "<li><a href='{url}' target='_blank' rel='noopener'>{title}</a>"
        "<span>{note}</span></li>".format(
            url=_esc(url),
            title=_esc(title),
            note=_esc(note),
        )
        for title, url, note in rows
    )


def _layout(
    *,
    eyebrow: str,
    title: str,
    dek: str,
    as_of: date,
    matched_start: pd.Period,
    full_end: pd.Period,
    partial: pd.Period | None,
    accent: str,
    body: str,
) -> str:
    partial_text = (
        f"{partial} is partial and excluded." if partial is not None else "No partial month detected."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{_esc(dek)}">
<title>{_esc(title)}</title>
<style>
:root {{
  --ink:#17201f; --muted:#66706d; --paper:#f5f3ec; --card:#fffefa;
  --line:#d9d7cc; --accent:{accent}; --wash:color-mix(in srgb, var(--accent) 9%, white);
  --serif:Georgia, "Times New Roman", serif; --sans:Inter, ui-sans-serif, system-ui, sans-serif;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; color:var(--ink); background:var(--paper); font:15px/1.6 var(--sans); }}
a {{ color:inherit; }}
.shell {{ width:min(1220px, calc(100% - 32px)); margin:auto; }}
.report-nav {{ display:flex; gap:8px; flex-wrap:wrap; padding:18px 0; }}
.report-nav a {{ text-decoration:none; border:1px solid var(--line); background:#fff9;
  border-radius:99px; padding:7px 12px; font-size:12px; }}
.hero {{ border-top:1px solid var(--line); padding:72px 0 54px; display:grid;
  grid-template-columns:minmax(0,1.5fr) minmax(250px,.6fr); gap:54px; align-items:end; }}
.eyebrow {{ color:var(--accent); text-transform:uppercase; letter-spacing:.16em;
  font-weight:800; font-size:11px; }}
h1,h2,h3 {{ font-family:var(--serif); line-height:1.08; margin:0; }}
h1 {{ font-size:clamp(44px,7vw,88px); max-width:950px; letter-spacing:-.045em; }}
.dek {{ font-size:clamp(17px,2vw,22px); max-width:760px; color:#46504d; margin:24px 0 0; }}
.stamp {{ border-left:3px solid var(--accent); padding:8px 0 8px 18px; }}
.stamp b,.stamp span {{ display:block; }}
.stamp b {{ font-size:18px; }} .stamp span {{ color:var(--muted); font-size:12px; }}
section {{ padding:54px 0; border-top:1px solid var(--line); }}
.section-head {{ display:grid; grid-template-columns:1fr 1fr; gap:32px; margin-bottom:28px; }}
h2 {{ font-size:clamp(30px,4vw,48px); letter-spacing:-.025em; }}
.section-head p {{ margin:0; color:var(--muted); max-width:650px; }}
.cards {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); padding:24px; min-height:180px; }}
.card .kicker {{ display:block; color:var(--accent); font-weight:800; font-size:11px;
  text-transform:uppercase; letter-spacing:.11em; margin-bottom:12px; }}
.card h3 {{ font-size:24px; }} .card p {{ color:var(--muted); margin:12px 0 0; }}
.tabs {{ display:flex; flex-wrap:wrap; gap:7px; margin:0 0 15px; }}
.tab {{ cursor:pointer; border:1px solid var(--line); color:var(--ink); background:#fff9;
  border-radius:99px; padding:9px 14px; font:700 12px var(--sans); }}
.tab.active {{ background:var(--accent); color:white; border-color:var(--accent); }}
.tab-panel {{ display:none; }} .tab-panel.active {{ display:block; }}
.table-wrap {{ overflow:auto; border:1px solid var(--line); background:var(--card); }}
table {{ width:100%; border-collapse:collapse; min-width:850px; }}
th,td {{ padding:15px 14px; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.1em;
  background:var(--wash); position:sticky; top:0; }}
td b,td small {{ display:block; }} td small {{ color:var(--muted); font-size:11px; margin-top:3px; }}
td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.matrix {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
.matrix article {{ background:var(--card); border:1px solid var(--line); padding:22px; }}
.matrix strong {{ color:var(--accent); display:block; font-size:11px; letter-spacing:.1em;
  text-transform:uppercase; margin-bottom:7px; }}
.matrix h3 {{ font-size:23px; }} .matrix p {{ color:var(--muted); margin:9px 0 0; }}
.callout {{ background:var(--accent); color:white; padding:30px; display:grid;
  grid-template-columns:.5fr 1.5fr; gap:24px; align-items:start; }}
.callout h3 {{ font-size:30px; }} .callout p {{ margin:0; opacity:.88; }}
.source-list {{ list-style:none; padding:0; margin:0; display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
.source-list li {{ padding:17px; border:1px solid var(--line); background:var(--card); }}
.source-list a {{ font-weight:800; text-decoration-thickness:1px; }}
.source-list span {{ color:var(--muted); display:block; font-size:12px; margin-top:5px; }}
footer {{ padding:32px 0 48px; color:var(--muted); font-size:12px; }}
@media (max-width:800px) {{
  .hero,.section-head,.callout {{ grid-template-columns:1fr; }}
  .hero {{ padding-top:44px; gap:28px; }} .cards {{ grid-template-columns:1fr; }}
  .matrix,.source-list {{ grid-template-columns:1fr; }} h1 {{ font-size:48px; }}
}}
</style>
</head>
<body>
<main class="shell">
{_nav()}
<header class="hero">
  <div><span class="eyebrow">{_esc(eyebrow)}</span><h1>{_esc(title)}</h1>
  <p class="dek">{_esc(dek)}</p></div>
  <aside class="stamp"><span>Evidence cut</span><b>{matched_start} → {full_end}</b>
  <span>As at {as_of.isoformat()}</span><span>{_esc(partial_text)}</span></aside>
</header>
{body}
<footer>Private-project diagnostic only · Provision and Liveability remain separate ·
No unified condominium ranking · Generated deterministically from the repository data.</footer>
</main>
<script>
document.querySelectorAll("[data-switch]").forEach(button => {{
  button.addEventListener("click", () => {{
    const key = button.dataset.switch;
    document.querySelectorAll("[data-switch]").forEach(el => el.classList.toggle("active", el.dataset.switch === key));
    document.querySelectorAll("[data-tab]").forEach(el => el.classList.toggle("active", el.dataset.tab === key));
  }});
}});
</script>
</body></html>"""


def render_micro(
    rows: list[dict[str, Any]],
    windows: dict[str, pd.Period | None],
    as_of: date,
) -> str:
    by_name = {row["project"]: row for row in rows}
    subject = by_name[SUBJECT]["stats"]["all"]
    water = by_name["THE WATERGARDENS AT CANBERRA"]["stats"]["all"]
    commodore = by_name["THE COMMODORE"]["stats"]["all"]
    older = by_name["CANBERRA RESIDENCES"]["stats"]["all"]

    def delta(peer: dict[str, Any]) -> str:
        if not subject["median_psf"] or not peer["median_psf"]:
            return "insufficient observations"
        return f"{(peer['median_psf'] / subject['median_psf'] - 1) * 100:+.1f}%"

    cards = [
        (
            "Closest recent control",
            "Watergardens",
            f"{water['n']} period-matched observations; median PSF is {delta(water)} "
            "versus the subject. Its Sub Sale state is not a developer launch state.",
        ),
        (
            "Exit-state control",
            "The Commodore",
            f"{commodore['n']} observations spanning {commodore['states']}; median PSF "
            f"is {delta(commodore)} versus the subject.",
        ),
        (
            "Age/layout control",
            "Canberra Residences",
            f"{older['n']} Resale observations; median PSF is {delta(older)}. "
            "Read its quantum with median size and 2010 lease start.",
        ),
    ]
    body = f"""
<section>
  <div class="section-head"><h2>What micro-location can isolate</h2><p>
  The comparison holds the Canberra precinct relatively tight, then exposes the
  remaining differences: sale state, lease vintage, layout size and floor mix.</p></div>
  <div class="cards">{''.join(
      f"<article class='card'><span class='kicker'>{_esc(k)}</span><h3>{_esc(t)}</h3><p>{_esc(p)}</p></article>"
      for k, t, p in cards
  )}</div>
</section>
<section>
  <div class="section-head"><h2>Bedroom-matched evidence</h2><p>
  Every row uses the same {_esc(str(windows['matched_start']))}–{_esc(str(windows['full_end']))}
  complete-month window. P10–P90 ranges reveal mix dispersion; a median is not a valuation.</p></div>
  <div class="tabs">{_tab_buttons()}</div>
  {_comparison_tables(rows, MICRO_ROLE)}
</section>
<section>
  <div class="section-head"><h2>Decision protocol</h2><p>
  Use controls sequentially. The objective is to understand what a premium buys,
  not to produce a single winner.</p></div>
  <div class="matrix">
    <article><strong>Step 01</strong><h3>Match bedroom and area</h3><p>
    Compare quantum, PSF and median square feet together. Compact launch layouts can
    carry a higher PSF while preserving a lower entry quantum.</p></article>
    <article><strong>Step 02</strong><h3>Match transaction state</h3><p>
    Canberra Crescent is New Sale evidence. Watergardens Sub Sales and Commodore
    Resales embed seller, completion, condition and financing effects.</p></article>
    <article><strong>Step 03</strong><h3>Interrogate the range</h3><p>
    A wide P10–P90 band flags floor, view and layout heterogeneity. Inspect the deep
    transaction ledger before treating the median as a benchmark.</p></article>
    <article><strong>Step 04</strong><h3>Stress-test exit comparables</h3><p>
    The recent controls are the better future exit-state candidates; the older
    control is useful for lease/layout tradeoffs, not a direct launch valuation.</p></article>
  </div>
</section>
<section><div class="callout"><h3>Boundary</h3><p>
Changes between projects are cross-sectional transaction-mix differences. They do
not measure apartment-level growth, and exact unit numbers are unavailable in URA PMI.</p></div></section>
<section>
  <div class="section-head"><h2>Sources and caveats</h2><p>
  Bedroom labels are secondary-source attributions applied conservatively by the
  shared loader; official URA rows remain the transaction source.</p></div>
  <ul class="source-list">{_sources()}</ul>
</section>"""
    return _layout(
        eyebrow="Strategy 01 · Micro-location",
        title="Compare Canberra with Canberra",
        dek=(
            "A precinct-first comparison of Canberra Crescent Residences against "
            "Watergardens, The Commodore and Canberra Residences."
        ),
        as_of=as_of,
        matched_start=windows["matched_start"],
        full_end=windows["full_end"],
        partial=windows["partial"],
        accent="#b7482a",
        body=body,
    )


def render_newness(
    rows: list[dict[str, Any]],
    time_rows: list[dict[str, Any]],
    vintage_rows: list[dict[str, Any]],
    windows: dict[str, pd.Period | None],
    as_of: date,
) -> str:
    vintage_body = []
    for row in vintage_rows:
        vintage_body.append(
            "<tr>"
            f"<td><b>{_esc(row['short'])}</b></td>"
            f"<td class='num'><b>{row['lease_start'] or '—'}</b><small>"
            f"{_num(row['lease_age'], suffix=' elapsed years')}</small></td>"
            f"<td><b>{_esc(row['first_observed_new_sale'] or 'Not observed')}</b>"
            "<small>within the repository's rolling extract</small></td>"
            f"<td><b>{_esc(row['first_observed_exit'] or 'Not observed')}</b>"
            "<small>first Sub Sale or Resale in extract</small></td>"
            f"<td><b>{_esc(row['all_states'])}</b></td></tr>"
        )
    body = f"""
<section>
  <div class="section-head"><h2>Lease and market-state ladder</h2><p>
  “Newness” is decomposed into lease commencement, first observed New Sale and
  first observed exit-state evidence. First-observed dates are extract-bound—not
  legal TOP dates or complete launch histories.</p></div>
  <div class="table-wrap"><table><thead><tr><th>Project</th><th>Lease clock</th>
  <th>First observed New Sale</th><th>First observed exit state</th>
  <th>All observed states</th></tr></thead><tbody>{''.join(vintage_body)}</tbody></table></div>
</section>
<section>
  <div class="section-head"><h2>Current common-period controls</h2><p>
  Bedroom tabs hold unit type more tightly. Quantum, PSF and size stay adjacent
  because none is interpretable alone.</p></div>
  <div class="tabs">{_tab_buttons()}</div>
  {_comparison_tables(rows, MICRO_ROLE)}
</section>
<section>
  <div class="section-head"><h2>Time-sliced transaction mix</h2><p>
  The same projects are split into H2 2025 and H1 2026. These are period medians,
  not repeat-sale growth. A change can reflect release sequence, floor, size,
  bedroom availability or sale-state composition.</p></div>
  <div class="tabs">{_tab_buttons()}</div>
  {_time_tables(time_rows)}
</section>
<section>
  <div class="section-head"><h2>How to use the newness controls</h2><p>
  Different controls answer different buyer questions; combining them into one
  score would erase the explanation.</p></div>
  <div class="matrix">
    <article><strong>2024 lease</strong><h3>Canberra Crescent</h3><p>
    Developer New Sale positioning and the youngest lease clock. Launch-month
    medians show the booked/released unit mix, not appreciation.</p></article>
    <article><strong>2020 lease</strong><h3>Watergardens</h3><p>
    Close newness and geography control. Sub Sales test a near-completion market
    state but are structurally different from developer sales.</p></article>
    <article><strong>2020 lease</strong><h3>The Commodore</h3><p>
    Similar lease vintage with actual Resale evidence, useful for studying an
    emerging exit market while retaining Canberra location.</p></article>
    <article><strong>2010 lease</strong><h3>Canberra Residences</h3><p>
    Older lease/layout control. A PSF discount may purchase more area; remaining
    lease and condition need separate diligence.</p></article>
  </div>
</section>
<section><div class="callout"><h3>Not appreciation</h3><p>
No exact apartment identifiers are available, so these pages make no repeat-sale
claim. Period-to-period medians are compositional evidence and must not be used as
unit growth rates.</p></div></section>
<section>
  <div class="section-head"><h2>Sources and calculation register</h2><p>
  Lease start is parsed from URA tenure text. Elapsed lease years are a simple
  as-of-year diagnostic and are not a legal remaining-lease calculation.</p></div>
  <ul class="source-list">{_sources([
      (
          "Watergardens developer brochure",
          RETAIL_PROFILE["THE WATERGARDENS AT CANBERRA"]["url"],
          "Developer disclosure of land tenure and project particulars; transaction evidence remains URA PMI.",
      )
  ])}</ul>
</section>"""
    return _layout(
        eyebrow="Strategy 02 · Newness controls",
        title="Separate age from price",
        dek=(
            "A lease-vintage, launch-state and time-mix comparison that keeps "
            "bedroom, quantum, PSF and size visible—and does not call mix appreciation."
        ),
        as_of=as_of,
        matched_start=windows["matched_start"],
        full_end=windows["full_end"],
        partial=windows["partial"],
        accent="#7454a3",
        body=body,
    )


def render_integration(
    rows: list[dict[str, Any]],
    windows: dict[str, pd.Period | None],
    as_of: date,
) -> str:
    retail_body = []
    for row in rows:
        retail_body.append(
            "<tr>"
            f"<td><b>{_esc(row['short'])}</b><small>{_esc(row['tenure'])}</small></td>"
            f"<td><b>{_esc(row['format'])}</b><small>{_esc(row['evidence'])}</small></td>"
            f"<td><b>{_esc(row['station'])}</b><small>"
            f"{_num(row['station_distance_m'], suffix='m')} straight-line</small></td>"
            f"<td>{_esc(row['tradeoff'])}</td>"
            f"<td><a href='{_esc(row['url'])}' target='_blank' rel='noopener'>Direct evidence</a></td>"
            "</tr>"
        )
    body = f"""
<section>
  <div class="section-head"><h2>Integration is not one variable</h2><p>
  This lens separates operational-station proximity from retail-at-project and
  full town-centre/transport-hub integration. Those conveniences are related,
  but they are not interchangeable.</p></div>
  <div class="table-wrap"><table><thead><tr><th>Project</th><th>Retail format</th>
  <th>Nearest operational rail</th><th>Buyer tradeoff</th><th>Source</th></tr></thead>
  <tbody>{''.join(retail_body)}</tbody></table></div>
</section>
<section>
  <div class="section-head"><h2>Price and access side by side</h2><p>
  Headline evidence uses the latest 18 complete months, {_esc(str(windows['current_start']))}
  to {_esc(str(windows['full_end']))}. Unlike the micro-location page, this wider
  lens intentionally allows Yishun/Canberra location drift.</p></div>
  <div class="tabs">{_tab_buttons()}</div>
  {_comparison_tables(rows, show_access=True)}
</section>
<section>
  <div class="section-head"><h2>Three useful integration tests</h2><p>
  Each test isolates a different lived-experience proposition. There is no
  universal premium and no unified ranking.</p></div>
  <div class="cards">
    <article class="card"><span class="kicker">Town-centre test</span><h3>North Park</h3><p>
    The strongest full-integration control: retail and transport-hub proposition,
    but with a 2015 lease and Yishun town-centre positioning.</p></article>
    <article class="card"><span class="kicker">Retail podium test</span><h3>Wisteria & Nine</h3><p>
    Tests daily retail at the project without assuming interchange-level access.
    Tenant mix, strata governance and actual walking routes require buyer diligence.</p></article>
    <article class="card"><span class="kicker">Near-rail test</span><h3>Canberra peers</h3><p>
    Watergardens, Commodore and Canberra Residences help distinguish simple
    station proximity from a mixed-use or integrated development proposition.</p></article>
  </div>
</section>
<section>
  <div class="section-head"><h2>Buyer-fit matrix</h2><p>
  Choose the proposition first, then inspect bedroom-matched achieved prices.
  Asking listings and projected rents are outside this evidence set.</p></div>
  <div class="matrix">
    <article><strong>Frequent rail user</strong><h3>Validate route, not radius</h3><p>
    Straight-line distance is a screening diagnostic. Entrances, crossings,
    shelter, gradients and actual walking time are not represented.</p></article>
    <article><strong>Convenience-first household</strong><h3>Audit retail depth</h3><p>
    Distinguish a neighbourhood podium from a large town-centre mall and bus
    interchange. “Mixed use” does not guarantee the same service depth.</p></article>
    <article><strong>Value-focused buyer</strong><h3>Price space and lease</h3><p>
    Compare quantum, PSF, median area and lease start together. A lower PSF can
    reflect more area, older lease or weaker integration—not automatic value.</p></article>
    <article><strong>Exit-focused buyer</strong><h3>Use actual exit states</h3><p>
    Give more weight to Sub Sale/Resale depth than developer New Sale absorption
    when testing future liquidity, while preserving location and vintage caveats.</p></article>
  </div>
</section>
<section><div class="callout"><h3>Spatial boundary</h3><p>
Distances are project-coordinate to station-coordinate haversine calculations.
They are not walking routes, and retail labels are qualitative factual profiles—not
price adjustments or guaranteed liveability outcomes.</p></div></section>
<section>
  <div class="section-head"><h2>Direct sources and method caveats</h2><p>
  Retail format sources establish factual project relationships. They do not
  establish a causal integration premium.</p></div>
  <ul class="source-list">{_sources([
      (
          "North Park / Northpoint City",
          RETAIL_PROFILE["NORTH PARK RESIDENCES"]["url"],
          RETAIL_PROFILE["NORTH PARK RESIDENCES"]["evidence"],
      ),
      (
          "The Wisteria / Wisteria Mall",
          RETAIL_PROFILE["THE WISTERIA"]["url"],
          RETAIL_PROFILE["THE WISTERIA"]["evidence"],
      ),
      (
          "Nine Residences / Junction Nine",
          RETAIL_PROFILE["NINE RESIDENCES"]["url"],
          RETAIL_PROFILE["NINE RESIDENCES"]["evidence"],
      ),
  ])}</ul>
</section>"""
    return _layout(
        eyebrow="Strategy 03 · Integration and access",
        title="Price convenience in layers",
        dek=(
            "A diagnostic comparison of Canberra Crescent with integrated, mixed-use "
            "and near-rail District 27 peers—without assuming those labels are equivalent."
        ),
        as_of=as_of,
        matched_start=windows["current_start"],
        full_end=windows["full_end"],
        partial=windows["partial"],
        accent="#17716a",
        body=body,
    )


def generate_from_transactions(
    txns: pd.DataFrame,
    locations_path: pathlib.Path,
    mrt_path: pathlib.Path,
    outputs: tuple[pathlib.Path, pathlib.Path, pathlib.Path],
    *,
    as_of: date,
) -> dict[str, Any]:
    windows = strategy_windows(txns, as_of)
    micro_rows = build_project_stats(
        txns,
        MICRO_PROJECTS,
        windows["matched_start"],
        windows["full_end"],
    )
    time_rows = build_time_rows(
        txns,
        MICRO_PROJECTS,
        windows["matched_start"],
        windows["full_end"],
    )
    vintage_rows = build_vintage_rows(
        txns,
        MICRO_PROJECTS,
        windows["full_end"],
        as_of,
    )
    integration_rows = build_project_stats(
        txns,
        INTEGRATION_PROJECTS,
        windows["current_start"],
        windows["full_end"],
    )
    integration_rows = build_spatial_rows(
        integration_rows,
        locations_path,
        mrt_path,
    )
    pages = (
        render_micro(micro_rows, windows, as_of),
        render_newness(micro_rows, time_rows, vintage_rows, windows, as_of),
        render_integration(integration_rows, windows, as_of),
    )
    for path, page in zip(outputs, pages):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
    return {
        "outputs": outputs,
        "windows": windows,
        "micro_rows": micro_rows,
        "time_rows": time_rows,
        "vintage_rows": vintage_rows,
        "integration_rows": integration_rows,
    }


def generate(
    raw_path: pathlib.Path,
    edgeprop_path: pathlib.Path,
    locations_path: pathlib.Path,
    mrt_path: pathlib.Path,
    outputs: tuple[pathlib.Path, pathlib.Path, pathlib.Path],
    *,
    as_of: date,
) -> dict[str, Any]:
    txns = load_district_transactions(raw_path, edgeprop_path)
    return generate_from_transactions(
        txns,
        locations_path,
        mrt_path,
        outputs,
        as_of=as_of,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate three Canberra / District 27 peer strategy pages."
    )
    parser.add_argument("--raw", type=pathlib.Path, default=DEFAULT_RAW)
    parser.add_argument("--edgeprop", type=pathlib.Path, default=DEFAULT_EDGEPROP)
    parser.add_argument("--locations", type=pathlib.Path, default=DEFAULT_LOCATIONS)
    parser.add_argument("--mrt", type=pathlib.Path, default=DEFAULT_MRT)
    parser.add_argument("--micro-out", type=pathlib.Path, default=DEFAULT_MICRO_OUT)
    parser.add_argument("--newness-out", type=pathlib.Path, default=DEFAULT_NEWNESS_OUT)
    parser.add_argument("--integration-out", type=pathlib.Path, default=DEFAULT_INTEGRATION_OUT)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    result = generate(
        args.raw,
        args.edgeprop,
        args.locations,
        args.mrt,
        (args.micro_out, args.newness_out, args.integration_out),
        as_of=args.as_of,
    )
    print(
        json.dumps(
            {
                "outputs": [str(path) for path in result["outputs"]],
                "matched_start": str(result["windows"]["matched_start"]),
                "full_end": str(result["windows"]["full_end"]),
                "partial": str(result["windows"]["partial"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
