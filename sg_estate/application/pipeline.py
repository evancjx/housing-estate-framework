"""Transactional orchestration for the canonical estate-model pipeline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import time
from typing import Iterable

from sg_estate import DEFAULT_AS_OF_YEAR, MODEL_VERSION
from sg_estate.contracts import (
    EMPLOYMENT,
    LEASE_RISK,
    LIVEABILITY,
    MASTER_OUTPUT,
    PROVISION,
    VALUE,
)
from sg_estate.paths import INPUT_DIR, OUTPUT_DIR, REPOSITORY_ROOT, RUNS_DIR


@dataclass(frozen=True)
class Stage:
    name: str
    command: tuple[str, ...]


DERIVED_INPUT_NAMES = (
    "tree_canopy.csv",
    "hdb_density.csv",
    "hawker_v2.csv",
    "coastal.csv",
    "bca_permits.csv",
)

# Committed snapshots that a refresh stage may use when its primary external
# source is unavailable. They are hashed even though the staged output replaces
# them.
REFRESH_FALLBACK_INPUT_NAMES = ("tree_canopy.csv",)

PIPELINE_INGESTER_PATHS = (
    "models/ingest_tree_canopy.py",
    "models/ingest_hdb_density.py",
    "models/ingest_hawker_v2.py",
    "models/ingest_coastal.py",
    "models/ingest_bca_permits.py",
)

OUTPUT_NAMES = (
    "provision_scores.csv",
    "liveability_matrix.csv",
    "value_output.csv",
    "value_output_private.csv",
    "lease_risk.csv",
    "employment_scores_T0.csv",
    "employment_scores_T5.csv",
    "employment_scores_T15.csv",
    "employment_trajectory.csv",
    "life_paths.csv",
    "master_output.csv",
)

SOURCE_INPUT_NAMES = (
    "estates.csv",
    "parks.csv",
    "markets.csv",
    "pipeline_data.json",
    "mrt_layer.csv",
    "bus_routes.csv",
    "chas.csv",
    "polyclinics.csv",
    "schools.csv",
    "supermarkets.csv",
    "childcare.csv",
    "community.csv",
    "sport.csv",
    "flood_risk.csv",
    "expressways.csv",
    "air_noise_corridors.csv",
    "eldercare.csv",
    "covered_linkway.csv",
    "jtc_industrial.csv",
    "air_quality.csv",
    "town_council_kpi.json",
    "judged_inputs.csv",
    "archetype_assignments.csv",
    "hdb_resale.csv",
    "ura_private.csv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state() -> dict[str, object]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ("git", *args),
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD") or None,
        "dirty": bool(run("status", "--porcelain")),
    }


def _portable_command(command: tuple[str, ...]) -> str:
    values = []
    root = str(REPOSITORY_ROOT)
    for index, argument in enumerate(command):
        if index == 0:
            values.append("python")
        elif argument.startswith(root):
            values.append("." + argument[len(root):])
        else:
            values.append(argument)
    return shlex.join(values)


def _code_state() -> dict[str, str]:
    candidates = [
        REPOSITORY_ROOT / "pyproject.toml",
        REPOSITORY_ROOT / "requirements-dev.txt",
        *(REPOSITORY_ROOT / relative for relative in PIPELINE_INGESTER_PATHS),
    ]
    package_root = REPOSITORY_ROOT / "sg_estate"
    if package_root.is_dir():
        candidates.extend(package_root.rglob("*.py"))
        candidates.extend(package_root.rglob("*.html"))
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): _sha256(path)
        for path in sorted(set(candidates))
        if path.is_file()
    }


class TransactionalPipeline:
    def __init__(self, *, as_of_year: int, refresh_derived: bool = True) -> None:
        self.as_of_year = as_of_year
        self.refresh_derived = refresh_derived
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.run_id = f"{timestamp}-v{MODEL_VERSION}"
        self.run_dir = RUNS_DIR / self.run_id
        self.staged_inputs = self.run_dir / "inputs"
        self.staged_outputs = self.run_dir / "outputs"
        self.logs = self.run_dir / "logs"
        for directory in (
            self.staged_inputs,
            self.staged_outputs,
            self.logs,
            OUTPUT_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.manifest: dict[str, object] = {
            "schema_version": 2,
            "run_id": self.run_id,
            "status": "running",
            "model_version": MODEL_VERSION,
            "as_of_year": as_of_year,
            "refresh_derived": refresh_derived,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "git": _git_state(),
            "python_version": platform.python_version(),
            "code": _code_state(),
            "data_catalog_sha256": _sha256(REPOSITORY_ROOT / "data" / "catalog.json"),
            "inputs": self._hash_inputs(),
            "stages": [],
        }
        self._write_manifest()

    def _hash_inputs(self) -> dict[str, str]:
        result = {}
        names = list(SOURCE_INPUT_NAMES)
        if self.refresh_derived:
            names.extend(REFRESH_FALLBACK_INPUT_NAMES)
        else:
            names.extend(DERIVED_INPUT_NAMES)
        for name in names:
            path = INPUT_DIR / name
            if not path.is_file():
                raise FileNotFoundError(f"required pipeline input not found: {path}")
            result[name] = _sha256(path)
        return result

    def _write_manifest(self) -> None:
        path = self.run_dir / "manifest.json"
        path.write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _python_stage(self, name: str, module_path: str, *args: object) -> Stage:
        command = (sys.executable, str(REPOSITORY_ROOT / module_path))
        return Stage(name, command + tuple(str(arg) for arg in args))

    def _module_stage(self, name: str, module: str, *args: object) -> Stage:
        command = (sys.executable, "-m", module)
        return Stage(name, command + tuple(str(arg) for arg in args))

    def _derived_stages(self) -> list[Stage]:
        if not self.refresh_derived:
            for name in DERIVED_INPUT_NAMES:
                shutil.copy2(INPUT_DIR / name, self.staged_inputs / name)
            return []

        return [
            self._python_stage(
                "tree_canopy",
                "models/ingest_tree_canopy.py",
                "--estates", INPUT_DIR / "estates.csv",
                "--parks", INPUT_DIR / "parks.csv",
                "--out", self.staged_inputs / "tree_canopy.csv",
                "--mss-fallback", INPUT_DIR / "tree_canopy.csv",
            ),
            self._python_stage(
                "hdb_density",
                "models/ingest_hdb_density.py",
                "--estates", INPUT_DIR / "estates.csv",
                "--out", self.staged_inputs / "hdb_density.csv",
            ),
            self._python_stage(
                "hawker_v2",
                "models/ingest_hawker_v2.py",
                "--estates", INPUT_DIR / "estates.csv",
                "--markets", INPUT_DIR / "markets.csv",
                "--out", self.staged_inputs / "hawker_v2.csv",
            ),
            self._python_stage(
                "coastal",
                "models/ingest_coastal.py",
                "--estates", INPUT_DIR / "estates.csv",
                "--out", self.staged_inputs / "coastal.csv",
            ),
            self._python_stage(
                "bca_permits",
                "models/ingest_bca_permits.py",
                "--pipeline", INPUT_DIR / "pipeline_data.json",
                "--estates", INPUT_DIR / "estates.csv",
                "--year", self.as_of_year,
                "--out", self.staged_inputs / "bca_permits.csv",
            ),
        ]

    def _model_stages(self) -> list[Stage]:
        provision = self.staged_outputs / "provision_scores.csv"
        liveability = self.staged_outputs / "liveability_matrix.csv"
        return [
            self._module_stage(
                "provision",
                "sg_estate.domain.provision",
                "--estates", INPUT_DIR / "estates.csv",
                "--mrt", INPUT_DIR / "mrt_layer.csv",
                "--bus", INPUT_DIR / "bus_routes.csv",
                "--clinics", INPUT_DIR / "chas.csv",
                "--polyclinics", INPUT_DIR / "polyclinics.csv",
                "--schools", INPUT_DIR / "schools.csv",
                "--parks", INPUT_DIR / "parks.csv",
                "--markets", INPUT_DIR / "markets.csv",
                "--supermarkets", INPUT_DIR / "supermarkets.csv",
                "--childcare", INPUT_DIR / "childcare.csv",
                "--community", INPUT_DIR / "community.csv",
                "--sport", INPUT_DIR / "sport.csv",
                "--flood", INPUT_DIR / "flood_risk.csv",
                "--noise", INPUT_DIR / "expressways.csv",
                "--air_noise", INPUT_DIR / "air_noise_corridors.csv",
                "--eldercare", INPUT_DIR / "eldercare.csv",
                "--covered_linkway", INPUT_DIR / "covered_linkway.csv",
                "--jtc_industrial", INPUT_DIR / "jtc_industrial.csv",
                "--air_quality", INPUT_DIR / "air_quality.csv",
                "--tcmr", INPUT_DIR / "town_council_kpi.json",
                "--tree_canopy", self.staged_inputs / "tree_canopy.csv",
                "--hdb_density", self.staged_inputs / "hdb_density.csv",
                "--hawker_v2", self.staged_inputs / "hawker_v2.csv",
                "--coastal", self.staged_inputs / "coastal.csv",
                "--judged", INPUT_DIR / "judged_inputs.csv",
                "--out", provision,
            ),
            self._module_stage(
                "liveability",
                "sg_estate.domain.liveability",
                "--scores", provision,
                "--pipeline", INPUT_DIR / "pipeline_data.json",
                "--archetypes", INPUT_DIR / "archetype_assignments.csv",
                "--bca", self.staged_inputs / "bca_permits.csv",
                "--year", self.as_of_year,
                "--out", liveability,
            ),
            self._module_stage(
                "value_hdb",
                "sg_estate.domain.value",
                "--scores", provision,
                "--hdb", INPUT_DIR / "hdb_resale.csv",
                "--out", self.staged_outputs / "value_output.csv",
            ),
            self._module_stage(
                "value_private",
                "sg_estate.domain.value",
                "--scores", provision,
                "--hdb", INPUT_DIR / "hdb_resale.csv",
                "--private", INPUT_DIR / "ura_private.csv",
                "--out", self.staged_outputs / "value_output_private.csv",
            ),
            self._module_stage(
                "lease_risk",
                "sg_estate.domain.lease_risk",
                "--hdb", INPUT_DIR / "hdb_resale.csv",
                "--estates", INPUT_DIR / "estates.csv",
                "--out", self.staged_outputs / "lease_risk.csv",
            ),
            self._module_stage(
                "employment",
                "sg_estate.domain.employment",
                "--out-dir", self.staged_outputs,
            ),
            self._module_stage(
                "master",
                "sg_estate.application.master",
                "--liveability", liveability,
                "--provision", provision,
                "--value_hdb", self.staged_outputs / "value_output.csv",
                "--employment", self.staged_outputs / "employment_scores_T0.csv",
                "--lease", self.staged_outputs / "lease_risk.csv",
                "--archetypes", INPUT_DIR / "archetype_assignments.csv",
                "--value_private", self.staged_outputs / "value_output_private.csv",
                "--life_paths", self.staged_outputs / "life_paths.csv",
                "--out", self.staged_outputs / "master_output.csv",
            ),
        ]

    def _run_stage(self, stage: Stage) -> None:
        print(f"[{self.run_id}] starting {stage.name}", flush=True)
        started = time.monotonic()
        log_path = self.logs / f"{stage.name}.log"
        record: dict[str, object] = {
            "name": stage.name,
            "command": _portable_command(stage.command),
            "log": str(log_path.relative_to(self.run_dir)),
            "status": "running",
        }
        stages = self.manifest["stages"]
        assert isinstance(stages, list)
        stages.append(record)
        self._write_manifest()
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(
                stage.command,
                cwd=REPOSITORY_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        record["returncode"] = result.returncode
        record["status"] = "complete" if result.returncode == 0 else "failed"
        self._write_manifest()
        if result.returncode != 0:
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            raise RuntimeError(
                f"stage {stage.name} failed; see {log_path}\n" + "\n".join(tail)
            )
        print(f"[{self.run_id}] completed {stage.name}", flush=True)

    def _validate(self) -> None:
        PROVISION.read_csv(self.staged_outputs / "provision_scores.csv")
        LIVEABILITY.read_csv(self.staged_outputs / "liveability_matrix.csv")
        VALUE.read_csv(self.staged_outputs / "value_output.csv")
        VALUE.read_csv(self.staged_outputs / "value_output_private.csv")
        LEASE_RISK.read_csv(self.staged_outputs / "lease_risk.csv")
        for horizon in ("T0", "T5", "T15"):
            EMPLOYMENT.read_csv(
                self.staged_outputs / f"employment_scores_{horizon}.csv"
            )
        MASTER_OUTPUT.read_csv(self.staged_outputs / "master_output.csv")

    def _promotions(self) -> list[tuple[Path, Path]]:
        promotions = [
            (self.staged_inputs / name, INPUT_DIR / name)
            for name in DERIVED_INPUT_NAMES
        ]
        promotions.extend(
            (self.staged_outputs / name, OUTPUT_DIR / name)
            for name in OUTPUT_NAMES
        )
        manifest_stage = self.staged_outputs / "run_manifest.json"
        shutil.copy2(self.run_dir / "manifest.json", manifest_stage)
        promotions.append((manifest_stage, OUTPUT_DIR / "run_manifest.json"))
        return promotions

    def _promote(self) -> None:
        backup_dir = self.run_dir / "backup"
        backup_dir.mkdir()
        completed: list[tuple[Path, Path | None, Path]] = []
        try:
            for index, (source, target) in enumerate(self._promotions()):
                if not source.is_file():
                    raise FileNotFoundError(f"validated output missing before promotion: {source}")
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = None
                if target.exists():
                    backup = backup_dir / f"{index:02d}-{target.name}"
                    os.replace(target, backup)
                try:
                    os.replace(source, target)
                except Exception:
                    if backup and backup.exists():
                        os.replace(backup, target)
                    raise
                completed.append((target, backup, source))
        except Exception:
            for target, backup, source in reversed(completed):
                if target.exists():
                    os.replace(target, source)
                if backup and backup.exists():
                    os.replace(backup, target)
            raise
        shutil.rmtree(backup_dir)

    def run(self) -> Path:
        try:
            for stage in (*self._derived_stages(), *self._model_stages()):
                self._run_stage(stage)
            self._validate()
            self.manifest["outputs"] = {
                name: _sha256(self.staged_outputs / name)
                for name in OUTPUT_NAMES
            }
            self.manifest["status"] = "complete"
            self.manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._write_manifest()
            self._promote()
            print(f"[{self.run_id}] promoted complete pipeline run", flush=True)
            return OUTPUT_DIR / "run_manifest.json"
        except Exception as exc:
            self.manifest["status"] = "failed"
            self.manifest["error"] = str(exc)
            self.manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._write_manifest()
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-year", type=int, default=DEFAULT_AS_OF_YEAR)
    parser.add_argument(
        "--reuse-derived",
        action="store_true",
        help="Reuse committed derived inputs for an offline deterministic rebuild.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    pipeline = TransactionalPipeline(
        as_of_year=args.as_of_year,
        refresh_derived=not args.reuse_derived,
    )
    manifest = pipeline.run()
    print(f"Run manifest: {manifest}")


if __name__ == "__main__":
    main()
