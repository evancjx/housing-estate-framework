#!/usr/bin/env python3
"""Publish frozen property evidence and verify its static-site references."""

from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from urllib.parse import parse_qs, unquote, urlsplit
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_DIR = ROOT / "data/raw/property_research"
DEFAULT_VIEWER_DIR = ROOT / "site/assets"
PUBLISHED_SITE = "https://evancjx.github.io/housing-estate-framework"
DATA_EXTENSIONS = {".csv", ".json", ".md"}


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value or "\\" in value or "\x00" in value
        or path.is_absolute() or re.match(r"^[A-Za-z]:", value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"Unsafe evidence path: {value!r}")
    return path


def _inside(root: Path, relative: PurePosixPath) -> Path:
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Evidence path escapes publication directory: {relative}")
    return target


def _extract_archive(archive: Path, destination: Path) -> None:
    """Check every member before writing; never use ZIP-controlled permissions."""
    try:
        with ZipFile(archive) as source:
            members = []
            seen = set()
            files = set()
            for member in source.infolist():
                value = member.filename[:-1] if member.is_dir() else member.filename
                relative = _relative_path(value)
                mode = member.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError(f"Non-regular evidence archive member: {member.filename}")
                if (kind == stat.S_IFDIR) != member.is_dir() and kind != 0:
                    raise ValueError(f"Inconsistent evidence archive member: {member.filename}")
                identity = str(relative).casefold()
                if identity in seen:
                    raise ValueError(f"Duplicate evidence archive member: {member.filename}")
                seen.add(identity)
                if not member.is_dir():
                    if relative.suffix not in DATA_EXTENSIONS:
                        raise ValueError(f"Unsupported evidence archive file: {member.filename}")
                    files.add(identity)
                _inside(destination, relative)
                members.append((member, relative))
            for _, relative in members:
                if any(str(parent).casefold() in files for parent in relative.parents):
                    raise ValueError(f"Evidence archive file/directory conflict: {relative}")
            for member, relative in members:
                target = _inside(destination, relative)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as reader, target.open("wb") as writer:
                        shutil.copyfileobj(reader, writer)
    except BadZipFile as exc:
        raise ValueError(f"Invalid evidence archive {archive}: {exc}") from exc


def publish_property_research(
    site_dir: Path,
    *,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    viewer_dir: Path = DEFAULT_VIEWER_DIR,
) -> int:
    """Publish dated evidence archives and the shared read-only data viewer."""
    archives = sorted(archive_dir.glob("*.zip"))
    if not archives:
        return 0
    viewers = [viewer_dir / name for name in (
        "research-data.html", "research-data.css", "research-data.js",
    )]
    for source in viewers:
        if not source.is_file():
            raise ValueError(f"Missing research viewer asset: {source}")
    for archive in archives:
        try:
            parsed_date = date.fromisoformat(archive.stem)
        except ValueError as exc:
            raise ValueError(f"Evidence archive must have a YYYY-MM-DD name: {archive.name}") from exc
        if parsed_date.isoformat() != archive.stem:
            raise ValueError(f"Evidence archive must have a YYYY-MM-DD name: {archive.name}")
        relative = PurePosixPath("research") / archive.stem
        destination = _inside(site_dir, relative)
        _extract_archive(archive, destination)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, destination / "source.zip")
    for source in viewers:
        relative = PurePosixPath(source.name) if source.suffix == ".html" else PurePosixPath("assets") / source.name
        target = _inside(site_dir, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return len(archives)


class _References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        attribute = "src" if tag in {"img", "script", "source"} else "href"
        if tag in {"a", "link", "img", "script", "source"} and fields.get(attribute):
            self.values.append(fields[attribute])


def validate_published_references(site_dir: Path, *, published_site: str = PUBLISHED_SITE) -> None:
    """Resolve this site's absolute links and each viewer's requested evidence."""
    base = urlsplit(published_site)
    prefix = base.path.rstrip("/") + "/"
    broken = []
    for html in site_dir.rglob("*.html"):
        parser = _References()
        parser.feed(html.read_text(encoding="utf-8"))
        for reference in parser.values:
            url = urlsplit(reference)
            same_site = bool(url.netloc and url.netloc.lower() == base.netloc.lower())
            if url.scheme or url.netloc:
                if not same_site or url.scheme not in {"", "http", "https"}:
                    continue
                decoded = unquote(url.path)
                if decoded == prefix.rstrip("/"):
                    relative = PurePosixPath("index.html")
                elif decoded.startswith(prefix):
                    value = decoded[len(prefix):] or "index.html"
                    try:
                        relative = _relative_path(value)
                    except ValueError as exc:
                        broken.append(f"{html.name} -> {reference} ({exc})")
                        continue
                else:
                    continue
            else:
                # Ordinary relative links are checked by the site builder;
                # this pass additionally follows viewer query parameters.
                if PurePosixPath(unquote(url.path)).name != "research-data.html":
                    continue
                target = html.parent / unquote(url.path)
                try:
                    relative = PurePosixPath(target.resolve().relative_to(site_dir.resolve()).as_posix())
                except ValueError:
                    broken.append(f"{html.name} -> {reference} (viewer escapes site)")
                    continue
            try:
                target = _inside(site_dir, relative)
                if target.is_dir():
                    target /= "index.html"
                if not target.is_file():
                    raise ValueError("missing publication target")
                if target.name == "research-data.html":
                    values = parse_qs(url.query, keep_blank_values=True).get("path", [])
                    if len(values) != 1:
                        raise ValueError("viewer requires one evidence path")
                    evidence = _relative_path(values[0])
                    if not str(evidence).startswith("research/") or not re.fullmatch(
                        r"research/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*\.csv",
                        str(evidence), re.IGNORECASE,
                    ):
                        raise ValueError("viewer path must select published research CSV data")
                    if not _inside(site_dir, evidence).is_file():
                        raise ValueError("missing viewer evidence target")
            except ValueError as exc:
                broken.append(f"{html.name} -> {reference} ({exc})")
    if broken:
        raise ValueError("Broken published research references:\n" + "\n".join(sorted(broken)))
