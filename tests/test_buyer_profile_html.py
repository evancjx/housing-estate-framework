"""Contracts for the generated buyer-profile explorer."""

from __future__ import annotations

from datetime import date
from io import StringIO
import json
from pathlib import Path
import re

import pandas as pd
import pytest

import buyer_profile_model as profile_model
from sg_estate.reporting.builders import _buyer_profile_impl as builder


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "outputs" / "buyer_profile_output.csv"
DEFINITIONS = ROOT / "data" / "inputs" / "buyer_profiles.example.json"
PAGE = ROOT / "buyer_profile_table.html"
SCRIPT = ROOT / "site" / "assets" / "buyer-profile.js"


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


def test_buyer_explorer_uses_shared_shell_and_framework_safe_stance() -> None:
    page = _page()

    assert page.count("assets/research-shell.css") == 1
    assert page.count("assets/research-shell.js") == 1
    assert page.count("assets/estate-explorer.css") == 1
    assert page.count("assets/buyer-profile.css") == 1
    assert page.count("assets/buyer-profile.js") == 1
    assert '<main id="research-content">' in page
    assert "Hard constraints first" in page
    assert "Rank inside one tenure only" in page
    assert "never a universal estate league table" in page
    assert "experimental weighted diagnostic" in page
    assert "Below 100 transactions" in page
    assert "employment remains current/T0" in page
    assert 'class="tbl-wrap" role="region"' in page
    assert '<caption>' in page
    assert 'role="status" aria-live="polite"' in page
    assert 'data-view="overview" aria-pressed="true"' in page
    assert 'data-status="eligible" aria-pressed="true"' in page
    assert "onclick=" not in page
    assert "oninput=" not in page
    assert "__BUYER_PROFILE_" not in page


def test_load_rows_requires_the_complete_buyer_profile_contract(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    pd.DataFrame({"estate": ["ALPHA"]}).to_csv(path, index=False)

    try:
        builder.load_rows(path)
    except SystemExit as exc:
        assert "missing required columns" in str(exc)
        assert "profile_id" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_profile_definitions_must_exactly_cover_output_scenarios() -> None:
    rows = builder.load_rows(OUTPUT)
    definitions = builder.load_profile_definitions(DEFINITIONS)
    missing = dict(definitions)
    missing.pop(next(iter(missing)))
    with pytest.raises(SystemExit, match="missing definitions"):
        builder.validate_profile_coverage(rows, missing)

    extra = dict(definitions)
    extra["unused-scenario"] = {"profile_id": "unused-scenario"}
    with pytest.raises(SystemExit, match="unused definitions"):
        builder.validate_profile_coverage(rows, extra)


def test_committed_buyer_output_matches_current_canonical_inputs() -> None:
    payload = json.loads(DEFINITIONS.read_text(encoding="utf-8"))
    profiles = profile_model._profiles_from_payload(payload)
    master = profile_model._load_csv(
        str(ROOT / "data" / "outputs" / "master_output.csv"), "master"
    )
    life_paths = profile_model._load_csv(
        str(ROOT / "data" / "outputs" / "life_paths.csv"), "life_paths"
    )
    private_values = profile_model._load_csv(
        str(ROOT / "data" / "outputs" / "private_segment_value.csv"),
        "private-values",
    )
    rebuilt = profile_model.run_many(
        master,
        life_paths,
        profiles,
        private_values=private_values,
    )

    # Round-trip the in-memory result through CSV so inferred dtypes match the
    # committed publication artifact exactly.
    expected = pd.read_csv(StringIO(rebuilt.to_csv(index=False)), keep_default_na=False)
    actual = pd.read_csv(OUTPUT, keep_default_na=False)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_publication_rows_mask_x_filtered_and_low_sample_precision() -> None:
    rows = builder.load_rows(OUTPUT)

    assert len(rows) == 175
    assert len({(row["profile_id"], row["estate"], row["tenure"]) for row in rows}) == 175

    for row in rows:
        if not row["eligible"]:
            assert row["rank"] is None
            assert row["profile_score"] is None
        if row["archetype"] == "X":
            assert row["score_reporting"] == "not_residential"
            assert row["soft_weight_covered"] is None
            assert row["liveability_score"] is None
            assert row["value_score"] is None
            assert row["employment_score"] is None
            assert row["lease_score"] is None
            assert row["provision_score"] is None
            assert row["life_path_end_score"] is None
            assert row["liveability_band"] == "N/R"
            assert row["value_band"] == "N/R"

    thin = [
        row
        for row in rows
        if row["value_n"] is not None and 0 < row["value_n"] < builder.VALUE_TRUST_THRESHOLD
    ]
    assert thin
    assert all(row["value_reporting"] == "band_only" for row in thin)
    assert all(row["value_score"] is None for row in thin)
    assert all(row["profile_score"] is None for row in thin if row["eligible"])
    assert all(row["rank"] is None for row in thin if row["eligible"])

    universes = {(row["profile_id"], row["tenure"]) for row in rows}
    for profile_id, tenure in universes:
        ranked = sorted(
            row["rank"]
            for row in rows
            if row["profile_id"] == profile_id
            and row["tenure"] == tenure
            and row["rank"] is not None
        )
        assert ranked == list(range(1, len(ranked) + 1))


def test_profile_summary_explains_scenarios_without_cross_profile_winners() -> None:
    rows = builder.load_rows(OUTPUT)
    definitions = builder.load_profile_definitions(DEFINITIONS)
    summary = builder.profile_summary(rows, definitions)

    assert [item["profile_id"] for item in summary] == list(definitions)
    assert len(summary) == 5
    assert all(item["description"] for item in summary)
    assert all(item["hard_filters"] for item in summary)
    assert all(item["soft_weights"] for item in summary)
    assert all(item["tenures"] for item in summary)
    assert all("top_estate" not in item and "top_score" not in item for item in summary)
    landed = next(item for item in summary if item["profile_id"] == "landed-family-amenity-upside")
    assert landed["band_only_value"] >= 1
    assert landed["ranked"] < landed["eligible"]


def test_embedded_rows_and_committed_artifact_match_the_canonical_renderer() -> None:
    rows = builder.load_rows(OUTPUT)
    definitions = builder.load_profile_definitions(DEFINITIONS)
    embedded_rows = _embedded("buyer-profile-data")
    embedded_profiles = _embedded("buyer-profile-summary")

    assert embedded_rows == rows
    assert embedded_profiles == builder.profile_summary(rows, definitions)

    generated_date = re.search(
        r'<time datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})">', _page()
    )
    assert generated_date
    rendered = builder.render_html(
        rows,
        generated_on=date.fromisoformat(generated_date.group(1)),
        definitions=definitions,
    )
    assert rendered == _page()


def test_browser_script_implements_accessible_url_backed_interactions() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'scope="row"' in script
    assert 'aria-sort="${state.direction' in script
    assert 'button.setAttribute("aria-pressed"' in script
    assert "history.replaceState" in script
    assert "URLSearchParams" in script
    assert "popstate" in script
    assert "notResidential(row)" in script
    assert "band_only" in script
    assert "current / T0 access" in script
    assert "No matching tenure-segment evidence" in script
    assert "Private Provision" not in script or "private-weighted" in script
