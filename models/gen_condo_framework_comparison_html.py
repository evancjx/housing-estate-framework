#!/usr/bin/env python3
"""
Generate an interactive two-condominium framework comparison.

This page keeps two evidence layers distinct:

- project evidence: achieved transactions, tenure, size, MRT and schools;
- estate context: the same Provision, Liveability, Value, Employment, Risk
  and Life Path factor families shown in ``comparison_table.html``.

Estate scores are context for a project's planning area (or a disclosed proxy);
they are never represented as condominium scores. HDB Value and the HDB lease
risk band are explicitly not applied to private condominium projects.

Reads:
  data/inputs/ura_private.csv
  data/inputs/estates.csv
  data/inputs/mrt_layer.csv
  data/outputs/private_project_locations.csv
  data/outputs/private_project_school_metrics.csv
  data/outputs/master_output.csv
  data/outputs/provision_scores.csv
  data/outputs/employment_scores_{T0,T5,T15}.csv
  data/outputs/life_paths.csv

Writes:
  condo_framework_comparison.html
"""

from __future__ import annotations

import argparse
import html
import json
import math
import pathlib
from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

import gen_private_project_comparison_html as private_projects


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_PRIVATE = ROOT / "data/inputs/ura_private.csv"
DEFAULT_ESTATES = ROOT / "data/inputs/estates.csv"
DEFAULT_MRT = ROOT / "data/inputs/mrt_layer.csv"
DEFAULT_LOCATIONS = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_SCHOOLS = ROOT / "data/outputs/private_project_school_metrics.csv"
DEFAULT_MASTER = ROOT / "data/outputs/master_output.csv"
DEFAULT_PROVISION = ROOT / "data/outputs/provision_scores.csv"
DEFAULT_EMPLOYMENT_T0 = ROOT / "data/outputs/employment_scores_T0.csv"
DEFAULT_EMPLOYMENT_T5 = ROOT / "data/outputs/employment_scores_T5.csv"
DEFAULT_EMPLOYMENT_T15 = ROOT / "data/outputs/employment_scores_T15.csv"
DEFAULT_LIFE_PATHS = ROOT / "data/outputs/life_paths.csv"
DEFAULT_OUT = ROOT / "condo_framework_comparison.html"

SQM_TO_SQFT = 10.7639
GENERIC_PROJECT_NAMES = {"-", "N/A", "RESIDENTIAL APARTMENTS"}
FRAMEWORK_FIELDS = {
    "archetype",
    "d_t0",
    "provision_band",
    "provision_score",
    "noise",
    "yf_t0_band",
    "sp_t0_band",
    "ret_t0_band",
    "ls_t0_band",
    "ls_t5_band",
    "ls_t15_band",
    "gap_yf_t0",
    "gap_sp_t0",
    "gap_ret_t0",
    "gap_ls_t0",
    "private_value_band",
    "private_value_multiplier",
    "private_value_n",
    "employment_t0_band",
    "employment_t0_score",
    "employment_t5_band",
    "employment_t5_score",
    "employment_t15_band",
    "employment_t15_score",
    "best_node",
    "worst_node",
    "best_path",
    "best_path_shift",
    "best_path_delta",
    "worst_path",
    "worst_path_shift",
    "worst_path_delta",
    "flags",
}


def script_safe_json(value: Any) -> str:
    """Serialize JSON without allowing data to terminate an inline script."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def value_or_none(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text in {"nan", "NaN", "None", "not_covered", "N/A", "N/R"}:
        return None
    return value


def float_or_none(value: Any) -> float | None:
    value = value_or_none(value)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def text_or_none(value: Any) -> str | None:
    value = value_or_none(value)
    return str(value).strip() if value is not None else None


def normalise_estate(value: Any) -> str:
    return str(value).strip().upper()


def _estate_lookup(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if "estate" not in frame:
        raise SystemExit("estate lookup input missing estate column")
    return {
        normalise_estate(row["estate"]): row.to_dict()
        for _, row in frame.drop_duplicates("estate", keep="last").iterrows()
    }


def build_framework_contexts(
    master: pd.DataFrame,
    provision: pd.DataFrame,
    employment_t0: pd.DataFrame,
    employment_t5: pd.DataFrame,
    employment_t15: pd.DataFrame,
    life_paths: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Build one comparison-table-compatible context object per estate."""
    required_master = {
        "estate",
        "archetype",
        "provision_band",
        "provision_score",
        "D_T0",
        "yf_T0_band",
        "sp_T0_band",
        "ret_T0_band",
        "ls_T0_band",
        "ls_T5_band",
        "ls_T15_band",
        "gap_yf_T0",
        "gap_sp_T0",
        "gap_ret_T0",
        "gap_ls_T0",
        "value_private_band",
        "value_private_score",
        "value_private_n",
    }
    missing = sorted(required_master - set(master.columns))
    if missing:
        raise SystemExit(f"master output missing required columns: {missing}")
    for label, frame in {
        "provision": provision,
        "employment T0": employment_t0,
        "employment T5": employment_t5,
        "employment T15": employment_t15,
        "life paths": life_paths,
    }.items():
        if "estate" not in frame:
            raise SystemExit(f"{label} input missing estate column")

    master_lookup = _estate_lookup(master)
    provision_lookup = _estate_lookup(provision)
    employment = {
        "T0": _estate_lookup(employment_t0),
        "T5": _estate_lookup(employment_t5),
        "T15": _estate_lookup(employment_t15),
    }
    paths: dict[str, dict[str, Any]] = {}
    if {"path", "delta"}.issubset(life_paths.columns):
        prepared = life_paths.copy()
        prepared["delta"] = pd.to_numeric(prepared["delta"], errors="coerce")
        prepared = prepared.dropna(subset=["delta"])
        for estate, group in prepared.groupby(
            prepared["estate"].map(normalise_estate), sort=False
        ):
            best = group.loc[group["delta"].idxmax()]
            worst = group.loc[group["delta"].idxmin()]
            paths[estate] = {
                "best_path": text_or_none(best.get("path")),
                "best_path_shift": text_or_none(best.get("band_shift")),
                "best_path_delta": float_or_none(best.get("delta")),
                "worst_path": text_or_none(worst.get("path")),
                "worst_path_shift": text_or_none(worst.get("band_shift")),
                "worst_path_delta": float_or_none(worst.get("delta")),
            }

    contexts: dict[str, dict[str, Any]] = {}
    for estate, row in master_lookup.items():
        score = float_or_none(row.get("provision_score"))
        private_score = float_or_none(row.get("value_private_score"))
        private_multiplier = (
            private_score / score
            if score is not None and score > 0 and private_score is not None
            else None
        )
        provision_row = provision_lookup.get(estate, {})
        emp0 = employment["T0"].get(estate, {})
        emp5 = employment["T5"].get(estate, {})
        emp15 = employment["T15"].get(estate, {})
        d_t0 = float_or_none(row.get("D_T0"))
        contexts[estate] = {
            "context_estate": estate,
            "archetype": text_or_none(row.get("archetype")),
            "d_t0": 1.0 if d_t0 is None else d_t0,
            "provision_band": text_or_none(row.get("provision_band")),
            "provision_score": score,
            "noise": float_or_none(provision_row.get("noise")),
            "yf_t0_band": text_or_none(row.get("yf_T0_band")),
            "sp_t0_band": text_or_none(row.get("sp_T0_band")),
            "ret_t0_band": text_or_none(row.get("ret_T0_band")),
            "ls_t0_band": text_or_none(row.get("ls_T0_band")),
            "ls_t5_band": text_or_none(row.get("ls_T5_band")),
            "ls_t15_band": text_or_none(row.get("ls_T15_band")),
            "gap_yf_t0": float_or_none(row.get("gap_yf_T0")),
            "gap_sp_t0": float_or_none(row.get("gap_sp_T0")),
            "gap_ret_t0": float_or_none(row.get("gap_ret_T0")),
            "gap_ls_t0": float_or_none(row.get("gap_ls_T0")),
            "private_value_band": text_or_none(row.get("value_private_band")),
            "private_value_multiplier": private_multiplier,
            "private_value_n": (
                int(float(row["value_private_n"]))
                if float_or_none(row.get("value_private_n")) is not None
                else None
            ),
            "employment_t0_band": text_or_none(emp0.get("emp_band")),
            "employment_t0_score": float_or_none(emp0.get("emp_score")),
            "employment_t5_band": text_or_none(emp5.get("emp_band")),
            "employment_t5_score": float_or_none(emp5.get("emp_score")),
            "employment_t15_band": text_or_none(emp15.get("emp_band")),
            "employment_t15_score": float_or_none(emp15.get("emp_score")),
            "best_node": text_or_none(emp0.get("best_node")),
            "worst_node": text_or_none(emp0.get("worst_node")),
            **paths.get(estate, {}),
        }
        flags = []
        if contexts[estate]["archetype"] == "X":
            flags.append("Not rated")
        if contexts[estate]["d_t0"] < 1:
            flags.append("Current disruption")
        if private_multiplier is not None:
            if private_multiplier > 1.1:
                flags.append("Private segment above provision relationship")
            elif private_multiplier < 0.9:
                flags.append("Private segment below provision relationship")
        contexts[estate]["flags"] = flags
    return contexts


def prepare_projects(
    aggregate_rows: list[dict[str, Any]],
    contexts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Strip project aggregates to browser fields and add stable unique IDs."""
    rows = [
        row
        for row in aggregate_rows
        if str(row.get("project", "")).strip().upper() not in GENERIC_PROJECT_NAMES
    ]
    name_counts = Counter(str(row["project"]).strip().upper() for row in rows)
    used_ids: Counter[str] = Counter()
    projects = []
    for row in rows:
        project = str(row["project"]).strip()
        name_key = project.upper()
        base_id = private_projects.slug(project)
        if name_counts[name_key] > 1:
            base_id = (
                f"{base_id}-d{row['district']}-"
                f"{private_projects.slug(str(row.get('street', 'unknown')))}"
            )
        used_ids[base_id] += 1
        project_id = (
            base_id
            if used_ids[base_id] == 1
            else f"{base_id}-{used_ids[base_id]}"
        )
        selection_label = (
            project
            if name_counts[name_key] == 1
            else f"{project} · D{row['district']} / {row.get('street', 'Unknown street')}"
        )
        context_estate = normalise_estate(row.get("context_area", ""))
        context = contexts.get(context_estate, {})
        median_price_mil = float_or_none(row.get("median_price_mil"))
        median_area_sqm = float_or_none(row.get("median_area_sqm"))
        median_psm = float_or_none(row.get("median_psm"))
        project_row = {
            "id": project_id,
            "selection_label": selection_label,
            "project": project,
            "street": text_or_none(row.get("street")),
            "district": text_or_none(row.get("district")),
            "planning_area": text_or_none(row.get("planning_area")),
            "context_estate": context_estate or None,
            "context_basis": text_or_none(row.get("context_basis")),
            "property_type": text_or_none(row.get("property_type")),
            "tenure": text_or_none(row.get("tenure")),
            "market_segment": text_or_none(row.get("market_segment")),
            "transactions_n": int(row.get("n", 0)),
            "recent_n": int(row.get("recent_n", 0)),
            "first_sale": text_or_none(row.get("first_sale")),
            "last_sale": text_or_none(row.get("last_sale")),
            "sale_mix": text_or_none(row.get("sale_mix")),
            "median_price": (
                median_price_mil * 1_000_000 if median_price_mil is not None else None
            ),
            "median_psf": (
                median_psm / SQM_TO_SQFT if median_psm is not None else None
            ),
            "median_area_sqm": median_area_sqm,
            "median_area_sqft": (
                median_area_sqm * SQM_TO_SQFT
                if median_area_sqm is not None
                else None
            ),
            "recent_delta_pct": float_or_none(row.get("recent_delta_pct")),
            "district_delta_pct": float_or_none(row.get("district_delta_pct")),
            "station_display": text_or_none(row.get("station_display")),
            "station_distance_m": float_or_none(row.get("station_distance_m")),
            "station_status": text_or_none(row.get("station_status")),
            "location_source": text_or_none(row.get("location_source")),
            "primary_1km_count": (
                int(row["primary_1km_count"])
                if float_or_none(row.get("primary_1km_count")) is not None
                else None
            ),
            "primary_1km_schools": text_or_none(row.get("primary_1km_schools")),
            "best_primary_1km_school": text_or_none(
                row.get("best_primary_1km_school")
            ),
            "best_primary_1km_distance_m": float_or_none(
                row.get("best_primary_1km_distance_m")
            ),
            "school_metrics_source": text_or_none(
                row.get("school_metrics_source")
            ),
            **context,
        }
        if not context:
            project_row["flags"] = ["Estate framework context unavailable"]
        projects.append(project_row)
    projects.sort(
        key=lambda item: (
            item["project"].upper(),
            item["district"] or "",
            item["street"] or "",
        )
    )
    return projects


def _default_ids(projects: list[dict[str, Any]]) -> tuple[str, str]:
    by_name = {project["project"].upper(): project["id"] for project in projects}
    preferred = (
        ("THE POIZ RESIDENCES", "PARK PLACE RESIDENCES AT PLQ"),
        ("TREASURE AT TAMPINES", "PARC ESTA"),
    )
    for first, second in preferred:
        if first in by_name and second in by_name:
            return by_name[first], by_name[second]
    if len(projects) < 2:
        raise SystemExit("at least two named condominium projects are required")
    return projects[0]["id"], projects[1]["id"]


def _options_html(projects: list[dict[str, Any]]) -> str:
    return "".join(
        f'<option value="{html.escape(project["selection_label"], quote=True)}">'
        f'D{html.escape(project["district"] or "—")} · '
        f'{html.escape(project["planning_area"] or "Unknown area")} · '
        f'{html.escape(project["street"] or "Unknown street")}</option>'
        for project in projects
    )


def build_browser_payload(
    projects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Deduplicate estate framework context from browser project records."""
    browser_contexts: dict[str, dict[str, Any]] = {}
    browser_projects = []
    for project in projects:
        context_key = project.get("context_estate") or f"uncovered:{project['id']}"
        browser_contexts.setdefault(
            context_key,
            {field: project.get(field) for field in FRAMEWORK_FIELDS},
        )
        browser_project = {
            key: value for key, value in project.items() if key not in FRAMEWORK_FIELDS
        }
        browser_project["context_key"] = context_key
        browser_projects.append(browser_project)
    return browser_projects, browser_contexts


def render_html(
    projects: list[dict[str, Any]],
    latest_month: str | None,
    as_of: date,
) -> str:
    first_default, second_default = _default_ids(projects)
    browser_projects, browser_contexts = build_browser_payload(projects)
    project_json = script_safe_json(browser_projects)
    context_json = script_safe_json(browser_contexts)
    default_json = script_safe_json((first_default, second_default))
    options = _options_html(projects)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Two-condominium framework comparison</title>
<meta name="description" content="Compare two Singapore condominium projects using achieved project evidence and the estate Provision, Liveability, Value, employment and risk framework.">
<link rel="stylesheet" href="assets/research-shell.css" data-research-shell>
<style>
:root{{--ink:#18231f;--muted:#64716b;--paper:#f4f6f2;--card:#fff;--line:#d8e0da;--accent:#08786d;--accent-soft:#e1f2ed;--warm:#b25a35;--warm-soft:#fff0e7;--navy:#17324d;--shadow:0 20px 55px rgba(21,44,35,.09)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;padding:20px;background:var(--paper);color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}}
main{{max-width:1180px;margin:auto;padding:30px 0 72px}}a{{color:inherit}}h1,h2{{font-family:Georgia,"Times New Roman",serif;letter-spacing:-.04em}}h1{{max-width:900px;margin:.2em 0;font-size:clamp(2.8rem,7vw,5.8rem);font-weight:500;line-height:.96}}h2{{margin:60px 0 8px;font-size:clamp(1.8rem,4vw,3rem)}}p{{max-width:80ch}}
.eyebrow{{color:var(--accent);font-size:.7rem;font-weight:900;letter-spacing:.15em;text-transform:uppercase}}.lede{{color:var(--muted);font-size:1.08rem}}.hero{{padding:34px 0 38px;border-bottom:1px solid var(--line)}}.proof{{display:flex;gap:10px 26px;flex-wrap:wrap;margin-top:24px;color:var(--muted);font-size:.76rem;font-weight:700}}.proof span::before{{content:"";display:inline-block;width:6px;height:6px;margin:0 8px 1px 0;border-radius:50%;background:var(--accent)}}
.compare-panel{{margin:30px 0;padding:8px;border:1px solid var(--line);border-radius:22px;background:rgba(255,255,255,.58);box-shadow:var(--shadow)}}.compare-inner{{padding:22px;border-radius:15px;background:#fff}}.input-grid{{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:end}}label{{display:block;font-size:.69rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase}}input{{width:100%;min-height:49px;margin-top:6px;padding:11px 13px;border:1px solid #b9c9c1;border-radius:9px;background:#fff;color:var(--ink);font:inherit;outline:none}}input:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(8,120,109,.13)}}
.actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px}}button{{min-height:42px;padding:9px 14px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);font:inherit;font-size:.78rem;font-weight:850;cursor:pointer}}button.primary{{border-color:var(--accent);background:var(--accent);color:#fff}}button:hover{{border-color:var(--accent)}}.swap{{align-self:end;margin-bottom:3px;border-radius:999px}}.form-error{{min-height:22px;margin:10px 0 0;color:#9a3d33;font-size:.78rem}}
.context-note,.caveat{{margin:20px 0;padding:16px 18px;border-left:4px solid var(--accent);border-radius:12px;background:var(--accent-soft);font-size:.82rem}}.caveat{{border-color:var(--warm);background:var(--warm-soft)}}.subject-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px}}.subject{{position:relative;min-height:295px;padding:22px;border:1px solid var(--line);border-radius:17px;background:var(--card)}}.subject-badge{{display:grid;width:32px;height:32px;place-items:center;border-radius:9px;background:var(--navy);color:#fff;font-weight:900}}.subject h3{{margin:20px 0 5px;font-size:1.35rem;letter-spacing:-.03em}}.subject .location{{color:var(--muted);font-size:.78rem}}.subject-metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin:20px 0;background:var(--line);border:1px solid var(--line);border-radius:11px;overflow:hidden}}.subject-metrics div{{padding:12px;background:#f9faf7}}.subject-metrics span{{display:block;color:var(--muted);font-size:.65rem}}.subject-metrics b{{display:block;margin-top:3px;font-size:.93rem}}.subject-links{{display:flex;gap:12px;flex-wrap:wrap;font-size:.72rem;font-weight:800;color:var(--accent)}}
.factor-group{{margin-top:18px;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#fff}}.factor-group header{{padding:17px 18px;background:#eef2ee}}.factor-group h3{{margin:0;font-size:1rem}}.factor-group header p{{margin:4px 0 0;color:var(--muted);font-size:.72rem}}.factor-head,.factor-row{{display:grid;grid-template-columns:minmax(150px,.8fr) minmax(190px,1fr) minmax(190px,1fr) minmax(160px,.8fr)}}.factor-head{{background:var(--navy);color:#fff;font-size:.67rem;font-weight:850;text-transform:uppercase;letter-spacing:.06em}}.factor-head>div,.factor-row>div{{padding:12px 15px}}.factor-row{{border-top:1px solid var(--line);align-items:start}}.factor-row:hover{{background:#fbfcfa}}.factor-label{{font-size:.78rem;font-weight:850}}.factor-value{{font-size:.82rem}}.factor-value small,.factor-diff small{{display:block;margin-top:3px;color:var(--muted);font-size:.68rem}}.factor-diff{{color:var(--muted);font-size:.74rem}}.band{{display:inline-block;padding:2px 7px;border-radius:5px;background:#e8ece9;font-weight:900}}.band-A{{background:#d9efe4;color:#176045}}.band-Bp{{background:#dceaf3;color:#235a78}}.band-C,.band-D,.band-F{{background:#f5e5df;color:#8b4834}}.gap-positive{{color:#187157;font-weight:850}}.gap-negative{{color:#a3443a;font-weight:850}}
.empty{{padding:24px;border:1px dashed #aebdb5;border-radius:12px;color:var(--muted);text-align:center}}.legend{{display:flex;gap:9px 18px;flex-wrap:wrap;margin-top:18px;color:var(--muted);font-size:.68rem}}.legend b{{color:var(--ink)}}[hidden]{{display:none!important}}:focus-visible{{outline:3px solid #f2a900;outline-offset:2px}}
@media(max-width:820px){{.input-grid{{grid-template-columns:1fr}}.swap{{justify-self:start;margin:0}}.subject-grid{{grid-template-columns:1fr}}.factor-head{{display:none}}.factor-row{{grid-template-columns:1fr 1fr}}.factor-label{{grid-column:1/-1;padding-bottom:3px!important;background:#f3f5f2}}.factor-diff{{grid-column:1/-1;padding-top:4px!important}}}}
@media(max-width:540px){{body{{padding:10px}}main{{padding-top:16px}}h1{{font-size:3rem}}.compare-inner{{padding:15px}}.subject-metrics{{grid-template-columns:1fr}}.factor-row{{grid-template-columns:1fr}}.factor-value,.factor-diff{{grid-column:1}}}}
@media print{{.research-shell-nav,.compare-panel .actions,.subject-links{{display:none!important}}body{{padding:0;background:#fff}}main{{max-width:none}}.factor-group{{break-inside:avoid}}}}
</style></head><body>
<main id="research-content">
<header class="hero"><div class="eyebrow">Project evidence × estate framework · updated {as_of:%d %b %Y}</div>
<h1>Compare two condominiums in the same framework.</h1>
<p class="lede">Select any two named private projects. The page compares achieved project evidence first, then applies the same estate-context factor families as the main comparison table—without manufacturing a single winner.</p>
<div class="proof"><span>{len(projects):,} named project records</span><span>Transaction data through {html.escape(latest_month or '—')}</span><span>Provision and Liveability remain separate</span></div></header>

<section class="compare-panel" aria-labelledby="compare-title"><div class="compare-inner">
<div class="eyebrow" id="compare-title">Choose two projects</div>
<form id="compare-form"><div class="input-grid">
  <label>Project A<input id="project-a" list="project-options" autocomplete="off" placeholder="Type a condominium name"></label>
  <button class="swap" id="swap-projects" type="button" aria-label="Swap projects">⇄ Swap</button>
  <label>Project B<input id="project-b" list="project-options" autocomplete="off" placeholder="Type another condominium name"></label>
</div><datalist id="project-options">{options}</datalist>
<div class="actions"><button class="primary" type="submit">Compare projects</button><button id="copy-view" type="button">Copy comparison link</button><button id="print-view" type="button">Print / save PDF</button></div>
<p class="form-error" id="form-error" role="alert" aria-live="polite"></p></form>
</div></section>

<section id="comparison-result" hidden>
<div class="context-note" id="context-note"></div>
<div class="subject-grid" id="subject-grid"></div>
<h2>Factor-by-factor comparison</h2>
<p>Difference values are descriptive A-minus-B calculations, not points in a combined score. Blank framework fields remain unavailable rather than being imputed.</p>
<div id="factor-groups"></div>
<div class="legend"><span><b>YF</b> young family</span><span><b>SP</b> single professional</span><span><b>Ret</b> retiree</span><span><b>LS</b> lifestyle</span><span><b>T0</b> now</span><span><b>T5</b> 2031</span><span><b>T15</b> 2041</span><span><b>Noise</b> 1–5, higher is quieter</span></div>
<div class="caveat"><b>Read before deciding.</b> Project price summaries cover each project's available transaction history and can differ in period, sale state, unit mix and sample depth. “Recent vs all” is mix-sensitive, not an appreciation rate. Estate framework values describe the planning-area context or disclosed proxy, not the condominium, block, stack or unit. HDB Value and HDB remaining-lease risk are not applied to private projects.</div>
</section>
</main><script src="assets/research-shell.js" data-research-shell></script>
<script>
(() => {{
  const CONTEXTS = {context_json};
  const PROJECTS = {project_json}.map(project => ({{...project, ...(CONTEXTS[project.context_key] || {{}})}}));
  const DEFAULTS = {default_json};
  const byId = new Map(PROJECTS.map(project => [project.id, project]));
  const byLabel = new Map(PROJECTS.map(project => [project.selection_label.toUpperCase(), project]));
  const nameCounts = PROJECTS.reduce((counts, project) => counts.set(project.project.toUpperCase(), (counts.get(project.project.toUpperCase()) || 0) + 1), new Map());
  const byUniqueName = new Map(PROJECTS.filter(project => nameCounts.get(project.project.toUpperCase()) === 1).map(project => [project.project.toUpperCase(), project]));
  const inputA = document.getElementById("project-a");
  const inputB = document.getElementById("project-b");
  const error = document.getElementById("form-error");
  let selected = null;

  const esc = value => String(value ?? "—").replace(/[&<>"']/g, character => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}}[character]));
  const available = value => value !== null && value !== undefined && value !== "" && value !== "not_covered";
  const money = value => available(value) ? new Intl.NumberFormat("en-SG", {{style:"currency",currency:"SGD",maximumFractionDigits:0}}).format(value) : "—";
  const number = (value, suffix="") => available(value) ? `${{new Intl.NumberFormat("en-SG", {{maximumFractionDigits:1}}).format(value)}}${{suffix}}` : "—";
  const percent = value => available(value) ? `${{value >= 0 ? "+" : ""}}${{Number(value).toFixed(1)}}%` : "—";
  const signed = (value, digits=2) => available(value) ? `${{value > 0 ? "+" : ""}}${{Number(value).toFixed(digits)}}` : "—";
  const title = value => available(value) ? String(value).toLowerCase().replace(/(^|[\\s/(-])\\S/g, match => match.toUpperCase()).replace(/Mrt/g, "MRT") : "—";
  const band = value => ({{main:available(value) ? value : "—", kind:"band"}});
  const gap = value => ({{main:signed(value), kind:available(value) ? (value > 0 ? "gap-positive" : value < 0 ? "gap-negative" : "") : ""}});
  const mainSub = (main, sub, kind="") => ({{main:available(main) ? main : "—", sub:available(sub) ? sub : "", kind}});
  const delta = (a, b, formatter=number) => available(a) && available(b) ? `A − B: ${{formatter(a - b)}}` : "Difference unavailable";
  const resolve = value => {{
    const key = String(value || "").trim();
    if (!key) return null;
    return byId.get(key) || byLabel.get(key.toUpperCase()) || byUniqueName.get(key.toUpperCase()) || null;
  }};

  function renderValue(value) {{
    const prepared = typeof value === "object" && value !== null ? value : {{main:value}};
    const main = available(prepared.main) ? prepared.main : "—";
    const className = prepared.kind === "band"
      ? `band band-${{String(main).replace("+", "p")}}`
      : prepared.kind || "";
    return `<div class="${{className}}">${{esc(main)}}</div>${{prepared.sub ? `<small>${{esc(prepared.sub)}}</small>` : ""}}`;
  }}

  function subjectCard(project, side) {{
    const explorer = `private_project_comparison_table.html?q=${{encodeURIComponent(project.project)}}`;
    return `<article class="subject"><span class="subject-badge">${{side}}</span>
      <h3>${{esc(title(project.project))}}</h3>
      <div class="location">D${{esc(project.district)}} · ${{esc(title(project.planning_area))}} · ${{esc(title(project.street))}}</div>
      <div class="subject-metrics">
        <div><span>Median achieved price</span><b>${{money(project.median_price)}}</b></div>
        <div><span>Median achieved PSF</span><b>${{number(project.median_psf, " psf")}}</b></div>
        <div><span>Transaction sample</span><b>n=${{number(project.transactions_n)}}</b></div>
      </div>
      <p><b>${{esc(project.tenure || "Tenure unavailable")}}</b><br>
      ${{esc(project.station_display || "MRT unavailable")}} · ${{number(project.station_distance_m, "m straight-line")}}<br>
      Estate context: ${{esc(title(project.context_estate))}}${{project.context_basis?.startsWith("proxy") ? " (proxy)" : ""}}</p>
      <div class="subject-links"><a href="${{explorer}}">Open project transactions →</a><a href="comparison_table.html">Open all estates →</a></div>
    </article>`;
  }}

  function factorRow(label, valueA, valueB, difference) {{
    return `<div class="factor-row"><div class="factor-label">${{esc(label)}}</div>
      <div class="factor-value">${{renderValue(valueA)}}</div>
      <div class="factor-value">${{renderValue(valueB)}}</div>
      <div class="factor-diff">${{esc(difference || "—")}}</div></div>`;
  }}

  function buildGroups(a, b) {{
    const sameContext = a.context_estate === b.context_estate;
    const trajectory = project => [project.ls_t0_band, project.ls_t5_band, project.ls_t15_band].map(value => value || "—").join(" → ");
    const trajectoryArrow = project => {{
      const order = {{"F":0,"D":1,"C":2,"B":3,"B+":4,"A":5}};
      const start = order[project.ls_t0_band], end = order[project.ls_t15_band];
      return start === undefined || end === undefined ? "—" : end > start ? "↑" : end < start ? "↓" : "→";
    }};
    const pathValue = (project, prefix) => mainSub(title(project[`${{prefix}}_path`]?.replaceAll("_", " ")), `${{project[`${{prefix}}_path_shift`] || "—"}} · Δ ${{signed(project[`${{prefix}}_path_delta`])}}`);
    const groups = [
      {{title:"Project market evidence", note:"Project-specific achieved transactions; periods and sale mix can differ.", rows:[
        ["Median achieved price", money(a.median_price), money(b.median_price), delta(a.median_price,b.median_price,money)],
        ["Median achieved PSF", number(a.median_psf," psf"), number(b.median_psf," psf"), delta(a.median_psf,b.median_psf,value => number(value," psf"))],
        ["Median transacted area", mainSub(number(a.median_area_sqft," sqft"),number(a.median_area_sqm," sqm")),mainSub(number(b.median_area_sqft," sqft"),number(b.median_area_sqm," sqm")),delta(a.median_area_sqft,b.median_area_sqft,value => number(value," sqft"))],
        ["Transaction sample", mainSub(`n=${{a.transactions_n}}`,`${{a.first_sale || "—"}}–${{a.last_sale || "—"}}`),mainSub(`n=${{b.transactions_n}}`,`${{b.first_sale || "—"}}–${{b.last_sale || "—"}}`),delta(a.transactions_n,b.transactions_n,value => number(value," records"))],
        ["Sale-state mix", a.sale_mix, b.sale_mix, "Compare like sale states in the project explorer"],
        ["Recent vs all-history median", percent(a.recent_delta_pct), percent(b.recent_delta_pct), "Mix-sensitive; not appreciation"],
        ["Project tenure", a.tenure, b.tenure, "Direct project fact; no combined tenure score"],
      ]}},
      {{title:"Access and education evidence", note:"Project-coordinate diagnostics; straight-line distances are not routes or eligibility decisions.", rows:[
        ["Nearest MRT", mainSub(a.station_display,number(a.station_distance_m,"m straight-line")),mainSub(b.station_display,number(b.station_distance_m,"m straight-line")),delta(a.station_distance_m,b.station_distance_m,value => number(value,"m"))],
        ["Primary schools within 1km", mainSub(number(a.primary_1km_count),a.primary_1km_schools),mainSub(number(b.primary_1km_count),b.primary_1km_schools),delta(a.primary_1km_count,b.primary_1km_count,value => number(value," schools"))],
        ["Best recorded primary proximity", mainSub(title(a.best_primary_1km_school),number(a.best_primary_1km_distance_m,"m")),mainSub(title(b.best_primary_1km_school),number(b.best_primary_1km_distance_m,"m")),"Diagnostic only; verify with MOE OneMap"],
        ["Location evidence", title(a.location_source?.replaceAll("_"," ")),title(b.location_source?.replaceAll("_"," ")),"Centroid proxies are less precise"],
      ]}},
      {{title:"Identity and Provision context", note:"Same fields as comparison_table.html, applied to the estate context—not the project.", rows:[
        ["Estate context", mainSub(title(a.context_estate),a.context_basis),mainSub(title(b.context_estate),b.context_basis),sameContext ? "Same estate context" : "Different estate contexts"],
        ["Archetype", a.archetype, b.archetype, "Estate archetype; not project type"],
        ["D disruption multiplier (T0)", number(a.d_t0),number(b.d_t0),delta(a.d_t0,b.d_t0,value => signed(value,2))],
        ["Provision band",band(a.provision_band),band(b.provision_band),"Objective estate supply view"],
        ["Provision score",number(a.provision_score),number(b.provision_score),delta(a.provision_score,b.provision_score,value => signed(value,2))],
      ]}},
      {{title:"Liveability (T0) and lifestyle trajectory", note:"Persona-relative estate context; do not read these as one universal rank.", rows:[
        ["Young family (YF)",band(a.yf_t0_band),band(b.yf_t0_band),"Persona-relative bands"],
        ["Single professional (SP)",band(a.sp_t0_band),band(b.sp_t0_band),"Persona-relative bands"],
        ["Retiree (Ret)",band(a.ret_t0_band),band(b.ret_t0_band),"Persona-relative bands"],
        ["Lifestyle (LS)",band(a.ls_t0_band),band(b.ls_t0_band),"Persona-relative bands"],
        ["LS T0 → T5 → T15",trajectory(a),trajectory(b),"Estate horizon sequence"],
        ["LS trajectory arrow",trajectoryArrow(a),trajectoryArrow(b),"Direction only; not return forecast"],
      ]}},
      {{title:"Gap (Liveability − Provision)", note:"Positive means that persona rates the estate above its objective supply checklist score.", rows:[
        ["YF gap",gap(a.gap_yf_t0),gap(b.gap_yf_t0),delta(a.gap_yf_t0,b.gap_yf_t0,value => signed(value,2))],
        ["SP gap",gap(a.gap_sp_t0),gap(b.gap_sp_t0),delta(a.gap_sp_t0,b.gap_sp_t0,value => signed(value,2))],
        ["Ret gap",gap(a.gap_ret_t0),gap(b.gap_ret_t0),delta(a.gap_ret_t0,b.gap_ret_t0,value => signed(value,2))],
        ["LS gap",gap(a.gap_ls_t0),gap(b.gap_ls_t0),delta(a.gap_ls_t0,b.gap_ls_t0,value => signed(value,2))],
      ]}},
      {{title:"Value context", note:"Private and HDB remain separate universes. Only private-segment context applies here.", rows:[
        ["HDB Value band / multiplier","Not applicable","Not applicable","Excluded from condo comparison"],
        ["Private Value band",band(a.private_value_band),band(b.private_value_band),"Estate private-resale segment"],
        ["Private Value multiplier",number(a.private_value_multiplier),number(b.private_value_multiplier),delta(a.private_value_multiplier,b.private_value_multiplier,value => signed(value,2))],
        ["Private Value sample",mainSub(number(a.private_value_n),"estate segment"),mainSub(number(b.private_value_n),"estate segment"),delta(a.private_value_n,b.private_value_n,value => number(value," records"))],
      ]}},
      {{title:"Employment, Risk and Life Path context", note:"Employment and paths are estate-horizon views. Project tenure replaces the HDB-only lease-risk field.", rows:[
        ["Employment T0",mainSub(band(a.employment_t0_band).main,number(a.employment_t0_score)),mainSub(band(b.employment_t0_band).main,number(b.employment_t0_score)),"Current estate access"],
        ["Employment T5",mainSub(band(a.employment_t5_band).main,number(a.employment_t5_score)),mainSub(band(b.employment_t5_band).main,number(b.employment_t5_score)),"2031 context"],
        ["Employment T15",mainSub(band(a.employment_t15_band).main,number(a.employment_t15_score)),mainSub(band(b.employment_t15_band).main,number(b.employment_t15_score)),"2041 context"],
        ["Lease risk",mainSub(a.tenure,"HDB lease band not applied"),mainSub(b.tenure,"HDB lease band not applied"),"Read project tenure directly"],
        ["Noise distance score",number(a.noise),number(b.noise),delta(a.noise,b.noise,value => signed(value,1))],
        ["Best life path",pathValue(a,"best"),pathValue(b,"best"),"Largest modeled estate change"],
        ["Worst life path",pathValue(a,"worst"),pathValue(b,"worst"),"Smallest change or largest decline"],
        ["Interpretation flags",(a.flags || []).join(" · ") || "None",(b.flags || []).join(" · ") || "None","Context warnings, not project labels"],
      ]}},
    ];
    return groups.map(group => `<section class="factor-group"><header><h3>${{esc(group.title)}}</h3><p>${{esc(group.note)}}</p></header>
      <div class="factor-head"><div>Factor</div><div>A · ${{esc(title(a.project))}}</div><div>B · ${{esc(title(b.project))}}</div><div>Descriptive difference</div></div>
      ${{group.rows.map(row => factorRow(...row)).join("")}}</section>`).join("");
  }}

  function compare(pushState=true) {{
    const a = resolve(inputA.value), b = resolve(inputB.value);
    if (!a || !b) {{
      error.textContent = "Choose two recognised project names from the suggestions.";
      document.getElementById("comparison-result").hidden = true;
      return;
    }}
    if (a.id === b.id) {{
      error.textContent = "Choose two different condominium project records.";
      document.getElementById("comparison-result").hidden = true;
      return;
    }}
    error.textContent = "";
    inputA.value = a.selection_label; inputB.value = b.selection_label;
    selected = [a,b];
    const sameContext = a.context_estate === b.context_estate;
    document.getElementById("context-note").innerHTML = sameContext
      ? `<b>Shared estate context:</b> Both projects map to ${{esc(title(a.context_estate))}}, so framework rows can match even when project transactions, tenure and access differ.`
      : `<b>Different estate contexts:</b> ${{esc(title(a.project))}} maps to ${{esc(title(a.context_estate))}} and ${{esc(title(b.project))}} maps to ${{esc(title(b.context_estate))}}. These are context comparisons, not project scores.`;
    document.getElementById("subject-grid").innerHTML = subjectCard(a,"A") + subjectCard(b,"B");
    document.getElementById("factor-groups").innerHTML = buildGroups(a,b);
    document.getElementById("comparison-result").hidden = false;
    if (pushState) {{
      const params = new URLSearchParams({{a:a.id,b:b.id}});
      history.replaceState({{}}, "", `${{location.pathname}}?${{params}}#comparison-result`);
    }}
  }}

  document.getElementById("compare-form").addEventListener("submit", event => {{event.preventDefault();compare();}});
  document.getElementById("swap-projects").addEventListener("click", () => {{
    const value = inputA.value; inputA.value = inputB.value; inputB.value = value; compare();
  }});
  document.getElementById("copy-view").addEventListener("click", async event => {{
    if (!selected) compare();
    if (!selected) return;
    const params = new URLSearchParams({{a:selected[0].id,b:selected[1].id}});
    const url = `${{location.origin}}${{location.pathname}}?${{params}}#comparison-result`;
    history.replaceState({{}}, "", url);
    try {{await navigator.clipboard.writeText(url);event.currentTarget.textContent="Link copied";}}
    catch (_) {{window.prompt("Copy this comparison link",url);}}
  }});
  document.getElementById("print-view").addEventListener("click", () => window.print());

  const params = new URLSearchParams(location.search);
  const initialA = byId.get(params.get("a")) || byId.get(DEFAULTS[0]);
  const initialB = byId.get(params.get("b")) || byId.get(DEFAULTS[1]);
  inputA.value = initialA.selection_label; inputB.value = initialB.selection_label;
  compare(false);
}})();
</script></body></html>"""


def load_projects_for_comparison(
    private_path: pathlib.Path = DEFAULT_PRIVATE,
    estates_path: pathlib.Path = DEFAULT_ESTATES,
    mrt_path: pathlib.Path = DEFAULT_MRT,
    locations_path: pathlib.Path = DEFAULT_LOCATIONS,
    schools_path: pathlib.Path = DEFAULT_SCHOOLS,
    master_path: pathlib.Path = DEFAULT_MASTER,
    provision_path: pathlib.Path = DEFAULT_PROVISION,
    employment_t0_path: pathlib.Path = DEFAULT_EMPLOYMENT_T0,
    employment_t5_path: pathlib.Path = DEFAULT_EMPLOYMENT_T5,
    employment_t15_path: pathlib.Path = DEFAULT_EMPLOYMENT_T15,
    life_paths_path: pathlib.Path = DEFAULT_LIFE_PATHS,
) -> tuple[list[dict[str, Any]], str | None]:
    """Load and enrich the reusable private-project comparison catalog."""
    private = private_projects.load_private(private_path)
    aggregate_rows = private_projects.aggregate_projects(
        private,
        pd.read_csv(estates_path),
        pd.read_csv(mrt_path),
        pd.read_csv(master_path).set_index("estate"),
        private_projects.load_project_locations(locations_path),
        private_projects.load_school_metrics(schools_path),
    )
    contexts = build_framework_contexts(
        pd.read_csv(master_path),
        pd.read_csv(provision_path),
        pd.read_csv(employment_t0_path),
        pd.read_csv(employment_t5_path),
        pd.read_csv(employment_t15_path),
        pd.read_csv(life_paths_path),
    )
    projects = prepare_projects(aggregate_rows, contexts)
    latest_month = private_projects.month_text(private["sale_month_dt"].max())
    return projects, latest_month


def generate(
    private_path: pathlib.Path = DEFAULT_PRIVATE,
    estates_path: pathlib.Path = DEFAULT_ESTATES,
    mrt_path: pathlib.Path = DEFAULT_MRT,
    locations_path: pathlib.Path = DEFAULT_LOCATIONS,
    schools_path: pathlib.Path = DEFAULT_SCHOOLS,
    master_path: pathlib.Path = DEFAULT_MASTER,
    provision_path: pathlib.Path = DEFAULT_PROVISION,
    employment_t0_path: pathlib.Path = DEFAULT_EMPLOYMENT_T0,
    employment_t5_path: pathlib.Path = DEFAULT_EMPLOYMENT_T5,
    employment_t15_path: pathlib.Path = DEFAULT_EMPLOYMENT_T15,
    life_paths_path: pathlib.Path = DEFAULT_LIFE_PATHS,
    out_path: pathlib.Path = DEFAULT_OUT,
    as_of: date | None = None,
) -> tuple[pathlib.Path, int]:
    projects, latest_month = load_projects_for_comparison(
        private_path,
        estates_path,
        mrt_path,
        locations_path,
        schools_path,
        master_path,
        provision_path,
        employment_t0_path,
        employment_t5_path,
        employment_t15_path,
        life_paths_path,
    )
    out_path.write_text(
        render_html(projects, latest_month, as_of or date.today()), encoding="utf-8"
    )
    return out_path, len(projects)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the two-condominium framework comparison"
    )
    parser.add_argument("--private", default=str(DEFAULT_PRIVATE))
    parser.add_argument("--estates", default=str(DEFAULT_ESTATES))
    parser.add_argument("--mrt", default=str(DEFAULT_MRT))
    parser.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    parser.add_argument("--schools", default=str(DEFAULT_SCHOOLS))
    parser.add_argument("--master", default=str(DEFAULT_MASTER))
    parser.add_argument("--provision", default=str(DEFAULT_PROVISION))
    parser.add_argument("--employment-t0", default=str(DEFAULT_EMPLOYMENT_T0))
    parser.add_argument("--employment-t5", default=str(DEFAULT_EMPLOYMENT_T5))
    parser.add_argument("--employment-t15", default=str(DEFAULT_EMPLOYMENT_T15))
    parser.add_argument("--life-paths", default=str(DEFAULT_LIFE_PATHS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path, count = generate(
        pathlib.Path(args.private),
        pathlib.Path(args.estates),
        pathlib.Path(args.mrt),
        pathlib.Path(args.locations),
        pathlib.Path(args.schools),
        pathlib.Path(args.master),
        pathlib.Path(args.provision),
        pathlib.Path(args.employment_t0),
        pathlib.Path(args.employment_t5),
        pathlib.Path(args.employment_t15),
        pathlib.Path(args.life_paths),
        pathlib.Path(args.out),
    )
    print(
        f"Written: {out_path} ({out_path.stat().st_size // 1024:,} KB, "
        f"{count:,} named project records)"
    )


if __name__ == "__main__":
    main()
