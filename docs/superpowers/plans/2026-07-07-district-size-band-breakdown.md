# Size-Band Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add size-band tabs (All · ≤50 · 50–70 · 70–100 · 100–130 · >130 sqm) with EdgeProp-derived `≈nBR` labels to the per-district private comparison pages.

**Architecture:** All changes live in `models/gen_district_private_comparison_html.py`. New band constants + `band_of()`; new `load_edgeprop_bedroom_labels()` (labels only — EdgeProp prices never enter the transaction set); `generate()` computes per-band aggregates by reusing the existing `aggregate_projects`/`district_summary` on filtered subsets; `render_html` is rewritten to render one section per band with a JS tab bar. Loaders and aggregation functions are unchanged.

**Tech Stack:** Python 3, pandas, vanilla JS in a self-contained HTML page.

**Spec:** `docs/superpowers/specs/2026-07-07-district-size-band-breakdown-design.md`

## Global Constraints

- Band ranges (on `area_sqm`, exclusive-lo / inclusive-hi): `le50` (0,50], `50to70` (50,70], `70to100` (70,100], `100to130` (100,130], `gt130` (130,∞). Pseudo-band `all` = no filter.
- Bedroom label rule per (display_project, band): needs **n ≥ 3** EdgeProp rows AND modal bedroom share **≥ 0.7** → label `≈{mode}BR`; else no entry.
- Bedroom labels come from EdgeProp rows of ALL years 2019–2026; transaction backfill stays 2019–2020 only (existing loaders untouched).
- `render_html` new signature: `render_html(district: str, per_band: dict[str, tuple[list[dict], dict]], bedroom_labels: dict[tuple[str, str], str]) -> str`.
- Band tabs (not `all`) show a `Bedrooms` column; `all` tab does not.
- Projects with 0 txns in a band are omitted from that band's table (aggregate on the filtered subset does this naturally).
- Page stays self-contained: no external URLs.
- Existing 18 unit tests + 1 integration test must keep passing (one render test updated to the new signature).

---

### Task 1: Band constants + `band_of`

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append after `DISTRICT_NAMES` block or at end)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Produces: `AREA_BANDS: list[tuple[str, str, float, float]]` (key, display label, lo, hi);
  `BAND_ORDER: list[str]` = `["all", "le50", "50to70", "70to100", "100to130", "gt130"]`;
  `BAND_LABELS: dict[str, str]` (includes `"all" -> "All"`);
  `band_of(area_sqm: float) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gen_district_private_comparison.py

def test_band_of_boundaries():
    assert gen.band_of(30.0) == "le50"
    assert gen.band_of(50.0) == "le50"
    assert gen.band_of(50.1) == "50to70"
    assert gen.band_of(70.0) == "50to70"
    assert gen.band_of(100.0) == "70to100"
    assert gen.band_of(130.0) == "100to130"
    assert gen.band_of(130.5) == "gt130"
    assert gen.band_of(500.0) == "gt130"
    assert gen.BAND_ORDER == ["all", "le50", "50to70", "70to100", "100to130", "gt130"]
    assert gen.BAND_LABELS["all"] == "All"
    assert gen.BAND_LABELS["gt130"] == ">130 sqm"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py::test_band_of_boundaries -v`
Expected: FAIL with `AttributeError: ... has no attribute 'band_of'`

- [ ] **Step 3: Implement**

```python
# append to models/gen_district_private_comparison_html.py

AREA_BANDS = [
    ("le50", "≤50 sqm", 0.0, 50.0),
    ("50to70", "50–70 sqm", 50.0, 70.0),
    ("70to100", "70–100 sqm", 70.0, 100.0),
    ("100to130", "100–130 sqm", 100.0, 130.0),
    ("gt130", ">130 sqm", 130.0, float("inf")),
]
BAND_ORDER = ["all"] + [key for key, _, _, _ in AREA_BANDS]
BAND_LABELS = {"all": "All", **{key: label for key, label, _, _ in AREA_BANDS}}


def band_of(area_sqm: float) -> str:
    for key, _, lo, hi in AREA_BANDS:
        if lo < area_sqm <= hi:
            return key
    return AREA_BANDS[0][0]  # loaders guarantee area > 0; defensive default
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: 20 passed (19 existing incl. the integration test — plain runs only deselect `snapshot` — + 1 new)

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: area band constants and band_of helper"
```

---

### Task 2: EdgeProp bedroom-label learning

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` (append)
- Modify: `tests/test_gen_district_private_comparison.py` (append)

**Interfaces:**
- Consumes: `normalise_district`, `display_project`, `band_of` from earlier tasks; the EdgeProp CSV schema (`Project`, `Street`, `Postal District`, `Bedrooms`, `Area (sqm)` columns; `_edgeprop_row` test helper exists).
- Produces: `load_edgeprop_bedroom_labels(path: pathlib.Path, district: str) -> dict[tuple[str, str], str]` keyed by `(display_project, band_key)`, values like `"≈3BR"`. Missing file → `{}`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gen_district_private_comparison.py

def test_bedroom_labels_mode_share_rule(tmp_path):
    rows = (
        # SELETARIS 116.1 sqm -> band 100to130; 3 rows, all "3" -> label (uses 2021+ rows too)
        [_edgeprop_row(**{"Date of Sale": "10 Jun 2021"}),
         _edgeprop_row(**{"Date of Sale": "10 Jun 2023"}),
         _edgeprop_row()]
        # EULER: only 2 rows -> no label
        + [_edgeprop_row(**{"Project": "EULER", "Bedrooms": "2", "Area (sqm)": "65"}) for _ in range(2)]
        # GAUSS: 3 rows split 2/1 -> share 0.67 < 0.7 -> no label
        + [_edgeprop_row(**{"Project": "GAUSS", "Bedrooms": "2", "Area (sqm)": "65"}),
           _edgeprop_row(**{"Project": "GAUSS", "Bedrooms": "2", "Area (sqm)": "66"}),
           _edgeprop_row(**{"Project": "GAUSS", "Bedrooms": "3", "Area (sqm)": "67"})]
        # NOETHER: unparseable bedrooms ignored entirely
        + [_edgeprop_row(**{"Project": "NOETHER", "Bedrooms": "-", "Area (sqm)": "80"}) for _ in range(3)]
    )
    path = _write_edgeprop(tmp_path, rows)
    labels = gen.load_edgeprop_bedroom_labels(path, "27")
    assert labels[("SELETARIS", "100to130")] == "≈3BR"
    assert ("EULER", "50to70") not in labels
    assert ("GAUSS", "50to70") not in labels
    assert not any(proj == "NOETHER" for proj, _ in labels)


def test_bedroom_labels_missing_file(tmp_path):
    assert gen.load_edgeprop_bedroom_labels(tmp_path / "nope.csv", "27") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: 2 new FAIL with `AttributeError: ... has no attribute 'load_edgeprop_bedroom_labels'`

- [ ] **Step 3: Implement**

```python
# append to models/gen_district_private_comparison_html.py

def load_edgeprop_bedroom_labels(path: pathlib.Path, district: str) -> dict:
    """(display_project, band_key) -> '≈nBR'. Labels only; prices never merged from here."""
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"Postal District": str, "Bedrooms": str})
    df = df[df["Postal District"].map(normalise_district) == district].copy()
    df["bedrooms"] = pd.to_numeric(df["Bedrooms"], errors="coerce")
    df["area_sqm"] = pd.to_numeric(df["Area (sqm)"], errors="coerce")
    df = df.dropna(subset=["bedrooms", "area_sqm"])
    df = df[(df["bedrooms"] > 0) & (df["area_sqm"] > 0)]
    if df.empty:
        return {}
    df["bedrooms"] = df["bedrooms"].astype(int)
    project = df["Project"].astype(str).str.strip().str.upper()
    street = df["Street"].astype(str).str.strip().str.upper()
    df["display_project"] = [display_project(p, s) for p, s in zip(project, street)]
    df["band"] = df["area_sqm"].map(band_of)
    labels = {}
    for (proj, band), grp in df.groupby(["display_project", "band"]):
        if len(grp) < 3:
            continue
        counts = grp["bedrooms"].value_counts()
        if counts.iloc[0] / len(grp) >= 0.7:
            labels[(proj, band)] = f"≈{counts.index[0]}BR"
    return labels
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: 22 passed

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: EdgeProp bedroom label learning per project and band"
```

---

### Task 3: Tabbed rendering + per-band generate

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` — replace the whole `render_html` function and the body of `generate` (keep `main` as is)
- Modify: `tests/test_gen_district_private_comparison.py` — replace `test_render_html_marks_low_n_years_and_backfill`, extend `test_generate_writes_self_contained_page`, add a band-membership test

**Interfaces:**
- Consumes: everything from Tasks 1–2 plus existing `aggregate_projects`, `district_summary`, `_fmt`, `_esc`, `MIN_YEAR_N`, `YEARS`, `DISTRICT_NAMES`.
- Produces: `render_html(district, per_band, bedroom_labels) -> str` where `per_band` maps band key → `(rows, summary)` (as returned by `aggregate_projects` / `district_summary`), rendered in `BAND_ORDER` order, skipping keys absent from `per_band`; `generate(...)` same signature/return as before (`(out_path, n_projects_all_band)`).

- [ ] **Step 1: Update/write the failing tests**

Replace `test_render_html_marks_low_n_years_and_backfill` with:

```python
def test_render_html_marks_low_n_years_and_backfill():
    year_stats = {y: (None, 0) for y in gen.YEARS}
    year_stats[2021] = (1000.0, 3)
    year_stats[2022] = (1050.0, 1)
    rows = [{
        "project": "ALPHA", "street": "S", "property_types": "Condominium",
        "tenure": "Freehold", "n_total": 4,
        "year_stats": year_stats,
        "growth_pct": None, "growth_from": None, "growth_to": None,
        "latest_year": 2022, "latest_median_psf": 1050.0, "latest_median_price": 1_000_000.0,
        "has_edgeprop_backfill": True,
    }]
    summary = {"total_txns": 4, "yearly": year_stats,
               "top_growth": [], "bottom_growth": []}
    html_text = gen.render_html("27", {"all": (rows, summary)}, {})
    assert "1,000" in html_text        # 2021 median shown (n>=3)
    assert "backfill" in html_text.lower()
```

Append the band tests (and extend the self-contained test in place by adding the tab assertions shown):

```python
def _band_section(html_text, key):
    import re
    m = re.search(rf'<section id="band-{key}".*?</section>', html_text, re.S)
    assert m, f"missing section band-{key}"
    return m.group(0)


def test_generate_renders_band_tabs_and_membership(tmp_path):
    canonical, edgeprop, raw_dir = _full_fixture(tmp_path)
    out_path, _ = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    text = out_path.read_text(encoding="utf-8")
    for label in ("All", "≤50 sqm", "50–70 sqm", "70–100 sqm", "100–130 sqm", ">130 sqm"):
        assert label in text
    # canonical SHAUGHNESSY row is 100.0 sqm -> band 70to100 only
    assert "THE SHAUGHNESSY" in _band_section(text, "70to100")
    assert "THE SHAUGHNESSY" not in _band_section(text, "gt130")
    # ura_raw landed row is 335.8 sqm -> gt130 only
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in _band_section(text, "gt130")
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" not in _band_section(text, "70to100")


def test_generate_shows_bedroom_label_in_band_table(tmp_path):
    canonical = _write_canonical(tmp_path)
    # 3 SELETARIS rows (116.1 sqm -> 100to130), all 3BR -> label ≈3BR
    edgeprop = _write_edgeprop(tmp_path, [
        _edgeprop_row(),
        _edgeprop_row(**{"Date of Sale": "16 Mar 2019"}),
        _edgeprop_row(**{"Date of Sale": "17 Mar 2019"}),
    ])
    raw_dir = tmp_path / "ura_raw"
    raw_dir.mkdir()
    out_path, _ = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    section = _band_section(out_path.read_text(encoding="utf-8"), "100to130")
    assert "≈3BR" in section
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: the replaced render test FAILS (old `render_html` signature mismatch → TypeError) and both new tests FAIL (no `<section id="band-...">` in output).

- [ ] **Step 3: Rewrite `render_html` and `generate`**

Replace the existing `render_html` function entirely with:

```python
def _render_summary_cards(summary: dict, growth_list_fn) -> str:
    yearly_cells = "".join(
        f"<td class='num'>{_fmt(summary['yearly'][y][0])}"
        f"<div class='n'>n={summary['yearly'][y][1]}</div></td>"
        for y in YEARS
    )
    yearly_heads = "".join(f"<th class='num'>{y}</th>" for y in YEARS)
    return (
        "<div class=\"summary\">"
        "<div class=\"card\"><h3>Median PSF by year</h3>"
        f"<table><tr>{yearly_heads}</tr><tr>{yearly_cells}</tr></table></div>"
        f"<div class=\"card\"><h3>Top growth</h3><ul>{growth_list_fn(summary['top_growth'])}</ul></div>"
        f"<div class=\"card\"><h3>Bottom growth</h3><ul>{growth_list_fn(summary['bottom_growth'])}</ul></div>"
        "</div>"
    )


def _render_project_table(band_key: str, rows: list[dict], bedroom_labels: dict) -> str:
    show_bedrooms = band_key != "all"
    year_heads = "".join(f"<th class='num sortable'>{y}</th>" for y in YEARS)
    bedroom_head = "<th class='sortable'>Bedrooms</th>" if show_bedrooms else ""
    body_rows = []
    for r in rows:
        year_cells = []
        for y in YEARS:
            median, n = r["year_stats"][y]
            if n >= MIN_YEAR_N and median is not None:
                year_cells.append(
                    f"<td class='num' data-v='{median:.0f}' title='n={n}'>{_fmt(median)}</td>"
                )
            else:
                year_cells.append(f"<td class='num muted' data-v='' title='n={n}'>—</td>")
        growth = r["growth_pct"]
        if growth is None:
            growth_cell = "<td class='num muted' data-v=''>—</td>"
        else:
            cls = "pos" if growth >= 0 else "neg"
            growth_cell = (
                f"<td class='num {cls}' data-v='{growth:.2f}' "
                f"title='{r['growth_from']}&rarr;{r['growth_to']}'>{growth:+.1f}%/yr</td>"
            )
        badge = (
            " <span class='badge' title='includes EdgeProp 2019&ndash;2020 backfill rows"
            " (incomplete coverage)'>backfill</span>"
            if r["has_edgeprop_backfill"] else ""
        )
        bedroom_cell = ""
        if show_bedrooms:
            label = bedroom_labels.get((r["project"], band_key), "")
            v = _esc(label) if label else ""
            bedroom_cell = f"<td data-v='{v}'>{v or '&mdash;'}</td>"
        psf_v = "" if r["latest_median_psf"] is None else f"{r['latest_median_psf']:.0f}"
        price_v = "" if r["latest_median_price"] is None else f"{r['latest_median_price']:.0f}"
        body_rows.append(
            "<tr>"
            f"<td data-v='{_esc(r['project'])}'>{_esc(r['project'])}{badge}</td>"
            f"<td data-v='{_esc(r['property_types'])}'>{_esc(r['property_types'])}</td>"
            f"<td data-v='{_esc(r['tenure'])}'>{_esc(r['tenure'])}</td>"
            + bedroom_cell
            + f"<td class='num' data-v='{r['n_total']}'>{r['n_total']}</td>"
            + "".join(year_cells)
            + growth_cell
            + f"<td class='num' data-v='{psf_v}'>{_fmt(r['latest_median_psf'])}</td>"
            + f"<td class='num' data-v='{price_v}'>{_fmt(r['latest_median_price'])}</td>"
            "</tr>"
        )
    return (
        "<table class=\"ptable\">"
        "<thead><tr>"
        "<th class=\"sortable\">Project</th><th class=\"sortable\">Type</th>"
        "<th class=\"sortable\">Tenure</th>"
        + bedroom_head +
        "<th class=\"num sortable\">Txns</th>" + year_heads +
        "<th class=\"num sortable\">Growth %/yr</th>"
        "<th class=\"num sortable\">Latest median PSF</th>"
        "<th class=\"num sortable\">Latest median price</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def render_html(district: str, per_band: dict, bedroom_labels: dict) -> str:
    district_name = DISTRICT_NAMES.get(district, f"District {district}")

    def _growth_list(items):
        if not items:
            return "<li class='muted'>—</li>"
        return "".join(
            f"<li>{_esc(i['project'])} <span class='{'pos' if i['growth_pct'] >= 0 else 'neg'}'>"
            f"{i['growth_pct']:+.1f}%/yr</span></li>"
            for i in items
        )

    band_keys = [k for k in BAND_ORDER if k in per_band]
    tab_buttons = "".join(
        f"<button class=\"tab{' active' if key == band_keys[0] else ''}\" "
        f"data-band=\"{key}\">{_esc(BAND_LABELS[key])}</button>"
        for key in band_keys
    )
    sections = []
    for key in band_keys:
        rows, summary = per_band[key]
        active = " active" if key == band_keys[0] else ""
        sections.append(
            f"<section id=\"band-{key}\" class=\"band{active}\">"
            f"<div class=\"bandmeta\">{_esc(BAND_LABELS[key])} &middot; "
            f"{summary['total_txns']:,} transactions &middot; {len(rows)} projects</div>"
            + _render_summary_cards(summary, _growth_list)
            + _render_project_table(key, rows, bedroom_labels)
            + "</section>"
        )
    total_txns = per_band[band_keys[0]][1]["total_txns"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>D{district} Private Property Comparison ({district_name})</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 24px; color: #1a1a2e; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .caveat {{ background: #fff7e0; border: 1px solid #e8c96a; border-radius: 8px;
             padding: 10px 14px; margin: 12px 0 20px; font-size: 13px; max-width: 900px; }}
  .tabs {{ margin: 0 0 16px; display: flex; gap: 6px; flex-wrap: wrap; }}
  .tab {{ border: 1px solid #ccd; background: #f4f4fa; border-radius: 6px 6px 0 0;
          padding: 6px 14px; font-size: 13px; cursor: pointer; }}
  .tab.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}
  section.band {{ display: none; }}
  section.band.active {{ display: block; }}
  .bandmeta {{ font-size: 13px; color: #555; margin-bottom: 10px; }}
  .summary {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 20px; }}
  .summary .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .summary h3 {{ margin: 0 0 6px; font-size: 13px; }}
  .summary ul {{ margin: 0; padding-left: 18px; }}
  table {{ border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 5px 9px; border-bottom: 1px solid #e4e4ee; text-align: left; white-space: nowrap; }}
  th {{ background: #f4f4fa; position: sticky; top: 0; cursor: pointer; user-select: none; }}
  section.band .ptable th {{ cursor: pointer; }}
  td.num, th.num {{ text-align: right; }}
  .muted {{ color: #9a9ab0; }}
  .pos {{ color: #0a7a3d; }}
  .neg {{ color: #b02a2a; }}
  .badge {{ background: #fdecc8; color: #8a6100; border-radius: 4px; padding: 1px 5px; font-size: 11px; }}
  .n {{ font-size: 10px; color: #9a9ab0; }}
</style>
</head>
<body>
<h1>District {district} &mdash; {_esc(district_name)}: Private Property Comparison</h1>
<div>Window: 2019&ndash;2026 &middot; median PSF (S$) by sale year &middot; {total_txns:,} transactions</div>
<div class="caveat">&#9888; 2019&ndash;2020 condo/apartment rows are backfilled from an incomplete EdgeProp scrape
(the canonical URA feed only reaches back to 2021). Pre-2021 medians are indicative only &mdash;
projects using that data carry a <span class="badge">backfill</span> badge. Landed 2019&ndash;2020 rows
come from raw URA PMI downloads. Year cells show &mdash; when the year has fewer than {MIN_YEAR_N} transactions.
Bedroom labels (&asymp;nBR) are estimates derived from EdgeProp unit listings per size band, shown only when
at least 3 units agree &ge;70%.</div>
<div class="tabs">{tab_buttons}</div>
{"".join(sections)}
<script>
document.querySelectorAll('.tab').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    document.querySelectorAll('.tab').forEach(function (b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('section.band').forEach(function (s) {{ s.classList.remove('active'); }});
    btn.classList.add('active');
    document.getElementById('band-' + btn.dataset.band).classList.add('active');
  }});
}});
document.querySelectorAll('.ptable').forEach(function (table) {{
  var tbody = table.querySelector('tbody');
  table.querySelectorAll('th').forEach(function (th, idx) {{
    th.addEventListener('click', function () {{
      var rows = Array.from(tbody.rows);
      var dir = th.dataset.dir === 'asc' ? -1 : 1;
      table.querySelectorAll('th').forEach(function (h) {{ delete h.dataset.dir; }});
      th.dataset.dir = dir === 1 ? 'asc' : 'desc';
      rows.sort(function (a, b) {{
        var av = a.cells[idx].dataset.v, bv = b.cells[idx].dataset.v;
        if (av === '' && bv === '') return 0;
        if (av === '') return 1;
        if (bv === '') return -1;
        var an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return (an - bn) * dir;
        return av.localeCompare(bv) * dir;
      }});
      rows.forEach(function (r) {{ tbody.appendChild(r); }});
    }});
  }});
}});
</script>
</body>
</html>
"""
```

Replace the body of `generate` with:

```python
def generate(district, private_path, edgeprop_path, raw_dir, out_dir):
    district = normalise_district(district)
    frames = [
        load_canonical(private_path, district),
        load_edgeprop_backfill(edgeprop_path, district),
        load_ura_raw_backfill(raw_dir, district),
    ]
    non_empty = [f for f in frames if not f.empty]
    merged = pd.concat(non_empty, ignore_index=True) if non_empty else _empty_unified()
    bedroom_labels = load_edgeprop_bedroom_labels(edgeprop_path, district)
    per_band = {}
    all_rows = aggregate_projects(merged)
    per_band["all"] = (all_rows, district_summary(merged, all_rows))
    for key, _, lo, hi in AREA_BANDS:
        sub = merged[(merged["area_sqm"] > lo) & (merged["area_sqm"] <= hi)]
        band_rows = aggregate_projects(sub)
        per_band[key] = (band_rows, district_summary(sub, band_rows))
    out_path = pathlib.Path(out_dir) / f"private_project_comparison_D{district}.html"
    out_path.write_text(render_html(district, per_band, bedroom_labels), encoding="utf-8")
    return out_path, len(all_rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: 24 passed (22 from Tasks 1–2 + 2 new generate tests; the replaced render test keeps the count flat and the pre-existing `test_generate_writes_self_contained_page` must still pass unmodified)

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: size-band tabs with bedroom labels on district pages"
```

---

### Task 4: Regenerate real pages + integration coverage

**Files:**
- Modify: `tests/test_gen_district_private_comparison.py` (extend the integration test)
- Regenerate: `private_project_comparison_D17.html`, `private_project_comparison_D27.html`

**Interfaces:**
- Consumes: `generate` from Task 3, committed data files.

- [ ] **Step 1: Extend the integration test**

In `test_generate_real_d17_d27`, after `assert "2019" in text`, add:

```python
        for label in ("≤50 sqm", "50–70 sqm", "70–100 sqm", "100–130 sqm", ">130 sqm"):
            assert label in text
        assert 'id="band-gt130"' in text
        assert "≈" in text  # at least one bedroom label rendered from real EdgeProp data
```

- [ ] **Step 2: Run the integration test**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -m integration -v`
Expected: 1 passed

- [ ] **Step 3: Run the full suite**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && make smoke`
Expected: all pass (137 passed ballpark: 131 previous + new tests, 1 deselected snapshot)

- [ ] **Step 4: Regenerate the pages**

```bash
cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && \
python3 models/gen_district_private_comparison_html.py --district 17 --district 27
```
Expected: two `Written:` lines; file sizes roughly 3–6× the previous 56/49 KB. Spot-check: tab bar present, All tab active by default, band tab shows Bedrooms column with some `≈nBR` values.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gen_district_private_comparison.py \
        private_project_comparison_D17.html private_project_comparison_D27.html
git commit -m "feat: size-band breakdown on D17/D27 comparison pages"
```
