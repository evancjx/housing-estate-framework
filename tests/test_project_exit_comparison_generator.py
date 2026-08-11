"""Generator and committed-data guards for the project exit decision lab."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import sys


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
    project_ids = [project["id"] for project in payload["projects"]]

    assert payload["schema"] == "project-exit-comparison.v1"
    assert payload["limits"] == {"min_projects": 2, "max_projects": 5}
    assert len(project_ids) > 2_000
    assert len(project_ids) == len(set(project_ids))
    assert set(project_ids) <= set(manifest["projects"])
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


def test_committed_page_matches_fresh_generation_without_rewriting_shards(
    tmp_path: Path,
) -> None:
    payload = _committed_payload()
    manifest_before = report.DEFAULT_MANIFEST.read_bytes()
    shard_before = (report.DEFAULT_MANIFEST.parent / "shard-00.json").read_bytes()
    output = tmp_path / "project_exit_comparison.html"

    report.generate(output, as_of=payload["generated_as_of"])

    assert output.read_bytes() == report.DEFAULT_OUT.read_bytes()
    assert report.DEFAULT_MANIFEST.read_bytes() == manifest_before
    assert (report.DEFAULT_MANIFEST.parent / "shard-00.json").read_bytes() == shard_before


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
