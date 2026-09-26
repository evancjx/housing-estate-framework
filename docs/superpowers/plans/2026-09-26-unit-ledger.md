# Project Unit Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `python3 -m scrapers.unit_ledger run --project "<URA name>"`. It fetches one project's
URA, EdgeProp and PropertyNoob transactions, plus an optional unit chart and recent-sales list. It
matches every transaction to an exact date and, where evidence allows, a unit. It writes a local
sortable table and a site sales view.

**Architecture:** A new package, `scrapers/unit_ledger/`, in three stages:
- `fetch.py` writes raw captures and needs the network.
- `sources.py`, `match.py` and `layout.py` are pure: they normalise and match with no I/O.
- `build.py` and `render.py` assemble the run directory and the HTML.

Every run directory keeps its raw captures, so `rebuild` works offline and a Canberra regression can
pin the behaviour.

**Tech Stack:** Python 3.11+, pandas 2.x, requests, stdlib `html.parser`, pytest. The EdgeProp
Playwright scraper already in the repo is called as a subprocess.

**Spec:** `docs/superpowers/specs/2026-09-26-unit-ledger-design.md`

## Global Constraints

- No new dependencies. HTML parsing uses the stdlib `html.parser` (no bs4). Network code uses
  `requests`, as `scrapers/ura_pmi_api.py` already does.
- Outputs are written only under `data/runs/unit-ledger/<project-slug>/<YYYY-MM-DD>/`, which Git
  ignores. Nothing is written to the repository root, `data/inputs/` or `data/outputs/`.
- `URA_ACCESS_KEY` is read only from the environment. It is never printed, logged or written to disk.
- Source precedence for conflicting values: URA > EdgeProp > PropertyNoob > chart > recent-sales
  list. Conflicts are recorded in the `conflict` column, never dropped.
- The unit-match labels are exact strings. The page and README show them verbatim:
  - `Published`
  - `Published (identical sales, matched as a set)`
  - `Published (date ±N days)`
  - `Published (PropertyNoob only)`
  - `Determined by block, floor and size`
  - `Inferred (unit chart sold date + EdgeProp block and floor)`
  - `Inferred (recent-sales list + EdgeProp block and floor)`
  - `By elimination (last chart-sold unit of this size and floor without a New Sale)`
  - `Ambiguous: <candidates>`
  - `Not found`
- Elimination applies to `New Sale` rows only, and only when a chart exists.
- No floor-plan images are downloaded or embedded; plan types are text parsed from the chart's image
  file names.
- Every test in `make smoke` runs offline. The Canberra regression test skips when its local captures
  are absent.
- Commits use the repository's conventional prefixes and end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Blocks written as `57A` or with no leading number.** The row stays unlocated (block `""`) instead
   of crashing, and it still appears in the table. Tested in Task 2
   (`test_load_edgeprop_keeps_rows_without_a_block_number`).
2. **URA floor ranges that are not five-floor bands** (`-`, `B1-B5`). Loading succeeds; such rows get
   no EdgeProp link and remain undated. Tested in Task 3
   (`test_unbanded_ura_floor_ranges_stay_unmatched_without_error`).
3. **PropertyNoob tokens like `#PH-01` or `#B1-02`.** They are excluded from matching without error.
   Tested in Task 2 (`test_load_propertynoob_keeps_exact_numeric_units_only`).
4. **A project listed in EdgeProp under different letter case.** Lookup is case-insensitive; an
   unlisted project triggers discovery instead of failing. Tested in Task 5.
5. **Running the same project twice on one day.** The old directory is replaced only after the new
   run succeeds, and a failed run leaves no partial directory. Tested in Task 5.

---

### Task 1: Move the PropertyNoob parser into `scrapers/` and create the package

The tested parser currently lives in the Git-ignored `data/runs/propertynoob-sales/2026-09-20/`.
Nothing tracked imports it, so moving it is safe.

**Files:**
- Create: `scrapers/propertynoob_sales.py` (copied verbatim from `data/runs/propertynoob-sales/2026-09-20/propertynoob_sales.py`)
- Create: `tests/test_propertynoob_sales.py` (copied from `data/runs/propertynoob-sales/2026-09-20/test_propertynoob_sales.py`, with the import changed)
- Create: `scrapers/unit_ledger/__init__.py`
- Commit: `docs/superpowers/specs/2026-09-26-unit-ledger-design.md` (already amended on disk)

**Interfaces:**
- Produces: `scrapers.propertynoob_sales.parse_sales_html(html, *, project_name, source_url, fetched_at_utc, source_slug=None) -> list[dict]`
  (unchanged). Each row dict has `source_row_number`, `sale_date`, `price_sgd`, `unit_number`,
  `unit_number_status`, `area_sqft` and `sale_type`.

- [ ] **Step 1: Copy the parser and its tests**

```bash
cp data/runs/propertynoob-sales/2026-09-20/propertynoob_sales.py scrapers/propertynoob_sales.py
cp data/runs/propertynoob-sales/2026-09-20/test_propertynoob_sales.py tests/test_propertynoob_sales.py
sed -i '' 's/^from propertynoob_sales import /from scrapers.propertynoob_sales import /' tests/test_propertynoob_sales.py
grep -n "^from scrapers.propertynoob_sales import" tests/test_propertynoob_sales.py
```

Expected: one line, `from scrapers.propertynoob_sales import main, parse_sales_html, write_sales_csv`.

- [ ] **Step 2: Create the package marker**

`scrapers/unit_ledger/__init__.py`:

```python
"""Per-project unit ledger: URA transactions matched to exact dates and units, with a site view."""
```

- [ ] **Step 3: Run the moved tests**

Run: `python3 -m pytest tests/test_propertynoob_sales.py -q`
Expected: all tests PASS. The count equals the number of `def test_` functions in the file.

- [ ] **Step 4: Commit**

```bash
git add scrapers/propertynoob_sales.py tests/test_propertynoob_sales.py scrapers/unit_ledger/__init__.py docs/superpowers/specs/2026-09-26-unit-ledger-design.md
git commit -m "feat(scrapers): adopt the PropertyNoob sales parser and start the unit ledger

Moves the tested parser out of an ignored research run so the unit
ledger can import it. Amends the spec with EdgeProp multiset union,
block/floor/size and chart-date rules found while validating the design.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Source normalisers and the unit-chart parser (`sources.py`)

**Files:**
- Create: `scrapers/unit_ledger/sources.py`
- Test: `tests/test_unit_ledger_sources.py`

**Interfaces:**
- Consumes: `scrapers.propertynoob_sales.parse_sales_html` (Task 1).
- Produces:
  - `SQFT_PER_SQM: float = 10.7639`
  - `floor_band(floor: int) -> str`, e.g. `7 -> "06-10"`
  - `slugify(name: str) -> str`, e.g. `"Canberra Crescent Residences" -> "canberra-crescent-residences"`
  - `load_ura(records: list[dict]) -> DataFrame` with columns `txn_id, sale_month, price, area_sqm, area_decimals, floor_level, type_of_sale, tenure`
  - `load_edgeprop(frames: list[DataFrame]) -> DataFrame` with columns `ep_id, sale_date, block, floor(Int64), price, area_sqm, area_sqft, bedrooms(Int64), type_of_sale, sale_month, floor_level`
  - `PN_COLUMNS = ["pn_id","sale_date","price","unit","floor","stack","area_sqft","type_of_sale"]`
  - `load_propertynoob(html: str, *, source_url: str, fetched_at_utc: str) -> DataFrame[PN_COLUMNS]` and `empty_propertynoob()`
  - `CHART_COLUMNS = ["block","unit","floor","stack","area_sqft","bedrooms","unit_type","chart_status","chart_sold_date"]`
  - `class ChartTemplateError(ValueError)`
  - `parse_chart(html: str) -> tuple[DataFrame[CHART_COLUMNS], str]`, where the string is the chart's as-of date (ISO)
  - `RECENT_COLUMNS = ["date","unit"]`
  - `load_recent_sales(frame: DataFrame) -> DataFrame[RECENT_COLUMNS]` and `empty_recent_sales()`
  - Blocks and stacks are always `str`; floors, prices and sqft are `int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_unit_ledger_sources.py`:

```python
"""Offline tests for unit-ledger source normalisers and the unit-chart parser."""

import pandas as pd
import pytest

from scrapers.unit_ledger import sources


def _ura(*txns):
    return [{
        "project": "DEMO",
        "street": "DEMO ROAD",
        "transaction": [
            {"contractDate": c, "price": str(p), "area": a, "floorRange": f,
             "typeOfSale": t, "noOfUnits": n, "tenure": "99 yrs"}
            for c, p, a, f, t, n in txns
        ],
    }]


def _ep(*rows):
    return pd.DataFrame([
        {"Date of Sale": d, "Street": street, "Address": f"{street} #{fl}-XX",
         "Price ($)": str(p), "Area (sqm)": sqm, "Area (sqft)": sqft,
         "Bedrooms": beds, "Sale Type": s}
        for d, street, fl, p, sqm, sqft, beds, s in rows
    ], dtype=str)


ROW_A = ("26 Aug 2026", "57 DEMO ROAD", "06", 2469854, "112.97", "1216", "4", "New Sale")
ROW_B = ("8 Aug 2026", "53 DEMO ROAD", "04", 2380000, "112.97", "1216", "4", "New Sale")


def _pn_html(rows):
    head = ("<tr><th></th><th>Date</th><th>Price</th><th>Unit</th><th>Area (sqft)</th>"
            "<th>PSF</th><th>Type</th><th>Sale</th></tr>")
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"


CHART = """<html><body><h1>Demo</h1><div> Available units as of 26 Sep 2026 </div>
<div class="tabs" id="tab-3"><ul class="tab-nav"><li><a href="#tabs-0">Blk 51</a></li></ul>
<div class="tab-container"><div class="tab-content" id="tabs-0"><table>
<thead><tr><th></th><th>#01</th><th>#02</th></tr></thead>
<tbody>
<tr><th>2</th>
<td><a href="https://img.example/floorPlanImg/20250708/2BR-C.png?quality=50"> 570 sqft <br /> 2 BR <br />
<strong>SOLD</strong> <br /> <strong> 01 Aug 2025 </strong></a></td>
<td><a href="https://img.example/floorPlanImg/20250708/3BR-Cb(PES).png?quality=50"> 1,216 sqft <br /> 3 BR </a></td>
</tr>
<tr><th>1</th><td></td><td><a href="https://img.example/floorPlanImg/1/1BR.png"> 409 sqft <br /> 1 BR </a></td></tr>
</tbody></table></div></div></div></body></html>"""


def test_floor_band_and_slugify():
    assert [sources.floor_band(f) for f in (1, 5, 6, 12, 51)] == ["01-05", "01-05", "06-10", "11-15", "51-55"]
    assert sources.slugify("  The Poiz Residences ") == "the-poiz-residences"


def test_load_ura_maps_sale_types_months_and_area_precision():
    ura = sources.load_ura(_ura(("0826", 2469854, "113", "06-10", "1", "1"),
                                ("0319", 900000, "92.5", "01-05", "3", "1")))
    assert list(ura.txn_id) == ["ura-1", "ura-2"]
    assert list(ura.sale_month) == ["2026-08", "2019-03"]
    assert list(ura.type_of_sale) == ["New Sale", "Resale"]
    assert list(ura.area_decimals) == [0, 1]
    assert list(ura.price) == [2469854, 900000]


def test_load_ura_rejects_bulk_transactions():
    with pytest.raises(ValueError, match="bulk"):
        sources.load_ura(_ura(("0826", 5000000, "400", "01-05", "1", "4")))


def test_load_edgeprop_takes_multiset_union_of_captures():
    ep = sources.load_edgeprop([_ep(ROW_A, ROW_A), _ep(ROW_A, ROW_B)])
    assert len(ep) == 3
    assert (ep.block == "57").sum() == 2
    row = ep[ep.block == "53"].iloc[0]
    assert (row.sale_date, row.floor, row.floor_level, row.area_sqft, row.sale_month) == (
        "2026-08-08", 4, "01-05", 1216, "2026-08")
    assert list(ep.ep_id) == ["ep-1", "ep-2", "ep-3"]


def test_load_edgeprop_rejects_unknown_sale_type():
    with pytest.raises(ValueError, match="sale type"):
        sources.load_edgeprop([_ep(ROW_A[:-1] + ("Auction",))])


def test_load_edgeprop_keeps_rows_without_a_block_number():
    ep = sources.load_edgeprop([_ep(("26 Aug 2026", "DEMO ROAD", "06", 2469854, "112.97", "1216", "-", "New Sale"))])
    assert ep.iloc[0].block == "" and pd.isna(ep.iloc[0].bedrooms)


def test_load_edgeprop_with_no_captures_is_empty_but_typed():
    ep = sources.load_edgeprop([])
    assert ep.empty and str(ep.area_sqm.dtype) == "float64"


def test_load_propertynoob_keeps_exact_numeric_units_only():
    html = _pn_html([
        ["4", "3 Apr 2026", "$1,981,100", "#05-07", "990", "$2,001", "Apartment", "New"],
        ["3", "2 Mar 2026", "$3,000,000", "#PH-01", "1,500", "$2,000", "Apartment", "New"],
        ["2", "2 Aug 2025", "$880,000", "#01-XX", "409", "$2,152", "Apartment", "New"],
        ["1", "1 Aug 2025", "$1,000,000", "#B1-02", "500", "$2,000", "Apartment", "Resale"],
    ])
    pn = sources.load_propertynoob(html, source_url="https://propertynoob.com/condo/demo/sales",
                                   fetched_at_utc="2026-09-26T00:00:00Z")
    assert list(pn.pn_id) == ["pn-4"]
    row = pn.iloc[0]
    assert (row.unit, row.floor, row.stack, row.area_sqft, row.type_of_sale) == ("#05-07", 5, "07", 990, "New Sale")


def test_parse_chart_reads_units_status_and_plan_types():
    chart, as_of = sources.parse_chart(CHART)
    assert as_of == "2026-09-26"
    assert list(chart.columns) == sources.CHART_COLUMNS
    rows = {u.unit: u for u in chart.itertuples()}
    assert set(rows) == {"#02-01", "#02-02", "#01-02"}
    assert (rows["#02-01"].chart_status, rows["#02-01"].chart_sold_date, rows["#02-01"].unit_type) == (
        "sold", "2025-08-01", "2BR-C")
    assert (rows["#02-02"].area_sqft, rows["#02-02"].bedrooms, rows["#02-02"].unit_type,
            rows["#02-02"].chart_status) == (1216, 3, "3BR-Cb (PES)", "available")
    assert (rows["#01-02"].block, rows["#01-02"].floor, rows["#01-02"].stack) == ("51", 1, "02")


def test_parse_chart_rejects_other_templates():
    with pytest.raises(sources.ChartTemplateError, match="unsupported"):
        sources.parse_chart("<html><body><table><tr><td>#01-01</td></tr></table></body></html>")


def test_parse_chart_rejects_an_unreadable_cell():
    with pytest.raises(sources.ChartTemplateError, match="unreadable unit cell"):
        sources.parse_chart(CHART.replace("409 sqft", "Studio"))


def test_load_recent_sales_validates_units():
    ok = sources.load_recent_sales(pd.DataFrame({"date": ["2026-09-24"], "unit": [" #01-18 "]}))
    assert list(ok.unit) == ["#01-18"]
    with pytest.raises(ValueError, match="unit number"):
        sources.load_recent_sales(pd.DataFrame({"date": ["2026-09-24"], "unit": ["01-18"]}))
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_unit_ledger_sources.py -q`
Expected: FAIL with `ImportError: cannot import name 'sources'`.

- [ ] **Step 3: Implement `scrapers/unit_ledger/sources.py`**

```python
"""Parse raw unit-ledger captures into normalised frames. No network access, no file I/O."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import unquote

import pandas as pd

from scrapers.propertynoob_sales import parse_sales_html

SQFT_PER_SQM = 10.7639
URA_SALE_TYPES = {"1": "New Sale", "2": "Sub Sale", "3": "Resale"}
SALE_TYPES = frozenset(URA_SALE_TYPES.values())

EP_REQUIRED = ["Date of Sale", "Street", "Address", "Price ($)", "Area (sqm)", "Area (sqft)", "Bedrooms", "Sale Type"]
EP_FIELDS = ["sale_date", "block", "floor", "price", "area_sqm", "area_sqft", "bedrooms", "type_of_sale"]
PN_COLUMNS = ["pn_id", "sale_date", "price", "unit", "floor", "stack", "area_sqft", "type_of_sale"]
CHART_COLUMNS = ["block", "unit", "floor", "stack", "area_sqft", "bedrooms", "unit_type", "chart_status", "chart_sold_date"]
RECENT_COLUMNS = ["date", "unit"]

_CELL = re.compile(r"([\d,]+) sqft (\d+) BR(?: SOLD (\d{1,2} \w{3} \d{4}))?")
_PLAN = re.compile(r"floorPlanImg/[^/]+/([^/?]+)\.\w+(?:\?|$)")
_UNIT = re.compile(r"#(\d+)-(\d+[A-Z]?)")


class ChartTemplateError(ValueError):
    """The unit-chart page is not the supported singmap agent-site template."""


def floor_band(floor: int) -> str:
    """URA five-floor band containing ``floor``, e.g. 7 -> '06-10'."""
    low = (int(floor) - 1) // 5 * 5 + 1
    return f"{low:02d}-{low + 4:02d}"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _iso(text: str) -> str:
    return datetime.strptime(" ".join(text.split()), "%d %b %Y").date().isoformat()


def _number(value) -> float:
    return float(str(value).replace(",", "").replace("$", "").strip())


# --- URA ---------------------------------------------------------------------

def load_ura(records: list[dict]) -> pd.DataFrame:
    """One row per URA PMI_Resi_Transaction record, in API order."""
    rows = []
    for project in records:
        for txn in project.get("transaction") or []:
            if str(txn.get("noOfUnits", "1")) != "1":
                raise ValueError(f"bulk URA transaction ({txn.get('noOfUnits')} units) is not supported: {txn}")
            sale = URA_SALE_TYPES.get(str(txn.get("typeOfSale")))
            if sale is None:
                raise ValueError(f"unknown URA typeOfSale: {txn.get('typeOfSale')!r}")
            month = str(txn.get("contractDate", ""))
            if not re.fullmatch(r"(0[1-9]|1[0-2])\d{2}", month):
                raise ValueError(f"invalid URA contractDate: {month!r}")
            area = str(txn["area"]).strip()
            rows.append({
                "sale_month": f"20{month[2:]}-{month[:2]}",
                "price": int(_number(txn["price"])),
                "area_sqm": float(area),
                "area_decimals": len(area.split(".", 1)[1]) if "." in area else 0,
                "floor_level": str(txn.get("floorRange", "")).strip(),
                "type_of_sale": sale,
                "tenure": str(txn.get("tenure", "")).strip(),
            })
    if not rows:
        raise ValueError("URA records contain no transactions")
    frame = pd.DataFrame(rows)
    frame.insert(0, "txn_id", [f"ura-{i}" for i in range(1, len(frame) + 1)])
    return frame


# --- EdgeProp ----------------------------------------------------------------

def _edgeprop_rows(frame: pd.DataFrame) -> list[tuple]:
    if frame.empty:
        return []
    missing = [c for c in EP_REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"EdgeProp capture is missing columns {missing}")
    rows = []
    for record in frame[EP_REQUIRED].itertuples(index=False):
        sale_date, street, address, price, sqm, sqft, beds, sale = (str(v).strip() for v in record)
        if sale not in SALE_TYPES:
            raise ValueError(f"unknown EdgeProp sale type: {sale!r}")
        block = re.match(r"(\d+[A-Z]?)\b", street)
        floor = re.search(r"#(\d+)-", address)
        bedrooms = pd.to_numeric(beds, errors="coerce")
        rows.append((
            _iso(sale_date),
            block.group(1) if block else "",
            int(floor.group(1)) if floor else None,
            int(_number(price)),
            round(_number(sqm), 3),
            int(round(_number(sqft))),
            None if pd.isna(bedrooms) else int(bedrooms),
            sale,
        ))
    return rows


def load_edgeprop(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Multiset union of EdgeProp captures.

    A row value seen k times in one capture and j times in another counts max(k, j) times:
    captures of the same page overlap, and pagination drops different rows on each pass.
    """
    union: Counter = Counter()
    for frame in frames:
        for key, count in Counter(_edgeprop_rows(frame)).items():
            union[key] = max(union[key], count)
    rows = [key for key, count in union.items() for _ in range(count)]
    ep = pd.DataFrame(rows, columns=EP_FIELDS).astype({
        "price": "int64", "area_sqm": "float64", "area_sqft": "int64", "floor": "Int64", "bedrooms": "Int64",
    })
    ep = ep.sort_values(["sale_date", "block", "floor", "price"], kind="stable").reset_index(drop=True)
    ep["sale_month"] = ep.sale_date.str[:7]
    ep["floor_level"] = [floor_band(f) if pd.notna(f) else "" for f in ep.floor]
    ep.insert(0, "ep_id", [f"ep-{i}" for i in range(1, len(ep) + 1)])
    return ep


# --- PropertyNoob ------------------------------------------------------------

def empty_propertynoob() -> pd.DataFrame:
    return pd.DataFrame(columns=PN_COLUMNS)


def load_propertynoob(html: str, *, source_url: str, fetched_at_utc: str) -> pd.DataFrame:
    """Rows with an exact numeric #FF-SS unit. Masked, penthouse and basement tokens are dropped."""
    rows = []
    for record in parse_sales_html(html, project_name="unit-ledger", source_url=source_url,
                                   fetched_at_utc=fetched_at_utc):
        unit = _UNIT.fullmatch(record["unit_number"]) if record["unit_number_status"] == "exact" else None
        if unit is None:
            continue
        rows.append({
            "pn_id": f"pn-{record['source_row_number']}",
            "sale_date": record["sale_date"],
            "price": record["price_sgd"],
            "unit": record["unit_number"],
            "floor": int(unit.group(1)),
            "stack": unit.group(2),
            "area_sqft": record["area_sqft"],
            "type_of_sale": record["sale_type"],
        })
    return pd.DataFrame(rows, columns=PN_COLUMNS)


# --- Unit chart (singmap agent-site template) ---------------------------------

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _Node:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children: list = []

    def text(self) -> str:
        parts = [c if isinstance(c, str) else c.text() for c in self.children]
        return " ".join(" ".join(parts).split())

    def iter(self, tag=None):
        for child in self.children:
            if isinstance(child, _Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.iter(tag)

    def by_id(self, element_id):
        return next((n for n in self.iter() if n.attrs.get("id") == element_id), None)


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", [], None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in _VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(_Node(tag, attrs, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse_chart(html: str) -> tuple[pd.DataFrame, str]:
    """Parse the per-block 'Tower View' grid of a singmap agent unit chart."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    root = builder.root
    as_of = re.search(r"Available units as of (\d{1,2} \w{3} \d{4})", root.text())
    tabs = root.by_id("tab-3")
    if as_of is None or tabs is None:
        raise ChartTemplateError(
            "unsupported unit-chart template: expected 'Available units as of <date>' and a #tab-3 block-tab container")
    rows = []
    for link in tabs.iter("a"):
        target = link.attrs.get("href") or ""
        if not target.startswith("#tabs-"):
            continue
        block = re.fullmatch(r"Blk\s+(\w+)", link.text())
        pane = root.by_id(target[1:])
        table = next(pane.iter("table"), None) if pane is not None else None
        header = next(table.iter("thead"), None) if table is not None else None
        body = next(table.iter("tbody"), None) if table is not None else None
        if block is None or header is None or body is None:
            raise ChartTemplateError(f"unsupported block tab {link.text()!r}")
        stacks = [th.text().lstrip("#") for th in header.iter("th")][1:]
        for tr in body.iter("tr"):
            cells = [c for c in tr.children if isinstance(c, _Node) and c.tag in ("th", "td")]
            try:
                floor = int(cells[0].text())
            except (IndexError, ValueError):
                raise ChartTemplateError(f"Blk {block.group(1)}: unreadable floor row {tr.text()[:60]!r}") from None
            for stack, cell in zip(stacks, cells[1:]):
                text = cell.text()
                if not text:
                    continue
                found = _CELL.fullmatch(text)
                anchor = next(cell.iter("a"), None)
                plan = _PLAN.search(anchor.attrs.get("href") or "") if anchor is not None else None
                if found is None or plan is None:
                    raise ChartTemplateError(
                        f"Blk {block.group(1)} floor {floor} stack {stack}: unreadable unit cell {text!r}")
                rows.append({
                    "block": block.group(1),
                    "unit": f"#{floor:02d}-{stack}",
                    "floor": floor,
                    "stack": stack,
                    "area_sqft": int(found.group(1).replace(",", "")),
                    "bedrooms": int(found.group(2)),
                    "unit_type": unquote(plan.group(1)).replace("(", " ("),
                    "chart_status": "sold" if found.group(3) else "available",
                    "chart_sold_date": _iso(found.group(3)) if found.group(3) else "",
                })
    if not rows:
        raise ChartTemplateError("unsupported unit-chart template: no units found")
    return pd.DataFrame(rows, columns=CHART_COLUMNS), _iso(as_of.group(1))


# --- Recent-sales list -----------------------------------------------------------

def empty_recent_sales() -> pd.DataFrame:
    return pd.DataFrame(columns=RECENT_COLUMNS)


def load_recent_sales(frame: pd.DataFrame) -> pd.DataFrame:
    """A developer's 'recently sold' list: dates and unit numbers only, never prices."""
    missing = [c for c in RECENT_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"recent-sales CSV is missing columns {missing}")
    out = frame[RECENT_COLUMNS].astype(str).apply(lambda column: column.str.strip())
    for sale_date, unit in zip(out.date, out.unit):
        date.fromisoformat(sale_date)
        if not _UNIT.fullmatch(unit):
            raise ValueError(f"recent-sales unit {unit!r} is not a #FF-SS unit number")
    return out.reset_index(drop=True)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_unit_ledger_sources.py -q`
Expected: 12 passed.

- [ ] **Step 5: Check the parser against the real Canberra chart**

```bash
python3 -c "
from pathlib import Path
from scrapers.unit_ledger import sources
chart, as_of = sources.parse_chart(Path('data/runs/unit-ledger-regression/canberra-crescent-residences/raw/chart.html').read_text())
print(as_of, len(chart), chart.chart_status.value_counts().to_dict(), chart.unit_type.nunique())"
```

Expected: `2026-09-26 376 {'sold': 351, 'available': 25} 26`. Skip this step if the directory is
absent.

- [ ] **Step 6: Commit**

```bash
git add scrapers/unit_ledger/sources.py tests/test_unit_ledger_sources.py
git commit -m "feat(unit-ledger): normalise URA, EdgeProp, PropertyNoob and unit-chart sources

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Matching rules and unit layout (`match.py`, `layout.py`)

**Files:**
- Create: `scrapers/unit_ledger/layout.py`
- Create: `scrapers/unit_ledger/match.py`
- Test: `tests/test_unit_ledger_match.py`

**Interfaces:**
- Consumes: everything `sources` produces (Task 2).
- Produces:
  - `layout.LAYOUT_COLUMNS` (equal to `sources.CHART_COLUMNS`) and `layout.UNIT_COLUMNS = ["block","unit","floor","stack","area_sqft","bedrooms","unit_type","layout_source","status","sale_count","first_txn_id","latest_txn_id","note"]`
  - `layout.stack_blocks(units) -> dict[str, set[str]]`
  - `layout.derived_units(ledger) -> DataFrame[LAYOUT_COLUMNS]`
  - `layout.summarise_units(units, ledger, recent, has_chart) -> DataFrame[UNIT_COLUMNS]`. `status` is one of `sold`, `sold_pre_window_only`, `sold_pending_ura`, `available` or `unknown`.
  - `match.LEDGER_COLUMNS` (the `transactions.csv` schema in the spec, in that order)
  - `match.MatchResult(ledger, units, unmatched_edgeprop: int, unmatched_propertynoob: int)`
  - `match.match_all(ura, ep, pn, chart_or_None, recent) -> MatchResult`
  - `match.uniquely_located_count(ledger, units) -> int`

- [ ] **Step 1: Write the failing tests**

`tests/test_unit_ledger_match.py`:

```python
"""Offline tests for unit-ledger matching rules and the per-unit summary."""

import pandas as pd

from scrapers.unit_ledger import layout, match, sources


def ura(*txns):
    """txns: (mmyy, price, sqm, floor band, URA typeOfSale code)."""
    return sources.load_ura([{"project": "DEMO", "transaction": [
        {"contractDate": c, "price": str(p), "area": str(a), "floorRange": f, "typeOfSale": t,
         "noOfUnits": "1", "tenure": "99 yrs"} for c, p, a, f, t in txns]}])


def ep(*rows):
    """rows: (d Mon yyyy, block, floor, price, sqm, sqft, sale type)."""
    return sources.load_edgeprop([pd.DataFrame([
        {"Date of Sale": d, "Street": f"{b} DEMO ROAD", "Address": f"{b} DEMO ROAD #{fl:02d}-XX",
         "Price ($)": str(p), "Area (sqm)": str(sqm), "Area (sqft)": str(sqft), "Bedrooms": "3", "Sale Type": s}
        for d, b, fl, p, sqm, sqft, s in rows], dtype=str)])


def pn(*rows):
    """rows: (iso date, price, #FF-SS, sqft, sale type)."""
    return pd.DataFrame([
        {"pn_id": f"pn-{i}", "sale_date": d, "price": p, "unit": u, "floor": int(u[1:3]), "stack": u[4:],
         "area_sqft": s, "type_of_sale": t}
        for i, (d, p, u, s, t) in enumerate(rows, 1)], columns=sources.PN_COLUMNS)


def chart(*units):
    """units: (block, #FF-SS, sqft, chart status, chart sold date)."""
    return pd.DataFrame([
        {"block": b, "unit": u, "floor": int(u[1:3]), "stack": u[4:], "area_sqft": s, "bedrooms": 3,
         "unit_type": "3BR", "chart_status": st, "chart_sold_date": sd}
        for b, u, s, st, sd in units], columns=sources.CHART_COLUMNS)


NO_RECENT = sources.empty_recent_sales()


def test_ura_row_takes_exact_date_block_and_floor_from_edgeprop():
    r = match.match_all(ura(("0826", 2469854, 113, "06-10", "1")),
                        ep(("26 Aug 2026", "57", 6, 2469854, 112.97, 1216, "New Sale")), pn(), None, NO_RECENT)
    row = r.ledger.iloc[0]
    assert (row.sale_date, row.block, row.floor, row.area_sqft, row.date_source) == (
        "2026-08-26", "57", 6, 1216, "EdgeProp (URA record)")
    assert row.psf == round(2469854 / 1216)


def test_disagreeing_edgeprop_candidates_leave_the_row_undated():
    r = match.match_all(ura(("0826", 2469854, 113, "06-10", "1")),
                        ep(("26 Aug 2026", "57", 6, 2469854, 112.97, 1216, "New Sale"),
                           ("20 Aug 2026", "55", 7, 2469854, 112.97, 1216, "New Sale")), pn(), None, NO_RECENT)
    row = r.ledger.iloc[0]
    assert row.sale_date == "" and "2 candidates for 1" in row.conflict


def test_unbanded_ura_floor_ranges_stay_unmatched_without_error():
    r = match.match_all(ura(("0826", 2469854, 113, "-", "1")),
                        ep(("26 Aug 2026", "57", 6, 2469854, 112.97, 1216, "New Sale")), pn(), None, NO_RECENT)
    assert r.ledger.iloc[0].sale_date == "" and r.unmatched_edgeprop == 1


def test_edgeprop_rows_before_the_ura_window_become_flagged_pre_window_rows():
    r = match.match_all(ura(("1021", 1500000, 92, "01-05", "3")),
                        ep(("15 Oct 2021", "51", 3, 1500000, 91.97, 990, "Resale"),
                           ("2 Aug 2016", "51", 3, 1100000, 91.97, 990, "New Sale")),
                        pn(("2021-10-15", 1500000, "#03-07", 990, "Resale"),
                           ("2016-08-02", 1100000, "#03-07", 990, "New Sale")), None, NO_RECENT)
    pre = r.ledger[r.ledger.origin == "Pre-window"].iloc[0]
    assert (pre.sale_date, pre.block, pre.unit, pre.price) == ("2016-08-02", "51", "#03-07", 1100000)
    assert "not verified against URA API" in pre.date_source


def test_a_unit_can_have_a_new_sale_and_a_later_resale():
    r = match.match_all(ura(("0822", 1500000, 92, "01-05", "1"), ("0825", 1800000, 92, "01-05", "3")),
                        ep(("2 Aug 2022", "51", 3, 1500000, 91.97, 990, "New Sale"),
                           ("9 Aug 2025", "51", 3, 1800000, 91.97, 990, "Resale")),
                        pn(("2022-08-02", 1500000, "#03-07", 990, "New Sale"),
                           ("2025-08-09", 1800000, "#03-07", 990, "Resale")), None, NO_RECENT)
    assert list(r.ledger.unit) == ["#03-07", "#03-07"]
    assert set(r.ledger.unit_source) == {"Published"}
    units = layout.summarise_units(r.units, r.ledger, NO_RECENT, has_chart=False)
    assert (units.iloc[0].sale_count, units.iloc[0].first_txn_id, units.iloc[0].latest_txn_id) == (2, "ura-1", "ura-2")


def test_identical_sales_in_one_block_are_matched_as_a_set():
    r = match.match_all(ura(("0825", 1372700, 62, "06-10", "1"), ("0825", 1372700, 62, "06-10", "1")),
                        ep(("17 Aug 2025", "55", 7, 1372700, 61.97, 667, "New Sale"),
                           ("17 Aug 2025", "55", 7, 1372700, 61.97, 667, "New Sale")),
                        pn(("2025-08-17", 1372700, "#07-20", 667, "New Sale"),
                           ("2025-08-17", 1372700, "#07-17", 667, "New Sale")),
                        chart(("55", "#07-17", 667, "sold", "2025-08-17"), ("55", "#07-20", 667, "sold", "2025-08-17")),
                        NO_RECENT)
    assert sorted(r.ledger.unit) == ["#07-17", "#07-20"]
    assert set(r.ledger.unit_source) == {"Published (identical sales, matched as a set)"}


def test_propertynoob_date_within_three_days_is_accepted_only_when_unique():
    sale = ura(("0825", 1372700, 62, "06-10", "1"))
    edge = ep(("17 Aug 2025", "55", 7, 1372700, 61.97, 667, "New Sale"))
    grid = chart(("55", "#07-17", 667, "sold", "2025-08-01"), ("55", "#07-20", 667, "sold", "2025-08-01"))
    one = match.match_all(sale, edge, pn(("2025-08-15", 1372700, "#07-20", 667, "New Sale")), grid, NO_RECENT)
    assert (one.ledger.iloc[0].unit, one.ledger.iloc[0].unit_source) == ("#07-20", "Published (date ±2 days)")
    assert "PropertyNoob dates this sale 2025-08-15" in one.ledger.iloc[0].conflict
    two = match.match_all(sale, edge, pn(("2025-08-15", 1372700, "#07-20", 667, "New Sale"),
                                         ("2025-08-16", 1372700, "#07-17", 667, "New Sale")), grid, NO_RECENT)
    assert two.ledger.iloc[0].unit == ""
    assert two.ledger.iloc[0].unit_source == "Ambiguous: 55 #07-17 / 55 #07-20"


def test_block_floor_and_size_determine_the_unit_without_propertynoob():
    grid = chart(("55", "#04-23", 990, "available", ""), ("55", "#04-24", 797, "sold", "2025-08-01"),
                 ("57", "#04-26", 990, "sold", "2026-09-21"))
    r = match.match_all(ura(("0926", 2050906, 92, "01-05", "1")),
                        ep(("17 Sep 2026", "55", 4, 2050906, 91.97, 990, "New Sale")), pn(), grid, NO_RECENT)
    row = r.ledger.iloc[0]
    assert (row.block, row.unit, row.unit_source) == ("55", "#04-23", "Determined by block, floor and size")
    units = layout.summarise_units(r.units, r.ledger, NO_RECENT, has_chart=True).set_index("unit")
    assert units.at["#04-23", "status"] == "sold"
    assert "Unit chart still shows it available" in units.at["#04-23", "note"]
    assert match.uniquely_located_count(r.ledger, r.units) == 1


def test_chart_sold_date_picks_between_same_size_units_on_a_floor():
    grid = chart(("55", "#09-23", 990, "sold", "2026-04-28"), ("55", "#09-19", 990, "sold", "2025-08-01"))
    r = match.match_all(ura(("0426", 2056100, 92, "06-10", "1")),
                        ep(("29 Apr 2026", "55", 9, 2056100, 91.97, 990, "New Sale")), pn(), grid, NO_RECENT)
    assert (r.ledger.iloc[0].unit, r.ledger.iloc[0].unit_source) == (
        "#09-23", "Inferred (unit chart sold date + EdgeProp block and floor)")


def test_recent_sales_list_picks_the_unit_when_the_chart_is_silent():
    recent = sources.load_recent_sales(pd.DataFrame({"date": ["2026-09-07"], "unit": ["#05-30"]}))
    grid = chart(("57", "#05-30", 1216, "available", ""), ("57", "#05-31", 1216, "available", ""))
    r = match.match_all(ura(("0926", 2463693, 113, "01-05", "1")),
                        ep(("7 Sep 2026", "57", 5, 2463693, 112.97, 1216, "New Sale")), pn(), grid, recent)
    assert (r.ledger.iloc[0].unit, r.ledger.iloc[0].unit_source) == (
        "#05-30", "Inferred (recent-sales list + EdgeProp block and floor)")


def test_elimination_applies_to_new_sales_only():
    grid = chart(("51", "#10-04", 667, "sold", "2025-08-30"), ("51", "#10-05", 797, "sold", "2025-08-01"))
    new = match.match_all(ura(("1025", 1359400, 62, "06-10", "1")), ep(), pn(), grid, NO_RECENT)
    assert (new.ledger.iloc[0].block, new.ledger.iloc[0].unit) == ("51", "#10-04")
    assert new.ledger.iloc[0].unit_source.startswith("By elimination")
    resale = match.match_all(ura(("1025", 1359400, 62, "06-10", "3")), ep(), pn(), grid, NO_RECENT)
    assert resale.ledger.iloc[0].unit == ""
    assert resale.ledger.iloc[0].unit_source == "Ambiguous: 51 #10-04"


def test_lapsed_booking_leaves_its_propertynoob_row_unmatched():
    grid = chart(("51", "#10-04", 667, "sold", "2025-08-30"), ("51", "#10-05", 797, "sold", "2025-08-01"))
    r = match.match_all(
        ura(("0825", 1550400, 74, "06-10", "1"), ("1025", 1359400, 62, "06-10", "1")),
        ep(("2 Aug 2025", "51", 10, 1550400, 74.04, 797, "New Sale"),
           ("1 Oct 2025", "51", 10, 1359400, 61.97, 667, "New Sale")),
        pn(("2025-08-02", 1550400, "#10-05", 797, "New Sale"), ("2025-08-02", 1346100, "#10-04", 667, "New Sale")),
        grid, NO_RECENT)
    lapsed = r.ledger[r.ledger.txn_id == "ura-2"].iloc[0]
    assert (lapsed.unit, lapsed.unit_source) == ("#10-04", "Determined by block, floor and size")
    assert r.unmatched_propertynoob == 1 and len(r.ledger) == 2


def test_summary_marks_pending_available_and_unknown_units():
    grid = chart(("57", "#04-30", 1216, "available", ""), ("57", "#10-30", 1216, "sold", "2026-08-09"),
                 ("57", "#03-30", 1216, "available", ""))
    recent = sources.load_recent_sales(pd.DataFrame({"date": ["2026-09-24"], "unit": ["#04-30"]}))
    empty = pd.DataFrame(columns=match.LEDGER_COLUMNS)
    units = layout.summarise_units(grid, empty, recent, has_chart=True).set_index("unit")
    assert units.at["#04-30", "status"] == "sold_pending_ura"
    assert "developer site sold 2026-09-24" in units.at["#04-30", "note"]
    assert units.at["#10-30", "status"] == "sold_pending_ura"
    assert units.at["#03-30", "status"] == "available"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_unit_ledger_match.py -q`
Expected: FAIL with `ImportError: cannot import name 'layout'`.

- [ ] **Step 3: Implement `scrapers/unit_ledger/layout.py`**

```python
"""Physical-unit layout for the unit ledger: from a unit chart, or derived from matched sales."""

from __future__ import annotations

import pandas as pd

from scrapers.unit_ledger.sources import CHART_COLUMNS

LAYOUT_COLUMNS = CHART_COLUMNS
UNIT_COLUMNS = ["block", "unit", "floor", "stack", "area_sqft", "bedrooms", "unit_type", "layout_source",
                "status", "sale_count", "first_txn_id", "latest_txn_id", "note"]


def stack_blocks(units: pd.DataFrame) -> dict[str, set[str]]:
    """Which blocks each stack number exists in."""
    mapping: dict[str, set[str]] = {}
    for block, stack in zip(units.block, units.stack):
        mapping.setdefault(stack, set()).add(block)
    return mapping


def derived_units(ledger: pd.DataFrame) -> pd.DataFrame:
    """Every unit identified in any matched sale; sizes and bedrooms are the most common observed."""
    rows = []
    known = ledger[(ledger.block != "") & (ledger.unit != "")]
    for (block, unit), group in known.groupby(["block", "unit"]):
        sizes = pd.to_numeric(group.area_sqft, errors="coerce").dropna()
        beds = pd.to_numeric(group.bedrooms, errors="coerce").dropna()
        rows.append({
            "block": block, "unit": unit, "floor": int(unit[1:unit.index("-")]), "stack": unit.split("-", 1)[1],
            "area_sqft": int(sizes.mode().iat[0]) if len(sizes) else pd.NA,
            "bedrooms": int(beds.mode().iat[0]) if len(beds) else pd.NA,
            "unit_type": "", "chart_status": "", "chart_sold_date": "",
        })
    return pd.DataFrame(rows, columns=LAYOUT_COLUMNS).astype({"floor": "Int64", "area_sqft": "Int64", "bedrooms": "Int64"})


def summarise_units(units: pd.DataFrame, ledger: pd.DataFrame, recent: pd.DataFrame, has_chart: bool) -> pd.DataFrame:
    """One row per physical unit with its status, sale count and first/latest transaction."""
    token_blocks = units.groupby("unit").block.nunique()
    recent_dates = {u: d for u, d in zip(recent.unit, recent.date) if token_blocks.get(u, 0) == 1}
    sales = ledger[ledger.unit != ""].copy()
    sales["order"] = sales.sale_month.astype(str) + sales.sale_date.astype(str)
    sales = sales.sort_values(["order", "txn_id"], kind="stable")
    grouped = {key: group for key, group in sales.groupby(["block", "unit"], sort=False)}
    rows = []
    for u in units.itertuples():
        g = grouped.get((u.block, u.unit))
        notes = []
        if g is not None and (g.origin == "URA").any():
            status = "sold"
        elif g is not None:
            status = "sold_pre_window_only"
        elif u.unit in recent_dates or u.chart_status == "sold":
            status = "sold_pending_ura"
            evidence = []
            if u.unit in recent_dates:
                evidence.append(f"developer site sold {recent_dates[u.unit]}")
            evidence.append(f"unit chart sold {u.chart_sold_date}" if u.chart_status == "sold"
                            else "unit chart still shows it available")
            notes.append("Sold, not yet in URA: " + "; ".join(evidence))
        elif has_chart:
            status = "available"
        else:
            status = "unknown"
        if g is not None and u.chart_status == "available":
            notes.append("Unit chart still shows it available")
        rows.append({
            "block": u.block, "unit": u.unit, "floor": u.floor, "stack": u.stack, "area_sqft": u.area_sqft,
            "bedrooms": u.bedrooms, "unit_type": u.unit_type, "layout_source": "chart" if has_chart else "derived",
            "status": status, "sale_count": 0 if g is None else len(g),
            "first_txn_id": "" if g is None else g.txn_id.iat[0],
            "latest_txn_id": "" if g is None else g.txn_id.iat[-1],
            "note": "; ".join(notes),
        })
    return pd.DataFrame(rows, columns=UNIT_COLUMNS)
```

- [ ] **Step 4: Implement `scrapers/unit_ledger/match.py`**

```python
"""Pure transaction-to-unit matching for the unit ledger. No I/O, no network.

Rules run per transaction, so a unit may have any number of sales. See
docs/superpowers/specs/2026-09-26-unit-ledger-design.md, "Matching rules".
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import NamedTuple

import pandas as pd

from scrapers.unit_ledger import layout
from scrapers.unit_ledger.sources import SQFT_PER_SQM, floor_band

LEDGER_COLUMNS = [
    "txn_id", "origin", "sale_date", "sale_month", "block", "unit", "floor", "floor_level",
    "area_sqm", "area_sqft", "bedrooms", "unit_type", "price", "psf", "type_of_sale", "tenure",
    "unit_source", "date_source", "conflict",
]
EDGEPROP_DATE = "EdgeProp (URA record)"
PN_KEY = ["sale_date", "price", "area_sqft", "floor"]
TOLERANCE_DAYS = 3
CHART_DATE_DAYS = 7
ELIMINATION = "By elimination (last chart-sold unit of this size and floor without a New Sale)"


class MatchResult(NamedTuple):
    ledger: pd.DataFrame
    units: pd.DataFrame
    unmatched_edgeprop: int
    unmatched_propertynoob: int


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _note(existing: str, note: str) -> str:
    return f"{existing}; {note}" if existing else note


def _set_unit(ledger, i, block, unit, label):
    ledger.at[i, "block"] = block
    ledger.at[i, "unit"] = unit
    ledger.at[i, "unit_source"] = label


def _na(n):
    return pd.array([pd.NA] * n, dtype="Int64")


# --- Step 1: URA -> EdgeProp ------------------------------------------------------

def link_ura_edgeprop(ura: pd.DataFrame, ep: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Give each URA row EdgeProp's exact date, block and floor. Returns (ledger, unused EdgeProp rows)."""
    n = len(ura)
    ledger = pd.DataFrame({
        "txn_id": ura.txn_id, "origin": "URA", "sale_date": "", "sale_month": ura.sale_month,
        "block": "", "unit": "", "floor": _na(n), "floor_level": ura.floor_level, "area_sqm": ura.area_sqm,
        "area_sqft": _na(n), "bedrooms": _na(n), "unit_type": "", "price": ura.price, "psf": _na(n),
        "type_of_sale": ura.type_of_sale, "tenure": ura.tenure, "unit_source": "",
        "date_source": "No EdgeProp record", "conflict": "",
    })
    decimals = int(ura.area_decimals.max())
    keys = ["sale_month", "price", "area_key", "floor_level", "type_of_sale"]
    ep_groups = {key: group for key, group in ep.assign(area_key=ep.area_sqm.round(decimals)).groupby(keys, sort=False)}
    used = set()
    for key, group in ledger.assign(area_key=ledger.area_sqm.round(decimals)).groupby(keys, sort=False):
        candidates = ep_groups.get(key)
        if candidates is None:
            continue
        rows = list(group.index)
        if len(candidates) > len(rows):
            spots = candidates[["sale_date", "block", "floor"]].drop_duplicates()
            if len(spots) > 1:
                listed = "; ".join(f"{s.sale_date} blk {s.block} floor {s.floor}" for s in spots.itertuples())
                for i in rows:
                    ledger.at[i, "conflict"] = (
                        f"EdgeProp has {len(candidates)} candidates for {len(rows)} identical URA rows: {listed}")
                continue
        for i, e in zip(rows, candidates.itertuples()):
            ledger.at[i, "sale_date"] = e.sale_date
            ledger.at[i, "block"] = e.block
            ledger.at[i, "floor"] = e.floor
            ledger.at[i, "area_sqft"] = e.area_sqft
            ledger.at[i, "bedrooms"] = e.bedrooms
            ledger.at[i, "date_source"] = EDGEPROP_DATE
            used.add(e.ep_id)
    return ledger, ep[~ep.ep_id.isin(used)].reset_index(drop=True)


def pre_window_rows(unused_ep: pd.DataFrame, earliest_month: str) -> tuple[pd.DataFrame, int]:
    """EdgeProp rows older than the URA pull become flagged rows; in-window leftovers are only counted."""
    old = unused_ep[unused_ep.sale_month < earliest_month]
    rows = pd.DataFrame({
        "txn_id": old.ep_id, "origin": "Pre-window", "sale_date": old.sale_date, "sale_month": old.sale_month,
        "block": old.block, "unit": "", "floor": old.floor, "floor_level": old.floor_level,
        "area_sqm": old.area_sqm, "area_sqft": old.area_sqft, "bedrooms": old.bedrooms, "unit_type": "",
        "price": old.price, "psf": _na(len(old)), "type_of_sale": old.type_of_sale, "tenure": "",
        "unit_source": "", "date_source": "EdgeProp (not verified against URA API)", "conflict": "",
    }, columns=LEDGER_COLUMNS)
    return rows.reset_index(drop=True), int((unused_ep.sale_month >= earliest_month).sum())


def fill_sizes(ledger: pd.DataFrame, chart: pd.DataFrame | None) -> pd.DataFrame:
    """Give rows without an EdgeProp size a sqft: the chart size for URA's sqm, else sqm x 10.7639."""
    ledger = ledger.copy()
    options: dict[int, set[int]] = {}
    if chart is not None:
        for sqft in chart.area_sqft.unique():
            options.setdefault(round(sqft / SQFT_PER_SQM), set()).add(int(sqft))
    for i in ledger.index[ledger.area_sqft.isna()]:
        sqm = float(ledger.at[i, "area_sqm"])
        fits = options.get(round(sqm))
        if fits is None:
            ledger.at[i, "area_sqft"] = round(sqm * SQFT_PER_SQM)
            if chart is not None:
                ledger.at[i, "conflict"] = _note(ledger.at[i, "conflict"], f"{sqm} sqm is not a size on the unit chart")
        elif len(fits) > 1:
            raise ValueError(f"{ledger.at[i, 'txn_id']}: URA area {sqm} sqm maps to several chart sizes "
                             f"{sorted(fits)} sqft; cannot size this row")
        else:
            ledger.at[i, "area_sqft"] = next(iter(fits))
    return ledger


# --- Step 2: -> PropertyNoob ------------------------------------------------------

def _located(ledger: pd.DataFrame) -> pd.Series:
    return (ledger.unit == "") & (ledger.sale_date != "") & ledger.floor.notna() & (ledger.block != "")


def learn_stack_blocks(ledger: pd.DataFrame, pn: pd.DataFrame) -> dict[str, set[str]]:
    """Stack -> blocks, learned from sales with exactly one located row and one PropertyNoob row."""
    pn_groups = {key: group for key, group in pn.groupby(PN_KEY)}
    learned: dict[str, set[str]] = {}
    located = ledger[(ledger.sale_date != "") & ledger.floor.notna() & (ledger.block != "")]
    for key, group in located.groupby(PN_KEY):
        candidates = pn_groups.get(key)
        if len(group) == 1 and candidates is not None and len(candidates) == 1:
            learned.setdefault(candidates.stack.iat[0], set()).add(group.block.iat[0])
    return learned


def attach_propertynoob(ledger, pn, stack_blocks):
    """Take the stack from PropertyNoob. Returns (ledger, unused PropertyNoob rows, stack map used)."""
    ledger = ledger.copy()
    if stack_blocks is None:
        stack_blocks = learn_stack_blocks(ledger, pn)
    by_id = pn.set_index("pn_id")
    free = set(pn.pn_id)

    def fits(block, candidates):
        return [p for p in candidates if p in free and block in stack_blocks.get(by_id.at[p, "stack"], ())]

    pn_groups = {key: list(group.pn_id) for key, group in pn.groupby(PN_KEY)}
    for key, group in ledger[_located(ledger)].groupby(PN_KEY):
        candidates = pn_groups.get(key, [])
        rows = list(group.index)
        progress = True
        while progress and rows:
            progress = False
            for i in list(rows):
                options = fits(ledger.at[i, "block"], candidates)
                if len(options) == 1:
                    _set_unit(ledger, i, ledger.at[i, "block"], by_id.at[options[0], "unit"], "Published")
                    free.discard(options[0])
                    rows.remove(i)
                    progress = True
            for block in sorted({ledger.at[i, "block"] for i in rows}):
                same = [i for i in rows if ledger.at[i, "block"] == block]
                options = sorted(fits(block, candidates), key=lambda p: by_id.at[p, "unit"])
                if len(same) > 1 and len(options) == len(same):
                    for i, p in zip(same, options):
                        _set_unit(ledger, i, block, by_id.at[p, "unit"], "Published (identical sales, matched as a set)")
                        free.discard(p)
                        rows.remove(i)
                    progress = True

    # ±N-day tolerance, accepted only when the pairing is unique in both directions.
    remaining = pn[pn.pn_id.isin(free)]
    proposals = []
    for i, r in ledger[_located(ledger)].iterrows():
        options = [
            p.pn_id for p in remaining.itertuples()
            if p.price == r.price and p.area_sqft == r.area_sqft and p.floor == r.floor
            and 0 < _days(p.sale_date, r.sale_date) <= TOLERANCE_DAYS
            and r.block in stack_blocks.get(p.stack, ())
        ]
        proposals.append((i, options))
    claimed = Counter(p for _, options in proposals for p in options)
    for i, options in proposals:
        if len(options) == 1 and claimed[options[0]] == 1:
            p = options[0]
            days = _days(by_id.at[p, "sale_date"], ledger.at[i, "sale_date"])
            _set_unit(ledger, i, ledger.at[i, "block"], by_id.at[p, "unit"], f"Published (date ±{days} days)")
            ledger.at[i, "conflict"] = _note(ledger.at[i, "conflict"],
                                             f"PropertyNoob dates this sale {by_id.at[p, 'sale_date']}")
            free.discard(p)
    return ledger, pn[pn.pn_id.isin(free)].reset_index(drop=True), stack_blocks


def propertynoob_pre_window_rows(unused_pn, earliest_month, stack_blocks) -> pd.DataFrame:
    """PropertyNoob-only sales older than the URA pull, flagged as not verified."""
    rows = []
    for p in unused_pn[unused_pn.sale_date.str[:7] < earliest_month].itertuples():
        blocks = stack_blocks.get(p.stack, set())
        block = next(iter(blocks)) if len(blocks) == 1 else ""
        rows.append({
            "txn_id": p.pn_id, "origin": "Pre-window", "sale_date": p.sale_date, "sale_month": p.sale_date[:7],
            "block": block, "unit": p.unit if block else "", "floor": p.floor, "floor_level": floor_band(p.floor),
            "area_sqm": round(p.area_sqft / SQFT_PER_SQM, 2), "area_sqft": p.area_sqft, "bedrooms": pd.NA,
            "unit_type": "", "price": p.price, "psf": pd.NA, "type_of_sale": p.type_of_sale, "tenure": "",
            "unit_source": "Published (PropertyNoob only)" if block else "",
            "date_source": "PropertyNoob (not verified against URA API)",
            "conflict": "" if block else f"PropertyNoob unit {p.unit}; its stack is not tied to one block",
        })
    frame = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    return frame.astype({"floor": "Int64", "area_sqft": "Int64", "bedrooms": "Int64", "psf": "Int64"})


# --- Step 3: leftovers ---------------------------------------------------------------

def _recent_with_blocks(recent, units):
    """Recent-sales entries with block, floor and size from the layout; tokens in several blocks are dropped."""
    if recent.empty or units.empty:
        return pd.DataFrame(columns=["date", "unit", "block", "floor", "area_sqft"])
    per_token = units.groupby("unit").block.nunique()
    unique = set(per_token[per_token == 1].index)
    return recent[recent.unit.isin(unique)].merge(units[["block", "unit", "floor", "area_sqft"]], on="unit")


def _strong_rule(r, units, recent, taken, has_chart):
    located = r.block != "" and pd.notna(r.floor)
    is_new = r.type_of_sale == "New Sale"
    if has_chart and located:
        spot = units[(units.block == r.block) & (units.floor == r.floor) & (units.area_sqft == r.area_sqft)]
        if len(spot) == 1:
            return spot.unit.iat[0], "Determined by block, floor and size"
        if is_new and r.sale_date:
            near = [u.unit for u in spot.itertuples()
                    if u.chart_status == "sold" and u.chart_sold_date
                    and _days(u.chart_sold_date, r.sale_date) <= CHART_DATE_DAYS
                    and (u.block, u.unit) not in taken]
            if len(near) == 1:
                return near[0], "Inferred (unit chart sold date + EdgeProp block and floor)"
    if is_new and located and not recent.empty:
        near = [f.unit for f in recent.itertuples()
                if f.date[:7] == r.sale_month and f.block == r.block and f.floor == r.floor
                and f.area_sqft == r.area_sqft and (f.block, f.unit) not in taken]
        if len(near) == 1:
            return near[0], "Inferred (recent-sales list + EdgeProp block and floor)"
    return None, ""


def _elimination(r, units, taken):
    pool = units[(units.chart_status == "sold") & (units.area_sqft == r.area_sqft)]
    if r.block != "" and pd.notna(r.floor):
        pool = pool[(pool.block == r.block) & (pool.floor == r.floor)]
    else:
        pool = pool[pool.floor.map(floor_band) == r.floor_level]
    free = [(u.block, u.unit) for u in pool.itertuples() if (u.block, u.unit) not in taken]
    return free[0] if len(free) == 1 else None


def _unresolved_label(r, units):
    if r.block != "" and pd.notna(r.floor):
        c = units[(units.block == r.block) & (units.floor == r.floor) & (units.area_sqft == r.area_sqft)]
    else:
        c = units[(units.floor.map(floor_band) == r.floor_level) & (units.area_sqft == r.area_sqft)]
    names = sorted(f"{b} {u}" for b, u in zip(c.block, c.unit))
    return f"Ambiguous: {' / '.join(names)}" if names else "Not found"


def resolve_leftovers(ledger, units, recent, has_chart):
    ledger = ledger.copy()
    recent = _recent_with_blocks(recent, units)

    def new_sale_units():
        done = ledger[(ledger.type_of_sale == "New Sale") & (ledger.unit != "")]
        return set(zip(done.block, done.unit))

    while True:
        progress = False
        taken = new_sale_units()
        for i in ledger.index[ledger.unit == ""]:
            unit, label = _strong_rule(ledger.loc[i], units, recent, taken, has_chart)
            if unit is None:
                continue
            spot = (ledger.at[i, "block"], unit)
            if ledger.at[i, "type_of_sale"] == "New Sale":
                if spot in taken:
                    ledger.at[i, "conflict"] = _note(ledger.at[i, "conflict"], "unit already has another New Sale matched")
                taken.add(spot)
            _set_unit(ledger, i, spot[0], unit, label)
            progress = True
        if progress:
            continue
        if has_chart:
            for i in ledger.index[(ledger.unit == "") & (ledger.type_of_sale == "New Sale")]:
                spot = _elimination(ledger.loc[i], units, taken)
                if spot:
                    _set_unit(ledger, i, spot[0], spot[1], ELIMINATION)
                    progress = True
                    break  # re-run the stronger rules before eliminating again
        if not progress:
            break
    for i in ledger.index[ledger.unit == ""]:
        ledger.at[i, "unit_source"] = _unresolved_label(ledger.loc[i], units)
    return ledger


# --- Finalise and orchestrate ------------------------------------------------------------

def finalise(ledger, units, has_chart) -> pd.DataFrame:
    """Chart size, bedrooms and plan type for matched units; bedrooms by size otherwise; $psf."""
    ledger = ledger.copy()
    if has_chart:
        info = units.set_index(["block", "unit"])
        by_size = units.groupby("area_sqft").bedrooms.unique()
        for i in ledger.index:
            key = (ledger.at[i, "block"], ledger.at[i, "unit"])
            if key in info.index:
                ledger.at[i, "area_sqft"] = info.at[key, "area_sqft"]
                ledger.at[i, "bedrooms"] = info.at[key, "bedrooms"]
                ledger.at[i, "unit_type"] = info.at[key, "unit_type"]
            elif pd.isna(ledger.at[i, "bedrooms"]):
                beds = by_size.get(ledger.at[i, "area_sqft"])
                if beds is not None and len(beds) == 1:
                    ledger.at[i, "bedrooms"] = beds[0]
    ledger = ledger.astype({"floor": "Int64", "area_sqft": "Int64", "bedrooms": "Int64"})
    ledger["psf"] = (ledger.price / ledger.area_sqft.astype("Float64")).round().astype("Int64")
    return ledger[LEDGER_COLUMNS].reset_index(drop=True)


def match_all(ura, ep, pn, chart, recent) -> MatchResult:
    has_chart = chart is not None
    earliest = ura.sale_month.min()
    ledger, unused_ep = link_ura_edgeprop(ura, ep)
    pre, unmatched_ep = pre_window_rows(unused_ep, earliest)
    if not pre.empty:
        ledger = pd.concat([ledger, pre], ignore_index=True)
    ledger = fill_sizes(ledger, chart)
    ledger, unused_pn, stack_map = attach_propertynoob(ledger, pn, layout.stack_blocks(chart) if has_chart else None)
    pn_pre = propertynoob_pre_window_rows(unused_pn, earliest, stack_map)
    if not pn_pre.empty:
        ledger = pd.concat([ledger, pn_pre], ignore_index=True)
    units = chart if has_chart else layout.derived_units(ledger)
    ledger = resolve_leftovers(ledger, units, recent, has_chart)
    ledger = finalise(ledger, units, has_chart)
    if not has_chart:
        units = layout.derived_units(ledger)
    unmatched_pn = int((unused_pn.sale_date.str[:7] >= earliest).sum())
    return MatchResult(ledger, units, unmatched_ep, unmatched_pn)


def uniquely_located_count(ledger, units) -> int:
    """URA rows whose EdgeProp block and floor plus size leave exactly one unit in the layout."""
    ura = ledger[(ledger.origin == "URA") & (ledger.block != "") & ledger.floor.notna()]
    sizes = units.groupby(["block", "floor", "area_sqft"]).size()
    return int(sum(sizes.get((r.block, r.floor, r.area_sqft), 0) == 1 for r in ura.itertuples()))
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_unit_ledger_match.py -q`
Expected: 13 passed. If a pandas dtype error appears (for example an `Int64` column receiving a
string), fix the cast in the function that assigns it. Do not loosen the test.

- [ ] **Step 6: Run the whole default gate**

Run: `make smoke`
Expected: PASS with no new failures.

- [ ] **Step 7: Commit**

```bash
git add scrapers/unit_ledger/layout.py scrapers/unit_ledger/match.py tests/test_unit_ledger_match.py
git commit -m "feat(unit-ledger): match transactions to exact dates and units

Per-transaction rules: URA to EdgeProp for date, block and floor;
PropertyNoob for the stack (identical sets, ±3-day unique tolerance);
then block/floor/size, chart sold date, recent-sales list and
New-Sale-only elimination. Unresolved rows list their candidates.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The HTML page (`render.py`, `template.html`)

**Files:**
- Create: `scrapers/unit_ledger/render.py`
- Create: `scrapers/unit_ledger/template.html`
- Test: `tests/test_unit_ledger_render.py`

**Interfaces:**
- Consumes: `match.LEDGER_COLUMNS`, `layout.UNIT_COLUMNS`.
- Produces: `render.render(ledger, units, meta: dict) -> str`. `meta` has the keys `project`,
  `fetched_at_utc`, `chart_as_of`, `has_chart` and `warnings` (a list of str). It also has `counts`, a
  dict with `transactions`, `ura`, `pre_window`, `dated`, `with_unit`, `ambiguous`, `not_found`,
  `uniquely_located` (int or None) and `unit_source` (a dict).

- [ ] **Step 1: Write the failing test**

`tests/test_unit_ledger_render.py`:

```python
"""Offline tests for the unit-ledger page renderer."""

import json
import re

import pandas as pd

from scrapers.unit_ledger import layout, match
from scrapers.unit_ledger.render import render

META = {
    "project": "DEMO </script><b>",
    "fetched_at_utc": "2026-09-26T05:00:00Z",
    "chart_as_of": "2026-09-26",
    "has_chart": True,
    "warnings": ["EdgeProp scrape did not complete"],
    "counts": {"transactions": 2, "ura": 1, "pre_window": 1, "dated": 2, "with_unit": 2, "ambiguous": 0,
               "not_found": 0, "uniquely_located": 1, "unit_source": {"Published": 2}},
}


def _ledger():
    rows = [
        {"txn_id": "ura-1", "origin": "URA", "sale_date": "2026-09-07", "sale_month": "2026-09", "block": "57",
         "unit": "#05-30", "floor": 5, "floor_level": "01-05", "area_sqm": 113.0, "area_sqft": 1216, "bedrooms": 4,
         "unit_type": "4BR-Sa", "price": 2463693, "psf": 2026, "type_of_sale": "Resale", "tenure": "99 yrs",
         "unit_source": "Published", "date_source": "EdgeProp (URA record)", "conflict": ""},
        {"txn_id": "ep-1", "origin": "Pre-window", "sale_date": "2016-08-02", "sale_month": "2016-08", "block": "57",
         "unit": "#05-30", "floor": 5, "floor_level": "01-05", "area_sqm": 112.97, "area_sqft": 1216, "bedrooms": 4,
         "unit_type": "4BR-Sa", "price": 1500000, "psf": 1234, "type_of_sale": "New Sale", "tenure": "",
         "unit_source": "Published", "date_source": "EdgeProp (not verified against URA API)", "conflict": ""},
    ]
    return pd.DataFrame(rows, columns=match.LEDGER_COLUMNS)


def _units():
    return pd.DataFrame([{
        "block": "57", "unit": "#05-30", "floor": 5, "stack": "30", "area_sqft": 1216, "bedrooms": 4,
        "unit_type": "4BR-Sa", "layout_source": "chart", "status": "sold", "sale_count": 2,
        "first_txn_id": "ep-1", "latest_txn_id": "ura-1", "note": ""}], columns=layout.UNIT_COLUMNS)


def test_render_embeds_data_and_leaves_no_placeholders():
    html = render(_ledger(), _units(), META)
    assert re.search(r"__[A-Z]+__", html) is None
    script = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert "</script>" not in script
    txns = json.loads(re.search(r"const TXNS = (.*);\n", html).group(1))
    assert [t["txn_id"] for t in txns] == ["ura-1", "ep-1"]
    units = json.loads(re.search(r"const UNITS = (.*);\n", html).group(1))
    assert units[0]["sale_count"] == 2 and units[0]["first_txn_id"] == "ep-1"
    assert "EdgeProp scrape did not complete" in html
    assert 'value="first"' in html and 'value="latest"' in html


def test_render_writes_nulls_for_missing_numbers():
    ledger = _ledger()
    ledger.loc[0, "psf"] = pd.NA
    ledger = ledger.astype({"psf": "Int64"})
    txns = json.loads(re.search(r"const TXNS = (.*);\n", render(ledger, _units(), META)).group(1))
    assert txns[0]["psf"] is None
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m pytest tests/test_unit_ledger_render.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.unit_ledger.render'`.

- [ ] **Step 3: Implement `scrapers/unit_ledger/render.py`**

```python
"""Render the unit ledger's self-contained HTML page."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

TEMPLATE = Path(__file__).with_name("template.html")


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records"))


def _embed(value) -> str:
    # "</" inside a <script> block would end it early; JSON allows the escaped form.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render(ledger: pd.DataFrame, units: pd.DataFrame, meta: dict) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("__META__", meta), ("__TRANSACTIONS__", _records(ledger)), ("__UNITS__", _records(units))):
        if html.count(token) != 1:
            raise ValueError(f"template must contain {token} exactly once")
        html = html.replace(token, _embed(value))
    return html
```

- [ ] **Step 4: Create `scrapers/unit_ledger/template.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unit Ledger</title>
<style>
:root {
  --bg: #ffffff; --fg: #1b1f24; --muted: #5b6470; --line: #d9dee4;
  --head: #f3f5f7; --hover: #eef3fb; --accent: #1f5fbf; --chip: #eef1f4;
  --pre: #eceffa; --pending: #fdf1d6; --pending-fg: #8a5a00; --avail: #e3f4e8; --avail-fg: #1d6b35;
  --empty: #f7f8f9; --warn: #fff4e5; --warn-line: #e8b765;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15181c; --fg: #e6e9ed; --muted: #9aa4b0; --line: #2c3239;
    --head: #1d2126; --hover: #1f2a38; --accent: #7fb0ff; --chip: #232830;
    --pre: #22263a; --pending: #3a2f16; --pending-fg: #f0c46a; --avail: #173222; --avail-fg: #7fd69a;
    --empty: #1a1d21; --warn: #33291a; --warn-line: #8a6a2e;
  }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 20px 16px 40px; background: var(--bg); color: var(--fg);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1300px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 36px 0 4px; }
.sub { color: var(--muted); margin: 0 0 16px; }
.jump { margin: -8px 0 16px; font-size: 13px; }
.jump a { color: var(--accent); }
.banner { background: var(--warn); border: 1px solid var(--warn-line); border-radius: 8px; padding: 10px 14px; margin: 0 0 16px; }
.banner ul { margin: 4px 0 0; padding-left: 18px; }
fieldset { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; margin: 0 0 12px; }
legend { color: var(--muted); padding: 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.opts { display: flex; flex-wrap: wrap; gap: 6px 14px; }
.opts label { white-space: nowrap; cursor: pointer; }
.n { color: var(--muted); font-size: 12px; }
.actions { display: flex; gap: 8px; margin-top: 8px; }
button { font: inherit; font-size: 12px; background: var(--chip); color: var(--fg);
  border: 1px solid var(--line); border-radius: 6px; padding: 3px 10px; cursor: pointer; }
.stats { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 4px 0 12px; color: var(--muted); }
.stats b { color: var(--fg); font-variant-numeric: tabular-nums; }
.wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
#ledger th, #ledger td { padding: 6px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
#ledger th { background: var(--head); position: sticky; top: 0; cursor: pointer; user-select: none; font-weight: 600; }
#ledger .num { text-align: right; }
#ledger th[aria-sort="ascending"]::after { content: " ▲"; color: var(--accent); }
#ledger th[aria-sort="descending"]::after { content: " ▼"; color: var(--accent); }
#ledger td.wrap-cell { white-space: normal; min-width: 200px; color: var(--muted); font-size: 12px; }
#ledger tbody tr:hover { background: var(--hover); }
#ledger tr.pre td { background: var(--pre); }
.notes { color: var(--muted); font-size: 12px; margin-top: 16px; }
.notes li { margin-bottom: 4px; }
.site-controls { display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0; font-size: 13px; }
.site-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 8px 0 14px; font-size: 12px; color: var(--muted); }
.site-legend span::before { content: ""; display: inline-block; width: 12px; height: 12px; border-radius: 3px;
  margin-right: 6px; vertical-align: -2px; border: 1px solid var(--line); background: var(--sw); }
.blocks { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(560px, 100%), 1fr)); gap: 20px; }
.block h3 { font-size: 15px; margin: 0 0 6px; }
table.site { min-width: 560px; table-layout: fixed; font-size: 11px; line-height: 1.3; }
table.site th, table.site td { border: 1px solid var(--line); padding: 4px 3px; text-align: center; }
table.site th { background: var(--head); font-weight: 600; }
table.site th.floor { width: 30px; }
table.site .t { font-weight: 600; }
table.site .a, table.site .s { color: var(--muted); }
table.site .p { font-weight: 600; margin-top: 2px; }
table.site .x { font-weight: 400; color: var(--muted); font-size: 10px; }
table.site td.pre { background: var(--pre); }
table.site td.pending { background: var(--pending); color: var(--pending-fg); }
table.site td.available { background: var(--avail); color: var(--avail-fg); }
table.site td.none { background: var(--empty); color: var(--muted); }
table.site td.unknown { color: var(--muted);
  background: repeating-linear-gradient(45deg, var(--empty), var(--empty) 4px, var(--bg) 4px, var(--bg) 8px); }
</style>
</head>
<body>
<main>
<h1 id="title"></h1>
<p class="sub" id="subtitle"></p>
<div class="banner" id="banner" hidden></div>
<p class="jump"><a href="#site">Jump to the site sales view</a></p>

<fieldset><legend>Sale type</legend><div class="opts" id="f-sale"></div></fieldset>
<fieldset><legend>Bedrooms</legend><div class="opts" id="f-beds"></div></fieldset>
<fieldset>
  <legend>Unit size (sqft)</legend>
  <div class="opts" id="f-size"></div>
  <div class="actions"><button type="button" data-all="f-size">Select all</button><button type="button" data-none="f-size">Clear all</button></div>
</fieldset>

<div class="stats" id="stats"></div>
<div class="wrap"><table id="ledger"><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table></div>

<ul class="notes">
  <li>Prices, months, floor bands and sqm come from URA's transaction API, which covers the last five years. Shaded rows are older sales from EdgeProp or PropertyNoob and are not verified against that API.</li>
  <li>URA's API gives only the month. Exact dates, blocks and floors come from EdgeProp, which republishes URA's dated record with the stack number hidden.</li>
  <li>Unit numbers are not official. <b>Published</b>: PropertyNoob printed the unit with this price, size, floor and date. <b>Determined by block, floor and size</b>: only one unit on that block and floor has this size. <b>Inferred</b>: the unit chart's sold date, or the developer's recent-sales list, picks one unit on that block and floor. <b>By elimination</b>: New Sales only; the last sold unit of that size and floor without a New Sale. <b>Ambiguous</b>: more than one unit fits, and the candidates are listed.</li>
  <li>$psf = price ÷ sqft. Prices are gross; URA publishes no nett price. Recent months may be incomplete because URA registers transactions with a lag.</li>
</ul>

<h2 id="site">Site sales view</h2>
<p class="sub">Each unit's achieved price, by block, floor and stack. Hover over a unit to see every sale.</p>
<div class="site-controls">
  <span>Show:</span>
  <label><input type="radio" name="mode" value="latest" checked> Latest sale</label>
  <label><input type="radio" name="mode" value="first"> First sale</label>
</div>
<div class="site-legend" id="legend"></div>
<div class="blocks" id="blocks"></div>
</main>

<script>
const META = __META__;
const TXNS = __TRANSACTIONS__;
const UNITS = __UNITS__;

const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
const num = v => v == null ? "—" : Number(v).toLocaleString();
const when = t => t.sale_date || t.sale_month;
const SHORT = {"New Sale": "New", "Sub Sale": "Sub", "Resale": "Resale"};
const c = META.counts;

document.title = `${META.project} unit ledger`;
document.getElementById("title").textContent = `${META.project}: transactions`;
document.getElementById("subtitle").textContent =
  `Fetched ${META.fetched_at_utc}. ${c.transactions} transactions: ${c.ura} from the URA API (last five years) and ` +
  `${c.pre_window} older ones not verified against it. ${c.dated} have an exact date and ${c.with_unit} a unit number` +
  (c.uniquely_located == null ? "" : `; for ${c.uniquely_located} URA rows, block, floor and size alone fix the unit`) +
  `. Click a column header to sort.`;
if (META.warnings.length) {
  const banner = document.getElementById("banner");
  banner.hidden = false;
  banner.innerHTML = "<b>Some sources were incomplete</b><ul>" + META.warnings.map(w => `<li>${esc(w)}</li>`).join("") + "</ul>";
}

const COLS = [
  { key: "sale_date", label: "Sale date", sort: when, fmt: (v, r) => esc(v || `${r.sale_month} (month only)`) },
  { key: "unit", label: "Unit", sort: r => r.unit ? `${r.block} ${r.unit}` : "", fmt: (v, r) => v ? `${esc(r.block)} ${esc(v)}` : "—" },
  { key: "origin", label: "Origin" },
  { key: "type_of_sale", label: "Sale type" },
  { key: "floor_level", label: "Floor band" },
  { key: "bedrooms", label: "Bedrooms", num: true, fmt: v => esc(v ?? "—") },
  { key: "area_sqft", label: "Size (sqft)", num: true, fmt: num },
  { key: "area_sqm", label: "Size (sqm)", num: true, fmt: v => esc(v ?? "—") },
  { key: "price", label: "Price (S$)", num: true, fmt: num },
  { key: "psf", label: "$psf", num: true, fmt: num },
  { key: "tenure", label: "Tenure" },
  { key: "unit_source", label: "Unit match", wrap: true },
  { key: "date_source", label: "Date source", wrap: true },
  { key: "conflict", label: "Conflicts", wrap: true },
];
let sortKey = "sale_date", sortDir = -1;
const keyOf = (r, k) => String(r[k] ?? "Unknown");

function buildChecks(id, key, labelFn) {
  const counts = new Map();
  TXNS.forEach(r => counts.set(keyOf(r, key), (counts.get(keyOf(r, key)) || 0) + 1));
  const keys = [...counts.keys()].sort((a, b) => (Number(a) - Number(b)) || a.localeCompare(b));
  document.getElementById(id).innerHTML = keys.map(k =>
    `<label><input type="checkbox" data-key="${key}" value="${esc(k)}" checked> ${labelFn(k)} <span class="n">(${counts.get(k)})</span></label>`).join("");
}
buildChecks("f-sale", "type_of_sale", k => esc(k));
buildChecks("f-beds", "bedrooms", k => k === "Unknown" ? "Unknown" : `${esc(k)} BR`);
buildChecks("f-size", "area_sqft", k => k === "Unknown" ? "Unknown" : Number(k).toLocaleString());

const checked = key => new Set([...document.querySelectorAll(`input[data-key="${key}"]:checked`)].map(i => i.value));
function median(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b), mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

const head = document.getElementById("head");
COLS.forEach(col => {
  const th = document.createElement("th");
  th.textContent = col.label;
  th.dataset.key = col.key;
  if (col.num) th.className = "num";
  th.addEventListener("click", () => {
    sortDir = sortKey === col.key ? -sortDir : (col.num ? -1 : 1);
    sortKey = col.key;
    render();
  });
  head.appendChild(th);
});

function render() {
  const sale = checked("type_of_sale"), beds = checked("bedrooms"), size = checked("area_sqft");
  const rows = TXNS.filter(r => sale.has(keyOf(r, "type_of_sale")) && beds.has(keyOf(r, "bedrooms")) && size.has(keyOf(r, "area_sqft")));
  const col = COLS.find(x => x.key === sortKey);
  const val = col.sort || (r => r[col.key]);
  rows.sort((a, b) => {
    const x = val(a), y = val(b);
    if (x == null || y == null) return (x == null) - (y == null);
    const d = typeof x === "number" ? x - y : String(x).localeCompare(String(y));
    return d * sortDir || when(b).localeCompare(when(a));
  });
  head.querySelectorAll("th").forEach(th =>
    th.setAttribute("aria-sort", th.dataset.key === sortKey ? (sortDir > 0 ? "ascending" : "descending") : "none"));
  document.getElementById("body").innerHTML = rows.map(r =>
    `<tr class="${r.origin === "URA" ? "" : "pre"}">` + COLS.map(col =>
      `<td class="${col.num ? "num" : col.wrap ? "wrap-cell" : ""}">${col.fmt ? col.fmt(r[col.key], r) : esc(r[col.key])}</td>`
    ).join("") + "</tr>").join("");
  const mp = median(rows.map(r => r.price)), mpsf = median(rows.map(r => r.psf).filter(v => v != null));
  document.getElementById("stats").innerHTML =
    `<div>Showing <b>${rows.length}</b> of ${TXNS.length}</div>` +
    `<div>Median price <b>${mp == null ? "–" : "S$" + Math.round(mp).toLocaleString()}</b></div>` +
    `<div>Median $psf <b>${mpsf == null ? "–" : Math.round(mpsf).toLocaleString()}</b></div>`;
}

const salesByUnit = new Map();
TXNS.forEach(t => {
  if (!t.unit) return;
  const k = `${t.block}|${t.unit}`;
  if (!salesByUnit.has(k)) salesByUnit.set(k, []);
  salesByUnit.get(k).push(t);
});
salesByUnit.forEach(list => list.sort((a, b) => when(a).localeCompare(when(b))));

const LEGEND = [
  ["var(--bg)", "Sold (URA price)"],
  ["var(--pre)", "Sold, older than the URA window (not verified)"],
  ["var(--pending)", "Sold, not yet in URA (no price)"],
  ...(META.has_chart ? [["var(--avail)", "Available"], ["var(--empty)", "No residential unit"]]
                     : [["var(--empty)", "Never seen in any sale"]]),
];
document.getElementById("legend").innerHTML = LEGEND.map(([sw, label]) => `<span style="--sw: ${sw}">${label}</span>`).join("");

function renderSite(mode) {
  const host = document.getElementById("blocks");
  if (!UNITS.length) {
    host.innerHTML = `<p class="sub">No unit numbers were resolved, so there is no site view.</p>`;
    return;
  }
  const allFloors = UNITS.map(u => u.floor);
  const blocks = [...new Set(UNITS.map(u => u.block))].sort((a, b) => a.localeCompare(b, undefined, {numeric: true}));
  host.innerHTML = blocks.map(b => {
    const units = UNITS.filter(u => u.block === b);
    const stacks = [...new Set(units.map(u => u.stack))].sort((x, y) => x.localeCompare(y, undefined, {numeric: true}));
    const floors = META.has_chart ? allFloors : units.map(u => u.floor);
    const lo = Math.min(...floors), hi = Math.max(...floors);
    const at = new Map(units.map(u => [`${u.floor}|${u.stack}`, u]));
    let body = "";
    for (let f = hi; f >= lo; f--) {
      body += `<tr><th class="floor">${f}</th>` + stacks.map(st => {
        const u = at.get(`${f}|${st}`);
        if (!u) return META.has_chart ? `<td class="none">—</td>` : `<td class="unknown">?</td>`;
        const sales = salesByUnit.get(`${u.block}|${u.unit}`) || [];
        const shown = mode === "first" ? sales[0] : sales[sales.length - 1];
        const tip = [`${u.block} ${u.unit}`, u.unit_type, u.area_sqft ? `${num(u.area_sqft)} sqft` : null,
          ...sales.map(s => `${when(s)} ${s.type_of_sale} S$${num(s.price)}${s.origin === "URA" ? "" : " (not verified against URA)"}`),
          u.note].filter(Boolean).join("\n");
        const top = (u.unit_type ? `<div class="t">${esc(u.unit_type)}</div>` : "") +
          `<div class="a">${u.area_sqft ? num(u.area_sqft) : ""}${u.bedrooms != null ? ` · ${u.bedrooms}BR` : ""}</div>`;
        let cls, value;
        if (shown) {
          cls = shown.origin === "URA" ? "sold" : "pre";
          value = `<div class="p">${num(shown.price)}${sales.length > 1 ? ` <span class="x">x${sales.length}</span>` : ""}</div>` +
            `<div class="s">${shown.psf != null ? `$${num(shown.psf)} psf` : ""}</div>` +
            `<div class="s">${esc(SHORT[shown.type_of_sale] || shown.type_of_sale)} ${esc(when(shown).slice(0, 4))}</div>`;
        } else if (u.status === "sold_pending_ura") {
          cls = "pending"; value = `<div class="p">Sold</div><div class="s">not yet in URA</div>`;
        } else if (u.status === "available") {
          cls = "available"; value = `<div class="p">Available</div>`;
        } else {
          cls = "unknown"; value = `<div class="p">—</div>`;
        }
        return `<td class="${cls}" title="${esc(tip)}">${top}${value}</td>`;
      }).join("") + "</tr>";
    }
    const headRow = `<tr><th class="floor"></th>${stacks.map(st => `<th>${esc(st)}</th>`).join("")}</tr>`;
    return `<div class="block"><h3>Blk ${esc(b)}</h3><div class="wrap"><table class="site"><thead>${headRow}</thead><tbody>${body}</tbody></table></div></div>`;
  }).join("");
}

document.addEventListener("change", e => {
  if (e.target.matches("input[data-key]")) render();
  if (e.target.name === "mode") renderSite(e.target.value);
});
document.querySelectorAll("[data-all], [data-none]").forEach(button => button.addEventListener("click", () => {
  const id = button.dataset.all || button.dataset.none;
  document.querySelectorAll(`#${id} input`).forEach(i => { i.checked = Boolean(button.dataset.all); });
  render();
}));
render();
renderSite("latest");
</script>
</body>
</html>
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_unit_ledger_render.py -q`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add scrapers/unit_ledger/render.py scrapers/unit_ledger/template.html tests/test_unit_ledger_render.py
git commit -m "feat(unit-ledger): render the transaction table and site sales view

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Fetching, run assembly and the command line (`fetch.py`, `build.py`, `__main__.py`)

**Files:**
- Create: `scrapers/unit_ledger/fetch.py`
- Create: `scrapers/unit_ledger/build.py`
- Create: `scrapers/unit_ledger/__main__.py`
- Test: `tests/test_unit_ledger_build.py`

**Interfaces:**
- Consumes: `sources.*`, `match.match_all`, `match.uniquely_located_count`, `layout.summarise_units` and `render.render` (Tasks 2–4).
- Produces:
  - `fetch.ProjectNotFound(ValueError)`
  - `fetch.fetch_ura(project) -> list[dict]`
  - `fetch.find_edgeprop_project(project, projects_csv: Path, logs: Path) -> dict | None`
  - `fetch.fetch_all(project, raw: Path, logs: Path, *, chart_url=None, recent_sales: Path | None = None) -> dict`, which writes `raw/fetch.json`
  - `build.build_run(run_dir: Path) -> dict` (the page's `meta`)
  - `build.run(project, *, chart_url=None, recent_sales=None, runs_root=RUNS_ROOT, today=None) -> Path`
  - `build.RUNS_ROOT = <repo>/data/runs/unit-ledger`
  - `__main__.main(argv=None) -> int`

This spec amendment adds `build.py`: the command-line module stays thin, and tests import
`build_run` without importing `__main__`.

- [ ] **Step 1: Write the failing tests**

`tests/test_unit_ledger_build.py`:

```python
"""Offline tests for unit-ledger run assembly, fetch helpers and failure handling."""

import json

import pandas as pd
import pytest

from scrapers.unit_ledger import build, fetch


def _raw_run(run_dir, with_edgeprop=True):
    raw = run_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "fetch.json").write_text(json.dumps({
        "project": "DEMO", "fetched_at_utc": "2026-09-26T00:00:00Z", "sources": {},
        "warnings": ["PropertyNoob page unavailable (404)"]}))
    (raw / "ura.json").write_text(json.dumps([{"project": "DEMO", "transaction": [
        {"contractDate": "0826", "price": "2469854", "area": "113", "floorRange": "06-10",
         "typeOfSale": "1", "noOfUnits": "1", "tenure": "99 yrs"}]}]))
    if with_edgeprop:
        pd.DataFrame([{"Date of Sale": "26 Aug 2026", "Street": "57 DEMO ROAD", "Address": "57 DEMO ROAD #06-XX",
                       "Price ($)": "2469854", "Area (sqm)": "112.97", "Area (sqft)": "1216", "Bedrooms": "4",
                       "Sale Type": "New Sale"}]).to_csv(raw / "edgeprop.csv", index=False)
    return run_dir


def test_build_run_writes_every_output(tmp_path):
    meta = build.build_run(_raw_run(tmp_path))
    for name in ("transactions.csv", "units.csv", "provenance.json", "README.md", "index.html"):
        assert (tmp_path / name).exists(), name
    assert meta["counts"]["dated"] == 1 and meta["counts"]["with_unit"] == 0
    assert "PropertyNoob page unavailable (404)" in (tmp_path / "README.md").read_text()
    assert "ura.json" in json.loads((tmp_path / "provenance.json").read_text())["raw_sha256"]


def test_build_run_warns_when_edgeprop_is_missing(tmp_path):
    meta = build.build_run(_raw_run(tmp_path, with_edgeprop=False))
    assert any("no matching EdgeProp record" in w for w in meta["warnings"])


def test_run_discards_partial_output_when_a_fetch_fails(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("URA batch 2 returned Status='Error'")
    monkeypatch.setattr(fetch, "fetch_all", boom)
    with pytest.raises(RuntimeError):
        build.run("DEMO", runs_root=tmp_path, today="2026-09-26")
    assert not any("2026-09-26" in p.name for p in tmp_path.rglob("*"))


def test_run_replaces_the_same_day_directory_only_after_success(tmp_path, monkeypatch):
    final = tmp_path / "demo" / "2026-09-26"
    final.mkdir(parents=True)
    (final / "old.txt").write_text("old")
    monkeypatch.setattr(fetch, "fetch_all", lambda project, raw, logs, **kwargs: _raw_run(raw.parent))
    out = build.run("DEMO", runs_root=tmp_path, today="2026-09-26")
    assert out == final and (final / "index.html").exists() and not (final / "old.txt").exists()


def test_fetch_ura_names_the_closest_projects(monkeypatch):
    monkeypatch.setattr(fetch.ura_pmi_api, "get_access_key", lambda: "key")
    monkeypatch.setattr(fetch.ura_pmi_api, "generate_token", lambda key, session: "token")
    monkeypatch.setattr(fetch.ura_pmi_api, "fetch_transactions", lambda key, token, batch, session: {
        "Status": "Success", "Result": [{"project": "CANBERRA CRESCENT RESIDENCES", "transaction": []}]})
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)
    with pytest.raises(fetch.ProjectNotFound, match="CANBERRA CRESCENT RESIDENCES"):
        fetch.fetch_ura("CANBERRA CRESCENT RESIDENCE")


def test_find_edgeprop_project_matches_names_case_insensitively(tmp_path, monkeypatch):
    listing = tmp_path / "projects.csv"
    listing.write_text("name,url,slug\nCanberra Crescent Residences,https://www.edgeprop.sg/condo-apartment/ccr,ccr\n")
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **k: pytest.fail("discovery must not run for a listed project"))
    assert fetch.find_edgeprop_project("CANBERRA CRESCENT RESIDENCES", listing, tmp_path)["slug"] == "ccr"


def test_find_edgeprop_project_runs_discovery_for_unlisted_names(tmp_path, monkeypatch):
    listing = tmp_path / "projects.csv"
    listing.write_text("name,url,slug\n")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        (tmp_path / "edgeprop_projects.csv").write_text("name,url,slug\nNEW PROJECT,https://x/new,new\n")

    monkeypatch.setattr(fetch.subprocess, "run", fake_run)
    assert fetch.find_edgeprop_project("New Project", listing, tmp_path)["slug"] == "new"
    assert "discover" in calls[0]
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest tests/test_unit_ledger_build.py -q`
Expected: FAIL with `ImportError: cannot import name 'build'`.

- [ ] **Step 3: Implement `scrapers/unit_ledger/fetch.py`**

```python
"""Network acquisition for the unit ledger. Writes raw captures only; never interprets them."""

from __future__ import annotations

import csv
import difflib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from scrapers import ura_pmi_api
from scrapers.unit_ledger import sources

ROOT = Path(__file__).resolve().parents[2]
EDGEPROP_SCRIPT = ROOT / "scrapers" / "edgeprop_condo_apartment_playwright.py"
EDGEPROP_PROJECTS = ROOT / "data" / "raw" / "edgeprop" / "edgeprop_condo_apartment_projects.csv"
PROPERTYNOOB_URL = "https://propertynoob.com/condo/{slug}/sales"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


class ProjectNotFound(ValueError):
    def __init__(self, project: str, closest: list[str]):
        super().__init__(f"{project!r} is not a project in the URA API result. "
                         f"Closest URA names: {', '.join(closest) or 'none'}")


def fetch_ura(project: str) -> list[dict]:
    """Every URA PMI_Resi_Transaction project record whose name equals ``project``."""
    key = ura_pmi_api.get_access_key()
    session = requests.Session()
    token = ura_pmi_api.generate_token(key, session)
    wanted = project.strip().upper()
    matches, names = [], set()
    for batch in ura_pmi_api.API_BATCHES:
        data = ura_pmi_api.fetch_transactions(key, token, batch, session)
        if data.get("Status") != "Success":
            raise RuntimeError(f"URA batch {batch} returned Status={data.get('Status')!r}")
        for record in data.get("Result") or []:
            name = str(record.get("project", "")).strip().upper()
            names.add(name)
            if name == wanted:
                matches.append(record)
        time.sleep(1)
    if not matches:
        raise ProjectNotFound(project, difflib.get_close_matches(wanted, sorted(names), n=5, cutoff=0))
    return matches


def _lookup(path: Path, project: str) -> dict | None:
    with path.open(newline="", encoding="utf-8") as handle:
        hits = [row for row in csv.DictReader(handle) if row["name"].strip().upper() == project.strip().upper()]
    return hits[0] if len(hits) == 1 else None


def find_edgeprop_project(project: str, projects_csv: Path, logs: Path) -> dict | None:
    """The EdgeProp project row (name, url, slug), discovering it when the cached list lacks it."""
    if projects_csv.exists():
        hit = _lookup(projects_csv, project)
        if hit:
            return hit
    out = logs / "edgeprop_projects.csv"
    subprocess.run([sys.executable, str(EDGEPROP_SCRIPT), "discover", "--match", project.strip().lower(),
                    "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    return _lookup(out, project) if out.exists() else None


def fetch_edgeprop(link: dict, out_csv: Path, logs: Path) -> str | None:
    """Scrape every EdgeProp transaction for one project. Returns an error message, or None on success."""
    listing = logs / "edgeprop_input.csv"
    with listing.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "url", "slug"])
        writer.writeheader()
        writer.writerow({k: link[k] for k in ("name", "url", "slug")})
    command = [sys.executable, str(EDGEPROP_SCRIPT), "scrape", "--input", str(listing), "--from-year", "1990",
               "--max-pages", "1000", "--out", str(out_csv), "--log", str(logs / "edgeprop_attempts.csv")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (logs / "edgeprop_scrape.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0 or not out_csv.exists():
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["no rows written"]
        return f"EdgeProp scrape did not complete ({tail[0]}); affected rows have no exact date, block or floor."
    return None


def fetch_page(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_all(project: str, raw: Path, logs: Path, *, chart_url: str | None = None,
              recent_sales: Path | None = None) -> dict:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    info = {"project": project.strip().upper(), "fetched_at_utc": fetched_at, "sources": {}, "warnings": []}

    def warn(source, url, message):
        info["sources"][source] = {"url": url, "status": "missing", "error": message}
        info["warnings"].append(message)

    records = fetch_ura(project)
    (raw / "ura.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    info["sources"]["ura"] = {"url": "URA Data Service PMI_Resi_Transaction", "status": "ok"}

    link = find_edgeprop_project(project, EDGEPROP_PROJECTS, logs)
    if link is None:
        warn("edgeprop", "", f"EdgeProp has no project page named {project!r}; rows have no exact date, block or floor.")
    else:
        error = fetch_edgeprop(link, raw / "edgeprop.csv", logs)
        if error:
            warn("edgeprop", link["url"], error)
        else:
            info["sources"]["edgeprop"] = {"url": link["url"], "status": "ok"}

    pn_url = PROPERTYNOOB_URL.format(slug=link["slug"] if link else sources.slugify(project))
    try:
        html = fetch_page(pn_url)
        sources.load_propertynoob(html, source_url=pn_url, fetched_at_utc=fetched_at)
    except requests.RequestException as exc:
        warn("propertynoob", pn_url, f"PropertyNoob page unavailable ({exc}); no published unit numbers.")
    except ValueError as exc:
        if "found 0" not in str(exc) and "no transaction rows" not in str(exc):
            raise
        warn("propertynoob", pn_url, f"PropertyNoob has no sales table at {pn_url}; no published unit numbers.")
    else:
        (raw / "propertynoob.html").write_text(html, encoding="utf-8")
        info["sources"]["propertynoob"] = {"url": pn_url, "status": "ok"}

    if chart_url:
        try:
            html = fetch_page(chart_url)
        except requests.RequestException as exc:
            warn("chart", chart_url, f"Unit chart unavailable ({exc}); the site view is derived from sales.")
        else:
            sources.parse_chart(html)  # an unsupported template aborts the run
            (raw / "chart.html").write_text(html, encoding="utf-8")
            info["sources"]["chart"] = {"url": chart_url, "status": "ok"}

    if recent_sales:
        sources.load_recent_sales(pd.read_csv(recent_sales, dtype=str))
        shutil.copyfile(recent_sales, raw / "recent_sales.csv")
        info["sources"]["recent_sales"] = {"url": str(recent_sales), "status": "ok"}

    (raw / "fetch.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info
```

- [ ] **Step 4: Implement `scrapers/unit_ledger/build.py`**

```python
"""Assemble a unit-ledger run directory: offline from raw/, or after a fresh fetch."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from scrapers.unit_ledger import layout, match, sources
from scrapers.unit_ledger.render import render

ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "data" / "runs" / "unit-ledger"


def _readme(meta: dict) -> str:
    c = meta["counts"]
    lines = [
        f"# {meta['project']}: unit ledger", "",
        f"Fetched {meta['fetched_at_utc']}. Research output, not a model input. Unit numbers come from "
        "third-party sources and are not official. Open `index.html` for the table and site view.", "",
        "| Measure | Count |", "| --- | ---: |",
        f"| Transactions | {c['transactions']} |",
        f"| From the URA API (last five years) | {c['ura']} |",
        f"| Older, not verified against the URA API | {c['pre_window']} |",
        f"| With an exact date | {c['dated']} |",
        f"| With a unit number | {c['with_unit']} |",
        f"| Ambiguous | {c['ambiguous']} |",
        f"| Not found | {c['not_found']} |",
    ]
    if c["uniquely_located"] is not None:
        lines.append(f"| URA rows whose block, floor and size alone fix the unit | {c['uniquely_located']} |")
    lines += ["", "## How units were matched", "", "| Rule | Rows |", "| --- | ---: |"]
    lines += [f"| {rule} | {n} |" for rule, n in sorted(c["unit_source"].items())]
    lines += ["", "## Warnings", ""] + ([f"- {w}" for w in meta["warnings"]] or ["None."])
    return "\n".join(lines) + "\n"


def build_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    raw = run_dir / "raw"
    fetch_info = json.loads((raw / "fetch.json").read_text(encoding="utf-8"))
    warnings = list(fetch_info.get("warnings", []))

    ura = sources.load_ura(json.loads((raw / "ura.json").read_text(encoding="utf-8")))
    ep = sources.load_edgeprop([pd.read_csv(p, dtype=str, keep_default_na=False)
                                for p in sorted(raw.glob("edgeprop*.csv"))])
    chart, chart_as_of = (sources.parse_chart((raw / "chart.html").read_text(encoding="utf-8"))
                          if (raw / "chart.html").exists() else (None, ""))
    pn = (sources.load_propertynoob((raw / "propertynoob.html").read_text(encoding="utf-8"),
                                    source_url=fetch_info["sources"]["propertynoob"]["url"],
                                    fetched_at_utc=fetch_info["fetched_at_utc"])
          if (raw / "propertynoob.html").exists() else sources.empty_propertynoob())
    recent = (sources.load_recent_sales(pd.read_csv(raw / "recent_sales.csv", dtype=str))
              if (raw / "recent_sales.csv").exists() else sources.empty_recent_sales())
    has_chart = chart is not None

    result = match.match_all(ura, ep, pn, chart, recent)
    ledger = result.ledger
    units = layout.summarise_units(result.units, ledger, recent, has_chart)

    no_edgeprop = int(((ledger.origin == "URA") & (ledger.sale_date == "")).sum())
    if no_edgeprop:
        warnings.append(f"{no_edgeprop} URA transactions have no matching EdgeProp record, "
                        "so they have no exact date, block or floor.")
    if result.unmatched_edgeprop:
        warnings.append(f"{result.unmatched_edgeprop} EdgeProp rows inside the URA window match no URA transaction.")
    if result.unmatched_propertynoob:
        warnings.append(f"{result.unmatched_propertynoob} PropertyNoob rows inside the URA window match no "
                        "transaction (for example a lapsed booking, or a sale URA has not published).")

    counts = {
        "transactions": len(ledger),
        "ura": int((ledger.origin == "URA").sum()),
        "pre_window": int((ledger.origin == "Pre-window").sum()),
        "dated": int((ledger.sale_date != "").sum()),
        "with_unit": int((ledger.unit != "").sum()),
        "ambiguous": int(ledger.unit_source.str.startswith("Ambiguous").sum()),
        "not_found": int((ledger.unit_source == "Not found").sum()),
        "uniquely_located": match.uniquely_located_count(ledger, chart) if has_chart else None,
        "unit_source": {k: int(v) for k, v in ledger.unit_source.str.split(":").str[0].value_counts().items()},
    }
    meta = {"project": fetch_info["project"], "fetched_at_utc": fetch_info["fetched_at_utc"],
            "chart_as_of": chart_as_of, "has_chart": has_chart, "warnings": warnings, "counts": counts}

    ledger.to_csv(run_dir / "transactions.csv", index=False)
    units.to_csv(run_dir / "units.csv", index=False)
    (run_dir / "index.html").write_text(render(ledger, units, meta), encoding="utf-8")
    provenance = {**fetch_info, "warnings": warnings, "counts": counts, "chart_as_of": chart_as_of,
                  "raw_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(raw.iterdir()) if p.is_file()}}
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=1), encoding="utf-8")
    (run_dir / "README.md").write_text(_readme(meta), encoding="utf-8")
    return meta


def run(project: str, *, chart_url: str | None = None, recent_sales: Path | None = None,
        runs_root: Path = RUNS_ROOT, today: str | None = None) -> Path:
    """Fetch and build into a partial directory; replace the day's run only once everything succeeded."""
    from scrapers.unit_ledger import fetch  # network dependencies load only when fetching

    today = today or date.today().isoformat()
    final = Path(runs_root) / sources.slugify(project) / today
    work = final.with_name(f".{today}.partial")
    shutil.rmtree(work, ignore_errors=True)
    (work / "raw").mkdir(parents=True)
    (work / "logs").mkdir()
    try:
        fetch.fetch_all(project, work / "raw", work / "logs", chart_url=chart_url, recent_sales=recent_sales)
        build_run(work)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    if final.exists():
        shutil.rmtree(final)
    work.rename(final)
    return final
```

- [ ] **Step 5: Implement `scrapers/unit_ledger/__main__.py`**

```python
"""Unit ledger command line.

    python3 -m scrapers.unit_ledger run --project "CANBERRA CRESCENT RESIDENCES" \\
        [--chart-url URL] [--recent-sales FILE.csv]
    python3 -m scrapers.unit_ledger rebuild data/runs/unit-ledger/<slug>/<YYYY-MM-DD>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scrapers.unit_ledger import build


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m scrapers.unit_ledger", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="fetch every source and build a run directory")
    run.add_argument("--project", required=True, help="project name exactly as URA publishes it")
    run.add_argument("--chart-url", help="singmap agent-site unit chart, e.g. https://<project>.isaacyee.com/units")
    run.add_argument("--recent-sales", type=Path, help="CSV with columns date,unit (developer's recently sold list)")
    rebuild = commands.add_parser("rebuild", help="rebuild outputs offline from a run directory's raw/")
    rebuild.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            out = build.run(args.project, chart_url=args.chart_url, recent_sales=args.recent_sales)
        else:
            build.build_run(args.run_dir)
            out = args.run_dir
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print((out / "README.md").read_text(encoding="utf-8"))
    print(f"Page: {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `python3 -m pytest tests/test_unit_ledger_build.py -q`
Expected: 7 passed.

- [ ] **Step 7: Check the command-line help**

Run: `python3 -m scrapers.unit_ledger run --help`
Expected: usage text listing `--project`, `--chart-url` and `--recent-sales`, with exit code 0.

- [ ] **Step 8: Run the whole default gate, then commit**

Run: `make smoke`
Expected: PASS.

```bash
git add scrapers/unit_ledger/fetch.py scrapers/unit_ledger/build.py scrapers/unit_ledger/__main__.py tests/test_unit_ledger_build.py
git commit -m "feat(unit-ledger): fetch sources and assemble run directories from the CLI

run fetches URA (required), EdgeProp, PropertyNoob and an optional chart
into a partial directory and replaces the day's run only on success;
rebuild works offline from raw/.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Canberra regression and the Canberra page

**Files:**
- Test: `tests/test_unit_ledger_canberra_regression.py`
- Local only (Git-ignored): `data/runs/unit-ledger/canberra-crescent-residences/2026-09-26/`
- Delete: `canberra_crescent_transactions.html` in the repository root. It is untracked, so this is a plain `rm`.

**Interfaces:**
- Consumes: `build.build_run` (Task 5) and the captures in
  `data/runs/unit-ledger-regression/canberra-crescent-residences/`: `raw/` holds `fetch.json`,
  `ura.json`, three `edgeprop*.csv` files, `propertynoob.html`, `chart.html` and `recent_sales.csv`;
  `golden/assignments.csv` holds the 348 `block,unit,sale_date,price` rows.

- [ ] **Step 1: Write the regression test**

`tests/test_unit_ledger_canberra_regression.py`:

```python
"""Rebuild Canberra Crescent Residences from saved captures and compare with the approved page.

The captures hold third-party unit-level records and stay in Git-ignored data/runs/, so this
test skips on machines (including CI) that do not have them.
"""

import shutil
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from scrapers.unit_ledger import build

REGRESSION = Path(__file__).resolve().parents[1] / "data/runs/unit-ledger-regression/canberra-crescent-residences"
pytestmark = pytest.mark.skipif(not (REGRESSION / "raw" / "ura.json").exists(),
                                reason="local Canberra captures are not present")


def test_rebuild_reproduces_the_348_approved_assignments(tmp_path):
    shutil.copytree(REGRESSION / "raw", tmp_path / "raw")
    meta = build.build_run(tmp_path)
    got = pd.read_csv(tmp_path / "transactions.csv", dtype=str, keep_default_na=False)
    got = got[got.origin == "URA"][["block", "unit", "sale_date", "price"]]
    want = pd.read_csv(REGRESSION / "golden" / "assignments.csv", dtype=str, keep_default_na=False)
    missing = Counter(map(tuple, want.values)) - Counter(map(tuple, got.values))
    extra = Counter(map(tuple, got.values)) - Counter(map(tuple, want.values))
    assert not missing and not extra, f"missing={sorted(missing)[:10]} extra={sorted(extra)[:10]}"
    assert meta["counts"]["ura"] == 348 and meta["counts"]["pre_window"] == 0
    assert meta["counts"]["uniquely_located"] == 189
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_unit_ledger_canberra_regression.py -q`
Expected: 1 passed.

**If it fails, stop.** Do not change a matching rule or the golden file to make it pass. Write down
each differing `(block, unit, sale_date, price)` with its `unit_source`, `date_source` and `conflict`
from `tmp_path/transactions.csv`, and report them to the user (spec: "If the Canberra regression
shows that any assignment depended on it, implementation stops"). To see the row details, rerun with
`python3 -m pytest tests/test_unit_ledger_canberra_regression.py -q --basetemp=/tmp/ul-reg` and read
the file that `find /tmp/ul-reg -name transactions.csv` prints.

- [ ] **Step 3: Build the Canberra run directory and read the page**

```bash
R=data/runs/unit-ledger/canberra-crescent-residences/2026-09-26
mkdir -p "$R" && cp -R data/runs/unit-ledger-regression/canberra-crescent-residences/raw "$R/raw"
python3 -m scrapers.unit_ledger rebuild "$R"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --dump-dom "file://$PWD/$R/index.html" 2>/dev/null \
  | python3 -c "import sys,re; d=sys.stdin.read(); body=re.search(r'<tbody id=\"body\">(.*?)</tbody>', d, re.S).group(1); print('rows', body.count('<tr')); print('blocks', re.findall(r'<h3>(Blk [^<]+)</h3>', d)); print('pending', d.count('class=\"pending\"'), 'available', d.count('class=\"available\"'))"
```

Expected:
- The README printout shows 348 transactions, 348 with an exact date, and 348 with a unit number.
- The warnings list PropertyNoob rows inside the URA window that match no transaction.
- The headless check prints `rows 348`, the blocks `['Blk 51', 'Blk 53', 'Blk 55', 'Blk 57']`, `pending 5` and `available 23`.

Then take a headless screenshot, `--screenshot=/tmp/ul.png --window-size=1400,1900 --virtual-time-budget=3000`,
and look at it. Check that the table renders and the four block grids appear lower on the page.

- [ ] **Step 4: Remove the superseded root page**

```bash
rm canberra_crescent_transactions.html
git status --short
```

Expected: `canberra_crescent_transactions.html` no longer appears, and no file under `data/runs/` is
listed.

- [ ] **Step 5: Commit the test**

```bash
git add tests/test_unit_ledger_canberra_regression.py
git commit -m "test(unit-ledger): pin the Canberra Crescent 348-row assignment

Skips when the local, Git-ignored captures are absent.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Resale smoke run, documentation and final gate

**Files:**
- Modify: `scrapers/README.md` (append a "Unit ledger" section)
- Local only: `data/runs/unit-ledger/the-poiz-residences/<today>/`

- [ ] **Step 1: Confirm the URA key is visible to this shell without printing it**

Run: `python3 -c "import os; print('set' if os.environ.get('URA_ACCESS_KEY') else 'missing')"`
Expected: `set`. If it prints `missing`, run `source ~/.zshrc` in the same command before the next
step (the session environment may predate the key).

- [ ] **Step 2: Run the pipeline live on a resale-heavy project**

Run: `python3 -m scrapers.unit_ledger run --project "THE POIZ RESIDENCES"`
Expected: exit code 0, and a README printout with non-zero Resale rows and a `Pre-window` count.

If the result is `ProjectNotFound`, rerun with the closest URA name from the message. The EdgeProp
scrape takes several minutes; that is expected.

- [ ] **Step 3: Record the coverage**

```bash
D=$(ls -d data/runs/unit-ledger/the-poiz-residences/*/ | tail -1)
python3 -c "
import json,sys; p=json.load(open('${D}provenance.json')); c=p['counts']
print({k: c[k] for k in ('transactions','ura','pre_window','dated','with_unit','ambiguous','not_found')})
print(c['unit_source']); print(p['warnings'])"
```

Expected: the numbers print. There is no pass threshold: this is the coverage report for success
criterion 2. Keep the output for the final summary to the user.

- [ ] **Step 4: Document usage in `scrapers/README.md`**

Append:

```markdown
## Unit ledger (per-project transactions by unit)

`python3 -m scrapers.unit_ledger run --project "<name exactly as URA publishes it>"` fetches the
project's URA transactions (last five years; needs `URA_ACCESS_KEY`), its full EdgeProp history, and
its PropertyNoob sales page. It then writes
`data/runs/unit-ledger/<slug>/<YYYY-MM-DD>/index.html`: a sortable transaction table and a site sales
view.

- `--chart-url` adds a singmap agent-site unit chart (for example `https://<project>.isaacyee.com/units`)
  for new launches.
- `--recent-sales FILE.csv` (columns `date,unit`) adds a developer's recently sold list.
- `python3 -m scrapers.unit_ledger rebuild <run dir>` rebuilds offline from the run's `raw/`.

Outputs stay in the Git-ignored `data/runs/` because they hold third-party unit-level records
(`docs/DATA_GOVERNANCE.md`). Design: `docs/superpowers/specs/2026-09-26-unit-ledger-design.md`.
```

- [ ] **Step 5: Final gate**

Run: `make smoke`
Expected: PASS. This includes the Canberra regression on this machine.

- [ ] **Step 6: Commit**

```bash
git add scrapers/README.md
git commit -m "docs(scrapers): document the unit ledger command

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
