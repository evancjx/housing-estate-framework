"""Public directory of the latest property analyses, grouped by postal district."""

from __future__ import annotations

from collections import Counter, defaultdict
from html import escape

from sg_estate.reporting.property_analysis import PropertyAnalysis, latest_property_analyses

DIRECTORY_PATH = "property-analyses.html"
UNKNOWN_SECTION = "unknown"

# Must equal DISTRICT_NAMES in index.html (tests/test_property_directory.py enforces it).
DISTRICT_NAMES = {
    "01": "Boat Quay · Raffles Place · Marina", "02": "Chinatown · Tanjong Pagar",
    "03": "Alexandra · Queenstown", "04": "HarbourFront · Telok Blangah",
    "05": "Buona Vista · West Coast", "06": "City Hall · Clarke Quay", "07": "Beach Road · Bugis",
    "08": "Farrer Park · Serangoon Road", "09": "Orchard · River Valley", "10": "Tanglin · Holland",
    "11": "Newton · Novena", "12": "Balestier · Toa Payoh", "13": "Macpherson · Potong Pasir",
    "14": "Eunos · Geylang · Paya Lebar", "15": "East Coast · Marine Parade",
    "16": "Bedok · Upper East Coast", "17": "Changi · Loyang · Pasir Ris", "18": "Pasir Ris · Tampines",
    "19": "Hougang · Punggol · Sengkang", "20": "Ang Mo Kio · Bishan",
    "21": "Clementi · Upper Bukit Timah", "22": "Boon Lay · Jurong · Tuas",
    "23": "Bukit Batok · Choa Chu Kang", "24": "Lim Chu Kang · Tengah", "25": "Admiralty · Woodlands",
    "26": "Lentor · Upper Thomson", "27": "Sembawang · Yishun", "28": "Seletar · Yio Chu Kang",
}


def normalize_name(value: str) -> str:
    return " ".join(value.split()).upper()


def stage_label(stage: str) -> str:
    if stage == "unverified":
        return "Stage not verified"
    return stage[:1].upper() + stage[1:]


def directory_entries(analyses: list[PropertyAnalysis], project_catalog: dict) -> list[dict]:
    """One entry per latest analysis, with the district the project finder uses."""
    districts = {normalize_name(p["name"]): str(p.get("district") or "")
                 for p in project_catalog.get("projects", [])}
    entries = []
    for analysis in latest_property_analyses(analyses):
        district = districts.get(normalize_name(analysis.project_name), "")
        entries.append({
            "name": analysis.project_name,
            "path": analysis.output_path,
            "stage": analysis.market_stage,
            "stage_label": stage_label(analysis.market_stage),
            "date_label": analysis.date_label,
            "captured_iso": analysis.captured_iso,
            "district": district if district in DISTRICT_NAMES else "",
        })
    return sorted(entries, key=lambda e: (e["name"].casefold(), e["path"]))


def _row(entry: dict) -> str:
    district = entry["district"]
    # Name and district name only: stages have chips, and codes match whole (data-district).
    search = " ".join(filter(None, (entry["name"], DISTRICT_NAMES.get(district, "")))).lower()
    return (
        f'<li data-stage="{escape(entry["stage"], quote=True)}" data-district="{escape(district, quote=True)}" '
        f'data-search="{escape(search, quote=True)}">'
        f'<a href="{escape(entry["path"], quote=True)}">{escape(entry["name"])}</a>'
        f'<span class="stage">{escape(entry["stage_label"])}</span>'
        f'<time datetime="{escape(entry["captured_iso"], quote=True)}">{escape(entry["date_label"])}</time>'
        "</li>"
    )


def _section(section_id: str, title: str, entries: list[dict]) -> str:
    rows = "".join(_row(entry) for entry in entries)
    return (
        f'<details class="district" id="{section_id}">'
        f'<summary><span class="title">{escape(title)}</span><span class="count">{len(entries)}</span></summary>'
        f"<ul>{rows}</ul></details>"
    )


def _latest(entries: list[dict]) -> dict | None:
    return max(entries, key=lambda e: e["captured_iso"]) if entries else None


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Every dated property analysis, searchable by project name and grouped by postal district.">
<title>Property analyses by district</title>
<link rel="stylesheet" href="assets/research-shell.css">
<link rel="stylesheet" href="assets/property-analysis.css">
<style>
.pd-controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:28px 0 10px; }
#directory-search { flex:1 1 280px; padding:12px 15px; border:1px solid var(--pa-line); border-radius:12px;
  background:#fff; color:var(--pa-ink); font:inherit; font-size:14px; }
#directory-search:focus { outline:3px solid var(--pa-teal-soft); border-color:var(--pa-teal); }
.chip { padding:7px 11px; border:1px solid var(--pa-line); border-radius:999px; background:#fff;
  color:var(--pa-muted); font:inherit; font-size:11px; font-weight:800; cursor:pointer; }
.chip:hover { color:var(--pa-teal-dark); }
.chip[aria-pressed="true"] { border-color:var(--pa-teal); background:var(--pa-teal-soft); color:var(--pa-teal-dark); }
.chip span { color:var(--pa-muted); font-weight:700; }
#directory-status { margin:0; color:var(--pa-muted); font-size:12px; }
.pd-sections { margin-top:24px; }
details.district { margin:0 0 10px; border:1px solid var(--pa-line); border-radius:16px; background:#fff;
  box-shadow:0 10px 30px rgba(23,50,40,.05); }
details.district summary { display:flex; gap:12px; align-items:center; padding:15px 18px; cursor:pointer;
  font-weight:800; list-style:none; }
details.district summary::-webkit-details-marker { display:none; }
details.district summary::before { content:"▸"; color:var(--pa-teal); }
details.district[open] > summary::before { content:"▾"; }
details.district summary .title { flex:1; }
details.district .count { padding:3px 9px; border-radius:999px; background:var(--pa-teal-soft);
  color:var(--pa-teal-dark); font-size:11px; }
details.district ul { list-style:none; margin:0; padding:0 18px 12px; }
details.district li { display:grid; grid-template-columns:1fr auto auto; gap:4px 16px; align-items:baseline;
  padding:9px 0; border-top:1px solid var(--pa-line); font-size:14px; }
details.district li a { color:var(--pa-teal-dark); font-weight:700; text-decoration:none; }
details.district li a:hover { text-decoration:underline; }
details.district .stage, details.district time { color:var(--pa-muted); font-size:11px; font-weight:700; }
@media (max-width:560px) { details.district li { grid-template-columns:1fr auto; }
  details.district li a { grid-column:1 / -1; } }
.empty-state { color:var(--pa-muted); }
</style>
</head>
<body class="property-analysis-page">
<main id="research-content">
<header class="pa-hero">
<a class="pa-kicker" href="index.html#reports">Research library</a>
<div class="pa-badges"><span>Point-in-time research</span><span>Grouped by postal district</span></div>
<h1>__HEADING__</h1>
<p class="pa-summary">__LEAD__</p>
<div class="pd-controls">
<input id="directory-search" type="search" placeholder="Project name or district, e.g. poiz, d27, sembawang" aria-label="Filter property analyses">
__CHIPS__
</div>
<p id="directory-status" aria-live="polite"></p>
</header>
<section class="pd-sections" aria-label="Property analyses by postal district">
__SECTIONS__
</section>
</main>
<script>
(() => {
  const input = document.getElementById("directory-search");
  const status = document.getElementById("directory-status");
  const chips = Array.from(document.querySelectorAll(".chip"));
  const sections = Array.from(document.querySelectorAll("details.district"));
  const total = document.querySelectorAll("details.district li").length;
  let stage = "";
  function apply() {
    const query = input.value.trim().toLowerCase();
    const code = /^d?\s*(\d{1,2})$/.exec(query);
    const want = code ? code[1].padStart(2, "0") : "";
    let shown = 0, last = null;
    sections.forEach(section => {
      let visible = 0;
      section.querySelectorAll("li").forEach(row => {
        const matches = code ? row.dataset.district === want : row.dataset.search.includes(query);
        const ok = (!query || matches) && (!stage || row.dataset.stage === stage);
        row.hidden = !ok;
        if (ok) { visible += 1; last = row; }
      });
      section.querySelector(".count").textContent = visible;
      section.hidden = visible === 0;
      if (query || stage) section.open = visible > 0;
      shown += visible;
    });
    status.textContent = (query || stage) ? `${shown} of ${total} analyses` : `${total} analyses`;
    return shown === 1 ? last : null;
  }
  input.addEventListener("input", apply);
  input.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    const only = apply();
    if (only) window.location.href = only.querySelector("a").href;
  });
  chips.forEach(chip => chip.addEventListener("click", () => {
    stage = stage === chip.dataset.stage ? "" : chip.dataset.stage;
    chips.forEach(other => other.setAttribute("aria-pressed", String(other.dataset.stage === stage)));
    apply();
  }));
  function openHash() {
    const target = location.hash && document.getElementById(location.hash.slice(1));
    if (target && target.tagName === "DETAILS") { target.open = true; target.scrollIntoView(); }
  }
  window.addEventListener("hashchange", openHash);
  openHash();
  apply();
})();
</script>
</body>
</html>
"""


def render_directory_page(entries: list[dict]) -> str:
    by_district: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        by_district[entry["district"]].append(entry)
    sections = [
        _section(f"d{code}", f"D{code} · {name}", by_district[code])
        for code, name in DISTRICT_NAMES.items() if code in by_district
    ]
    if "" in by_district:
        sections.append(_section(UNKNOWN_SECTION, "District not known", by_district[""]))
    stages = Counter(entry["stage"] for entry in entries)
    chips = "\n".join(
        f'<button type="button" class="chip" data-stage="{escape(stage, quote=True)}" aria-pressed="false">'
        f"{escape(stage_label(stage))} <span>{count}</span></button>"
        for stage, count in sorted(stages.items(), key=lambda item: (-item[1], item[0]))
    )
    latest = _latest(entries)
    if latest is None:
        heading, lead = "No project analyses published yet", "Dated project analyses will be listed here."
    else:
        heading = f"{len(entries)} property analyses"
        lead = (f"Latest captured {latest['date_label']}. Each is a dated, point-in-time snapshot of "
                "one project, grouped by postal district.")
    body = "\n".join(sections) or '<p class="empty-state">No project analyses published yet.</p>'
    replacements = {"__HEADING__": escape(heading), "__LEAD__": escape(lead),
                    "__CHIPS__": chips, "__SECTIONS__": body}
    page = PAGE
    for token, value in replacements.items():
        page = page.replace(token, value)
    return page


def summary_card(entries: list[dict]) -> str:
    """The single home-grid card that replaces one card per analysis."""
    latest = _latest(entries)
    if latest is None:
        heading = "No project analyses published yet"
        body = "Dated project analyses will be listed by postal district."
    else:
        heading = f"Browse {len(entries)} project analyses by district"
        body = f"Latest captured {latest['date_label']}. Each is a dated snapshot."
    return "\n".join((
        '      <a class="card property-analysis-card" data-kind="analysis project" '
        'data-search="property analysis property analyses directory district project" '
        f'href="{DIRECTORY_PATH}">',
        f'        <span class="tag">Property analyses</span><h3>{escape(heading)}</h3>',
        f"        <p>{escape(body)}</p>",
        '        <span class="open">Open the property analysis directory →</span>',
        "      </a>",
    ))


def directory_catalog_entry() -> dict:
    return {
        "id": "property-analysis-directory",
        "path": DIRECTORY_PATH,
        "title": "Property analyses by district",
        "category": "property-analysis",
        "kind": "property-analysis-directory",
        "summary": "Every latest dated project analysis, searchable by name and grouped by postal district.",
        "tags": ["private property", "property analysis", "directory", "district"],
    }
