"""The frozen source package is deterministic and excludes preview/session files."""
import json
from zipfile import ZipFile

import pytest

from scripts.package_property_research import package, selected_files


def test_packaging_preserves_csv_bytes_and_excludes_local_artifacts(tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    required = ["transactions.csv", "transactions_original_fields.csv", "projects.csv", "cohorts.csv", "provenance.json", "enrichment/individual_editorial_notes.json", "enrichment/individual_project_profiles.json"]
    for name in required:
        path = batch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}" if path.suffix == ".json" else b'"name","value"\r\n"same","1"\r\n"same","1"\r\n')
    (batch / "individual_report_manifest.json").write_text(json.dumps({"reports": [{}] * 553, "future_site_reports": [{}] * 4}))
    for name in ["report.html", "report_data.json", "storage-state.json", "enrichment/credentials.json", "raw/storage_state.json", "reference/page.html", "program.py"]:
        path = batch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not evidence")
    paths = {p.relative_to(batch).as_posix() for p in selected_files(batch)}
    assert paths == set(required) | {"individual_report_manifest.json"}
    first, second = tmp_path / "one.zip", tmp_path / "two.zip"
    package(batch, first)
    package(batch, second)
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        assert archive.read("transactions.csv") == (batch / "transactions.csv").read_bytes()
        manifest = json.loads(archive.read("package_manifest.json"))
        assert len(manifest["files"]) == len(paths)
        assert all(len(row["sha256"]) == 64 for row in manifest["files"])
        restored = tmp_path / "restored"
        archive.extractall(restored)
    roundtrip = tmp_path / "roundtrip.zip"
    package(restored, roundtrip)
    assert roundtrip.read_bytes() == first.read_bytes()


def test_incomplete_research_package_fails_before_writing(tmp_path):
    with pytest.raises(ValueError, match="Missing frozen evidence"):
        package(tmp_path, tmp_path / "invalid.zip")
    assert not (tmp_path / "invalid.zip").exists()
