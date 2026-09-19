"""Tests for the interactive two-to-five-condominium comparison."""

from datetime import date
import json
from pathlib import Path
import re

import pytest

import gen_condo_framework_comparison_html as two_project
import gen_multi_condo_framework_comparison_html as comparison


DATASET_REVISION = "a" * 64
CATALOG_REVISION = "b" * 64
TRANSACTION_SCHEMA = {
    "version": 1,
    "record_format": "positional_array",
    "fields": [
        "sale_month",
        "price",
        "area_sqm",
        "area_sqft",
        "psf",
        "sale_type",
        "floor_level",
        "bedrooms",
        "bedroom_source",
        "data_source",
    ],
}
TRANSACTION_ENUMERATIONS = {
    "sale_types": ["New Sale", "Resale", "Sub Sale"],
    "floor_levels": ["01 to 05"],
    "bedroom_sources": ["matched"],
    "data_sources": ["ura_private"],
}
ROOT = Path(__file__).resolve().parents[1]


def _project(index: int, estate: str = "TEST ESTATE") -> dict:
    return {
        "id": f"project-{index}",
        "selection_label": f"PROJECT {index}",
        "project": f"PROJECT {index}",
        "district": "15",
        "planning_area": estate,
        "street": f"STREET {index}",
        "context_estate": estate,
        "context_basis": "direct",
        "tenure": "Freehold",
        "transactions_n": 20 + index,
        "median_price": 1_000_000 + index * 100_000,
        "median_psf": 2_000 + index * 50,
    }


def _catalog(projects: list[dict]) -> dict:
    browser_projects, contexts = two_project.build_browser_payload(projects)
    for project in browser_projects:
        project["capabilities"] = {
            "private_explorer": True,
            "framework_comparison": True,
            "transactions": True,
            "project_exit": True,
        }
    return {
        "schema": "private-project-catalog.v1",
        "catalog_revision": CATALOG_REVISION,
        "transaction_dataset_revision": DATASET_REVISION,
        "latest_project_month": "2026-06",
        "counts": {
            "all": len(projects),
            "comparison": len(projects),
            "transaction": len(projects),
        },
        "projects": browser_projects,
        "contexts": contexts,
    }


def test_default_ids_uses_a_deterministic_three_project_fallback():
    projects = [_project(index) for index in range(1, 6)]

    assert comparison.default_ids(projects) == [
        "project-1",
        "project-2",
        "project-3",
    ]


def test_default_ids_requires_at_least_two_projects():
    with pytest.raises(SystemExit, match="at least two"):
        comparison.default_ids([_project(1)])


def test_options_escape_labels_and_descriptions():
    project = _project(1)
    project.update(
        {
            "selection_label": 'A "PROJECT" & CO',
            "street": "<FIRST STREET>",
        }
    )

    options = comparison.options_html([project])

    assert 'value="A &quot;PROJECT&quot; &amp; CO"' in options
    assert "&lt;FIRST STREET&gt;" in options
    assert '<FIRST STREET>' not in options


def test_browser_payload_deduplicates_shared_estate_context():
    projects = [_project(1), _project(2)]
    projects[0]["provision_band"] = "B+"
    projects[1]["provision_band"] = "B+"

    browser_projects, contexts = two_project.build_browser_payload(projects)

    assert list(contexts) == ["TEST ESTATE"]
    assert contexts["TEST ESTATE"]["provision_band"] == "B+"
    assert all(project["context_key"] == "TEST ESTATE" for project in browser_projects)
    assert all("provision_band" not in project for project in browser_projects)


def test_render_exposes_two_to_five_workflow_and_framework_boundaries():
    projects = [_project(index) for index in range(1, 6)]
    page = comparison.render_html(
        projects,
        "2026-06",
        date(2026, 7, 26),
        dataset_revision=DATASET_REVISION,
        transaction_schema=TRANSACTION_SCHEMA,
        transaction_enumerations=TRANSACTION_ENUMERATIONS,
        project_catalog=_catalog(projects),
    )

    assert "<title>Multi-condominium framework comparison</title>" in page
    assert "const MIN_PROJECTS = 2, MAX_PROJECTS = 5;" in page
    assert 'id="project-tray"' in page
    assert 'id="add-project"' in page
    assert "Maximum 5 projects" in page
    assert "move-up" in page and "move-down" in page and "remove" in page
    assert 'getAll("p")' in page
    assert 'params.append("p",project.id)' in page
    assert 'window.addEventListener("popstate"' in page
    assert "Each project record can appear only once" in page
    assert "Project A is the reference" in page
    assert "Factor-by-factor matrix" in page
    assert "Transaction comparison and detailed analysis" in page
    assert 'id="tx-window"' in page
    assert 'id="tx-sale"' in page
    assert 'id="tx-bedroom"' in page
    assert 'id="tx-size"' in page
    assert 'id="tx-floor"' in page
    assert 'id="tx-source"' in page
    assert "Selected-period snapshot" in page
    assert "Annual median achieved PSF" in page
    assert "Detailed analysis" in page
    assert "Full transaction ledgers" in page
    assert "Download filtered CSV" in page
    assert "change in achieved median PSF, not repeat-unit appreciation" in page
    assert "incomplete EdgeProp backfill" in page
    assert "Bedroom provenance describes a transaction-row match" in page
    assert '<script src="assets/data-loader.js"></script>' in page
    assert page.index('src="assets/data-loader.js"') < page.index(
        "window.SGEstateData.loadMany"
    )
    assert "window.SGEstateData.loadMany(paths.map(transactionShardRequest))" in page
    assert f'const EXPECTED_DATASET_REVISION = "{DATASET_REVISION}";' in page
    assert "revision:EXPECTED_DATASET_REVISION" in page
    assert "payload.dataset_revision !== EXPECTED_DATASET_REVISION" in page
    assert "Transaction data generation changed while this page was open" in page
    assert "Reload required." in page
    assert "location.reload()" in page
    assert "timeoutMs:12_000" in page
    assert "sameTransactionContract(payload.schema,EXPECTED_TRANSACTION_SCHEMA)" in page
    assert (
        "sameTransactionContract(payload.enumerations,EXPECTED_TRANSACTION_ENUMERATIONS)"
        in page
    )
    assert "transactionErrors = new Map()" in page
    assert 'result.status!=="fulfilled"' in page
    assert "This project is missing from its transaction shard." in page
    assert "This project's transaction rows are malformed." in page
    assert "Transaction evidence unavailable." in page
    assert 'data-state="unavailable"' in page
    assert "excluded from totals and CSV" in page
    assert "downloadButton.disabled=!availableModels.length" in page
    assert "downloadableProjects.forEach" in page
    assert "Promise.all(paths" not in page
    assert "fetch(path)" not in page
    assert "transactionLoadToken" in page
    assert "show-more-transactions" in page
    assert 'scope="row"' in page and 'scope="col"' in page
    assert 'class="matrix-wrap" role="region" tabindex="0"' in page
    assert "Identity and Provision context" in page
    assert "Liveability (T0) and lifestyle trajectory" in page
    assert "HDB Value band / multiplier" in page
    assert "Not applicable" in page
    assert "without collapsing the evidence into a misleading winner" in page
    assert "Estate framework values describe the planning-area context" in page
    assert f'"path":"assets/project-catalog/{CATALOG_REVISION}/catalog.json"' in page
    assert "hydrateProjectCatalog" in page
    assert "Retry project catalog" in page
    assert "file:// pages" in page
    assert "capabilities.framework_comparison" in page
    assert "revision:PROJECT_CATALOG.revision" in page
    assert page.count('<option value="PROJECT ') == 3


@pytest.mark.parametrize("revision", [None, "", "A" * 64, "a" * 63, "g" * 64])
def test_render_rejects_missing_or_non_sha256_dataset_revision(revision):
    projects = [_project(1), _project(2)]
    with pytest.raises(SystemExit, match="dataset_revision"):
        comparison.render_html(
            projects,
            "2026-06",
            date(2026, 7, 26),
            dataset_revision=revision,
            transaction_schema=TRANSACTION_SCHEMA,
            transaction_enumerations=TRANSACTION_ENUMERATIONS,
            project_catalog=_catalog(projects),
        )


def test_render_requires_manifest_schema_and_enumerations():
    projects = [_project(1), _project(2)]
    with pytest.raises(SystemExit, match="schema and enumerations"):
        comparison.render_html(
            projects,
            "2026-06",
            date(2026, 7, 26),
            dataset_revision=DATASET_REVISION,
            project_catalog=_catalog(projects),
        )


def test_render_requires_catalog_with_matching_transaction_revision():
    projects = [_project(1), _project(2)]
    catalog = _catalog(projects)
    catalog["transaction_dataset_revision"] = "c" * 64

    with pytest.raises(SystemExit, match="transaction revision"):
        comparison.render_html(
            projects,
            "2026-06",
            date(2026, 7, 26),
            dataset_revision=DATASET_REVISION,
            transaction_schema=TRANSACTION_SCHEMA,
            transaction_enumerations=TRANSACTION_ENUMERATIONS,
            project_catalog=catalog,
        )


def test_committed_multi_page_meets_bootstrap_budget_and_shares_catalog_url():
    page_path = ROOT / "multi_condo_framework_comparison.html"
    page = page_path.read_text(encoding="utf-8")
    options = page.split('<datalist id="project-options">', 1)[1].split(
        "</datalist>", 1
    )[0]
    catalog_path = re.search(
        r'"path":"(assets/project-catalog/[0-9a-f]{64}/catalog\.json)"',
        page,
    )
    exit_payload = json.loads(
        re.search(
            r'<script id="project-exit-data" type="application/json">(.*?)</script>',
            (ROOT / "project_exit_comparison.html").read_text(encoding="utf-8"),
        ).group(1)
    )

    assert page_path.stat().st_size <= 500 * 1024
    assert options.count("<option ") == 3
    assert catalog_path
    assert catalog_path.group(1) == exit_payload["catalog"]["path"]
