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
