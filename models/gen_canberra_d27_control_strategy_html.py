#!/usr/bin/env python3
"""
Generate three Canberra / District 27 comparison-control workbooks.

These private-project diagnostics sit on the Liveability/Value side of the
framework. They do not create a unified condo ranking and do not feed project
facts into estate-level Provision scores.

Writes:
  canberra_strategy_4_unit_matching.html
  canberra_strategy_5_sale_state.html
  canberra_strategy_6_planning_context.html
"""

from __future__ import annotations

import argparse
import html
import pathlib
from datetime import date
from typing import Any

import pandas as pd

import gen_canberra_crescent_d27_html as core


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_OUTPUT_DIR = ROOT
UNIT_PROJECTS = (
    core.SUBJECT,
    "THE WATERGARDENS AT CANBERRA",
    "THE COMMODORE",
    "CANBERRA RESIDENCES",
)
PEER_LABELS = {
    core.SUBJECT: "Subject launch",
    "THE WATERGARDENS AT CANBERRA": "Closest completed precinct peer",
    "THE COMMODORE": "Closest newer precinct peer",
    "CANBERRA RESIDENCES": "Older same-precinct control",
}
STRATEGY_PAGES = (
    ("1", "Micro-location", "canberra_strategy_1_micro_location.html"),
    ("2", "Newness", "canberra_strategy_2_newness.html"),
    ("3", "Integration", "canberra_strategy_3_integration.html"),
    ("4", "Unit matching", "canberra_strategy_4_unit_matching.html"),
    ("5", "Sale states", "canberra_strategy_5_sale_state.html"),
    ("6", "Planning context", "canberra_strategy_6_planning_context.html"),
)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if value >= 1_000_000:
        return f"S${value / 1_000_000:.3f}m"
    return f"S${value:,.0f}"


def num(
    value: float | None,
    *,
    prefix: str = "",
    suffix: str = "",
    digits: int = 0,
) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{prefix}{float(value):,.{digits}f}{suffix}"


def delta(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    css = "up" if value > 0 else "down" if value < 0 else ""
    return f"<span class='{css}'>{float(value):+.1f}%</span>"


def pct_delta(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or pd.isna(value) or pd.isna(base) or base == 0:
        return None
    return (float(value) / float(base) - 1.0) * 100.0


def describe(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {
            "n": 0,
            "median_price": None,
            "median_psf": None,
            "median_sqft": None,
            "p25_psf": None,
            "p75_psf": None,
        }
    return {
        "n": int(len(group)),
        "median_price": float(group["price"].median()),
        "median_psf": float(group["psf"].median()),
        "median_sqft": float(group["sqft"].median()),
        "p25_psf": float(group["psf"].quantile(0.25)),
        "p75_psf": float(group["psf"].quantile(0.75)),
    }


def table(headers: list[str], rows: list[list[str]], class_name: str = "") -> str:
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        f"<div class='table-wrap'><table class='{esc(class_name)}'>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def nav(active: str) -> str:
    links = []
    for number, label, filename in STRATEGY_PAGES:
        active_class = " active" if number == active else ""
        links.append(
            f"<a class='strategy-link{active_class}' href='{esc(filename)}'>"
            f"<span>{number}</span>{esc(label)}</a>"
        )
    return (
        "<nav class='report-nav' aria-label='Canberra comparison workbooks'>"
        "<a class='hub-link' href='canberra_crescent_d27_deep_analysis.html'>"
        "← District analysis</a>"
        f"<div class='strategy-links'>{''.join(links)}</div></nav>"
    )


def page(
    *,
    active: str,
    kicker: str,
    title: str,
    standfirst: str,
    body: str,
    as_of: date,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#092f2b">
  <title>{esc(title)}</title>
  <style>
    :root {{
      --ink:#12211f; --muted:#5f6e6b; --paper:#f4f0e8; --card:#fffdf8;
      --green:#0d574f; --green-2:#0b3733; --mint:#d9ebe4; --line:#d8d4c9;
      --amber:#c98128; --red:#a24639; --shadow:0 16px 42px rgba(21,42,38,.09);
    }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{
      margin:0; color:var(--ink); background:var(--paper);
      font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      overflow-wrap:anywhere;
    }}
    a {{ color:var(--green); text-underline-offset:3px; }}
    .shell {{ width:min(1180px,calc(100% - 40px)); margin:0 auto; }}
    .report-nav {{
      position:sticky; top:0; z-index:10; background:rgba(244,240,232,.96);
      backdrop-filter:blur(12px); border-bottom:1px solid var(--line); padding:12px max(20px,calc((100vw - 1180px)/2));
    }}
    .hub-link {{ display:inline-flex; min-height:42px; align-items:center; font-weight:750; text-decoration:none; }}
    .strategy-links {{
      display:flex; gap:8px; overflow-x:auto; padding:8px 0 2px;
      scrollbar-width:thin; -webkit-overflow-scrolling:touch;
    }}
    .strategy-link {{
      flex:0 0 auto; display:flex; align-items:center; gap:7px; min-height:42px;
      padding:7px 11px; border:1px solid var(--line); border-radius:999px;
      background:var(--card); text-decoration:none; color:var(--ink); font-weight:700;
    }}
    .strategy-link span {{
      width:24px; height:24px; display:grid; place-items:center; border-radius:50%;
      color:white; background:var(--green);
    }}
    .strategy-link.active {{ color:white; background:var(--green-2); border-color:var(--green-2); }}
    .hero {{
      color:white; padding:76px 0 68px;
      background:
        radial-gradient(circle at 85% 18%,rgba(217,235,228,.18),transparent 27%),
        linear-gradient(135deg,#092f2b,#0d574f 72%,#407b68);
    }}
    .kicker {{ margin:0 0 12px; color:#bfe1d6; font-size:.78rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; }}
    h1 {{ max-width:880px; margin:0; font:700 clamp(2.15rem,6vw,4.7rem)/1.02 Georgia,serif; letter-spacing:-.045em; }}
    .standfirst {{ max-width:780px; margin:24px 0 0; color:#e3f0ec; font-size:clamp(1rem,2.2vw,1.25rem); }}
    .meta {{ display:flex; flex-wrap:wrap; gap:9px; margin-top:28px; }}
    .meta span {{ border:1px solid rgba(255,255,255,.25); border-radius:999px; padding:7px 11px; font-size:.82rem; }}
    main {{ padding:44px 0 70px; }}
    section {{ margin:0 0 46px; scroll-margin-top:120px; }}
    h2 {{ margin:0 0 11px; font:700 clamp(1.55rem,3.5vw,2.4rem)/1.12 Georgia,serif; letter-spacing:-.025em; }}
    h3 {{ margin:0 0 7px; font-size:1rem; }}
    .lede {{ max-width:820px; margin:0 0 21px; color:var(--muted); }}
    .cards {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
    .card {{
      min-width:0; background:var(--card); border:1px solid var(--line);
      border-radius:18px; padding:20px; box-shadow:var(--shadow);
    }}
    .card p {{ margin:5px 0 0; color:var(--muted); }}
    .eyebrow {{ color:var(--green); font-size:.72rem; font-weight:850; letter-spacing:.1em; text-transform:uppercase; }}
    .metric {{ display:block; margin:7px 0 3px; font:700 clamp(1.55rem,3vw,2.2rem)/1.05 Georgia,serif; }}
    .note {{
      border-left:4px solid var(--amber); background:#fff7e8; border-radius:4px 14px 14px 4px;
      padding:15px 17px; color:#5a4630; margin:18px 0;
    }}
    .method {{ border-left-color:var(--green); background:var(--mint); color:#1c4841; }}
    .table-wrap {{
      width:100%; overflow-x:auto; border:1px solid var(--line); border-radius:16px;
      background:var(--card); box-shadow:var(--shadow); -webkit-overflow-scrolling:touch;
    }}
    table {{ width:100%; min-width:760px; border-collapse:collapse; }}
    th {{
      position:sticky; top:0; z-index:1; background:#e7e2d7; color:#34413e;
      padding:12px; text-align:left; font-size:.7rem; letter-spacing:.055em; text-transform:uppercase;
    }}
    td {{ padding:12px; border-top:1px solid var(--line); vertical-align:top; }}
    tbody tr:hover {{ background:#f5faf7; }}
    td small, th small {{ display:block; margin-top:3px; color:var(--muted); font-size:.74rem; line-height:1.35; text-transform:none; letter-spacing:0; }}
    .num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
    .up {{ color:var(--red); font-weight:800; }}
    .down {{ color:var(--green); font-weight:800; }}
    .tag {{ display:inline-block; padding:3px 7px; border-radius:999px; background:var(--mint); color:var(--green-2); font-size:.7rem; font-weight:800; }}
    .timeline {{ display:grid; gap:13px; }}
    .event {{ display:grid; grid-template-columns:150px 1fr; gap:18px; align-items:start; }}
    .event .when {{ color:var(--green); font-weight:850; }}
    .source-list {{ padding-left:20px; }}
    footer {{ padding:28px 0 50px; border-top:1px solid var(--line); color:var(--muted); }}
    @media (max-width:820px) {{
      .cards {{ grid-template-columns:1fr 1fr; }}
      .event {{ grid-template-columns:110px 1fr; }}
    }}
    @media (max-width:600px) {{
      .shell {{ width:min(100% - 24px,1180px); }}
      .report-nav {{ padding:8px 12px; }}
      .strategy-link {{ min-height:44px; }}
      .hero {{ padding:50px 0 46px; }}
      main {{ padding-top:32px; }}
      section {{ margin-bottom:38px; }}
      .cards {{ grid-template-columns:1fr; }}
      .card {{ padding:17px; }}
      .event {{ grid-template-columns:1fr; gap:3px; }}
      table {{ min-width:680px; }}
      th,td {{ padding:10px; }}
    }}
    @media (prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} }}
  </style>
</head>
<body>
  {nav(active)}
  <header class="hero">
    <div class="shell">
      <p class="kicker">{esc(kicker)}</p>
      <h1>{esc(title)}</h1>
      <p class="standfirst">{esc(standfirst)}</p>
      <div class="meta">
        <span>Official URA caveats</span>
        <span>District 27 apartments &amp; condos</span>
        <span>Data through July 2026; headline window through June</span>
        <span>Generated {as_of.isoformat()}</span>
      </div>
    </div>
  </header>
  <main class="shell">{body}</main>
  <footer><div class="shell">
    Private-project diagnostic only. Provision and Liveability remain separate;
    no unified condominium ranking is produced. HDB and private housing are not blended.
    <a href="index.html">All reports</a>.
  </div></footer>
</body>
</html>
"""


def current_window(
    txns: pd.DataFrame,
    as_of: date,
) -> tuple[pd.DataFrame, dict[str, pd.Period | None]]:
    window = core.comparison_window(txns, as_of)
    recent = txns[
        txns["sale_period"].between(window["current_start"], window["full_end"])
    ].copy()
    return recent, window


def unit_matching_rows(recent: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    subject = recent[recent["project_name"].eq(core.SUBJECT)]
    for unit_key in ("1", "2", "3", "4"):
        unit_subject = subject[subject["unit_key"].eq(unit_key)]
        for band in sorted(unit_subject["size_band_low"].unique()):
            subject_cell = unit_subject[unit_subject["size_band_low"].eq(band)]
            if len(subject_cell) < 3:
                continue
            subject_stats = describe(subject_cell)
            for peer in UNIT_PROJECTS[1:]:
                peer_cell = recent[
                    recent["project_name"].eq(peer)
                    & recent["unit_key"].eq(unit_key)
                    & recent["size_band_low"].eq(band)
                ]
                if len(peer_cell) < 3:
                    continue
                peer_stats = describe(peer_cell)
                rows.append(
                    {
                        "unit_key": unit_key,
                        "size_band": f"{band:,}–{band + 99:,} sqft",
                        "peer": peer,
                        "subject": subject_stats,
                        "peer_stats": peer_stats,
                        "delta_psf": pct_delta(
                            peer_stats["median_psf"], subject_stats["median_psf"]
                        ),
                        "delta_quantum": pct_delta(
                            peer_stats["median_price"], subject_stats["median_price"]
                        ),
                        "sale_state": " / ".join(
                            sorted(peer_cell["type_of_sale"].unique().tolist())
                        ),
                    }
                )
    return rows


def render_unit_matching(
    txns: pd.DataFrame,
    as_of: date,
) -> str:
    recent, window = current_window(txns, as_of)
    subject = describe(recent[recent["project_name"].eq(core.SUBJECT)])
    matched = unit_matching_rows(recent)
    project_rows = []
    for project in UNIT_PROJECTS:
        group = recent[recent["project_name"].eq(project)]
        stat = describe(group)
        bedroom_counts = group["unit_key"].value_counts()
        coverage = " · ".join(
            f"{key}BR {int(bedroom_counts.get(key, 0))}"
            for key in ("1", "2", "3", "4")
            if bedroom_counts.get(key, 0)
        )
        project_rows.append(
            [
                f"<b>{esc(project)}</b><small>{esc(PEER_LABELS[project])}</small>",
                f"<span class='tag'>{esc(' / '.join(sorted(group['type_of_sale'].unique())))}</span>",
                f"<span class='num'>{stat['n']}</span><small>{esc(coverage or 'Bedroom unavailable')}</small>",
                f"<span class='num'>{money(stat['median_price'])}</span>",
                f"<span class='num'>{num(stat['median_psf'], prefix='S$')}</span>",
                f"<span class='num'>{num(stat['median_sqft'], suffix=' sqft')}</span>",
            ]
        )
    matched_html_rows = []
    for row in matched:
        matched_html_rows.append(
            [
                f"<b>{row['unit_key']} bedroom</b><small>{esc(row['size_band'])}</small>",
                f"<b>{esc(row['peer'])}</b><small>{esc(row['sale_state'])}</small>",
                f"<span class='num'>{row['subject']['n']}</span>",
                f"<span class='num'>{money(row['subject']['median_price'])}</span><small>{num(row['subject']['median_psf'], prefix='S$')} PSF</small>",
                f"<span class='num'>{row['peer_stats']['n']}</span>",
                f"<span class='num'>{money(row['peer_stats']['median_price'])}</span><small>{num(row['peer_stats']['median_psf'], prefix='S$')} PSF</small>",
                f"<span class='num'>{delta(row['delta_psf'])}</span><small>peer vs subject PSF</small>",
                f"<span class='num'>{delta(row['delta_quantum'])}</span><small>peer vs subject quantum</small>",
            ]
        )
    if not matched_html_rows:
        matched_html_rows = [[
            "<b>No sufficiently deep cells</b>",
            "Bedroom and 100-sqft controls",
            "—", "—", "—", "—", "—",
            "A missing cell is evidence of weak comparability, not permission to widen it silently.",
        ]]

    floor_rows = []
    subject_txns = recent[recent["project_name"].eq(core.SUBJECT)]
    for (unit_key, floor), group in subject_txns.groupby(
        ["unit_key", "floor_level"], dropna=False
    ):
        if unit_key == "unknown":
            continue
        stat = describe(group)
        floor_rows.append(
            [
                f"<b>{esc(unit_key)} bedroom</b>",
                esc(core.clean_text(floor, "Unavailable")),
                f"<span class='num'>{stat['n']}</span>",
                f"<span class='num'>{money(stat['median_price'])}</span>",
                f"<span class='num'>{num(stat['median_psf'], prefix='S$')}</span>",
                f"<span class='num'>{num(stat['median_sqft'], suffix=' sqft')}</span>",
            ]
        )

    cards = f"""
    <div class="cards">
      <article class="card"><span class="eyebrow">Subject median</span>
        <b class="metric">{num(subject['median_psf'], prefix='S$')}</b>
        <p>PSF across {subject['n']} complete-month launch caveats.</p></article>
      <article class="card"><span class="eyebrow">Strict matched cells</span>
        <b class="metric">{len(matched)}</b>
        <p>Bedroom + 100-sqft cells where subject and peer each have at least three caveats.</p></article>
      <article class="card"><span class="eyebrow">Control order</span>
        <b class="metric">Bed → size → floor</b>
        <p>Quantum and sale state stay visible beside PSF.</p></article>
    </div>"""
    body = f"""
    <section>
      <h2>The comparison rule</h2>
      <p class="lede">Start with bedroom type, restrict to the same 100-sqft band,
      then inspect floor. Report both total quantum and PSF. Cells below n=3 are
      withheld from strict comparisons so one unusual caveat cannot masquerade as a market.</p>
      <div class="note method"><b>Window:</b> {window['current_start']} to {window['full_end']}.
      July 2026 is partial and excluded. Bedroom labels are conservatively attributed
      from EdgeProp to the official URA rows; exact apartment numbers are unavailable.</div>
      {cards}
    </section>
    <section>
      <h2>Peer coverage before matching</h2>
      <p class="lede">This table shows why an all-unit median is only an orientation.
      Project mix, compactness and transaction state differ materially.</p>
      {table(['Project / role','Sale state','n / bedroom coverage','Median quantum','Median PSF','Median size'], project_rows)}
    </section>
    <section>
      <h2>Strict bedroom-and-size matches</h2>
      <p class="lede">Positive deltas mean the peer is above Canberra Crescent;
      negative deltas mean it is below. These are achieved-price gaps, not growth forecasts.</p>
      {table(['Matched cohort','Peer / state','Subject n','Subject result','Peer n','Peer result','PSF gap','Quantum gap'], matched_html_rows)}
    </section>
    <section>
      <h2>Subject floor-band audit</h2>
      <p class="lede">Launch release sequencing across floor bands can move monthly
      medians even when underlying pricing has not appreciated.</p>
      {table(['Unit type','URA floor band','n','Median quantum','Median PSF','Median size'], floor_rows)}
    </section>
    <section>
      <h2>Interpretation</h2>
      <div class="cards">
        <article class="card"><h3>Compact-unit distortion</h3><p>Smaller homes often carry a
        higher PSF while preserving a lower entry quantum. A PSF premium without the
        quantum column is incomplete.</p></article>
        <article class="card"><h3>Floor is a second-order control</h3><p>URA publishes bands,
        not exact floors. Compare within the band and retain sample counts.</p></article>
        <article class="card"><h3>Thinness is a finding</h3><p>If a peer has no matching
        cell, disclose the absence. Do not replace it with a convenient all-unit average.</p></article>
      </div>
    </section>
    """
    return page(
        active="4",
        kicker="Strategy 04 · Bedroom, size and floor controls",
        title="Match the home before comparing the price",
        standfirst=(
            "A unit-matched Canberra Crescent workbook that keeps bedroom type, "
            "100-sqft size band, floor band, quantum and PSF in one view."
        ),
        body=body,
        as_of=as_of,
    )


def sale_state_rows(txns: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    complete = txns[txns["sale_period"].le(pd.Period("2026-06", freq="M"))]
    for (year, state), group in complete.groupby(["year", "type_of_sale"], sort=True):
        stat = describe(group)
        rows.append(
            [
                f"<b>{int(year)}</b>",
                f"<span class='tag'>{esc(state)}</span>",
                f"<span class='num'>{stat['n']}</span>",
                f"<span class='num'>{group['project_name'].nunique()}</span>",
                f"<span class='num'>{money(stat['median_price'])}</span>",
                f"<span class='num'>{num(stat['median_psf'], prefix='S$')}</span><small>{num(stat['p25_psf'], prefix='S$')}–{num(stat['p75_psf'], prefix='S$')} IQR</small>",
                f"<span class='num'>{num(stat['median_sqft'], suffix=' sqft')}</span>",
            ]
        )
    return rows


def render_sale_state(
    txns: pd.DataFrame,
    as_of: date,
) -> str:
    recent, window = current_window(txns, as_of)
    state_cards = []
    for state in ("New Sale", "Sub Sale", "Resale"):
        group = recent[recent["type_of_sale"].eq(state)]
        stat = describe(group)
        state_cards.append(
            f"<article class='card'><span class='eyebrow'>{esc(state)}</span>"
            f"<b class='metric'>{stat['n']:,}</b><p>{group['project_name'].nunique()} projects · "
            f"{num(stat['median_psf'], prefix='S$')} median PSF · {money(stat['median_price'])} median quantum.</p></article>"
        )

    project_records = []
    for (state, project), group in recent.groupby(
        ["type_of_sale", "project_name"], sort=True
    ):
        stat = describe(group)
        project_records.append(
            {
                "state": state,
                "n": stat["n"],
                "row": [
                f"<span class='tag'>{esc(state)}</span>",
                f"<b>{esc(project)}</b>",
                f"<span class='num'>{stat['n']}</span>",
                f"<span class='num'>{money(stat['median_price'])}</span>",
                f"<span class='num'>{num(stat['median_psf'], prefix='S$')}</span>",
                f"<span class='num'>{num(stat['median_sqft'], suffix=' sqft')}</span>",
                f"{group['sale_period'].min()}–{group['sale_period'].max()}",
                ],
            }
        )
    project_records.sort(
        key=lambda record: (
            {"New Sale": 0, "Sub Sale": 1, "Resale": 2}.get(record["state"], 9),
            -record["n"],
        )
    )
    project_rows = [record["row"] for record in project_records]

    subject = recent[recent["project_name"].eq(core.SUBJECT)]
    month_rows = []
    first_psf = None
    for month, group in subject.groupby("sale_period", sort=True):
        stat = describe(group)
        if first_psf is None:
            first_psf = stat["median_psf"]
        mix = group["unit_key"].value_counts()
        mix_text = " · ".join(
            f"{unit}BR {int(mix.get(unit, 0))}"
            for unit in ("1", "2", "3", "4")
            if mix.get(unit, 0)
        )
        month_rows.append(
            [
                f"<b>{month}</b>",
                f"<span class='num'>{stat['n']}</span>",
                f"<span class='num'>{money(stat['median_price'])}</span>",
                f"<span class='num'>{num(stat['median_psf'], prefix='S$')}</span>",
                f"<span class='num'>{delta(pct_delta(stat['median_psf'], first_psf))}</span>",
                esc(mix_text),
            ]
        )

    body = f"""
    <section>
      <h2>Three different price-forming processes</h2>
      <p class="lede">New Sale reflects developer release and booking strategy.
      Sub Sale reflects pre-completion or early-completion assignments. Resale reflects
      owner decisions, unit condition, remaining lease and a lived-in project market.
      They can be compared side by side, but not spliced into one appreciation line.</p>
      <div class="cards">{''.join(state_cards)}</div>
      <div class="note method"><b>Headline window:</b> {window['current_start']} to {window['full_end']}.
      Counts are caveats, not unique buyers. July 2026 remains in the full district
      ledger but is excluded here because it is partial.</div>
    </section>
    <section>
      <h2>State-by-year district evidence</h2>
      <p class="lede">Project breadth reveals whether a median is broad market evidence
      or dominated by one launch. The state column must remain part of every reading.</p>
      {table(['Year','Sale state','Caveats','Projects','Median quantum','Median PSF / IQR','Median size'], sale_state_rows(txns))}
    </section>
    <section>
      <h2>Current-window project liquidity</h2>
      <p class="lede">Transaction count is shown within state. A high launch count is
      absorption evidence; it is not the same as resale exit liquidity.</p>
      {table(['Sale state','Project','n','Median quantum','Median PSF','Median size','Observed months'], project_rows)}
    </section>
    <section>
      <h2>Canberra Crescent launch sequence</h2>
      <p class="lede">The first launch month is the reference only to reveal changing
      booked-unit mix. It is not an apartment repeat-sale comparison and therefore is
      not labelled capital growth.</p>
      {table(['Month','Caveats','Median quantum','Median PSF','PSF vs first month','Bedroom mix'], month_rows)}
    </section>
    <section>
      <h2>How to read an exit thesis</h2>
      <div class="cards">
        <article class="card"><h3>Launch absorption</h3><p>Use subject caveat count,
        bedroom mix and booked quantum. Do not call caveat-to-stock a confirmed sell-through rate.</p></article>
        <article class="card"><h3>Resale liquidity</h3><p>Use completed peers' resale
        counts and project breadth. This tests observed exits, not the subject's future demand.</p></article>
        <article class="card"><h3>Sub-sale bridge</h3><p>Read separately because seller
        constraints and completion timing differ from both developer sales and mature resale.</p></article>
      </div>
    </section>
    """
    return page(
        active="5",
        kicker="Strategy 05 · Sale-state and liquidity controls",
        title="Keep launch, sub-sale and resale evidence apart",
        standfirst=(
            "District 27 liquidity separated by the transaction state that formed "
            "the price, so launch absorption is never presented as verified growth."
        ),
        body=body,
        as_of=as_of,
    )


def planning_rows() -> list[list[str]]:
    plans = [
        (
            "Canberra MRT and Canberra Plaza",
            "Delivered",
            "Present",
            "Current access and amenity evidence. Already available; do not count it again as future upside.",
            "https://www.lta.gov.sg/content/ltagov/en/getting_around/public_transport/rail_network/north_south_line.html",
            "LTA",
        ),
        (
            "North-South Corridor",
            "Committed / under construction",
            "Viaduct targeted 2027; tunnel targeted 2029",
            "Transport and public-realm context. Timing and indirect access effects remain execution-sensitive.",
            "https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/road_commuter_facilities/north_south_corridor.html/",
            "LTA",
        ),
        (
            "RTS Link and Woodlands Regional Centre",
            "Committed plus multi-stage district",
            "RTS targeted end-2026; regional-centre build-out is broader",
            "Northern employment and cross-border context, not direct integration at Canberra.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/north/powering-industry-and-work-spaces--enhancing-the-rustic-region-and-its-past/",
            "URA",
        ),
        (
            "Sembawang Shipyard transformation",
            "Long-dated planning concept",
            "Operations expected to wind down from 2028",
            "Retain as optional context. No price uplift, opening year or delivery certainty is assumed.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/north/sembawang-shipyard/",
            "URA",
        ),
        (
            "Additional North-region housing",
            "Progressive supply",
            "Multi-stage",
            "May deepen amenities and the household base while also creating competing future stock.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/north/home-for-all--nearby-to-nature/",
            "URA",
        ),
    ]
    return [
        [
            f"<b>{esc(name)}</b>",
            f"<span class='tag'>{esc(status)}</span>",
            esc(horizon),
            esc(treatment),
            f"<a href='{esc(url)}'>{esc(authority)} primary source</a>",
        ]
        for name, status, horizon, treatment, url, authority in plans
    ]


def render_planning(
    txns: pd.DataFrame,
    as_of: date,
) -> str:
    recent, window = current_window(txns, as_of)
    subject = recent[recent["project_name"].eq(core.SUBJECT)]
    cards = f"""
    <div class="cards">
      <article class="card"><span class="eyebrow">Delivered</span>
        <b class="metric">Price today</b><p>Canberra MRT and current amenities belong
        in present access evidence, not a future-upside bucket.</p></article>
      <article class="card"><span class="eyebrow">Committed</span>
        <b class="metric">Scenario only</b><p>Keep authority target dates visible and
        test delay or indirect-benefit risk.</p></article>
      <article class="card"><span class="eyebrow">Concept</span>
        <b class="metric">No uplift</b><p>Long-dated planning ideas support narrative
        context but are assigned no achieved-price premium.</p></article>
    </div>"""

    exposure_rows = [
        [
            "<b>Canberra Crescent Residences</b>",
            "Canberra precinct",
            "Current MRT/retail access is part of today's proposition",
            "NSC and wider North-region development",
            "Shipyard concept timing; future competing supply",
        ],
        [
            "<b>The Watergardens / The Commodore</b>",
            "Closest Canberra controls",
            "Share much of the same delivered neighbourhood evidence",
            "Useful control: common area plans reduce false attribution",
            "Completion and sale-state differences remain",
        ],
        [
            "<b>North Park Residences</b>",
            "Yishun integrated control",
            "Direct mature town-centre integration",
            "Tests the market value of integration already delivered",
            "Different town, age and remaining lease",
        ],
        [
            "<b>The Wisteria / Nine Residences</b>",
            "Yishun mixed-use controls",
            "Delivered retail convenience with different rail access",
            "Secondary integration controls",
            "Location and project-age drift",
        ],
    ]

    body = f"""
    <section>
      <h2>An evidence ladder, not an uplift score</h2>
      <p class="lede">Planning information is classified by delivery status. Delivered
      infrastructure belongs in current liveability. Committed work is scenario context.
      Concepts receive no price uplift. This avoids double-counting current amenities and
      treating policy intent as a completed asset.</p>
      {cards}
      <div class="note method"><b>Transaction anchor:</b> {len(subject)} subject caveats
      in the complete {window['current_start']}–{window['full_end']} window. Planning
      evidence does not alter their achieved prices.</div>
    </section>
    <section>
      <h2>Official planning register</h2>
      <p class="lede">Target dates and statuses follow the linked authority pages as
      reviewed on {as_of.isoformat()}. A target is not a guarantee; re-verify before a purchase decision.</p>
      {table(['Plan / asset','Evidence class','Published horizon','Treatment in comparison','Primary source'], planning_rows())}
    </section>
    <section>
      <h2>Peer exposure matrix</h2>
      <p class="lede">The closest Canberra peers share much of the area story. That
      makes them useful controls: a district-wide plan should not be credited only to
      the subject.</p>
      {table(['Project group','Role','Delivered evidence','Future context','Main confounder'], exposure_rows)}
    </section>
    <section>
      <h2>Decision rules</h2>
      <div class="timeline">
        <article class="card event"><div class="when">Delivered</div><div><h3>Observe it now</h3>
        <p>Check actual access, amenity quality and achieved peer prices. Do not label
        an existing asset as an unpriced catalyst.</p></div></article>
        <article class="card event"><div class="when">Targeted</div><div><h3>Use scenarios</h3>
        <p>Compare on-time, delayed and weaker-than-expected benefit cases. Keep the
        authority target date beside the claim.</p></div></article>
        <article class="card event"><div class="when">Conceptual</div><div><h3>Assign zero base-case uplift</h3>
        <p>Record optionality and competing-supply risk, but require a firmer delivery
        commitment before changing a valuation assumption.</p></div></article>
      </div>
    </section>
    <section>
      <h2>Source and caveat register</h2>
      <ul class="source-list">
        <li>URA official private residential caveats provide transaction evidence;
        they do not identify exact apartments or prove repeat-sale growth.</li>
        <li>LTA and URA pages provide project status and planning context. Published
        target dates may change after this report date.</li>
        <li>No planning item is converted into a condominium score, forecast return,
        guaranteed appreciation rate or Provision component.</li>
      </ul>
    </section>
    """
    return page(
        active="6",
        kicker="Strategy 06 · Planning evidence controls",
        title="Treat future plans as context, not booked returns",
        standfirst=(
            "A source-led evidence ladder for Canberra and northern Singapore that "
            "separates delivered amenities, committed projects and long-dated concepts."
        ),
        body=body,
        as_of=as_of,
    )


def generate(
    raw_path: pathlib.Path,
    edgeprop_path: pathlib.Path,
    output_dir: pathlib.Path,
    as_of: date,
) -> list[pathlib.Path]:
    txns = core.load_district_transactions(raw_path, edgeprop_path)
    outputs = [
        output_dir / "canberra_strategy_4_unit_matching.html",
        output_dir / "canberra_strategy_5_sale_state.html",
        output_dir / "canberra_strategy_6_planning_context.html",
    ]
    contents = [
        render_unit_matching(txns, as_of),
        render_sale_state(txns, as_of),
        render_planning(txns, as_of),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, content in zip(outputs, contents):
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=pathlib.Path, default=core.DEFAULT_RAW)
    parser.add_argument("--edgeprop", type=pathlib.Path, default=core.DEFAULT_EDGEPROP)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(args.raw, args.edgeprop, args.output_dir, args.as_of)


if __name__ == "__main__":
    main()
