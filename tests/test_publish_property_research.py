"""Frozen evidence cannot escape the site or leave broken public data links."""

import stat
from zipfile import ZipFile, ZipInfo

import pytest

from scripts.publish_property_research import (
    PUBLISHED_SITE,
    publish_property_research,
    validate_published_references,
)


@pytest.fixture
def publication(tmp_path):
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    viewer_dir = tmp_path / "viewer"
    viewer_dir.mkdir()
    (viewer_dir / "research-data.html").write_text(
        '<link rel="stylesheet" href="assets/research-data.css">'
        '<script src="assets/research-data.js"></script>', encoding="utf-8",
    )
    (viewer_dir / "research-data.css").write_text("body {}", encoding="utf-8")
    (viewer_dir / "research-data.js").write_text("void 0;", encoding="utf-8")
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    return site_dir, archive_dir, viewer_dir


def write_archive(archive_dir, entries):
    archive = archive_dir / "2026-09-20.zip"
    with ZipFile(archive, "w") as bundle:
        for name, contents in entries:
            bundle.writestr(name, contents)
    return archive


def test_publishes_exact_frozen_rows_nested_evidence_and_download_archive(publication):
    site_dir, archive_dir, viewer_dir = publication
    rows = "record_id,price\na,1000000\nb,1000000\n"
    archive = write_archive(archive_dir, [
        ("transactions.csv", rows),
        ("individual/sample-project/cohorts.csv", "n,median_price\n2,1000000\n"),
        ("enrichment/provenance.json", '{"quarter":"2026Q2"}'),
        ("README.md", "# Frozen capture\n"),
    ])

    assert publish_property_research(site_dir, archive_dir=archive_dir, viewer_dir=viewer_dir) == 1

    published = site_dir / "research/2026-09-20"
    assert (published / "transactions.csv").read_text() == rows
    assert (published / "individual/sample-project/cohorts.csv").is_file()
    assert (published / "source.zip").read_bytes() == archive.read_bytes()
    assert (site_dir / "research-data.html").read_bytes() == (viewer_dir / "research-data.html").read_bytes()
    assert (site_dir / "assets/research-data.js").is_file()


@pytest.mark.parametrize("unsafe", [
    "../escape.csv", "/absolute.csv", "enrichment/../../escape.csv",
    "C:/escape.csv", "enrichment\\escape.csv", "enrichment/./data.csv",
    "enrichment//data.csv", "payload.html", "payload.js", "program.py",
])
def test_archive_paths_and_executable_formats_are_rejected_before_any_extraction(publication, unsafe):
    site_dir, archive_dir, viewer_dir = publication
    write_archive(archive_dir, [("valid.csv", "a\n1\n"), (unsafe, "bad")])

    with pytest.raises(ValueError, match="Unsafe|Unsupported"):
        publish_property_research(site_dir, archive_dir=archive_dir, viewer_dir=viewer_dir)
    assert not (site_dir / "research/2026-09-20/valid.csv").exists()
    assert not (site_dir.parent / "escape.csv").exists()


def test_archive_symbolic_links_are_rejected(publication):
    site_dir, archive_dir, viewer_dir = publication
    link = ZipInfo("linked.csv")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    write_archive(archive_dir, [(link, "../../outside.csv")])

    with pytest.raises(ValueError, match="Non-regular"):
        publish_property_research(site_dir, archive_dir=archive_dir, viewer_dir=viewer_dir)


@pytest.mark.parametrize("entries", [
    [("data.csv", "first"), ("DATA.csv", "second")],
    [("data.csv", "first"), ("data.csv/child.csv", "second")],
])
def test_archive_cannot_overwrite_case_equivalent_names_or_conflict_with_directories(publication, entries):
    site_dir, archive_dir, viewer_dir = publication
    write_archive(archive_dir, entries)

    with pytest.raises(ValueError, match="Duplicate|conflict"):
        publish_property_research(site_dir, archive_dir=archive_dir, viewer_dir=viewer_dir)
    assert not (site_dir / "research/2026-09-20/data.csv").exists()


def test_archive_cannot_follow_an_existing_destination_symlink(publication):
    site_dir, archive_dir, viewer_dir = publication
    outside = site_dir.parent / "outside"
    outside.mkdir()
    (site_dir / "research").symlink_to(outside, target_is_directory=True)
    write_archive(archive_dir, [("data.csv", "x\n")])

    with pytest.raises(ValueError, match="escapes"):
        publish_property_research(site_dir, archive_dir=archive_dir, viewer_dir=viewer_dir)
    assert not list(outside.iterdir())


def test_same_site_absolute_reports_downloads_and_encoded_viewer_paths_resolve(tmp_path):
    (tmp_path / "project.html").write_text("<p>Project</p>")
    (tmp_path / "research-data.html").write_text("<p>Viewer</p>")
    evidence = tmp_path / "research/2026-09-20"
    evidence.mkdir(parents=True)
    (evidence / "unit_rows.csv").write_text("price\n1000000\n")
    (evidence / "source.zip").write_bytes(b"archive")
    (tmp_path / "index.html").write_text(
        f'<a href="{PUBLISHED_SITE}/project.html#decision">Report</a>'
        f'<a href="{PUBLISHED_SITE}/research/2026-09-20/source.zip?download=1">Archive</a>'
        f'<a href="{PUBLISHED_SITE}/research-data.html?path=research%2F2026-09-20%2Funit_rows.csv">Rows</a>'
        '<a href="research-data.html?path=research/2026-09-20/unit_rows.csv">Relative viewer</a>'
        '<a href="https://example.com/missing.csv">External source</a>'
    )

    validate_published_references(tmp_path)


@pytest.mark.parametrize("reference, message", [
    (f"{PUBLISHED_SITE}/missing.html", "missing publication target"),
    (f"{PUBLISHED_SITE}/research/2026-09-20/missing.csv", "missing publication target"),
    (f"{PUBLISHED_SITE}/research-data.html?path=research/2026-09-20/missing.csv", "missing viewer evidence"),
    ("research-data.html?path=research/2026-09-20/missing.csv", "missing viewer evidence"),
    ("research-data.html", "requires one evidence path"),
    ("research-data.html?path=research/a.csv&path=research/b.csv", "requires one evidence path"),
    ("research-data.html?path=research/%2E%2E/private.csv", "Unsafe evidence path"),
    ("research-data.html?path=reports.json", "must select published research"),
    ("research-data.html?path=research/2026-09-20/provenance.json", "must select published research"),
    ("research-data.html?path=research/2026-09-20/unit%20rows.csv", "must select published research"),
    (f"{PUBLISHED_SITE}/%2E%2E/private.csv", "Unsafe evidence path"),
])
def test_missing_or_unsafe_public_evidence_references_fail_validation(tmp_path, reference, message):
    (tmp_path / "research-data.html").write_text("<p>Viewer</p>")
    (tmp_path / "reports.json").write_text("{}")
    (tmp_path / "index.html").write_text(f'<a href="{reference}">Evidence</a>')

    with pytest.raises(ValueError, match=message):
        validate_published_references(tmp_path)
