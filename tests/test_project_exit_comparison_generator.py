"""Generator and committed-data guards for the project exit decision lab."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
if str(MODELS) not in sys.path:
    sys.path.insert(0, str(MODELS))

import gen_project_exit_comparison_html as report  # noqa: E402


class _PayloadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("id") == "project-exit-data":
            self.capture = True

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.capture:
            self.capture = False


def _committed_payload() -> dict:
    parser = _PayloadParser()
    parser.feed(report.DEFAULT_OUT.read_text(encoding="utf-8"))
    return json.loads("".join(parser.parts))


def test_committed_payload_reconciles_to_transaction_manifest() -> None:
    payload = _committed_payload()
    manifest = report.load_transaction_manifest()
    catalog = report.private_project_catalog.load_project_catalog(
        report.DEFAULT_PROJECT_CATALOG,
        transaction_manifest=manifest,
    )
    project_ids = [project["id"] for project in payload["projects"]]

    assert payload["schema"] == "project-exit-comparison.v1"
    assert payload["dataset_revision"] == manifest["dataset_revision"]
    assert payload["limits"] == {"min_projects": 2, "max_projects": 5}
    assert project_ids == payload["defaults"]
    assert len(project_ids) == 3
    assert len(project_ids) == len(set(project_ids))
    assert len(catalog["projects"]) > 2_000
    assert set(project_ids) <= set(manifest["projects"])
    assert payload["catalog"] == {
        "path": report.private_project_catalog.catalog_asset_path(
            catalog["catalog_revision"]
        ),
        "revision": catalog["catalog_revision"],
        "schema": catalog["schema"],
    }
    assert set(payload["defaults"]) <= set(project_ids)
    assert payload["source_metadata"] == manifest["source_metadata"]
    assert payload["transaction_schema"] == manifest["schema"]
    assert payload["transaction_enumerations"] == manifest["enumerations"]
    assert payload["source_metadata"]["reconciliation"]["matches"] is True

    for project in payload["projects"]:
        transaction = manifest["projects"][project["id"]]
        assert project["transaction_shard"] == transaction["transaction_shard"]
        assert project["transaction_count"] == transaction["transaction_count"]
        assert project["transaction_complete_through"] == transaction[
            "transaction_complete_through"
        ]
        assert project["capabilities"]["project_exit"] is True


@pytest.mark.parametrize("revision", [None, "", "A" * 64, "a" * 63, "g" * 64])
def test_manifest_rejects_missing_or_non_sha256_dataset_revision(
    tmp_path: Path, revision: str | None
) -> None:
    manifest = {
        "schema": {},
        "enumerations": {},
        "source_metadata": {},
        "projects": {},
    }
    if revision is not None:
        manifest["dataset_revision"] = revision
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="dataset_revision"):
        report.load_transaction_manifest(path)


def test_committed_page_matches_fresh_generation_without_rewriting_shards(
    tmp_path: Path,
) -> None:
    payload = _committed_payload()
    manifest_before = report.DEFAULT_MANIFEST.read_bytes()
    manifest = report.load_transaction_manifest()
    sample_shard = ROOT / "site" / next(iter(manifest["projects"].values()))[
        "transaction_shard"
    ]
    shard_before = sample_shard.read_bytes()
    output = tmp_path / "project_exit_comparison.html"

    report.generate(output, as_of=payload["generated_as_of"])

    assert output.read_bytes() == report.DEFAULT_OUT.read_bytes()
    assert report.DEFAULT_MANIFEST.read_bytes() == manifest_before
    assert sample_shard.read_bytes() == shard_before


def test_script_safe_json_cannot_close_its_data_element() -> None:
    encoded = report.script_safe_json({"name": "Example </script> project"})

    assert "</script>" not in encoded.lower()
    assert json.loads(encoded) == {"name": "Example </script> project"}


def test_public_page_attributes_ura_source_licence_and_vintage() -> None:
    page = report.DEFAULT_OUT.read_text(encoding="utf-8")

    assert (
        "https://eservice.ura.gov.sg/property-market-information/"
        "pmiResidentialTransactionSearch"
    ) in page
    assert (
        "https://www.ura.gov.sg/eservices-info/maps/acceptance-grant-licence/"
    ) in page
    assert "URA does not endorse this scenario tool" in page
    assert _committed_payload()["latest_project_month"] in page
