#!/usr/bin/env python3
"""Generate the static shell and data contract for the project exit decision lab.

The browser loads achieved transaction rows from the already committed shards.
This generator only joins the reusable private-project catalog to the committed
transaction manifest; it never rebuilds or rewrites transaction assets.

The page compares recorded transactions in a same-size cohort and can apply a
user-controlled projected exit scenario. It does not compare layouts, estimate
liquidity, or publish an investment forecast.

Reads:
  data/inputs/ura_private.csv and the supporting project evidence used by
    gen_condo_framework_comparison_html.load_projects_for_comparison()
  site/assets/condo-transactions/manifest.json
  sg_estate/reporting/templates/project_exit_comparison.html

Writes:
  project_exit_comparison.html
"""

from __future__ import annotations

import argparse
from datetime import date
import html
import json
import pathlib
from typing import Any

import gen_condo_framework_comparison_html as project_comparison


ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_MANIFEST = ROOT / "site/assets/condo-transactions/manifest.json"
DEFAULT_TEMPLATE = (
    ROOT / "sg_estate/reporting/templates/project_exit_comparison.html"
)
DEFAULT_OUT = ROOT / "project_exit_comparison.html"

MIN_PROJECTS = 2
MAX_PROJECTS = 5
PREFERRED_DEFAULT_IDS = (
    "the-poiz-residences",
    "parc-esta",
    "treasure-at-tampines",
)


def script_safe_json(value: Any) -> str:
    """Serialize data without allowing a project value to close the script tag."""

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _as_of_date(value: date | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"invalid --as-of date {value!r}; expected YYYY-MM-DD") from exc


def load_transaction_manifest(path: pathlib.Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Load and minimally validate the committed transaction manifest."""

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"transaction manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid transaction manifest JSON: {path}: {exc}") from exc

    required = {"schema", "enumerations", "source_metadata", "projects"}
    missing = sorted(required - set(manifest))
    if missing:
        raise SystemExit(f"transaction manifest missing required keys: {missing}")
    if not isinstance(manifest["projects"], dict):
        raise SystemExit("transaction manifest projects must be an object keyed by project id")
    return manifest


def _default_ids(projects: list[dict[str, Any]]) -> list[str]:
    """Use the requested example set when complete, else the first three records."""

    available = {str(project["id"]) for project in projects}
    if all(project_id in available for project_id in PREFERRED_DEFAULT_IDS):
        return list(PREFERRED_DEFAULT_IDS)
    return [str(project["id"]) for project in projects[:3]]


def build_payload(
    projects: list[dict[str, Any]],
    manifest: dict[str, Any],
    *,
    latest_project_month: str | None,
    as_of: date | str | None = None,
) -> dict[str, Any]:
    """Join project identity and spatial evidence to committed shard metadata."""

    generated_on = _as_of_date(as_of)
    if len(projects) < MIN_PROJECTS:
        raise SystemExit(
            f"project exit comparison needs at least {MIN_PROJECTS} project records"
        )

    project_ids = [str(project.get("id", "")).strip() for project in projects]
    if any(not project_id for project_id in project_ids):
        raise SystemExit("project catalog contains a record without an id")
    if len(set(project_ids)) != len(project_ids):
        raise SystemExit("project catalog contains duplicate ids")

    manifest_projects = manifest["projects"]
    missing_manifest = [
        project_id for project_id in project_ids if project_id not in manifest_projects
    ]
    if missing_manifest:
        sample = ", ".join(missing_manifest[:5])
        suffix = "" if len(missing_manifest) <= 5 else ", …"
        raise SystemExit(
            f"transaction manifest is missing {len(missing_manifest)} project ids: "
            f"{sample}{suffix}"
        )

    output_projects: list[dict[str, Any]] = []
    for project in projects:
        transaction = manifest_projects[str(project["id"])]
        output_projects.append(
            {
                "id": project["id"],
                "selection_label": project["selection_label"],
                "name": project["project"],
                "street": project.get("street"),
                "district": project.get("district"),
                "planning_area": project.get("planning_area"),
                "tenure": project.get("tenure"),
                "property_type": project.get("property_type"),
                "transaction_shard": transaction.get("transaction_shard"),
                "transaction_count": transaction.get("transaction_count"),
                "transaction_first_month": transaction.get(
                    "transaction_first_month"
                ),
                "transaction_last_month": transaction.get("transaction_last_month"),
                "transaction_complete_through": transaction.get(
                    "transaction_complete_through"
                ),
                "station_display": project.get("station_display"),
                "station_distance_m": project.get("station_distance_m"),
                "station_status": project.get("station_status"),
                "location_source": project.get("location_source"),
                "primary_1km_count": project.get("primary_1km_count"),
                "primary_1km_schools": project.get("primary_1km_schools"),
                "best_primary_1km_school": project.get(
                    "best_primary_1km_school"
                ),
                "best_primary_1km_distance_m": project.get(
                    "best_primary_1km_distance_m"
                ),
                "school_metrics_source": project.get("school_metrics_source"),
            }
        )

    return {
        "schema": "project-exit-comparison.v1",
        "generated_as_of": generated_on.isoformat(),
        "latest_project_month": latest_project_month,
        "limits": {"min_projects": MIN_PROJECTS, "max_projects": MAX_PROJECTS},
        "defaults": _default_ids(projects),
        "transaction_schema": manifest["schema"],
        "transaction_enumerations": manifest["enumerations"],
        "source_metadata": manifest["source_metadata"],
        "sources": {
            "project_catalog": "data/inputs/ura_private.csv",
            "project_locations": "data/outputs/private_project_locations.csv",
            "school_metrics": "data/outputs/private_project_school_metrics.csv",
            "transaction_manifest": "site/assets/condo-transactions/manifest.json",
        },
        "projects": output_projects,
    }


def _project_options(projects: list[dict[str, Any]]) -> str:
    return "\n".join(
        "      <option "
        f'value="{html.escape(str(project["selection_label"]), quote=True)}" '
        f'data-project-id="{html.escape(str(project["id"]), quote=True)}"></option>'
        for project in projects
    )


def _project_slots(
    projects: list[dict[str, Any]], default_ids: list[str]
) -> str:
    by_id = {str(project["id"]): project for project in projects}
    slots = []
    for index, project_id in enumerate(default_ids, start=1):
        project = by_id[project_id]
        letter = chr(64 + index)
        slots.append(
            f'''      <div class="project-slot" data-project-slot>
        <span class="slot-label" aria-hidden="true">{letter}</span>
        <label for="project-slot-{index}">
          <span>Project {letter}</span>
          <input id="project-slot-{index}" name="projects" type="search"
            class="project-picker" data-project-input
            data-project-id="{html.escape(project_id, quote=True)}"
            list="project-options" autocomplete="off" required
            value="{html.escape(str(project['selection_label']), quote=True)}">
        </label>
        <button class="remove-project" data-remove-project type="button"
          aria-label="Remove project {letter}">Remove</button>
      </div>'''
        )
    return "\n".join(slots)


def render_html(
    payload: dict[str, Any],
    *,
    template_path: pathlib.Path = DEFAULT_TEMPLATE,
) -> str:
    """Render the deterministic page shell from a prepared browser payload."""

    generated_on = _as_of_date(payload["generated_as_of"])
    projects = payload["projects"]
    defaults = payload["defaults"]
    planned_sale_year = generated_on.year + 5
    purchase_month = generated_on.strftime("%Y-%m")
    planned_sale_month = f"{planned_sale_year:04d}-{generated_on.month:02d}"
    latest_month = payload.get("latest_project_month") or "Unavailable"

    template = template_path.read_text(encoding="utf-8")
    replacements = {
        "__PROJECT_COUNT__": f"{len(projects):,}",
        "__PROJECT_COUNT_RAW__": str(len(projects)),
        "__GENERATED_DATE_ISO__": generated_on.isoformat(),
        "__GENERATED_DATE_LABEL__": f"{generated_on.day} {generated_on:%b %Y}",
        "__LATEST_PROJECT_MONTH__": html.escape(str(latest_month)),
        "__PURCHASE_MONTH__": purchase_month,
        "__PLANNED_SALE_MONTH__": planned_sale_month,
        "__PROJECT_OPTIONS__": _project_options(projects),
        "__DEFAULT_PROJECT_SLOTS__": _project_slots(projects, defaults),
        "__PROJECT_EXIT_DATA_JSON__": script_safe_json(payload),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    unresolved = [marker for marker in replacements if marker in template]
    if unresolved:
        raise RuntimeError(f"unresolved project-exit template markers: {unresolved}")
    return template


def generate(
    out_path: pathlib.Path = DEFAULT_OUT,
    *,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST,
    private_path: pathlib.Path = project_comparison.DEFAULT_PRIVATE,
    as_of: date | str | None = None,
) -> tuple[pathlib.Path, int]:
    """Load committed inputs and write the decision-lab shell."""

    generated_on = _as_of_date(as_of)
    projects, latest_project_month = project_comparison.load_projects_for_comparison(
        private_path=private_path
    )
    manifest = load_transaction_manifest(manifest_path)
    payload = build_payload(
        projects,
        manifest,
        latest_project_month=latest_project_month,
        as_of=generated_on,
    )
    out_path.write_text(render_html(payload), encoding="utf-8")
    return out_path, len(projects)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the private-project exit comparison decision lab"
    )
    parser.add_argument("--private", default=str(project_comparison.DEFAULT_PRIVATE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--as-of",
        help="Inject the generated date as YYYY-MM-DD for a deterministic render",
    )
    args = parser.parse_args()
    output, count = generate(
        pathlib.Path(args.out),
        manifest_path=pathlib.Path(args.manifest),
        private_path=pathlib.Path(args.private),
        as_of=args.as_of,
    )
    manifest = load_transaction_manifest(pathlib.Path(args.manifest))
    transaction_count = manifest["source_metadata"]["reconciliation"][
        "project_transaction_count"
    ]
    print(
        f"Written: {output} ({output.stat().st_size // 1024:,} KB, "
        f"{count:,} project records, {transaction_count:,} achieved transactions, "
        f"{MIN_PROJECTS}–{MAX_PROJECTS} selections)"
    )


if __name__ == "__main__":
    main()
