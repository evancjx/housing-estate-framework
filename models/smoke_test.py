#!/usr/bin/env python3
"""
No-dependency smoke checks for the scoring pipeline.

This verifies the framework constants, reruns the deterministic local pipeline
into a temporary directory, and compares the outputs against committed canonical
CSVs in data/.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

try:
    from framework_config import (
        DATA_DIR,
        PERSONA_DELTAS,
        PERSONAS,
        PROVISION_WEIGHTS,
        ROOT_DIR,
        S_GROUPS,
        build_persona_weights,
        validate_framework_config,
    )
except ImportError:  # pragma: no cover - supports package-style imports
    from models.framework_config import (
        DATA_DIR,
        PERSONA_DELTAS,
        PERSONAS,
        PROVISION_WEIGHTS,
        ROOT_DIR,
        S_GROUPS,
        build_persona_weights,
        validate_framework_config,
    )


def run_cmd(args: list[str]) -> None:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        print(completed.stdout)
        raise SystemExit(completed.returncode)


def sorted_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    sort_cols = [c for c in ["estate", "segment"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df


def assert_csv_matches(generated: Path, committed: Path, atol: float = 1e-8) -> None:
    left = sorted_csv(generated)
    right = sorted_csv(committed)
    assert list(left.columns) == list(right.columns), (
        f"{committed} columns differ from generated output"
    )
    assert_frame_equal(left, right, check_exact=False, atol=atol, rtol=atol)


def validate_constants() -> None:
    validate_framework_config()
    assert abs(sum(PROVISION_WEIGHTS.values()) - 1.0) < 1e-9

    grouped = [component for components in S_GROUPS.values() for component in components]
    assert sorted(grouped) == sorted(PROVISION_WEIGHTS)
    assert len(grouped) == len(set(grouped))

    for group, deltas in PERSONA_DELTAS.items():
        assert group in S_GROUPS
        assert set(deltas) == set(PERSONAS)

    persona_weights = build_persona_weights()
    for persona, weights in persona_weights.items():
        assert set(weights) == set(PROVISION_WEIGHTS), persona
        assert min(weights.values()) >= 0, persona
        assert abs(sum(weights.values()) - 1.0) < 1e-9, persona


def main() -> None:
    validate_constants()

    with tempfile.TemporaryDirectory(prefix="estate-smoke-") as tmp:
        tmp_dir = Path(tmp)
        provision_out = tmp_dir / "provision_scores.csv"
        liveability_out = tmp_dir / "liveability_matrix.csv"
        value_out = tmp_dir / "value_output.csv"
        employment_dir = tmp_dir / "employment"

        run_cmd([
            "models/provision_model.py",
            "--estates", str(DATA_DIR / "estates.csv"),
            "--mrt", str(DATA_DIR / "mrt_layer.csv"),
            "--bus", str(DATA_DIR / "bus_routes.csv"),
            "--clinics", str(DATA_DIR / "chas.csv"),
            "--polyclinics", str(DATA_DIR / "polyclinics.csv"),
            "--schools", str(DATA_DIR / "schools.csv"),
            "--parks", str(DATA_DIR / "parks.csv"),
            "--markets", str(DATA_DIR / "markets.csv"),
            "--supermarkets", str(DATA_DIR / "supermarkets.csv"),
            "--childcare", str(DATA_DIR / "childcare.csv"),
            "--community", str(DATA_DIR / "community.csv"),
            "--sport", str(DATA_DIR / "sport.csv"),
            "--flood", str(DATA_DIR / "flood_risk.csv"),
            "--noise", str(DATA_DIR / "expressways.csv"),
            "--air_noise", str(DATA_DIR / "air_noise_corridors.csv"),
            "--eldercare", str(DATA_DIR / "eldercare.csv"),
            "--covered_linkway", str(DATA_DIR / "covered_linkway.csv"),
            "--judged", str(DATA_DIR / "judged_inputs.csv"),
            "--out", str(provision_out),
        ])
        assert_csv_matches(provision_out, DATA_DIR / "provision_scores.csv")

        run_cmd([
            "models/liveability_model.py",
            "--scores", str(provision_out),
            "--pipeline", str(DATA_DIR / "pipeline_data.json"),
            "--out", str(liveability_out),
        ])
        assert_csv_matches(liveability_out, DATA_DIR / "liveability_matrix.csv")

        run_cmd([
            "models/value_model.py",
            "--scores", str(provision_out),
            "--hdb", str(DATA_DIR / "hdb_resale.csv"),
            "--out", str(value_out),
        ])
        assert_csv_matches(value_out, DATA_DIR / "value_output.csv")

        run_cmd([
            "models/employment_model.py",
            "--out-dir", str(employment_dir),
        ])
        for filename in [
            "employment_scores_T0.csv",
            "employment_scores_T5.csv",
            "employment_scores_T15.csv",
            "employment_trajectory.csv",
        ]:
            assert_csv_matches(employment_dir / filename, DATA_DIR / filename)

    print("smoke ok")


if __name__ == "__main__":
    main()
