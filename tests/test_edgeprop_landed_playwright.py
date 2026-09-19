from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scrapers import edgeprop_landed_playwright as landed
from sg_estate import scrape_generation
from sg_estate.contracts import ContractError


NOW = datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)


class FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


@asynccontextmanager
async def fake_page_factory(_args):
    yield FakePage()


def write_catalog(path: Path, projects: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "url", "slug"])
        writer.writeheader()
        writer.writerows(projects)


def project(slug: str) -> dict[str, str]:
    return {
        "name": f"Project {slug.upper()}",
        "url": f"https://www.edgeprop.sg/landed-house/{slug}",
        "slug": slug,
    }


def transaction_row(source: dict[str, str], *, sale_date: str = "7 Oct 2020") -> dict[str, object]:
    return {
        "Project": source["name"],
        "planning_area": "BEDOK",
        "Postal District": "14",
        "Date of Sale": sale_date,
        "Street": "XX TEST ROAD",
        "Unit Price ($psf)": 965,
        "Price ($)": 3_760_000,
        "Type": "Terrace House",
        "Tenure": "Freehold",
        "Sale Type": "Resale",
        "Area (sqft)": 3_895,
        "Area (sqm)": 361.857,
        "Type of Area": "Land",
        "Purchaser Address": "Private",
        "Source": "URA",
        "source_quality": "not_clean",
        "source_url": source["url"],
        "source_slug": source["slug"],
    }


def success(source: dict[str, str], *, pages: int = 1) -> landed.ScrapeResult:
    return landed.ScrapeResult(
        rows=[transaction_row(source)],
        pages_scraped=pages,
        completion_reason=landed.TERMINAL_COMPLETION,
        source_reported_row_count=1,
    )


def arguments(
    tmp_path: Path,
    catalog: Path,
    *,
    generation_id: str = "landed-generation-one",
    max_pages: int = 200,
) -> argparse.Namespace:
    return argparse.Namespace(
        input=str(catalog),
        out="candidate.csv",
        generation_manifest=str(tmp_path / "generation" / "manifest.json"),
        generation_id=generation_id,
        limit=None,
        start=0,
        match=None,
        resume=False,
        resume_attempts=False,
        log=None,
        wait_ms=0,
        timeout_ms=1_000,
        max_pages=max_pages,
        delay=0,
        headed=False,
    )


@pytest.mark.asyncio
async def test_new_generation_captures_exact_resolved_scope_and_catalog(tmp_path: Path) -> None:
    projects = [project("alpha"), project("bravo"), project("charlie")]
    catalog = tmp_path / "landed-projects.csv"
    write_catalog(catalog, projects)
    args = arguments(tmp_path, catalog, max_pages=17)
    args.match = "a"
    args.start = 1
    args.limit = 1
    called: list[str] = []

    async def scraper(_page, source, **_kwargs):
        called.append(source["slug"])
        return success(source)

    manifest = await landed.run(
        args,
        project_scraper=scraper,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )

    assert manifest["status"] == "complete"
    assert called == ["bravo"]
    scope = manifest["requested_scope"]
    assert scope["project_catalog"] == {
        "name": catalog.name,
        "sha256": scrape_generation.sha256_file(catalog),
    }
    assert scope["parameters"] == {
        "artifact_schema": landed.ARTIFACT_SCHEMA,
        "max_pages": 17,
    }
    assert scope["partitions"] == [
        {
            "partition_id": landed.partition_id_for_url(projects[1]["url"]),
            "name": projects[1]["name"],
            "source_url": projects[1]["url"],
            "source_slug": projects[1]["slug"],
        }
    ]
    assert landed.partition_id_for_url("HTTPS://WWW.EDGEPROP.SG/landed-house/bravo#top") == (
        landed.partition_id_for_url(projects[1]["url"])
    )


@pytest.mark.asyncio
async def test_resume_retries_failure_and_skips_only_selected_success(tmp_path: Path) -> None:
    projects = [project("alpha"), project("bravo")]
    catalog = tmp_path / "landed-projects.csv"
    write_catalog(catalog, projects)
    args = arguments(tmp_path, catalog)
    candidate = tmp_path / "generation" / "candidate.csv"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("prior-candidate\n", encoding="utf-8")
    first_calls: list[str] = []

    async def first_scraper(_page, source, **_kwargs):
        first_calls.append(source["slug"])
        if source["slug"] == "bravo":
            return landed.ScrapeResult(
                rows=[],
                pages_scraped=1,
                completion_reason="zero_rows",
                error_message="no parseable rows",
            )
        return success(source)

    first = await landed.run(
        args,
        project_scraper=first_scraper,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )

    assert first["status"] == "open"
    assert first_calls == ["alpha", "bravo"]
    assert candidate.read_text(encoding="utf-8") == "prior-candidate\n"
    second_calls: list[str] = []

    async def second_scraper(_page, source, **_kwargs):
        second_calls.append(source["slug"])
        return success(source)

    second = await landed.run(
        args,
        project_scraper=second_scraper,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )

    assert second["status"] == "complete"
    assert second_calls == ["bravo"]
    attempts = {
        value["partition_id"]: [attempt["status"] for attempt in value["attempts"]]
        for value in second["partitions"]
    }
    assert attempts[landed.partition_id_for_url(projects[0]["url"])] == ["succeeded"]
    assert attempts[landed.partition_id_for_url(projects[1]["url"])] == [
        "failed",
        "succeeded",
    ]
    with candidate.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == landed.FIELDS
    assert sorted(row["source_slug"] for row in rows) == ["alpha", "bravo"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        landed.ScrapeResult(rows=[], pages_scraped=1, completion_reason="zero_rows"),
        landed.ScrapeResult(
            rows=[transaction_row(project("alpha"))],
            pages_scraped=2,
            completion_reason="max_pages_exhausted",
        ),
        landed.ScrapeResult(
            rows=[transaction_row(project("alpha"))],
            pages_scraped=1,
            completion_reason="pagination_click_failed",
        ),
        landed.ScrapeResult(
            rows=[transaction_row(project("alpha"))],
            pages_scraped=1,
            completion_reason="pagination_did_not_advance",
        ),
    ],
    ids=["zero", "max-pages", "click", "did-not-advance"],
)
async def test_partial_or_zero_results_remain_pending(
    tmp_path: Path,
    outcome: landed.ScrapeResult,
) -> None:
    catalog = tmp_path / "landed-projects.csv"
    source = project("alpha")
    write_catalog(catalog, [source])
    args = arguments(tmp_path, catalog)

    async def scraper(_page, _source, **_kwargs):
        return outcome

    manifest = await landed.run(
        args,
        project_scraper=scraper,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )

    assert manifest["status"] == "open"
    assert manifest["summary"] == {
        "requested": 1,
        "selected": 0,
        "succeeded": 0,
        "confirmed_empty": 0,
        "failed": 1,
        "pending": 1,
    }
    attempt = manifest["partitions"][0]["attempts"][0]
    assert attempt["status"] == "failed"
    assert attempt["artifact"] is None
    assert attempt["observations"]["parsed_row_count"] == len(outcome.rows)
    assert not (tmp_path / "generation" / "candidate.csv").exists()


@pytest.mark.asyncio
async def test_exception_and_artifact_provenance_mismatch_do_not_publish(tmp_path: Path) -> None:
    catalog = tmp_path / "landed-projects.csv"
    source = project("alpha")
    write_catalog(catalog, [source])
    args = arguments(tmp_path, catalog)

    async def raises(_page, _source, **_kwargs):
        raise RuntimeError("navigation failed")

    first = await landed.run(
        args,
        project_scraper=raises,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )
    assert first["partitions"][0]["attempts"][0]["error_code"] == "project_scrape_error"

    async def wrong_provenance(_page, _source, **_kwargs):
        row = transaction_row(source)
        row["source_url"] = "https://www.edgeprop.sg/landed-house/not-alpha"
        return landed.ScrapeResult(
            rows=[row],
            pages_scraped=1,
            completion_reason=landed.TERMINAL_COMPLETION,
            source_reported_row_count=1,
        )

    second = await landed.run(
        args,
        project_scraper=wrong_provenance,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )
    assert [attempt["status"] for attempt in second["partitions"][0]["attempts"]] == [
        "failed",
        "failed",
    ]
    assert not list((tmp_path / "generation" / "artifacts").rglob("*.csv"))


@pytest.mark.asyncio
async def test_orphaned_attempt_artifact_is_immutable_and_retry_uses_new_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = tmp_path / "landed-projects.csv"
    source = project("alpha")
    write_catalog(catalog, [source])
    args = arguments(tmp_path, catalog)

    async def scraper(_page, selected, **_kwargs):
        return success(selected)

    real_record_attempt = landed.scrape_generation.record_attempt

    def crash_before_checkpoint(*_args, **_kwargs):
        raise RuntimeError("simulated crash before manifest append")

    monkeypatch.setattr(
        landed.scrape_generation,
        "record_attempt",
        crash_before_checkpoint,
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        await landed.run(
            args,
            project_scraper=scraper,
            page_factory=fake_page_factory,
            now=lambda: NOW,
        )

    artifacts_root = tmp_path / "generation" / "artifacts"
    orphaned = list(artifacts_root.rglob("*.csv"))
    assert len(orphaned) == 1
    orphaned_bytes = orphaned[0].read_bytes()
    manifest = scrape_generation.load_generation(args.generation_manifest)
    assert manifest["summary"]["pending"] == 1
    assert manifest["partitions"][0]["attempts"] == []

    monkeypatch.setattr(
        landed.scrape_generation,
        "record_attempt",
        real_record_attempt,
    )
    completed = await landed.run(
        args,
        project_scraper=scraper,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )

    artifacts = list(artifacts_root.rglob("*.csv"))
    assert completed["status"] == "complete"
    assert len(artifacts) == 2
    assert orphaned[0].read_bytes() == orphaned_bytes
    selected = completed["partitions"][0]["attempts"][0]
    selected_path = (
        Path(args.generation_manifest).parent
        / selected["artifact"]["relative_path"]
    ).resolve()
    assert selected["attempt_id"] == selected_path.stem
    assert selected_path != orphaned[0].resolve()


@pytest.mark.asyncio
async def test_scope_or_generation_mismatch_preserves_manifest_and_candidate(tmp_path: Path) -> None:
    catalog = tmp_path / "landed-projects.csv"
    source = project("alpha")
    write_catalog(catalog, [source])
    args = arguments(tmp_path, catalog)

    async def incomplete(_page, _source, **_kwargs):
        return landed.ScrapeResult(rows=[], completion_reason="zero_rows")

    await landed.run(
        args,
        project_scraper=incomplete,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )
    manifest_path = Path(args.generation_manifest)
    candidate = manifest_path.parent / "candidate.csv"
    candidate.write_text("previous\n", encoding="utf-8")
    before_manifest = manifest_path.read_bytes()
    before_candidate = candidate.read_bytes()

    changed_scope = arguments(tmp_path, catalog, max_pages=201)
    with pytest.raises(ContractError, match="requested_scope"):
        await landed.run(
            changed_scope,
            project_scraper=incomplete,
            page_factory=fake_page_factory,
            now=lambda: NOW,
        )
    assert manifest_path.read_bytes() == before_manifest
    assert candidate.read_bytes() == before_candidate

    changed_generation = arguments(tmp_path, catalog, generation_id="different-generation")
    with pytest.raises(ContractError, match="generation_id"):
        await landed.run(
            changed_generation,
            project_scraper=incomplete,
            page_factory=fake_page_factory,
            now=lambda: NOW,
        )
    assert manifest_path.read_bytes() == before_manifest
    assert candidate.read_bytes() == before_candidate


@pytest.mark.asyncio
async def test_candidate_is_exact_deterministic_and_contains_each_artifact_once(tmp_path: Path) -> None:
    projects = [project("charlie"), project("alpha"), project("bravo")]
    catalog = tmp_path / "landed-projects.csv"
    write_catalog(catalog, projects)
    args = arguments(tmp_path, catalog)

    async def scraper(_page, source, **_kwargs):
        return success(source)

    manifest = await landed.run(
        args,
        project_scraper=scraper,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )
    candidate = tmp_path / "generation" / "candidate.csv"
    before = candidate.read_bytes()
    duplicate_build = tmp_path / "generation" / "candidate-again.csv"
    landed.merge_generation_candidate(Path(args.generation_manifest), duplicate_build)

    assert manifest["status"] == "complete"
    assert duplicate_build.read_bytes() == before
    with candidate.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == landed.FIELDS
    assert len(rows) == len(projects)
    assert sorted(row["source_slug"] for row in rows) == ["alpha", "bravo", "charlie"]
    assert manifest["output"]["row_count"] == len(projects)

    calls = 0

    async def must_not_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("complete generation must not scrape")

    resumed = await landed.run(
        args,
        project_scraper=must_not_run,
        page_factory=fake_page_factory,
        now=lambda: NOW,
    )
    assert resumed == manifest
    assert calls == 0
    assert candidate.read_bytes() == before


def test_resume_attempts_is_rejected_and_playwright_import_is_optional(tmp_path: Path) -> None:
    catalog = tmp_path / "landed-projects.csv"
    write_catalog(catalog, [project("alpha")])
    args = arguments(tmp_path, catalog)
    args.resume_attempts = True

    with pytest.raises(ValueError, match="unsafe and unsupported"):
        import asyncio

        asyncio.run(
            landed.run(
                args,
                project_scraper=lambda *_args, **_kwargs: None,
                page_factory=fake_page_factory,
                now=lambda: NOW,
            )
        )

    assert landed.PlaywrightTimeoutError is not None


@pytest.mark.asyncio
async def test_command_boundary_errors_clearly_when_playwright_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = tmp_path / "landed-projects.csv"
    write_catalog(catalog, [project("alpha")])
    args = arguments(tmp_path, catalog)
    monkeypatch.setattr(landed, "async_playwright", None)

    with pytest.raises(RuntimeError, match="Playwright is unavailable"):
        await landed.run(args, now=lambda: NOW)


def test_validated_artifact_rejects_wrong_header_and_provenance(tmp_path: Path) -> None:
    source = project("alpha")
    bad_header = tmp_path / "bad-header.csv"
    bad_header.write_text("source_url,source_slug\nurl,slug\n", encoding="utf-8")
    with pytest.raises(ContractError, match="exact FIELDS header"):
        landed.read_validated_artifact(
            bad_header,
            source_url=source["url"],
            source_slug=source["slug"],
        )

    wrong = transaction_row(source)
    wrong["source_slug"] = "wrong"
    wrong_path = tmp_path / "wrong.csv"
    with wrong_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=landed.FIELDS)
        writer.writeheader()
        writer.writerow(wrong)
    with pytest.raises(ContractError, match="source_slug"):
        landed.read_validated_artifact(
            wrong_path,
            source_url=source["url"],
            source_slug=source["slug"],
        )


def test_mixed_source_manifest_is_rejected(tmp_path: Path) -> None:
    catalog = tmp_path / "landed-projects.csv"
    source = project("alpha")
    write_catalog(catalog, [source])
    args = arguments(tmp_path, catalog)
    scope = landed.requested_scope(catalog, [source], max_pages=args.max_pages)
    manifest = scrape_generation.new_generation(
        "edgeprop_condo_apartment",
        scope,
        generation_id=args.generation_id,
        now=NOW,
    )
    manifest_path = Path(args.generation_manifest)
    scrape_generation.write_generation(manifest_path, manifest)
    before = json.loads(manifest_path.read_text(encoding="utf-8"))

    with pytest.raises(ContractError, match="expected source"):
        import asyncio

        asyncio.run(
            landed.run(
                args,
                project_scraper=lambda *_args, **_kwargs: None,
                page_factory=fake_page_factory,
                now=lambda: NOW,
            )
        )
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == before


def test_direct_script_help_bootstraps_repository_imports(tmp_path: Path) -> None:
    script = Path(landed.__file__).resolve()
    completed = subprocess.run(
        (sys.executable, str(script), "--help"),
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--generation-manifest" in completed.stdout
    assert "ModuleNotFoundError" not in completed.stderr
