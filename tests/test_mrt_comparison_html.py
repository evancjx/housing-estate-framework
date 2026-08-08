"""Contracts for the generated MRT and LRT context explorer."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re

import pandas as pd
import pytest

from sg_estate.domain.value import CFG as VALUE_CFG
from sg_estate.reporting.builders import _mrt_comparison_impl as builder


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "mrt_comparison_table.html"
SCRIPT = ROOT / "site" / "assets" / "mrt-comparison.js"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _embedded(script_id: str) -> object:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        _page(),
        flags=re.DOTALL,
    )
    assert match, f"generated data script {script_id!r} is missing"
    return json.loads(match.group(1))


def test_mrt_explorer_uses_shared_shell_and_framework_safe_stance() -> None:
    page = _page()

    assert page.count("assets/research-shell.css") == 1
    assert page.count("assets/research-shell.js") == 1
    assert page.count("assets/estate-explorer.css") == 1
    assert page.count("assets/mrt-comparison.css") == 1
    assert page.count("assets/mrt-comparison.js") == 1
    assert '<main id="research-content">' in page
    assert "without ranking the network" in page
    assert "Nearest centroid, not catchment" in page
    assert "Interchanges repeat once per service code" in page
    assert "not a live service feed" in page
    assert "Official sources and derived points" in page
    assert "Planned-overlay boundary" in page
    assert "Context is withheld" in page
    assert "differences inside ±0.3 are not a defensible rank" in page
    assert "HDB and private Value remain separate tenure universes" in page
    assert 'id="station-search" type="search"' in page
    assert 'role="status" aria-live="polite"' in page
    assert 'class="tbl-wrap" role="region"' in page
    assert "<caption>" in page
    assert 'data-view="overview" aria-pressed="true"' in page
    assert 'data-status="all" aria-pressed="true"' in page
    assert "onclick=" not in page
    assert "oninput=" not in page
    assert "__MRT_" not in page


def test_every_committed_station_code_is_published_once_with_line_summary() -> None:
    rows = _embedded("mrt-comparison-data")
    line_summary = _embedded("mrt-line-summary")
    source = pd.read_csv(ROOT / "data" / "inputs" / "mrt_layer.csv")

    assert len(rows) == len(source)
    assert {(row["station"], row["code"]) for row in rows} == {
        (str(row["name"]).strip(), str(row["stn_code"]).strip())
        for _, row in source.iterrows()
    }
    assert len({row["code"] for row in rows}) == len(rows)
    assert sum(item["records"] for item in line_summary) == len(rows)
    assert sum(item["open"] for item in line_summary) == int(
        (source["operational"] == 1).sum()
    )
    assert sum(item["future"] for item in line_summary) == int(
        (source["operational"] == 0).sum()
    )


def test_centroid_geometry_is_exact_and_distant_context_is_withheld() -> None:
    rows = {row["station"]: row for row in _embedded("mrt-comparison-data")}
    estates = pd.read_csv(ROOT / "data" / "inputs" / "estates.csv")
    source = pd.read_csv(ROOT / "data" / "inputs" / "mrt_layer.csv")
    station = source.loc[source["name"] == "Tampines"].iloc[0]
    expected = min(
        [
            (
            str(estate["estate"]),
            builder.haversine_m(
                float(station["lat"]),
                float(station["lon"]),
                float(estate["lat"]),
                float(estate["lon"]),
            ),
            )
            for _, estate in estates.iterrows()
        ],
        key=lambda item: item[1],
    )

    assert rows["Tampines"]["estate"] == expected[0]
    assert rows["Tampines"]["distance_m"] == round(expected[1])
    assert rows["Tampines"]["context_status"] == "available"

    tuas = rows["Tuas Link"]
    assert tuas["distance_m"] > 1400
    assert tuas["context_status"] == "out_of_range"
    for field in (
        "provision_band",
        "provision_score",
        "yf0",
        "ls15",
        "hdb_value_band",
        "private_value_band",
        "employment_band",
        "lease_band",
    ):
        assert tuas[field] is None

    assert builder.distance_band(600) == "le600"
    assert builder.distance_band(600.01) == "601-1000"
    assert builder.distance_band(1000) == "601-1000"
    assert builder.distance_band(1000.01) == "1001-1400"
    assert builder.distance_band(1400) == "1001-1400"
    assert builder.distance_band(1400.01) == "gt1400"


def test_whole_payload_reproduces_geometry_and_gates_every_context_field() -> None:
    rows = _embedded("mrt-comparison-data")
    source = pd.read_csv(ROOT / "data" / "inputs" / "mrt_layer.csv")
    estates = pd.read_csv(ROOT / "data" / "inputs" / "estates.csv")
    master = pd.read_csv(ROOT / "data" / "outputs" / "master_output.csv").set_index("estate")
    source_by_code = source.set_index("stn_code")
    model_fields = (
        "archetype",
        "provision_band",
        "provision_score",
        "yf0",
        "sp0",
        "ret0",
        "ls0",
        "ls5",
        "ls15",
        "hdb_value_band",
        "hdb_value_basis",
        "hdb_value_n",
        "private_value_band",
        "private_value_basis",
        "private_value_n",
        "employment_band",
        "lease_band",
        "lease_source",
    )

    for row in rows:
        station = source_by_code.loc[row["code"]]
        distances = [
            (
                str(estate["estate"]),
                builder.haversine_m(
                    float(station["lat"]),
                    float(station["lon"]),
                    float(estate["lat"]),
                    float(estate["lon"]),
                ),
            )
            for _, estate in estates.iterrows()
        ]
        nearest, distance = min(distances, key=lambda item: item[1])
        context = master.loc[nearest]
        archetype = str(context["archetype"]).strip()
        expected_status = (
            "not_residential"
            if archetype == "X"
            else "out_of_range"
            if distance > 1400
            else "available"
        )

        assert row["station"] == str(station["name"]).strip()
        assert row["line"] == str(station["line"]).strip()
        assert row["status"] == ("open" if station["operational"] == 1 else "future")
        assert row["network_status"] == station["network_status"]
        assert row["planned_opening"] == builder.controlled_text(station["planned_opening"])
        assert row["status_as_of"] == station["status_as_of"]
        assert row["network_status_source"] == station["network_status_source"]
        assert row["geometry_basis"] == station["geometry_basis"]
        assert row["geometry_source"] == station["geometry_source"]
        assert row["lat"] == round(float(station["lat"]), 6)
        assert row["lon"] == round(float(station["lon"]), 6)
        assert row["estate"] == nearest
        assert row["distance_m"] == round(distance)
        assert row["distance_band"] == builder.distance_band(distance)
        assert row["centroids_800m"] == sum(value <= 800 for _, value in distances)
        assert row["centroids_1400m"] == sum(value <= 1400 for _, value in distances)
        assert row["context_status"] == expected_status

        if expected_status != "available":
            assert all(row[field] is None for field in model_fields)
            assert row["measured_only"] is False
            assert row["hdb_value_status"] == expected_status
            assert row["private_value_status"] == expected_status
            assert row["employment_status"] == expected_status
            assert row["lease_status"] == expected_status
            continue

        assert row["archetype"] == archetype
        assert row["provision_band"] == builder.clean_band(context["provision_band"])
        assert row["provision_score"] == builder.clean_number(context["provision_score"], 2)
        assert row["yf0"] == builder.clean_band(context["yf_T0_band"])
        assert row["sp0"] == builder.clean_band(context["sp_T0_band"])
        assert row["ret0"] == builder.clean_band(context["ret_T0_band"])
        assert row["ls0"] == builder.clean_band(context["ls_T0_band"])
        assert row["ls5"] == builder.clean_band(context["ls_T5_band"])
        assert row["ls15"] == builder.clean_band(context["ls_T15_band"])
        assert row["hdb_value_band"] == builder.clean_band(context["value_hdb_band"])
        assert row["hdb_value_basis"] == builder.controlled_text(context["value_hdb_basis"])
        assert row["hdb_value_n"] == builder.clean_number(context["value_hdb_n"])
        assert row["hdb_value_status"] == builder.controlled_text(context["value_hdb_status"])
        assert row["private_value_band"] == builder.clean_band(context["value_private_band"])
        assert row["private_value_basis"] == builder.controlled_text(context["value_private_basis"])
        assert row["private_value_n"] == builder.clean_number(context["value_private_n"])
        assert row["private_value_status"] == builder.controlled_text(context["value_private_status"])
        assert row["employment_band"] == builder.clean_band(context["emp_band"])
        assert row["employment_status"] == builder.controlled_text(context["employment_status"])
        assert row["lease_band"] == builder.clean_band(context["lease_band"])
        assert row["lease_status"] == builder.controlled_text(context["lease_status"])
        assert row["lease_source"] == builder.controlled_text(context["lease_source"])


def test_non_residential_gate_and_value_provenance_remain_explicit() -> None:
    rows = {row["station"]: row for row in _embedded("mrt-comparison-data")}
    central = rows["Outram Park"]

    assert central["estate"] == "CENTRAL AREA"
    assert central["archetype"] is None
    assert central["context_status"] == "not_residential"
    assert central["provision_score"] is None
    assert central["hdb_value_band"] is None
    assert central["private_value_band"] is None
    assert central["employment_band"] is None
    assert central["lease_band"] is None

    canberra = rows["Canberra"]
    assert canberra["hdb_value_band"] == "B+"
    assert canberra["hdb_value_basis"] == "proxy_from:SEMBAWANG"
    assert canberra["hdb_value_status"] == "available"
    assert canberra["private_value_band"] == "A"
    assert canberra["private_value_basis"] == "proxy_from:SEMBAWANG"
    assert canberra["private_value_status"] == "available"

    statuses = {
        row[field]
        for row in rows.values()
        for field in ("hdb_value_status", "private_value_status")
    }
    assert {"available", "not_covered", "not_residential", "out_of_range"} <= statuses
    assert builder.controlled_text("no_data") == "no_data"
    assert builder.controlled_text("not_covered") == "not_covered"


def test_source_contract_rejects_missing_columns_and_duplicate_codes(tmp_path) -> None:
    estates = ROOT / "data" / "inputs" / "estates.csv"
    master = ROOT / "data" / "outputs" / "master_output.csv"
    missing = tmp_path / "missing.csv"
    pd.DataFrame({"name": ["A"]}).to_csv(missing, index=False)
    with pytest.raises(SystemExit, match="missing required columns"):
        builder.load_rows(missing, estates, master)

    source = pd.read_csv(ROOT / "data" / "inputs" / "mrt_layer.csv").head(2)
    source.loc[source.index[1], "stn_code"] = source.iloc[0]["stn_code"]
    duplicate = tmp_path / "duplicate.csv"
    source.to_csv(duplicate, index=False)
    with pytest.raises(SystemExit, match="duplicate station codes"):
        builder.load_rows(duplicate, estates, master)


def test_interchange_memberships_are_complete_and_explained() -> None:
    rows = _embedded("mrt-comparison-data")
    dhoby = [row for row in rows if row["station"] == "Dhoby Ghaut"]

    assert [(row["code"], row["line"]) for row in dhoby] == [
        ("CC1", "Circle Line"),
        ("NE6", "North East Line"),
        ("NS24", "North-South Line"),
    ]
    assert "Interchanges repeat once per service code" in _page()


def test_generator_template_and_committed_artifact_remain_in_sync() -> None:
    generated_date = re.search(
        r'<b>Generated:</b>\s*<time datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})">',
        _page(),
    )
    assert generated_date
    rendered = builder.render_html(
        generated_on=date.fromisoformat(generated_date.group(1))
    )
    assert rendered == _page()


def test_value_trust_threshold_is_single_sourced_from_the_domain_model() -> None:
    config = _embedded("mrt-comparison-config")

    assert builder.VALUE_TRUST_THRESHOLD == VALUE_CFG["trust_decimal_n"]
    assert config == {
        "value_trust_threshold": VALUE_CFG["trust_decimal_n"],
        "status_as_of": "2026-08-08",
        "planned_horizon": 2031,
    }


def test_browser_script_implements_accessible_url_backed_typed_interactions() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'scope="row"' in script
    assert 'aria-sort="${state.direction' in script
    assert 'button.setAttribute("aria-pressed"' in script
    assert "history.replaceState" in script
    assert "URLSearchParams" in script
    assert "popstate" in script
    assert "escapeHTML" in script
    assert "context_status !== \"available\"" in script
    assert "nearest centroid is beyond 1.4 km" in script
    assert "Interchanges repeat as separate code-line rows" in script
    assert "reviewed status source" in script
    assert "config.value_trust_threshold" in script
    assert "VALUE_TRUST_THRESHOLD = 100" not in script
