import asyncio
from argparse import Namespace
import json
from pathlib import Path
from types import SimpleNamespace

from scrapers import ingest_ura_raw, run_download
from scrapers import ura_pmi_api as api
from scrapers import ura_pmi_playwright as playwright
from sg_estate import scrape_generation


STAMP = "2026-08-13T00:00:00+00:00"


def _api_project(*, district: str, property_type: str, project: str) -> dict:
    return {
        "project": project,
        "street": "TEST ROAD",
        "marketSegment": "OCR",
        "transaction": [
            {
                "propertyType": property_type,
                "district": district,
                "price": "1200000",
                "area": "80",
                "contractDate": "0626",
                "tenure": "Freehold",
                "typeOfSale": "3",
                "typeOfArea": (
                    "Land" if property_type == "Terrace House" else "Strata"
                ),
                "noOfUnits": "1",
            }
        ],
    }


def _api_args(tmp_path: Path) -> Namespace:
    return Namespace(
        out_dir=str(tmp_path),
        attempt_manifest=str(tmp_path / "api-attempts.json"),
        districts=["15", "16"],
        prop_types=["1", "3"],
        year_from="2026",
        month_from="6",
        year_to="2026",
        month_to="6",
    )


def test_api_requires_all_four_batches_before_writing_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "get_access_key", lambda: "test-key")
    monkeypatch.setattr(api, "generate_token", lambda _key, _session: "test-token")

    def fake_fetch(_key, _token, batch, _session):
        if batch == 1:
            return {
                "Status": "Success",
                "Result": [
                    _api_project(
                        district="15", property_type="Condominium", project="D15 CONDO"
                    ),
                    _api_project(
                        district="16", property_type="Terrace House", project="D16 HOUSE"
                    ),
                ],
            }
        if batch == 2:
            raise RuntimeError("fixture batch failure")
        raise AssertionError("later API batches must not run after failure")

    monkeypatch.setattr(api, "fetch_transactions", fake_fetch)

    manifest = api.run(_api_args(tmp_path), session=object(), sleep=lambda _seconds: None)

    assert manifest["status"] == "failed"
    assert manifest["summary"] == {
        "requested": 4,
        "succeeded": 0,
        "confirmed_empty": 0,
        "failed": 4,
    }
    assert [request["status"] for request in manifest["source_requests"]] == [
        "succeeded",
        "failed",
        "failed",
        "failed",
    ]
    assert all(
        attempt["error_code"] == "incomplete_api_batches"
        for attempt in manifest["attempts"]
    )
    assert not list(tmp_path.glob("pmi_api_*.csv"))
    assert json.loads((tmp_path / "api-attempts.json").read_text()) == manifest


def test_api_emits_one_terminal_attempt_per_requested_partition(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "get_access_key", lambda: "test-key")
    monkeypatch.setattr(api, "generate_token", lambda _key, _session: "test-token")

    def fake_fetch(_key, _token, batch, _session):
        result = []
        if batch == 1:
            result = [
                _api_project(
                    district="15", property_type="Condominium", project="D15 CONDO"
                ),
                _api_project(
                    district="16", property_type="Terrace House", project="D16 HOUSE"
                ),
            ]
        return {"Status": "Success", "Result": result}

    monkeypatch.setattr(api, "fetch_transactions", fake_fetch)

    args = _api_args(tmp_path)
    args.out_dir = str(tmp_path / "raw")
    manifest = api.run(args, session=object(), sleep=lambda _seconds: None)

    assert manifest["status"] == "succeeded"
    assert manifest["requested_scope"] == {
        "districts": ["15", "16"],
        "property_types": ["1", "3"],
        "sale_types": ["1", "2", "3"],
        "year_from": "2026",
        "month_from": "6",
        "year_to": "2026",
        "month_to": "6",
    }
    assert len(manifest["source_requests"]) == 4
    assert {attempt["partition_id"] for attempt in manifest["attempts"]} == {
        "d15-p1",
        "d15-p3",
        "d16-p1",
        "d16-p3",
    }
    status = {
        attempt["partition_id"]: attempt["status"]
        for attempt in manifest["attempts"]
    }
    assert status == {
        "d15-p1": "confirmed_empty",
        "d15-p3": "succeeded",
        "d16-p1": "succeeded",
        "d16-p3": "confirmed_empty",
    }
    for attempt in manifest["attempts"]:
        artifact = attempt["artifact"]
        if attempt["status"] == "succeeded":
            assert artifact["row_count"] == 1
            assert artifact["byte_count"] > 0
            assert len(artifact["sha256"]) == 64
            assert artifact["relative_path"].startswith("raw/")
            assert (tmp_path / artifact["relative_path"]).is_file()
        else:
            assert artifact is None
            assert attempt["observations"] == {"row_count": 0}

    candidate, metadata = ingest_ura_raw.build_complete_candidate(
        tmp_path / "api-attempts.json"
    )
    assert len(candidate) == 2
    assert metadata["request"]["coverage_start"] == "2026-06"
    assert metadata["request"]["coverage_end"] == "2026-06"
    assert metadata["reconciliation"]["district_counts"] == {"15": 1, "16": 1}
    assert metadata["reconciliation"]["property_type_counts"] == {"1": 1, "3": 1}


def test_api_rejects_unproven_requested_date_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "get_access_key", lambda: "test-key")
    monkeypatch.setattr(api, "generate_token", lambda _key, _session: "test-token")
    monkeypatch.setattr(
        api,
        "fetch_transactions",
        lambda _key, _token, _batch, _session: {
            "Status": "Success",
            "Result": [
                _api_project(
                    district="15", property_type="Condominium", project="D15 CONDO"
                )
            ],
        },
    )
    args = _api_args(tmp_path)
    args.month_from = "5"

    manifest = api.run(args, session=object(), sleep=lambda _seconds: None)

    assert manifest["status"] == "failed"
    assert all(
        attempt["error_code"] == "unsupported_api_date_scope"
        for attempt in manifest["attempts"]
    )
    assert not list(tmp_path.glob("pmi_api_*.csv"))


class _FakeBrowser:
    async def new_context(self, **_kwargs):
        return self

    async def new_page(self):
        return object()

    async def close(self):
        return None


class _FakeChromium:
    async def launch(self, **_kwargs):
        return _FakeBrowser()


class _FakePlaywrightManager:
    async def __aenter__(self):
        return SimpleNamespace(chromium=_FakeChromium())

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


def _playwright_args(tmp_path: Path) -> Namespace:
    return Namespace(
        out_dir=str(tmp_path / "raw"),
        attempt_manifest=str(tmp_path / "playwright-attempts.json"),
        districts=["15", "16"],
        prop_types=["1", "3"],
        prop_type="3",
        year_from="2021",
        month_from="1",
        year_to="2026",
        month_to="12",
        sale_type=[],
        headed=False,
        timeout=1,
    )


def test_playwright_manifest_records_failed_partition_and_fails_run(
    monkeypatch, tmp_path
):
    async def fake_download(**kwargs):
        district = kwargs["district"]
        prop_type = kwargs["prop_type"]
        status = "failed" if (district, prop_type) == ("16", "3") else "confirmed_empty"
        return playwright.new_attempt(
            district=district,
            prop_type=prop_type,
            method="playwright",
            status=status,
            started_at=STAMP,
            completed_at=STAMP,
            observations={"row_count": 0} if status == "confirmed_empty" else None,
            error_code="fixture_failure" if status == "failed" else None,
            error_message="fixture failed" if status == "failed" else None,
        )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(playwright, "download_district", fake_download)
    monkeypatch.setattr(playwright.asyncio, "sleep", no_sleep)

    manifest = asyncio.run(
        playwright.run(
            _playwright_args(tmp_path),
            playwright_factory=lambda: _FakePlaywrightManager(),
        )
    )

    assert manifest["status"] == "failed"
    assert manifest["summary"] == {
        "requested": 4,
        "succeeded": 0,
        "confirmed_empty": 3,
        "failed": 1,
    }
    assert len(manifest["attempts"]) == 4
    assert json.loads((tmp_path / "playwright-attempts.json").read_text()) == manifest


def test_partial_month_or_sale_type_uses_scoped_filename():
    assert playwright.scoped_raw_filename(
        "15", "2021", "2", "2026", "11", "3", ["3"]
    ) == "pmi_d15_2021-2026_m02-11_sale-3.csv"
    assert playwright.scoped_raw_filename(
        "15", "2021", "1", "2026", "12", "3", []
    ) == "pmi_d15_2021-2026.csv"


def test_downloader_cli_exit_codes_follow_manifest_status(monkeypatch, tmp_path):
    async def failed_playwright(_args):
        return {"status": "failed"}

    monkeypatch.setattr(playwright, "run", failed_playwright)
    assert playwright.main(["--districts", "15", "--out_dir", str(tmp_path)]) == 1

    monkeypatch.setattr(api, "run", lambda _args: {"status": "failed"})
    assert api.main(["--districts", "15", "--out_dir", str(tmp_path)]) == 1


def test_orchestrator_retries_unverified_existing_file_and_propagates_failure(
    monkeypatch, tmp_path
):
    existing = tmp_path / "pmi_d15_2021-2026.csv"
    existing.write_text("existing,unverified\n", encoding="utf-8")
    captured = {}

    def fake_playwright(districts, year_from, year_to, out_dir, prop_types, manifest):
        captured["districts"] = districts
        captured["manifest"] = manifest
        return False

    monkeypatch.setattr(run_download, "run_playwright_subprocess", fake_playwright)

    exit_code = run_download.main(
        [
            "--mode",
            "playwright",
            "--districts",
            "15",
            "--out_dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 1
    assert captured["districts"] == ["15"]
    assert captured["manifest"] == tmp_path / "ura_pmi_attempts.json"
    assert existing.read_text(encoding="utf-8") == "existing,unverified\n"


def _write_child_manifest(
    path: Path,
    *,
    method: str,
    status: str,
    districts: list[str] | None = None,
    prop_types: list[str] | None = None,
) -> dict:
    districts = districts or ["15"]
    prop_types = prop_types or ["3"]
    attempts = [
        playwright.new_attempt(
            district=district,
            prop_type=prop_type,
            method=method,
            status=status,
            started_at=STAMP,
            completed_at=STAMP,
            observations={"row_count": 0} if status == "confirmed_empty" else None,
            error_code="fixture_failure" if status == "failed" else None,
            error_message="fixture failed" if status == "failed" else None,
        )
        for district in districts
        for prop_type in prop_types
    ]
    manifest = playwright.build_attempt_manifest(
        method=method,
        started_at=STAMP,
        completed_at=STAMP,
        districts=districts,
        prop_types=prop_types,
        year_from="2025",
        month_from="1",
        year_to="2025",
        month_to="12",
        sale_types=["1", "2", "3"],
        attempts=attempts,
    )
    playwright.atomic_write_json(path, manifest)
    return manifest


def test_both_mode_selects_only_complete_exact_scope_api_fallback(
    monkeypatch, tmp_path
):
    raw_dir = tmp_path / "raw"
    selected = tmp_path / "attempts.json"
    calls = {}

    def fake_playwright(_districts, _yf, _yt, _out, _types, manifest):
        _write_child_manifest(manifest, method="playwright", status="failed")
        return False

    def fake_api(out_dir, prop_types, districts, manifest, year_from, year_to):
        calls["api"] = (out_dir, prop_types, districts, year_from, year_to)
        _write_child_manifest(manifest, method="api", status="confirmed_empty")
        return True

    monkeypatch.setattr(run_download, "run_playwright_subprocess", fake_playwright)
    monkeypatch.setattr(run_download, "run_api_subprocess", fake_api)

    exit_code = run_download.main(
        [
            "--mode",
            "both",
            "--districts",
            "15",
            "--year_from",
            "2025",
            "--year_to",
            "2025",
            "--out_dir",
            str(raw_dir),
            "--attempt-manifest",
            str(selected),
        ]
    )

    assert exit_code == 0
    assert calls["api"] == (raw_dir, ["3"], ["15"], "2025", "2025")
    assert json.loads(selected.read_text())["method"] == "api"
    assert json.loads(selected.read_text())["status"] == "succeeded"
    assert selected.with_name("attempts.playwright.json").is_file()
    assert selected.with_name("attempts.api.json").is_file()


def test_orchestrator_rejects_unchanged_stale_child_manifest(monkeypatch, tmp_path):
    selected = tmp_path / "attempts.json"
    _write_child_manifest(selected, method="playwright", status="confirmed_empty")

    monkeypatch.setattr(
        run_download,
        "run_playwright_subprocess",
        lambda *_args: True,
    )

    exit_code = run_download.main(
        [
            "--mode",
            "playwright",
            "--districts",
            "15",
            "--year_from",
            "2025",
            "--year_to",
            "2025",
            "--out_dir",
            str(tmp_path),
            "--attempt-manifest",
            str(selected),
        ]
    )

    replaced = json.loads(selected.read_text())
    assert exit_code == 1
    assert replaced["status"] == "failed"
    assert replaced["attempts"][0]["error_code"] == (
        "subprocess_failed_without_manifest"
    )


def test_orchestrator_generation_resume_retries_only_pending_pairs(
    monkeypatch,
    tmp_path,
):
    raw_dir = tmp_path / "raw"
    selected = tmp_path / "attempts.json"
    calls = []

    def fake_playwright(districts, year_from, year_to, out_dir, prop_types, manifest):
        calls.append((list(districts), list(prop_types)))
        stamp = playwright.utc_now()
        attempts = []
        for district in districts:
            for prop_type in prop_types:
                succeeds = district == "15" or len(calls) > 1
                artifact = None
                observations = None
                if succeeds:
                    artifact_path = out_dir / f"current-d{district}-p{prop_type}.csv"
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    artifact_path.write_text("value\ncurrent\n", encoding="utf-8")
                    artifact = playwright.artifact_metadata(
                        artifact_path,
                        relative_to=manifest.parent,
                    )
                    observations = {"row_count": 1}
                attempts.append(
                    playwright.new_attempt(
                        district=district,
                        prop_type=prop_type,
                        method="playwright",
                        status="succeeded" if succeeds else "failed",
                        started_at=stamp,
                        completed_at=playwright.utc_now(),
                        artifact=artifact,
                        observations=observations,
                        error_code=None if succeeds else "fixture_failure",
                        error_message=None if succeeds else "fixture failed",
                    )
                )
        child = playwright.build_attempt_manifest(
            method="playwright",
            started_at=stamp,
            completed_at=playwright.utc_now(),
            districts=districts,
            prop_types=prop_types,
            year_from=year_from,
            month_from="1",
            year_to=year_to,
            month_to="12",
            sale_types=["1", "2", "3"],
            attempts=attempts,
        )
        playwright.atomic_write_json(manifest, child)
        return child["status"] == "succeeded"

    monkeypatch.setattr(run_download, "run_playwright_subprocess", fake_playwright)
    argv = [
        "--mode",
        "playwright",
        "--districts",
        "15",
        "16",
        "--year_from",
        "2025",
        "--year_to",
        "2025",
        "--out_dir",
        str(raw_dir),
        "--attempt-manifest",
        str(selected),
        "--generation-id",
        "ura-resume-fixture",
    ]

    assert run_download.main(argv) == 1
    assert calls == [(["15", "16"], ["3"])]
    assert run_download.main(argv) == 0
    assert calls == [(["15", "16"], ["3"]), (["16"], ["3"])]

    generation_path = tmp_path / "attempts.generation.json"
    generation = scrape_generation.load_generation(
        generation_path,
        expected_generation_id="ura-resume-fixture",
    )
    histories = {
        partition["partition_id"]: [
            attempt["status"] for attempt in partition["attempts"]
        ]
        for partition in generation["partitions"]
    }
    assert histories == {
        "d15-p3": ["succeeded"],
        "d16-p3": ["failed", "succeeded"],
    }
    assert generation["summary"]["pending"] == 0
    snapshot = json.loads(selected.read_text(encoding="utf-8"))
    assert snapshot["status"] == "succeeded"
    assert [attempt["partition_id"] for attempt in snapshot["attempts"]] == [
        "d15-p3",
        "d16-p3",
    ]
