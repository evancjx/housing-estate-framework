#!/usr/bin/env python3
"""
Generate an interactive framework comparison for two to five condominiums.

The first selected project is the neutral reference. Other columns may show
descriptive numeric differences versus that reference, but the page does not
calculate an overall score or winner.

Project evidence (transactions, tenure, MRT and schools) remains separate from
estate context (Provision, persona-relative Liveability, private Value,
Employment, Risk and Life Path). HDB Value and HDB lease-risk fields are not
applied to private condominium projects.

The data contract is shared with ``gen_condo_framework_comparison_html.py``.

Writes:
  multi_condo_framework_comparison.html
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
from datetime import date
from typing import Any

import gen_condo_framework_comparison_html as two_project


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_OUT = ROOT / "multi_condo_framework_comparison.html"
MIN_PROJECTS = 2
MAX_PROJECTS = 5


def default_ids(projects: list[dict[str, Any]]) -> list[str]:
    """Return a useful three-project example, falling back deterministically."""
    by_name = {project["project"].upper(): project["id"] for project in projects}
    preferred_sets = (
        (
            "THE POIZ RESIDENCES",
            "PARK PLACE RESIDENCES AT PLQ",
            "TREASURE AT TAMPINES",
        ),
        ("EMERALD OF KATONG", "THE CONTINUUM", "ONE AMBER"),
    )
    for names in preferred_sets:
        if all(name in by_name for name in names):
            return [by_name[name] for name in names]
    if len(projects) < MIN_PROJECTS:
        raise SystemExit("at least two named condominium projects are required")
    return [project["id"] for project in projects[: min(3, len(projects))]]


def options_html(projects: list[dict[str, Any]]) -> str:
    return "".join(
        f'<option value="{html.escape(project["selection_label"], quote=True)}">'
        f'D{html.escape(project["district"] or "—")} · '
        f'{html.escape(project["planning_area"] or "Unknown area")} · '
        f'{html.escape(project["street"] or "Unknown street")}</option>'
        for project in projects
    )


def render_html(
    projects: list[dict[str, Any]],
    latest_month: str | None,
    as_of: date,
) -> str:
    defaults = default_ids(projects)
    browser_projects, browser_contexts = two_project.build_browser_payload(projects)
    project_json = json.dumps(
        browser_projects, ensure_ascii=False, separators=(",", ":")
    )
    context_json = json.dumps(
        browser_contexts, ensure_ascii=False, separators=(",", ":")
    )
    default_json = json.dumps(defaults, separators=(",", ":"))
    options = options_html(projects)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Multi-condominium framework comparison</title>
<meta name="description" content="Compare two to five Singapore condominium projects using achieved project evidence and the estate Provision, Liveability, private Value, Employment, Risk and Life Path framework.">
<link rel="stylesheet" href="assets/research-shell.css" data-research-shell>
<style>
:root{{--ink:#18231f;--muted:#64716b;--paper:#f4f6f2;--card:#fff;--line:#d8e0da;--accent:#08786d;--accent-soft:#e1f2ed;--warm:#b25a35;--warm-soft:#fff0e7;--navy:#17324d;--shadow:0 20px 55px rgba(21,44,35,.09);--badge-a:#17324d;--badge-b:#08786d;--badge-c:#a45e2d;--badge-d:#67528b;--badge-e:#6a6656}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;padding:20px;background:var(--paper);color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}}main{{max-width:1280px;margin:auto;padding:30px 0 72px}}a{{color:inherit}}h1,h2{{font-family:Georgia,"Times New Roman",serif;letter-spacing:-.04em}}h1{{max-width:1020px;margin:.2em 0;font-size:clamp(2.8rem,7vw,5.8rem);font-weight:500;line-height:.96}}h2{{margin:60px 0 8px;font-size:clamp(1.8rem,4vw,3rem)}}p{{max-width:84ch}}
.eyebrow{{color:var(--accent);font-size:.7rem;font-weight:900;letter-spacing:.15em;text-transform:uppercase}}.lede{{color:var(--muted);font-size:1.08rem}}.hero{{padding:34px 0 38px;border-bottom:1px solid var(--line)}}.proof{{display:flex;gap:10px 26px;flex-wrap:wrap;margin-top:24px;color:var(--muted);font-size:.76rem;font-weight:700}}.proof span::before{{content:"";display:inline-block;width:6px;height:6px;margin:0 8px 1px 0;border-radius:50%;background:var(--accent)}}
.set-panel{{margin:30px 0;padding:8px;border:1px solid var(--line);border-radius:22px;background:rgba(255,255,255,.58);box-shadow:var(--shadow)}}.set-inner{{padding:22px;border-radius:15px;background:#fff}}.set-head{{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:13px}}.set-count{{color:var(--muted);font-size:.75rem;font-weight:800}}.project-tray{{display:grid;gap:8px}}.project-row{{display:grid;grid-template-columns:104px minmax(250px,1fr) auto;gap:10px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:12px;background:#fafbf9}}.slot-label{{display:flex;align-items:center;gap:8px;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.06em}}.project-badge{{display:grid;width:32px;height:32px;place-items:center;border-radius:9px;background:var(--badge-a);color:#fff;font-size:.78rem;font-weight:900}}.project-row:nth-child(2) .project-badge,.badge-B{{background:var(--badge-b)}}.project-row:nth-child(3) .project-badge,.badge-C{{background:var(--badge-c)}}.project-row:nth-child(4) .project-badge,.badge-D{{background:var(--badge-d)}}.project-row:nth-child(5) .project-badge,.badge-E{{background:var(--badge-e)}}.badge-A{{background:var(--badge-a)}}
.slot-field label{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}input{{width:100%;min-height:47px;padding:10px 12px;border:1px solid #b9c9c1;border-radius:9px;background:#fff;color:var(--ink);font:inherit;outline:none}}input:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(8,120,109,.13)}}input.invalid{{border-color:#a83d34;box-shadow:0 0 0 2px rgba(168,61,52,.12)}}.row-actions{{display:flex;gap:5px}}button{{min-height:42px;padding:8px 12px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);font:inherit;font-size:.75rem;font-weight:850;cursor:pointer}}button.primary{{border-color:var(--accent);background:var(--accent);color:#fff}}button:hover:not(:disabled){{border-color:var(--accent)}}button:disabled{{cursor:not-allowed;opacity:.42}}.icon-button{{width:42px;padding:7px}}.set-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px}}.set-error{{min-height:22px;margin:10px 0 0;color:#9a3d33;font-size:.78rem}}.set-status{{min-height:20px;margin:3px 0 0;color:var(--muted);font-size:.72rem}}
.context-note,.caveat{{margin:20px 0;padding:16px 18px;border-left:4px solid var(--accent);border-radius:12px;background:var(--accent-soft);font-size:.82rem}}.caveat{{border-color:var(--warm);background:var(--warm-soft)}}.result-tools{{display:flex;align-items:end;justify-content:space-between;gap:14px;flex-wrap:wrap}}.result-tools h2{{margin-bottom:0}}.detail-actions{{display:flex;gap:7px;margin-bottom:4px}}
.subject-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:20px}}.subject{{min-height:285px;padding:19px;border:1px solid var(--line);border-radius:17px;background:var(--card)}}.subject h3{{margin:17px 0 5px;font-size:1.16rem;letter-spacing:-.03em}}.subject .location{{min-height:38px;color:var(--muted);font-size:.72rem}}.subject-metrics{{display:grid;grid-template-columns:1fr 1fr;gap:1px;margin:17px 0;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden}}.subject-metrics div{{padding:10px;background:#f9faf7}}.subject-metrics span{{display:block;color:var(--muted);font-size:.61rem}}.subject-metrics b{{display:block;margin-top:3px;font-size:.84rem}}.subject p{{font-size:.76rem}}.subject-links{{font-size:.69rem;font-weight:850;color:var(--accent)}}
.factor-group{{margin-top:15px;border:1px solid var(--line);border-radius:15px;overflow:hidden;background:#fff}}.factor-group summary{{display:flex;padding:16px 18px;align-items:start;justify-content:space-between;gap:16px;background:#eef2ee;cursor:pointer;list-style-position:inside}}.factor-group summary b{{font-size:.94rem}}.factor-group summary span{{max-width:720px;color:var(--muted);font-size:.7rem;text-align:right}}.matrix-wrap{{max-width:100%;overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px 14px;border-top:1px solid var(--line);text-align:left;vertical-align:top;font-size:.78rem}}thead th{{position:sticky;top:0;z-index:2;background:var(--navy);color:#fff;border-top:0;font-size:.67rem;text-transform:uppercase;letter-spacing:.05em}}th[scope=row]{{position:sticky;left:0;z-index:1;width:170px;background:#f8faf7;font-weight:850}}thead th:first-child{{left:0;z-index:3}}td small{{display:block;margin-top:3px;color:var(--muted);font-size:.65rem}}.reference-note{{color:var(--accent)}}.band{{display:inline-block;padding:2px 7px;border-radius:5px;background:#e8ece9;font-weight:900}}.band-A{{background:#d9efe4;color:#176045}}.band-Bp{{background:#dceaf3;color:#235a78}}.band-C,.band-D,.band-F{{background:#f5e5df;color:#8b4834}}.gap-positive{{color:#187157;font-weight:850}}.gap-negative{{color:#a3443a;font-weight:850}}
.legend{{display:flex;gap:9px 18px;flex-wrap:wrap;margin-top:18px;color:var(--muted);font-size:.68rem}}.legend b{{color:var(--ink)}}[hidden]{{display:none!important}}:focus-visible{{outline:3px solid #f2a900;outline-offset:2px}}
@media(max-width:760px){{.project-row{{grid-template-columns:1fr}}.slot-label{{justify-content:space-between}}.row-actions{{justify-content:flex-start}}.factor-group summary{{display:block}}.factor-group summary span{{display:block;margin:4px 0 0;text-align:left}}.subject-grid{{grid-template-columns:1fr}}}}
@media(max-width:540px){{body{{padding:10px}}main{{padding-top:16px}}h1{{font-size:3rem}}.set-inner{{padding:14px}}.set-head{{align-items:start;flex-direction:column}}.subject-metrics{{grid-template-columns:1fr}}.detail-actions{{width:100%}}}}
@media print{{.research-shell-nav,.set-panel,.detail-actions,.subject-links{{display:none!important}}body{{padding:0;background:#fff}}main{{max-width:none}}details{{display:block}}details>summary{{list-style:none}}.factor-group{{break-inside:avoid}}.matrix-wrap{{overflow:visible}}table{{min-width:100%;font-size:9px}}}}
</style></head><body>
<main id="research-content">
<header class="hero"><div class="eyebrow">2–5 projects · project evidence × estate framework · updated {as_of:%d %b %Y}</div>
<h1>Build a condominium comparison set.</h1>
<p class="lede">Choose two to five named private projects. Project A is the reference; every factor stays visible in its own column so trade-offs do not collapse into a misleading winner.</p>
<div class="proof"><span>{len(projects):,} named project records</span><span>Transaction data through {html.escape(latest_month or '—')}</span><span>Ordered share links preserve the reference</span></div></header>

<section class="set-panel" aria-labelledby="set-title"><div class="set-inner">
<div class="set-head"><div><div class="eyebrow" id="set-title">Comparison set</div><p class="set-status" id="set-status" role="status" aria-live="polite"></p></div><span class="set-count" id="set-count"></span></div>
<form id="set-form"><div class="project-tray" id="project-tray"></div>
<datalist id="project-options">{options}</datalist>
<div class="set-actions"><button id="add-project" type="button">+ Add project</button><button class="primary" type="submit">Compare projects</button><button id="copy-view" type="button">Copy comparison link</button><button id="print-view" type="button">Print / save PDF</button></div>
<p class="set-error" id="set-error" role="alert" aria-live="assertive"></p></form>
</div></section>

<section id="comparison-result" hidden>
<div class="context-note" id="context-note"></div>
<div class="subject-grid" id="subject-grid"></div>
<div class="result-tools"><div><h2 id="result-heading" tabindex="-1">Factor-by-factor matrix</h2><p>Neutral “vs A” values are descriptive differences, not points in an overall score.</p></div>
<div class="detail-actions"><button id="expand-all" type="button">Expand all</button><button id="collapse-all" type="button">Collapse all</button></div></div>
<div id="factor-groups"></div>
<div class="legend"><span><b>A</b> reference project</span><span><b>YF</b> young family</span><span><b>SP</b> single professional</span><span><b>Ret</b> retiree</span><span><b>LS</b> lifestyle</span><span><b>T0</b> now</span><span><b>T5</b> 2031</span><span><b>T15</b> 2041</span><span><b>Noise</b> 1–5, higher is quieter</span></div>
<div class="caveat"><b>Read before deciding.</b> Project summaries can differ in period, sale state, unit mix and sample depth. “Recent vs all” is mix-sensitive, not appreciation. Estate framework values describe the planning-area context or disclosed proxy, not the condominium, block, stack or unit. HDB Value and HDB remaining-lease risk are not applied to private projects.</div>
</section>
</main><script src="assets/research-shell.js" data-research-shell></script>
<script>
(() => {{
  const MIN_PROJECTS = {MIN_PROJECTS}, MAX_PROJECTS = {MAX_PROJECTS};
  const LETTERS = ["A","B","C","D","E"];
  const CONTEXTS = {context_json};
  const PROJECTS = {project_json}.map(project => ({{...project, ...(CONTEXTS[project.context_key] || {{}})}}));
  const DEFAULTS = {default_json};
  const byId = new Map(PROJECTS.map(project => [project.id, project]));
  const byLabel = new Map(PROJECTS.map(project => [project.selection_label.toUpperCase(), project]));
  const nameCounts = PROJECTS.reduce((counts, project) => counts.set(project.project.toUpperCase(), (counts.get(project.project.toUpperCase()) || 0) + 1), new Map());
  const byUniqueName = new Map(PROJECTS.filter(project => nameCounts.get(project.project.toUpperCase()) === 1).map(project => [project.project.toUpperCase(), project]));
  const tray = document.getElementById("project-tray");
  const error = document.getElementById("set-error");
  const status = document.getElementById("set-status");
  const addButton = document.getElementById("add-project");
  let slots = [], selected = [], slotSequence = 0;

  const esc = value => String(value ?? "—").replace(/[&<>"']/g, character => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}}[character]));
  const available = value => value !== null && value !== undefined && value !== "" && value !== "not_covered";
  const money = value => available(value) ? new Intl.NumberFormat("en-SG", {{style:"currency",currency:"SGD",maximumFractionDigits:0}}).format(value) : "—";
  const number = (value, suffix="") => available(value) ? `${{new Intl.NumberFormat("en-SG", {{maximumFractionDigits:1}}).format(value)}}${{suffix}}` : "—";
  const percent = value => available(value) ? `${{value >= 0 ? "+" : ""}}${{Number(value).toFixed(1)}}%` : "—";
  const signed = (value, digits=2) => available(value) ? `${{value > 0 ? "+" : ""}}${{Number(value).toFixed(digits)}}` : "—";
  const title = value => available(value) ? String(value).toLowerCase().replace(/(^|[\\s/(-])\\S/g, match => match.toUpperCase()).replace(/Mrt/g, "MRT") : "—";
  const band = value => ({{main:available(value) ? value : "—", kind:"band"}});
  const gap = value => ({{main:signed(value), kind:available(value) ? (value > 0 ? "gap-positive" : value < 0 ? "gap-negative" : "") : ""}});
  const mainSub = (main, sub, kind="", raw=null, diffFormatter=null) => ({{main:available(main) ? main : "—",sub:available(sub) ? sub : "",kind,raw,diffFormatter}});
  const resolve = value => {{
    const key = String(value || "").trim();
    return byId.get(key) || byLabel.get(key.toUpperCase()) || byUniqueName.get(key.toUpperCase()) || null;
  }};
  const announce = message => {{status.textContent = message;}};
  const slot = project => ({{key:++slotSequence,value:project ? project.selection_label : ""}});

  function syncSlotValues() {{
    tray.querySelectorAll("input").forEach(input => {{
      const current = slots.find(item => item.key === Number(input.dataset.key));
      if (current) current.value = input.value;
    }});
  }}

  function markDirty(message="Selection changed. Choose Compare projects to refresh the matrix.") {{
    selected = [];
    document.getElementById("comparison-result").hidden = true;
    announce(message);
  }}

  function renderTray(focusKey=null) {{
    tray.innerHTML = slots.map((item,index) => {{
      const letter = LETTERS[index], reference = index === 0 ? "Reference" : `Project ${{letter}}`;
      return `<div class="project-row" data-key="${{item.key}}">
        <div class="slot-label"><span class="project-badge">${{letter}}</span><span>${{reference}}</span></div>
        <div class="slot-field"><label for="project-slot-${{item.key}}">${{reference}} condominium</label>
          <input id="project-slot-${{item.key}}" data-key="${{item.key}}" list="project-options" autocomplete="off"
            value="${{esc(item.value)}}" placeholder="Type a condominium name"></div>
        <div class="row-actions">
          <button class="icon-button move-up" type="button" data-index="${{index}}" aria-label="Move ${{reference}} up" ${{index === 0 ? "disabled" : ""}}>↑</button>
          <button class="icon-button move-down" type="button" data-index="${{index}}" aria-label="Move ${{reference}} down" ${{index === slots.length - 1 ? "disabled" : ""}}>↓</button>
          <button class="icon-button remove" type="button" data-index="${{index}}" aria-label="Remove ${{reference}}" ${{slots.length <= MIN_PROJECTS ? "disabled" : ""}}>×</button>
        </div></div>`;
    }}).join("");
    document.getElementById("set-count").textContent = `${{slots.length}} / ${{MAX_PROJECTS}} projects`;
    addButton.disabled = slots.length >= MAX_PROJECTS;
    addButton.textContent = slots.length >= MAX_PROJECTS ? "Maximum 5 projects" : "+ Add project";
    tray.querySelectorAll("input").forEach(input => input.addEventListener("input", () => {{
      const current = slots.find(item => item.key === Number(input.dataset.key));
      if (current) current.value = input.value;
      input.classList.remove("invalid");
      markDirty();
    }}));
    tray.querySelectorAll(".move-up,.move-down").forEach(button => button.addEventListener("click", () => {{
      syncSlotValues();
      const index = Number(button.dataset.index);
      const target = button.classList.contains("move-up") ? index - 1 : index + 1;
      [slots[index],slots[target]] = [slots[target],slots[index]];
      const movedKey = slots[target].key;
      markDirty(`Project moved to position ${{target + 1}}. Project A remains the reference.`);
      renderTray(movedKey);
    }}));
    tray.querySelectorAll(".remove").forEach(button => button.addEventListener("click", () => {{
      if (slots.length <= MIN_PROJECTS) return;
      syncSlotValues();
      const index = Number(button.dataset.index);
      const removed = slots.splice(index,1)[0];
      const focus = slots[Math.min(index,slots.length - 1)]?.key;
      markDirty(`Project removed. ${{slots.length}} projects remain.`);
      renderTray(focus);
    }}));
    if (focusKey) document.getElementById(`project-slot-${{focusKey}}`)?.focus();
  }}

  function validateSlots() {{
    syncSlotValues();
    tray.querySelectorAll("input").forEach(input => input.classList.remove("invalid"));
    const resolved = slots.map(item => resolve(item.value));
    const invalid = resolved.map((project,index) => project ? -1 : index).filter(index => index >= 0);
    if (invalid.length) {{
      invalid.forEach(index => tray.querySelectorAll("input")[index].classList.add("invalid"));
      error.textContent = "Choose a recognised condominium name for every project row.";
      return null;
    }}
    const ids = resolved.map(project => project.id);
    if (new Set(ids).size !== ids.length) {{
      error.textContent = "Each project record can appear only once in the comparison set.";
      return null;
    }}
    if (resolved.length < MIN_PROJECTS || resolved.length > MAX_PROJECTS) {{
      error.textContent = "Choose between two and five projects.";
      return null;
    }}
    error.textContent = "";
    return resolved;
  }}

  function canonicalURL(projects) {{
    const params = new URLSearchParams();
    projects.forEach(project => params.append("p",project.id));
    return `${{location.origin}}${{location.pathname}}?${{params}}#comparison-result`;
  }}

  function renderValue(value, project, reference, index) {{
    const prepared = typeof value === "object" && value !== null ? value : {{main:value}};
    const main = available(prepared.main) ? prepared.main : "—";
    const className = prepared.kind === "band" ? `band band-${{String(main).replace("+","p")}}` : prepared.kind || "";
    let secondary = prepared.sub ? `<small>${{esc(prepared.sub)}}</small>` : "";
    if (index === 0) secondary += '<small class="reference-note">Reference</small>';
    else if (prepared.diffFormatter && available(prepared.raw)) {{
      const referenceValue = prepared.referenceRaw ? prepared.referenceRaw(reference) : null;
      if (available(referenceValue)) secondary += `<small>vs A: ${{esc(prepared.diffFormatter(prepared.raw - referenceValue))}}</small>`;
    }}
    return `<div class="${{className}}">${{esc(main)}}</div>${{secondary}}`;
  }}

  function subjectCard(project,index) {{
    const letter = LETTERS[index];
    return `<article class="subject"><span class="project-badge badge-${{letter}}">${{letter}}</span>
      <h3>${{esc(title(project.project))}}</h3>
      <div class="location">D${{esc(project.district)}} · ${{esc(title(project.planning_area))}} · ${{esc(title(project.street))}}</div>
      <div class="subject-metrics">
        <div><span>Median achieved price</span><b>${{money(project.median_price)}}</b></div>
        <div><span>Median achieved PSF</span><b>${{number(project.median_psf," psf")}}</b></div>
        <div><span>Transaction sample</span><b>n=${{number(project.transactions_n)}}</b></div>
        <div><span>Estate context</span><b>${{esc(title(project.context_estate))}}</b></div>
      </div>
      <p><b>${{esc(project.tenure || "Tenure unavailable")}}</b><br>${{esc(project.station_display || "MRT unavailable")}} · ${{number(project.station_distance_m,"m straight-line")}}</p>
      <a class="subject-links" href="private_project_comparison_table.html?q=${{encodeURIComponent(project.project)}}">Open project transactions →</a>
    </article>`;
  }}

  function comparisonValue(project, field, formatter, suffix="") {{
    const raw = project[field];
    return mainSub(formatter(raw,suffix), "", "", raw, value => formatter(value,suffix));
  }}

  function groupsFor(projects) {{
    const trajectory = project => [project.ls_t0_band,project.ls_t5_band,project.ls_t15_band].map(value => value || "—").join(" → ");
    const trajectoryArrow = project => {{
      const order = {{"F":0,"D":1,"C":2,"B":3,"B+":4,"A":5}}, start=order[project.ls_t0_band],end=order[project.ls_t15_band];
      return start === undefined || end === undefined ? "—" : end > start ? "↑" : end < start ? "↓" : "→";
    }};
    const pathValue = (project,prefix) => mainSub(title(project[`${{prefix}}_path`]?.replaceAll("_"," ")),`${{project[`${{prefix}}_path_shift`] || "—"}} · Δ ${{signed(project[`${{prefix}}_path_delta`])}}`);
    return [
      {{title:"Project market evidence",note:"Project-specific achieved transactions; periods and sale mix can differ.",open:true,rows:[
        {{label:"Median achieved price",value:p=>comparisonValue(p,"median_price",money),referenceRaw:p=>p.median_price}},
        {{label:"Median achieved PSF",value:p=>comparisonValue(p,"median_psf",number," psf"),referenceRaw:p=>p.median_psf}},
        {{label:"Median transacted area",value:p=>mainSub(number(p.median_area_sqft," sqft"),number(p.median_area_sqm," sqm"),"",p.median_area_sqft,value=>number(value," sqft")),referenceRaw:p=>p.median_area_sqft}},
        {{label:"Transaction sample",value:p=>mainSub(`n=${{p.transactions_n}}`,`${{p.first_sale || "—"}}–${{p.last_sale || "—"}}`,"",p.transactions_n,value=>number(value," records")),referenceRaw:p=>p.transactions_n}},
        {{label:"Sale-state mix",value:p=>p.sale_mix}},
        {{label:"Recent vs all-history median",value:p=>mainSub(percent(p.recent_delta_pct),"Mix-sensitive; not appreciation")}},
        {{label:"Project tenure",value:p=>p.tenure}},
      ]}},
      {{title:"Access and education evidence",note:"Project-coordinate diagnostics; straight-line distances are not routes or eligibility decisions.",open:true,rows:[
        {{label:"Nearest MRT",value:p=>mainSub(p.station_display,number(p.station_distance_m,"m straight-line"),"",p.station_distance_m,value=>number(value,"m")),referenceRaw:p=>p.station_distance_m}},
        {{label:"Primary schools within 1km",value:p=>mainSub(number(p.primary_1km_count),p.primary_1km_schools,"",p.primary_1km_count,value=>number(value," schools")),referenceRaw:p=>p.primary_1km_count}},
        {{label:"Best recorded primary proximity",value:p=>mainSub(title(p.best_primary_1km_school),number(p.best_primary_1km_distance_m,"m"))}},
        {{label:"Location evidence",value:p=>title(p.location_source?.replaceAll("_"," "))}},
      ]}},
      {{title:"Identity and Provision context",note:"Estate-context fields from comparison_table.html; they are not condominium scores.",rows:[
        {{label:"Estate context",value:p=>mainSub(title(p.context_estate),p.context_basis)}},
        {{label:"Archetype",value:p=>p.archetype}},
        {{label:"D disruption multiplier (T0)",value:p=>mainSub(number(p.d_t0),"","",p.d_t0,value=>signed(value,2)),referenceRaw:p=>p.d_t0}},
        {{label:"Provision band",value:p=>band(p.provision_band)}},
        {{label:"Provision score",value:p=>mainSub(number(p.provision_score),"","",p.provision_score,value=>signed(value,2)),referenceRaw:p=>p.provision_score}},
      ]}},
      {{title:"Liveability (T0) and lifestyle trajectory",note:"Persona-relative estate context; never one universal ranking.",rows:[
        {{label:"Young family (YF)",value:p=>band(p.yf_t0_band)}},
        {{label:"Single professional (SP)",value:p=>band(p.sp_t0_band)}},
        {{label:"Retiree (Ret)",value:p=>band(p.ret_t0_band)}},
        {{label:"Lifestyle (LS)",value:p=>band(p.ls_t0_band)}},
        {{label:"LS T0 → T5 → T15",value:p=>trajectory(p)}},
        {{label:"LS trajectory arrow",value:p=>mainSub(trajectoryArrow(p),"Direction; not return forecast")}},
      ]}},
      {{title:"Gap (Liveability − Provision)",note:"Positive means the persona rates the estate above its objective supply checklist.",rows:[
        {{label:"YF gap",value:p=>mainSub(gap(p.gap_yf_t0).main,"",gap(p.gap_yf_t0).kind,p.gap_yf_t0,value=>signed(value,2)),referenceRaw:p=>p.gap_yf_t0}},
        {{label:"SP gap",value:p=>mainSub(gap(p.gap_sp_t0).main,"",gap(p.gap_sp_t0).kind,p.gap_sp_t0,value=>signed(value,2)),referenceRaw:p=>p.gap_sp_t0}},
        {{label:"Ret gap",value:p=>mainSub(gap(p.gap_ret_t0).main,"",gap(p.gap_ret_t0).kind,p.gap_ret_t0,value=>signed(value,2)),referenceRaw:p=>p.gap_ret_t0}},
        {{label:"LS gap",value:p=>mainSub(gap(p.gap_ls_t0).main,"",gap(p.gap_ls_t0).kind,p.gap_ls_t0,value=>signed(value,2)),referenceRaw:p=>p.gap_ls_t0}},
      ]}},
      {{title:"Value context",note:"Private and HDB remain separate universes. Only private-segment context applies.",rows:[
        {{label:"HDB Value band / multiplier",value:p=>mainSub("Not applicable","Excluded from condo comparison")}},
        {{label:"Private Value band",value:p=>band(p.private_value_band)}},
        {{label:"Private Value multiplier",value:p=>mainSub(number(p.private_value_multiplier),"Estate private-resale segment","",p.private_value_multiplier,value=>signed(value,2)),referenceRaw:p=>p.private_value_multiplier}},
        {{label:"Private Value sample",value:p=>mainSub(number(p.private_value_n),"Estate segment","",p.private_value_n,value=>number(value," records")),referenceRaw:p=>p.private_value_n}},
      ]}},
      {{title:"Employment, Risk and Life Path context",note:"Estate-horizon views. Project tenure replaces the HDB-only lease-risk field.",rows:[
        {{label:"Employment T0",value:p=>mainSub(p.employment_t0_band,number(p.employment_t0_score))}},
        {{label:"Employment T5",value:p=>mainSub(p.employment_t5_band,number(p.employment_t5_score))}},
        {{label:"Employment T15",value:p=>mainSub(p.employment_t15_band,number(p.employment_t15_score))}},
        {{label:"Lease risk",value:p=>mainSub(p.tenure,"HDB lease band not applied")}},
        {{label:"Noise distance score",value:p=>mainSub(number(p.noise),"1–5; higher is quieter","",p.noise,value=>signed(value,1)),referenceRaw:p=>p.noise}},
        {{label:"Best life path",value:p=>pathValue(p,"best")}},
        {{label:"Worst life path",value:p=>pathValue(p,"worst")}},
        {{label:"Interpretation flags",value:p=>(p.flags || []).join(" · ") || "None"}},
      ]}},
    ];
  }}

  function renderGroups(projects) {{
    const reference = projects[0], groups=groupsFor(projects);
    document.getElementById("factor-groups").innerHTML = groups.map(group => `<details class="factor-group" ${{group.open ? "open" : ""}}>
      <summary><b>${{esc(group.title)}}</b><span>${{esc(group.note)}}</span></summary>
      <div class="matrix-wrap" role="region" tabindex="0" aria-label="${{esc(group.title)}} comparison matrix">
      <table style="min-width:${{170 + projects.length * 190}}px"><thead><tr><th scope="col">Factor</th>${{projects.map((project,index)=>`<th scope="col">${{LETTERS[index]}} · ${{esc(title(project.project))}}</th>`).join("")}}</tr></thead>
      <tbody>${{group.rows.map(row=>`<tr><th scope="row">${{esc(row.label)}}</th>${{projects.map((project,index)=>{{
        const prepared=row.value(project);
        if (prepared && typeof prepared === "object" && row.referenceRaw) prepared.referenceRaw=row.referenceRaw;
        return `<td>${{renderValue(prepared,project,reference,index)}}</td>`;
      }}).join("")}}</tr>`).join("")}}</tbody></table></div></details>`).join("");
  }}

  function renderContext(projects) {{
    const contexts = new Map();
    projects.forEach((project,index) => {{
      const key=project.context_estate || "Unavailable";
      if (!contexts.has(key)) contexts.set(key,[]);
      contexts.get(key).push(LETTERS[index]);
    }});
    if (contexts.size === 1) {{
      const estate=contexts.keys().next().value;
      return `<b>Shared estate context:</b> All projects map to ${{esc(title(estate))}}. Framework columns may repeat even when project transactions, tenure and access differ.`;
    }}
    return `<b>Mixed estate contexts:</b> ` + [...contexts.entries()].map(([estate,letters])=>`${{letters.join("/")}} → ${{esc(title(estate))}}`).join(" · ") + `. These remain context comparisons, not project scores.`;
  }}

  function showComparison(projects,historyMode="push",focusResult=true) {{
    selected=projects;
    slots=projects.map(project=>slot(project));
    renderTray();
    document.getElementById("context-note").innerHTML=renderContext(projects);
    document.getElementById("subject-grid").innerHTML=projects.map(subjectCard).join("");
    renderGroups(projects);
    document.getElementById("comparison-result").hidden=false;
    announce(`${{projects.length}} projects compared. Project A is the reference.`);
    const url=canonicalURL(projects);
    if (historyMode === "push" && location.href !== url) history.pushState({{}}, "", url);
    else if (historyMode === "replace") history.replaceState({{}}, "", url);
    if (focusResult) document.getElementById("result-heading").focus();
  }}

  function restoreFromURL(focusResult=false) {{
    const requested=new URLSearchParams(location.search).getAll("p");
    const valid=[],seen=new Set();let omitted=0;
    requested.forEach(id => {{
      const project=byId.get(id);
      if (!project || seen.has(id) || valid.length >= MAX_PROJECTS) omitted+=1;
      else {{valid.push(project);seen.add(id);}}
    }});
    const restored=valid.length >= MIN_PROJECTS ? valid : DEFAULTS.map(id=>byId.get(id)).filter(Boolean);
    showComparison(restored,"none",focusResult);
    if (requested.length && omitted) announce(`${{omitted}} invalid, duplicate or excess URL project entr${{omitted === 1 ? "y was" : "ies were"}} omitted.`);
    else if (requested.length && valid.length < MIN_PROJECTS) announce("The URL did not contain two valid projects; the example set was restored.");
  }}

  addButton.addEventListener("click", () => {{
    if (slots.length >= MAX_PROJECTS) return;
    syncSlotValues();const added=slot(null);slots.push(added);
    markDirty(`Blank project row added. ${{slots.length}} of ${{MAX_PROJECTS}} rows in use.`);
    renderTray(added.key);
  }});
  document.getElementById("set-form").addEventListener("submit", event => {{
    event.preventDefault();const projects=validateSlots();if (projects) showComparison(projects);
  }});
  document.getElementById("copy-view").addEventListener("click", async event => {{
    const projects=selected.length ? selected : validateSlots();if (!projects) return;
    if (!selected.length) showComparison(projects,"replace",false);
    const url=canonicalURL(projects);history.replaceState({{}}, "", url);
    try {{await navigator.clipboard.writeText(url);event.currentTarget.textContent="Link copied";announce("Ordered comparison link copied.");}}
    catch (_) {{window.prompt("Copy this comparison link",url);}}
  }});
  document.getElementById("print-view").addEventListener("click", () => {{
    const projects=selected.length ? selected : validateSlots();if (!projects) return;
    if (!selected.length) showComparison(projects,"replace",false);
    window.print();
  }});
  document.getElementById("expand-all").addEventListener("click", () => document.querySelectorAll(".factor-group").forEach(group=>group.open=true));
  document.getElementById("collapse-all").addEventListener("click", () => document.querySelectorAll(".factor-group").forEach(group=>group.open=false));
  window.addEventListener("beforeprint", () => document.querySelectorAll(".factor-group").forEach(group=>group.open=true));
  window.addEventListener("popstate", () => restoreFromURL(false));
  restoreFromURL(false);
}})();
</script></body></html>"""


def generate(
    out_path: pathlib.Path = DEFAULT_OUT,
    as_of: date | None = None,
) -> tuple[pathlib.Path, int]:
    projects, latest_month = two_project.load_projects_for_comparison()
    out_path.write_text(
        render_html(projects, latest_month, as_of or date.today()), encoding="utf-8"
    )
    return out_path, len(projects)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the two-to-five-condominium framework comparison"
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path, count = generate(pathlib.Path(args.out))
    print(
        f"Written: {out_path} ({out_path.stat().st_size // 1024:,} KB, "
        f"{count:,} named project records, {MIN_PROJECTS}–{MAX_PROJECTS} selections)"
    )


if __name__ == "__main__":
    main()
