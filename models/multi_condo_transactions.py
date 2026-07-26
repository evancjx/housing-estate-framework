"""Build bounded, browser-safe transaction shards for multi-condo comparison.

The canonical URA frame owns modern transactions. Rows are assigned to a
prepared project only through the exact four-part identity used by the project
catalog: project, street, postal district, and planning area. Official
multiplicity is preserved; identical URA rows may be separate caveats.

Bedroom attribution is secondary evidence. It is joined by an occurrence-safe
transaction key so repeated rows cannot fan out. EdgeProp-only history is
limited to rows explicitly tagged ``edgeprop_backfill`` in 2019–20, and is
assigned only when normalized project name plus district identifies one
prepared project unambiguously.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from build_private_bedrooms import normalise_project_name

SQM_TO_SQFT = 10.7639
CANONICAL_START = "2021-06"
BACKFILL_PERIOD = ("2019-01", "2020-12")
KNOWN_GAP = ("2021-01", "2021-05")
SHARD_COUNT = 64
ASSET_PREFIX = "assets/condo-transactions"

# Positional records are deliberately allowlisted. Do not add project names,
# addresses, purchaser details, or scraper-only fields to browser output.
RECORD_FIELDS = [
    "sale_month",
    "price",
    "area_sqm",
    "area_sqft",
    "psf",
    "sale_type",
    "floor_level",
    "bedrooms",
    "bedroom_source",
    "data_source",
]
ENUMERATED_FIELDS = {
    "sale_type": "sale_types",
    "floor_level": "floor_levels",
    "bedroom_source": "bedroom_sources",
    "data_source": "data_sources",
}
SCHEMA = {
    "version": 1,
    "record_format": "positional_array",
    "fields": RECORD_FIELDS,
    "enumerated_fields": ENUMERATED_FIELDS,
}

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_BEDROOM_SOURCE_ORDER = [
    "unknown",
    "edgeprop_exact",
    "edgeprop_band_label",
    "research_unit_mix",
]
_DATA_SOURCE_ORDER = ["ura_private", "edgeprop_backfill"]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return " ".join(str(value).strip().split())


def _identity_text(value: Any) -> str:
    return _text(value).upper()


def _district(value: Any) -> str:
    digits = "".join(character for character in _text(value) if character.isdigit())
    return digits.zfill(2)[-2:] if digits else ""


def _month(value: Any) -> str | None:
    text = _text(value)
    match = _MONTH_RE.fullmatch(text)
    if not match or not 1 <= int(match.group(2)) <= 12:
        return None
    return text


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number) or number <= 0:
        return None
    return number


def _compact_number(value: float, places: int) -> int | float:
    rounded = round(float(value), places)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _bedroom(value: Any, source: Any) -> tuple[int | None, str]:
    source_text = _text(source) or "unknown"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "unknown"
    if pd.isna(number) or number <= 0 or not number.is_integer():
        return None, "unknown"
    if source_text == "unknown":
        return None, "unknown"
    return int(number), source_text


def _project_identity(
    project: Any, street: Any, district: Any, planning_area: Any
) -> tuple[str, str, str, str]:
    return (
        _identity_text(project),
        _identity_text(street),
        _district(district),
        _identity_text(planning_area),
    )


def _transaction_key(
    project: Any,
    district: Any,
    sale_month: Any,
    price: Any,
    area_sqm: Any,
) -> tuple[str, str, str, float, float] | None:
    month = _month(sale_month)
    price_number = _positive_number(price)
    area_number = _positive_number(area_sqm)
    project_norm = normalise_project_name(project)
    district_norm = _district(district)
    if (
        not project_norm
        or not district_norm
        or month is None
        or price_number is None
        or area_number is None
    ):
        return None
    return (
        project_norm,
        district_norm,
        month,
        round(price_number, 2),
        round(area_number, 4),
    )


def shard_index(project_id: str) -> int:
    """Return a stable 0..63 shard for a prepared project ID."""
    digest = hashlib.sha256(project_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % SHARD_COUNT


def shard_path(project_id: str) -> str:
    return f"{ASSET_PREFIX}/shard-{shard_index(project_id):02d}.json"


def _previous_month(month: str | None) -> str | None:
    if month is None:
        return None
    period = pd.Period(month, freq="M") - 1
    previous = str(period)
    return previous if previous >= CANONICAL_START else None


def _analysis_60_start(complete_end: str | None) -> str | None:
    if complete_end is None:
        return None
    start = str(pd.Period(complete_end, freq="M") - 59)
    return max(start, CANONICAL_START)


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _prepared_maps(
    projects: Sequence[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[tuple[str, str, str, str], str],
    dict[tuple[str, str], set[str]],
]:
    copied = [copy.deepcopy(dict(project)) for project in projects]
    project_ids = [_text(project.get("id")) for project in copied]
    if any(not project_id for project_id in project_ids):
        raise ValueError("every prepared project requires a non-empty id")
    duplicates = sorted(
        project_id for project_id, count in Counter(project_ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(f"prepared project IDs are not unique: {duplicates}")
    for project, project_id in zip(copied, project_ids):
        project["id"] = project_id

    identities: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    backfill_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    for project, project_id in zip(copied, project_ids):
        identity = _project_identity(
            project.get("project"),
            project.get("street"),
            project.get("district"),
            project.get("planning_area"),
        )
        if all(identity):
            identities[identity].add(project_id)
        name_key = (
            normalise_project_name(project.get("project")),
            _district(project.get("district")),
        )
        if all(name_key):
            backfill_names[name_key].add(project_id)

    exact = {
        identity: next(iter(ids))
        for identity, ids in identities.items()
        if len(ids) == 1
    }
    return copied, exact, backfill_names


def _bedroom_occurrences(
    bedrooms: pd.DataFrame,
) -> dict[tuple[tuple[str, str, str, float, float], int], tuple[int | None, str]]:
    occurrences: Counter[tuple[str, str, str, float, float]] = Counter()
    lookup = {}
    for row in bedrooms.to_dict("records"):
        if _text(row.get("data_source")) != "ura_private":
            continue
        key = _transaction_key(
            row.get("project_name"),
            row.get("postal_district"),
            row.get("sale_month"),
            row.get("transacted_price"),
            row.get("area_sqm"),
        )
        if key is None:
            continue
        occurrence = occurrences[key]
        occurrences[key] += 1
        lookup[(key, occurrence)] = _bedroom(
            row.get("bedrooms"), row.get("bedroom_source")
        )
    return lookup


def _record(
    *,
    month: str,
    price: float,
    area_sqm: float,
    sale_type: Any,
    floor_level: Any,
    bedrooms: int | None,
    bedroom_source: str,
    data_source: str,
    ordinal: int,
) -> dict[str, Any]:
    area_sqft = area_sqm * SQM_TO_SQFT
    return {
        "sale_month": month,
        "price": _compact_number(price, 2),
        "area_sqm": _compact_number(area_sqm, 4),
        "area_sqft": int(round(area_sqft)),
        "psf": _compact_number(price / area_sqft, 2),
        "sale_type": _text(sale_type) or "Unknown",
        "floor_level": _text(floor_level) or None,
        "bedrooms": bedrooms,
        "bedroom_source": bedroom_source,
        "data_source": data_source,
        "_ordinal": ordinal,
    }


def _enum_values(
    records_by_project: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[str]]:
    records = [
        record for project_records in records_by_project.values() for record in project_records
    ]

    def values(field: str) -> set[str]:
        return {
            str(record[field])
            for record in records
            if record.get(field) is not None
        }

    bedroom_sources = values("bedroom_source")
    ordered_bedroom_sources = [
        source for source in _BEDROOM_SOURCE_ORDER if source in bedroom_sources
    ]
    ordered_bedroom_sources.extend(
        sorted(bedroom_sources - set(ordered_bedroom_sources))
    )
    data_sources = values("data_source")
    ordered_data_sources = [
        source for source in _DATA_SOURCE_ORDER if source in data_sources
    ]
    ordered_data_sources.extend(sorted(data_sources - set(ordered_data_sources)))
    return {
        "sale_types": sorted(values("sale_type")),
        "floor_levels": sorted(values("floor_level")),
        "bedroom_sources": ordered_bedroom_sources,
        "data_sources": ordered_data_sources,
    }


def _encode_record(
    record: Mapping[str, Any], enumerations: Mapping[str, Sequence[str]]
) -> list[Any]:
    indexes = {
        enum_name: {value: index for index, value in enumerate(values)}
        for enum_name, values in enumerations.items()
    }
    encoded = []
    for field in RECORD_FIELDS:
        value = record.get(field)
        enum_name = ENUMERATED_FIELDS.get(field)
        if enum_name is not None and value is not None:
            value = indexes[enum_name][value]
        encoded.append(value)
    return encoded


def build_transaction_shards(
    raw_ura: pd.DataFrame,
    bedroom_output: pd.DataFrame,
    projects: Sequence[Mapping[str, Any]],
    *,
    shard_count: int = SHARD_COUNT,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any]]:
    """Return copied project rows, 64 shard payloads, and manifest metadata.

    The input frames and prepared project dictionaries are never mutated.
    """
    if shard_count != SHARD_COUNT:
        raise ValueError(f"transaction output is fixed at {SHARD_COUNT} shards")
    _require_columns(
        raw_ura,
        {
            "project_name",
            "street_name",
            "postal_district",
            "planning_area",
            "sale_month",
            "transacted_price",
            "area_sqm",
        },
        "raw URA transactions",
    )
    if not bedroom_output.empty:
        _require_columns(
            bedroom_output,
            {
                "project_name",
                "postal_district",
                "sale_month",
                "transacted_price",
                "area_sqm",
                "data_source",
                "bedrooms",
                "bedroom_source",
            },
            "bedroom output",
        )

    copied_projects, exact_identities, backfill_names = _prepared_maps(projects)
    records_by_project: dict[str, list[dict[str, Any]]] = {
        project["id"]: [] for project in copied_projects
    }
    bedroom_lookup = _bedroom_occurrences(bedroom_output)
    raw_occurrences: Counter[tuple[str, str, str, float, float]] = Counter()
    counts = {
        "canonical_input_rows": int(len(raw_ura)),
        "canonical_included_rows": 0,
        "canonical_invalid_rows": 0,
        "canonical_unmapped_rows": 0,
        "backfill_input_rows": 0,
        "backfill_included_rows": 0,
        "backfill_invalid_rows": 0,
        "backfill_unmapped_rows": 0,
        "backfill_ambiguous_rows": 0,
    }
    valid_canonical_months = []

    for ordinal, row in enumerate(raw_ura.to_dict("records")):
        key = _transaction_key(
            row.get("project_name"),
            row.get("postal_district"),
            row.get("sale_month"),
            row.get("transacted_price"),
            row.get("area_sqm"),
        )
        occurrence = None
        if key is not None:
            occurrence = raw_occurrences[key]
            raw_occurrences[key] += 1

        month = _month(row.get("sale_month"))
        price = _positive_number(row.get("transacted_price"))
        area_sqm = _positive_number(row.get("area_sqm"))
        if (
            key is None
            or month is None
            or month < CANONICAL_START
            or price is None
            or area_sqm is None
        ):
            counts["canonical_invalid_rows"] += 1
            continue
        valid_canonical_months.append(month)
        identity = _project_identity(
            row.get("project_name"),
            row.get("street_name"),
            row.get("postal_district"),
            row.get("planning_area"),
        )
        project_id = exact_identities.get(identity)
        if project_id is None:
            counts["canonical_unmapped_rows"] += 1
            continue
        bedroom_value, bedroom_source = bedroom_lookup.get(
            (key, occurrence), (None, "unknown")
        )
        records_by_project[project_id].append(
            _record(
                month=month,
                price=price,
                area_sqm=area_sqm,
                sale_type=row.get("type_of_sale"),
                floor_level=row.get("floor_level"),
                bedrooms=bedroom_value,
                bedroom_source=bedroom_source,
                data_source="ura_private",
                ordinal=ordinal,
            )
        )
        counts["canonical_included_rows"] += 1

    valid_backfill_months = []
    if not bedroom_output.empty:
        for offset, row in enumerate(bedroom_output.to_dict("records"), start=len(raw_ura)):
            if _text(row.get("data_source")) != "edgeprop_backfill":
                continue
            counts["backfill_input_rows"] += 1
            month = _month(row.get("sale_month"))
            price = _positive_number(row.get("transacted_price"))
            area_sqm = _positive_number(row.get("area_sqm"))
            name = normalise_project_name(row.get("project_name"))
            district = _district(row.get("postal_district"))
            if (
                month is None
                or not BACKFILL_PERIOD[0] <= month <= BACKFILL_PERIOD[1]
                or price is None
                or area_sqm is None
                or not name
                or not district
            ):
                counts["backfill_invalid_rows"] += 1
                continue
            valid_backfill_months.append(month)
            candidates = backfill_names.get((name, district), set())
            if len(candidates) > 1:
                counts["backfill_ambiguous_rows"] += 1
                continue
            if not candidates:
                counts["backfill_unmapped_rows"] += 1
                continue
            project_id = next(iter(candidates))
            bedroom_value, bedroom_source = _bedroom(
                row.get("bedrooms"), row.get("bedroom_source")
            )
            records_by_project[project_id].append(
                _record(
                    month=month,
                    price=price,
                    area_sqm=area_sqm,
                    sale_type=row.get("type_of_sale"),
                    floor_level=row.get("floor_level"),
                    bedrooms=bedroom_value,
                    bedroom_source=bedroom_source,
                    data_source="edgeprop_backfill",
                    ordinal=offset,
                )
            )
            counts["backfill_included_rows"] += 1

    latest_month = max(valid_canonical_months, default=None)
    complete_through = _previous_month(latest_month)
    source_metadata = {
        "canonical": {
            "source": "ura_private",
            "status": "canonical",
            "start_month": CANONICAL_START,
            "coverage_start": CANONICAL_START,
            "latest_month": latest_month,
            "partial_month": latest_month,
            "latest_month_partial": latest_month is not None,
            "complete_end": complete_through,
            "complete_through": complete_through,
            "analysis_60_start": _analysis_60_start(complete_through),
        },
        "historical_backfill": {
            "source": "edgeprop_backfill",
            "status": "incomplete",
            "period_start": BACKFILL_PERIOD[0],
            "period_end": BACKFILL_PERIOD[1],
            "observed_start": min(valid_backfill_months, default=None),
            "observed_end": max(valid_backfill_months, default=None),
        },
        "known_gap": {
            "status": "not_covered",
            "period_start": KNOWN_GAP[0],
            "period_end": KNOWN_GAP[1],
        },
        "counts": counts,
    }

    for project_id, records in records_by_project.items():
        records.sort(
            key=lambda record: (
                -int(record["sale_month"].replace("-", "")),
                record["_ordinal"],
            )
        )

    enumerations = _enum_values(records_by_project)
    encoded_by_project = {
        project_id: [
            _encode_record(record, enumerations) for record in project_records
        ]
        for project_id, project_records in records_by_project.items()
    }

    project_manifest = {}
    for project in copied_projects:
        project_id = project["id"]
        records = records_by_project[project_id]
        months = [record["sale_month"] for record in records]
        canonical_count = sum(
            record["data_source"] == "ura_private" for record in records
        )
        backfill_count = len(records) - canonical_count
        project_metadata = {
            "transaction_shard": shard_path(project_id),
            "transaction_count": len(records),
            "canonical_transaction_count": canonical_count,
            "backfill_transaction_count": backfill_count,
            "transaction_first_month": min(months, default=None),
            "transaction_last_month": max(months, default=None),
            "transaction_complete_through": complete_through,
        }
        project.update(project_metadata)
        project_manifest[project_id] = project_metadata

    shards: dict[int, dict[str, Any]] = {}
    for index in range(SHARD_COUNT):
        project_ids = sorted(
            project_id
            for project_id in encoded_by_project
            if shard_index(project_id) == index
        )
        shard_projects = {
            project_id: encoded_by_project[project_id] for project_id in project_ids
        }
        shards[index] = {
            "schema": copy.deepcopy(SCHEMA),
            "enumerations": copy.deepcopy(enumerations),
            "source_metadata": copy.deepcopy(source_metadata),
            "shard_metadata": {
                "index": index,
                "project_count": len(project_ids),
                "transaction_count": sum(
                    len(records) for records in shard_projects.values()
                ),
            },
            "projects": shard_projects,
        }

    project_total = sum(
        metadata["transaction_count"] for metadata in project_manifest.values()
    )
    shard_total = sum(
        shard["shard_metadata"]["transaction_count"] for shard in shards.values()
    )
    reconciliation = {
        "project_transaction_count": project_total,
        "shard_transaction_count": shard_total,
        "matches": project_total == shard_total,
    }
    source_metadata["reconciliation"] = reconciliation
    for shard in shards.values():
        shard["source_metadata"]["reconciliation"] = copy.deepcopy(reconciliation)

    manifest = {
        "schema": copy.deepcopy(SCHEMA),
        "enumerations": copy.deepcopy(enumerations),
        "source_metadata": copy.deepcopy(source_metadata),
        "projects": project_manifest,
    }
    return copied_projects, shards, manifest


def write_shards(
    output_dir: pathlib.Path | str,
    shards: Mapping[int, Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> list[pathlib.Path]:
    """Overwrite exactly shard-00..63 plus manifest; leave other files alone."""
    if set(shards) != set(range(SHARD_COUNT)):
        raise ValueError(f"expected exactly shard indexes 0..{SHARD_COUNT - 1}")
    directory = pathlib.Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for index in range(SHARD_COUNT):
        path = directory / f"shard-{index:02d}.json"
        path.write_text(
            json.dumps(shards[index], ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written.append(path)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written
