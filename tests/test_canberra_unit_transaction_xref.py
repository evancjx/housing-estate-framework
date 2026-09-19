from __future__ import annotations

import pandas as pd

from models.build_canberra_unit_transaction_xref import (
    _TableParser,
    _floor_band,
    _month_distance,
    _parse_chart_cell,
    _solve_structural_group,
    build_tables,
    reconcile_edgeprop_to_ura,
    residual_ura_matches,
)


def test_stdlib_table_parser_extracts_cells_without_optional_html_packages() -> None:
    parser = _TableParser()
    parser.feed(
        "<html><table><thead><tr><th></th><th>#01</th></tr></thead>"
        "<tbody><tr><th>12</th><td>570 sqft<br>2 BR<br><strong>SOLD</strong>"
        "<br><strong>01 Aug 2025</strong></td></tr></tbody></table></html>"
    )
    assert parser.tables == [[["", "#01"], ["12", "570 sqft 2 BR SOLD 01 Aug 2025"]]]


def test_parse_chart_cell_keeps_marketing_status_date_separate() -> None:
    assert _parse_chart_cell("1,216 sqft  4 BR  SOLD  07 Aug 2026") == (
        1216,
        4,
        "sold",
        "2026-08-07",
    )
    assert _parse_chart_cell("990 sqft  3 BR") == (990, 3, "available", "")


def test_structural_solver_accepts_only_pairs_forced_across_every_optimum() -> None:
    units = {0: pd.Timestamp("2025-08-01"), 1: pd.Timestamp("2025-08-10")}
    edges = {10: pd.Timestamp("2025-08-02"), 11: pd.Timestamp("2025-08-11")}
    unique = _solve_structural_group("unique", [0, 1], [10, 11], units, edges)
    assert unique.forced == {0: 10, 1: 11}
    assert unique.candidates == {}
    assert unique.optimal_assignment_count == 1

    tied_units = {0: pd.Timestamp("2025-08-01"), 1: pd.Timestamp("2025-08-01")}
    tied_edges = {10: pd.Timestamp("2025-08-02"), 11: pd.Timestamp("2025-08-02")}
    tied = _solve_structural_group("tied", [0, 1], [10, 11], tied_units, tied_edges)
    assert tied.forced == {}
    assert tied.candidates == {0: (10, 11), 1: (10, 11)}
    assert tied.optimal_assignment_count == 2

    absent = _solve_structural_group("absent", [0, 1], [], tied_units, {})
    assert absent.unmatched == (0, 1)


def _edge_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["edge_idx"] = range(len(frame))
    return frame.set_index("edge_idx", drop=False)


def _ura_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["ura_idx"] = range(len(frame))
    return frame.set_index("ura_idx", drop=False)


def test_edgeprop_ura_bridge_preserves_duplicate_occurrence_multiplicity() -> None:
    edge = _edge_frame(
        [
            {
                "sale_month": pd.Timestamp("2025-08-01"),
                "transacted_price_sgd": 1_500_000,
                "area_sqft_rounded": 990,
                "floor_band": "01 to 05",
                "Sale Type": "New Sale",
                "source_row_number": row_number,
            }
            for row_number in (20, 21)
        ]
    )
    ura = _ura_frame(
        [
            {
                "sale_month": pd.Timestamp("2025-08-01"),
                "transacted_price_sgd": 1_500_000,
                "area_sqft_rounded": 990,
                "floor_band": "01 to 05",
                "type_of_sale": "New Sale",
            }
            for _ in range(3)
        ]
    )

    bridge, residual = reconcile_edgeprop_to_ura(edge, ura)

    assert len(bridge) == 2
    assert residual == (2,)
    assert {metadata["ura_candidate_count"] for metadata in bridge.values()} == {3}
    assert {metadata["ura_record_identity_status"] for metadata in bridge.values()} == {
        "duplicate_public_signature_occurrence_preserved"
    }
    assert len({metadata["ura_idx"] for metadata in bridge.values()}) == 2


def test_residual_inference_requires_area_floor_band_and_nearby_month() -> None:
    sold = pd.DataFrame(
        [
            {"unit_number": "#03-29", "floor": 3, "area_sqft_reported": 667, "reported_sold_date": "2025-08-22"},
            {"unit_number": "#06-24", "floor": 6, "area_sqft_reported": 797, "reported_sold_date": "2025-10-13"},
            {"unit_number": "#09-07", "floor": 9, "area_sqft_reported": 990, "reported_sold_date": "2026-05-02"},
            {"unit_number": "#04-22", "floor": 4, "area_sqft_reported": 1216, "reported_sold_date": "2026-07-11"},
            {"unit_number": "#08-30", "floor": 8, "area_sqft_reported": 1216, "reported_sold_date": "2026-07-25"},
            {"unit_number": "#09-30", "floor": 9, "area_sqft_reported": 1216, "reported_sold_date": "2026-08-07"},
        ]
    )
    ura = _ura_frame(
        [
            {"area_sqft_rounded": 667, "floor_low": 1, "floor_high": 5, "sale_month": pd.Timestamp("2025-08-01")},
            {"area_sqft_rounded": 797, "floor_low": 6, "floor_high": 10, "sale_month": pd.Timestamp("2025-10-01")},
            {"area_sqft_rounded": 990, "floor_low": 6, "floor_high": 10, "sale_month": pd.Timestamp("2026-04-01")},
            {"area_sqft_rounded": 1216, "floor_low": 1, "floor_high": 5, "sale_month": pd.Timestamp("2026-07-01")},
        ]
    )

    inferred, pending = residual_ura_matches(sold, set(sold.index), ura, tuple(ura.index))

    assert {sold.at[chart_idx, "unit_number"]: ura_idx for chart_idx, ura_idx in inferred.items()} == {
        "#03-29": 0,
        "#06-24": 1,
        "#09-07": 2,
        "#04-22": 3,
    }
    assert {sold.at[chart_idx, "unit_number"] for chart_idx in pending} == {"#08-30", "#09-30"}
    assert _floor_band(12) == "11 to 15"
    assert _month_distance(pd.Timestamp("2026-05-02"), pd.Timestamp("2026-04-01")) == 1


def test_ambiguous_primary_rows_do_not_receive_arbitrary_transaction_values() -> None:
    chart = pd.DataFrame(
        [
            {
                "project_name": "CANBERRA CRESCENT RESIDENCES",
                "block": 51,
                "floor": 4,
                "stack": stack,
                "unit_number": f"#04-{stack:02d}",
                "area_sqft_reported": 990,
                "bedrooms": 3,
                "reported_status": "sold",
                "reported_sold_date": "2025-08-01",
                "unit_source_as_of": "2026-08-13",
                "unit_source_url": "https://example.invalid/unit-chart",
            }
            for stack in (3, 6)
        ]
    )
    edge_rows = []
    ura_rows = []
    for idx, price in enumerate((1_500_000, 1_510_000)):
        edge_rows.append(
            {
                "block": 51,
                "floor": 4,
                "area_sqft_rounded": 990,
                "bedrooms": 3,
                "transaction_date": pd.Timestamp("2025-08-02"),
                "sale_month": pd.Timestamp("2025-08-01"),
                "transacted_price_sgd": price,
                "unit_price_psf": round(price / 990),
                "floor_band": "01 to 05",
                "Sale Type": "New Sale",
                "source_row_number": idx + 2,
                "edgeprop_record_id": f"edge-{idx}",
                "Address": "51 CANBERRA CRESCENT #04-XX",
                "published_unit": "#04-XX",
                "source_url": "https://example.invalid/edge",
            }
        )
        ura_rows.append(
            {
                "sale_month": pd.Timestamp("2025-08-01"),
                "transacted_price_sgd": price,
                "area_sqft_rounded": 990,
                "area_sqft": 990.29,
                "area_sqm": 92.0,
                "unit_price_psf": round(price / 990),
                "floor_band": "01 to 05",
                "floor_low": 1,
                "floor_high": 5,
                "type_of_sale": "New Sale",
                "source_row_number": idx + 2,
                "ura_record_id": f"ura-{idx}",
            }
        )

    primary, candidates, diagnostics = build_tables(
        chart,
        _edge_frame(edge_rows),
        _ura_frame(ura_rows),
    )

    assert set(primary["match_status"]) == {"ambiguous_unit_transaction"}
    assert (primary["edgeprop_transaction_date"] == "").all()
    assert (primary["ura_transacted_price_sgd"] == "").all()
    assert (primary["ura_record_id"] == "").all()
    assert primary["candidate_price_min_sgd"].eq(1_500_000).all()
    assert primary["candidate_price_max_sgd"].eq(1_510_000).all()
    assert len(candidates) == 4
    assert candidates.groupby("xref_id").size().eq(2).all()
    assert diagnostics["ambiguous_unit_count"] == 2
