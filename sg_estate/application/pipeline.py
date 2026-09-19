"""Transactional orchestration for the canonical estate-model pipeline."""

from __future__ import annotations

import argparse
import csv
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
    ContractError,
    EMPLOYMENT,
    LEASE_RISK,
    LIVEABILITY,
    MASTER_OUTPUT,
    PROVISION,
    VALUE,
)
from sg_estate.paths import INPUT_DIR, OUTPUT_DIR, REPOSITORY_ROOT, RUNS_DIR
from sg_estate.source_receipts import (
    build_source_receipt,
    read_source_receipt,
    receipt_path_for,
    validate_receipt_for_output,
    write_source_receipt,
)
from sg_estate.ura_acquisition import acquisition_path_for, validate_acquisition_bundle


RUN_MANIFEST_SCHEMA_VERSION = 3
CATALOG_SCHEMA_VERSION = 1


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

LOCAL_DERIVED_SOURCE_IDENTITIES = {
    "hawker_v2.csv": "derived:data/inputs/markets.csv+curated-stall-counts",
    "coastal.csv": (
        "derived:data/inputs/estates.csv+curated-blue-infrastructure-anchors"
    ),
    "bca_permits.csv": "derived:data/inputs/pipeline_data.json",
}

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

# Source receipts are optional for historical committed inputs: absence means
# unknown provenance, never an inferred date. When a sidecar does exist, bind
# it to the exact canonical bytes and carry it into the promoted run manifest.
# mrt_layer_names is published with the rail layer for dashboard/report use even
# though the scoring pipeline consumes mrt_layer.csv directly.
OPTIONAL_SOURCE_RECEIPT_NAMES = (
    *SOURCE_INPUT_NAMES,
    "mrt_layer_names.csv",
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
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
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
            "source_receipts": {},
            "stages": [],
        }
        self._write_manifest()

    @classmethod
    def load_awaiting_review(cls, run_id: str) -> "TransactionalPipeline":
        """Reload one staged refresh run for an explicit reviewed promotion."""

        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("run id must be one run-directory name")
        runs_root = RUNS_DIR.resolve()
        run_dir = (RUNS_DIR / run_id).resolve(strict=True)
        if run_dir.parent != runs_root:
            raise ValueError("run id resolves outside the pipeline run directory")
        manifest_path = run_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid run manifest JSON: {manifest_path}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise ContractError(f"run manifest must be a JSON object: {manifest_path}")
        if manifest.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
            raise ContractError(
                f"run manifest schema_version must be {RUN_MANIFEST_SCHEMA_VERSION}"
            )
        if manifest.get("run_id") != run_id:
            raise ContractError("run manifest run_id does not match its directory")
        if manifest.get("status") != "awaiting_review":
            raise ContractError("only an awaiting_review run can be promoted")
        if manifest.get("refresh_derived") is not True:
            raise ContractError("reviewed promotion requires a refreshed derived-input run")
        as_of_year = manifest.get("as_of_year")
        if isinstance(as_of_year, bool) or not isinstance(as_of_year, int):
            raise ContractError("run manifest as_of_year must be an integer")

        pipeline = cls.__new__(cls)
        pipeline.as_of_year = as_of_year
        pipeline.refresh_derived = True
        pipeline.run_id = run_id
        pipeline.run_dir = run_dir
        pipeline.staged_inputs = run_dir / "inputs"
        pipeline.staged_outputs = run_dir / "outputs"
        pipeline.logs = run_dir / "logs"
        pipeline.manifest = manifest
        return pipeline

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

        # Evidence sidecars are part of the input snapshot whenever they exist.
        # Their schemas are validated separately, but hashing the exact bytes
        # prevents a different, still-valid receipt or URA acquisition manifest
        # from being substituted after the model run was staged.
        for name in OPTIONAL_SOURCE_RECEIPT_NAMES:
            sidecar = receipt_path_for(INPUT_DIR / name)
            if sidecar.is_file():
                result[sidecar.name] = _sha256(sidecar)
        ura_acquisition = acquisition_path_for(INPUT_DIR / "ura_private.csv")
        if ura_acquisition.is_file():
            result[ura_acquisition.name] = _sha256(ura_acquisition)
        return result

    def _write_manifest(self) -> None:
        path = self.run_dir / "manifest.json"
        path.write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _catalog_datasets(self) -> dict[str, dict[str, object]]:
        catalog_path = REPOSITORY_ROOT / "data" / "catalog.json"
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid data catalog JSON: {catalog_path}: {exc}") from exc
        if not isinstance(catalog, dict) or catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise ContractError(
                f"data catalog schema_version must be {CATALOG_SCHEMA_VERSION}"
            )
        datasets = catalog.get("datasets")
        if not isinstance(datasets, dict):
            raise ContractError("data catalog datasets must be a JSON object")
        catalog_entries: dict[str, dict[str, object]] = {}
        for name, entry in datasets.items():
            if not isinstance(name, str) or not isinstance(entry, dict):
                raise ContractError("data catalog datasets must map IDs to objects")
            catalog_entries[name] = entry
        for name in DERIVED_INPUT_NAMES:
            entry = catalog_entries.get(name)
            if not isinstance(entry, dict):
                raise ContractError(f"data catalog is missing dataset {name}")
            authority = entry.get("authority")
            zone = entry.get("zone")
            if not isinstance(authority, str) or not authority.strip():
                raise ContractError(f"data catalog dataset {name} has no authority")
            if zone not in {"derived", "ingested"}:
                raise ContractError(
                    f"data catalog dataset {name} must be derived or ingested"
                )
        return catalog_entries

    @staticmethod
    def _csv_row_count(path: Path) -> int:
        """Count non-empty data records independently of an ingester receipt."""

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ContractError(f"staged CSV has no header: {path}") from exc
            if not header or not any(value.strip() for value in header):
                raise ContractError(f"staged CSV has an empty header: {path}")
            return sum(
                1 for row in reader if row and any(value.strip() for value in row)
            )

    @classmethod
    def _artifact_row_count(cls, path: Path, dataset_id: str) -> int:
        """Count persisted records independently of producer metadata."""

        if path.suffix.lower() == ".csv":
            return cls._csv_row_count(path)
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ContractError(f"invalid staged JSON dataset: {path}: {exc}") from exc
            if dataset_id == "pipeline_data.json":
                records = payload.get("pipeline_items") if isinstance(payload, dict) else None
                if not isinstance(records, list):
                    raise ContractError(
                        f"{path} must contain a pipeline_items array for receipt validation"
                    )
                return len(records)
            if isinstance(payload, (list, dict)):
                return len(payload)
            raise ContractError(f"cannot count records in JSON dataset: {path}")
        raise ContractError(f"receipt row-count validation is unsupported for {path}")

    def _validate_receipt(
        self,
        name: str,
        receipt: dict[str, object],
        catalog_entry: dict[str, object],
        *,
        output: Path | None = None,
    ) -> dict[str, object]:
        output = output or self.staged_inputs / name
        validated = validate_receipt_for_output(
            receipt,
            output,
            source=f"source receipt for {name}",
        )
        if validated["dataset_id"] != name:
            raise ContractError(
                f"source receipt for {name}.dataset_id must be {name!r}"
            )
        expected_authority = catalog_entry["authority"]
        if validated["authority"] != expected_authority:
            raise ContractError(
                f"source receipt for {name}.authority must match data/catalog.json"
            )
        if validated["validation_status"] != "passed":
            raise ContractError(
                f"source receipt for {name}.validation_status must be 'passed'"
            )
        actual_rows = self._artifact_row_count(output, name)
        if validated["row_count"] != actual_rows:
            raise ContractError(
                f"source receipt for {name}.row_count does not match staged CSV: "
                f"expected {actual_rows}, got {validated['row_count']}"
            )
        return validated

    def _collect_source_receipts(self) -> dict[str, dict[str, object]]:
        catalog = self._catalog_datasets()
        expected_sidecars = {
            receipt_path_for(self.staged_inputs / name).name
            for name in DERIVED_INPUT_NAMES
        }
        actual_sidecars = {
            path.name for path in self.staged_inputs.glob("*.receipt.json")
        }
        if actual_sidecars != expected_sidecars:
            missing = sorted(expected_sidecars - actual_sidecars)
            unexpected = sorted(actual_sidecars - expected_sidecars)
            raise ContractError(
                "staged source receipt sidecars do not match derived inputs: "
                f"missing={missing}, unexpected={unexpected}"
            )

        receipts: dict[str, dict[str, object]] = {}
        for name in DERIVED_INPUT_NAMES:
            output = self.staged_inputs / name
            sidecar = receipt_path_for(output)
            receipt = read_source_receipt(sidecar, output_path=output)
            receipts[name] = self._validate_receipt(name, receipt, catalog[name])

        ura_output = INPUT_DIR / "ura_private.csv"
        ura_receipt = receipt_path_for(ura_output)
        ura_acquisition = acquisition_path_for(ura_output)
        if ura_acquisition.is_file() and not ura_receipt.is_file():
            raise ContractError(
                "ura_private.csv acquisition manifest exists without its "
                "digest-bound source receipt"
            )
        for name in OPTIONAL_SOURCE_RECEIPT_NAMES:
            output = INPUT_DIR / name
            sidecar = receipt_path_for(output)
            if not sidecar.is_file():
                continue
            entry = catalog.get(name)
            if not isinstance(entry, dict):
                raise ContractError(
                    f"source receipt exists for {name}, but data/catalog.json has no entry"
                )
            receipt = read_source_receipt(sidecar, output_path=output)
            receipts[name] = self._validate_receipt(
                name,
                receipt,
                entry,
                output=output,
            )
            if name == "ura_private.csv":
                acquisition = acquisition_path_for(output)
                if not acquisition.is_file():
                    raise ContractError(
                        "validated ura_private.csv receipt requires its reviewed "
                        "acquisition manifest sidecar"
                    )
                validate_acquisition_bundle(
                    output,
                    allowed_statuses=("complete",),
                )
        return receipts

    def _write_offline_receipts(self) -> None:
        catalog = self._catalog_datasets()
        for name in DERIVED_INPUT_NAMES:
            output = self.staged_inputs / name
            entry = catalog[name]
            receipt = build_source_receipt(
                output,
                dataset_id=name,
                authority=str(entry["authority"]),
                source_identity=f"committed:data/inputs/{name}",
                retrieved_at=None,
                coverage_start=None,
                coverage_end=None,
                row_count=self._csv_row_count(output),
                # Reuse copies already-published bytes without performing a
                # retrieval or recomputation in this run. Record that actual
                # acquisition mode, independently of the catalog's semantic
                # zone for the dataset.
                cache_state="offline",
                fallback_state="not_used",
                validation_status="passed",
            )
            write_source_receipt(output, receipt)

    def _write_local_derived_receipts(self) -> None:
        """Record deterministic pipeline transforms that perform no retrieval."""

        catalog = self._catalog_datasets()
        for name, source_identity in LOCAL_DERIVED_SOURCE_IDENTITIES.items():
            output = self.staged_inputs / name
            sidecar = receipt_path_for(output)
            if sidecar.exists():
                continue
            receipt = build_source_receipt(
                output,
                dataset_id=name,
                authority=str(catalog[name]["authority"]),
                source_identity=source_identity,
                retrieved_at=None,
                coverage_start=None,
                coverage_end=None,
                row_count=self._csv_row_count(output),
                cache_state="derived",
                fallback_state="not_used",
                validation_status="passed",
            )
            write_source_receipt(output, receipt)

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
            self._write_offline_receipts()
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

    def _record_validated_artifacts(self) -> None:
        current_inputs = self._hash_inputs()
        if self.manifest.get("inputs") != current_inputs:
            raise ContractError(
                "canonical source inputs or evidence sidecars changed during "
                "the pipeline run"
            )
        self.manifest["outputs"] = {
            name: _sha256(self.staged_outputs / name)
            for name in OUTPUT_NAMES
        }
        self.manifest["source_receipts"] = self._collect_source_receipts()
        self._write_manifest()

    def _revalidate_awaiting_review(self) -> None:
        """Fail closed if any reviewed-run evidence changed after staging."""

        catalog_path = REPOSITORY_ROOT / "data" / "catalog.json"
        catalog_hash = self.manifest.get("data_catalog_sha256")
        if catalog_hash != _sha256(catalog_path):
            raise ContractError(
                "data/catalog.json changed after staging; start a new refresh run"
            )
        # Parse and validate the relevant catalog entries independently of its
        # recorded digest so a malformed but consistently hashed catalog fails.
        self._catalog_datasets()

        recorded_code = self.manifest.get("code")
        if recorded_code != _code_state():
            raise ContractError(
                "pipeline code changed after staging; start a new refresh run"
            )

        recorded_inputs = self.manifest.get("inputs")
        current_inputs = self._hash_inputs()
        if recorded_inputs != current_inputs:
            raise ContractError(
                "canonical source inputs changed after staging; start a new refresh run"
            )

        recorded_outputs = self.manifest.get("outputs")
        if not isinstance(recorded_outputs, dict) or set(recorded_outputs) != set(OUTPUT_NAMES):
            raise ContractError("run manifest outputs must exactly match pipeline outputs")
        for name in OUTPUT_NAMES:
            output = self.staged_outputs / name
            if not output.is_file():
                raise FileNotFoundError(f"reviewed staged output is missing: {output}")
            if recorded_outputs[name] != _sha256(output):
                raise ContractError(f"run manifest output hash does not match {name}")

        recorded_receipts = self.manifest.get("source_receipts")
        if not isinstance(recorded_receipts, dict) or not set(
            DERIVED_INPUT_NAMES
        ).issubset(recorded_receipts):
            raise ContractError(
                "run manifest source_receipts must include every derived input"
            )
        catalog = self._catalog_datasets()
        sidecar_receipts = self._collect_source_receipts()
        if set(recorded_receipts) != set(sidecar_receipts):
            raise ContractError(
                "run manifest source_receipts no longer match current sidecars"
            )
        for name, sidecar_receipt in sidecar_receipts.items():
            manifest_receipt = recorded_receipts[name]
            if not isinstance(manifest_receipt, dict):
                raise ContractError(f"run manifest source receipt for {name} must be an object")
            output = (
                self.staged_inputs / name
                if name in DERIVED_INPUT_NAMES
                else INPUT_DIR / name
            )
            validated_manifest_receipt = self._validate_receipt(
                name,
                manifest_receipt,
                catalog[name],
                output=output,
            )
            if validated_manifest_receipt != sidecar_receipt:
                raise ContractError(
                    f"run manifest source receipt does not match staged sidecar for {name}"
                )

        self._validate()

    def _promotions(self) -> list[tuple[Path, Path]]:
        promotions: list[tuple[Path, Path]] = []
        for name in DERIVED_INPUT_NAMES:
            staged_input = self.staged_inputs / name
            promotions.append((staged_input, INPUT_DIR / name))
            promotions.append(
                (
                    receipt_path_for(staged_input),
                    receipt_path_for(INPUT_DIR / name),
                )
            )
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
        if backup_dir.exists():
            raise FileExistsError(
                f"promotion backup directory already exists: {backup_dir}"
            )
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
            try:
                for target, backup, source in reversed(completed):
                    if target.exists():
                        os.replace(target, source)
                    if backup and backup.exists():
                        os.replace(backup, target)
            finally:
                shutil.rmtree(backup_dir, ignore_errors=True)
            raise
        shutil.rmtree(backup_dir)

    def promote_reviewed(self) -> Path:
        """Revalidate and atomically promote an explicitly reviewed refresh."""

        self._revalidate_awaiting_review()
        awaiting_manifest = dict(self.manifest)
        self.manifest["status"] = "complete"
        self.manifest["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        self.manifest["completed_at"] = self.manifest["reviewed_at"]
        self._write_manifest()
        try:
            self._promote()
        except Exception:
            self.manifest = awaiting_manifest
            self._write_manifest()
            raise
        print(f"[{self.run_id}] promoted reviewed pipeline run", flush=True)
        return OUTPUT_DIR / "run_manifest.json"

    def run(self) -> Path:
        try:
            for stage in self._derived_stages():
                self._run_stage(stage)
            if self.refresh_derived:
                self._write_local_derived_receipts()
            for stage in self._model_stages():
                self._run_stage(stage)
            self._validate()
            self._record_validated_artifacts()
            if self.refresh_derived:
                self.manifest["status"] = "awaiting_review"
                self.manifest["staged_at"] = datetime.now(timezone.utc).isoformat()
                self._write_manifest()
                print(
                    f"[{self.run_id}] staged refresh awaiting explicit review; "
                    "canonical files were not changed",
                    flush=True,
                )
                return self.run_dir / "manifest.json"

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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--reuse-derived",
        action="store_true",
        help="Reuse committed derived inputs for an offline deterministic rebuild.",
    )
    mode.add_argument(
        "--promote-run",
        "--promote-reviewed",
        dest="promote_run",
        metavar="RUN_ID",
        help=(
            "Revalidate and atomically promote one reviewed run currently in "
            "awaiting_review state."
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.promote_run:
        pipeline = TransactionalPipeline.load_awaiting_review(args.promote_run)
        manifest = pipeline.promote_reviewed()
        print(f"Run manifest: {manifest}")
        return
    pipeline = TransactionalPipeline(
        as_of_year=args.as_of_year,
        refresh_derived=not args.reuse_derived,
    )
    manifest = pipeline.run()
    print(f"Run manifest: {manifest}")


if __name__ == "__main__":
    main()
