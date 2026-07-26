from pathlib import Path

import pytest

from sg_estate.application import pipeline as pipeline_module


def _configure_pipeline_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    inputs = root / "data" / "inputs"
    outputs = root / "data" / "outputs"
    runs = root / "data" / "runs"
    for directory in (inputs, outputs, runs):
        directory.mkdir(parents=True)
    (root / "data" / "catalog.json").write_text("{}\n", encoding="utf-8")
    for name in (
        *pipeline_module.SOURCE_INPUT_NAMES,
        *pipeline_module.DERIVED_INPUT_NAMES,
    ):
        (inputs / name).write_text(f"{name}\n", encoding="utf-8")
    monkeypatch.setattr(pipeline_module, "REPOSITORY_ROOT", root)
    monkeypatch.setattr(pipeline_module, "INPUT_DIR", inputs)
    monkeypatch.setattr(pipeline_module, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(pipeline_module, "RUNS_DIR", runs)
    return inputs, outputs, runs


def test_reuse_run_stages_derived_inputs_and_records_manifest(monkeypatch, tmp_path):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2030,
        refresh_derived=False,
    )
    assert pipeline._derived_stages() == []
    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (pipeline.staged_inputs / name).read_bytes() == (inputs / name).read_bytes()
    assert pipeline.manifest["as_of_year"] == 2030
    assert pipeline.manifest["refresh_derived"] is False
    assert pipeline.manifest["schema_version"] == 2
    assert pipeline.manifest["python_version"]
    assert isinstance(pipeline.manifest["code"], dict)
    assert len(pipeline.manifest["inputs"]) == (
        len(pipeline_module.SOURCE_INPUT_NAMES)
        + len(pipeline_module.DERIVED_INPUT_NAMES)
    )
    commands = " ".join(
        argument
        for stage in pipeline._model_stages()
        for argument in stage.command
    )
    assert "--year" in commands
    assert "2030" in commands


def test_promotion_replaces_complete_file_set(monkeypatch, tmp_path):
    _, outputs, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    for name in pipeline_module.OUTPUT_NAMES:
        (pipeline.staged_outputs / name).write_text(
            f"new-{name}\n", encoding="utf-8"
        )
    old_output = outputs / "provision_scores.csv"
    old_output.write_text("old\n", encoding="utf-8")
    pipeline.manifest["status"] = "complete"
    pipeline._write_manifest()

    pipeline._promote()

    assert old_output.read_text(encoding="utf-8") == "new-provision_scores.csv\n"
    assert (outputs / "run_manifest.json").is_file()
    for name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / name).is_file()


def test_promotion_restores_target_when_replace_fails_after_backup(
    monkeypatch, tmp_path
):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    for name in pipeline_module.OUTPUT_NAMES:
        (pipeline.staged_outputs / name).write_text(
            f"new-{name}\n", encoding="utf-8"
        )
    pipeline.manifest["status"] = "complete"
    pipeline._write_manifest()

    target = inputs / pipeline_module.DERIVED_INPUT_NAMES[0]
    target.write_text("old-tree-canopy\n", encoding="utf-8")
    staged = pipeline.staged_inputs / pipeline_module.DERIVED_INPUT_NAMES[0]
    real_replace = pipeline_module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(source) == staged and not failed:
            failed = True
            raise OSError("simulated promotion failure")
        return real_replace(source, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", fail_once)

    with pytest.raises(OSError, match="simulated promotion failure"):
        pipeline._promote()

    assert target.read_text(encoding="utf-8") == "old-tree-canopy\n"
    assert staged.is_file()


def test_promotion_rolls_back_already_replaced_targets(monkeypatch, tmp_path):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    for name in pipeline_module.OUTPUT_NAMES:
        (pipeline.staged_outputs / name).write_text(
            f"new-{name}\n", encoding="utf-8"
        )
    pipeline.manifest["status"] = "complete"
    pipeline._write_manifest()

    first_three = pipeline_module.DERIVED_INPUT_NAMES[:3]
    for name in first_three:
        (inputs / name).write_text(f"old-{name}\n", encoding="utf-8")

    failed_source = pipeline.staged_inputs / first_three[-1]
    real_replace = pipeline_module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(source) == failed_source and not failed:
            failed = True
            raise OSError("simulated later promotion failure")
        return real_replace(source, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", fail_once)

    with pytest.raises(OSError, match="simulated later promotion failure"):
        pipeline._promote()

    for name in first_three:
        assert (inputs / name).read_text(encoding="utf-8") == f"old-{name}\n"
        assert (pipeline.staged_inputs / name).is_file()
