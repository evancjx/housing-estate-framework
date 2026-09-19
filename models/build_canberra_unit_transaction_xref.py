#!/usr/bin/env python3
"""Build an auditable Canberra Crescent unit-to-transaction cross-reference.

This is a research dataset, not a canonical model input.  Exact unit numbers and
"sold" dates come from an independently managed marketing availability page.
Prices and public transaction attributes come from the repository's EdgeProp
and URA PMI snapshots.  The builder keeps those source concepts separate and
never assigns a price to a unit when more than one globally optimal assignment
exists.

The matching sequence is deliberately conservative:

1. Parse the four tower tables from a captured HTML page.
2. Within (block, floor, rounded area, bedrooms), find every maximum-cardinality
   chart-to-EdgeProp assignment with minimum total date cost.  Date cost is
   ``abs((EdgeProp date - reported sold date) - 1 day)`` because the public
   transaction date is normally one day after the marketing status date.
3. Accept only pairs that are identical in every optimal assignment.
4. Reconcile EdgeProp rows to raw URA PMI rows on public transaction fields,
   preserving duplicate occurrence multiplicity.
5. For chart rows with no EdgeProp candidate, permit a clearly labelled
   residual URA inference using area, floor band, and same/adjacent month.

The output must not be promoted into ``data/inputs`` or ``data/outputs`` without
separate source-rights review and a stronger unit-number authority.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT = "CANBERRA CRESCENT RESIDENCES"
UNIT_SOURCE_URL = "https://canberracrescent.projectdeveloper.info/units"
URA_SOURCE_URL = "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch"
EXPECTED_TOWERS: tuple[tuple[int, tuple[int, ...], tuple[int, ...]], ...] = (
    (51, tuple(range(1, 9)), tuple(range(2, 13))),
    (53, tuple(range(9, 17)), tuple(range(1, 13))),
    (55, tuple(range(17, 25)), tuple(range(1, 13))),
    (57, tuple(range(25, 33)), tuple(range(1, 13))),
)

PRIMARY_COLUMNS = [
    "xref_id",
    "project_name",
    "block_number",
    "address",
    "unit_number",
    "floor_number",
    "stack_number",
    "bedrooms",
    "area_sqft_reported",
    "reported_sold_date",
    "unit_number_status",
    "unit_source_status",
    "unit_source_as_of",
    "unit_source_url",
    "match_status",
    "confidence",
    "match_group_id",
    "optimal_assignment_count",
    "transaction_candidate_count",
    "candidate_transaction_date_min",
    "candidate_transaction_date_max",
    "candidate_price_min_sgd",
    "candidate_price_max_sgd",
    "edgeprop_transaction_date",
    "edgeprop_date_delta_days",
    "edgeprop_address",
    "edgeprop_published_unit",
    "edgeprop_record_id",
    "edgeprop_source_url",
    "ura_match_status",
    "ura_record_group_id",
    "ura_record_id",
    "ura_record_identity_status",
    "ura_candidate_count",
    "ura_sale_month",
    "ura_floor_band",
    "ura_area_sqm",
    "ura_area_sqft",
    "ura_transacted_price_sgd",
    "ura_unit_price_psf",
    "ura_type_of_sale",
    "ura_source_url",
    "match_method",
    "match_note",
]

CANDIDATE_COLUMNS = [
    "xref_id",
    "project_name",
    "block_number",
    "unit_number",
    "floor_number",
    "stack_number",
    "area_sqft_reported",
    "bedrooms",
    "reported_sold_date",
    "match_group_id",
    "optimal_assignment_count",
    "candidate_rank",
    "candidate_present_in_optimal_solution",
    "edgeprop_transaction_date",
    "edgeprop_date_delta_days",
    "edgeprop_address",
    "edgeprop_published_unit",
    "edgeprop_record_id",
    "edgeprop_source_url",
    "ura_record_group_id",
    "ura_record_id",
    "ura_record_identity_status",
    "ura_candidate_count",
    "ura_sale_month",
    "ura_floor_band",
    "ura_area_sqm",
    "ura_area_sqft",
    "ura_transacted_price_sgd",
    "ura_unit_price_psf",
    "ura_type_of_sale",
    "ura_source_url",
]


class XrefBuildError(RuntimeError):
    """Raised when a source or matching invariant is not satisfied."""


class _TableParser(HTMLParser):
    """Extract table cell text without adding an undeclared HTML dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"th", "td"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._table_depth == 1 and tag in {"th", "td"} and self._cell_parts is not None:
            assert self._row is not None
            self._row.append(" ".join(" ".join(self._cell_parts).split()))
            self._cell_parts = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            assert self._rows is not None
            if self._row:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1:
                assert self._rows is not None
                self.tables.append(self._rows)
                self._rows = None
            self._table_depth -= 1


@dataclass(frozen=True)
class GroupSolution:
    """All-optima result for one structural match group."""

    group_id: str
    optimum_cost: int
    optimal_assignment_count: int
    forced: dict[int, int]
    candidates: dict[int, tuple[int, ...]]
    unmatched: tuple[int, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, values: Iterable[Any], length: int = 16) -> str:
    payload = "\x1f".join(str(value) for value in values).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:length]}"


def _clean_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).replace({"-": None, "nan": None}),
        errors="coerce",
    )


def _floor_band(floor: int) -> str:
    low = ((int(floor) - 1) // 5) * 5 + 1
    return f"{low:02d} to {low + 4:02d}"


def _month_distance(left: pd.Timestamp, right: pd.Timestamp) -> int:
    return abs((left.year * 12 + left.month) - (right.year * 12 + right.month))


def _parse_chart_cell(value: Any) -> tuple[int, int, str, str]:
    text = " ".join(str(value).split())
    match = re.fullmatch(
        r"(?P<area>[\d,]+) sqft (?P<bedrooms>\d+) BR"
        r"(?: SOLD (?P<date>\d{2} [A-Za-z]{3} \d{4}))?",
        text,
    )
    if not match:
        raise XrefBuildError(f"Unexpected tower-table cell: {text!r}")
    sold_date = ""
    status = "available"
    if match.group("date"):
        sold_date = pd.to_datetime(match.group("date"), format="%d %b %Y").date().isoformat()
        status = "sold"
    return int(match.group("area").replace(",", "")), int(match.group("bedrooms")), status, sold_date


def parse_unit_chart(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    html = path.read_text(encoding="utf-8")
    title_match = re.search(
        r"<title>\s*Canberra Crescent Residences available units as of "
        r"(?P<as_of>\d{1,2} [A-Za-z]{3} \d{4})\s*</title>",
        html,
        flags=re.IGNORECASE,
    )
    if not title_match:
        raise XrefBuildError("Could not find the dated Canberra availability-page title")
    source_as_of = pd.to_datetime(title_match.group("as_of"), format="%d %b %Y").date().isoformat()

    parser = _TableParser()
    parser.feed(html)
    tables = parser.tables
    if len(tables) < 4:
        raise XrefBuildError(f"Expected at least four HTML tables, found {len(tables)}")

    records: list[dict[str, Any]] = []
    for raw_table, (block, expected_stacks, expected_floors) in zip(tables[:4], EXPECTED_TOWERS):
        if not raw_table or len(raw_table[0]) != len(expected_stacks) + 1:
            raise XrefBuildError(f"Unexpected tower-table header width for block {block}")
        headers = raw_table[0]
        body = raw_table[1:]
        if any(len(row) != len(headers) for row in body):
            raise XrefBuildError(f"Ragged tower table for block {block}")
        try:
            floors = tuple(sorted(int(row[0]) for row in body))
        except (TypeError, ValueError) as exc:
            raise XrefBuildError(f"Non-numeric floor label in block {block}") from exc
        if floors != expected_floors:
            raise XrefBuildError(
                f"Unexpected floors for block {block}: expected {expected_floors}, found {floors}"
            )

        parsed_stacks: list[int] = []
        for column in headers[1:]:
            stack_match = re.fullmatch(r"#?(\d{2})", str(column).strip())
            if not stack_match:
                raise XrefBuildError(f"Unexpected stack heading in block {block}: {column!r}")
            parsed_stacks.append(int(stack_match.group(1)))
        if tuple(parsed_stacks) != expected_stacks:
            raise XrefBuildError(
                f"Unexpected stacks for block {block}: expected {expected_stacks}, "
                f"found {tuple(parsed_stacks)}"
            )

        for row in body:
            floor = int(row[0])
            for cell, stack in zip(row[1:], parsed_stacks):
                area, bedrooms, status, sold_date = _parse_chart_cell(cell)
                records.append(
                    {
                        "project_name": PROJECT,
                        "block": block,
                        "floor": floor,
                        "stack": stack,
                        "unit_number": f"#{floor:02d}-{stack:02d}",
                        "area_sqft_reported": area,
                        "bedrooms": bedrooms,
                        "reported_status": status,
                        "reported_sold_date": sold_date,
                        "unit_source_as_of": source_as_of,
                        "unit_source_url": UNIT_SOURCE_URL,
                    }
                )

    frame = pd.DataFrame.from_records(records)
    expected_units = sum(len(stacks) * len(floors) for _, stacks, floors in EXPECTED_TOWERS)
    if len(frame) != expected_units or frame["unit_number"].duplicated().any():
        raise XrefBuildError(
            f"Tower geometry failed: expected {expected_units} unique units, found {len(frame)}"
        )
    frame = frame.sort_values(["block", "floor", "stack"], kind="stable").reset_index(drop=True)
    frame.index.name = "chart_idx"
    return frame, {
        "source_as_of": source_as_of,
        "captured_sha256": _sha256(path),
        "unit_count": int(len(frame)),
        "sold_count": int((frame["reported_status"] == "sold").sum()),
        "available_count": int((frame["reported_status"] == "available").sum()),
    }


def load_edgeprop(path: Path) -> pd.DataFrame:
    source = pd.read_csv(path, low_memory=False)
    project = source[source["Project"].astype(str).str.strip().str.upper().eq(PROJECT)].copy()
    if project.empty:
        raise XrefBuildError(f"No {PROJECT} rows found in {path}")

    address_pattern = re.compile(
        r"^(?P<block>\d+)\s+CANBERRA CRESCENT\s+#(?P<floor>\d{2})-XX$",
        flags=re.IGNORECASE,
    )
    address_parts = project["Address"].astype(str).str.strip().map(address_pattern.fullmatch)
    if address_parts.isna().any():
        examples = project.loc[address_parts.isna(), "Address"].head().tolist()
        raise XrefBuildError(f"Unexpected EdgeProp address format: {examples}")

    project["block"] = [int(match.group("block")) for match in address_parts]
    project["floor"] = [int(match.group("floor")) for match in address_parts]
    project["bedrooms"] = _clean_number(project["Bedrooms"]).astype("Int64")
    project["area_sqft_rounded"] = _clean_number(project["Area (sqft)"]).round().astype("Int64")
    project["transacted_price_sgd"] = _clean_number(project["Price ($)"]).round().astype("Int64")
    project["unit_price_psf"] = _clean_number(project["Unit Price ($psf)"]).round().astype("Int64")
    project["transaction_date"] = pd.to_datetime(project["Date of Sale"], format="%d %b %Y")
    project["sale_month"] = project["transaction_date"].dt.to_period("M").dt.to_timestamp()
    project["floor_band"] = project["floor"].map(_floor_band)
    project["source_row_number"] = project.index + 2
    project["edgeprop_record_id"] = project["source_row_number"].map(lambda value: f"edgeprop-row-{value}")
    project["published_unit"] = project["floor"].map(lambda floor: f"#{floor:02d}-XX")
    project["edge_idx"] = range(len(project))

    required_numeric = [
        "bedrooms",
        "area_sqft_rounded",
        "transacted_price_sgd",
        "unit_price_psf",
    ]
    if project[required_numeric].isna().any().any():
        raise XrefBuildError("Subject EdgeProp rows contain missing required numeric values")

    return project.reset_index(drop=True).set_index("edge_idx", drop=False)


def load_ura(path: Path) -> pd.DataFrame:
    source = pd.read_csv(path, low_memory=False)
    project = source[source["Project Name"].astype(str).str.strip().str.upper().eq(PROJECT)].copy()
    if project.empty:
        raise XrefBuildError(f"No {PROJECT} rows found in {path}")

    project["sale_month"] = pd.to_datetime(project["Sale Date"], format="%b-%y")
    project["transacted_price_sgd"] = _clean_number(project["Transacted Price ($)"]).round().astype("Int64")
    project["area_sqft"] = _clean_number(project["Area (SQFT)"])
    project["area_sqft_rounded"] = project["area_sqft"].round().astype("Int64")
    project["area_sqm"] = _clean_number(project["Area (SQM)"])
    project["unit_price_psf"] = _clean_number(project["Unit Price ($ PSF)"]).round().astype("Int64")
    project["floor_band"] = project["Floor Level"].astype(str).str.strip()
    floor_parts = project["floor_band"].str.extract(r"^(\d{2}) to (\d{2})$")
    if floor_parts.isna().any().any():
        examples = project.loc[floor_parts.isna().any(axis=1), "Floor Level"].head().tolist()
        raise XrefBuildError(f"Unexpected URA floor-band format: {examples}")
    project["floor_low"] = floor_parts[0].astype(int)
    project["floor_high"] = floor_parts[1].astype(int)
    project["type_of_sale"] = project["Type of Sale"].astype(str).str.strip()
    project["source_row_number"] = project.index + 2
    project["ura_record_id"] = project["source_row_number"].map(lambda value: f"ura-pmi-d27-row-{value}")
    project["ura_idx"] = range(len(project))

    required_numeric = ["transacted_price_sgd", "area_sqft", "area_sqm", "unit_price_psf"]
    if project[required_numeric].isna().any().any():
        raise XrefBuildError("Subject URA rows contain missing required numeric values")
    return project.reset_index(drop=True).set_index("ura_idx", drop=False)


def _bridge_signature_from_edge(row: pd.Series) -> tuple[Any, ...]:
    return (
        row["sale_month"].strftime("%Y-%m"),
        int(row["transacted_price_sgd"]),
        int(row["area_sqft_rounded"]),
        str(row["floor_band"]),
        str(row["Sale Type"]).strip(),
    )


def _bridge_signature_from_ura(row: pd.Series) -> tuple[Any, ...]:
    return (
        row["sale_month"].strftime("%Y-%m"),
        int(row["transacted_price_sgd"]),
        int(row["area_sqft_rounded"]),
        str(row["floor_band"]),
        str(row["type_of_sale"]),
    )


def reconcile_edgeprop_to_ura(
    edge: pd.DataFrame,
    ura: pd.DataFrame,
) -> tuple[dict[int, dict[str, Any]], tuple[int, ...]]:
    edge_groups: dict[tuple[Any, ...], list[int]] = {}
    ura_groups: dict[tuple[Any, ...], list[int]] = {}
    for edge_idx, row in edge.iterrows():
        edge_groups.setdefault(_bridge_signature_from_edge(row), []).append(int(edge_idx))
    for ura_idx, row in ura.iterrows():
        ura_groups.setdefault(_bridge_signature_from_ura(row), []).append(int(ura_idx))

    bridge: dict[int, dict[str, Any]] = {}
    used_ura: set[int] = set()
    failures: list[str] = []
    for signature, edge_indices in sorted(edge_groups.items(), key=lambda item: str(item[0])):
        ura_indices = sorted(ura_groups.get(signature, []))
        edge_indices = sorted(edge_indices, key=lambda idx: int(edge.at[idx, "source_row_number"]))
        if len(ura_indices) < len(edge_indices):
            failures.append(
                f"signature={signature!r}: {len(edge_indices)} EdgeProp vs {len(ura_indices)} URA"
            )
            continue
        group_id = _stable_id("ura-group", signature)
        identity_status = (
            "unique_public_signature"
            if len(ura_indices) == 1
            else "duplicate_public_signature_occurrence_preserved"
        )
        for occurrence, (edge_idx, ura_idx) in enumerate(zip(edge_indices, ura_indices), start=1):
            bridge[edge_idx] = {
                "ura_idx": ura_idx,
                "ura_record_group_id": group_id,
                "ura_candidate_count": len(ura_indices),
                "ura_record_identity_status": identity_status,
                "ura_group_occurrence": occurrence,
            }
            used_ura.add(ura_idx)
    if failures:
        raise XrefBuildError("EdgeProp-to-URA reconciliation failures: " + "; ".join(failures[:10]))
    if len(bridge) != len(edge):
        raise XrefBuildError(f"Only reconciled {len(bridge)} of {len(edge)} EdgeProp rows")
    return bridge, tuple(sorted(set(int(idx) for idx in ura.index) - used_ura))


def _structural_group_id(key: tuple[int, int, int, int]) -> str:
    block, floor, area, bedrooms = key
    return f"struct-{block}-{floor:02d}-{area}-{bedrooms}br"


def _solve_structural_group(
    group_id: str,
    unit_indices: list[int],
    edge_indices: list[int],
    unit_dates: dict[int, pd.Timestamp],
    edge_dates: dict[int, pd.Timestamp],
) -> GroupSolution:
    """Enumerate all max-cardinality/minimum-date-cost assignments.

    Group sizes in this project are small (at most a few same-layout stacks on a
    floor), which makes exhaustive enumeration transparent and avoids silently
    selecting one arbitrary Hungarian-solver optimum.
    """

    units = tuple(sorted(unit_indices))
    edges = tuple(sorted(edge_indices))
    if not edges:
        return GroupSolution(group_id, 0, 1, {}, {}, units)

    assignments: list[dict[int, int]] = []
    if len(units) >= len(edges):
        option_count = math.perm(len(units), len(edges))
        if option_count > 250_000:
            raise XrefBuildError(f"Structural group {group_id} has {option_count} assignment options")
        for chosen_units in itertools.combinations(units, len(edges)):
            for permuted_edges in itertools.permutations(edges):
                assignments.append(dict(zip(chosen_units, permuted_edges)))
    else:
        option_count = math.perm(len(edges), len(units))
        if option_count > 250_000:
            raise XrefBuildError(f"Structural group {group_id} has {option_count} assignment options")
        for chosen_edges in itertools.combinations(edges, len(units)):
            for permuted_edges in itertools.permutations(chosen_edges):
                assignments.append(dict(zip(units, permuted_edges)))

    def assignment_cost(assignment: dict[int, int]) -> int:
        return sum(
            abs(int((edge_dates[edge_idx] - unit_dates[unit_idx]).days) - 1)
            for unit_idx, edge_idx in assignment.items()
        )

    costs = [assignment_cost(assignment) for assignment in assignments]
    optimum_cost = min(costs)
    optima = [assignment for assignment, cost in zip(assignments, costs) if cost == optimum_cost]

    forced: dict[int, int] = {}
    candidates: dict[int, tuple[int, ...]] = {}
    unmatched: list[int] = []
    for unit_idx in units:
        states = {assignment.get(unit_idx) for assignment in optima}
        if len(states) == 1 and None not in states:
            forced[unit_idx] = int(next(iter(states)))
        elif states == {None}:
            unmatched.append(unit_idx)
        else:
            candidates[unit_idx] = tuple(sorted(int(state) for state in states if state is not None))

    return GroupSolution(
        group_id=group_id,
        optimum_cost=optimum_cost,
        optimal_assignment_count=len(optima),
        forced=forced,
        candidates=candidates,
        unmatched=tuple(unmatched),
    )


def match_chart_to_edgeprop(
    sold: pd.DataFrame,
    edge: pd.DataFrame,
) -> tuple[dict[int, int], dict[int, tuple[int, ...]], set[int], dict[int, GroupSolution]]:
    sold_groups: dict[tuple[int, int, int, int], list[int]] = {}
    edge_groups: dict[tuple[int, int, int, int], list[int]] = {}
    for chart_idx, row in sold.iterrows():
        key = (int(row["block"]), int(row["floor"]), int(row["area_sqft_reported"]), int(row["bedrooms"]))
        sold_groups.setdefault(key, []).append(int(chart_idx))
    for edge_idx, row in edge.iterrows():
        key = (int(row["block"]), int(row["floor"]), int(row["area_sqft_rounded"]), int(row["bedrooms"]))
        edge_groups.setdefault(key, []).append(int(edge_idx))

    missing_chart_groups = set(edge_groups) - set(sold_groups)
    if missing_chart_groups:
        raise XrefBuildError(
            "EdgeProp structural groups absent from sold chart: "
            + ", ".join(map(str, sorted(missing_chart_groups)))
        )

    unit_dates = {
        int(idx): pd.Timestamp(value)
        for idx, value in sold["reported_sold_date"].items()
    }
    edge_dates = {int(idx): pd.Timestamp(value) for idx, value in edge["transaction_date"].items()}
    forced: dict[int, int] = {}
    candidates: dict[int, tuple[int, ...]] = {}
    unmatched: set[int] = set()
    solutions: dict[int, GroupSolution] = {}

    for key, unit_indices in sold_groups.items():
        solution = _solve_structural_group(
            _structural_group_id(key),
            unit_indices,
            edge_groups.get(key, []),
            unit_dates,
            edge_dates,
        )
        forced.update(solution.forced)
        candidates.update(solution.candidates)
        unmatched.update(solution.unmatched)
        for unit_idx in unit_indices:
            solutions[unit_idx] = solution

    accounted = set(forced) | set(candidates) | unmatched
    if accounted != set(int(idx) for idx in sold.index):
        raise XrefBuildError("Chart-to-EdgeProp solver did not classify every sold chart row")
    return forced, candidates, unmatched, solutions


def residual_ura_matches(
    sold: pd.DataFrame,
    unmatched: set[int],
    ura: pd.DataFrame,
    residual_ura_indices: tuple[int, ...],
) -> tuple[dict[int, int], set[int]]:
    """Infer only mutually unique residual matches under the stated rule."""

    candidates_by_unit: dict[int, set[int]] = {}
    candidates_by_ura: dict[int, set[int]] = {}
    for chart_idx in sorted(unmatched):
        unit = sold.loc[chart_idx]
        unit_month = pd.Timestamp(unit["reported_sold_date"]).to_period("M").to_timestamp()
        for ura_idx in residual_ura_indices:
            transaction = ura.loc[ura_idx]
            if int(unit["area_sqft_reported"]) != int(transaction["area_sqft_rounded"]):
                continue
            if not int(transaction["floor_low"]) <= int(unit["floor"]) <= int(transaction["floor_high"]):
                continue
            if _month_distance(unit_month, transaction["sale_month"]) > 1:
                continue
            candidates_by_unit.setdefault(chart_idx, set()).add(ura_idx)
            candidates_by_ura.setdefault(ura_idx, set()).add(chart_idx)

    inferred: dict[int, int] = {}
    progress = True
    while progress:
        progress = False
        for chart_idx, ura_candidates in sorted(candidates_by_unit.items()):
            remaining_ura = ura_candidates - set(inferred.values())
            if chart_idx in inferred or len(remaining_ura) != 1:
                continue
            ura_idx = next(iter(remaining_ura))
            remaining_units = candidates_by_ura.get(ura_idx, set()) - set(inferred)
            if remaining_units == {chart_idx}:
                inferred[chart_idx] = ura_idx
                progress = True

    pending = set(unmatched) - set(inferred)
    return inferred, pending


def _ura_fields(
    ura_row: pd.Series,
    bridge_meta: dict[str, Any] | None,
    *,
    inferred: bool = False,
) -> dict[str, Any]:
    if bridge_meta is None:
        signature = _bridge_signature_from_ura(ura_row)
        record_group_id = _stable_id("ura-residual", signature)
        identity_status = "residual_unique_public_signature" if inferred else ""
        candidate_count: Any = 1 if inferred else ""
    else:
        record_group_id = bridge_meta["ura_record_group_id"]
        identity_status = bridge_meta["ura_record_identity_status"]
        candidate_count = bridge_meta["ura_candidate_count"]
    return {
        "ura_record_group_id": record_group_id,
        "ura_record_id": ura_row["ura_record_id"],
        "ura_record_identity_status": identity_status,
        "ura_candidate_count": candidate_count,
        "ura_sale_month": ura_row["sale_month"].strftime("%Y-%m"),
        "ura_floor_band": ura_row["floor_band"],
        "ura_area_sqm": float(ura_row["area_sqm"]),
        "ura_area_sqft": float(ura_row["area_sqft"]),
        "ura_transacted_price_sgd": int(ura_row["transacted_price_sgd"]),
        "ura_unit_price_psf": int(ura_row["unit_price_psf"]),
        "ura_type_of_sale": ura_row["type_of_sale"],
        "ura_source_url": URA_SOURCE_URL,
    }


def _edge_fields(edge_row: pd.Series) -> dict[str, Any]:
    return {
        "edgeprop_transaction_date": edge_row["transaction_date"].date().isoformat(),
        "edgeprop_address": edge_row["Address"],
        "edgeprop_published_unit": edge_row["published_unit"],
        "edgeprop_record_id": edge_row["edgeprop_record_id"],
        "edgeprop_source_url": edge_row["source_url"],
    }


def _blank_primary() -> dict[str, Any]:
    return {column: "" for column in PRIMARY_COLUMNS}


def build_tables(
    chart: pd.DataFrame,
    edge: pd.DataFrame,
    ura: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    sold = chart[chart["reported_status"].eq("sold")].copy()
    bridge, residual_ura = reconcile_edgeprop_to_ura(edge, ura)
    forced, ambiguous, unmatched, solutions = match_chart_to_edgeprop(sold, edge)
    residual_inferred, pending = residual_ura_matches(sold, unmatched, ura, residual_ura)

    used_residual = set(residual_inferred.values())
    if used_residual != set(residual_ura):
        unused = sorted(set(residual_ura) - used_residual)
        raise XrefBuildError(f"Not every residual URA row was inferred: unused indices {unused}")

    primary_records: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}

    for chart_idx, unit in sold.iterrows():
        chart_idx = int(chart_idx)
        solution = solutions[chart_idx]
        xref_id = f"CCR-{int(unit['block'])}-{int(unit['floor']):02d}-{int(unit['stack']):02d}"
        record = _blank_primary()
        record.update(
            {
                "xref_id": xref_id,
                "project_name": PROJECT,
                "block_number": int(unit["block"]),
                "address": f"{int(unit['block'])} CANBERRA CRESCENT",
                "unit_number": unit["unit_number"],
                "floor_number": int(unit["floor"]),
                "stack_number": f"{int(unit['stack']):02d}",
                "bedrooms": int(unit["bedrooms"]),
                "area_sqft_reported": int(unit["area_sqft_reported"]),
                "reported_sold_date": unit["reported_sold_date"],
                "unit_number_status": "agent_reported_exact_not_official",
                "unit_source_status": "agent_reported_sold",
                "unit_source_as_of": unit["unit_source_as_of"],
                "unit_source_url": unit["unit_source_url"],
                "match_group_id": solution.group_id,
                "optimal_assignment_count": solution.optimal_assignment_count,
            }
        )

        if chart_idx in forced:
            edge_idx = forced[chart_idx]
            edge_row = edge.loc[edge_idx]
            bridge_meta = bridge[edge_idx]
            ura_row = ura.loc[bridge_meta["ura_idx"]]
            delta = int((edge_row["transaction_date"] - pd.Timestamp(unit["reported_sold_date"])).days)
            if delta in (0, 1):
                match_status = "corroborated_high"
                confidence = "high"
                note = "Forced in every global optimum; EdgeProp date is the same day or one day later."
            elif abs(delta) <= 5:
                match_status = "corroborated_medium"
                confidence = "medium"
                note = "Forced in every global optimum; source dates differ by no more than five days."
            else:
                match_status = "date_outlier_review"
                confidence = "review"
                note = "Forced structurally in every global optimum, but the source-date gap needs review."
            record.update(_edge_fields(edge_row))
            record.update(_ura_fields(ura_row, bridge_meta))
            record.update(
                {
                    "match_status": match_status,
                    "confidence": confidence,
                    "transaction_candidate_count": 1,
                    "edgeprop_date_delta_days": delta,
                    "ura_match_status": "reconciled_via_edgeprop_public_signature",
                    "match_method": "all_optima_forced_structural+edgeprop_ura_public_signature",
                    "match_note": note,
                }
            )
        elif chart_idx in ambiguous:
            edge_indices = ambiguous[chart_idx]
            candidate_edges = edge.loc[list(edge_indices)]
            candidate_prices = [int(edge.at[idx, "transacted_price_sgd"]) for idx in edge_indices]
            candidate_dates = [edge.at[idx, "transaction_date"].date().isoformat() for idx in edge_indices]
            record.update(
                {
                    "match_status": "ambiguous_unit_transaction",
                    "confidence": "ambiguous",
                    "transaction_candidate_count": len(edge_indices),
                    "candidate_transaction_date_min": min(candidate_dates),
                    "candidate_transaction_date_max": max(candidate_dates),
                    "candidate_price_min_sgd": min(candidate_prices),
                    "candidate_price_max_sgd": max(candidate_prices),
                    "ura_match_status": "candidate_set_only_no_unit_assignment",
                    "match_method": "all_optima_candidate_set",
                    "match_note": (
                        "Multiple unit-to-transaction assignments are equally optimal; individual "
                        "EdgeProp/URA date and price fields are intentionally blank."
                    ),
                }
            )
            for rank, edge_idx in enumerate(
                sorted(edge_indices, key=lambda idx: (edge.at[idx, "transaction_date"], edge.at[idx, "edgeprop_record_id"])),
                start=1,
            ):
                edge_row = edge.loc[edge_idx]
                bridge_meta = bridge[edge_idx]
                ura_row = ura.loc[bridge_meta["ura_idx"]]
                delta = int((edge_row["transaction_date"] - pd.Timestamp(unit["reported_sold_date"])).days)
                candidate = {
                    "xref_id": xref_id,
                    "project_name": PROJECT,
                    "block_number": int(unit["block"]),
                    "unit_number": unit["unit_number"],
                    "floor_number": int(unit["floor"]),
                    "stack_number": f"{int(unit['stack']):02d}",
                    "area_sqft_reported": int(unit["area_sqft_reported"]),
                    "bedrooms": int(unit["bedrooms"]),
                    "reported_sold_date": unit["reported_sold_date"],
                    "match_group_id": solution.group_id,
                    "optimal_assignment_count": solution.optimal_assignment_count,
                    "candidate_rank": rank,
                    "candidate_present_in_optimal_solution": True,
                    "edgeprop_date_delta_days": delta,
                }
                candidate.update(_edge_fields(edge_row))
                candidate.update(_ura_fields(ura_row, bridge_meta))
                candidate_records.append(candidate)
        elif chart_idx in residual_inferred:
            ura_idx = residual_inferred[chart_idx]
            ura_row = ura.loc[ura_idx]
            record.update(_ura_fields(ura_row, None, inferred=True))
            record.update(
                {
                    "match_status": "ura_residual_inferred",
                    "confidence": "inferred",
                    "transaction_candidate_count": 1,
                    "ura_match_status": "residual_ura_inferred_no_block_or_unit",
                    "match_method": "residual_area_floor_band_same_or_adjacent_month",
                    "match_note": (
                        "Unique residual URA candidate by rounded area, floor band, and "
                        "same/adjacent month; URA does not corroborate block or exact unit."
                    ),
                }
            )
        elif chart_idx in pending:
            record.update(
                {
                    "match_status": "unit_source_only_pending_ura",
                    "confidence": "pending",
                    "transaction_candidate_count": 0,
                    "ura_match_status": "not_in_local_edgeprop_or_ura_snapshot",
                    "match_method": "unit_source_only",
                    "match_note": "No transaction candidate in the repository snapshots used for this run.",
                }
            )
        else:
            raise XrefBuildError(f"Sold chart row {chart_idx} has no output classification")

        status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
        primary_records.append(record)

    primary = pd.DataFrame.from_records(primary_records, columns=PRIMARY_COLUMNS)
    primary["_sort_date"] = pd.to_datetime(primary["reported_sold_date"])
    primary = primary.sort_values(
        ["_sort_date", "block_number", "floor_number", "stack_number"],
        ascending=[False, True, True, True],
        kind="stable",
    ).drop(columns="_sort_date").reset_index(drop=True)

    candidates_frame = pd.DataFrame.from_records(candidate_records, columns=CANDIDATE_COLUMNS)
    if not candidates_frame.empty:
        candidates_frame = candidates_frame.sort_values(
            ["xref_id", "candidate_rank"], kind="stable"
        ).reset_index(drop=True)

    diagnostics = {
        "forced_assignment_count": len(forced),
        "ambiguous_unit_count": len(ambiguous),
        "unmatched_after_edgeprop_count": len(unmatched),
        "residual_ura_inferred_count": len(residual_inferred),
        "pending_count": len(pending),
        "candidate_row_count": len(candidates_frame),
        **{f"status_{key}": value for key, value in sorted(status_counts.items())},
    }
    return primary, candidates_frame, diagnostics


def _jsonable_counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts().sort_index().items()}


def write_outputs(
    output_dir: Path,
    primary: pd.DataFrame,
    candidates: pd.DataFrame,
    *,
    chart_meta: dict[str, Any],
    diagnostics: dict[str, int],
    unit_html: Path,
    edgeprop_csv: Path,
    ura_csv: Path,
    edge_count: int,
    ura_count: int,
    generated_at: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    primary_path = output_dir / "canberra_crescent_unit_transactions.csv"
    candidate_path = output_dir / "canberra_crescent_ambiguous_candidates.csv"
    provenance_path = output_dir / "provenance.json"

    primary.to_csv(primary_path, index=False, lineterminator="\n")
    candidates.to_csv(candidate_path, index=False, lineterminator="\n")

    provenance: dict[str, Any] = {
        "schema_version": "canberra-unit-transaction-xref.v1",
        "dataset_status": "internal_research_noncanonical",
        "generated_at_utc": generated_at,
        "project": PROJECT,
        "notice": (
            "Exact unit numbers and reported sold dates are agent-reported, not official URA fields. "
            "Do not use this dataset as legal proof of sale or ownership."
        ),
        "sources": {
            "unit_chart": {
                "role": "agent_reported_exact_unit_and_status_date",
                "source_url": UNIT_SOURCE_URL,
                "local_capture": str(unit_html),
                "source_page_as_of": chart_meta["source_as_of"],
                "sha256": chart_meta["captured_sha256"],
                "rights_review": "not_reviewed_do_not_publish_source_html",
            },
            "edgeprop_snapshot": {
                "role": "masked_floor_transaction_date_and_public_attributes",
                "local_file": str(edgeprop_csv),
                "sha256": _sha256(edgeprop_csv),
                "subject_row_count": edge_count,
            },
            "ura_pmi_snapshot": {
                "role": "official_public_month_floor_band_price_area_attributes",
                "source_url": URA_SOURCE_URL,
                "local_file": str(ura_csv),
                "sha256": _sha256(ura_csv),
                "subject_row_count": ura_count,
                "unit_number_available": False,
            },
        },
        "source_inventory": {
            "unit_chart_units": chart_meta["unit_count"],
            "unit_chart_reported_sold": chart_meta["sold_count"],
            "unit_chart_available_excluded": chart_meta["available_count"],
            "edgeprop_subject_transactions": edge_count,
            "ura_subject_transactions": ura_count,
        },
        "matching_policy": {
            "chart_to_edgeprop_structure": ["block", "floor", "rounded_area_sqft", "bedrooms"],
            "objective": (
                "maximum cardinality, then minimum sum(abs((edgeprop_date - "
                "reported_sold_date) - 1 day))"
            ),
            "acceptance": "pair must be identical across every globally optimal group assignment",
            "edgeprop_to_ura_signature": [
                "sale_month",
                "transacted_price_sgd",
                "rounded_area_sqft",
                "floor_band",
                "type_of_sale",
            ],
            "duplicate_policy": "preserve raw occurrence multiplicity; do not deduplicate",
            "residual_inference": "rounded area + containing floor band + same/adjacent month",
            "ambiguous_policy": (
                "leave individual EdgeProp/URA date, price, and record fields blank in primary; "
                "publish normalized candidate rows separately"
            ),
        },
        "diagnostics": diagnostics,
        "primary_status_counts": _jsonable_counts(primary["match_status"]),
        "outputs": {
            "primary": {
                "file": primary_path.name,
                "row_count": len(primary),
                "sha256": _sha256(primary_path),
                "sort": "reported_sold_date descending, then block/floor/stack ascending",
            },
            "ambiguous_candidates": {
                "file": candidate_path.name,
                "row_count": len(candidates),
                "unit_count": int(candidates["xref_id"].nunique()) if not candidates.empty else 0,
                "sha256": _sha256(candidate_path),
            },
        },
        "caveats": [
            "Marketing reported sold date, EdgeProp transaction date, and URA sale month are distinct fields.",
            "URA PMI public search does not expose exact unit number in this snapshot.",
            "Residual URA matches do not independently prove block, stack, or exact unit.",
            "The two pending rows may reflect source timing beyond the local transaction snapshots.",
        ],
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return provenance


def _parse_generated_at(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--generated-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--generated-at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-html", type=Path, required=True, help="Captured unit-chart HTML")
    parser.add_argument(
        "--edgeprop-csv",
        type=Path,
        default=Path("data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv"),
    )
    parser.add_argument(
        "--ura-csv", type=Path, default=Path("data/raw/ura/pmi_d27_2021-2026.csv")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--generated-at",
        type=_parse_generated_at,
        required=True,
        help="Explicit ISO-8601 provenance timestamp for deterministic output",
    )
    parser.add_argument("--expected-as-of", default="2026-08-13")
    parser.add_argument("--expected-sold", type=int, default=342)
    parser.add_argument("--expected-edgeprop", type=int, default=336)
    parser.add_argument("--expected-ura", type=int, default=340)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chart, chart_meta = parse_unit_chart(args.unit_html)
    edge = load_edgeprop(args.edgeprop_csv)
    ura = load_ura(args.ura_csv)

    observed = {
        "source as-of": (chart_meta["source_as_of"], args.expected_as_of),
        "reported sold": (chart_meta["sold_count"], args.expected_sold),
        "EdgeProp subject rows": (len(edge), args.expected_edgeprop),
        "URA subject rows": (len(ura), args.expected_ura),
    }
    failures = [f"{name}: expected {expected}, found {actual}" for name, (actual, expected) in observed.items() if actual != expected]
    if failures:
        raise XrefBuildError("Capture/input expectations failed: " + "; ".join(failures))

    primary, candidates, diagnostics = build_tables(chart, edge, ura)
    expected_diagnostics = {
        "forced_assignment_count": 316,
        "ambiguous_unit_count": 20,
        "unmatched_after_edgeprop_count": 6,
        "residual_ura_inferred_count": 4,
        "pending_count": 2,
        "status_corroborated_high": 279,
        "status_corroborated_medium": 35,
        "status_date_outlier_review": 2,
    }
    diagnostic_failures = [
        f"{name}: expected {expected}, found {diagnostics.get(name)}"
        for name, expected in expected_diagnostics.items()
        if diagnostics.get(name) != expected
    ]
    if diagnostic_failures:
        raise XrefBuildError("Matching expectations failed: " + "; ".join(diagnostic_failures))
    if len(primary) != args.expected_sold:
        raise XrefBuildError(f"Expected {args.expected_sold} primary rows, found {len(primary)}")

    provenance = write_outputs(
        args.output_dir,
        primary,
        candidates,
        chart_meta=chart_meta,
        diagnostics=diagnostics,
        unit_html=args.unit_html,
        edgeprop_csv=args.edgeprop_csv,
        ura_csv=args.ura_csv,
        edge_count=len(edge),
        ura_count=len(ura),
        generated_at=args.generated_at,
    )
    print(json.dumps({"output_dir": str(args.output_dir), **provenance["outputs"], "diagnostics": diagnostics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
