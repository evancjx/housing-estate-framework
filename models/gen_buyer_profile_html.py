#!/usr/bin/env python3
"""
Generate buyer_profile_table.html from data/buyer_profile_output.csv.

Reads:
  data/buyer_profile_output.csv

Writes:
  buyer_profile_table.html

Run:
  python3 models/gen_buyer_profile_html.py
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
from datetime import date
from typing import Any

import pandas as pd


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "data/buyer_profile_output.csv"
DEFAULT_OUT = ROOT / "buyer_profile_table.html"

REQUIRED_COLUMNS = {
    "profile_id",
    "estate",
    "tenure",
    "eligible",
    "rank",
    "profile_score",
    "filter_reasons",
    "liveability_band",
    "value_band",
    "value_basis",
    "value_n",
    "employment_band",
    "lease_band",
    "provision_band",
    "archetype",
}


def clean_text(value: Any, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return default
    return text


def number_or_none(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text in {"N/R", "N/A", "no_data", "not_covered"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"true", "1", "yes", "y"}


def load_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run models/buyer_profile_model.py first.")
    df = pd.read_csv(path, keep_default_na=False)
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rows.append({
            "profile_id": clean_text(row["profile_id"]),
            "estate": clean_text(row["estate"]),
            "tenure": clean_text(row["tenure"]),
            "eligible": bool_value(row["eligible"]),
            "rank": int(number_or_none(row["rank"]) or 0) or None,
            "profile_score": number_or_none(row["profile_score"]),
            "soft_weight_covered": number_or_none(row.get("soft_weight_covered")),
            "filter_reasons": clean_text(row["filter_reasons"]),
            "persona": clean_text(row.get("persona")),
            "horizon": clean_text(row.get("horizon")),
            "life_path": clean_text(row.get("life_path")),
            "liveability_score": number_or_none(row.get("liveability_score")),
            "liveability_band": clean_text(row["liveability_band"]),
            "value_score": number_or_none(row.get("value_score")),
            "value_band": clean_text(row["value_band"]),
            "value_basis": clean_text(row["value_basis"]),
            "value_n": number_or_none(row["value_n"]),
            "employment_score": number_or_none(row.get("employment_score")),
            "employment_band": clean_text(row["employment_band"]),
            "lease_score": number_or_none(row.get("lease_score")),
            "lease_band": clean_text(row["lease_band"]),
            "provision_score": number_or_none(row.get("provision_score")),
            "provision_band": clean_text(row["provision_band"]),
            "archetype": clean_text(row["archetype"]),
            "measured_only": bool_value(row.get("measured_only", False)),
        })
    return rows


def profile_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for profile_id in sorted({r["profile_id"] for r in rows}):
        profile_rows = [r for r in rows if r["profile_id"] == profile_id]
        eligible = [r for r in profile_rows if r["eligible"]]
        top = sorted(
            eligible,
            key=lambda r: (r["rank"] is None, r["rank"] or 9999, -(r["profile_score"] or 0)),
        )[:1]
        out.append({
            "profile_id": profile_id,
            "rows": len(profile_rows),
            "eligible": len(eligible),
            "top_estate": top[0]["estate"] if top else "",
            "top_tenure": top[0]["tenure"] if top else "",
            "top_score": top[0]["profile_score"] if top else None,
        })
    return out


def render_html(rows: list[dict[str, Any]], generated_on: str) -> str:
    profiles = sorted({r["profile_id"] for r in rows})
    tenures = sorted({r["tenure"] for r in rows})
    summary = profile_summary(rows)
    data_json = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    summary_json = json.dumps(summary, ensure_ascii=False).replace("</", "<\\/")
    profile_options = "\n".join(
        f'<option value="{html.escape(p)}">{html.escape(p)}</option>' for p in profiles
    )
    tenure_options = "\n".join(
        f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in tenures
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Buyer Profile Evaluation</title>
  <style>
    :root {{
      --bg: #f6f7f8;
      --surface: #ffffff;
      --line: #d9dee5;
      --text: #1f2933;
      --muted: #687586;
      --good: #146c43;
      --warn: #9a5b00;
      --bad: #9b1c31;
      --blue: #1f5f99;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
    }}
    header {{
      padding: 18px 24px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    main {{
      padding: 16px 24px 28px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .tile {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      min-height: 86px;
    }}
    .tile strong {{
      display: block;
      font-size: 13px;
      margin-bottom: 8px;
      overflow-wrap: anywhere;
    }}
    .tile-row {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
    }}
    .controls {{
      display: grid;
      grid-template-columns: minmax(220px, 1.3fr) minmax(190px, 1fr) minmax(120px, .55fr) minmax(120px, .55fr) minmax(150px, .7fr) auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 12px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
    }}
    label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    select, input {{
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #fff;
      color: var(--text);
      padding: 6px 8px;
      font: inherit;
    }}
    button {{
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #f9fafb;
      color: var(--text);
      padding: 6px 12px;
      font: inherit;
      cursor: pointer;
    }}
    button:hover {{ background: #eef2f6; }}
    .table-wrap {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: auto;
      max-height: 72vh;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1160px;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef2f6;
      color: #334155;
      font-size: 12px;
      font-weight: 650;
    }}
    tr:hover td {{ background: #fbfcfd; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .muted {{ color: var(--muted); }}
    .reason {{
      white-space: normal;
      min-width: 260px;
      color: var(--muted);
    }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      line-height: 1.4;
      border: 1px solid var(--line);
      background: #f8fafc;
    }}
    .ok {{ color: var(--good); border-color: #a8d5bd; background: #eef8f2; }}
    .no {{ color: var(--bad); border-color: #efb4bd; background: #fff1f3; }}
    .seg {{ color: var(--blue); border-color: #b8d2ea; background: #eef6fc; }}
    .band-a, .band-bp {{ color: var(--good); }}
    .band-b {{ color: var(--blue); }}
    .band-c, .band-d {{ color: var(--warn); }}
    .band-f, .band-nr, .band-no {{ color: var(--bad); }}
    .countline {{
      margin: 8px 0 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 900px) {{
      main {{ padding: 12px; }}
      header {{ padding: 14px 12px 10px; }}
      .controls {{ grid-template-columns: 1fr 1fr; }}
      .controls .wide {{ grid-column: 1 / -1; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Buyer Profile Evaluation</h1>
    <div class="meta">Generated {html.escape(generated_on)} from data/buyer_profile_output.csv</div>
  </header>
  <main>
    <section class="summary" id="summary"></section>
    <section class="controls">
      <div class="wide">
        <label for="profileFilter">Profile</label>
        <select id="profileFilter">
          <option value="">All profiles</option>
          {profile_options}
        </select>
      </div>
      <div>
        <label for="searchFilter">Estate</label>
        <input id="searchFilter" type="search" placeholder="Search estate">
      </div>
      <div>
        <label for="tenureFilter">Segment</label>
        <select id="tenureFilter">
          <option value="">All</option>
          {tenure_options}
        </select>
      </div>
      <div>
        <label for="eligibleFilter">Status</label>
        <select id="eligibleFilter">
          <option value="">All</option>
          <option value="true">Eligible</option>
          <option value="false">Filtered</option>
        </select>
      </div>
      <div>
        <label for="minScore">Min score</label>
        <input id="minScore" type="number" min="0" max="5" step="0.1" placeholder="0.0">
      </div>
      <button id="resetBtn" type="button">Reset</button>
    </section>
    <div class="countline" id="countLine"></div>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Profile</th>
            <th class="num">Rank</th>
            <th>Estate</th>
            <th>Segment</th>
            <th>Status</th>
            <th class="num">Score</th>
            <th>Liveability</th>
            <th>Value</th>
            <th>Employment</th>
            <th>Lease</th>
            <th>Provision</th>
            <th>Value Basis</th>
            <th>Reasons</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </section>
  </main>
  <script id="rowData" type="application/json">{data_json}</script>
  <script id="summaryData" type="application/json">{summary_json}</script>
  <script>
    const rows = JSON.parse(document.getElementById("rowData").textContent);
    const summary = JSON.parse(document.getElementById("summaryData").textContent);
    const controls = {{
      profile: document.getElementById("profileFilter"),
      search: document.getElementById("searchFilter"),
      tenure: document.getElementById("tenureFilter"),
      eligible: document.getElementById("eligibleFilter"),
      minScore: document.getElementById("minScore"),
    }};
    const tbody = document.getElementById("rows");
    const countLine = document.getElementById("countLine");

    function esc(value) {{
      return String(value ?? "").replace(/[&<>"']/g, ch => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }}[ch]));
    }}
    function fmt(value, digits = 3) {{
      if (value === null || value === undefined || value === "") return "";
      const num = Number(value);
      if (!Number.isFinite(num)) return esc(value);
      return num.toFixed(digits).replace(/\\.0+$/, "").replace(/(\\.\\d*?)0+$/, "$1");
    }}
    function bandClass(value) {{
      const text = String(value || "").toLowerCase().replace("+", "p");
      if (!text) return "";
      if (text === "n/r") return "band-nr";
      if (text === "no_data" || text === "not_covered") return "band-no";
      return "band-" + text.replace(/[^a-z0-9]+/g, "");
    }}
    function badge(text, cls = "") {{
      return `<span class="badge ${{cls}}">${{esc(text)}}</span>`;
    }}
    function matches(row) {{
      const q = controls.search.value.trim().toLowerCase();
      const minScore = Number(controls.minScore.value);
      if (controls.profile.value && row.profile_id !== controls.profile.value) return false;
      if (controls.tenure.value && row.tenure !== controls.tenure.value) return false;
      if (controls.eligible.value && String(row.eligible) !== controls.eligible.value) return false;
      if (q && !String(row.estate).toLowerCase().includes(q)) return false;
      if (Number.isFinite(minScore) && controls.minScore.value !== "" && Number(row.profile_score ?? -1) < minScore) return false;
      return true;
    }}
    function renderSummary() {{
      document.getElementById("summary").innerHTML = summary.map(item => `
        <article class="tile">
          <strong>${{esc(item.profile_id)}}</strong>
          <div class="tile-row"><span>Eligible</span><span>${{item.eligible}} / ${{item.rows}}</span></div>
          <div class="tile-row"><span>Top</span><span>${{esc(item.top_estate || "")}} ${{item.top_tenure ? "(" + esc(item.top_tenure) + ")" : ""}}</span></div>
          <div class="tile-row"><span>Score</span><span>${{fmt(item.top_score)}}</span></div>
        </article>
      `).join("");
    }}
    function renderRows() {{
      const filtered = rows.filter(matches).sort((a, b) => {{
        if (a.eligible !== b.eligible) return a.eligible ? -1 : 1;
        if (a.profile_id !== b.profile_id) return a.profile_id.localeCompare(b.profile_id);
        const ar = a.rank ?? 99999;
        const br = b.rank ?? 99999;
        if (ar !== br) return ar - br;
        return String(a.estate).localeCompare(String(b.estate));
      }});
      countLine.textContent = `${{filtered.length}} of ${{rows.length}} rows shown`;
      tbody.innerHTML = filtered.map(row => `
        <tr>
          <td>${{esc(row.profile_id)}}</td>
          <td class="num">${{row.rank ?? ""}}</td>
          <td><strong>${{esc(row.estate)}}</strong><div class="muted">Archetype ${{esc(row.archetype || "")}}</div></td>
          <td>${{badge(row.tenure, "seg")}}</td>
          <td>${{row.eligible ? badge("eligible", "ok") : badge("filtered", "no")}}</td>
          <td class="num">${{fmt(row.profile_score)}}</td>
          <td><span class="${{bandClass(row.liveability_band)}}">${{esc(row.liveability_band)}}</span><div class="muted">${{fmt(row.liveability_score)}}</div></td>
          <td><span class="${{bandClass(row.value_band)}}">${{esc(row.value_band)}}</span><div class="muted">${{fmt(row.value_score)}}</div></td>
          <td><span class="${{bandClass(row.employment_band)}}">${{esc(row.employment_band)}}</span><div class="muted">${{fmt(row.employment_score)}}</div></td>
          <td><span class="${{bandClass(row.lease_band)}}">${{esc(row.lease_band)}}</span><div class="muted">${{fmt(row.lease_score)}}</div></td>
          <td><span class="${{bandClass(row.provision_band)}}">${{esc(row.provision_band)}}</span><div class="muted">${{fmt(row.provision_score)}}</div></td>
          <td>${{esc(row.value_basis)}}<div class="muted">n=${{fmt(row.value_n, 0)}}</div></td>
          <td class="reason">${{esc(row.filter_reasons || "")}}</td>
        </tr>
      `).join("");
    }}
    Object.values(controls).forEach(el => el.addEventListener("input", renderRows));
    document.getElementById("resetBtn").addEventListener("click", () => {{
      Object.values(controls).forEach(el => el.value = "");
      renderRows();
    }});
    renderSummary();
    renderRows();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate buyer profile HTML table")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    rows = load_rows(pathlib.Path(args.input))
    html_text = render_html(rows, date.today().isoformat())
    pathlib.Path(args.out).write_text(html_text, encoding="utf-8")
    print(f"gen_buyer_profile_html: wrote {len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
