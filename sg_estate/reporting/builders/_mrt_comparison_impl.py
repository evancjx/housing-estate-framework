"""Internal MRT report renderer; execute only through ``mrt_comparison.build``.
Generate mrt_comparison_table.html from committed MRT and estate outputs.

Reads:
  data/inputs/mrt_layer.csv        - station coordinates, line, operational flag
  data/inputs/estates.csv          - framework estate centroids
  data/outputs/master_output.csv    - estate-level model context

Writes:
  mrt_comparison_table.html

Run:
  python3 models/gen_mrt_comparison_html.py
"""

from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd

from sg_estate.paths import REPOSITORY_ROOT as ROOT
from sg_estate.reporting.common import atomic_write_text, html_json, optional_value


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def distance_band(meters: float) -> str:
    if meters <= 600:
        return "core"
    if meters <= 1000:
        return "near"
    if meters <= 1400:
        return "edge"
    return "outside"


def val(value, default=None):
    result = optional_value(value)
    return default if result is None else result


def short_line(line: str) -> str:
    words = str(line).replace("-", " ").split()
    ignore = {"line", "branch"}
    code = "".join(word[0].upper() for word in words if word.lower() not in ignore)
    return code or "MRT"


mrt = pd.read_csv(ROOT / "data/inputs/mrt_layer.csv")
estates = pd.read_csv(ROOT / "data/inputs/estates.csv")
master = pd.read_csv(ROOT / "data/outputs/master_output.csv").set_index("estate")

rows = []
for _, station in mrt.iterrows():
    slat = float(station["lat"])
    slon = float(station["lon"])
    distances = [
        (
            str(estate["estate"]).strip(),
            haversine_m(slat, slon, float(estate["lat"]), float(estate["lon"])),
        )
        for _, estate in estates.iterrows()
    ]
    nearest_estate, nearest_m = min(distances, key=lambda item: item[1])
    within_800 = sum(1 for _, distance in distances if distance <= 800)
    within_1400 = sum(1 for _, distance in distances if distance <= 1400)

    context = master.loc[nearest_estate] if nearest_estate in master.index else {}
    line = str(station["line"]).strip()
    status = "Open" if int(station["operational"]) == 1 else "Future"
    ls0 = val(context.get("ls_T0_band") if hasattr(context, "get") else None, "-")
    ls5 = val(context.get("ls_T5_band") if hasattr(context, "get") else None, "-")
    ls15 = val(context.get("ls_T15_band") if hasattr(context, "get") else None, "-")

    rows.append(
        {
            "station": str(station["name"]).strip(),
            "code": str(station["stn_code"]).strip(),
            "line": line,
            "line_key": slug(line),
            "line_short": short_line(line),
            "status": status,
            "lat": round(slat, 6),
            "lon": round(slon, 6),
            "estate": nearest_estate,
            "distance_m": int(round(nearest_m)),
            "distance_band": distance_band(nearest_m),
            "within_800": within_800,
            "within_1400": within_1400,
            "provision_band": val(context.get("provision_band") if hasattr(context, "get") else None, "-"),
            "provision_score": round(float(context.get("provision_score")), 2)
            if hasattr(context, "get") and val(context.get("provision_score")) is not None
            else None,
            "ls_traj": f"{ls0} -> {ls5} -> {ls15}",
            "hdb_value_band": val(context.get("value_hdb_band") if hasattr(context, "get") else None, "-"),
            "private_value_band": val(context.get("value_private_band") if hasattr(context, "get") else None, "-"),
            "employment_band": val(context.get("emp_band") if hasattr(context, "get") else None, "-"),
            "lease_band": val(context.get("lease_band") if hasattr(context, "get") else None, "-"),
        }
    )

rows.sort(key=lambda row: row["station"])

line_counts = mrt.groupby("line").size().sort_index()
line_buttons = "\n".join(
    f'  <button class="filter-btn" data-line="{slug(line)}" onclick="filterLine(\'{slug(line)}\', this)">{line} ({count})</button>'
    for line, count in line_counts.items()
)

today = date.today().strftime("%Y-%m-%d")
open_count = int((mrt["operational"] == 1).sum())
future_count = int((mrt["operational"] == 0).sum())
data_js = html_json(rows, indent=2)

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SG MRT Station Comparison</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", monospace;
    background: #0b0d12;
    color: #cbd5e1;
    padding: 32px;
    font-size: 12px;
  }}
  h1 {{ font-size: 17px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; }}
  .meta {{ font-size: 11px; color: #64748b; margin-bottom: 18px; }}
  .summary {{
    display: grid;
    grid-template-columns: repeat(4, minmax(120px, 1fr));
    gap: 10px;
    margin-bottom: 16px;
  }}
  .metric {{
    border: 1px solid #1e293b;
    border-radius: 6px;
    background: #0d1117;
    padding: 9px 10px;
  }}
  .metric b {{ display: block; color: #f1f5f9; font-size: 16px; margin-bottom: 2px; }}
  .metric span {{ color: #64748b; font-size: 10px; }}
  .help-note {{
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    margin-bottom: 16px; padding: 8px 10px;
    border: 1px solid #1e293b; border-radius: 6px;
    background: #0d1117; color: #64748b; font-size: 11px; line-height: 1.45;
  }}
  .help-note strong {{ color: #cbd5e1; }}
  .controls {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }}
  .filter-btn {{
    padding: 5px 10px; border-radius: 5px; border: 1px solid #1e293b;
    background: #111827; color: #94a3b8; font-size: 11px; cursor: pointer;
    transition: all 0.15s;
  }}
  .filter-btn:hover, .filter-btn.active {{ border-color: #38bdf8; color: #bae6fd; background: #082f49; }}
  .search {{
    padding: 5px 10px; border-radius: 5px; border: 1px solid #1e293b;
    background: #111827; color: #e2e8f0; font-size: 11px; outline: none; width: 190px;
  }}
  .search::placeholder {{ color: #475569; }}
  .search:focus {{ border-color: #38bdf8; }}
  .line-controls {{ margin-bottom: 16px; }}
  .tbl-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #1e293b; }}
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
  thead tr.cols th.sorted {{ color: #bae6fd; }}
  thead tr.cols th.sorted-asc::after {{ content: " asc"; }}
  thead tr.cols th.sorted-desc::after {{ content: " desc"; }}
  .g-station {{ background:#0d1117; color:#38bdf8; }}
  .g-catchment {{ background:#0d1117; color:#22c55e; }}
  .g-model {{ background:#0d1117; color:#a78bfa; }}
  .g-risk {{ background:#0d1117; color:#f59e0b; }}
  tbody tr {{ border-bottom: 1px solid #111827; transition: background 0.1s; }}
  tbody tr:hover {{ background: #111827; }}
  tbody tr.hidden {{ display: none; }}
  td {{ padding: 7px 10px; text-align: center; }}
  td.station-name {{ text-align: left; font-weight: 700; color: #e2e8f0; min-width: 150px; }}
  td.estate-name {{ text-align: left; font-weight: 600; color: #cbd5e1; }}
  .line-badge {{
    display: inline-flex; min-width: 36px; height: 18px; align-items: center; justify-content: center;
    border-radius: 4px; padding: 0 6px; font-size: 10px; font-weight: 800;
    background: #172554; color: #bfdbfe;
  }}
  .line-north-south-line {{ background:#3f0909; color:#fca5a5; }}
  .line-east-west-line {{ background:#052e16; color:#86efac; }}
  .line-north-east-line {{ background:#2d1b4e; color:#c4b5fd; }}
  .line-circle-line, .line-circle-line-extension {{ background:#3b2f0b; color:#fde68a; }}
  .line-downtown-line {{ background:#0b2f4a; color:#7dd3fc; }}
  .line-thomson-east-coast-line {{ background:#3b2414; color:#fdba74; }}
  .line-jurong-region-line {{ background:#064e3b; color:#6ee7b7; }}
  .line-punggol-lrt, .line-sengkang-lrt, .line-bukit-panjang-lrt {{ background:#1f2937; color:#d1d5db; }}
  .line-changi-airport-branch-line {{ background:#083344; color:#67e8f9; }}
  .status {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; }}
  .status-open {{ background:#052e16; color:#4ade80; }}
  .status-future {{ background:#422006; color:#fbbf24; }}
  .catch-core {{ color:#4ade80; font-weight:700; }}
  .catch-near {{ color:#86efac; }}
  .catch-edge {{ color:#fbbf24; }}
  .catch-outside {{ color:#f87171; }}
  .band {{
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-weight: 700; font-size: 11px; letter-spacing: 0.3px;
  }}
  .b-A {{ background:#14532d; color:#4ade80; }}
  .b-Bp {{ background:#1e3a5f; color:#60a5fa; }}
  .b-B {{ background:#1e293b; color:#94a3b8; }}
  .b-C {{ background:#292524; color:#a8a29e; }}
  .b-D {{ background:#431407; color:#fb923c; }}
  .b-F {{ background:#3f0909; color:#f87171; }}
  .b-NR {{ background:transparent; color:#475569; }}
  .muted {{ color:#64748b; font-size: 10px; }}
  @media (max-width: 760px) {{
    body {{ padding: 18px; }}
    .summary {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
    .search {{ width: 100%; }}
  }}
  @media (max-width: 480px) {{
    body {{ padding: 18px 14px 28px; }}
    .summary {{ grid-template-columns: 1fr; }}
    .filter-btn {{ min-height: 36px; }}
  }}
</style>
</head>
<body>
<h1>SG MRT Station Comparison</h1>
<p class="meta">{len(rows)} station records | {open_count} open | {future_count} future | nearest-estate context from framework outputs | {today}</p>

<div class="summary">
  <div class="metric"><b>{len(rows)}</b><span>station records</span></div>
  <div class="metric"><b>{len(line_counts)}</b><span>lines represented</span></div>
  <div class="metric"><b>{open_count}</b><span>open stations</span></div>
  <div class="metric"><b>{future_count}</b><span>future stations</span></div>
</div>

<div class="help-note">
  <strong>Station context:</strong>
  <span>Nearest estate is based on framework estate centroid distance, not formal planning-area station assignment.</span>
  <span>Model columns describe that nearest estate, so HDB/private value remains segmented at estate level.</span>
</div>

<div class="controls">
  <button class="filter-btn active" onclick="filterStatus('all', this)">All</button>
  <button class="filter-btn" onclick="filterStatus('Open', this)">Open</button>
  <button class="filter-btn" onclick="filterStatus('Future', this)">Future</button>
  <input class="search" id="search" placeholder="Search station, code, estate..." oninput="filterTable()">
</div>
<div class="controls line-controls">
  <button class="filter-btn active" data-line="all" onclick="filterLine('all', this)">All lines</button>
{line_buttons}
</div>

<div class="tbl-wrap">
<table>
<thead>
  <tr class="group">
    <th colspan="5" class="g-station">Station</th>
    <th colspan="5" class="g-catchment">Nearest Estate Context</th>
    <th colspan="5" class="g-model">Estate Model Signals</th>
    <th colspan="2" class="g-risk">Employment / Risk</th>
  </tr>
  <tr class="cols">
    <th onclick="sortTable(0)">Station</th>
    <th onclick="sortTable(1)">Code</th>
    <th onclick="sortTable(2)">Line</th>
    <th onclick="sortTable(3)">Status</th>
    <th onclick="sortTable(4)">Line name</th>
    <th onclick="sortTable(5)">Nearest estate</th>
    <th onclick="sortTable(6)">Distance</th>
    <th onclick="sortTable(7)">Catchment</th>
    <th onclick="sortTable(8)">Estates 800m</th>
    <th onclick="sortTable(9)">Estates 1.4km</th>
    <th onclick="sortTable(10)">Prov</th>
    <th onclick="sortTable(11)">Score</th>
    <th onclick="sortTable(12)">LS path</th>
    <th onclick="sortTable(13)">HDB value</th>
    <th onclick="sortTable(14)">Private value</th>
    <th onclick="sortTable(15)">Employment</th>
    <th onclick="sortTable(16)">Lease</th>
  </tr>
</thead>
<tbody id="tbody"></tbody>
</table>
</div>

<script>
const DATA = {data_js};

function bandHTML(value) {{
  if (!value || value === "-") return '<span class="muted">-</span>';
  const cls = value === "B+" ? "Bp" : value.replace("/", "R");
  return `<span class="band b-${{cls}}">${{value}}</span>`;
}}
function statusHTML(value) {{
  const cls = value === "Open" ? "status-open" : "status-future";
  return `<span class="status ${{cls}}">${{value}}</span>`;
}}
function distanceHTML(row) {{
  return `<span class="catch-${{row.distance_band}}">${{row.distance_m.toLocaleString()}}m</span>`;
}}
function renderRow(row) {{
  return `<tr data-line="${{row.line_key}}" data-status="${{row.status}}" data-search="${{[row.station,row.code,row.line,row.estate].join(' ').toLowerCase()}}">
    <td class="station-name">${{row.station}}</td>
    <td>${{row.code}}</td>
    <td><span class="line-badge line-${{row.line_key}}">${{row.line_short}}</span></td>
    <td>${{statusHTML(row.status)}}</td>
    <td class="muted">${{row.line}}</td>
    <td class="estate-name">${{row.estate}}</td>
    <td>${{distanceHTML(row)}}</td>
    <td>${{row.distance_band}}</td>
    <td>${{row.within_800}}</td>
    <td>${{row.within_1400}}</td>
    <td>${{bandHTML(row.provision_band)}}</td>
    <td>${{row.provision_score !== null ? row.provision_score.toFixed(2) : '<span class="muted">-</span>'}}</td>
    <td class="muted">${{row.ls_traj}}</td>
    <td>${{bandHTML(row.hdb_value_band)}}</td>
    <td>${{bandHTML(row.private_value_band)}}</td>
    <td>${{bandHTML(row.employment_band)}}</td>
    <td>${{bandHTML(row.lease_band)}}</td>
  </tr>`;
}}

const tbody = document.getElementById("tbody");
tbody.innerHTML = DATA.map(renderRow).join("");

let activeStatus = "all";
let activeLine = "all";
let searchVal = "";
function filterStatus(status, btn) {{
  activeStatus = status;
  btn.parentElement.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  applyFilters();
}}
function filterLine(line, btn) {{
  activeLine = line;
  document.querySelectorAll(".line-controls .filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  applyFilters();
}}
function filterTable() {{
  searchVal = document.getElementById("search").value.toLowerCase();
  applyFilters();
}}
function applyFilters() {{
  document.querySelectorAll("#tbody tr").forEach(tr => {{
    const statusOk = activeStatus === "all" || tr.dataset.status === activeStatus;
    const lineOk = activeLine === "all" || tr.dataset.line === activeLine;
    const searchOk = tr.dataset.search.includes(searchVal);
    tr.classList.toggle("hidden", !(statusOk && lineOk && searchOk));
  }});
}}

let sortCol = -1;
let sortAsc = true;
function sortTable(col) {{
  const ths = document.querySelectorAll("thead tr.cols th");
  ths.forEach(th => th.classList.remove("sorted","sorted-asc","sorted-desc"));
  if (sortCol === col) sortAsc = !sortAsc;
  else {{ sortCol = col; sortAsc = true; }}
  ths[col].classList.add("sorted", sortAsc ? "sorted-asc" : "sorted-desc");
  const rows = Array.from(document.querySelectorAll("#tbody tr"));
  const bandOrder = {{A:6,"B+":5,B:4,C:3,D:2,F:1,"-":0}};
  const catchmentOrder = {{core:4,near:3,edge:2,outside:1}};
  rows.sort((a, b) => {{
    const at = a.querySelectorAll("td")[col]?.innerText.trim() || "";
    const bt = b.querySelectorAll("td")[col]?.innerText.trim() || "";
    const an = parseFloat(at.replace(/[^0-9.\\-]/g, ""));
    const bn = parseFloat(bt.replace(/[^0-9.\\-]/g, ""));
    let cmp;
    if (!isNaN(an) && !isNaN(bn)) cmp = an - bn;
    else if (bandOrder[at] !== undefined && bandOrder[bt] !== undefined) cmp = bandOrder[at] - bandOrder[bt];
    else if (catchmentOrder[at] !== undefined && catchmentOrder[bt] !== undefined) cmp = catchmentOrder[at] - catchmentOrder[bt];
    else cmp = at.localeCompare(bt);
    return sortAsc ? cmp : -cmp;
  }});
  rows.forEach(row => tbody.appendChild(row));
}}
sortTable(0);
</script>
</body>
</html>
"""

out = ROOT / "mrt_comparison_table.html"
atomic_write_text(out, HTML)
print(f"Written: {out} ({out.stat().st_size // 1024} KB, {len(rows)} station records)")
