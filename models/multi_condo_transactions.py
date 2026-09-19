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
import os
import pathlib
import re
import shutil
import tempfile
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
_DATASET_REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = {
    "dataset_revision",
    "schema",
    "enumerations",
    "source_metadata",
    "shard_count",
    "shards",
    "projects",
}
_SHARD_KEYS = {
    "dataset_revision",
    "schema",
    "enumerations",
    "source_metadata",
    "shard_metadata",
    "projects",
}
_PROJECT_MANIFEST_KEYS = {
    "transaction_shard",
    "transaction_count",
    "canonical_transaction_count",
    "backfill_transaction_count",
    "transaction_first_month",
    "transaction_last_month",
    "transaction_complete_through",
}


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


def _shard_asset_path(index: int, dataset_revision: str | None = None) -> str:
    revision_segment = f"/{dataset_revision}" if dataset_revision else ""
    return f"{ASSET_PREFIX}{revision_segment}/shard-{index:02d}.json"


def shard_path(project_id: str, dataset_revision: str | None = None) -> str:
    return _shard_asset_path(shard_index(project_id), dataset_revision)


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


def _canonical_json(payload: Any) -> str:
    """Return the one canonical JSON representation used for hashes and files."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _logical_revision_payload(
    shards: Mapping[int, Mapping[str, Any]], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Remove publication-derived fields while preserving all logical content."""
    logical_manifest = copy.deepcopy(dict(manifest))
    logical_manifest.pop("dataset_revision", None)
    manifest_projects = logical_manifest.get("projects")
    if isinstance(manifest_projects, Mapping):
        for project_id, metadata in manifest_projects.items():
            if isinstance(metadata, dict):
                metadata["transaction_shard"] = shard_path(str(project_id))
    inventory = logical_manifest.get("shards")
    if isinstance(inventory, list):
        for entry in inventory:
            if isinstance(entry, dict) and type(entry.get("index")) is int:
                entry["path"] = _shard_asset_path(entry["index"])

    logical_shards = []
    for index in range(SHARD_COUNT):
        shard = copy.deepcopy(dict(shards[index]))
        shard.pop("dataset_revision", None)
        logical_shards.append(shard)
    return {"manifest": logical_manifest, "shards": logical_shards}


def compute_dataset_revision(
    shards: Mapping[int, Mapping[str, Any]], manifest: Mapping[str, Any]
) -> str:
    """Hash normalized logical manifest and ordered shard content.

    The revision and revision-derived asset paths are excluded to avoid a
    self-referential digest. Dictionary keys are sorted and shards are ordered
    by their fixed numeric index before hashing.
    """
    normalized = _canonical_json(_logical_revision_payload(shards, manifest))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _require_revision(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DATASET_REVISION_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 hex string")
    return value


def validate_transaction_bundle(
    shards: Mapping[int, Mapping[str, Any]], manifest: Mapping[str, Any]
) -> None:
    """Validate the exact 64-shard publication contract and its revision."""
    if set(shards) != set(range(SHARD_COUNT)):
        raise ValueError(f"expected exactly shard indexes 0..{SHARD_COUNT - 1}")
    if not isinstance(manifest, Mapping) or set(manifest) != _MANIFEST_KEYS:
        raise ValueError(f"manifest keys must be exactly {sorted(_MANIFEST_KEYS)}")

    revision = _require_revision(
        manifest.get("dataset_revision"), "manifest dataset_revision"
    )
    if manifest.get("schema") != SCHEMA:
        raise ValueError("manifest schema does not match the transaction schema")
    if manifest.get("shard_count") != SHARD_COUNT:
        raise ValueError(f"manifest shard_count must be {SHARD_COUNT}")

    enumerations = manifest.get("enumerations")
    expected_enumerations = set(ENUMERATED_FIELDS.values())
    if not isinstance(enumerations, Mapping) or set(enumerations) != expected_enumerations:
        raise ValueError(
            f"manifest enumerations must be exactly {sorted(expected_enumerations)}"
        )
    for name, values in enumerations.items():
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) for value in values)
            or len(values) != len(set(values))
        ):
            raise ValueError(f"manifest enumeration {name!r} must contain unique strings")

    source_metadata = manifest.get("source_metadata")
    if not isinstance(source_metadata, Mapping):
        raise ValueError("manifest source_metadata must be an object")
    manifest_projects = manifest.get("projects")
    if not isinstance(manifest_projects, Mapping):
        raise ValueError("manifest projects must be an object")
    if any(not isinstance(project_id, str) or not project_id for project_id in manifest_projects):
        raise ValueError("manifest project IDs must be non-empty strings")

    inventory = manifest.get("shards")
    if not isinstance(inventory, list) or len(inventory) != SHARD_COUNT:
        raise ValueError(f"manifest shards must contain exactly {SHARD_COUNT} entries")

    source_positions = {
        field: RECORD_FIELDS.index(field) for field in ENUMERATED_FIELDS
    }
    month_position = RECORD_FIELDS.index("sale_month")
    data_source_position = RECORD_FIELDS.index("data_source")
    data_source_values = enumerations[ENUMERATED_FIELDS["data_source"]]
    total_transactions = 0
    total_canonical = 0
    total_backfill = 0
    expected_inventory = []

    complete_through = None
    canonical_metadata = source_metadata.get("canonical")
    if isinstance(canonical_metadata, Mapping):
        complete_through = canonical_metadata.get("complete_through")

    for index in range(SHARD_COUNT):
        shard = shards[index]
        if not isinstance(shard, Mapping) or set(shard) != _SHARD_KEYS:
            raise ValueError(
                f"shard {index:02d} keys must be exactly {sorted(_SHARD_KEYS)}"
            )
        if shard.get("dataset_revision") != revision:
            raise ValueError(f"shard {index:02d} dataset_revision does not match manifest")
        if shard.get("schema") != SCHEMA:
            raise ValueError(f"shard {index:02d} schema does not match manifest")
        if shard.get("enumerations") != enumerations:
            raise ValueError(f"shard {index:02d} enumerations do not match manifest")
        if shard.get("source_metadata") != source_metadata:
            raise ValueError(f"shard {index:02d} source_metadata does not match manifest")

        shard_projects = shard.get("projects")
        if not isinstance(shard_projects, Mapping):
            raise ValueError(f"shard {index:02d} projects must be an object")
        expected_project_ids = sorted(
            project_id
            for project_id in manifest_projects
            if shard_index(project_id) == index
        )
        if set(shard_projects) != set(expected_project_ids):
            raise ValueError(f"shard {index:02d} project membership does not match manifest")

        shard_transaction_count = 0
        for project_id in expected_project_ids:
            records = shard_projects[project_id]
            if not isinstance(records, list):
                raise ValueError(f"project {project_id!r} records must be a list")

            months = []
            canonical_count = 0
            backfill_count = 0
            for record in records:
                if not isinstance(record, list) or len(record) != len(RECORD_FIELDS):
                    raise ValueError(
                        f"project {project_id!r} record does not match positional schema"
                    )
                for field, enum_name in ENUMERATED_FIELDS.items():
                    enum_index = record[source_positions[field]]
                    if enum_index is None:
                        continue
                    if (
                        type(enum_index) is not int
                        or not 0 <= enum_index < len(enumerations[enum_name])
                    ):
                        raise ValueError(
                            f"project {project_id!r} has invalid {field} enumeration"
                        )
                month = record[month_position]
                if _month(month) != month:
                    raise ValueError(f"project {project_id!r} has an invalid sale_month")
                months.append(month)
                source_index = record[data_source_position]
                if type(source_index) is not int or not 0 <= source_index < len(data_source_values):
                    raise ValueError(f"project {project_id!r} has no valid data_source")
                data_source = data_source_values[source_index]
                if data_source == "ura_private":
                    canonical_count += 1
                elif data_source == "edgeprop_backfill":
                    backfill_count += 1
                else:
                    raise ValueError(
                        f"project {project_id!r} has unsupported data_source {data_source!r}"
                    )

            expected_project_metadata = {
                "transaction_shard": shard_path(project_id, revision),
                "transaction_count": len(records),
                "canonical_transaction_count": canonical_count,
                "backfill_transaction_count": backfill_count,
                "transaction_first_month": min(months, default=None),
                "transaction_last_month": max(months, default=None),
                "transaction_complete_through": complete_through,
            }
            metadata = manifest_projects[project_id]
            if (
                not isinstance(metadata, Mapping)
                or set(metadata) != _PROJECT_MANIFEST_KEYS
                or dict(metadata) != expected_project_metadata
            ):
                raise ValueError(f"project {project_id!r} manifest metadata is inconsistent")

            shard_transaction_count += len(records)
            total_canonical += canonical_count
            total_backfill += backfill_count

        expected_shard_metadata = {
            "index": index,
            "project_count": len(expected_project_ids),
            "transaction_count": shard_transaction_count,
        }
        if shard.get("shard_metadata") != expected_shard_metadata:
            raise ValueError(f"shard {index:02d} metadata is inconsistent")
        expected_inventory.append(
            {
                "index": index,
                "path": _shard_asset_path(index, revision),
                "project_count": len(expected_project_ids),
                "transaction_count": shard_transaction_count,
            }
        )
        total_transactions += shard_transaction_count

    if inventory != expected_inventory:
        raise ValueError("manifest shard inventory is inconsistent")

    expected_reconciliation = {
        "project_transaction_count": total_transactions,
        "shard_transaction_count": total_transactions,
        "matches": True,
    }
    if source_metadata.get("reconciliation") != expected_reconciliation:
        raise ValueError("manifest transaction reconciliation is inconsistent")
    counts = source_metadata.get("counts")
    if not isinstance(counts, Mapping):
        raise ValueError("manifest source counts must be an object")
    if counts.get("canonical_included_rows") != total_canonical:
        raise ValueError("canonical included count does not match shard records")
    if counts.get("backfill_included_rows") != total_backfill:
        raise ValueError("backfill included count does not match shard records")

    calculated_revision = compute_dataset_revision(shards, manifest)
    if calculated_revision != revision:
        raise ValueError(
            "dataset_revision does not match normalized manifest and shard contents"
        )


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
        "shard_count": SHARD_COUNT,
        "shards": [
            {
                "index": index,
                "path": _shard_asset_path(index),
                "project_count": shards[index]["shard_metadata"]["project_count"],
                "transaction_count": shards[index]["shard_metadata"][
                    "transaction_count"
                ],
            }
            for index in range(SHARD_COUNT)
        ],
        "projects": project_manifest,
    }
    revision = compute_dataset_revision(shards, manifest)
    manifest["dataset_revision"] = revision
    for entry in manifest["shards"]:
        entry["path"] = _shard_asset_path(entry["index"], revision)
    for project in copied_projects:
        path = shard_path(project["id"], revision)
        project["transaction_shard"] = path
        manifest["projects"][project["id"]]["transaction_shard"] = path
    for shard in shards.values():
        shard["dataset_revision"] = revision

    validate_transaction_bundle(shards, manifest)
    return copied_projects, shards, manifest


def write_shards(
    output_dir: pathlib.Path | str,
    shards: Mapping[int, Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> list[pathlib.Path]:
    """Atomically publish one immutable revision and switch the root manifest.

    A complete bundle is written and reread from a staging directory first.
    Promotion renames that directory to ``<output_dir>/<dataset_revision>``.
    The unversioned root manifest is atomically replaced only after the bundle
    is durable, so an interrupted publication leaves its previous revision
    usable. Existing revision directories, legacy root shards, and unrelated
    files are retained.

    The returned paths are the 64 immutable shards, their bundle manifest, and
    the root manifest, in that order.
    """
    validate_transaction_bundle(shards, manifest)
    directory = pathlib.Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    revision = str(manifest["dataset_revision"])
    target = directory / revision
    staging = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{revision}.staging-", dir=directory)
    )
    root_temporary: pathlib.Path | None = None

    try:
        for index in range(SHARD_COUNT):
            _write_json_file(staging / f"shard-{index:02d}.json", shards[index])
        _write_json_file(staging / "manifest.json", manifest)
        _validate_bundle_directory(staging, shards, manifest)
        _fsync_directory(staging)

        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise ValueError(
                    f"revision target exists but is not a directory: {target}"
                )
            _validate_bundle_directory(target, shards, manifest)
            shutil.rmtree(staging)
            staging = target
        else:
            try:
                os.replace(staging, target)
                staging = target
            except OSError:
                # A concurrent publisher of identical content may win the
                # target name between the existence check and rename.
                if target.is_dir() and not target.is_symlink():
                    _validate_bundle_directory(target, shards, manifest)
                    shutil.rmtree(staging)
                    staging = target
                else:
                    raise

        _fsync_directory(directory)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".manifest-", suffix=".json.tmp", dir=directory
        )
        os.close(descriptor)
        root_temporary = pathlib.Path(temporary_name)
        _write_json_file(root_temporary, manifest)
        if json.loads(root_temporary.read_text(encoding="utf-8")) != dict(manifest):
            raise ValueError("staged root manifest does not match generated manifest")
        os.replace(root_temporary, directory / "manifest.json")
        root_temporary = None
        _fsync_directory(directory)
    finally:
        if root_temporary is not None:
            root_temporary.unlink(missing_ok=True)
        if staging != target and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return [
        *(target / f"shard-{index:02d}.json" for index in range(SHARD_COUNT)),
        target / "manifest.json",
        directory / "manifest.json",
    ]


def _write_json_file(path: pathlib.Path, payload: Mapping[str, Any]) -> None:
    serialized = _canonical_json(payload)
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def _validate_bundle_directory(
    directory: pathlib.Path,
    shards: Mapping[int, Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> None:
    expected_names = {
        *(f"shard-{index:02d}.json" for index in range(SHARD_COUNT)),
        "manifest.json",
    }
    actual_names = {path.name for path in directory.iterdir()}
    if actual_names != expected_names:
        raise ValueError(
            f"staged transaction bundle membership mismatch in {directory}"
        )

    loaded_shards = {}
    for index in range(SHARD_COUNT):
        path = directory / f"shard-{index:02d}.json"
        loaded_shards[index] = json.loads(path.read_text(encoding="utf-8"))
    loaded_manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    validate_transaction_bundle(loaded_shards, loaded_manifest)
    if _canonical_json(loaded_shards) != _canonical_json(dict(shards)):
        raise ValueError("staged shard payloads do not match generated shards")
    if _canonical_json(loaded_manifest) != _canonical_json(dict(manifest)):
        raise ValueError("staged manifest does not match generated manifest")


def _fsync_directory(directory: pathlib.Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
