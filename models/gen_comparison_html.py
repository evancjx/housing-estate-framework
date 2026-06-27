"""
Generate comparison_table.html from committed model outputs.

Reads:
  data/master_output.csv          — provision, liveability, value, employment, lease, archetypes
  data/provision_scores.csv       — per-component scores (noise column)
  data/employment_scores_T{0,5,15}.csv  — employment band per horizon

Writes:
  comparison_table.html

Run:
  python3 models/gen_comparison_html.py
"""

import json
import math
import pathlib
from datetime import date

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent

# ── load inputs ────────────────────────────────────────────────────────────────

master = pd.read_csv(ROOT / "data/master_output.csv")
prov_s = pd.read_csv(ROOT / "data/provision_scores.csv")[["estate", "noise"]].set_index("estate")
emp0   = pd.read_csv(ROOT / "data/employment_scores_T0.csv")[["estate", "emp_band"]].rename(columns={"emp_band": "e0"}).set_index("estate")
emp5   = pd.read_csv(ROOT / "data/employment_scores_T5.csv")[["estate", "emp_band"]].rename(columns={"emp_band": "e5"}).set_index("estate")
emp15  = pd.read_csv(ROOT / "data/employment_scores_T15.csv")[["estate", "emp_band"]].rename(columns={"emp_band": "e15"}).set_index("estate")

_lp = pd.read_csv(ROOT / "data/life_paths.csv")
life_best  = _lp.loc[_lp.groupby("estate")["delta"].idxmax()].set_index("estate")["path"]
life_worst = _lp.loc[_lp.groupby("estate")["delta"].idxmin()].set_index("estate")["path"]

# ── helpers ─────────────────────────────────────────────────────────────────────

def _val(v):
    """Return None for missing/not_covered values."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "nan", "NaN", "not_covered", "no_data", "N/A", "None"):
        return None
    return v

def _float(v):
    x = _val(v)
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def _band(v):
    x = _val(v)
    if x is None:
        return None
    return str(x)

def _mult(value_score, provision_score):
    v = _float(value_score)
    p = _float(provision_score)
    if v is None or p is None or p == 0:
        return None
    return round(v / p, 4)

def _gap(v):
    x = _float(v)
    if x is None:
        return None
    return round(x, 2)

def _flags(row, hdb_m, d):
    flags = []
    arch = str(row.get("archetype", "")).strip()
    if arch == "X":
        flags.append("nr")
    if d is not None and d < 1.0:
        flags.append("disruption")
    if hdb_m is not None:
        if hdb_m > 1.1:
            flags.append("underpriced")
        elif hdb_m < 0.9:
            flags.append("overpriced")
    return ",".join(flags)

# ── build DATA rows ─────────────────────────────────────────────────────────────

rows = []
for _, r in master.iterrows():
    estate = str(r["estate"]).strip()
    arch   = _band(r.get("archetype")) or "?"
    d      = _float(r.get("D_T0")) if _val(r.get("D_T0")) else 1.0
    prov_b = _band(r.get("provision_band"))
    score  = _float(r.get("provision_score"))
    prov_n = _float(r.get("provision_score"))

    noise_raw = prov_s.loc[estate, "noise"] if estate in prov_s.index else None
    noise = int(noise_raw) if noise_raw is not None and not math.isnan(float(noise_raw)) else None

    hdb_b = _band(r.get("value_hdb_band"))
    hdb_m = _mult(r.get("value_hdb_score"), prov_n)

    # Private value
    pvt_b_raw = _val(r.get("value_private_band"))
    pvt_b = str(pvt_b_raw) if pvt_b_raw not in (None, "not_covered") else None
    pvt_m = _mult(r.get("value_private_score"), prov_n) if pvt_b else None
    pvt_n_raw = _float(r.get("value_private_n"))
    pvt_n = int(pvt_n_raw) if pvt_n_raw and not math.isnan(pvt_n_raw) else None

    # Employment per horizon
    e0  = str(emp0.loc[estate, "e0"])  if estate in emp0.index  else None
    e5  = str(emp5.loc[estate, "e5"])  if estate in emp5.index  else None
    e15 = str(emp15.loc[estate, "e15"]) if estate in emp15.index else None

    lease  = _band(r.get("lease_band"))
    best   = str(life_best[estate]) if estate in life_best.index else None
    worst  = str(life_worst[estate]) if estate in life_worst.index else None

    flag = _flags(dict(r), hdb_m, d)

    obj = {
        "estate": estate,
        "arch":   arch,
        "d":      d,
        "prov":   prov_b,
        "score":  round(score, 2) if score is not None else None,
        "noise":  noise,
        "yf0":    _band(r.get("yf_T0_band")),
        "sp0":    _band(r.get("sp_T0_band")),
        "ret0":   _band(r.get("ret_T0_band")),
        "ls0":    _band(r.get("ls_T0_band")),
        "ls5":    _band(r.get("ls_T5_band")),
        "ls15":   _band(r.get("ls_T15_band")),
        "gap_yf": _gap(r.get("gap_yf_T0")),
        "gap_sp": _gap(r.get("gap_sp_T0")),
        "gap_ret": _gap(r.get("gap_ret_T0")),
        "gap_ls": _gap(r.get("gap_ls_T0")),
        "hdb_b":  hdb_b,
        "hdb_m":  hdb_m,
        "pvt_b":  pvt_b,
        "pvt_m":  pvt_m,
        "pvt_n":  pvt_n,
        "emp0":   e0,
        "emp5":   e5,
        "emp15":  e15,
        "lease":  lease,
        "best":   str(best) if best else None,
        "worst":  str(worst) if worst else None,
        "flag":   flag,
    }
    rows.append(obj)

n_estates   = len(rows)
today       = date.today().strftime("%Y-%m-%d")
data_js     = json.dumps(rows, indent=2, ensure_ascii=False)

# ── HTML template ───────────────────────────────────────────────────────────────

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SG Estate Comparison — All Districts</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", monospace;
    background: #0b0d12;
    color: #cbd5e1;
    padding: 32px;
    font-size: 12px;
  }}
  h1 {{ font-size: 17px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; letter-spacing: -0.3px; }}
  .meta {{ font-size: 11px; color: #475569; margin-bottom: 24px; }}
  .help-note {{
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    margin: -8px 0 16px; padding: 8px 10px;
    border: 1px solid #1e293b; border-radius: 6px;
    background: #0d1117; color: #64748b; font-size: 11px; line-height: 1.45;
  }}
  .help-note strong {{ color: #cbd5e1; font-weight: 700; }}
  .help-note span {{ color: #475569; }}

  .controls {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }}
  .filter-btn {{
    padding: 5px 12px; border-radius: 5px; border: 1px solid #1e293b;
    background: #111827; color: #94a3b8; font-size: 11px; cursor: pointer;
    transition: all 0.15s;
  }}
  .filter-btn:hover, .filter-btn.active {{ border-color: #6366f1; color: #a5b4fc; background: #1e1b4b; }}
  .search {{ padding: 5px 10px; border-radius: 5px; border: 1px solid #1e293b;
            background: #111827; color: #e2e8f0; font-size: 11px; outline: none; width: 160px; }}
  .search::placeholder {{ color: #374151; }}
  .search:focus {{ border-color: #6366f1; }}

  .tbl-wrap {{ overflow-x: auto; border-radius: 10px; border: 1px solid #1e293b; }}
  table {{ border-collapse: collapse; width: 100%; white-space: nowrap; }}

  thead tr.group th {{
    padding: 8px 10px 6px;
    font-size: 9px; font-weight: 700; letter-spacing: 1.1px; text-transform: uppercase;
    border-bottom: 1px solid #1e293b;
    text-align: center;
  }}
  thead tr.cols th {{
    padding: 6px 10px 8px;
    font-size: 10px; font-weight: 600; color: #64748b;
    border-bottom: 2px solid #1e293b;
    cursor: pointer; user-select: none;
    text-align: center;
  }}
  thead tr.cols th:hover {{ color: #94a3b8; }}
  thead tr.cols th.sorted {{ color: #a5b4fc; }}
  thead tr.cols th.sorted-asc::after {{ content: " ↑"; }}
  thead tr.cols th.sorted-desc::after {{ content: " ↓"; }}
  .tip {{
    position: relative;
    display: inline-flex;
    align-items: center;
    border-bottom: 1px dotted #475569;
    cursor: help;
  }}
  .tip::after {{
    content: attr(data-tip);
    position: absolute;
    left: 50%;
    top: calc(100% + 8px);
    transform: translateX(-50%);
    z-index: 50;
    width: max-content;
    max-width: 240px;
    padding: 6px 8px;
    border: 1px solid #334155;
    border-radius: 5px;
    background: #020617;
    color: #cbd5e1;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0;
    text-transform: none;
    line-height: 1.35;
    text-align: left;
    white-space: normal;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s ease;
  }}
  .tip::before {{
    content: "";
    position: absolute;
    left: 50%;
    top: calc(100% + 3px);
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-bottom-color: #334155;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s ease;
  }}
  .tip:hover::after,
  .tip:hover::before,
  .tip:focus-visible::after,
  .tip:focus-visible::before {{
    opacity: 1;
  }}

  .g-id   {{ background: #0d1117; color: #334155; }}
  .g-prov {{ background: #0d1117; color: #1e40af; }}
  .g-live {{ background: #0d1117; color: #065f46; }}
  .g-gap  {{ background: #0d1117; color: #7c3aed; }}
  .g-val  {{ background: #0d1117; color: #92400e; }}
  .g-emp  {{ background: #0d1117; color: #1d4ed8; }}
  .g-risk {{ background: #0d1117; color: #7f1d1d; }}
  .g-path {{ background: #0d1117; color: #374151; }}

  tbody tr {{ border-bottom: 1px solid #111827; transition: background 0.1s; }}
  tbody tr:hover {{ background: #111827; }}
  tbody tr.nr-row {{ opacity: 0.45; }}
  tbody tr.hidden {{ display: none; }}

  td {{ padding: 7px 10px; text-align: center; }}
  td.estate-name {{ text-align: left; font-weight: 600; color: #e2e8f0; min-width: 130px; }}
  td.path {{ font-size: 10px; color: #64748b; }}
  td.pvt-n {{ font-size: 10px; color: #475569; }}

  .band {{
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-weight: 700; font-size: 11px; letter-spacing: 0.3px;
  }}
  .b-A   {{ background: #14532d; color: #4ade80; }}
  .b-Bp  {{ background: #1e3a5f; color: #60a5fa; }}
  .b-B   {{ background: #1e293b; color: #94a3b8; }}
  .b-C   {{ background: #292524; color: #a8a29e; }}
  .b-D   {{ background: #431407; color: #fb923c; }}
  .b-F   {{ background: #3f0909; color: #f87171; }}
  .b-NR  {{ background: transparent; color: #374151; }}

  .arch {{
    display: inline-block; width: 18px; height: 18px; border-radius: 4px;
    text-align: center; line-height: 18px; font-weight: 800; font-size: 11px;
  }}
  .arch-A {{ background:#1e3a5f; color:#60a5fa; }}
  .arch-B {{ background:#1e293b; color:#94a3b8; }}
  .arch-C {{ background:#1e3a2f; color:#6ee7b7; }}
  .arch-D {{ background:#3b1f2b; color:#f9a8d4; }}
  .arch-E {{ background:#2d1b4e; color:#c4b5fd; }}
  .arch-F {{ background:#292524; color:#a8a29e; }}
  .arch-G {{ background:#1c2f1c; color:#86efac; }}
  .arch-X {{ background:#374151; color:#9ca3af; }}

  .traj {{ font-family: monospace; font-size: 11px; color: #94a3b8; letter-spacing: 0.5px; }}
  .gap-pos  {{ color: #4ade80; font-weight: 700; }}
  .gap-neg  {{ color: #f87171; font-weight: 700; }}
  .gap-zero {{ color: #374151; }}
  .mult-up   {{ color: #4ade80; font-size: 11px; }}
  .mult-flat {{ color: #64748b; font-size: 11px; }}
  .mult-down {{ color: #f87171; font-size: 11px; }}
  .d-full {{ color: #374151; }}
  .d-warn {{ color: #fbbf24; font-weight: 700; }}
  .d-bad  {{ color: #f87171; font-weight: 700; }}

  .note-overpriced  {{ background: #3f0909; color: #f87171; padding: 1px 5px; border-radius: 3px; font-size: 10px; }}
  .note-underpriced {{ background: #14532d; color: #4ade80; padding: 1px 5px; border-radius: 3px; font-size: 10px; }}
  .note-disrupt     {{ background: #431407; color: #fbbf24; padding: 1px 5px; border-radius: 3px; font-size: 10px; }}
  .note-nr          {{ background: #1e293b; color: #475569; padding: 1px 5px; border-radius: 3px; font-size: 10px; }}

  .noise-dot {{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px;
    vertical-align: middle;
  }}

  .legend {{
    display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px;
    font-size: 10px; color: #475569;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}

  th[colspan] {{ border-right: 1px solid #1e3a5f; }}
  td:last-child {{ border-right: none; }}
  .col-sep {{ border-left: 1px solid #1e293b; }}
</style>
</head>
<body>
<h1>SG Estate Comparison</h1>
<p class="meta">{n_estates} estates · 20-component provision · 4 personas × 3 horizons · HDB + private value · {today}</p>

<div class="help-note">
  <strong>Liveability note:</strong>
  <div>YF=young family, SP=single professional, Ret=retiree, <strong>LS=lifestyle persona</strong>.</div>
  <span>LS trajectory shows the lifestyle persona band from T0 now to T5 2031 to T15 2041.</span>
</div>

<div class="controls">
  <button class="filter-btn active" onclick="filterArch('all',this)">All</button>
  <button class="filter-btn" onclick="filterArch('A',this)">A — Regional</button>
  <button class="filter-btn" onclick="filterArch('B',this)">B — Mature HDB</button>
  <button class="filter-btn" onclick="filterArch('C',this)">C — Coastal</button>
  <button class="filter-btn" onclick="filterArch('D',this)">D — Private Enclave</button>
  <button class="filter-btn" onclick="filterArch('E',this)">E — New Central-Edge</button>
  <button class="filter-btn" onclick="filterArch('F',this)">F — Infill MRT Node</button>
  <button class="filter-btn" onclick="filterArch('G',this)">G — New Town</button>
  <input class="search" id="search" placeholder="Search estate..." oninput="filterTable()">
</div>

<div class="tbl-wrap">
<table>
<thead>
  <tr class="group">
    <th colspan="2" class="g-id"><span class="tip" data-tip="Estate name and archetype family.">IDENTITY</span></th>
    <th colspan="3" class="g-prov"><span class="tip" data-tip="Objective supply-side provision score plus the T0 disruption multiplier.">PROVISION</span></th>
    <th colspan="4" class="g-live"><span class="tip" data-tip="Current liveability bands by persona. These are person-relative, not a single estate ranking.">LIVEABILITY (T0)</span></th>
    <th colspan="2" class="g-live"><span class="tip" data-tip="Lifestyle persona trajectory from T0 now to T5 2031 to T15 2041.">LS TRAJECTORY</span></th>
    <th colspan="4" class="g-gap"><span class="tip" data-tip="Liveability minus provision. Positive means the persona rates the estate above its supply checklist score.">GAP (live−prov)</span></th>
    <th colspan="2" class="g-val"><span class="tip" data-tip="HDB resale value segment. Value is kept separate from private value.">HDB VALUE</span></th>
    <th colspan="3" class="g-val"><span class="tip" data-tip="Private resale value segment. Not blended or ranked against HDB.">PRIVATE VALUE</span></th>
    <th colspan="3" class="g-emp"><span class="tip" data-tip="Employment access bands across current and future horizons.">EMPLOYMENT</span></th>
    <th colspan="2" class="g-risk"><span class="tip" data-tip="Lease and noise risk indicators. Higher bands or scores are better.">RISK</span></th>
    <th colspan="2" class="g-path"><span class="tip" data-tip="Life-stage paths with the largest and smallest modeled change.">LIFE PATH</span></th>
    <th class="g-path"><span class="tip" data-tip="Flags for notable interpretation issues such as disruption or pricing signals.">FLAGS</span></th>
  </tr>
  <tr class="cols">
    <th onclick="sortTable(0)"><span class="tip" data-tip="Estate or sub-estate name.">Estate</span></th>
    <th onclick="sortTable(1)"><span class="tip" data-tip="Archetype code: A regional, B mature HDB, C coastal, D private enclave, E new central-edge, F infill MRT node, G new town, X not rated.">Type</span></th>
    <th onclick="sortTable(2)"><span class="tip" data-tip="D = disruption multiplier at T0. 1.00 means no current construction penalty; lower values reduce liveability.">D</span></th>
    <th onclick="sortTable(3)"><span class="tip" data-tip="Provision band: objective supply-side score for what is available in the estate.">Prov</span></th>
    <th onclick="sortTable(4)"><span class="tip" data-tip="Numeric provision score on the 1 to 5 framework scale.">Score</span></th>
    <th onclick="sortTable(5)"><span class="tip" data-tip="YF = young family liveability band at T0.">YF</span></th>
    <th onclick="sortTable(6)"><span class="tip" data-tip="SP = single professional liveability band at T0.">SP</span></th>
    <th onclick="sortTable(7)"><span class="tip" data-tip="Ret = retiree liveability band at T0.">Ret</span></th>
    <th onclick="sortTable(8)"><span class="tip" data-tip="LS = lifestyle persona liveability band at T0.">LS</span></th>
    <th onclick="sortTable(9)"><span class="tip" data-tip="Lifestyle persona band sequence from now to 2031 to 2041.">T0→T5→T15</span></th>
    <th onclick="sortTable(10)"><span class="tip" data-tip="Net lifestyle trajectory: up, flat, or down from T0 to T15.">Arrow</span></th>
    <th onclick="sortTable(11)"><span class="tip" data-tip="Young family liveability score minus provision score at T0.">YF gap</span></th>
    <th onclick="sortTable(12)"><span class="tip" data-tip="Single professional liveability score minus provision score at T0.">SP gap</span></th>
    <th onclick="sortTable(13)"><span class="tip" data-tip="Retiree liveability score minus provision score at T0.">Ret gap</span></th>
    <th onclick="sortTable(14)"><span class="tip" data-tip="Lifestyle persona liveability score minus provision score at T0.">LS gap</span></th>
    <th onclick="sortTable(15)"><span class="tip" data-tip="HDB value band. Below trust threshold, the model reports bands rather than decimal precision.">Band</span></th>
    <th onclick="sortTable(16)"><span class="tip" data-tip="HDB value multiplier versus provision. Above 1 suggests underpriced; below 1 suggests overpriced.">Mult</span></th>
    <th onclick="sortTable(17)"><span class="tip" data-tip="Private resale value band. This is separate from HDB value.">Band</span></th>
    <th onclick="sortTable(18)"><span class="tip" data-tip="Private value multiplier versus provision. Above 1 suggests underpriced; below 1 suggests overpriced.">Mult</span></th>
    <th onclick="sortTable(19)"><span class="tip" data-tip="Private resale sample count used for the value estimate.">n</span></th>
    <th onclick="sortTable(20)"><span class="tip" data-tip="Current employment access band.">T0</span></th>
    <th onclick="sortTable(21)"><span class="tip" data-tip="2031 employment access band after modeled near-term changes.">T5</span></th>
    <th onclick="sortTable(22)"><span class="tip" data-tip="2041 employment access band after modeled long-horizon changes.">T15</span></th>
    <th onclick="sortTable(23)"><span class="tip" data-tip="Lease risk band from HDB resale remaining lease years or manual override for new estates.">Lease</span></th>
    <th onclick="sortTable(24)"><span class="tip" data-tip="Noise distance score from 1 to 5. Higher is quieter.">Noise</span></th>
    <th onclick="sortTable(25)"><span class="tip" data-tip="Life-stage path with the largest modeled improvement for this estate.">Best path</span></th>
    <th onclick="sortTable(26)"><span class="tip" data-tip="Life-stage path with the smallest modeled improvement or largest decline.">Worst path</span></th>
    <th onclick="sortTable(27)"><span class="tip" data-tip="Interpretation flags such as not rated, disruption, underpriced, or overpriced.">Notes</span></th>
  </tr>
</thead>
<tbody id="tbody">
</tbody>
</table>
</div>

<div class="legend">
  <div class="legend-item"><span class="band b-A">A</span> best</div>
  <div class="legend-item"><span class="band b-Bp">B+</span></div>
  <div class="legend-item"><span class="band b-B">B</span></div>
  <div class="legend-item"><span class="band b-C">C</span></div>
  <div class="legend-item"><span class="band b-D">D</span></div>
  <div class="legend-item"><span class="band b-F">F</span> worst</div>
  <div style="width:1px;height:14px;background:#1e293b;margin:0 4px"></div>
  <div class="legend-item"><span style="color:#4ade80">▲ mult</span> underpriced vs provision</div>
  <div class="legend-item"><span style="color:#f87171">▼ mult</span> overpriced vs provision</div>
  <div class="legend-item"><span style="color:#4ade80">+gap</span> lovable beyond checklist</div>
  <div class="legend-item"><span style="color:#f87171">−gap</span> over-equipped for persona</div>
  <div style="width:1px;height:14px;background:#1e293b;margin:0 4px"></div>
  <div class="legend-item">Liveability personas: YF=YoungFam · SP=SinglePro · Ret=Retiree · LS=Lifestyle</div>
  <div class="legend-item">T0=now · T5=2031 · T15=2041</div>
  <div class="legend-item">Noise in Risk = distance score 1–5 (5=quiet)</div>
  <div class="legend-item">Archetypes: A=Regional · B=Mature HDB · C=Coastal · D=Private Enclave · E=New Central-Edge · F=Infill Node · G=New Town · X=N/R</div>
  <div class="legend-item">Gap values shown as raw score delta (positive=punches above provision, negative=below)</div>
</div>

<script>
const DATA = {data_js};

function bandClass(b) {{
  if (!b || b === "N/R" || b === "—") return "b-NR";
  return {{A:"b-A","B+":"b-Bp",B:"b-B",C:"b-C",D:"b-D",F:"b-F"}}[b] || "b-NR";
}}
function bandHTML(b) {{
  if (!b) return '<span class="band b-NR">—</span>';
  if (b === "N/R") return '<span class="band b-NR">N/R</span>';
  return `<span class="band ${{bandClass(b)}}">${{b}}</span>`;
}}
function multHTML(m) {{
  if (m === null || m === undefined) return '<span style="color:#374151">—</span>';
  const cls = m >= 1.05 ? "mult-up" : m <= 0.90 ? "mult-down" : "mult-flat";
  const arrow = m >= 1.05 ? "▲" : m <= 0.90 ? "▼" : "";
  return `<span class="${{cls}}">${{arrow}}${{m.toFixed(2)}}×</span>`;
}}
function gapHTML(g) {{
  if (g === null || g === undefined) return '<span style="color:#374151">N/R</span>';
  if (g > 0.02)  return `<span class="gap-pos">+${{g.toFixed(2)}}</span>`;
  if (g < -0.02) return `<span class="gap-neg">${{g.toFixed(2)}}</span>`;
  return `<span class="gap-zero">0</span>`;
}}
function dHTML(d) {{
  if (d >= 1.0) return '<span class="d-full">1.00</span>';
  if (d >= 0.95) return `<span class="d-warn">${{d.toFixed(2)}}</span>`;
  return `<span class="d-bad">${{d.toFixed(2)}}</span>`;
}}
function noiseScoreHTML(n) {{
  if (n === null || n === undefined) return '—';
  const colors = {{1:"#f87171",2:"#fb923c",3:"#fbbf24",4:"#86efac",5:"#4ade80"}};
  const labels = {{1:"loud",2:"noisy",3:"mod",4:"quiet",5:"silent"}};
  return `<span class="noise-dot" style="background:${{colors[n]}}"></span>${{n}} <span style="color:#374151;font-size:10px">${{labels[n]}}</span>`;
}}
function pathShort(p) {{
  return {{forming_family:"forming fam",downsizing:"downsizing",settling_single:"settling",ageing_in_place:"ageing",upgrader:"upgrader","N/R":"N/R"}}[p] || (p || "—");
}}
function flagHTML(f) {{
  if (!f) return "";
  return f.split(",").map(p => {{
    if (p==="overpriced")  return '<span class="note-overpriced">▼ overpriced</span>';
    if (p==="underpriced") return '<span class="note-underpriced">▲ underpriced</span>';
    if (p==="disruption")  return '<span class="note-disrupt">⚠ disruption</span>';
    if (p==="nr")          return '<span class="note-nr">N/R — exits pipeline</span>';
    return "";
  }}).join(" ");
}}
function trajHTML(r) {{
  if (!r.ls0 || r.ls0 === "N/R") return '<span style="color:#374151">N/R</span>';
  const order = {{A:6,"B+":5,B:4,C:3,D:2,F:1}};
  const arrow = (a,b) => {{ const d=(order[b]||0)-(order[a]||0); return d>0?"↗":d<0?"↘":"→"; }};
  return `<span class="traj">${{r.ls0}} ${{arrow(r.ls0,r.ls5)}} ${{r.ls5}} ${{arrow(r.ls5,r.ls15)}} ${{r.ls15}}</span>`;
}}
function trajArrow(r) {{
  if (!r.ls0 || r.ls0 === "N/R") return '—';
  const order = {{A:6,"B+":5,B:4,C:3,D:2,F:1}};
  const net = (order[r.ls15]||0) - (order[r.ls0]||0);
  if (net > 1) return '<span style="color:#4ade80;font-weight:700">↑↑</span>';
  if (net > 0) return '<span style="color:#86efac">↑</span>';
  if (net < 0) return '<span style="color:#f87171">↓</span>';
  return '<span style="color:#374151">→</span>';
}}

function renderRow(r) {{
  const isNR = r.arch === "X";
  return `<tr class="${{isNR ? 'nr-row' : ''}}" data-arch="${{r.arch}}" data-estate="${{r.estate.toLowerCase()}}">
    <td class="estate-name">${{r.estate}}</td>
    <td><span class="arch arch-${{r.arch}}">${{r.arch}}</span></td>
    <td>${{dHTML(r.d)}}</td>
    <td>${{bandHTML(r.prov)}}</td>
    <td style="color:#64748b">${{r.score !== null ? r.score.toFixed(2) : "—"}}</td>
    <td>${{bandHTML(r.yf0)}}</td>
    <td>${{bandHTML(r.sp0)}}</td>
    <td>${{bandHTML(r.ret0)}}</td>
    <td>${{bandHTML(r.ls0)}}</td>
    <td>${{trajHTML(r)}}</td>
    <td>${{trajArrow(r)}}</td>
    <td>${{gapHTML(r.gap_yf)}}</td>
    <td>${{gapHTML(r.gap_sp)}}</td>
    <td>${{gapHTML(r.gap_ret)}}</td>
    <td>${{gapHTML(r.gap_ls)}}</td>
    <td>${{bandHTML(r.hdb_b)}}</td>
    <td>${{multHTML(r.hdb_m)}}</td>
    <td>${{bandHTML(r.pvt_b)}}</td>
    <td>${{r.pvt_m !== null ? multHTML(r.pvt_m) : '<span style="color:#374151">—</span>'}}</td>
    <td class="pvt-n">${{r.pvt_n !== null ? r.pvt_n.toLocaleString() : '—'}}</td>
    <td>${{bandHTML(r.emp0)}}</td>
    <td>${{bandHTML(r.emp5)}}</td>
    <td>${{bandHTML(r.emp15)}}</td>
    <td>${{bandHTML(r.lease)}}</td>
    <td>${{noiseScoreHTML(r.noise)}}</td>
    <td class="path">${{pathShort(r.best)}}</td>
    <td class="path">${{pathShort(r.worst)}}</td>
    <td>${{flagHTML(r.flag)}}</td>
  </tr>`;
}}

const tbody = document.getElementById("tbody");
tbody.innerHTML = DATA.map(renderRow).join("");

let activeArch = "all", searchVal = "";
function filterArch(arch, btn) {{
  activeArch = arch;
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  applyFilters();
}}
function filterTable() {{
  searchVal = document.getElementById("search").value.toLowerCase();
  applyFilters();
}}
function applyFilters() {{
  document.querySelectorAll("#tbody tr").forEach(tr => {{
    const archOk = activeArch === "all" || tr.dataset.arch === activeArch;
    const searchOk = tr.dataset.estate.includes(searchVal);
    tr.classList.toggle("hidden", !(archOk && searchOk));
  }});
}}

let sortCol = -1, sortAsc = true;
function sortTable(col) {{
  const ths = document.querySelectorAll("thead tr.cols th");
  ths.forEach(th => th.classList.remove("sorted","sorted-asc","sorted-desc"));
  if (sortCol === col) sortAsc = !sortAsc;
  else {{ sortCol = col; sortAsc = true; }}
  ths[col].classList.add("sorted", sortAsc ? "sorted-asc" : "sorted-desc");
  const rows = Array.from(document.querySelectorAll("#tbody tr"));
  const BAND_ORDER = {{A:6,"B+":5,B:4,C:3,D:2,F:1,"N/R":0}};
  rows.sort((a,b) => {{
    const at = a.querySelectorAll("td")[col]?.innerText.trim() || "";
    const bt = b.querySelectorAll("td")[col]?.innerText.trim() || "";
    const an = parseFloat(at.replace(/[^0-9.\\-]/g,""));
    const bn = parseFloat(bt.replace(/[^0-9.\\-]/g,""));
    let cmp;
    if (!isNaN(an) && !isNaN(bn)) cmp = an - bn;
    else if (BAND_ORDER[at] !== undefined && BAND_ORDER[bt] !== undefined) cmp = BAND_ORDER[at] - BAND_ORDER[bt];
    else cmp = at.localeCompare(bt);
    return sortAsc ? cmp : -cmp;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</body>
</html>"""

out = ROOT / "comparison_table.html"
out.write_text(HTML, encoding="utf-8")
print(f"Written: {out}  ({out.stat().st_size // 1024} KB, {n_estates} estates)")
