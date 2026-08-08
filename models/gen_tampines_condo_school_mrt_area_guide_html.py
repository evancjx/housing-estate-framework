#!/usr/bin/env python3
"""Generate the dated Tampines condo, school and MRT proximity area guide."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
from string import Template


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "tampines_condo_school_mrt_area_guide_2026-08-08.html"
CAPTURED = "2026-08-08 02:15:00 SGT (UTC+08:00)"
CANONICAL = (
    "https://evancjx.github.io/housing-estate-framework/"
    "tampines_condo_school_mrt_area_guide_2026-08-08.html"
)

# project, school status, school evidence, MRT status, MRT evidence, project note
PROJECTS = (
    (
        "Apollo Gardens",
        "yes",
        "Yes — Changkat Primary",
        "borderline",
        "Borderline — Upper Changi, about 5–7 minutes depending on block",
        "Completed apartment",
    ),
    (
        "Arc at Tampines",
        "yes",
        "Yes — St. Hilda's Primary",
        "no",
        "No",
        "EC-origin",
    ),
    (
        "Aurelle of Tampines",
        "yes",
        "Yes — Elias Park or Angsana Primary",
        "future",
        "No today — future CR6 Tampines North",
        "EC under construction",
    ),
    (
        "Cascadale",
        "yes",
        "Yes — East Spring Primary",
        "no",
        "No — Upper Changi is about 6–7 minutes",
        "Completed condominium",
    ),
    (
        "Changi Court",
        "borderline",
        "Borderline — East Spring is approximately at the 1 km cutoff",
        "yes",
        "Yes — Upper Changi, about 3–4 minutes",
        "Completed condominium",
    ),
    (
        "Changi Green",
        "yes",
        "Yes — East Spring Primary",
        "borderline",
        "Borderline — Upper Changi, about 5–6 minutes from the nearer side",
        "Completed condominium",
    ),
    (
        "Changi Rise Condominium",
        "yes",
        "Yes — East Spring Primary",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "CityLife@Tampines",
        "yes",
        "Yes — Angsana Primary",
        "no",
        "No — Tampines is about 7–11 minutes",
        "EC-origin",
    ),
    (
        "Double Bay Residences",
        "yes",
        "Yes — Changkat Primary",
        "no",
        "No — Simei is about 6–7 minutes",
        "Completed condominium",
    ),
    (
        "Eastpoint Green",
        "yes",
        "Yes — Changkat Primary",
        "no",
        "No — Simei is about 7–11 minutes by a usable route",
        "Completed condominium",
    ),
    (
        "Melville Park",
        "yes",
        "Yes — East Spring Primary",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "Modena",
        "yes",
        "Yes — Changkat Primary",
        "yes",
        "Yes — Simei, about 3–4 minutes",
        "Completed condominium",
    ),
    (
        "My Manhattan",
        "yes",
        "Yes — Changkat Primary",
        "yes",
        "Yes — Simei, about 1–3 minutes",
        "Completed condominium",
    ),
    (
        "Parc Central Residences",
        "yes",
        "Yes — Poi Ching School",
        "no",
        "No",
        "Executive condominium",
    ),
    (
        "ParkTown Residence",
        "yes",
        "Yes — Angsana Primary",
        "future",
        "No today — direct connection to future CR6 Tampines North",
        "Under construction",
    ),
    (
        "Pinery Residences",
        "yes",
        "Yes — Junyuan Primary",
        "yes",
        "Yes on completion — planned direct link to Tampines West, about 2–3 minutes",
        "Under construction",
    ),
    (
        "Pinevale",
        "yes",
        "Yes — Poi Ching School",
        "no",
        "No",
        "EC-origin",
    ),
    (
        "Q Bay Residences",
        "no",
        "No — St. Hilda's is slightly outside the modelled cutoff",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "Rivelle Tampines",
        "yes",
        "Yes — Junyuan Primary",
        "borderline",
        "Borderline — advertised near five minutes; mapped routes are closer to six",
        "EC under construction",
    ),
    (
        "Savannah Condopark",
        "yes",
        "Yes — East Spring Primary",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "Simei Green Condominium",
        "yes",
        "Yes — Changkat Primary",
        "borderline",
        "Borderline — Upper Changi, about 4–6 minutes depending on block and gate",
        "EC-origin",
    ),
    (
        "Sunbird View",
        "yes",
        "Yes — Changkat Primary",
        "no",
        "No — about seven minutes",
        "Completed apartment",
    ),
    (
        "Sunhaven",
        "yes",
        "Yes — East Spring Primary",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "The Alps Residences",
        "yes",
        "Yes — Poi Ching School",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "The Eden at Tampines",
        "yes",
        "Yes — East Spring Primary",
        "no",
        "No — Tampines East is about 6–8 minutes",
        "EC-origin",
    ),
    (
        "The Santorini",
        "yes",
        "Yes, block-dependent — Poi Ching or St. Hilda's near the cutoff",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "The Tampines Trilliant",
        "yes",
        "Yes — Angsana Primary",
        "no",
        "No — Tampines is about eight minutes",
        "EC-origin",
    ),
    (
        "The Tapestry",
        "yes",
        "Yes — Poi Ching School",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "The Tropica",
        "no",
        "No — St. Hilda's is just outside the modelled cutoff",
        "no",
        "No",
        "Completed condominium",
    ),
    (
        "Treasure at Tampines",
        "yes",
        "Yes — Changkat Primary",
        "no",
        "No — Simei is about eight minutes",
        "Completed condominium",
    ),
    (
        "Tropical Spring",
        "yes",
        "Yes — Changkat Primary",
        "yes",
        "Yes — Simei, about 4–5 minutes",
        "Completed condominium",
    ),
    (
        "Tropicana Condominium",
        "yes",
        "Yes, near cutoff — Changkat Primary",
        "yes",
        "Yes — Upper Changi, about one minute",
        "Completed condominium",
    ),
    (
        "Tenet",
        "yes",
        "Yes — Angsana Primary",
        "future",
        "No today — future CR6 Tampines North remains about six minutes",
        "Executive condominium",
    ),
    (
        "Waterview",
        "no",
        "No — the nearest primary school exceeds 1 km",
        "no",
        "No",
        "Completed condominium",
    ),
)


STATUS_LABELS = {
    "yes": "Yes",
    "borderline": "Borderline",
    "future": "Future only",
    "no": "No",
}


def _status_cell(status: str, evidence: str) -> str:
    return (
        f'<span class="status status-{escape(status)}">'
        f"{escape(STATUS_LABELS[status])}</span> "
        f"{escape(evidence)}"
    )


def table_rows() -> str:
    rows = []
    for project, school_status, school, mrt_status, mrt, note in PROJECTS:
        search = " ".join((project, school, mrt, note)).casefold()
        rows.append(
            "\n".join(
                (
                    f'<tr data-school="{escape(school_status)}" '
                    f'data-mrt="{escape(mrt_status)}" '
                    f'data-search="{escape(search, quote=True)}">',
                    f"  <th scope=\"row\">{escape(project)}"
                    f"<small>{escape(note)}</small></th>",
                    f"  <td>{_status_cell(school_status, school)}</td>",
                    f"  <td>{_status_cell(mrt_status, mrt)}</td>",
                    "</tr>",
                )
            )
        )
    return "\n".join(rows)


PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="A dated guide to 34 Tampines Planning Area condominium and EC projects, primary schools within 1 km and operational MRT walks of about five minutes.">
<link rel="canonical" href="$canonical">
<title>Tampines condominium, school and MRT area guide — 8 Aug 2026</title>
<style>
:root {
  color-scheme: light;
  --ink: #17202a;
  --muted: #576474;
  --line: #d9e0e7;
  --paper: #ffffff;
  --wash: #f4f7f9;
  --navy: #0b3954;
  --teal: #087e8b;
  --gold: #9a6700;
  --red: #9b2c2c;
  --green: #176b46;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--wash);
  color: var(--ink);
  font: 16px/1.6 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
a { color: #075985; }
a:hover { color: #0c4a6e; }
.page {
  width: min(1180px, calc(100% - 32px));
  margin: 32px auto 64px;
}
.hero {
  position: relative;
  overflow: hidden;
  padding: clamp(28px, 6vw, 64px);
  border-radius: 24px;
  color: #fff;
  background: linear-gradient(135deg, #082f49 0%, #0b5261 64%, #167d8d 100%);
  box-shadow: 0 18px 44px rgba(11, 57, 84, .22);
}
.hero::after {
  content: "";
  position: absolute;
  width: 280px;
  height: 280px;
  right: -90px;
  top: -120px;
  border: 42px solid rgba(255,255,255,.08);
  border-radius: 50%;
}
.eyebrow { font-size: .78rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
h1 { max-width: 850px; margin: 12px 0; font-size: clamp(2rem, 5vw, 4.3rem); line-height: 1.02; }
.hero p { max-width: 820px; margin: 0; color: #d7f2f3; font-size: 1.06rem; }
.captured { margin-top: 18px !important; font-size: .9rem !important; }
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 20px 0;
}
.stat, .panel {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(23, 32, 42, .05);
}
.stat { padding: 20px; }
.stat strong { display: block; color: var(--navy); font-size: 2rem; line-height: 1; }
.stat span { display: block; margin-top: 8px; color: var(--muted); font-size: .9rem; }
.panel { margin-top: 20px; padding: clamp(20px, 4vw, 38px); }
.panel h2 { margin: 0 0 12px; color: var(--navy); font-size: clamp(1.35rem, 3vw, 2rem); }
.panel h3 { margin: 28px 0 8px; color: var(--navy); }
.decision { border-left: 5px solid var(--teal); }
.notice {
  margin: 16px 0 0;
  padding: 14px 16px;
  border-radius: 12px;
  background: #fff8dd;
  border: 1px solid #ead69a;
  color: #5f4700;
}
.controls {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 12px;
  margin: 18px 0;
}
label { display: grid; gap: 5px; color: var(--muted); font-size: .82rem; font-weight: 700; }
input, select {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid #b9c4cf;
  border-radius: 10px;
  background: #fff;
  color: var(--ink);
  font: inherit;
}
.result-count { color: var(--muted); font-size: .92rem; }
.table-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 14px; }
table { width: 100%; min-width: 880px; border-collapse: collapse; background: #fff; }
th, td { padding: 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
thead th { position: sticky; top: 0; z-index: 1; background: #eaf1f4; color: var(--navy); font-size: .83rem; }
tbody th { width: 25%; color: var(--navy); }
tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #f8fbfc; }
small { display: block; margin-top: 3px; color: var(--muted); font-weight: 500; }
.status {
  display: inline-block;
  margin: 0 5px 4px 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: .76rem;
  font-weight: 800;
}
.status-yes { background: #dff5e9; color: var(--green); }
.status-borderline { background: #fff0c7; color: var(--gold); }
.status-future { background: #dceeff; color: #195a8a; }
.status-no { background: #fbe4e4; color: var(--red); }
.source-list li { margin: 7px 0; }
.footer { margin: 24px 0; color: var(--muted); font-size: .86rem; text-align: center; }
[hidden] { display: none !important; }
@media (max-width: 820px) {
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .controls { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .page { width: min(100% - 20px, 1180px); margin-top: 10px; }
  .hero, .panel { border-radius: 16px; }
  .stats { grid-template-columns: 1fr 1fr; gap: 9px; }
  .stat { padding: 14px; }
  .stat strong { font-size: 1.55rem; }
}
</style>
</head>
<body>
<main class="page">
  <header class="hero">
    <div class="eyebrow">Tampines Planning Area · dated area research</div>
    <h1>Condominiums, primary schools and five-minute MRT access</h1>
    <p>A boundary-controlled guide to completed condos, apartments, EC-origin projects and current launches—without folding Pasir Ris into Tampines.</p>
    <p class="captured">Research captured: $captured</p>
  </header>

  <section class="stats" aria-label="Headline findings">
    <article class="stat"><strong>34</strong><span>identified projects</span></article>
    <article class="stat"><strong>30</strong><span>indicative school matches</span></article>
    <article class="stat"><strong>6</strong><span>clear operational-MRT matches</span></article>
    <article class="stat"><strong>4</strong><span>borderline MRT cases</span></article>
  </section>

  <section class="panel decision">
    <h2>Decision</h2>
    <p>Primary-school proximity is common across Tampines private housing, but a defensible five-minute walk to an operational MRT entrance is scarce. The six clear cases are <strong>Changi Court, Pinery Residences, Modena, My Manhattan, Tropical Spring and Tropicana Condominium</strong>. Apollo Gardens, Changi Green, Rivelle Tampines and Simei Green Condominium are block- or gate-dependent and should not be advertised as project-wide five-minute walks without an exact route check.</p>
    <p class="notice"><strong>Screening guide:</strong> this is not an MOE Home-School Distance certificate, an LTA walking-time promise or a property valuation. Verify the exact block, postal code, project gate and station entrance before acting.</p>
  </section>

  <section class="panel">
    <h2>Scope</h2>
    <p>The scope is the official <strong>URA Tampines Planning Area</strong>, including Tampines, Simei and the Upper Changi/Xilin fringe. Pasir Ris is excluded even though many portals group it with Tampines inside postal District 18. The list includes completed private condos and apartments, EC-origin projects, current ECs and launched projects under construction.</p>
    <p>Inventory was reconciled against URA transaction and pipeline resources, the repository's captured project ledger, the official URA subzone polygon and OneMap address results. Landed housing, HDB estates and an unnamed low-confidence transaction placeholder are excluded.</p>
  </section>

  <section class="panel" id="project-table">
    <h2>All projects</h2>
    <div class="controls">
      <label>Search project or evidence
        <input id="search" type="search" placeholder="Try Simei, Poi Ching or Tampines West">
      </label>
      <label>Primary school
        <select id="school-filter">
          <option value="all">All results</option>
          <option value="yes">Yes</option>
          <option value="borderline">Borderline</option>
          <option value="no">No</option>
        </select>
      </label>
      <label>Operational MRT
        <select id="mrt-filter">
          <option value="all">All results</option>
          <option value="yes">Clear Yes</option>
          <option value="borderline">Borderline</option>
          <option value="future">Future station only</option>
          <option value="no">No</option>
        </select>
      </label>
    </div>
    <p class="result-count" id="result-count" aria-live="polite">Showing 34 of 34 projects.</p>
    <div class="table-wrap" role="region" aria-label="Tampines condo proximity table" tabindex="0">
      <table>
        <thead><tr><th scope="col">Project</th><th scope="col">Primary school within 1 km?</th><th scope="col">Operational MRT within about five minutes?</th></tr></thead>
        <tbody id="project-rows">
$table_rows
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <h2>How the tests work</h2>
    <h3>Primary school</h3>
    <p>The screening pass measures straight-line distance from reviewed project or residential-block coordinates to MOE school coordinates. A project receives Yes when at least one represented block falls within 1,000 m. MOE's official method is different: it measures the shortest distance from the School Land Boundary to the exact approved residential footprint. Use OneMap SchoolQuery for the applicable P1 exercise.</p>
    <p>Cutoff-sensitive projects include Changi Court, The Santorini, Tropicana Condominium, Q Bay Residences and The Tropica. School proximity affects admission priority, not guaranteed placement.</p>
    <h3>MRT walk</h3>
    <p>Only stations operational at the capture time count. Reviewed project/block coordinates were paired with OneMap entrance points and plausible routes were checked against pedestrian-network routing and public route cards. Five minutes is treated as an approximate usable route, not a circular 400 m radius.</p>
    <p>Future CR6 Tampines North is excluded until passenger service begins in 2030. Xilin was also excluded because LTA was still carrying out final Downtown Line extension integration tests ahead of its second-half-2026 opening.</p>
  </section>

  <section class="panel">
    <h2>Buyer verification sequence</h2>
    <ol>
      <li>Confirm the exact residential block and postal code.</li>
      <li>Check OneMap SchoolQuery for the relevant P1 registration exercise.</li>
      <li>Confirm the station is operational on LTA's current rail map.</li>
      <li>Time the walk from the actual residential gate to the intended station entrance.</li>
    </ol>
  </section>

  <section class="panel">
    <h2>Sources and limitations</h2>
    <ul class="source-list">
      <li><a href="https://data.gov.sg/datasets/d_8594ae9ff96d0c708bc2af633048edfb/view">URA Master Plan 2019 subzone boundary dataset</a></li>
      <li><a href="https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/east/">URA East Region plan</a></li>
      <li><a href="https://www.ura.gov.sg/property-data/private-residential-properties/">URA private residential property data</a></li>
      <li><a href="https://www.sla.gov.sg/geospatial/onemap/">SLA OneMap and SchoolQuery</a></li>
      <li><a href="https://www.moe.gov.sg/-/media/files/news/press/2024/annex-a---start-of-2024-dsa-and-eae.pdf">MOE Home-School Distance methodology</a></li>
      <li><a href="https://www.lta.gov.sg/content/ltagov/en/getting_around/public_transport/rail_network.html">LTA current rail network</a></li>
      <li><a href="https://www.lta.gov.sg/content/ltagov/en/newsroom/2022/2/news-releases/LTA_awards_civil_contracts_for_design_and_construction.html">LTA CRL1 and Tampines North timing</a></li>
      <li><a href="https://www.lta.gov.sg/content/ltagov/en/newsroom/2026/4/news-releases/train-service-adjustments-tel-and-dtl-to-facilitate-rail-expansion-works.html">LTA 2026 Downtown Line extension testing</a></li>
      <li><a href="https://valhalla.github.io/valhalla/start/introduction/">Valhalla pedestrian-routing documentation</a></li>
    </ul>
    <p>Project coordinates do not represent every legal lot boundary or pedestrian gate. Walking routes can change with construction hoardings, crossings and gate openings. Under-construction routes describe the completed design and cannot be physically walked from an occupied unit today. Portal walking estimates are supplementary evidence, not official LTA measurements.</p>
  </section>

  <p class="footer">Point-in-time area research · $captured · Evidence and limitations remain visible.</p>
</main>
<script>
(function () {
  const search = document.getElementById('search');
  const school = document.getElementById('school-filter');
  const mrt = document.getElementById('mrt-filter');
  const rows = Array.from(document.querySelectorAll('#project-rows tr'));
  const count = document.getElementById('result-count');
  function applyFilters() {
    const needle = search.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach(function (row) {
      const matchesSearch = !needle || row.dataset.search.includes(needle);
      const matchesSchool = school.value === 'all' || row.dataset.school === school.value;
      const matchesMrt = mrt.value === 'all' || row.dataset.mrt === mrt.value;
      row.hidden = !(matchesSearch && matchesSchool && matchesMrt);
      if (!row.hidden) visible += 1;
    });
    count.textContent = 'Showing ' + visible + ' of ' + rows.length + ' projects.';
  }
  search.addEventListener('input', applyFilters);
  school.addEventListener('change', applyFilters);
  mrt.addEventListener('change', applyFilters);
}());
</script>
</body>
</html>
"""
)


def render_page() -> str:
    return PAGE.substitute(
        canonical=escape(CANONICAL, quote=True),
        captured=escape(CAPTURED),
        table_rows=table_rows(),
    )


def generate(out: Path = DEFAULT_OUT) -> Path:
    out.write_text(render_page(), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    output = generate(args.out)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
