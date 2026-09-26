"""Parse the complete transaction table from a saved public PropertyNoob sales page.

Every source row is preserved, including repeat sales and apparent duplicates.
Sequence checks establish completeness of the supplied table, not the provider's
coverage of actual transactions. Unit tokens are reported as printed; a token
alone does not identify a block in a development with multiple blocks.
"""

import argparse
import csv
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlparse


HEADERS = ["", "Date", "Price", "Unit", "Area (sqft)", "PSF", "Type", "Sale"]
SALE_TYPES = {"New": "New Sale", "Sub": "Sub Sale", "Resale": "Resale"}
FIELDNAMES = [
    "project_name", "source_slug", "source_row_number", "sale_date", "price_sgd",
    "unit_number", "unit_number_status", "area_sqft", "unit_price_psf",
    "property_type", "sale_type", "source_sale_type", "source_url", "fetched_at_utc",
]


class _TableParser(HTMLParser):
    """Collect table cells, retaining header tags and rejecting truncated tables."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell_tag = None
        self.cell_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table is not None:
                raise ValueError("Nested table encountered; sales HTML schema changed")
            self.table = []
        elif self.table is not None and tag == "tr":
            if self.row is not None:
                raise ValueError("Malformed table: previous row was not closed")
            self.row = []
        elif self.table is not None and tag in {"th", "td"}:
            if self.row is None or self.cell_tag is not None:
                raise ValueError("Malformed table: unexpected cell")
            self.cell_tag = tag
            self.cell_text = []

    def handle_data(self, data):
        if self.cell_tag is not None:
            self.cell_text.append(data)

    def handle_endtag(self, tag):
        if self.table is None:
            return
        if tag in {"td", "th"}:
            if self.cell_tag != tag or self.row is None:
                raise ValueError("Malformed table: mismatched cell closing tag")
            self.row.append((tag, " ".join("".join(self.cell_text).split())))
            self.cell_tag = None
        elif tag == "tr":
            if self.row is None or self.cell_tag is not None:
                raise ValueError("Malformed table: incomplete row")
            self.table.append(self.row)
            self.row = None
        elif tag == "table":
            if self.row is not None or self.cell_tag is not None:
                raise ValueError("Malformed table: incomplete row at table end")
            self.tables.append(self.table)
            self.table = None

    def close(self):
        super().close()
        if self.table is not None:
            raise ValueError("Truncated HTML: table was not closed")


def _positive_integer(value, field, currency=False):
    pattern = r"(?:[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)"
    if currency:
        pattern = r"\$" + pattern
    if not re.fullmatch(pattern, value):
        raise ValueError(f"invalid {field}: {value!r}")
    return int(value.removeprefix("$").replace(",", ""))


def _unit_status(unit):
    if unit in {"", "-", "N/A"}:
        return "not_present"
    if re.fullmatch(r"#(?:\d+|PH|B\d+)-\d+[A-Z]?", unit):
        return "exact"
    if re.fullmatch(r"#[A-Za-z0-9*?]+-[A-Za-z0-9*?]+", unit) and re.search(
        r"[xX*?]", unit
    ):
        return "masked"
    raise ValueError(f"invalid unit token: {unit!r}")


def parse_sales_html(html, *, project_name, source_url, fetched_at_utc, source_slug=None):
    """Return normalized rows, failing instead of silently returning partial data."""
    if not project_name.strip():
        raise ValueError("project_name must not be empty")
    if source_slug is None:
        match = re.fullmatch(r"/condo/([^/]+)/sales/?", urlparse(source_url).path)
        if match is None:
            raise ValueError("Cannot derive source_slug from source_url; specify source_slug")
        source_slug = match.group(1)

    parser = _TableParser()
    parser.feed(html)
    parser.close()
    sales_tables = [
        table for table in parser.tables
        if table and [text for _, text in table[0]] == HEADERS
        and all(tag == "th" for tag, _ in table[0])
    ]
    if len(sales_tables) != 1:
        raise ValueError(
            "Expected exactly one sales table with headers "
            f"{HEADERS!r}; found {len(sales_tables)} (missing table or schema changed)"
        )
    table = sales_tables[0]
    if len(table) == 1:
        raise ValueError("Sales table contains no transaction rows")

    rows = []
    for position, cells in enumerate(table[1:], start=1):
        if len(cells) != len(HEADERS) or any(tag != "td" for tag, _ in cells):
            raise ValueError(f"Sales row {position}: expected eight data cells")
        sequence, date, price, unit, area, psf, property_type, sale = [
            text for _, text in cells
        ]
        try:
            if not property_type:
                raise ValueError("property type is missing")
            if sale not in SALE_TYPES:
                raise ValueError(f"unknown sale type: {sale!r}")
            row = {
                "project_name": project_name.strip().upper(),
                "source_slug": source_slug,
                "source_row_number": _positive_integer(sequence, "sequence"),
                "sale_date": datetime.strptime(date, "%d %b %Y").date().isoformat(),
                "price_sgd": _positive_integer(price, "price", currency=True),
                "unit_number": unit,
                "unit_number_status": _unit_status(unit),
                "area_sqft": _positive_integer(area, "area"),
                "unit_price_psf": _positive_integer(psf, "PSF", currency=True),
                "property_type": property_type,
                "sale_type": SALE_TYPES[sale],
                "source_sale_type": sale,
                "source_url": source_url,
                "fetched_at_utc": fetched_at_utc,
            }
        except ValueError as exc:
            raise ValueError(f"Sales row {position} (source sequence {sequence!r}): {exc}") from exc
        rows.append(row)

    actual = [row["source_row_number"] for row in rows]
    expected = list(range(len(rows), 0, -1))
    if actual != expected:
        mismatch = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
        raise ValueError(
            "Sales sequence must descend without gaps or duplicate IDs from "
            f"{len(rows)} to 1; row {mismatch + 1} has {actual[mismatch]}, "
            f"expected {expected[mismatch]}"
        )
    return rows


def write_sales_csv(rows, path):
    """Write validated rows as UTF-8 CSV with LF line endings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("parse", help="Parse a saved public sales HTML page")
    command.add_argument("--html-file", type=Path, required=True)
    command.add_argument("--project-name", required=True)
    command.add_argument("--source-url", required=True)
    command.add_argument("--source-slug")
    command.add_argument("--fetched-at-utc", required=True, help="Actual HTML capture timestamp")
    command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows = parse_sales_html(
            args.html_file.read_text(encoding="utf-8"),
            project_name=args.project_name,
            source_url=args.source_url,
            source_slug=args.source_slug,
            fetched_at_utc=args.fetched_at_utc,
        )
        write_sales_csv(rows, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"PropertyNoob parse failed: {exc}\n")
    print(f"Wrote {len(rows)} source transaction rows to {args.out}")


if __name__ == "__main__":
    main()
