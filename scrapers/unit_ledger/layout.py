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
    for block, stack in zip(units["block"], units["stack"]):
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
