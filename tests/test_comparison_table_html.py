"""Contracts for the generated estate-context explorer."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "comparison_table.html"
SCRIPT = ROOT / "site" / "assets" / "estate-comparison.js"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _embedded_rows() -> list[dict]:
    match = re.search(
        r'<script id="estate-comparison-data" type="application/json">(.*?)</script>',
        _page(),
        flags=re.DOTALL,
    )
    assert match, "generated estate data script is missing"
    return json.loads(match.group(1))


def test_estate_explorer_uses_the_shared_site_experience_and_progressive_disclosure() -> None:
    page = _page()

    assert page.count("assets/research-shell.css") == 1
    assert page.count("assets/research-shell.js") == 1
    assert page.count("assets/estate-explorer.css") == 1
    assert page.count("assets/estate-comparison.js") == 1
    assert '<main id="research-content">' in page
    assert 'id="estate-search" type="search"' in page
    assert 'role="status" aria-live="polite"' in page
    assert 'data-view="overview" aria-pressed="true"' in page
    assert 'data-view="all" aria-pressed="false"' in page
    assert 'id="reset-view" type="button"' in page
    assert 'class="tbl-wrap" role="region"' in page
    assert '<caption>' in page
    assert "without forcing a winner" in page
    assert "never blended or ranked against each other" in page
    assert "persona-and-horizon profile" in page
    assert "differences inside ±0.3 are not a defensible rank" in page
    assert "onclick=" not in page
    assert "oninput=" not in page
    assert "__ESTATE_" not in page


def test_generated_rows_preserve_every_estate_and_framework_evidence_state() -> None:
    rows = _embedded_rows()
    master = pd.read_csv(ROOT / "data" / "outputs" / "master_output.csv")

    assert len(rows) == len(master) == 35
    assert {row["estate"] for row in rows} == set(master["estate"])
    assert len({row["estate"] for row in rows}) == len(rows)

    canberra = next(row for row in rows if row["estate"] == "CANBERRA")
    assert canberra["hdb_status"] == "available"
    assert canberra["hdb_basis"] == "proxy_from:SEMBAWANG"
    assert canberra["pvt_status"] == "available"
    assert canberra["pvt_basis"] == "proxy_from:SEMBAWANG"

    statuses = {
        row[status]
        for row in rows
        for status in ("hdb_status", "pvt_status")
    }
    assert {"available", "no_data", "not_covered", "not_applicable"} <= statuses

    central = next(row for row in rows if row["estate"] == "CENTRAL AREA")
    assert central["arch"] == "X"
    assert central["flag"] == "nr"


def test_value_adjustments_use_their_own_tenure_segment_bases() -> None:
    rows = {row["estate"]: row for row in _embedded_rows()}
    master = pd.read_csv(ROOT / "data" / "outputs" / "master_output.csv")

    for _, source in master.iterrows():
        row = rows[source["estate"]]
        if (
            pd.notna(source["value_hdb_score"])
            and source["value_hdb_n"] >= 100
        ):
            expected_hdb = round(
                source["value_hdb_score"] / source["provision_score"], 4
            )
            assert row["hdb_m"] == pytest.approx(expected_hdb)
        else:
            assert row["hdb_m"] is None
        if (
            pd.notna(source["value_private_score"])
            and source["value_private_n"] >= 100
        ):
            expected_private = round(
                source["value_private_score"] / source["provision_private"], 4
            )
            assert row["pvt_m"] == pytest.approx(expected_private)
        else:
            assert row["pvt_m"] is None


def test_gap_labels_and_life_path_deltas_come_from_canonical_outputs() -> None:
    rows = {row["estate"]: row for row in _embedded_rows()}
    master = pd.read_csv(ROOT / "data" / "outputs" / "master_output.csv")
    life_paths = pd.read_csv(ROOT / "data" / "outputs" / "life_paths.csv")

    for _, source in master.iterrows():
        row = rows[source["estate"]]
        for short, persona in (
            ("yf", "yf"),
            ("sp", "sp"),
            ("ret", "ret"),
            ("ls", "ls"),
        ):
            expected = source[f"gap_{persona}_T0_label"]
            assert row[f"gap_{short}_label"] == expected

        estate_paths = life_paths[life_paths["estate"] == source["estate"]]
        if estate_paths["delta"].notna().any():
            assert row["best_delta"] == pytest.approx(
                estate_paths["delta"].max(), abs=0.011
            )
            assert row["worst_delta"] == pytest.approx(
                estate_paths["delta"].min(), abs=0.011
            )
        else:
            assert row["best_delta"] is None
            assert row["worst_delta"] is None


def test_browser_script_implements_accessible_sort_filter_url_and_x_gate() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'heading.removeAttribute("aria-sort")' in script
    assert 'button.type = "button"' in script
    assert 'button.setAttribute("aria-pressed"' in script
    assert "history.replaceState" in script
    assert "URLSearchParams" in script
    assert "escapeHTML" in script
    assert 'row.arch === "X"' in script
    assert "canonical dead band ±0.5" in script
    assert "PRICE_SIGNAL_HIGH = 1.10" in script
    assert "PRICE_SIGNAL_LOW = 0.90" in script


def test_generator_template_and_committed_artifact_remain_in_sync() -> None:
    from sg_estate.reporting.builders import _comparison_impl as builder

    generated_date = re.search(
        r'<time datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})">', _page()
    )
    assert generated_date
    rendered = builder.render_html(
        generated_on=date.fromisoformat(generated_date.group(1))
    )

    assert rendered == _page()
    assert builder._trusted_multiplier(1.2345, 99) is None
    assert builder._trusted_multiplier(1.2345, 100) == 1.2345
    assert builder._flags({}, None, None, 1.0) == ""
