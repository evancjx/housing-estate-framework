"""Checks for the static GitHub Pages report bundle."""

from collections import Counter
from copy import deepcopy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil

import pandas as pd
import pytest

from sg_estate import source_receipts
from scripts import build_pages_site


ROOT = Path(__file__).parent.parent


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


class _LibraryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []
        self.primary_links = []
        self.history_links = []
        self._card = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "article" and "report-card" in classes:
            self._card = values
            self.cards.append(values)
        elif tag == "a" and "report-primary-link" in classes:
            self.primary_links.append((self._card, values))
        elif tag == "a" and "report-history-link" in classes:
            self.history_links.append((self._card, values))

    def handle_endtag(self, tag):
        if tag == "article":
            self._card = None


def test_pages_landing_library_represents_authored_and_generated_reports():
    parser = _LibraryParser()
    parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    primary_paths = []
    for card, link in parser.primary_links:
        assert card is not None
        assert link["href"] == card["data-report-path"]
        primary_paths.append(card["data-report-path"])
    history_paths = []
    for _, link in parser.history_links:
        assert link["href"] == link["data-report-path"]
        history_paths.append(link["data-report-path"])

    authored_catalog = build_pages_site.load_catalog()
    authored_paths = {report["path"] for report in authored_catalog["reports"]}
    analyses = build_pages_site.discover_property_analyses()
    generated_paths = {analysis.output_path for analysis in analyses}
    represented = Counter([*primary_paths, *history_paths])

    assert len(authored_paths) == 26
    assert len(generated_paths) == 28
    assert len(primary_paths) == 52
    assert len(history_paths) == 2
    assert represented == Counter(authored_paths | generated_paths)
    assert set(represented.values()) == {1}
    assert all(ROOT.joinpath(*Path(path).parts).is_file() for path in authored_paths)
    assert all(not (ROOT / path).exists() for path in generated_paths)


def test_report_catalog_covers_every_root_report():
    catalog = json.loads(
        (ROOT / "site" / "reports.json").read_text(encoding="utf-8")
    )
    paths = [report["path"] for report in catalog["reports"]]

    assert catalog["schema_version"] == 2
    assert len(paths) == len(set(paths))
    assert set(paths) == {
        path.name for path in ROOT.glob("*.html") if path.name != "index.html"
    }
    assert all(report["summary"].strip() for report in catalog["reports"])
    assert all(report["tags"] for report in catalog["reports"])


def test_pages_builder_packages_reports_catalog_and_assets(tmp_path):
    assets = tmp_path / "source-assets"
    assets.mkdir()
    (assets / "research-shell.css").write_text("body {}", encoding="utf-8")
    (assets / "research-shell.js").write_text("void 0;", encoding="utf-8")
    (assets / "data-loader.js").write_text("void 0;", encoding="utf-8")
    (assets / "estate-explorer.css").write_text("body {}", encoding="utf-8")
    (assets / "estate-comparison.js").write_text("void 0;", encoding="utf-8")
    (assets / "buyer-profile.css").write_text("body {}", encoding="utf-8")
    (assets / "buyer-profile.js").write_text("void 0;", encoding="utf-8")
    (assets / "mrt-comparison.css").write_text("body {}", encoding="utf-8")
    (assets / "mrt-comparison.js").write_text("void 0;", encoding="utf-8")
    (assets / "private-project-comparison.css").write_text(
        "body {}", encoding="utf-8"
    )
    (assets / "private-project-comparison.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "home-loan-planner.js").write_text("void 0;", encoding="utf-8")
    (assets / "condo-loan-timeline-planner.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "condo-loan-timeline-funding-v3.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "project-exit-comparison.css").write_text(
        "body {}", encoding="utf-8"
    )
    (assets / "project-exit-comparison.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "property-analysis.css").write_text("body {}", encoding="utf-8")
    _write_transaction_fixture(assets)
    output = ROOT / f"_site-test-{tmp_path.name}-{os.getpid()}"
    try:
        count = build_pages_site.build_site(output, assets_dir=assets)

        source_count = len(build_pages_site.load_catalog()["reports"])
        analyses = build_pages_site.discover_property_analyses()
        assert count == source_count + len(analyses)
        assert (output / "index.html").is_file()
        assert (output / "reports.json").is_file()
        assert (output / "data-status.json").is_file()
        assert (output / "assets" / "research-shell.css").is_file()
        assert (output / "assets" / "data-loader.js").is_file()
        assert (output / "assets" / "data-loader.js").is_file()
        assert (output / "assets" / "estate-explorer.css").is_file()
        assert (output / "assets" / "estate-comparison.js").is_file()
        assert (output / "assets" / "buyer-profile.css").is_file()
        assert (output / "assets" / "buyer-profile.js").is_file()
        assert (output / "assets" / "mrt-comparison.css").is_file()
        assert (output / "assets" / "mrt-comparison.js").is_file()
        assert (output / "assets" / "home-loan-planner.js").is_file()
        assert (output / "assets" / "condo-loan-timeline-planner.js").is_file()
        assert (output / "assets" / "condo-loan-timeline-funding-v3.js").is_file()
        assert (output / "assets" / "project-exit-comparison.css").is_file()
        assert (output / "assets" / "project-exit-comparison.js").is_file()
        assert (output / "home_loan_planner.html").is_file()
        assert (output / "condo_loan_timeline_planner.html").is_file()
        assert (output / "project_exit_comparison.html").is_file()
        assert (
            output / "assets" / "condo-transactions" / "manifest.json"
        ).is_file()
        transaction_manifest = json.loads(
            (
                output / "assets" / "condo-transactions" / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert (
            output
            / "assets"
            / "condo-transactions"
            / transaction_manifest["dataset_revision"]
            / "shard-00.json"
        ).is_file()
        project_catalog = json.loads(
            (
                output / "assets" / "project-catalog" / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert (
            output
            / "assets"
            / "project-catalog"
            / project_catalog["catalog_revision"]
            / "catalog.json"
        ).is_file()
        project_registry = json.loads(
            (
                output / "assets" / "project-identity-registry" / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert (
            output
            / "assets"
            / "project-identity-registry"
            / project_registry["registry_revision"]
            / "registry.json"
        ).is_file()
        landing = (output / "index.html").read_text(encoding="utf-8")
        assert project_registry["registry_revision"] in landing
        assert build_pages_site.project_registry_data.registry_asset_path(
            project_registry["registry_revision"]
        ) in landing
        config_match = re.search(
            r'<script type="application/json" id="project-identity-registry-config">'
            r"(.*?)</script>",
            landing,
            flags=re.DOTALL,
        )
        assert config_match
        config = json.loads(config_match.group(1))
        assert config["bootstrap"] == (
            build_pages_site.project_registry_bootstrap_records(project_registry)
        )
        assert (output / ".nojekyll").is_file()
        for analysis in analyses:
            assert (output / analysis.output_path).is_file()
        merged_catalog = json.loads(
            (output / "reports.json").read_text(encoding="utf-8")
        )
        assert merged_catalog["schema_version"] == 2
        assert len(merged_catalog["reports"]) == count
        assert all(report["data_families"] for report in merged_catalog["reports"])
        property_entries = [
            report
            for report in merged_catalog["reports"]
            if report["kind"] == "property-analysis"
        ]
        assert {"Arc at Tampines", "Park Place Residences at PLQ"} <= {
            report["project_name"]
            for report in property_entries
        }
        assert {report["id"] for report in property_entries} == {
            analysis.report_id for analysis in analyses
        }
        assert {report["path"] for report in property_entries} == {
            analysis.output_path for analysis in analyses
        }
        landing = (output / "index.html").read_text(encoding="utf-8")
        assert build_pages_site.PROPERTY_CARDS_MARKER not in landing
        assert landing.count(build_pages_site.REPORT_LIBRARY_START_MARKER) == 1
        assert landing.count(build_pages_site.REPORT_LIBRARY_END_MARKER) == 1
        assert build_pages_site.DATA_STATUS_MARKER not in landing
        assert "Know what is fresh—and what is not" in landing
        assert 'href="data-status.json"' in landing
        assert "data-kind=\"analysis project\"" in landing
        assert all(
            f'href="{analysis.output_path}"' in landing for analysis in analyses
        )
        assert "earlier snapshot" in landing
        assert "Property Analysis · Property Analysis" not in landing
        assert "Property analysis · Future Project" in landing
        report = (output / "comparison_table.html").read_text(encoding="utf-8")
        assert report.count("assets/research-shell.css") == 1
        assert report.count("assets/research-shell.js") == 1
        assert report.count('id="research-report-status"') == 1
        bootstrap_match = re.search(
            r'<script type="application/json" id="research-report-status">(.*?)</script>',
            report,
            flags=re.DOTALL,
        )
        assert bootstrap_match
        bootstrap = json.loads(bootstrap_match.group(1))
        assert bootstrap["data_families"] == [
            "estate_model",
            "private_transactions",
        ]
        assert bootstrap["families"]["estate_model"]["data_through"] is None
        assert bootstrap["families"]["private_transactions"][
            "data_through"
        ] == json.loads(
            (output / "data-status.json").read_text(encoding="utf-8")
        )["families"]["private_transactions"]["complete_through"]
        assert bootstrap["generated_at"] != bootstrap["families"][
            "private_transactions"
        ]["data_through"]
        buyer_report = (output / "buyer_profile_table.html").read_text(
            encoding="utf-8"
        )
        assert buyer_report.count("assets/research-shell.css") == 1
        assert buyer_report.count("assets/research-shell.js") == 1
        assert buyer_report.count("assets/estate-explorer.css") == 1
        assert buyer_report.count("assets/buyer-profile.css") == 1
        assert buyer_report.count("assets/buyer-profile.js") == 1
        mrt_report = (output / "mrt_comparison_table.html").read_text(
            encoding="utf-8"
        )
        assert mrt_report.count("assets/research-shell.css") == 1
        assert mrt_report.count("assets/research-shell.js") == 1
        assert mrt_report.count("assets/estate-explorer.css") == 1
        assert mrt_report.count("assets/mrt-comparison.css") == 1
        assert mrt_report.count("assets/mrt-comparison.js") == 1
        built_status = json.loads(
            (output / "data-status.json").read_text(encoding="utf-8")
        )
        for entry in merged_catalog["reports"]:
            entry_html = (output / entry["path"]).read_text(encoding="utf-8")
            assert entry_html.count('id="research-report-status"') == 1
            entry_match = re.search(
                r'<script type="application/json" id="research-report-status">(.*?)</script>',
                entry_html,
                flags=re.DOTALL,
            )
            assert entry_match
            entry_status = json.loads(entry_match.group(1))
            assert entry_status["report_path"] == entry["path"]
            assert entry_status["data_families"] == entry["data_families"]
            assert set(entry_status["families"]) == set(entry["data_families"])
            for family_id in entry["data_families"]:
                expected_family = dict(built_status["families"][family_id])
                if entry["kind"] == "property-analysis" and family_id == (
                    "market_research"
                ):
                    expected_family["last_checked"] = entry["captured_at"]
                assert entry_status["families"][family_id] == expected_family
        captured_entry = property_entries[0]
        captured_html = (output / captured_entry["path"]).read_text(
            encoding="utf-8"
        )
        captured_match = re.search(
            r'<script type="application/json" id="research-report-status">(.*?)</script>',
            captured_html,
            flags=re.DOTALL,
        )
        assert captured_match
        captured_status = json.loads(captured_match.group(1))
        assert captured_status["data_families"] == ["market_research"]
        assert captured_status["families"]["market_research"][
            "last_checked"
        ] == captured_entry["captured_at"]
        assert captured_status["families"]["market_research"][
            "data_through"
        ] is None
    finally:
        if output.is_dir():
            for path in sorted(output.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            output.rmdir()


def test_project_identity_registry_replaces_legacy_landing_name_index():
    registry = build_pages_site.validate_project_identity_registry_assets(
        build_pages_site.DEFAULT_ASSETS
    )
    records = registry["records"]
    records_by_id = {record["id"]: record for record in records}
    treasure = records_by_id["treasure-at-tampines"]

    assert registry["counts"]["records"] == len(records)
    assert treasure["identity"]["precision"] == "full"
    assert treasure["capabilities"]["explorer"] == {
        "available": True,
        "routes": [
            {
                "path": "private_project_comparison_table.html?"
                "q=TREASURE%20AT%20TAMPINES%20TAMPINES%20LANE&district=18",
                "source": "private_project_explorer",
                "is_latest": True,
            }
        ],
        "evidence_status": "achieved_transactions",
        "reason": None,
    }
    name_only = next(
        record for record in records if record["identity"]["name"] == "2B COMPLEX"
    )
    assert name_only["identity"]["precision"] == "name_only"
    assert name_only["capabilities"]["explorer"]["available"] is False
    assert name_only["capabilities"]["explorer"]["reason"]
    duplicate_name = [
        record
        for record in records
        if record["identity"]["name"] == "EASTERN LAGOON"
    ]
    assert len(duplicate_name) > 1
    assert len({record["id"] for record in duplicate_name}) == len(duplicate_name)
    assert len(
        {record["identity"]["selection_label"] for record in duplicate_name}
    ) == len(duplicate_name)


def test_project_report_routes_include_authored_and_generated_histories():
    catalog = build_pages_site.load_catalog()
    analyses = build_pages_site.discover_property_analyses()

    routes = build_pages_site.build_project_report_routes(catalog, analyses)
    poiz = [
        route
        for route in routes
        if route["project_name"].upper() == "THE POIZ RESIDENCES"
    ]

    assert {route["path"] for route in poiz} == {
        "poiz_east_resale_comparison.html",
        "poiz_east_unit_growth_transactions.html",
        "property-analysis-2026-07-27-the-poiz-residences.html",
    }
    assert sum(route["is_latest"] is True for route in poiz) == 3
    assert all(
        set(route)
        == {
            "project_name",
            "project_slug",
            "path",
            "source",
            "is_latest",
            "street",
            "district",
            "planning_area",
        }
        for route in routes
    )


def _merged_report_catalog():
    catalog = build_pages_site.load_catalog()
    analyses, _, merged = build_pages_site._prepare_property_publication(
        catalog,
        property_analysis_dir=build_pages_site.DEFAULT_PROPERTY_ANALYSIS_DIR,
    )
    return catalog, analyses, merged


def _property_report(
    *,
    report_id="analysis-2026-08-08-sample",
    path="analysis-2026-08-08-sample.html",
    captured_at="2026-08-08T09:00:00+08:00",
    is_latest=True,
):
    return {
        "id": report_id,
        "path": path,
        "title": "Sample Residence — dated analysis",
        "category": "property-analysis",
        "kind": "property-analysis",
        "summary": "A point-in-time decision record.",
        "tags": ["sample", "property analysis"],
        "data_families": ["market_research"],
        "project_name": "Sample Residence",
        "project_slug": "sample-residence",
        "captured_at": captured_at,
        "status": "complete",
        "market_stage": "resale",
        "is_latest": is_latest,
    }


def test_merged_library_represents_every_path_exactly_once_and_groups_history():
    _, _, merged = _merged_report_catalog()
    rendered = build_pages_site.render_report_library(merged)
    parser = _LibraryParser()
    parser.feed(rendered)

    represented = Counter(
        card["data-report-path"] for card in parser.cards
    ) + Counter(link["data-report-path"] for _, link in parser.history_links)
    expected = Counter(report["path"] for report in merged["reports"])

    assert represented == expected
    assert set(represented.values()) == {1}
    assert len(parser.cards) == 52
    assert len(parser.primary_links) == 52
    assert len(parser.history_links) == 2
    assert len(parser.cards) + len(parser.history_links) == 54
    assert all(card["data-freshness"] in {"dated", "unknown"} for card in parser.cards)
    assert sum(card["data-freshness"] == "dated" for card in parser.cards) == 26
    assert sum(card["data-freshness"] == "unknown" for card in parser.cards) == 26

    primary_paths = {card["data-report-path"] for card in parser.cards}
    history_paths = {link["data-report-path"] for _, link in parser.history_links}
    for slug in ("canberra-crescent-residences", "the-lakegarden-residences"):
        project_reports = sorted(
            (
                report
                for report in merged["reports"]
                if report.get("project_slug") == slug
            ),
            key=lambda report: report["captured_at"],
            reverse=True,
        )
        assert project_reports[0]["path"] in primary_paths
        assert project_reports[1]["path"] in history_paths
        assert project_reports[1]["path"] not in primary_paths

    # Authored entries are independent products, not older analysis snapshots.
    assert "canberra_crescent_d27_deep_analysis.html" in primary_paths
    assert "poiz_east_resale_comparison.html" in primary_paths
    assert "poiz_east_unit_growth_transactions.html" in primary_paths


def test_property_history_is_ordered_by_capture_not_catalog_position():
    newest = _property_report()
    older = _property_report(
        report_id="analysis-2026-08-03-sample",
        path="analysis-2026-08-03-sample.html",
        captured_at="2026-08-03T09:00:00+08:00",
        is_latest=False,
    )
    rendered = build_pages_site.render_report_library({"reports": [older, newest]})
    parser = _LibraryParser()
    parser.feed(rendered)

    assert parser.cards[0]["data-report-path"] == newest["path"]
    assert parser.history_links[0][1]["data-report-path"] == older["path"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda reports: [report.update(is_latest=False) for report in reports], "exactly one latest"),
        (lambda reports: [report.update(is_latest=True) for report in reports], "exactly one latest"),
        (
            lambda reports: (
                reports[0].update(is_latest=True),
                reports[1].update(is_latest=False),
            ),
            "latest capture is not the newest",
        ),
        (lambda reports: reports[0].update(captured_at=reports[1]["captured_at"]), "repeats captured_at"),
        (lambda reports: reports[0].update(captured_at="2026-08-03T09:00:00"), "UTC offset"),
        (lambda reports: reports[0].update(id=reports[1]["id"]), "Duplicate merged report id"),
        (lambda reports: reports[0].update(path=reports[1]["path"]), "Duplicate merged report path"),
    ],
)
def test_property_history_contract_fails_closed(mutate, message):
    older = _property_report(
        report_id="analysis-2026-08-03-sample",
        path="analysis-2026-08-03-sample.html",
        captured_at="2026-08-03T09:00:00+08:00",
        is_latest=False,
    )
    newest = _property_report()
    reports = [older, newest]
    mutate(reports)

    with pytest.raises(ValueError, match=message):
        build_pages_site.render_report_library({"reports": reports})


def test_catalog_only_addition_drives_card_category_and_district_route():
    report = {
        "id": "district-09",
        "path": "district_09.html",
        "title": "District 09 research",
        "category": "district",
        "kind": "research",
        "summary": "A newly catalogued district report.",
        "tags": ["district 09"],
        "data_families": ["market_research"],
    }
    catalog = {"reports": [report]}

    rendered = build_pages_site.render_report_library(catalog)
    options = build_pages_site._category_options(catalog)
    config = build_pages_site.build_report_library_config(catalog)

    assert 'data-report-path="district_09.html"' in rendered
    assert 'data-category="district"' in rendered
    assert '<option value="district">District</option>' in options
    assert config == {
        "schema_version": 1,
        "district_routes": {"9": "district_09.html"},
    }


def test_nested_report_paths_with_same_basename_remain_distinct_and_safe():
    reports = []
    for report_id, path in (
        ("nested-a", "a/report.html"),
        ("nested-b", "b/report.html"),
    ):
        reports.append(
            {
                "id": report_id,
                "path": path,
                "title": report_id,
                "category": "district",
                "kind": "research",
                "summary": "Nested safe report.",
                "tags": ["nested"],
                "data_families": ["market_research"],
            }
        )
    rendered = build_pages_site.render_report_library({"reports": reports})

    assert 'data-report-path="a/report.html"' in rendered
    assert 'data-report-path="b/report.html"' in rendered

    reports[0]["id"] = "district-12"
    config = build_pages_site.build_report_library_config({"reports": reports})
    assert config["district_routes"] == {"12": "a/report.html"}


def test_report_library_escapes_catalog_content_and_rejects_bad_category():
    report = {
        "id": "safe-entry",
        "path": "safe-entry.html",
        "title": 'Safe <script>alert("x")</script>',
        "category": "new-category",
        "kind": "research",
        "summary": 'Summary with <b>markup</b> & "quotes".',
        "tags": ['tag "quoted"'],
        "data_families": ["market_research"],
    }
    rendered = build_pages_site.render_report_library({"reports": [report]})

    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert '&lt;b&gt;markup&lt;/b&gt; &amp; &quot;' in rendered
    assert "&quot;quoted&quot;" in rendered

    report["category"] = "Bad Category"
    with pytest.raises(ValueError, match="normalized lowercase URL-safe token"):
        build_pages_site.render_report_library({"reports": [report]})


def test_district_config_excludes_pair_and_noncanonical_metadata():
    _, _, merged = _merged_report_catalog()
    config = build_pages_site.build_report_library_config(merged)

    assert config["district_routes"] == {
        "17": "private_project_comparison_D17.html",
        "18": "private_project_comparison_D18.html",
        "27": "private_project_comparison_D27.html",
    }
    assert "district_pair_comparison_D18_D26.html" not in config[
        "district_routes"
    ].values()
    assert "tampines_condo_school_mrt_area_guide_2026-08-08.html" not in config[
        "district_routes"
    ].values()


def test_report_library_injection_is_idempotent_and_preserves_markers(tmp_path):
    catalog = {
        "reports": [
            {
                "id": "district-09",
                "path": "district_09.html",
                "title": "District 09 research",
                "category": "district",
                "kind": "research",
                "summary": "A catalog-driven district report.",
                "tags": ["district 09"],
                "data_families": ["market_research"],
            }
        ]
    }
    index_path = tmp_path / "index.html"
    index_path.write_text(
        "\n".join(
            (
                "<select>",
                build_pages_site.REPORT_CATEGORY_OPTIONS_START_MARKER,
                '<option value="all">All categories</option>',
                build_pages_site.REPORT_CATEGORY_OPTIONS_END_MARKER,
                "</select>",
                '<div id="report-grid">',
                build_pages_site.REPORT_LIBRARY_START_MARKER,
                "legacy cards",
                build_pages_site.REPORT_LIBRARY_END_MARKER,
                "</div>",
                build_pages_site.REPORT_LIBRARY_CONFIG_START_MARKER,
                '<script type="application/json" id="report-library-config">'
                f"{build_pages_site.REPORT_LIBRARY_CONFIG_MARKER}</script>",
                build_pages_site.REPORT_LIBRARY_CONFIG_END_MARKER,
            )
        ),
        encoding="utf-8",
    )

    build_pages_site.inject_report_library(index_path, catalog)
    first = index_path.read_bytes()
    build_pages_site.inject_report_library(index_path, catalog)
    second = index_path.read_bytes()

    assert second == first
    source = second.decode("utf-8")
    for marker in (
        build_pages_site.REPORT_CATEGORY_OPTIONS_START_MARKER,
        build_pages_site.REPORT_CATEGORY_OPTIONS_END_MARKER,
        build_pages_site.REPORT_LIBRARY_START_MARKER,
        build_pages_site.REPORT_LIBRARY_END_MARKER,
        build_pages_site.REPORT_LIBRARY_CONFIG_START_MARKER,
        build_pages_site.REPORT_LIBRARY_CONFIG_END_MARKER,
    ):
        assert source.count(marker) == 1


def test_project_registry_route_validation_rejects_swapped_ownership():
    catalog, analyses, _ = _merged_report_catalog()
    registry = deepcopy(
        build_pages_site.validate_project_identity_registry_assets(
            build_pages_site.DEFAULT_ASSETS
        )
    )
    route_owners = [
        record
        for record in registry["records"]
        if len(record["capabilities"]["dedicated_report"]["routes"]) == 1
    ]
    first, second = route_owners[:2]
    first_route = first["capabilities"]["dedicated_report"]["routes"][0]
    second_route = second["capabilities"]["dedicated_report"]["routes"][0]
    first["capabilities"]["dedicated_report"]["routes"] = [second_route]
    second["capabilities"]["dedicated_report"]["routes"] = [first_route]

    with pytest.raises(ValueError, match="same-record source key|ownership"):
        build_pages_site.validate_project_registry_report_routes(
            registry,
            catalog,
            analyses,
        )


def test_landing_project_registry_exposes_loading_fallback_and_retry_states():
    landing = (ROOT / "index.html").read_text(encoding="utf-8")
    config_match = re.search(
        r'<script type="application/json" id="project-identity-registry-config">'
        r"(.*?)</script>",
        landing,
        flags=re.DOTALL,
    )
    assert config_match
    config = json.loads(config_match.group(1))
    registry = build_pages_site.validate_project_identity_registry_assets(
        build_pages_site.DEFAULT_ASSETS
    )
    assert config == {
        "schema": registry["schema"],
        "revision": registry["registry_revision"],
        "path": build_pages_site.project_registry_data.registry_asset_path(
            registry["registry_revision"]
        ),
        "counts": registry["counts"],
        "bootstrap": build_pages_site.project_registry_bootstrap_records(registry),
    }

    assert 'src="assets/data-loader.js"' in landing
    assert 'id="project-catalog-status"' in landing
    assert 'id="project-catalog-status-copy"' in landing
    assert 'id="project-catalog-retry"' in landing
    assert "Loading canonical project registry…" in landing
    assert "Canonical project registry unavailable. Search is limited" in landing
    assert "window.SGEstateData.loadJSON(PROJECT_REGISTRY.path" in landing
    assert "window.SGEstateData.invalidate(PROJECT_REGISTRY.path" in landing
    assert 'projectCatalogRetry.addEventListener("click"' in landing
    assert "projects = payload.records;" in landing
    assert landing.count("renderSuggestions();") >= 2
    assert "data-project-id" in landing
    assert "selectedProjectId" in landing


def test_data_status_keeps_coverage_and_generation_dates_distinct():
    status = build_pages_site.build_data_status()

    assert status["schema_version"] == 2
    assert status["model_run"]["status"] == "complete"
    assert status["model_run"]["generated_at"]
    assert status["families"]["estate_model"]["hdb_transactions_through"]
    private = status["families"]["private_transactions"]
    assert private["complete_through"] <= private["latest_period"]
    assert private["status"] in {
        "partial_latest_period",
        "complete_latest_period",
    }
    assert status["families"]["rail_network"]["checked_through"]
    assert status["families"]["estate_model"]["data_through"] is None
    assert status["families"]["estate_model"]["last_checked"] is None
    assert status["families"]["estate_model"]["generated_at"]
    assert status["families"]["private_transactions"]["data_through"] == (
        private["complete_through"]
    )
    assert status["families"]["private_transactions"]["generated_at"] is None
    assert status["families"]["rail_network"]["data_through"] is None
    assert status["families"]["rail_network"]["last_checked"]
    assert status["families"]["finance_assumptions"] == {
        "label": "Finance assumptions",
        "status": "assumption_driven",
        "data_through": None,
        "last_checked": None,
        "generated_at": None,
        "note": "User-entered scenarios and visible assumptions; no live market-data feed.",
    }
    assert status["families"]["market_research"] == {
        "label": "Market research",
        "status": "point_in_time_or_unreceipted",
        "data_through": None,
        "last_checked": None,
        "generated_at": None,
        "note": (
            "Point-in-time or source-specific project research; generic dates "
            "remain unknown unless the report records a capture."
        ),
    }
    assert all(dataset["retrieved_at"] is None for dataset in status["datasets"])
    assert {dataset["dataset_id"] for dataset in status["datasets"]} == set(
        json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))[
            "datasets"
        ]
    )


def test_report_generation_date_requires_its_own_explicit_label():
    source = """<p>
      <b>Transaction data through:</b> <time datetime="2026-06">Jun 2026</time>
      · <b>Generated:</b> <time datetime="2026-08-09">9 Aug 2026</time>
    </p>"""

    assert build_pages_site._report_generated_at(source) == "2026-08-09"
    assert build_pages_site._report_generated_at(
        '<p>Generated report · <time datetime="2026-06">Jun 2026</time></p>'
    ) is None


def test_status_bootstrap_is_injected_even_without_shell_assets(tmp_path):
    report_path = tmp_path / "report.html"
    report_path.write_text(
        "<!doctype html><html><head></head><body><h1>Report</h1></body></html>",
        encoding="utf-8",
    )
    family = {
        "label": "Finance assumptions",
        "status": "assumption_driven",
        "data_through": None,
        "last_checked": None,
        "generated_at": None,
        "note": "User-entered assumptions.",
    }

    build_pages_site.inject_research_shell(
        tmp_path,
        catalog={
            "reports": [
                {
                    "path": "report.html",
                    "data_families": ["finance_assumptions"],
                }
            ]
        },
        data_status={"families": {"finance_assumptions": family}},
    )

    source = report_path.read_text(encoding="utf-8")
    assert source.count('id="research-report-status"') == 1
    assert "research-shell.css" not in source
    assert "research-shell.js" not in source


def _write_data_status_fixture(tmp_path: Path, *, schema_version: int = 3):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    dataset_id = "sample.csv"
    dataset = inputs / dataset_id
    dataset.write_text("estate,value\nALPHA,1\n", encoding="utf-8")
    for name, content in {
        "hdb_resale.csv": "month\n2026-06\n",
        "mrt_layer.csv": "status_as_of\n2026-08-08\n",
        "mrt_network_status.csv": "status_as_of\n2026-08-08\n",
    }.items():
        (inputs / name).write_text(content, encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "datasets": {
                    dataset_id: {
                        "zone": "ingested",
                        "producer": "models/example.py",
                        "authority": "Example Authority",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    transaction_manifest = tmp_path / "transaction-manifest.json"
    transaction_manifest.write_text(
        json.dumps({"source_metadata": {"canonical": {}}}),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": schema_version,
        "status": "complete",
        "as_of_year": 2026,
        "completed_at": "2026-08-13T01:00:00+00:00",
        "refresh_derived": schema_version == 3,
        "inputs": {dataset_id: source_receipts.sha256_file(dataset)},
    }
    if schema_version == 3:
        receipt = source_receipts.build_source_receipt(
            dataset,
            dataset_id=dataset_id,
            authority="Example Authority",
            source_url="https://data.example.test/sample.csv",
            source_identity="example-sample-v1",
            retrieved_at="2026-08-12T23:30:00+00:00",
            coverage_start="2026-01",
            coverage_end="2026-07",
            row_count=1,
            cache_state="fresh",
            fallback_state="not_used",
            validation_status="passed",
        )
        manifest["source_receipts"] = {dataset_id: receipt}
    run_manifest = tmp_path / "run-manifest.json"
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    return inputs, catalog, run_manifest, transaction_manifest, dataset


def test_data_status_maps_validated_v3_source_receipts(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, _ = (
        _write_data_status_fixture(tmp_path)
    )

    status = build_pages_site.build_data_status(
        catalog_path=catalog,
        run_manifest_path=run_manifest,
        transaction_manifest_path=transaction_manifest,
        input_dir=inputs,
    )

    dataset = status["datasets"][0]
    assert status["schema_version"] == 2
    assert status["model_run"]["refresh_mode"] == "network_refresh"
    assert status["model_run"]["source_receipt_modes"] == {"sample.csv": "fresh"}
    assert dataset["status"] == "verified_in_model_run"
    assert dataset["retrieved_at"] == "2026-08-12T23:30:00+00:00"
    assert dataset["coverage_start"] == "2026-01"
    assert dataset["coverage_end"] == "2026-07"
    assert dataset["coverage_basis"] == "source_receipt"
    assert dataset["row_count"] == 1
    assert dataset["cache_state"] == "fresh"
    assert dataset["fallback_state"] == "not_used"
    assert dataset["validation_status"] == "passed"
    assert dataset["acquisition_mode"] == "fresh"
    assert status["families"]["private_transactions"]["status"] == "unknown"
    assert status["families"]["private_transactions"]["data_through"] is None


def test_data_status_uses_promoted_receipt_hash_for_refreshed_output(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, _ = (
        _write_data_status_fixture(tmp_path)
    )
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    # Refreshed outputs are not run inputs. A colliding input key can instead
    # describe the pre-refresh fallback bytes, as tree_canopy does.
    manifest["inputs"]["sample.csv"] = "0" * 64
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    status = build_pages_site.build_data_status(
        catalog_path=catalog,
        run_manifest_path=run_manifest,
        transaction_manifest_path=transaction_manifest,
        input_dir=inputs,
    )

    assert status["datasets"][0]["status"] == "verified_in_model_run"


def test_data_status_surfaces_fallback_when_other_receipt_is_fresh(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, _ = (
        _write_data_status_fixture(tmp_path)
    )
    second_id = "fallback.csv"
    second = inputs / second_id
    second.write_text("estate,value\nBETA,2\n", encoding="utf-8")
    catalog_value = json.loads(catalog.read_text(encoding="utf-8"))
    catalog_value["datasets"][second_id] = {
        "zone": "ingested",
        "producer": "models/fallback.py",
        "authority": "Fallback Authority",
    }
    catalog.write_text(json.dumps(catalog_value), encoding="utf-8")
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest["source_receipts"][second_id] = source_receipts.build_source_receipt(
        second,
        dataset_id=second_id,
        authority="Fallback Authority",
        source_identity="reviewed:fallback-snapshot",
        retrieved_at=None,
        coverage_start=None,
        coverage_end=None,
        row_count=1,
        cache_state="offline",
        fallback_state="used",
        validation_status="passed",
    )
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    status = build_pages_site.build_data_status(
        catalog_path=catalog,
        run_manifest_path=run_manifest,
        transaction_manifest_path=transaction_manifest,
        input_dir=inputs,
    )

    assert status["model_run"]["refresh_mode"] == "reviewed_fallback"
    assert status["model_run"]["source_receipt_modes"] == {
        "fallback.csv": "fallback",
        "sample.csv": "fresh",
    }


def test_data_status_marks_current_bytes_modified_since_run(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, dataset_path = (
        _write_data_status_fixture(tmp_path)
    )
    dataset_path.write_text("estate,value\nALPHA,2\n", encoding="utf-8")

    status = build_pages_site.build_data_status(
        catalog_path=catalog,
        run_manifest_path=run_manifest,
        transaction_manifest_path=transaction_manifest,
        input_dir=inputs,
    )

    assert status["datasets"][0]["status"] == "modified_since_run"


def test_data_status_legacy_manifest_keeps_unknown_receipt_fields_null(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, _ = (
        _write_data_status_fixture(tmp_path, schema_version=2)
    )

    status = build_pages_site.build_data_status(
        catalog_path=catalog,
        run_manifest_path=run_manifest,
        transaction_manifest_path=transaction_manifest,
        input_dir=inputs,
    )

    dataset = status["datasets"][0]
    assert dataset["retrieved_at"] is None
    assert dataset["coverage_start"] is None
    assert dataset["cache_state"] == "unknown"
    assert dataset["acquisition_mode"] == "unknown"


def test_data_status_rejects_receipt_authority_disagreement(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, _ = (
        _write_data_status_fixture(tmp_path)
    )
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest["source_receipts"]["sample.csv"]["authority"] = "Other Authority"
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="authority.*differs"):
        build_pages_site.build_data_status(
            catalog_path=catalog,
            run_manifest_path=run_manifest,
            transaction_manifest_path=transaction_manifest,
            input_dir=inputs,
        )


def test_data_status_rejects_unvalidated_promoted_receipt(tmp_path):
    inputs, catalog, run_manifest, transaction_manifest, _ = (
        _write_data_status_fixture(tmp_path)
    )
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest["source_receipts"]["sample.csv"]["validation_status"] = "not_run"
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="was not validated"):
        build_pages_site.build_data_status(
            catalog_path=catalog,
            run_manifest_path=run_manifest,
            transaction_manifest_path=transaction_manifest,
            input_dir=inputs,
        )


def test_pages_builder_rejects_output_outside_repository(tmp_path):
    with pytest.raises(ValueError, match="inside the repository"):
        build_pages_site.build_site(tmp_path / "site")


def test_pages_builder_does_not_replace_unowned_directory(tmp_path):
    output = ROOT / f"_site-unowned-test-{tmp_path.name}-{os.getpid()}"
    output.mkdir()
    (output / "user-file.txt").write_text("keep", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="unowned non-empty"):
            build_pages_site.build_site(output)
        assert (output / "user-file.txt").read_text(encoding="utf-8") == "keep"
    finally:
        (output / "user-file.txt").unlink()
        output.rmdir()


def test_pages_link_validator_rejects_missing_local_asset(tmp_path):
    (tmp_path / "index.html").write_text(
        '<link rel="stylesheet" href="assets/missing.css">',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="assets/missing.css"):
        build_pages_site.validate_site_links(tmp_path)


def _write_transaction_fixture(assets: Path, *, count: int = 1) -> Path:
    transaction_dir = assets / "condo-transactions"
    raw = pd.DataFrame(
        [
            {
                "project_name": "SAMPLE RESIDENCES",
                "street_name": "ONE ROAD",
                "postal_district": "01",
                "planning_area": "DOWNTOWN CORE",
                "sale_month": "2026-01",
                "transacted_price": 1_000_000,
                "area_sqm": 50,
                "type_of_sale": "Resale",
                "floor_level": "01-05",
            }
            for _ in range(count)
        ]
    )
    _, shards, manifest = build_pages_site.transaction_data.build_transaction_shards(
        raw,
        pd.DataFrame(),
        [
            {
                "id": "sample",
                "project": "SAMPLE RESIDENCES",
                "street": "ONE ROAD",
                "district": "01",
                "planning_area": "DOWNTOWN CORE",
            }
        ],
    )
    build_pages_site.transaction_data.write_shards(
        transaction_dir,
        shards,
        manifest,
    )
    project_payload = build_pages_site.project_catalog_data.build_project_catalog(
        [
            {
                "project": "SAMPLE RESIDENCES",
                "street": "ONE ROAD",
                "district": "01",
                "planning_area": "DOWNTOWN CORE",
            }
        ],
        [
            {
                "id": "sample",
                "selection_label": "SAMPLE RESIDENCES",
                "project": "SAMPLE RESIDENCES",
                "street": "ONE ROAD",
                "district": "01",
                "planning_area": "DOWNTOWN CORE",
                "context_key": "DOWNTOWN CORE",
            }
        ],
        {"DOWNTOWN CORE": {"provision_band": "B"}},
        manifest,
        latest_project_month="2026-01",
    )
    build_pages_site.project_catalog_data.publish_project_catalog(
        assets / "project-catalog",
        project_payload,
        transaction_manifest=manifest,
    )
    shutil.copytree(
        ROOT / "site" / "assets" / "project-identity-registry",
        assets / "project-identity-registry",
    )
    return transaction_dir


def _transaction_manifest(transaction_dir: Path) -> dict:
    return json.loads(
        (transaction_dir / "manifest.json").read_text(encoding="utf-8")
    )


def _transaction_shard_path(transaction_dir: Path, index: int) -> Path:
    manifest = _transaction_manifest(transaction_dir)
    return transaction_dir / manifest["dataset_revision"] / f"shard-{index:02d}.json"


def _write_both_transaction_manifests(
    transaction_dir: Path,
    manifest: dict,
) -> None:
    encoded = json.dumps(manifest)
    (transaction_dir / "manifest.json").write_text(encoded, encoding="utf-8")
    (
        transaction_dir / manifest["dataset_revision"] / "manifest.json"
    ).write_text(encoded, encoding="utf-8")


def _run_pages_check(monkeypatch, assets: Path) -> None:
    monkeypatch.setattr(build_pages_site, "DEFAULT_ASSETS", assets)
    monkeypatch.setattr(
        build_pages_site,
        "parse_args",
        lambda: build_pages_site.argparse.Namespace(out=None),
    )
    monkeypatch.setattr(build_pages_site, "load_catalog", lambda: {"reports": []})
    monkeypatch.setattr(
        build_pages_site,
        "_prepare_property_publication",
        lambda catalog, property_analysis_dir: ([], {}, catalog),
    )
    monkeypatch.setattr(
        build_pages_site,
        "build_data_status",
        lambda: {"datasets": []},
    )
    build_pages_site.main()


def test_transaction_asset_validator_reconciles_manifest_and_shards(tmp_path):
    assets = tmp_path / "assets"
    _write_transaction_fixture(assets)

    build_pages_site.validate_transaction_assets(assets)


def test_project_catalog_asset_validator_reconciles_immutable_catalog(tmp_path):
    assets = tmp_path / "assets"
    _write_transaction_fixture(assets)

    build_pages_site.validate_project_catalog_assets(assets)


def test_project_catalog_asset_validator_rejects_mixed_root_and_immutable(
    tmp_path,
):
    assets = tmp_path / "assets"
    _write_transaction_fixture(assets)
    root = assets / "project-catalog" / "manifest.json"
    payload = json.loads(root.read_text(encoding="utf-8"))
    payload["latest_project_month"] = "2025-12"
    payload["catalog_revision"] = (
        build_pages_site.project_catalog_data.compute_catalog_revision(payload)
    )
    root.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot load project catalog|Immutable"):
        build_pages_site.validate_project_catalog_assets(assets)


def test_transaction_asset_validator_rejects_missing_project_rows(tmp_path):
    assets = tmp_path / "assets"
    transaction_dir = _write_transaction_fixture(assets)
    shard_path = _transaction_shard_path(
        transaction_dir,
        build_pages_site.transaction_data.shard_index("sample"),
    )
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    shard["projects"] = {}
    shard_path.write_text(json.dumps(shard), encoding="utf-8")

    with pytest.raises(ValueError, match="membership does not match"):
        build_pages_site.validate_transaction_assets(assets)


@pytest.mark.parametrize("failure", ["missing", "corrupt", "wrong_revision"])
def test_pages_check_rejects_incomplete_or_mixed_transaction_generation(
    tmp_path,
    monkeypatch,
    failure,
):
    assets = tmp_path / "assets"
    transaction_dir = _write_transaction_fixture(assets)
    shard_path = _transaction_shard_path(transaction_dir, 0)
    if failure == "missing":
        shard_path.unlink()
        expected = "does not exist"
    elif failure == "corrupt":
        shard_path.write_text("{not-json", encoding="utf-8")
        expected = "Cannot load transaction shard"
    else:
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        shard["dataset_revision"] = "0" * 64
        shard_path.write_text(json.dumps(shard), encoding="utf-8")
        expected = "dataset_revision does not match"

    with pytest.raises(ValueError, match=expected):
        _run_pages_check(monkeypatch, assets)


def test_transaction_asset_validator_rejects_unsafe_inventory_path(tmp_path):
    assets = tmp_path / "assets"
    transaction_dir = _write_transaction_fixture(assets)
    manifest = _transaction_manifest(transaction_dir)
    manifest["shards"][0]["path"] = "assets/condo-transactions/../shard-00.json"
    _write_both_transaction_manifests(transaction_dir, manifest)

    with pytest.raises(ValueError, match="unsafe or unexpected path"):
        build_pages_site.validate_transaction_assets(assets)


def test_transaction_asset_validator_recomputes_dataset_revision(tmp_path):
    assets = tmp_path / "assets"
    transaction_dir = _write_transaction_fixture(assets)
    shard_path = _transaction_shard_path(
        transaction_dir,
        build_pages_site.transaction_data.shard_index("sample"),
    )
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    shard["projects"]["sample"][0][1] += 1
    shard_path.write_text(json.dumps(shard), encoding="utf-8")

    with pytest.raises(ValueError, match="dataset_revision does not match normalized"):
        build_pages_site.validate_transaction_assets(assets)


def test_pages_workflow_uses_validated_site_builder():
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    assert "python scripts/build_pages_site.py --out _site" in workflow
    assert workflow.count("scripts/build_pages_site.py --out _site") == 1
    assert '- "property_analysis/**"' in workflow
    assert '- "sg_estate/reporting/**"' in workflow
    assert '- "site/**"' in workflow
    assert '- "models/gen_project_exit_comparison_html.py"' in workflow
    assert '- "models/gen_multi_condo_framework_comparison_html.py"' in workflow
    assert '- "models/multi_condo_transactions.py"' in workflow
    assert '- "models/private_project_catalog.py"' in workflow
    assert '- "data/inputs/ura_private.csv"' in workflow
    assert "edgeprop_condo_apartment_projects.csv" in workflow
    assert "actions/configure-pages@v5" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v4" in workflow


def test_root_reports_have_no_broken_internal_html_links():
    generated_paths = {
        analysis.output_path
        for analysis in build_pages_site.discover_property_analyses()
    }
    broken = []
    for report in ROOT.glob("*.html"):
        parser = _LinkParser()
        parser.feed(report.read_text(encoding="utf-8"))
        for href in parser.hrefs:
            target = href.split("#", 1)[0].split("?", 1)[0]
            if target.endswith(".html") and "://" not in target:
                is_generated_landing_route = (
                    report.name == "index.html" and target in generated_paths
                )
                if not (ROOT / target).is_file() and not is_generated_landing_route:
                    broken.append(f"{report.name} -> {target}")

    assert broken == []
