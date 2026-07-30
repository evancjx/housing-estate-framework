"""Safe, deterministic publication of dated private-property analyses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from string import Template
import re
from urllib.parse import quote, unquote, urlsplit

from markdown import Markdown

from sg_estate.reporting.common import html_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROPERTY_ANALYSIS_DIR = ROOT / "property_analysis"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "property_analysis.html"
PUBLISHED_SITE = "https://evancjx.github.io/housing-estate-framework"
SOURCE_REPOSITORY = "https://github.com/evancjx/housing-estate-framework"

FILENAME_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})-"
    r"(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md"
)
METADATA_RE = re.compile(r"^(?P<label>[A-Za-z][A-Za-z ]+):\s+\*\*(?P<value>.+)\*\*$")
CAPTURED_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"SGT \(UTC\+08:00\)$"
)
REQUIRED_METADATA = {
    "Research captured",
    "Property",
    "Analysis type",
    "Status",
}
ALLOWED_MARKET_STAGES = {"future project", "resale"}
IGNORED_MARKDOWN_FILES = {"README.md"}
ALLOWED_LINK_SCHEMES = {"http", "https", "mailto"}
FORBIDDEN_TAGS = {"embed", "iframe", "object", "script", "style"}
ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h2",
    "h3",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "div": {"aria-label", "class", "role", "tabindex"},
    "h2": {"id"},
    "h3": {"id"},
    "span": {"class"},
    "td": {"style"},
    "th": {"scope", "style"},
}
SAFE_ALIGNMENT_STYLE_RE = re.compile(r"^text-align:\s*(left|center|right);?$")


@dataclass(frozen=True)
class PropertyAnalysis:
    """Validated source metadata for one point-in-time property analysis."""

    source_path: Path
    project_slug: str
    title: str
    project_name: str
    property_description: str
    captured_at: datetime
    captured_display: str
    analysis_type: str
    status: str
    market_stage: str
    summary: str
    body_markdown: str

    @property
    def report_id(self) -> str:
        return f"property-analysis-{self.source_path.stem}"

    @property
    def output_path(self) -> str:
        return f"{self.report_id}.html"

    @property
    def captured_iso(self) -> str:
        return self.captured_at.isoformat()

    @property
    def date_label(self) -> str:
        return self.captured_at.strftime("%d %b %Y")

    @property
    def source_relative_path(self) -> str:
        try:
            return self.source_path.relative_to(ROOT).as_posix()
        except ValueError:
            return self.source_path.name

    def catalog_entry(self, *, is_latest: bool) -> dict:
        """Return the public report-catalog representation."""

        return {
            "id": self.report_id,
            "path": self.output_path,
            "title": self.title,
            "category": "property-analysis",
            "kind": "property-analysis",
            "summary": self.summary,
            "tags": [
                "private property",
                "property analysis",
                self.market_stage,
                "valuation",
                "investment",
                self.project_name,
            ],
            "project_name": self.project_name,
            "project_slug": self.project_slug,
            "captured_at": self.captured_iso,
            "status": self.status,
            "market_stage": self.market_stage,
            "source_path": self.source_relative_path,
            "is_latest": is_latest,
        }


class _RenderedFragmentParser(HTMLParser):
    """Collect security-sensitive features from rendered Markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []
        self.forbidden_tags: list[str] = []
        self.unsafe_attributes: list[str] = []
        self.h1_count = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in FORBIDDEN_TAGS:
            self.forbidden_tags.append(normalized_tag)
        if normalized_tag not in ALLOWED_TAGS:
            self.forbidden_tags.append(normalized_tag)
        if normalized_tag == "h1":
            self.h1_count += 1
        values = dict(attrs)
        for attribute in ("href", "src"):
            value = values.get(attribute)
            if value:
                self.references.append((normalized_tag, value))
        for attribute, value in attrs:
            normalized_attribute = attribute.casefold()
            if normalized_attribute not in ALLOWED_ATTRIBUTES.get(normalized_tag, set()):
                self.unsafe_attributes.append(
                    f"{normalized_tag}[{normalized_attribute}]"
                )
            if (
                normalized_attribute == "style"
                and (
                    value is None
                    or not SAFE_ALIGNMENT_STYLE_RE.fullmatch(value.strip())
                )
            ):
                self.unsafe_attributes.append(
                    f"{normalized_tag}[style={value!r}]"
                )


def _plain_markdown(value: str) -> str:
    value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_`~]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _summary_from_decision(body_markdown: str, *, limit: int = 300) -> str:
    match = re.search(
        r"^##\s+Decision\s*$\s*(?P<decision>.+?)(?:\n\s*\n|\Z)",
        body_markdown,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError("Property analysis must contain a non-empty '## Decision' section")
    summary = _plain_markdown(match.group("decision"))
    if not summary:
        raise ValueError("Property analysis Decision section must begin with prose")
    if len(summary) <= limit:
        return summary
    sentence_end = summary.rfind(". ", 0, limit)
    word_end = summary.rfind(" ", 0, limit - 1)
    end = sentence_end + 1 if sentence_end >= limit // 2 else word_end
    return summary[: max(end, limit // 2)].rstrip(" ,;:-") + "…"


def parse_property_analysis(source_path: Path) -> PropertyAnalysis:
    """Parse and validate the repository's dated Markdown publication format."""

    filename_match = FILENAME_RE.fullmatch(source_path.name)
    if not filename_match:
        raise ValueError(
            f"{source_path.name} must match YYYY-MM-DD-project-slug.md"
        )
    if source_path.is_symlink():
        raise ValueError(f"Property analysis sources cannot be symlinks: {source_path}")

    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read property analysis {source_path}: {exc}") from exc

    lines = source.splitlines()
    if not lines or not lines[0].startswith("# ") or lines[0].startswith("## "):
        raise ValueError(f"{source_path.name} must begin with exactly one level-one title")
    title = lines[0][2:].strip()
    if not title or " — " not in title:
        raise ValueError(
            f"{source_path.name} title must be '<project> — <analysis description>'"
        )
    project_name = title.split(" — ", 1)[0].strip()
    if not project_name:
        raise ValueError(f"{source_path.name} title has no project name")

    first_section = next(
        (position for position, line in enumerate(lines[1:], start=1) if line.startswith("## ")),
        None,
    )
    if first_section is None:
        raise ValueError(f"{source_path.name} has no level-two analysis sections")

    metadata: dict[str, str] = {}
    for line in lines[1:first_section]:
        candidate = line.strip()
        if not candidate:
            continue
        match = METADATA_RE.fullmatch(candidate)
        if not match:
            raise ValueError(
                f"{source_path.name} has invalid publication metadata: {candidate!r}"
            )
        label = match.group("label")
        if label in metadata:
            raise ValueError(f"{source_path.name} repeats metadata field {label!r}")
        metadata[label] = match.group("value").strip()

    missing = REQUIRED_METADATA - metadata.keys()
    if missing:
        raise ValueError(
            f"{source_path.name} is missing metadata: {', '.join(sorted(missing))}"
        )
    unknown = metadata.keys() - (REQUIRED_METADATA | {"Market stage", "Summary"})
    if unknown:
        raise ValueError(
            f"{source_path.name} has unknown metadata: {', '.join(sorted(unknown))}"
        )

    captured_match = CAPTURED_RE.fullmatch(metadata["Research captured"])
    if not captured_match:
        raise ValueError(
            f"{source_path.name} Research captured must use "
            "'YYYY-MM-DD HH:MM:SS SGT (UTC+08:00)'"
        )
    captured_at = datetime.strptime(
        captured_match.group("timestamp"), "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=timezone(timedelta(hours=8)))
    if captured_at.date().isoformat() != filename_match.group("date"):
        raise ValueError(
            f"{source_path.name} date does not match Research captured "
            f"{captured_at.date().isoformat()}"
        )

    body_markdown = "\n".join(lines[first_section:]).strip() + "\n"
    if re.search(r"^#\s+", body_markdown, flags=re.MULTILINE):
        raise ValueError(f"{source_path.name} may contain only one level-one title")
    summary = metadata.get("Summary") or _summary_from_decision(body_markdown)
    summary = _plain_markdown(summary)
    if not summary:
        raise ValueError(f"{source_path.name} Summary cannot be empty")
    market_stage = metadata.get("Market stage", "resale").casefold()
    if market_stage not in ALLOWED_MARKET_STAGES:
        raise ValueError(
            f"{source_path.name} Market stage must be one of: "
            f"{', '.join(sorted(ALLOWED_MARKET_STAGES))}"
        )

    return PropertyAnalysis(
        source_path=source_path.resolve(),
        project_slug=filename_match.group("slug"),
        title=title,
        project_name=project_name,
        property_description=metadata["Property"],
        captured_at=captured_at,
        captured_display=metadata["Research captured"],
        analysis_type=metadata["Analysis type"],
        status=metadata["Status"],
        market_stage=market_stage,
        summary=summary,
        body_markdown=body_markdown,
    )


def discover_property_analyses(
    source_dir: Path = DEFAULT_PROPERTY_ANALYSIS_DIR,
) -> list[PropertyAnalysis]:
    """Discover direct dated Markdown sources in deterministic newest-first order."""

    if not source_dir.is_dir():
        raise ValueError(f"Property analysis directory does not exist: {source_dir}")

    analyses: list[PropertyAnalysis] = []
    for source_path in sorted(source_dir.glob("*.md")):
        if source_path.name in IGNORED_MARKDOWN_FILES or source_path.name.startswith("_"):
            continue
        analyses.append(parse_property_analysis(source_path))
    if not analyses:
        raise ValueError(f"No publishable property analyses found in {source_dir}")

    seen_ids: set[str] = set()
    seen_outputs: set[str] = set()
    seen_captures: set[tuple[str, str]] = set()
    slug_project_names: dict[str, str] = {}
    project_name_slugs: dict[str, str] = {}
    for analysis in analyses:
        if analysis.report_id in seen_ids:
            raise ValueError(f"Duplicate property analysis id: {analysis.report_id}")
        seen_ids.add(analysis.report_id)
        if analysis.output_path in seen_outputs:
            raise ValueError(f"Duplicate property analysis output: {analysis.output_path}")
        seen_outputs.add(analysis.output_path)

        project_name_key = " ".join(analysis.project_name.split()).casefold()
        capture_key = (analysis.project_slug, analysis.captured_iso)
        if capture_key in seen_captures:
            raise ValueError(
                f"Duplicate property capture for {analysis.project_name} at "
                f"{analysis.captured_iso}"
            )
        seen_captures.add(capture_key)
        previous_name = slug_project_names.setdefault(
            analysis.project_slug, project_name_key
        )
        if previous_name != project_name_key:
            raise ValueError(
                f"Project slug {analysis.project_slug!r} uses inconsistent names: "
                f"{previous_name!r} and {project_name_key!r}"
            )
        previous_slug = project_name_slugs.setdefault(
            project_name_key, analysis.project_slug
        )
        if previous_slug != analysis.project_slug:
            raise ValueError(
                f"Project {analysis.project_name!r} uses inconsistent slugs: "
                f"{previous_slug!r} and {analysis.project_slug!r}"
            )

    return sorted(
        analyses,
        key=lambda analysis: (
            -analysis.captured_at.timestamp(),
            analysis.project_name.casefold(),
            analysis.output_path,
        ),
    )


def latest_property_analyses(
    analyses: list[PropertyAnalysis],
) -> list[PropertyAnalysis]:
    """Return the newest capture for each project, preserving discovery order."""

    latest: list[PropertyAnalysis] = []
    seen_projects: set[str] = set()
    for analysis in analyses:
        if analysis.project_slug not in seen_projects:
            latest.append(analysis)
            seen_projects.add(analysis.project_slug)
    return latest


def property_catalog_entries(
    analyses: list[PropertyAnalysis],
) -> list[dict]:
    """Return entries for every capture, marking each project's newest capture."""

    latest_ids = {analysis.report_id for analysis in latest_property_analyses(analyses)}
    return [
        analysis.catalog_entry(is_latest=analysis.report_id in latest_ids)
        for analysis in analyses
    ]


def _normalized_reference(reference: str) -> str:
    normalized = "".join(character for character in reference if ord(character) > 32)
    normalized = normalized.replace("\\", "/")
    for _ in range(3):
        decoded = unquote(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    return normalized


def _validate_rendered_fragment(fragment: str, *, source_name: str) -> None:
    parser = _RenderedFragmentParser()
    parser.feed(fragment)
    if parser.forbidden_tags:
        raise ValueError(
            f"{source_name} rendered forbidden HTML: "
            f"{', '.join(sorted(set(parser.forbidden_tags)))}"
        )
    if parser.unsafe_attributes:
        raise ValueError(
            f"{source_name} rendered unsafe HTML attributes: "
            f"{', '.join(sorted(set(parser.unsafe_attributes)))}"
        )
    if parser.h1_count:
        raise ValueError(f"{source_name} rendered an unexpected level-one title")

    for tag, reference in parser.references:
        normalized = _normalized_reference(reference)
        if tag == "img":
            raise ValueError(f"{source_name} images are not supported: {reference!r}")
        if normalized.startswith("#"):
            continue
        if normalized.startswith("//"):
            raise ValueError(
                f"{source_name} contains a protocol-relative link: {reference!r}"
            )
        scheme = urlsplit(normalized).scheme.casefold()
        if scheme not in ALLOWED_LINK_SCHEMES:
            raise ValueError(
                f"{source_name} contains an unsafe or relative link: {reference!r}"
            )


def render_markdown(analysis: PropertyAnalysis) -> tuple[str, str]:
    """Render escaped Markdown and return safe body and table-of-contents HTML."""

    escaped_markdown = escape(analysis.body_markdown, quote=False)
    renderer = Markdown(
        extensions=["tables", "toc"],
        extension_configs={
            "toc": {
                "toc_depth": "2-3",
                "title": "On this page",
            }
        },
        output_format="html5",
    )
    body_html = renderer.convert(escaped_markdown)

    def add_header_scope(match: re.Match[str]) -> str:
        attributes = match.group("attributes") or ""
        if re.search(r"\bscope\s*=", attributes, flags=re.IGNORECASE):
            return match.group(0)
        return f"<th scope=\"col\"{attributes}>"

    body_html = re.sub(
        r"<th(?P<attributes>\s[^>]*)?>",
        add_header_scope,
        body_html,
        flags=re.IGNORECASE,
    )
    table_number = 0

    def wrap_table(match: re.Match[str]) -> str:
        nonlocal table_number
        table_number += 1
        return (
            '<div class="tbl-wrap pa-table-wrap" role="region" tabindex="0" '
            f'aria-label="Scrollable research table {table_number}">'
            f"{match.group(0)}</div>"
        )

    body_html = re.sub(
        r"<table\b.*?</table>",
        wrap_table,
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    toc_html = getattr(renderer, "toc", "")
    _validate_rendered_fragment(body_html + toc_html, source_name=analysis.source_path.name)
    return body_html, toc_html


def render_property_analysis_page(analysis: PropertyAnalysis) -> str:
    """Render one complete static property-analysis page."""

    body_html, toc_html = render_markdown(analysis)
    canonical_url = f"{PUBLISHED_SITE}/{quote(analysis.output_path)}"
    source_url = (
        f"{SOURCE_REPOSITORY}/blob/main/"
        f"{quote(analysis.source_relative_path, safe='/')}"
    )
    structured_data = html_json(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": analysis.title,
            "description": analysis.summary,
            "datePublished": analysis.captured_iso,
            "dateModified": analysis.captured_iso,
            "about": {
                "@type": "Residence",
                "name": analysis.project_name,
                "address": analysis.property_description,
            },
            "mainEntityOfPage": canonical_url,
            "url": canonical_url,
        }
    )
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        page_title=escape(
            f"{analysis.project_name} property analysis — {analysis.date_label}"
        ),
        meta_description=escape(analysis.summary, quote=True),
        canonical_url=escape(canonical_url, quote=True),
        structured_data=structured_data,
        title=escape(analysis.title),
        project_name=escape(analysis.project_name),
        property_description=escape(analysis.property_description),
        captured_display=escape(analysis.captured_display),
        captured_iso=escape(analysis.captured_iso, quote=True),
        analysis_type=escape(analysis.analysis_type),
        status=escape(analysis.status),
        summary=escape(analysis.summary),
        toc_html=toc_html,
        body_html=body_html,
        source_url=escape(source_url, quote=True),
    )


__all__ = [
    "DEFAULT_PROPERTY_ANALYSIS_DIR",
    "PropertyAnalysis",
    "discover_property_analyses",
    "latest_property_analyses",
    "parse_property_analysis",
    "property_catalog_entries",
    "render_markdown",
    "render_property_analysis_page",
]
