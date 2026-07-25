#!/usr/bin/env python3
"""
Generate a transaction-level unit-type growth companion to the Poiz comparison.

This is a private-project diagnostic on the Liveability/Value side of the
framework. It does not create a unified project ranking or feed project facts
into the estate-level Provision score.

Reads:
  data/inputs/poiz_east_project_profiles.csv
      name,url,slug,region,role,official_units,official_source_url
  data/outputs/private_transactions_bedrooms.csv
      project_name,property_type,tenure,sale_month,type_of_sale,
      transacted_price,area_sqm,floor_level,data_source,bedrooms,
      bedroom_source

Writes:
  poiz_east_unit_growth_transactions.html

Method:
  - Resale transactions only.
  - Growth compares the median achieved PSF and price in the latest 12 complete
    months with the preceding 12 complete months.
  - Growth appears only when both windows have at least three transactions.
  - A current partial month is listed in the ledger but excluded from growth.
  - "Unit type" means bedroom count and observed size/floor range. URA caveats
    do not expose exact apartment numbers, so the output does not claim
    repeat-sale tracking of the same physical apartment.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
from datetime import date
from typing import Any

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_PROFILES = ROOT / "data/inputs/poiz_east_project_profiles.csv"
DEFAULT_TRANSACTIONS = ROOT / "data/outputs/private_transactions_bedrooms.csv"
DEFAULT_OUT = ROOT / "poiz_east_unit_growth_transactions.html"

SQM_TO_SQFT = 10.7639
MIN_GROWTH_SAMPLE = 3
PROFILE_COLUMNS = {
    "name",
    "url",
    "slug",
    "region",
    "role",
    "official_units",
    "official_source_url",
}
TRANSACTION_COLUMNS = {
    "project_name",
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
UNIT_KEYS = ("all", "1", "2", "3", "4", "5", "unknown")


def normalise_project(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def clean_text(value: Any, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none"} else default


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
    if profiles["official_units"].isna().any():
        raise SystemExit(f"{path} has invalid official_units")
    profiles["page_slug"] = profiles["slug"].map(
        lambda value: re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    )
    return profiles


def load_transactions(path: pathlib.Path, projects: set[str]) -> pd.DataFrame:
    txns = pd.read_csv(path, low_memory=False)
    missing = sorted(TRANSACTION_COLUMNS - set(txns.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    txns = txns.copy()
    txns["project"] = txns["project_name"].map(normalise_project)
    txns = txns[txns["project"].isin(projects)]
    txns = txns[txns["type_of_sale"].astype(str).str.strip().str.casefold().eq("resale")]
    txns = txns[
        ~txns["property_type"].astype(str).str.contains(
            "House|Executive Condominium",
            case=False,
            na=False,
        )
    ]
    txns["sale_period"] = pd.to_datetime(txns["sale_month"], errors="coerce").dt.to_period("M")
    txns["price"] = pd.to_numeric(txns["transacted_price"], errors="coerce")
    txns["area_sqm"] = pd.to_numeric(txns["area_sqm"], errors="coerce")
    txns["bedrooms"] = pd.to_numeric(txns["bedrooms"], errors="coerce")
    txns = txns.dropna(subset=["sale_period", "price", "area_sqm"])
    txns = txns[(txns["price"] > 0) & (txns["area_sqm"] > 0)]
    txns["sqft"] = txns["area_sqm"] * SQM_TO_SQFT
    txns["psf"] = txns["price"] / txns["sqft"]
    txns["unit_key"] = txns["bedrooms"].map(
        lambda value: str(int(value)) if pd.notna(value) else "unknown"
    )
    return txns.reset_index(drop=True)


def comparison_periods(
    txns: pd.DataFrame,
    as_of: date,
) -> dict[str, pd.Period | None]:
    if txns.empty:
        raise ValueError("no transactions")
    latest = txns["sale_period"].max()
    current = pd.Period(as_of.strftime("%Y-%m"), freq="M")
    full_end = current - 1 if latest >= current else latest
    partial = latest if latest > full_end else None
    return {
        "prior_start": full_end - 23,
        "prior_end": full_end - 12,
        "recent_start": full_end - 11,
        "full_end": full_end,
        "partial": partial,
    }


def _segment(group: pd.DataFrame, key: str) -> pd.DataFrame:
    if key == "all":
        return group
    return group[group["unit_key"].eq(key)]


def _median(group: pd.DataFrame, column: str) -> float | None:
    return float(group[column].median()) if not group.empty else None


def _growth(
    recent_value: float | None,
    prior_value: float | None,
    recent_n: int,
    prior_n: int,
) -> float | None:
    if (
        recent_value is None
        or prior_value is None
        or prior_value <= 0
        or recent_n < MIN_GROWTH_SAMPLE
        or prior_n < MIN_GROWTH_SAMPLE
    ):
        return None
    return (recent_value / prior_value - 1.0) * 100.0


def describe_unit_type(
    complete: pd.DataFrame,
    periods: dict[str, pd.Period | None],
    key: str,
) -> dict[str, Any]:
    history = _segment(complete, key)
    recent = history[
        history["sale_period"].between(periods["recent_start"], periods["full_end"])
    ]
    prior = history[
        history["sale_period"].between(periods["prior_start"], periods["prior_end"])
    ]
    recent_price = _median(recent, "price")
    prior_price = _median(prior, "price")
    recent_psf = _median(recent, "psf")
    prior_psf = _median(prior, "psf")
    return {
        "key": key,
        "history_n": int(len(history)),
        "recent_n": int(len(recent)),
        "prior_n": int(len(prior)),
        "recent_price": recent_price,
        "prior_price": prior_price,
        "recent_psf": recent_psf,
        "prior_psf": prior_psf,
        "recent_sqft": _median(recent, "sqft"),
        "psf_growth_pct": _growth(recent_psf, prior_psf, len(recent), len(prior)),
        "price_growth_pct": _growth(recent_price, prior_price, len(recent), len(prior)),
        "first_month": str(history["sale_period"].min()) if not history.empty else None,
        "last_month": str(history["sale_period"].max()) if not history.empty else None,
    }


def annual_history(complete: pd.DataFrame, keys: list[str]) -> list[dict[str, Any]]:
    years = sorted(complete["sale_period"].dt.year.unique().tolist())
    result = []
    for year in years:
        year_group = complete[complete["sale_period"].dt.year.eq(year)]
        cells = {}
        for key in keys:
            segment = _segment(year_group, key)
            cells[key] = {
                "n": int(len(segment)),
                "median_psf": _median(segment, "psf"),
                "median_price": _median(segment, "price"),
            }
        result.append({"year": int(year), "cells": cells})
    return result


def build_projects(
    profiles: pd.DataFrame,
    txns: pd.DataFrame,
    as_of: date,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    periods = comparison_periods(txns, as_of)
    projects = []
    for profile in profiles.to_dict("records"):
        project = profile["project"]
        group = txns[txns["project"].eq(project)].copy()
        if group.empty:
            raise ValueError(f"no resale transactions for profiled project: {project}")
        complete = group[group["sale_period"].le(periods["full_end"])].copy()
        partial = group[group["sale_period"].gt(periods["full_end"])].copy()
        present_keys = [
            key
            for key in UNIT_KEYS
            if key == "all" or not _segment(complete, key).empty
        ]
        stats = {
            key: describe_unit_type(complete, periods, key)
            for key in present_keys
        }
        exact_share = (
            group["bedroom_source"].eq("edgeprop_exact").sum()
            / group["bedrooms"].notna().sum()
            if group["bedrooms"].notna().any()
            else None
        )
        transactions = group.sort_values(
            ["sale_period", "price", "area_sqm"],
            ascending=[False, False, False],
        ).to_dict("records")
        projects.append(
            {
                **profile,
                "present_keys": present_keys,
                "stats": stats,
                "annual": annual_history(complete, present_keys),
                "transactions": transactions,
                "complete_n": int(len(complete)),
                "partial_n": int(len(partial)),
                "first_month": str(complete["sale_period"].min()),
                "last_month": str(group["sale_period"].max()),
                "exact_bedroom_share": float(exact_share) if exact_share is not None else None,
            }
        )

    display_periods = {
        key: str(value) if value is not None else "none"
        for key, value in periods.items()
    }
    return projects, display_periods


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"S${value / 1_000_000:.3g}m"
    return f"S${value / 1_000:.0f}k"


def _number(
    value: float | None,
    prefix: str = "",
    suffix: str = "",
    digits: int = 0,
) -> str:
    if value is None:
        return "—"
    return f"{prefix}{value:,.{digits}f}{suffix}"


def _growth_label(value: float | None) -> str:
    if value is None:
        return "<span class='na'>insufficient</span>"
    css = "positive" if value > 0.5 else "negative" if value < -0.5 else "neutral"
    return f"<span class='growth {css}'>{value:+.1f}%</span>"


def _unit_label(key: str) -> str:
    if key == "all":
        return "All unit types"
    if key == "unknown":
        return "Bedroom unknown"
    return f"{key} bedroom{'s' if key != '1' else ''}"


def _source_label(value: Any) -> str:
    source = clean_text(value).casefold()
    if source == "ura_private":
        return "URA caveat"
    if source == "edgeprop_backfill":
        return "EdgeProp backfill"
    return clean_text(value)


def _bedroom_source_label(value: Any) -> str:
    labels = {
        "edgeprop_exact": "Exact row match",
        "edgeprop_band_label": "EdgeProp band",
        "size_rule": "Size rule",
        "unknown": "Unknown",
    }
    source = clean_text(value, "unknown")
    return labels.get(source, source.replace("_", " ").title())


def _growth_table(project: dict[str, Any]) -> str:
    rows = []
    for key in project["present_keys"]:
        stat = project["stats"][key]
        rows.append(
            f"<tr data-growth-unit='{_esc(key)}'>"
            f"<td><b>{_esc(_unit_label(key))}</b><small>{stat['first_month']}–{stat['last_month']}</small></td>"
            f"<td class='num'>{stat['history_n']}</td>"
            f"<td class='num'>{stat['recent_n']}<small>prior {stat['prior_n']}</small></td>"
            f"<td class='num'>{_money(stat['recent_price'])}<small>prior {_money(stat['prior_price'])}</small></td>"
            f"<td class='num'>{_number(stat['recent_psf'], prefix='S$', digits=0)}"
            f"<small>prior {_number(stat['prior_psf'], prefix='S$', digits=0)}</small></td>"
            f"<td class='num'>{_growth_label(stat['psf_growth_pct'])}</td>"
            f"<td class='num'>{_growth_label(stat['price_growth_pct'])}</td>"
            f"<td class='num'>{_number(stat['recent_sqft'], suffix=' sqft', digits=0)}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table class='growth-table'><thead><tr>"
        "<th>Unit type / history</th><th class='num'>All txns</th>"
        "<th class='num'>Recent 12m<small>prior 12m</small></th>"
        "<th class='num'>Median quantum<small>recent / prior</small></th>"
        "<th class='num'>Median PSF<small>recent / prior</small></th>"
        "<th class='num'>PSF growth</th><th class='num'>Quantum growth</th>"
        f"<th class='num'>Recent median size</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _annual_table(project: dict[str, Any], full_end: str) -> str:
    keys = project["present_keys"]
    headings = "".join(f"<th class='num'>{_esc(_unit_label(key))}</th>" for key in keys)
    rows = []
    full_end_year = int(full_end[:4])
    for annual in project["annual"]:
        cells = []
        for key in keys:
            cell = annual["cells"][key]
            cells.append(
                "<td class='num'>"
                f"{_number(cell['median_psf'], prefix='S$', digits=0)}"
                f"<small>{cell['n']} transaction{'s' if cell['n'] != 1 else ''}</small>"
                "</td>"
            )
        ytd = " · YTD" if annual["year"] == full_end_year else ""
        rows.append(
            f"<tr><td><b>{annual['year']}{ytd}</b></td>{''.join(cells)}</tr>"
        )
    return (
        "<div class='table-wrap annual-wrap'><table class='annual-table'><thead><tr>"
        f"<th>Calendar year</th>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _transaction_table(project: dict[str, Any]) -> str:
    rows = []
    for number, txn in enumerate(project["transactions"], 1):
        period = str(txn["sale_period"])
        unit_key = txn["unit_key"]
        bedrooms = _unit_label(unit_key)
        floor = clean_text(txn.get("floor_level"), "Not published")
        partial = bool(txn["sale_period"] > pd.Period(project["stats"]["all"]["last_month"], freq="M"))
        status = "<span class='partial'>partial month</span>" if partial else ""
        profile = f"{bedrooms} · {_number(txn['sqft'], suffix=' sqft', digits=0)}"
        searchable = f"{period} {bedrooms} {floor} {txn['price']:.0f} {txn['psf']:.0f}"
        rows.append(
            f"<tr data-unit='{_esc(unit_key)}' data-year='{period[:4]}' "
            f"data-search='{_esc(searchable.lower())}'>"
            f"<td><b>{period}</b>{status}<small>record {number:03d}</small></td>"
            f"<td><b>{_esc(profile)}</b></td>"
            f"<td>{_esc(floor)}</td>"
            f"<td class='num'>{_money(float(txn['price']))}</td>"
            f"<td class='num'>{_number(float(txn['psf']), prefix='S$', digits=0)}</td>"
            f"<td>{_esc(clean_text(txn.get('tenure')))}</td>"
            f"<td>{_esc(_bedroom_source_label(txn.get('bedroom_source')))}</td>"
            f"<td>{_esc(_source_label(txn.get('data_source')))}</td>"
            "</tr>"
        )
    years = sorted(
        {str(txn["sale_period"])[:4] for txn in project["transactions"]},
        reverse=True,
    )
    unit_options = "".join(
        f"<option value='{_esc(key)}'>{_esc(_unit_label(key))}</option>"
        for key in project["present_keys"]
        if key != "all"
    )
    year_options = "".join(
        f"<option value='{year}'>{year}</option>"
        for year in years
    )
    return (
        "<div class='ledger-controls'>"
        "<label>Unit type<select class='txn-unit'><option value='all'>All unit types</option>"
        f"{unit_options}</select></label>"
        "<label>Sale year<select class='txn-year'><option value='all'>All years</option>"
        f"{year_options}</select></label>"
        "<label class='search-label'>Search<input class='txn-search' type='search' "
        "placeholder='month, floor, price or PSF'></label>"
        f"<span class='visible-count'>{len(project['transactions']):,} records shown</span>"
        "</div>"
        "<div class='table-wrap ledger-wrap'><table class='transaction-table'><thead><tr>"
        "<th>Sale month</th><th>Observed unit profile</th><th>Floor range</th>"
        "<th class='num'>Achieved price</th><th class='num'>PSF</th><th>Tenure</th>"
        "<th>Bedroom evidence</th><th>Sale evidence</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _project_panel(project: dict[str, Any], periods: dict[str, str], active: bool) -> str:
    all_stats = project["stats"]["all"]
    active_class = " active" if active else ""
    exact = (
        _number(project["exact_bedroom_share"] * 100, suffix="%", digits=1)
        if project["exact_bedroom_share"] is not None
        else "—"
    )
    return (
        f"<section id='{_esc(project['page_slug'])}' class='project-panel{active_class}' "
        f"data-project='{_esc(project['page_slug'])}'>"
        "<div class='project-heading'>"
        "<div>"
        f"<span class='region'>{_esc(project['region'])}</span>"
        f"<h2>{_esc(project['project'])}</h2>"
        f"<p>{_esc(project['role'])} · {int(project['official_units']):,} official units · "
        f"<a href='{_esc(project['official_source_url'])}'>official project facts</a> · "
        f"<a href='{_esc(project['url'])}'>transaction source page</a></p>"
        "</div>"
        "<div class='history-pill'>"
        f"<b>{project['first_month']}–{project['last_month']}</b>"
        f"<span>{project['complete_n']:,} complete-month records · {project['partial_n']} partial</span>"
        "</div></div>"
        "<div class='project-metrics'>"
        f"<article><span>Recent 12m median PSF</span><b>{_number(all_stats['recent_psf'], prefix='S$', digits=0)}</b></article>"
        f"<article><span>PSF growth vs prior 12m</span><b>{_growth_label(all_stats['psf_growth_pct'])}</b></article>"
        f"<article><span>Recent / prior transactions</span><b>{all_stats['recent_n']} / {all_stats['prior_n']}</b></article>"
        f"<article><span>Exact bedroom matches</span><b>{exact}</b></article>"
        "</div>"
        "<h3 class='section-title'>Growth by bedroom / unit type</h3>"
        f"<p class='section-note'>Recent {_esc(periods['recent_start'])}–{_esc(periods['full_end'])} "
        f"versus prior {_esc(periods['prior_start'])}–{_esc(periods['prior_end'])}. "
        "These are changes in median achieved sales, not repeat-sale appreciation.</p>"
        f"{_growth_table(project)}"
        "<h3 class='section-title'>Calendar-year median achieved PSF</h3>"
        "<p class='section-note'>Annual cells retain their transaction count so thin years remain visible.</p>"
        f"{_annual_table(project, periods['full_end'])}"
        "<h3 class='section-title'>Every available resale transaction</h3>"
        "<p class='section-note'>Each row is one published transaction record. Similar bedroom, size "
        "and floor-range rows may or may not be the same physical apartment.</p>"
        f"{_transaction_table(project)}"
        "</section>"
    )


def render_html(
    projects: list[dict[str, Any]],
    periods: dict[str, str],
    as_of: date,
) -> str:
    tabs = "".join(
        f"<button class='project-tab{' active' if index == 0 else ''}' "
        f"data-project='{_esc(project['page_slug'])}'>{_esc(project['project'])}</button>"
        for index, project in enumerate(projects)
    )
    panels = "".join(
        _project_panel(project, periods, index == 0)
        for index, project in enumerate(projects)
    )
    transaction_total = sum(len(project["transactions"]) for project in projects)
    partial_total = sum(project["partial_n"] for project in projects)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Poiz and East Condos · Unit Growth and Transactions</title>
<style>
  :root {{
    --ink:#17212b; --muted:#617080; --line:#d9e1e8; --paper:#f4f7f8;
    --card:#fff; --accent:#0f766e; --accent-soft:#dff4f0;
    --positive:#0b7a42; --positive-soft:#dff4e9;
    --negative:#b4412f; --negative-soft:#fae7e3; --warm:#9a5b13;
  }}
  * {{ box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  main {{ max-width:1500px; margin:0 auto; padding:42px 28px 72px; }}
  a {{ color:inherit; text-decoration-color:#70afa7; text-underline-offset:3px; }}
  .eyebrow {{ color:var(--accent); font-size:11px; font-weight:850;
    letter-spacing:.14em; text-transform:uppercase; }}
  h1 {{ max-width:970px; margin:8px 0 12px; font-size:clamp(30px,4vw,52px);
    line-height:1.02; letter-spacing:-.04em; }}
  .lede {{ max-width:970px; margin:0; color:var(--muted); font-size:16px; line-height:1.6; }}
  .back-link {{ display:inline-flex; margin-top:14px; color:var(--accent); font-weight:800; font-size:12px; }}
  .method-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:28px 0 16px; }}
  .method-grid article {{ min-height:112px; padding:18px; border-radius:14px; background:var(--ink); color:white; }}
  .method-grid b {{ display:block; margin-bottom:6px; font-size:23px; }}
  .method-grid span {{ color:#cbd5df; font-size:11px; line-height:1.5; }}
  .identity-note {{ margin:16px 0 28px; padding:17px 19px; border:1px solid #a7dacf;
    border-radius:14px; background:var(--accent-soft); font-size:13px; line-height:1.55; }}
  .identity-note b {{ color:var(--accent); }}
  .project-tabs {{ position:sticky; top:0; z-index:8; display:flex; gap:7px; overflow:auto;
    margin:0 -10px 22px; padding:11px 10px; background:rgba(244,247,248,.94);
    backdrop-filter:blur(12px); }}
  .project-tab {{ flex:0 0 auto; border:1px solid var(--line); border-radius:9px;
    background:white; color:var(--ink); padding:9px 12px; cursor:pointer;
    font-size:10px; font-weight:800; }}
  .project-tab.active {{ border-color:var(--ink); background:var(--ink); color:white; }}
  .project-panel {{ display:none; }} .project-panel.active {{ display:block; }}
  .project-heading {{ display:flex; align-items:flex-start; justify-content:space-between; gap:22px;
    margin:20px 0 14px; }}
  .project-heading h2 {{ margin:8px 0 5px; font-size:28px; letter-spacing:-.03em; }}
  .project-heading p {{ margin:0; color:var(--muted); font-size:11px; line-height:1.55; }}
  .region {{ display:inline-block; border-radius:99px; padding:5px 9px; background:var(--accent-soft);
    color:var(--accent); font-size:9px; font-weight:850; text-transform:uppercase; letter-spacing:.05em; }}
  .history-pill {{ flex:0 0 auto; min-width:245px; padding:14px 16px; border-radius:12px; background:white; border:1px solid var(--line); }}
  .history-pill b,.history-pill span {{ display:block; }} .history-pill b {{ font-size:13px; }}
  .history-pill span {{ margin-top:4px; color:var(--muted); font-size:10px; }}
  .project-metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:11px; margin:16px 0 28px; }}
  .project-metrics article {{ padding:16px; border:1px solid var(--line); border-radius:13px; background:white; }}
  .project-metrics span {{ display:block; min-height:28px; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.04em; }}
  .project-metrics b {{ display:block; margin-top:5px; font-size:21px; }}
  .section-title {{ margin:32px 0 6px; font-size:18px; letter-spacing:-.015em; }}
  .section-note {{ margin:0 0 11px; color:var(--muted); font-size:11px; line-height:1.5; }}
  .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:14px; background:white; }}
  table {{ width:100%; border-collapse:collapse; font-size:11px; }}
  .growth-table {{ min-width:1050px; }} .annual-table {{ min-width:900px; }}
  .transaction-table {{ min-width:1160px; }}
  th,td {{ padding:10px 9px; border-bottom:1px solid #e8edf1; text-align:left; vertical-align:top; }}
  th {{ position:sticky; top:0; z-index:2; background:#edf2f4; color:#52616e;
    font-size:9px; text-transform:uppercase; letter-spacing:.04em; }}
  th small,td small {{ display:block; margin-top:3px; color:#7a8895; font-size:9px;
    font-weight:500; text-transform:none; letter-spacing:0; }}
  th.num,td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  tbody tr:hover {{ background:#f7faf9; }}
  .growth {{ display:inline-flex; border-radius:99px; padding:4px 8px; font-weight:850; }}
  .growth.positive {{ color:var(--positive); background:var(--positive-soft); }}
  .growth.negative {{ color:var(--negative); background:var(--negative-soft); }}
  .growth.neutral {{ color:var(--muted); background:#eef1f3; }}
  .na {{ color:#84909a; font-size:9px; font-weight:650; }}
  .annual-table td {{ min-width:130px; }}
  .ledger-controls {{ display:flex; align-items:flex-end; gap:9px; flex-wrap:wrap; margin:11px 0; }}
  .ledger-controls label {{ display:flex; flex-direction:column; gap:4px; color:var(--muted);
    font-size:9px; font-weight:800; text-transform:uppercase; letter-spacing:.04em; }}
  select,input {{ min-width:170px; border:1px solid var(--line); border-radius:9px; background:white;
    color:var(--ink); padding:9px 10px; font:inherit; font-size:11px; }}
  .search-label {{ flex:1; }} .search-label input {{ width:100%; min-width:220px; }}
  .visible-count {{ margin-left:auto; padding:9px 0; color:var(--muted); font-size:10px; }}
  .ledger-wrap {{ max-height:650px; }} .transaction-table th {{ top:0; }}
  .partial {{ display:block; width:max-content; margin-top:4px; border-radius:99px;
    padding:2px 5px; color:var(--warm); background:#fff1d6; font-size:8px; font-weight:850; }}
  .footer-note {{ margin-top:28px; padding:16px 18px; border-left:4px solid var(--warm);
    background:white; color:var(--muted); font-size:11px; line-height:1.6; }}
  @media(max-width:900px) {{
    .method-grid,.project-metrics {{ grid-template-columns:repeat(2,1fr); }}
    .project-heading {{ display:block; }} .history-pill {{ margin-top:12px; min-width:0; }}
  }}
  @media(max-width:560px) {{
    main {{ padding:28px 15px 50px; }}
    .method-grid,.project-metrics {{ grid-template-columns:1fr; }}
    .visible-count {{ width:100%; margin:0; }}
  }}
</style>
</head>
<body><main>
<div class="eyebrow">Transaction ledger · unit-type growth · generated {_esc(as_of.isoformat())}</div>
<h1>What sold, and how each condo’s unit types moved</h1>
<p class="lede">A transaction-by-transaction companion to the Poiz versus East-side comparison. Select a condominium to inspect rolling 12-month growth by bedroom type, calendar-year medians, and every available resale caveat.</p>
<a class="back-link" href="poiz_east_resale_comparison.html">← Return to the project comparison</a>
<div class="method-grid">
  <article><b>{len(projects)}</b><span>condominiums, kept separate rather than collapsed into one project ranking</span></article>
  <article><b>{transaction_total:,}</b><span>available resale transaction records, including {partial_total} in the disclosed partial month</span></article>
  <article><b>{_esc(periods['recent_start'])}–{_esc(periods['full_end'])}</b><span>latest 12 complete months compared with {_esc(periods['prior_start'])}–{_esc(periods['prior_end'])}</span></article>
  <article><b>n ≥ {MIN_GROWTH_SAMPLE} + {MIN_GROWTH_SAMPLE}</b><span>minimum recent and prior samples before a growth percentage is displayed</span></article>
</div>
<div class="identity-note"><b>Important unit limitation:</b> exact apartment numbers are not published in the source caveats. “Unit type” means bedroom count, observed size and floor range. Growth is the change in median achieved sales for that type—not verified appreciation of the same physical apartment.</div>
<nav class="project-tabs" aria-label="Choose condominium">{tabs}</nav>
{panels}
<div class="footer-note"><b>Evidence notes.</b> Growth excludes the partial {_esc(periods['partial'])} month. URA caveats are voluntary and not exhaustive; older EdgeProp backfill rows are identified in the ledger. Bedroom counts are secondary row matches because URA does not publish bedrooms. Price growth can remain mix-sensitive even inside a bedroom category because size, floor, facing, condition and view are not identical. Floor values are published ranges, not exact floors.</div>
</main>
<script>
function activateProject(slug) {{
  document.querySelectorAll(".project-tab").forEach(function(button) {{
    button.classList.toggle("active", button.dataset.project === slug);
  }});
  document.querySelectorAll(".project-panel").forEach(function(panel) {{
    panel.classList.toggle("active", panel.dataset.project === slug);
  }});
  if (history.replaceState) history.replaceState(null, "", "#" + slug);
}}

document.querySelectorAll(".project-tab").forEach(function(button) {{
  button.addEventListener("click", function() {{ activateProject(button.dataset.project); }});
}});

function applyLedgerFilter(panel) {{
  var unit = panel.querySelector(".txn-unit").value;
  var year = panel.querySelector(".txn-year").value;
  var search = panel.querySelector(".txn-search").value.trim().toLowerCase();
  var visible = 0;
  panel.querySelectorAll(".transaction-table tbody tr").forEach(function(row) {{
    var show = (unit === "all" || row.dataset.unit === unit) &&
      (year === "all" || row.dataset.year === year) &&
      (!search || row.dataset.search.indexOf(search) !== -1);
    row.hidden = !show;
    if (show) visible += 1;
  }});
  panel.querySelector(".visible-count").textContent =
    visible.toLocaleString() + " record" + (visible === 1 ? "" : "s") + " shown";
}}

document.querySelectorAll(".project-panel").forEach(function(panel) {{
  panel.querySelectorAll(".txn-unit,.txn-year").forEach(function(control) {{
    control.addEventListener("change", function() {{ applyLedgerFilter(panel); }});
  }});
  panel.querySelector(".txn-search").addEventListener("input", function() {{
    applyLedgerFilter(panel);
  }});
}});

var requested = window.location.hash.slice(1);
if (requested && document.querySelector("[data-project='" + requested + "']")) {{
  activateProject(requested);
}}
</script>
</body></html>"""


def generate(
    profiles_path: pathlib.Path = DEFAULT_PROFILES,
    transactions_path: pathlib.Path = DEFAULT_TRANSACTIONS,
    out_path: pathlib.Path = DEFAULT_OUT,
    as_of: date | None = None,
) -> tuple[pathlib.Path, list[dict[str, Any]], dict[str, str]]:
    as_of = as_of or date.today()
    profiles = load_profiles(profiles_path)
    txns = load_transactions(transactions_path, set(profiles["project"]))
    missing = sorted(set(profiles["project"]) - set(txns["project"]))
    if missing:
        raise SystemExit(f"no resale rows for profiled projects: {missing}")
    projects, periods = build_projects(profiles, txns, as_of)
    out_path.write_text(render_html(projects, periods, as_of), encoding="utf-8")
    return out_path, projects, periods


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate unit-type growth and resale transaction ledgers"
    )
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES))
    parser.add_argument("--transactions", default=str(DEFAULT_TRANSACTIONS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path, projects, periods = generate(
        pathlib.Path(args.profiles),
        pathlib.Path(args.transactions),
        pathlib.Path(args.out),
    )
    print(
        f"Written: {out_path} ({len(projects)} projects, "
        f"{sum(len(project['transactions']) for project in projects):,} resale records, "
        f"growth through {periods['full_end']})"
    )


if __name__ == "__main__":
    main()
