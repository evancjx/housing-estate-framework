"""Contracts shared by the authored and generated report catalogs."""

from __future__ import annotations


REPORT_CATALOG_SCHEMA_VERSION = 2
DATA_FAMILY_IDS = frozenset(
    {
        "estate_model",
        "private_transactions",
        "rail_network",
        "finance_assumptions",
        "market_research",
    }
)


def validate_data_families(value: object, *, source: str) -> list[str]:
    """Return a valid, non-empty and duplicate-free family-ID list."""

    if not isinstance(value, list) or not value:
        raise ValueError(f"{source} must be a non-empty list")
    if not all(isinstance(family_id, str) and family_id for family_id in value):
        raise ValueError(f"{source} must contain non-empty string identifiers")
    unknown = sorted(set(value) - DATA_FAMILY_IDS)
    if unknown:
        raise ValueError(
            f"{source} contains unknown data family identifiers: "
            f"{', '.join(unknown)}"
        )
    if len(value) != len(set(value)):
        raise ValueError(f"{source} must not contain duplicate identifiers")
    return value


__all__ = [
    "DATA_FAMILY_IDS",
    "REPORT_CATALOG_SCHEMA_VERSION",
    "validate_data_families",
]
