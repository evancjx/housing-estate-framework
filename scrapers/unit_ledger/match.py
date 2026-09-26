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
            learned.setdefault(candidates["stack"].iat[0], set()).add(group.block.iat[0])
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
