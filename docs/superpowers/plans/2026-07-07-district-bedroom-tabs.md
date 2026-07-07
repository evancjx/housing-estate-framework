# Bedroom-Count Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bedroom-count tabs (1BR · 2BR · 3BR · 4BR · 5BR+ · Unknown) as a second labelled tab row on the district comparison pages.

**Architecture:** All in `models/gen_district_private_comparison_html.py`. The EdgeProp label loader is refactored to return integer bedroom counts; a `bedroom_class()` helper maps each transaction to a class via its `(display_project, band_of(area))` key; `generate()` adds one `per_band` entry per bedroom class; `render_html` renders two labelled tab rows and builds `≈nBR` strings from the ints.

**Tech Stack:** Python 3, pandas, vanilla JS, self-contained HTML.

**Spec:** `docs/superpowers/specs/2026-07-07-district-bedroom-tabs-design.md`

## Global Constraints

- `load_edgeprop_bedroom_labels` is RENAMED to `load_edgeprop_bedroom_counts` returning `dict[tuple[str, str], int]`; same learning rule (n ≥ 3, modal share ≥ 0.7).
- `BEDROOM_ORDER = ["br1", "br2", "br3", "br4", "br5plus", "brunknown"]`; `BEDROOM_LABELS = {"br1": "1BR", "br2": "2BR", "br3": "3BR", "br4": "4BR", "br5plus": "5BR+", "brunknown": "Unknown"}`.
- `bedroom_class(count)`: 1–4 → `br1`…`br4`; ≥5 → `br5plus`; `None` → `brunknown`. All landed ends up `brunknown` (no EdgeProp labels for landed).
- The `≈nBR` column appears ONLY on size-band tabs (`le50`…`gt130`) — not on `all`, not on bedroom tabs.
- Empty bedroom classes still render as sections with empty tables.
- Section ids: `band-br1` … `band-brunknown`; existing JS tab switching reused unchanged.
- Page stays self-contained; existing tests keep passing except the two label tests updated to int assertions.

---

### Task 1: Loader refactor to ints + bedroom constants

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` — rename `load_edgeprop_bedroom_labels` → `load_edgeprop_bedroom_counts`, change label build; add constants + `bedroom_class`
- Modify: `tests/test_gen_district_private_comparison.py` — update `test_bedroom_labels_mode_share_rule`, `test_bedroom_labels_missing_file`; add `test_bedroom_class`

**Interfaces:**
- Produces: `load_edgeprop_bedroom_counts(path: pathlib.Path, district: str) -> dict[tuple[str, str], int]`; `BEDROOM_ORDER: list[str]`; `BEDROOM_LABELS: dict[str, str]`; `bedroom_class(count: int | None) -> str`.
- NOTE: this task temporarily breaks `generate`/`render_html` callers of the old name — Task 2 fixes them; run only the targeted tests in this task.

- [ ] **Step 1: Update/write the failing tests**

Replace the two existing label tests' assertion blocks and add the class test:

```python
# in test_bedroom_labels_mode_share_rule, replace the 4 assert lines with:
    labels = gen.load_edgeprop_bedroom_counts(path, "27")
    assert labels[("SELETARIS", "100to130")] == 3
    assert ("EULER", "50to70") not in labels
    assert ("GAUSS", "50to70") not in labels
    assert not any(proj == "NOETHER" for proj, _ in labels)

# in test_bedroom_labels_missing_file:
    assert gen.load_edgeprop_bedroom_counts(tmp_path / "nope.csv", "27") == {}

# appended:
def test_bedroom_class():
    assert gen.bedroom_class(1) == "br1"
    assert gen.bedroom_class(4) == "br4"
    assert gen.bedroom_class(5) == "br5plus"
    assert gen.bedroom_class(7) == "br5plus"
    assert gen.bedroom_class(None) == "brunknown"
    assert gen.BEDROOM_ORDER == ["br1", "br2", "br3", "br4", "br5plus", "brunknown"]
    assert gen.BEDROOM_LABELS["br5plus"] == "5BR+"
```

- [ ] **Step 2: Run to verify failures**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -k "bedroom" -v`
Expected: 3 FAIL (`AttributeError` on the new names)

- [ ] **Step 3: Implement**

In the loader, rename the function and replace the label-string line:

```python
def load_edgeprop_bedroom_counts(path: pathlib.Path, district: str) -> dict:
    """(display_project, band_key) -> modal bedroom count. Labels only; prices never merged."""
    ...
        if counts.iloc[0] / len(grp) >= 0.7:
            labels[(proj, band)] = int(counts.index[0])
    return labels
```

Append constants + helper:

```python
BEDROOM_ORDER = ["br1", "br2", "br3", "br4", "br5plus", "brunknown"]
BEDROOM_LABELS = {"br1": "1BR", "br2": "2BR", "br3": "3BR", "br4": "4BR",
                  "br5plus": "5BR+", "brunknown": "Unknown"}


def bedroom_class(count) -> str:
    if count is None:
        return "brunknown"
    if count >= 5:
        return "br5plus"
    return f"br{int(count)}"
```

- [ ] **Step 4: Run targeted tests**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -k "bedroom" -v`
Expected: 3 passed (generate-dependent tests are NOT run here; they still reference the old name until Task 2)

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "refactor: bedroom label loader returns ints; bedroom class constants"
```

---

### Task 2: Bedroom sections in generate + two-row tab bar

**Files:**
- Modify: `models/gen_district_private_comparison_html.py` — `generate`, `render_html`, `_render_project_table`
- Modify: `tests/test_gen_district_private_comparison.py` — add membership/render tests

**Interfaces:**
- Consumes: Task 1 names; existing `aggregate_projects`, `district_summary`, `display_project`, `band_of`, `BAND_ORDER`, `BAND_LABELS`.
- Produces: `render_html(district, per_band, bedroom_counts)` where `per_band` may contain size keys AND bedroom keys; `SIZE_BAND_KEYS: frozenset[str]` (the five `AREA_BANDS` keys).

- [ ] **Step 1: Write the failing tests**

```python
def test_generate_renders_bedroom_tabs_and_membership(tmp_path):
    canonical = _write_canonical(tmp_path)
    edgeprop = _write_edgeprop(tmp_path, [
        _edgeprop_row(),
        _edgeprop_row(**{"Date of Sale": "16 Mar 2019"}),
        _edgeprop_row(**{"Date of Sale": "17 Mar 2019"}),
    ])  # SELETARIS 116.1 sqm -> (SELETARIS, 100to130) -> 3BR
    raw_dir = _write_ura_raw(tmp_path, "27", [_ura_raw_row(**{"Postal District": "27"})])
    out_path, _ = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    text = out_path.read_text(encoding="utf-8")
    for label in ("1BR", "2BR", "3BR", "4BR", "5BR+", "Unknown"):
        assert label in text
    assert "SELETARIS" in _band_section(text, "br3")
    assert "SELETARIS" not in _band_section(text, "br2")
    # landed + unlabelled canonical rows -> Unknown
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in _band_section(text, "brunknown")
    assert "THE SHAUGHNESSY" in _band_section(text, "brunknown")
    # bedroom sections do not carry the ≈nBR column
    assert "≈3BR" not in _band_section(text, "br3")
    assert "≈3BR" in _band_section(text, "100to130")


def test_render_html_two_tab_rows():
    year_stats = {y: (None, 0) for y in gen.YEARS}
    rows_summary = ([], {"total_txns": 0, "yearly": year_stats, "top_growth": [], "bottom_growth": []})
    per_band = {k: rows_summary for k in gen.BAND_ORDER + gen.BEDROOM_ORDER}
    html_text = gen.render_html("27", per_band, {})
    assert "Size:" in html_text and "Bedrooms:" in html_text
    for key in gen.BAND_ORDER + gen.BEDROOM_ORDER:
        assert f'id="band-{key}"' in html_text
```

- [ ] **Step 2: Run to verify failures**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: the 2 new tests FAIL; also any test still touching the removed old loader name fails until this task's code lands (none should — Task 1 updated them).

- [ ] **Step 3: Implement**

Add near `AREA_BANDS`:

```python
SIZE_BAND_KEYS = frozenset(key for key, _, _, _ in AREA_BANDS)
ALL_TAB_LABELS = {**BAND_LABELS, **BEDROOM_LABELS}
```

`_render_project_table`: `show_bedrooms = band_key in SIZE_BAND_KEYS`; label cell becomes:

```python
        if show_bedrooms:
            count = bedroom_counts.get((r["project"], band_key))
            v = f"≈{count}BR" if count is not None else ""
            bedroom_cell = f"<td data-v='{v}'>{v or '&mdash;'}</td>"
```

(param renamed `bedroom_labels` → `bedroom_counts`.)

`render_html`: replace the single `tab_buttons` block with two rows and iterate both orders:

```python
    def _tab_buttons(keys, active_key):
        return "".join(
            f"<button class=\"tab{' active' if key == active_key else ''}\" "
            f"data-band=\"{key}\">{ALL_TAB_LABELS[key]}</button>"
            for key in keys
        )

    size_keys = [k for k in BAND_ORDER if k in per_band]
    bedroom_keys = [k for k in BEDROOM_ORDER if k in per_band]
    band_keys = size_keys + bedroom_keys
    active_key = band_keys[0]
    tab_bar = (
        f"<div class=\"tabrow\"><span class=\"tablabel\">Size:</span>{_tab_buttons(size_keys, active_key)}</div>"
        + (f"<div class=\"tabrow\"><span class=\"tablabel\">Bedrooms:</span>{_tab_buttons(bedroom_keys, active_key)}</div>"
           if bedroom_keys else "")
    )
```

Sections loop uses `band_keys`, `ALL_TAB_LABELS[key]` in the meta line, `active_key` for the
active section. In the HTML template replace `<div class="tabs">{tab_buttons}</div>` with
`<div class="tabs">{tab_bar}</div>` and add CSS:

```css
  .tabs {{ margin: 0 0 16px; }}
  .tabrow {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 6px; }}
  .tablabel {{ font-size: 12px; color: #555; min-width: 72px; }}
```

Caveat banner: append sentence

```
Bedroom tabs classify each transaction by its project + size band's EdgeProp label; atypical
units can be misclassified, and Unknown collects unlabelled transactions (including all landed).
```

`generate`: after computing size bands, assign classes and add bedroom entries:

```python
    bedroom_counts = load_edgeprop_bedroom_counts(edgeprop_path, district)
    ...
    disp = [display_project(p, s) for p, s in zip(merged["project"], merged["street"])]
    bands = [band_of(a) for a in merged["area_sqm"]]
    merged["bed_class"] = [
        bedroom_class(bedroom_counts.get((d, b))) for d, b in zip(disp, bands)
    ]
    for key in BEDROOM_ORDER:
        sub = merged[merged["bed_class"] == key]
        class_rows = aggregate_projects(sub)
        per_band[key] = (class_rows, district_summary(sub, class_rows))
```

(`render_html(district, per_band, bedroom_counts)` call updated.)

- [ ] **Step 4: Run the whole file's tests**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -q`
Expected: 27 passed (25 after Task 1 + 2 new)

- [ ] **Step 5: Commit**

```bash
git add models/gen_district_private_comparison_html.py tests/test_gen_district_private_comparison.py
git commit -m "feat: bedroom-count tabs on district comparison pages"
```

---

### Task 3: Integration coverage + regenerate real pages

**Files:**
- Modify: `tests/test_gen_district_private_comparison.py` (integration test)
- Regenerate: `private_project_comparison_D17.html`, `private_project_comparison_D27.html`

- [ ] **Step 1: Extend the integration test**

After the existing band assertions in `test_generate_real_d17_d27`, add:

```python
        for label in ("1BR", "2BR", "3BR", "4BR", "5BR+", "Unknown"):
            assert label in text
        assert 'id="band-brunknown"' in text
        assert 'id="band-br3"' in text
```

- [ ] **Step 2: Run integration + full suite**

Run: `cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && python3 -m pytest tests/test_gen_district_private_comparison.py -m integration -q && make smoke`
Expected: integration 1 passed; full suite all pass (~139).

- [ ] **Step 3: Regenerate pages**

```bash
cd "/Users/evancjx/workspace/Housing Estate/SG-Estate-Framework" && \
python3 models/gen_district_private_comparison_html.py --district 17 --district 27
```
Expected: two `Written:` lines, sizes ~1.7× previous (12 sections instead of 6). Spot-check: two tab rows, bedroom sections populated, Unknown holds landed projects.

- [ ] **Step 4: Commit**

```bash
git add tests/test_gen_district_private_comparison.py \
        private_project_comparison_D17.html private_project_comparison_D27.html
git commit -m "feat: bedroom tabs on D17/D27 pages"
```
