"""Tests for the interactive two-to-five-condominium comparison."""

from datetime import date

import pytest

import gen_condo_framework_comparison_html as two_project
import gen_multi_condo_framework_comparison_html as comparison


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
    page = comparison.render_html(
        [_project(index) for index in range(1, 6)],
        "2026-06",
        date(2026, 7, 26),
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
    assert "fetchTransactionShard" in page
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
