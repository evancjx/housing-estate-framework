"""Offline contract tests for public PropertyNoob transaction extraction."""

import csv
from html import escape

import pytest

from scrapers.propertynoob_sales import main, parse_sales_html, write_sales_csv


SOURCE_URL = "https://propertynoob.com/condo/example-project/sales/"
FETCHED_AT = "2026-09-20T04:00:00Z"


def _row(sequence, *, unit="#02-03", sale="New", price="$1,500,000"):
    return [str(sequence), "14 Jun 2025", price, unit, "721", "$2,080", "Apartment", sale]


def _html(rows):
    header = "<tr>" + "".join(
        f"<th>{cell}</th>"
        for cell in ["&nbsp;", "Date", "Price", "Unit", "Area (sqft)", "PSF", "Type", "Sale"]
    ) + "</tr>"
    body = "".join(
        "<tr>" + "".join(f"<td><span>{escape(cell)}</span></td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        "<table><tbody><tr><td>Record Price</td><td>$9,000,000</td></tr></tbody></table>"
        f"<table><thead>{header}</thead><tbody>{body}</tbody></table>"
    )


def _parse(html):
    return parse_sales_html(
        html, project_name=" Example Project ", source_url=SOURCE_URL, fetched_at_utc=FETCHED_AT
    )


def test_preserves_every_occurrence_and_all_sale_types(tmp_path):
    rows = _parse(_html([_row(4, sale="Resale"), _row(3, sale="Sub"), _row(2), _row(1)]))
    assert [r["source_row_number"] for r in rows] == [4, 3, 2, 1]
    assert [r["sale_type"] for r in rows] == ["Resale", "Sub Sale", "New Sale", "New Sale"]
    assert [r["source_sale_type"] for r in rows] == ["Resale", "Sub", "New", "New"]
    assert len({r["unit_number"] for r in rows}) == 1
    assert rows[0]["unit_number"] == "#02-03"
    assert rows[0]["unit_number_status"] == "exact"
    assert rows[0]["sale_date"] == "2025-06-14"
    assert rows[0]["price_sgd"] == 1500000
    assert rows[0]["area_sqft"] == 721
    assert rows[0]["unit_price_psf"] == 2080
    assert rows[0]["project_name"] == "EXAMPLE PROJECT"
    assert rows[0]["source_slug"] == "example-project"
    assert rows[0]["source_url"] == SOURCE_URL
    assert rows[0]["fetched_at_utc"] == FETCHED_AT
    out = tmp_path / "sales.csv"
    write_sales_csv(rows, out)
    assert b"\r\n" not in out.read_bytes()
    with out.open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 4


@pytest.mark.parametrize("unit,status", [("#02-XX", "masked"), ("#**-03", "masked"), ("-", "not_present")])
def test_does_not_fill_masked_or_missing_units(unit, status):
    row = _parse(_html([_row(1, unit=unit)]))[0]
    assert row["unit_number"] == unit
    assert row["unit_number_status"] == status


@pytest.mark.parametrize("sequence", [[3, 1], [2, 2], [1, 2], [3, 2]])
def test_rejects_partial_or_reordered_sequence(sequence):
    with pytest.raises(ValueError, match="sequence must descend"):
        _parse(_html([_row(i) for i in sequence]))


@pytest.mark.parametrize(
    "html,message",
    [
        ("<html>Blocked</html>", "Expected exactly one sales table"),
        (_html([_row(1)]).replace("Area (sqft)", "Area (sqm)"), "schema changed"),
        (_html([_row(1)]) + _html([_row(1)]), "found 2"),
        (_html([_row(1)])[:-8], "Truncated HTML"),
        (_html([_row(1)[:-1]]), "eight data cells"),
        (_html([_row(1, price="$1,50,000")]), "invalid price"),
        (_html([_row(1, sale="Unknown")]), "unknown sale type"),
        (_html([_row(1, unit="02-03")]), "invalid unit token"),
        (_html([_row(1)]).replace("14 Jun 2025", "31 Jun 2025"), "day is out of range"),
        (_html([]), "no transaction rows"),
    ],
)
def test_rejects_malformed_or_changed_source(html, message):
    with pytest.raises(ValueError, match=message):
        _parse(html)


def test_cli_validates_before_overwriting_existing_output(tmp_path, capsys):
    html_file = tmp_path / "sales.html"
    html_file.write_text(_html([_row(2)]), encoding="utf-8")
    out = tmp_path / "sales.csv"
    out.write_text("previous capture\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([
            "parse", "--html-file", str(html_file), "--project-name", "EXAMPLE PROJECT",
            "--source-url", SOURCE_URL, "--fetched-at-utc", FETCHED_AT, "--out", str(out),
        ])
    assert exc.value.code == 1
    assert "sequence must descend" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "previous capture\n"
