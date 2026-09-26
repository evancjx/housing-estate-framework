# Property Analysis Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Replace the 563 per-analysis cards on the Pages home grid with one summary card.
- Add a generated `property-analyses.html` directory that is searchable and grouped by postal
  district.
- Make the home finder surface analyses directly.

**Architecture:**
- A new pure module, `sg_estate/reporting/property_directory.py`, builds directory entries, the
  directory page and the summary card from the latest analyses and the finder's project index.
- `scripts/build_pages_site.py` writes the page, swaps the cards marker for the summary card,
  catalogues the page, and adds each project's latest analysis link to `projects.json`.
- `index.html` gets small finder changes.

**Tech Stack:** Python 3.11+, stdlib `html.escape`, pytest, and vanilla JavaScript in a static
page.

**Spec:** `docs/superpowers/specs/2026-09-26-property-analysis-directory-design.md`

## Global Constraints

- Existing analysis URLs `property-analysis-<date>-<slug>.html` do not change.
- The directory page lives at `property-analyses.html`. It is generated into the site output and is
  never a root file. Its catalogue `kind` is `"property-analysis-directory"`.
- The district for each analysis comes from the finder's project index (`build_project_catalog` plus
  `add_report_projects`), joined on the whitespace-normalised, upper-cased project name. Codes
  outside `"01"`–`"28"` count as unknown.
- A section with no known district has `id="unknown"` and the label "District not known". An
  analysis is never dropped and never given a guessed district.
- The `unverified` stage is labelled "Stage not verified". Other stages capitalise their first
  letter only ("new launch" → "New launch").
- The summary-card body reads "Latest captured <DD Mon YYYY>. Each is a dated snapshot.". The empty
  heading reads "No project analyses published yet".
- Python `DISTRICT_NAMES` must equal the `DISTRICT_NAMES` object in `index.html`.
- The directory works without JavaScript: `<details>` sections and plain links.
- No new dependencies.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Project names with `&`, `<`, `"` or `@`** (for example "Optima @ Tanah Merah"): they must be
   escaped in rows, the summary card and data attributes. Tested in Task 1
   (`test_directory_escapes_project_names`).
2. **Two latest analyses with the same display name but different slugs:** both are listed, and
   neither is dropped. Tested in Task 1 (`test_directory_keeps_same_named_analyses`).
3. **Index district values outside D01–D28** (`""`, `"29"`, `"0"`): the analysis goes to "District
   not known". Tested in Task 1 (`test_directory_unknown_for_out_of_range_district`).
4. **A `#dNN` link for a district with no analyses:** no section exists, and the page must not throw
   when opening the hash. Tested in Task 1 (`test_directory_script_guards_missing_hash_target`).
5. **`projects.json` failing to load:** the finder falls back to its built-in list, which has no
   `analysis` field, and must not throw. Tested in Task 3 (`test_finder_tolerates_projects_without_analysis`).

---

### Task 1: Directory module (`sg_estate/reporting/property_directory.py`)

**Files:**
- Create: `sg_estate/reporting/property_directory.py`
- Test: `tests/test_property_directory.py`

**Interfaces:**
- Consumes:
  - `sg_estate.reporting.property_analysis.PropertyAnalysis`, with `project_name`, `output_path`,
    `market_stage`, `date_label` and `captured_iso`.
  - `latest_property_analyses(analyses) -> list[PropertyAnalysis]`.
- Produces:
  - `DIRECTORY_PATH = "property-analyses.html"`
  - `DISTRICT_NAMES: dict[str, str]` (keys `"01"`–`"28"`)
  - `normalize_name(value: str) -> str`
  - `stage_label(stage: str) -> str`
  - `directory_entries(analyses, project_catalog: dict) -> list[dict]`. Each dict has the keys
    `name`, `path`, `stage`, `stage_label`, `date_label`, `captured_iso` and `district` (a
    two-digit code, or `""`).
  - `render_directory_page(entries: list[dict]) -> str`
  - `summary_card(entries: list[dict]) -> str`
  - `directory_catalog_entry() -> dict`

- [ ] **Step 1: Write the failing tests**

`tests/test_property_directory.py`:

```python
"""Property-analysis directory: district grouping, labels, escaping and the home summary card."""

import re
from pathlib import Path

import pytest

from sg_estate.reporting.property_analysis import parse_property_analysis
from sg_estate.reporting.property_directory import (
    DIRECTORY_PATH,
    DISTRICT_NAMES,
    directory_catalog_entry,
    directory_entries,
    render_directory_page,
    stage_label,
    summary_card,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture
def analysis(tmp_path):
    def create(project, slug, *, stage="resale", date="2026-09-20"):
        source = tmp_path / f"{date}-{slug}.md"
        source.write_text(
            f"# {project} — property analysis\n\n"
            f"Research captured: **{date} 12:00:00 SGT (UTC+08:00)**  \n"
            f"Property: **{project}, Singapore**  \n"
            "Analysis type: **individual project evidence**  \n"
            "Status: **point-in-time market snapshot**  \n"
            f"Market stage: **{stage}**\n\n"
            "## Decision\n\nNo executable offer has been verified.\n",
            encoding="utf-8",
        )
        return parse_property_analysis(source)

    return create


def _catalog(*pairs):
    return {"projects": [{"name": n, "slug": n.lower().replace(" ", "-"), "district": d} for n, d in pairs]}


def test_stage_labels():
    assert stage_label("unverified") == "Stage not verified"
    assert stage_label("new launch") == "New launch"
    assert stage_label("resale") == "Resale"


def test_entries_take_district_from_the_project_index(analysis):
    entries = directory_entries(
        [analysis("Canberra Crescent Residences", "canberra-crescent-residences", stage="new launch")],
        _catalog(("CANBERRA  CRESCENT RESIDENCES", "27")),
    )
    assert entries == [{
        "name": "Canberra Crescent Residences",
        "path": "property-analysis-2026-09-20-canberra-crescent-residences.html",
        "stage": "new launch",
        "stage_label": "New launch",
        "date_label": "20 Sep 2026",
        "captured_iso": entries[0]["captured_iso"],
        "district": "27",
    }]


def test_directory_unknown_for_out_of_range_district(analysis):
    reports = [analysis("Alpha", "alpha"), analysis("Beta", "beta"), analysis("Gamma", "gamma")]
    entries = directory_entries(reports, _catalog(("ALPHA", ""), ("BETA", "29"), ("GAMMA", "0")))
    assert {e["district"] for e in entries} == {""}
    page = render_directory_page(entries)
    assert re.search(r'<details class="district" id="unknown">.*Alpha.*Beta.*Gamma.*</details>', page, re.S)


def test_page_groups_rows_by_district_in_numeric_order_with_counts(analysis):
    reports = [analysis("Zeta Park", "zeta-park"), analysis("Alpha Court", "alpha-court"),
               analysis("Beta Lodge", "beta-lodge"), analysis("Lost Place", "lost-place")]
    page = render_directory_page(directory_entries(
        reports, _catalog(("ZETA PARK", "27"), ("ALPHA COURT", "27"), ("BETA LODGE", "09"))))
    assert page.index('id="d09"') < page.index('id="d27"') < page.index('id="unknown"')
    d27 = page[page.index('id="d27"'):page.index("</details>", page.index('id="d27"'))]
    assert "D27 · Sembawang · Yishun" in d27 and '<span class="count">2</span>' in d27
    assert d27.index("Alpha Court") < d27.index("Zeta Park")
    assert 'id="d01"' not in page
    assert page.count('href="property-analysis-') == 4
    assert "<details" in page and " open" not in page.split("<main", 1)[1].split("<script", 1)[0]


def test_page_rows_carry_stage_and_date(analysis):
    page = render_directory_page(directory_entries(
        [analysis("Pinery Residences", "pinery-residences", stage="unverified", date="2026-08-08")],
        _catalog(("PINERY RESIDENCES", "20"))))
    assert 'data-stage="unverified"' in page
    assert ">Stage not verified<" in page
    assert ">08 Aug 2026<" in page
    assert 'data-stage="unverified" aria-pressed="false">Stage not verified <span>1</span>' in page


def test_directory_escapes_project_names():
    entry = {"name": 'Optima @ Tanah Merah & "Co" <x>', "path": "property-analysis-2026-09-20-optima.html",
             "stage": "resale", "stage_label": "Resale", "date_label": "20 Sep 2026",
             "captured_iso": "2026-09-20T12:00:00+08:00", "district": ""}
    page = render_directory_page([entry])
    assert "<x>" not in page
    assert "Optima @ Tanah Merah &amp; &quot;Co&quot; &lt;x&gt;" in page


def test_directory_keeps_same_named_analyses(analysis):
    entries = directory_entries(
        [analysis("Twin Tower", "twin-tower"), analysis("Twin Tower", "twin-tower-2")], {"projects": []})
    assert len(entries) == 2
    assert render_directory_page(entries).count(">Twin Tower<") == 2


def test_directory_script_guards_missing_hash_target():
    page = render_directory_page([])
    assert 'document.getElementById(location.hash.slice(1))' in page
    assert 'target && target.tagName === "DETAILS"' in page


def test_empty_directory_and_card():
    assert "No project analyses published yet" in render_directory_page([])
    card = summary_card([])
    assert "No project analyses published yet" in card
    assert f'href="{DIRECTORY_PATH}"' in card


def test_summary_card_counts_latest_and_links_directory(analysis):
    entries = directory_entries([analysis("A One", "a-one", date="2026-08-08"),
                                 analysis("B Two", "b-two", date="2026-09-26")], {"projects": []})
    card = summary_card(entries)
    assert card.count('<a class="card property-analysis-card"') == 1
    assert "Browse 2 project analyses by district" in card
    assert "Latest captured 26 Sep 2026. Each is a dated snapshot." in card
    assert 'data-kind="analysis project"' in card and "property analysis" in card


def test_catalog_entry_shape():
    entry = directory_catalog_entry()
    assert entry["path"] == DIRECTORY_PATH
    assert entry["kind"] == "property-analysis-directory"
    assert {"id", "path", "title", "category", "kind", "summary", "tags"} <= set(entry)


def test_python_district_names_match_index_html():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const DISTRICT_NAMES = \{(.*?)\};", source, re.S).group(1)
    js = dict(re.findall(r'"(\d{2})":"([^"]*)"', block))
    assert js == DISTRICT_NAMES
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_property_directory.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sg_estate.reporting.property_directory'`.

- [ ] **Step 3: Implement `sg_estate/reporting/property_directory.py`**

```python
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
    search = " ".join(filter(None, (
        entry["name"],
        f"d{district} {district} {DISTRICT_NAMES[district]}" if district else "",
        entry["stage_label"],
    ))).lower()
    return (
        f'<li data-stage="{escape(entry["stage"], quote=True)}" data-search="{escape(search, quote=True)}">'
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


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Property analyses by district</title>
<style>
:root { --bg:#fff; --fg:#1b1f24; --muted:#5b6470; --line:#d9dee4; --soft:#f3f5f7; --accent:#1f5fbf; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#15181c; --fg:#e6e9ed; --muted:#9aa4b0; --line:#2c3239; --soft:#1d2126; --accent:#7fb0ff; }
}
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px 48px; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width:860px; margin:0 auto; }
h1 { font-size:24px; margin:0 0 4px; }
.lead { color:var(--muted); margin:0 0 18px; }
.lead a { color:var(--accent); }
.controls { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 8px; }
#directory-search { flex:1 1 260px; font:inherit; padding:9px 12px; border:1px solid var(--line);
  border-radius:8px; background:var(--bg); color:var(--fg); }
.chip { font:inherit; font-size:13px; padding:6px 10px; border:1px solid var(--line); border-radius:999px;
  background:var(--soft); color:var(--fg); cursor:pointer; }
.chip[aria-pressed="true"] { border-color:var(--accent); color:var(--accent); }
.chip span { color:var(--muted); }
#directory-status { color:var(--muted); font-size:13px; margin:0 0 12px; }
details.district { border:1px solid var(--line); border-radius:10px; margin:0 0 8px; }
details.district summary { display:flex; justify-content:space-between; gap:12px; padding:10px 14px;
  cursor:pointer; font-weight:600; }
details.district .count { color:var(--muted); font-weight:400; }
details.district ul { list-style:none; margin:0; padding:0 14px 10px; }
details.district li { display:grid; grid-template-columns:1fr auto auto; gap:4px 14px; padding:7px 0;
  border-top:1px solid var(--line); font-size:14px; }
details.district li a { color:var(--accent); }
details.district .stage, details.district time { color:var(--muted); font-size:13px; }
@media (max-width:520px) { details.district li { grid-template-columns:1fr auto; }
  details.district li a { grid-column:1 / -1; } }
.empty-state { color:var(--muted); }
</style>
</head>
<body>
<main>
<h1>__HEADING__</h1>
<p class="lead">__LEAD__ <a href="index.html">Back to the research library</a>.</p>
<div class="controls">
<input id="directory-search" type="search" placeholder="Project name or district, e.g. poiz, d27, sembawang" aria-label="Filter property analyses">
__CHIPS__
</div>
<p id="directory-status" aria-live="polite"></p>
__SECTIONS__
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
    let shown = 0, last = null;
    sections.forEach(section => {
      let visible = 0;
      section.querySelectorAll("li").forEach(row => {
        const ok = (!query || row.dataset.search.includes(query)) && (!stage || row.dataset.stage === stage);
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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_property_directory.py -q`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add sg_estate/reporting/property_directory.py tests/test_property_directory.py
git commit -m "feat(pages): build a district-grouped property analysis directory

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Build integration (`scripts/build_pages_site.py`)

**Files:**
- Modify: `scripts/build_pages_site.py`. This touches the imports, `_prepare_property_publication`,
  `_property_cards` (removed), `inject_property_library` and `build_site`, and adds
  `add_analysis_links`.
- Modify: `tests/test_property_analysis_pages.py`, in the seven tests that call `_property_cards`.
- Modify: `tests/test_pages_site.py`, in `test_pages_builder_packages_reports_catalog_and_assets`.
- Test: `tests/test_pages_site.py` (new tests appended).

**Interfaces:**
- Consumes (Task 1): `DIRECTORY_PATH`, `directory_entries`, `render_directory_page`,
  `summary_card`, `directory_catalog_entry` and `normalize_name`.
- Produces:
  - `build_pages_site.add_analysis_links(catalog: dict, analyses) -> dict`. It returns a new catalog
    in which each project whose normalised name matches a latest analysis gains
    `"analysis": {"path": str, "date": str}`.
  - `inject_property_library(index_path, analyses)`: the signature is unchanged. It now writes the
    summary card.
  - The built site contains `property-analyses.html`, and its `reports.json` includes the directory
    entry.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pages_site.py`:

```python
def test_analysis_links_are_added_to_matching_projects_only(parsed_report):
    catalog = {"projects": [
        {"name": "LUCERNE  GRAND", "slug": "lucerne-grand", "district": "18"},
        {"name": "OTHER", "slug": "other"},
    ]}
    older = parsed_report("Lucerne Grand", "lucerne-grand", date="2026-08-08")
    newest = parsed_report("Lucerne Grand", "lucerne-grand", date="2026-09-20")

    # Discovery order is newest first; latest_property_analyses keeps the first per slug.
    updated = build_pages_site.add_analysis_links(catalog, [newest, older])

    assert updated["projects"][0]["analysis"] == {
        "path": "property-analysis-2026-09-20-lucerne-grand.html", "date": "20 Sep 2026"}
    assert "analysis" not in updated["projects"][1]
    assert "analysis" not in catalog["projects"][0]


def test_home_library_gets_one_summary_card_not_one_card_per_analysis(parsed_report, tmp_path):
    index_copy = tmp_path / "index.html"
    index_copy.write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    reports = [parsed_report("Alpha One", "alpha-one"), parsed_report("Beta Two", "beta-two")]

    build_pages_site.inject_property_library(index_copy, reports)
    landing = index_copy.read_text(encoding="utf-8")

    assert landing.count('class="card property-analysis-card"') == 1
    assert "Browse 2 project analyses by district" in landing
    assert 'href="property-analyses.html"' in landing
    assert 'href="property-analysis-2026-09-20-alpha-one.html"' not in landing
    assert '"ALPHA ONE": "property-analysis-2026-09-20-alpha-one.html"' in landing


def test_directory_path_collision_with_catalog_is_rejected():
    catalog = {"reports": [{"id": "x", "path": "property-analyses.html"}]}
    with pytest.raises(ValueError, match="property-analyses.html"):
        build_pages_site._prepare_property_publication(
            catalog, property_analysis_dir=ROOT / "property_analysis")
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_pages_site.py -q -k "analysis_links or summary_card or directory_path_collision"`
Expected: 3 failed. One with `AttributeError: ... no attribute 'add_analysis_links'`, and two with
assertion failures.

- [ ] **Step 3: Implement the build changes**

In `scripts/build_pages_site.py`:

a) Imports: after the `from sg_estate.reporting.property_analysis import (...)` block, add:

```python
from sg_estate.reporting.property_directory import (
    DIRECTORY_PATH,
    directory_catalog_entry,
    directory_entries,
    normalize_name,
    render_directory_page,
    summary_card,
)
```

b) In `_prepare_property_publication`, directly after the `existing_paths = ...` line, add:

```python
    if DIRECTORY_PATH in existing_paths or (ROOT / DIRECTORY_PATH).exists():
        raise ValueError(
            f"Property analysis directory collides with an authored report: {DIRECTORY_PATH}"
        )
```

Then change the merged reports list so it includes the directory entry:

```python
    merged_catalog["reports"] = [
        *property_catalog_entries(analyses),
        directory_catalog_entry(),
        *catalog["reports"],
    ]
```

c) Delete the whole `_property_cards` function. Replace `inject_property_library` with:

```python
def inject_property_library(index_path: Path, analyses: list[PropertyAnalysis]) -> None:
    """Inject the single property-analysis summary card and exact project-finder routes."""

    source = index_path.read_text(encoding="utf-8")
    for marker in (PROPERTY_CARDS_MARKER, PROPERTY_ROUTES_MARKER):
        if source.count(marker) != 1:
            raise ValueError(
                f"{index_path.name} must contain exactly one publication marker {marker}"
            )
    card = summary_card(directory_entries(analyses, {"projects": []}))
    updated = source.replace(PROPERTY_CARDS_MARKER, card)
    updated = updated.replace(PROPERTY_ROUTES_MARKER, _property_routes(analyses))
    index_path.write_text(updated, encoding="utf-8")
```

d) Add after `add_report_projects`:

```python
def add_analysis_links(catalog: dict, analyses: list[PropertyAnalysis]) -> dict:
    """Give each finder project with a latest analysis a direct link and its capture date."""
    latest = {normalize_name(a.project_name): a for a in latest_property_analyses(analyses)}
    projects = []
    for project in catalog["projects"]:
        project = dict(project)
        analysis = latest.get(normalize_name(project["name"]))
        if analysis is not None:
            project["analysis"] = {"path": analysis.output_path, "date": analysis.date_label}
        projects.append(project)
    return {**catalog, "projects": projects}
```

e) In `build_site`, change the `project_catalog = ...` line to:

```python
    project_catalog = add_analysis_links(
        add_report_projects(build_project_catalog(), analyses), analyses
    )
```

Then, directly after the loop that writes `rendered_pages`, add:

```python
    (output_dir / DIRECTORY_PATH).write_text(
        render_directory_page(directory_entries(analyses, project_catalog)),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Update the tests that used `_property_cards`**

In `tests/test_property_analysis_pages.py`:
- Add the import
  `from sg_estate.reporting.property_directory import directory_entries, render_directory_page`.
- Apply the exact replacements below. Each "card" becomes the rendered directory row.

| Line (current) | Replace | With |
| --- | --- | --- |
| 234 | `assert "Property analysis · Mixed Market" in build_pages_site._property_cards([analysis])` | `assert ">Mixed market<" in render_directory_page(directory_entries([analysis], {"projects": []}))` |
| 256, 279, 298, 315, 357, 377 | `card = build_pages_site._property_cards([analysis])` | `card = render_directory_page(directory_entries([analysis], {"projects": []}))` |
| 260, 283, 361, 381 | `assert " new launch " in card` | `assert 'data-stage="new launch"' in card` |
| 261 | `assert " resale " not in card` | `assert 'data-stage="resale"' not in card` |
| 262, 302, 362, 382 | `assert "Property analysis · New Launch · 08 Aug 2026" in card` | `assert ">New launch<" in card and ">08 Aug 2026<" in card` |
| 284 | `assert "Property analysis · New Launch · 03 Aug 2026" in card` | `assert ">New launch<" in card and ">03 Aug 2026<" in card` |
| 319 | `assert "Property analysis · New Launch · 13 Aug 2026" in card` | `assert ">New launch<" in card and ">13 Aug 2026<" in card` |

In `tests/test_pages_site.py`, in `test_pages_builder_packages_reports_catalog_and_assets`:
- Change `assert count == source_count + len(analyses)` to
  `assert count == source_count + len(analyses) + 1`.
- Replace the block that starts at `future_card = next(` and runs through
  `assert " resale " not in future_card` with:

```python
        directory = (output / "property-analyses.html").read_text(encoding="utf-8")
        future_row = next(
            line
            for line in directory.split("<li ")
            if f'href="{latest_future["path"]}"' in line
        )
        assert latest_future["market_stage"] == "future project"
        assert 'data-stage="future project"' in future_row
        assert 'data-stage="resale"' not in future_row
        assert landing.count('class="card property-analysis-card"') == 1
        assert directory.count('href="property-analysis-') == len(
            latest_property_analyses(analyses)
        )
        assert any(r["kind"] == "property-analysis-directory" for r in merged_catalog["reports"])
        projects = json.loads((output / "projects.json").read_text(encoding="utf-8"))["projects"]
        assert any("analysis" in p for p in projects)
```

and add `from sg_estate.reporting.property_analysis import latest_property_analyses` to that file's
imports.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_pages_site.py tests/test_property_analysis_pages.py tests/test_property_directory.py -q`
Expected: all pass. `test_report_catalog_covers_every_root_report` may still fail on this machine
for the pre-existing untracked-file reason, so check any failure names only local untracked files.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_pages_site.py tests/test_pages_site.py tests/test_property_analysis_pages.py
git commit -m "feat(pages): replace per-analysis home cards with the district directory

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Home finder and library chip (`index.html`)

**Files:**
- Modify: `index.html`, in the filter chip (line ~225), the suggestion markup (line ~499),
  `updateCondoRoute` and `updateDistrictRoute`.
- Test: `tests/test_pages_site.py` (new tests appended).

**Interfaces:**
- Consumes (Task 2): each entry in `projects.json` may carry `analysis: {path, date}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pages_site.py`:

```python
def test_library_has_no_property_analysis_chip():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'data-filter="analysis"' not in source


def test_finder_offers_the_dated_analysis_and_district_directory():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "Analysis · ${escapeMarkup(project.analysis.date)}" in source
    assert "Open the ${escapeMarkup(analysis.date)} analysis" in source
    assert 'property-analyses.html#d${district}' in source


def test_finder_tolerates_projects_without_analysis():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "project.analysis ?" in source
    assert "project && project.analysis && project.analysis.path === " in source
    assert "p.analysis && " in source
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_pages_site.py -q -k "chip or finder_offers or finder_tolerates"`
Expected: 3 failed.

- [ ] **Step 3: Edit `index.html`**

a) Delete this line:

```html
      <button class="filter-chip" type="button" data-filter="analysis" aria-pressed="false">Property analyses</button>
```

b) In `renderSuggestions`, replace the `suggestions.innerHTML = matches.map(...)` template line with:

```js
      `<li role="option"><button type="button" data-index="${index}" data-name="${escapeMarkup(project.name)}">${escapeMarkup(project.name)}<small>${project.district ? `District ${String(project.district).padStart(2, "0")}` : "Project explorer"}${project.analysis ? ` · Analysis · ${escapeMarkup(project.analysis.date)}` : ""}</small></button></li>`
```

c) In `updateCondoRoute`, add this helper directly above the function:

```js
  function analysisLink(project, report) {
    const analysis = project && project.analysis && project.analysis.path === report ? project.analysis : null;
    return analysis
      ? `<a href="${escapeMarkup(analysis.path)}">Open the ${escapeMarkup(analysis.date)} analysis</a>, or use the broader explorer.`
      : `Dedicated project research is available. <a href="${report}">Open that report</a>, or use the broader explorer.`;
  }
```

Then replace the two existing assignments
``condoRoute.innerHTML = `Dedicated project research is available. <a href="${directReport}">Open that report</a>, or use the broader explorer.`;``
and
``condoRoute.innerHTML = `Dedicated project research is available. <a href="${report}">Open that report</a>, or use the broader explorer.`;``
with `condoRoute.innerHTML = analysisLink(project, directReport);` and
`condoRoute.innerHTML = analysisLink(project, report);` respectively.

d) In `updateDistrictRoute`, append just before its closing `}`:

```js
    const analysed = district
      ? projects.filter(p => p.analysis && String(p.district || "").padStart(2, "0") === district).length
      : 0;
    if (analysed) {
      districtRoute.insertAdjacentHTML("beforeend",
        ` <a href="property-analyses.html#d${district}">${analysed} property ${analysed === 1 ? "analysis" : "analyses"} in D${district} →</a>`);
    }
```

- [ ] **Step 4: Run the tests and check the page script's syntax**

Run: `python3 -m pytest tests/test_pages_site.py -q -k "chip or finder_offers or finder_tolerates" && python3 -c "import re;open('index-check.js','w').write(re.findall(r'<script>(.*?)</script>',open('index.html').read(),re.S)[-1])" && node --check index-check.js && rm index-check.js`
Expected: 3 passed, and `node --check` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add index.html tests/test_pages_site.py
git commit -m "feat(pages): surface dated analyses in the home finder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Full build check

- [ ] **Step 1: Build the site into an ignored in-repo directory and check it**

```bash
rm -rf data/runs/pages-check && python3 scripts/build_pages_site.py --out data/runs/pages-check
python3 - <<'EOF'
import json, re
root = "data/runs/pages-check"
page = open(f"{root}/property-analyses.html").read()
landing = open(f"{root}/index.html").read()
print("rows", page.count("<li data-stage"), "sections", len(re.findall(r'<details class="district"', page)),
      "unknown", 'id="unknown"' in page, "cards", landing.count('property-analysis-card"'))
projects = json.load(open(f"{root}/projects.json"))["projects"]
print("projects with analysis", sum("analysis" in p for p in projects))
EOF
```

Expected:
- The build prints "Built N research reports".
- `rows` equals the number of latest analyses (563 on 2026-09-26), and `unknown True`.
- `cards 1`, and "projects with analysis" is at least 549.

- [ ] **Step 2: Final gate**

Run: `make smoke`
Expected: pass. The only acceptable failure is the pre-existing catalog check that names untracked
local files (`data/inputs/bus_*.json`).

- [ ] **Step 3: Remove the check output**

Run: `rm -rf data/runs/pages-check`
