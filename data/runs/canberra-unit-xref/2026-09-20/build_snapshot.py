"""Rebuild this research snapshot from the adjacent, source-labelled CSVs.

Run from any directory. This is an isolated research extract, not a model input.
Public unit numbers are source assertions; masked-unit links are inferences.
"""

import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent


def read(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write(name, rows):
    with (HERE / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def integer(value):
    return int(value.replace(",", ""))


def main():
    chart = read(HERE / "agent_unit_chart.csv")
    published = read(HERE / "published_unit_transactions.csv")
    masked = read(HERE / "masked_transactions.csv")
    huttons = {r["unit"]: r for r in read(HERE / "huttons_unit_status.csv")}
    current_edgeprop = read(HERE / "edgeprop_current_transactions.csv")
    units = {row["unit"]: row for row in chart}
    assert len(chart) == len(units) == 376
    assert len(huttons) == 376
    assert all(huttons[r["unit"]]["block"] == r["block"] for r in chart)
    assert len(published) == 330
    ura = [
        row for row in read(HERE / "ura_project_snapshot.csv")
        if row["Project Name"] == "CANBERRA CRESCENT RESIDENCES"
        and row["Type of Sale"] == "New Sale"
    ]
    assert len(ura) == 340  # Historical July-cutoff comparison, not current URA.
    observations = []
    for row in published + masked:
        direct = "*" not in row["published_unit"] and "X" not in row["published_unit"]
        if direct:
            candidates = [units[row["published_unit"]]]
        else:
            candidates = [
                unit for unit in chart
                if unit["chart_status"] == "sold"
                and unit["block"] == row["block"]
                and unit["unit"].split("-")[0] == row["published_unit"].split("-")[0]
                and unit["area_sqft"] == row["area_sqft"]
                and abs((date.fromisoformat(unit["chart_sold_date"])
                         - date.fromisoformat(row["transaction_date"])).days) <= 7
            ]
        unit = candidates[0] if len(candidates) == 1 else None
        floor = int(row["published_unit"].split("-")[0][1:])
        month = datetime.strptime(row["transaction_date"], "%Y-%m-%d").strftime("%b-%y")
        corroboration = [
            official for official in ura
            if official["Sale Date"] == month
            and integer(official["Transacted Price ($)"]) == int(row["price_sgd"])
            and round(float(official["Area (SQFT)"].replace(",", ""))) == int(row["area_sqft"])
            and int(official["Floor Level"].split(" to ")[0]) <= floor
            <= int(official["Floor Level"].split(" to ")[1])
        ]
        current_matches = [
            portal for portal in current_edgeprop
            if datetime.strptime(portal["Date of Sale"], "%d %b %Y").date().isoformat()
            == row["transaction_date"]
            and portal["Address"].split()[0] == row["block"]
            and portal["Address"].split("#")[-1].split("-")[0] == f"{floor:02d}"
            and int(portal["Price ($)"]) == int(row["price_sgd"])
            and int(portal["Area (sqft)"]) == int(row["area_sqft"])
        ]
        status = "published_full_unit" if direct else (
            "inferred_unique_within_7_days" if unit else "unresolved_masked"
        )
        observations.append({
            **row,
            "linked_unit": unit["unit"] if unit else "",
            "unit_link_status": status,
            "candidate_unit_count": len(candidates),
            "candidate_units": "|".join(c["unit"] for c in candidates),
            "chart_sold_date": unit["chart_sold_date"] if unit else "",
            "transaction_minus_chart_days": (
                (date.fromisoformat(row["transaction_date"])
                 - date.fromisoformat(unit["chart_sold_date"])).days if unit else ""
            ),
            "local_ura_matching_record_count": len(corroboration),
            "current_edgeprop_matching_record_count": len(current_matches),
            "local_ura_check": (
                "matching_public_signature_not_unit_proof" if corroboration
                else "after_local_snapshot" if row["transaction_date"] >= "2026-08-01"
                else "no_matching_public_signature"
            ),
        })
    write("price_observations.csv", observations)

    inventory = []
    for unit in chart:
        huttons_unit = huttons[unit["unit"]]
        huttons_status = "sold" if huttons_unit["sold"] == "True" else "available"
        status_conflict = huttons_status != unit["chart_status"]
        matched = [r for r in observations if r["linked_unit"] == unit["unit"]]
        # Retain every source observation, but don't count a second source for
        # the same date/price/size as another transaction event.
        events = {(r["transaction_date"], int(r["price_sgd"]), r["area_sqft"]) for r in matched}
        prices = sorted({event[1] for event in events})
        if not prices:
            status = "sold_price_not_found" if "sold" in (unit["chart_status"], huttons_status) else "chart_available"
        elif len(prices) > 1:
            status = "multiple_historical_prices_review"
        elif not any(r["local_ura_matching_record_count"] or r["current_edgeprop_matching_record_count"] for r in matched):
            status = "published_price_unreconciled"
        elif any(r["unit_link_status"] == "published_full_unit" for r in matched):
            status = "published_full_unit_price"
        else:
            status = "inferred_unit_price"
        inventory.append({
            **unit,
            "huttons_status": huttons_status,
            "status_conflict": status_conflict,
            "huttons_source_url": huttons_unit["source"],
            "price_status": status,
            "price_sgd": prices[0] if len(prices) == 1 and status != "published_price_unreconciled" else "",
            "historical_price_min_sgd": min(prices) if prices else "",
            "historical_price_max_sgd": max(prices) if prices else "",
            "source_observation_count": len(matched),
            "distinct_date_price_area_events": len(events),
            "earliest_transaction_date": min((r["transaction_date"] for r in matched), default=""),
            "latest_transaction_date": max((r["transaction_date"] for r in matched), default=""),
            "price_source_urls": "|".join(sorted({r["source_url"] for r in matched})),
            "review_note": (
                "Published historical price has no matching local URA or current EdgeProp signature; current achieved price unresolved."
                if status == "published_price_unreconciled" else
                "Different historical prices retained; cancellation/rebooking/correction not established."
                if len(prices) > 1 else
                "Repeated transaction dates at one price; current legal status not established."
                if len(events) > 1 else ""
            ),
        })
    assert len({r["unit"] for r in inventory}) == 376
    assert all(not r["price_sgd"] for r in inventory if r["price_status"] == "multiple_historical_prices_review")
    write("unit_price_inventory.csv", inventory)
    counts = {
        "chart_units": len(chart),
        "chart_status": dict(Counter(r["chart_status"] for r in chart)),
        "huttons_status": dict(Counter(r["huttons_status"] for r in inventory)),
        "status_conflict_units": [r["unit"] for r in inventory if r["status_conflict"]],
        "direct_transaction_records": len(published),
        "direct_distinct_units": len({r["published_unit"] for r in published}),
        "masked_transaction_records": len(masked),
        "observation_link_status": dict(Counter(r["unit_link_status"] for r in observations)),
        "inventory_price_status": dict(Counter(r["price_status"] for r in inventory)),
        "units_with_any_price_observation": sum(bool(r["source_observation_count"]) for r in inventory),
        "units_with_single_price_value": sum(bool(r["price_sgd"]) for r in inventory),
    }
    (HERE / "counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
