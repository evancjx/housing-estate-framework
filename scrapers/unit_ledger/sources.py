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
