import argparse
import asyncio
import csv
from pathlib import Path

import pytest

from scrapers import edgeprop_condo_apartment_playwright as condo
from sg_estate import scrape_generation
from sg_estate.contracts import ContractError


FIXTURE = Path(__file__).parent / "fixtures/edgeprop/condo_unit_transactions.txt"


class FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


def write_projects(path: Path, projects: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "url", "slug"])
        writer.writeheader()
        for name, slug in projects:
            writer.writerow(
                {
                    "name": name,
                    "url": f"https://www.edgeprop.sg/condo-apartment/{slug}",
                    "slug": slug,
                }
            )


def scrape_args(
    tmp_path: Path,
    *,
    projects: list[tuple[str, str]] | None = None,
    resume: bool = False,
    from_year: int = 2019,
    max_pages: int = 7,
    generation_id: str | None = "condo-test-generation",
) -> argparse.Namespace:
    catalog = tmp_path / "projects.csv"
    if not catalog.exists():
        write_projects(
            catalog,
            projects
            or [
                ("ALPHA RESIDENCES", "alpha-residences"),
                ("MDIS RESIDENCE", "mdis-residence@stirling"),
            ],
        )
    return argparse.Namespace(
        input=str(catalog),
        generation_manifest=str(tmp_path / "generation" / "manifest.json"),
        generation_id=generation_id,
        out="legacy.csv",
        unit_out="units.csv",
        storage_state=None,
        from_year=from_year,
        limit=None,
        start=0,
        match=None,
        resume=resume,
        resume_attempts=False,
        log=None,
        wait_ms=0,
        timeout_ms=100,
        max_pages=max_pages,
        delay=0,
        headed=False,
    )


def transaction_row(project: dict[str, str], *, marker: str = "1") -> dict[str, str]:
    row = {field: "" for field in condo.UNIT_FIELDS}
    row.update(
        {
            "Project": project["name"],
            "planning_area": "TEST",
            "Postal District": "01",
            "Date of Sale": f"{marker} Jan 2026",
            "Address": f"{marker} TEST ROAD #01-01",
            "Street": f"{marker} TEST ROAD",
            "unit_number": "#01-01",
            "unit_floor": "01",
            "unit_stack": "01",
            "unit_number_status": "exact",
            "unit_number_source": "edgeprop_address",
            "Bedrooms": "2",
            "Unit Price ($psf)": "2000",
            "Price ($)": "1000000",
            "Type": "Condominium",
            "Tenure": "Freehold",
            "Sale Type": "Resale",
            "Area (sqft)": "500",
            "Area (sqm)": "46.452",
            "Type of Area": "Strata",
            "Purchaser Address": "Private",
            "Source": "URA",
            "source_quality": "not_clean",
            "source_url": project["url"],
            "source_slug": project["slug"],
        }
    )
    return row


def successful_result(project: dict[str, str], *, marker: str = "1") -> condo.ScrapeResult:
    return condo.ScrapeResult(
        rows=[transaction_row(project, marker=marker)],
        pages_scraped=2,
        oldest_date="2026-01-01",
        completion_reason="terminal_pagination",
        source_advertised_count=1,
    )


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return list(reader.fieldnames or []), rows


def test_discover_project_links_keeps_condo_apartment_detail_pages_only():
    html = """
    <a href="/condo-apartment/all">All</a>
    <a href="/condo-apartment/treasure-at-tampines">TREASURE AT TAMPINES</a>
    <a href="/condo-apartment/treasure-at-tampines">Duplicate</a>
    <a href="/landed-house/kembangan-estate">Not condo</a>
    <a href="https://www.edgeprop.sg/condo-apartment/normanton-park">NORMANTON PARK</a>
    """

    links = condo.discover_project_links(html)

    assert [link.name for link in links] == ["TREASURE AT TAMPINES", "NORMANTON PARK"]
    assert links[0].url == "https://www.edgeprop.sg/condo-apartment/treasure-at-tampines"
    assert links[0].slug == "treasure-at-tampines"


def test_parse_condo_rendered_transaction_text():
    text = """
    Sales Transaction of TREASURE AT TAMPINES
    Date
    Area (sqft)
    Bedrooms
    Price (S$ psf)
    Price (S$)
    Type of Sale
    Address
    Type of Area
    Purchaser Address
    Source
    22 JUN 2026
    840
    3
    1,830
    1,536,500
    Resale
    55 TAMPINES LANE #06-XX
    Strata\tPrivate
    URA
    """

    rows = condo.parse_transaction_text(
        text,
        project_name="TREASURE AT TAMPINES",
        planning_area="Tampines",
        postal_district="18",
        property_type="Condominium",
        tenure="99 yrs from 29/11/2018",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Project"] == "TREASURE AT TAMPINES"
    assert row["planning_area"] == "TAMPINES"
    assert row["Postal District"] == "18"
    assert row["Date of Sale"] == "22 Jun 2026"
    assert row["Address"] == "55 TAMPINES LANE #06-XX"
    assert row["Street"] == "55 TAMPINES LANE"
    assert row["unit_number"] == ""
    assert row["unit_number_status"] == "masked"
    assert row["unit_number_source"] == "edgeprop_address"
    assert row["Bedrooms"] == "3"
    assert row["Unit Price ($psf)"] == 1830
    assert row["Price ($)"] == 1536500
    assert row["Type"] == "Condominium"
    assert row["Tenure"] == "99 yrs from 29/11/2018"
    assert row["Sale Type"] == "Resale"
    assert row["Area (sqft)"] == 840
    assert row["Area (sqm)"] == 78.039
    assert row["Type of Area"] == "Strata"
    assert row["Purchaser Address"] == "Private"
    assert row["Source"] == "URA"


def test_parse_condo_transaction_text_with_separate_area_and_buyer_lines():
    text = """
    17 JUN 2026
    592
    2
    1,740
    1,030,000
    Resale
    15 TAMPINES LANE #11-XX
    Strata
    HDB
    URA
    """

    rows = condo.parse_transaction_text(text, project_name="TEST", property_type="Apartment")

    assert len(rows) == 1
    assert rows[0]["Type of Area"] == "Strata"
    assert rows[0]["Purchaser Address"] == "HDB"
    assert rows[0]["Source"] == "URA"


def test_advertised_sales_count_accepts_singular_and_plural_labels():
    assert condo.advertised_sales_count("ALL SALES TRANSACTIONS (935)") == 935
    assert condo.advertised_sales_count("ALL SALES TRANSACTION (0)") == 0
    assert condo.advertised_sales_count("No transaction table") is None


def test_unit_fixture_preserves_exact_values_and_marks_unavailable_units():
    text = FIXTURE.read_text(encoding="utf-8")

    rows = condo.parse_transaction_text(
        text,
        project_name="TEST RESIDENCES",
        planning_area="NOVENA",
        postal_district="11",
        property_type="Condominium",
        tenure="Freehold",
    )

    assert len(rows) == 4
    exact, masked, absent, unparseable = rows
    assert exact["unit_number"] == "#06-15"
    assert exact["unit_floor"] == "06"
    assert exact["unit_stack"] == "15"
    assert exact["unit_number_status"] == "exact"
    assert exact["unit_number_source"] == "edgeprop_address"
    assert exact["Street"] == "10 TEST ROAD"

    assert masked["unit_number"] == ""
    assert masked["unit_floor"] == ""
    assert masked["unit_stack"] == ""
    assert masked["unit_number_status"] == "masked"
    assert masked["unit_number_source"] == "edgeprop_address"
    assert masked["Address"].endswith("#06-XX")

    assert absent["unit_number"] == ""
    assert absent["unit_number_status"] == "not_present"
    assert absent["unit_number_source"] == ""

    assert unparseable["unit_number"] == ""
    assert unparseable["unit_number_status"] == "unparseable"
    assert unparseable["unit_number_source"] == "edgeprop_address"
    assert unparseable["Address"].endswith("#LEVEL")


def test_parse_saved_transactions_writes_stable_unit_schema(tmp_path):
    out = tmp_path / "units.csv"
    args = argparse.Namespace(
        html_file=[],
        text_file=[str(FIXTURE)],
        project_name="",
        planning_area="",
        postal_district="",
        property_type="Condominium/Apartment",
        tenure="",
        source_url="https://www.edgeprop.sg/condo-apartment/test-residences",
        source_slug="test-residences",
        out=str(out),
    )

    condo.parse_saved_transactions(args)

    with out.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == condo.UNIT_FIELDS
    assert len(rows) == 4
    assert rows[0]["Project"] == "TEST RESIDENCES"
    assert rows[0]["planning_area"] == "NOVENA"
    assert rows[0]["Postal District"] == "11"
    assert rows[0]["unit_number"] == "#06-15"
    assert rows[1]["unit_number_status"] == "masked"
    assert all(row["source_quality"] == "not_clean" for row in rows)
    assert all(row["source_slug"] == "test-residences" for row in rows)


def test_extract_unit_number_rejects_ambiguity_and_preserves_alphanumeric_tokens():
    ambiguous = condo.extract_unit_number("10 TEST ROAD #01-01 / #02-02")
    penthouse = condo.extract_unit_number("10 TEST ROAD #PH-01")
    basement = condo.extract_unit_number("10 TEST ROAD #B1-01")

    assert ambiguous["unit_number"] == ""
    assert ambiguous["unit_number_status"] == "unparseable"
    assert penthouse["unit_number"] == "#PH-01"
    assert penthouse["unit_floor"] == "PH"
    assert penthouse["unit_number_status"] == "exact"
    assert basement["unit_number"] == "#B1-01"
    assert basement["unit_floor"] == "B1"
    assert basement["unit_number_status"] == "exact"


def test_generation_scope_captures_exact_filtered_batch_catalog_and_parameters(
    tmp_path: Path,
) -> None:
    args = scrape_args(tmp_path)
    args.match = "mdis"
    run = condo.prepare_generation(args)
    manifest = scrape_generation.load_generation(run.manifest_path)

    scope = manifest["requested_scope"]
    assert scope["project_catalog"] == {
        "name": "projects.csv",
        "sha256": condo.sha256_bytes((tmp_path / "projects.csv").read_bytes()),
    }
    assert scope["parameters"] == {
        "access_mode": "public",
        "artifact_schema": condo.ARTIFACT_SCHEMA,
        "from_year": 2019,
        "max_pages": 7,
    }
    assert len(scope["partitions"]) == 1
    partition = scope["partitions"][0]
    assert partition["source_slug"] == "mdis-residence@stirling"
    assert partition["partition_id"] == condo.partition_id_for_url(partition["source_url"])
    assert "@" not in partition["partition_id"]
    assert run.output_path == (tmp_path / "generation" / "legacy.csv").resolve()
    assert run.unit_output_path == (tmp_path / "generation" / "units.csv").resolve()


def test_generation_paths_are_scoped_and_legacy_attempt_resume_is_rejected(
    tmp_path: Path,
) -> None:
    escaping = scrape_args(tmp_path)
    escaping.out = "../canonical.csv"
    with pytest.raises(SystemExit, match="inside the generation root"):
        condo.prepare_generation(escaping)

    legacy_resume = scrape_args(tmp_path)
    legacy_resume.resume_attempts = True
    with pytest.raises(SystemExit, match="never resume evidence"):
        condo.prepare_generation(legacy_resume)


def test_retry_skips_only_selected_artifacts_and_assembles_exact_projections_once(
    tmp_path: Path,
) -> None:
    args = scrape_args(tmp_path)
    prior_legacy = tmp_path / "generation" / "legacy.csv"
    prior_legacy.parent.mkdir(parents=True)
    prior_legacy.write_text("prior output\n", encoding="utf-8")
    first_calls: list[str] = []

    async def first_scrape(_page, project, **_kwargs):
        first_calls.append(project["slug"])
        if project["slug"].startswith("mdis"):
            raise RuntimeError("injected navigation error")
        return successful_result(project, marker="1")

    with pytest.raises(SystemExit) as first_exit:
        asyncio.run(
            condo.scrape(args, page=FakePage(), scrape_project_fn=first_scrape)
        )
    assert first_exit.value.code == 1
    assert prior_legacy.read_text(encoding="utf-8") == "prior output\n"
    manifest = scrape_generation.load_generation(args.generation_manifest)
    assert manifest["summary"] == {
        "requested": 2,
        "selected": 1,
        "succeeded": 1,
        "confirmed_empty": 0,
        "failed": 1,
        "pending": 1,
    }

    # The manifest itself is the resume authority; the legacy --resume flag is
    # accepted for compatibility but is not required.
    retry_args = scrape_args(tmp_path)
    retry_calls: list[str] = []

    async def retry_scrape(_page, project, **_kwargs):
        retry_calls.append(project["slug"])
        return successful_result(project, marker="2")

    asyncio.run(
        condo.scrape(retry_args, page=FakePage(), scrape_project_fn=retry_scrape)
    )

    assert sorted(first_calls) == ["alpha-residences", "mdis-residence@stirling"]
    assert retry_calls == ["mdis-residence@stirling"]
    complete = scrape_generation.load_generation(args.generation_manifest)
    assert complete["status"] == "complete"
    assert complete["summary"]["succeeded"] == 2
    assert complete["output"]["row_count"] == 2

    legacy_fields, legacy_rows = read_csv(prior_legacy)
    unit_fields, unit_rows = read_csv(tmp_path / "generation" / "units.csv")
    assert legacy_fields == condo.FIELDS
    assert unit_fields == condo.UNIT_FIELDS
    assert len(legacy_rows) == len(unit_rows) == 2
    assert len({row["source_url"] for row in legacy_rows}) == 2
    assert legacy_rows == [
        {field: row[field] for field in condo.FIELDS} for row in unit_rows
    ]
    selected = scrape_generation.selected_artifacts(args.generation_manifest)
    assert sum(artifact.row_count for artifact in selected) == len(legacy_rows)

    attempts = {
        partition["partition_id"]: partition["attempts"]
        for partition in complete["partitions"]
    }
    failed_then_succeeded = next(value for value in attempts.values() if len(value) == 2)
    assert [attempt["status"] for attempt in failed_then_succeeded] == [
        "failed",
        "succeeded",
    ]
    passing = next(
        attempt
        for partition_attempts in attempts.values()
        for attempt in partition_attempts
        if attempt["status"] == "succeeded"
    )
    assert passing["retrieved_at"].endswith("Z")
    assert passing["completed_at"].endswith("Z")
    assert passing["source_reported_row_count"] == 1
    assert passing["observations"]["completion_reason"] == "terminal_pagination"
    assert passing["observations"]["source_advertised_count"] == 1


@pytest.mark.parametrize(
    ("outcome", "error_code"),
    [
        ("zero", "zero_rows"),
        ("exception", "scrape_exception"),
        ("max_pages", "max_pages_exhausted"),
        ("click", "pagination_click_failure"),
    ],
)
def test_zero_error_and_partial_results_remain_pending_without_replacing_candidate(
    tmp_path: Path,
    outcome: str,
    error_code: str,
) -> None:
    args = scrape_args(tmp_path, projects=[("ALPHA", "alpha")])
    candidate = tmp_path / "generation" / "legacy.csv"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("preserve me\n", encoding="utf-8")

    async def fake_scrape(_page, project, **_kwargs):
        if outcome == "exception":
            raise RuntimeError("injected page error")
        if outcome == "zero":
            return condo.ScrapeResult(
                rows=[],
                pages_scraped=1,
                completion_reason="terminal_pagination",
                source_advertised_count=0,
            )
        return condo.ScrapeResult(
            rows=[transaction_row(project)],
            pages_scraped=7,
            completion_reason=(
                "max_pages_exhausted"
                if outcome == "max_pages"
                else "pagination_click_failure"
            ),
            source_advertised_count=40,
        )

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(
            condo.scrape(args, page=FakePage(), scrape_project_fn=fake_scrape)
        )
    assert exc_info.value.code == 1
    assert candidate.read_text(encoding="utf-8") == "preserve me\n"

    manifest = scrape_generation.load_generation(args.generation_manifest)
    assert manifest["status"] == "open"
    assert manifest["summary"]["pending"] == 1
    attempt = manifest["partitions"][0]["attempts"][0]
    assert attempt["status"] == "failed"
    assert attempt["error_code"] == error_code
    assert attempt["artifact"] is None


def test_artifact_provenance_mismatch_is_failed_and_never_selected(
    tmp_path: Path,
) -> None:
    args = scrape_args(tmp_path, projects=[("ALPHA", "alpha")])

    async def mismatched_scrape(_page, project, **_kwargs):
        row = transaction_row(project)
        row["source_slug"] = "different-slug"
        return condo.ScrapeResult(
            rows=[row],
            pages_scraped=1,
            completion_reason="terminal_pagination",
            source_advertised_count=1,
        )

    with pytest.raises(SystemExit):
        asyncio.run(
            condo.scrape(args, page=FakePage(), scrape_project_fn=mismatched_scrape)
        )

    manifest = scrape_generation.load_generation(args.generation_manifest)
    attempt = manifest["partitions"][0]["attempts"][0]
    assert attempt["error_code"] == "artifact_validation_failed"
    assert attempt["artifact"] is None
    assert manifest["partitions"][0]["selected_attempt_id"] is None
    assert not list((tmp_path / "generation" / "artifacts").rglob("*.csv"))


def test_resume_rejects_changed_scope_catalog_and_generation_evidence(
    tmp_path: Path,
) -> None:
    args = scrape_args(tmp_path, projects=[("ALPHA", "alpha")])
    condo.prepare_generation(args)

    changed_scope = scrape_args(tmp_path, resume=True, from_year=2020)
    with pytest.raises(ContractError, match="requested_scope"):
        condo.prepare_generation(changed_scope)

    changed_generation = scrape_args(
        tmp_path, resume=True, generation_id="different-generation"
    )
    with pytest.raises(ContractError, match="generation_id"):
        condo.prepare_generation(changed_generation)

    (tmp_path / "projects.csv").write_text(
        (tmp_path / "projects.csv").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    changed_catalog = scrape_args(tmp_path, resume=True)
    with pytest.raises(ContractError, match="requested_scope"):
        condo.prepare_generation(changed_catalog)


def test_selected_artifact_tampering_aborts_resume_before_scraping(
    tmp_path: Path,
) -> None:
    args = scrape_args(tmp_path)

    async def first_scrape(_page, project, **_kwargs):
        if project["slug"].startswith("mdis"):
            raise RuntimeError("leave one pending")
        return successful_result(project)

    with pytest.raises(SystemExit):
        asyncio.run(
            condo.scrape(args, page=FakePage(), scrape_project_fn=first_scrape)
        )
    artifact = scrape_generation.selected_artifacts(args.generation_manifest)[0].path
    artifact.write_text("tampered\n", encoding="utf-8")
    calls: list[str] = []

    async def must_not_run(_page, project, **_kwargs):
        calls.append(project["slug"])
        return successful_result(project)

    retry = scrape_args(tmp_path, resume=True)
    with pytest.raises(ContractError, match="byte_count|sha256"):
        asyncio.run(
            condo.scrape(retry, page=FakePage(), scrape_project_fn=must_not_run)
        )
    assert calls == []


def test_crash_after_atomic_artifact_write_leaves_orphan_and_retry_uses_new_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = scrape_args(tmp_path, projects=[("ALPHA", "alpha")])
    identifiers = iter(["attempt-orphan", "attempt-retry"])
    monkeypatch.setattr(condo, "new_attempt_id", lambda: next(identifiers))
    real_record_attempt = condo.scrape_generation.record_attempt

    def crash_before_manifest_switch(*call_args, **call_kwargs):
        if call_kwargs.get("status") == "succeeded":
            raise OSError("injected manifest switch crash")
        return real_record_attempt(*call_args, **call_kwargs)

    monkeypatch.setattr(
        condo.scrape_generation, "record_attempt", crash_before_manifest_switch
    )

    async def fake_scrape(_page, project, **_kwargs):
        return successful_result(project)

    with pytest.raises(OSError, match="manifest switch crash"):
        asyncio.run(
            condo.scrape(args, page=FakePage(), scrape_project_fn=fake_scrape)
        )
    orphan = next((tmp_path / "generation" / "artifacts").rglob("attempt-orphan.csv"))
    orphan_bytes = orphan.read_bytes()
    manifest = scrape_generation.load_generation(args.generation_manifest)
    assert manifest["summary"]["pending"] == 1

    monkeypatch.setattr(condo.scrape_generation, "record_attempt", real_record_attempt)
    retry = scrape_args(tmp_path, resume=True)
    asyncio.run(
        condo.scrape(retry, page=FakePage(), scrape_project_fn=fake_scrape)
    )

    retry_artifact = next(
        (tmp_path / "generation" / "artifacts").rglob("attempt-retry.csv")
    )
    assert retry_artifact != orphan
    assert orphan.read_bytes() == orphan_bytes
    assert scrape_generation.load_generation(args.generation_manifest)["status"] == "complete"
