"""Executable DataFrame contracts for pipeline boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from sg_estate.domain.framework import BAND_EDGES, PROVISION_WEIGHTS


class ContractError(ValueError):
    """Raised when a pipeline dataset violates its declared contract."""


@dataclass(frozen=True)
class DataFrameContract:
    required: frozenset[str]
    unique: tuple[tuple[str, ...], ...] = ()
    numeric_ranges: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    allowed_values: Mapping[str, frozenset[object]] = field(default_factory=dict)

    def validate(self, frame: pd.DataFrame, *, source: str = "dataframe") -> pd.DataFrame:
        missing = sorted(self.required - set(frame.columns))
        if missing:
            raise ContractError(f"{source} missing required columns: {missing}")

        for columns in self.unique:
            duplicate_mask = frame.duplicated(list(columns), keep=False)
            if duplicate_mask.any():
                examples = (
                    frame.loc[duplicate_mask, list(columns)]
                    .drop_duplicates()
                    .head(5)
                    .to_dict("records")
                )
                raise ContractError(
                    f"{source} has duplicate key {columns}: {examples}"
                )

        for column, (minimum, maximum) in self.numeric_ranges.items():
            if column not in frame:
                continue
            numeric = pd.to_numeric(frame[column], errors="coerce")
            invalid_type = frame[column].notna() & numeric.isna()
            if invalid_type.any():
                raise ContractError(f"{source}.{column} contains non-numeric values")
            outside = numeric.notna() & ~numeric.between(minimum, maximum)
            if outside.any():
                values = sorted(numeric.loc[outside].unique())[:5]
                raise ContractError(
                    f"{source}.{column} outside [{minimum}, {maximum}]: {values}"
                )

        for column, allowed in self.allowed_values.items():
            if column not in frame:
                continue
            invalid = frame[column].dropna().loc[lambda values: ~values.isin(allowed)]
            if not invalid.empty:
                values = sorted({str(value) for value in invalid.unique()})[:5]
                raise ContractError(f"{source}.{column} has invalid values: {values}")

        return frame

    def read_csv(self, path: str | Path, **kwargs) -> pd.DataFrame:
        frame = pd.read_csv(path, **kwargs)
        return self.validate(frame, source=str(path))


def require_estate_coverage(
    spine: Iterable[object],
    candidate: Iterable[object],
    *,
    source: str,
    allow_missing: bool = True,
) -> set[str]:
    """Validate that a candidate dataset does not introduce unknown estates."""

    expected = {str(value).strip().upper() for value in spine}
    actual = {str(value).strip().upper() for value in candidate}
    unknown = actual - expected
    if unknown:
        raise ContractError(f"{source} contains unknown estates: {sorted(unknown)}")
    missing = expected - actual
    if missing and not allow_missing:
        raise ContractError(f"{source} missing estates: {sorted(missing)}")
    return missing


ESTATES = DataFrameContract(
    required=frozenset({"estate", "lat", "lon"}),
    unique=(("estate",),),
    numeric_ranges={"lat": (-90.0, 90.0), "lon": (-180.0, 180.0)},
)

POINT_LAYER = DataFrameContract(
    required=frozenset({"lat", "lon"}),
    numeric_ranges={"lat": (-90.0, 90.0), "lon": (-180.0, 180.0)},
)

SCORE_BASE = DataFrameContract(
    required=frozenset({"estate", "score"}),
    unique=(("estate",),),
    numeric_ranges={"score": (1.0, 5.0)},
)

PROVISION = DataFrameContract(
    required=frozenset(
        {"estate", "score", "score_private", "band", *PROVISION_WEIGHTS.keys()}
    ),
    unique=(("estate",),),
    numeric_ranges={
        **{component: (1.0, 5.0) for component in PROVISION_WEIGHTS},
        "score": (1.0, 5.0),
        "score_private": (1.0, 5.0),
    },
    allowed_values={"band": frozenset(label for _, label in BAND_EDGES)},
)

MASTER_PROVISION = DataFrameContract(
    required=frozenset({"estate", "score_private", "measured_only"}),
    unique=(("estate",),),
    numeric_ranges={"score_private": (1.0, 5.0)},
)

LIVEABILITY = DataFrameContract(
    required=frozenset(
        {
            "estate",
            "archetype",
            "provision_score",
            "provision_band",
            "D_T0",
            "D_T5",
            "D_T15",
        }
    ),
    unique=(("estate",),),
    numeric_ranges={
        "provision_score": (1.0, 5.0),
        "D_T0": (0.70, 1.0),
        "D_T5": (0.70, 1.0),
        "D_T15": (0.70, 1.0),
    },
)

VALUE = DataFrameContract(
    required=frozenset(
        {"estate", "segment", "n", "value_score", "value_band", "value_basis"}
    ),
    unique=(("estate", "segment"),),
    numeric_ranges={"n": (0.0, float("inf")), "value_score": (0.0, 10.0)},
)

EMPLOYMENT = DataFrameContract(
    required=frozenset(
        {"estate", "emp_score", "emp_band", "best_node", "worst_node"}
    ),
    unique=(("estate",),),
    numeric_ranges={"emp_score": (1.0, 5.0)},
)

LEASE_RISK = DataFrameContract(
    required=frozenset(
        {"estate", "lease_score", "lease_band", "source"}
    ),
    unique=(("estate",),),
    numeric_ranges={"lease_score": (1.0, 5.0)},
)

ARCHETYPES = DataFrameContract(
    required=frozenset({"estate", "archetype", "confidence"}),
    unique=(("estate",),),
)

MASTER_OUTPUT = DataFrameContract(
    required=frozenset(
        {
            "estate",
            "model_version",
            "provision_score",
            "provision_band",
            "provision_private_status",
            "value_hdb_status",
            "employment_status",
            "lease_status",
            "value_private_status",
        }
    ),
    unique=(("estate",),),
    numeric_ranges={
        "provision_score": (1.0, 5.0),
        "value_hdb_score": (0.0, 10.0),
        "emp_score": (1.0, 5.0),
        "lease_score": (1.0, 5.0),
        "value_private_score": (0.0, 10.0),
    },
    allowed_values={
        column: frozenset(
            {"available", "no_data", "not_covered", "not_applicable"}
        )
        for column in (
            "provision_private_status",
            "value_hdb_status",
            "employment_status",
            "lease_status",
            "value_private_status",
        )
    },
)

__all__ = [
    "ARCHETYPES",
    "EMPLOYMENT",
    "ESTATES",
    "LEASE_RISK",
    "LIVEABILITY",
    "MASTER_OUTPUT",
    "MASTER_PROVISION",
    "POINT_LAYER",
    "PROVISION",
    "SCORE_BASE",
    "VALUE",
    "ContractError",
    "DataFrameContract",
    "require_estate_coverage",
]
