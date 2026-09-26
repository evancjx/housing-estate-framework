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
