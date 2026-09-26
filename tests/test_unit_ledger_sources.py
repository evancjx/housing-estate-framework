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
