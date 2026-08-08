import ast
import importlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import pytest

import aliases
import framework_config
import liveability_model
import provision_model
from sg_estate import MODEL_VERSION
from sg_estate.contracts import ContractError, DataFrameContract, MASTER_OUTPUT
from sg_estate.domain import aliases as domain_aliases
from sg_estate.domain import framework as domain_framework
from sg_estate.reporting.builders import buyer_profile as buyer_profile_builder
from sg_estate.reporting.builders import comparison as comparison_builder
from sg_estate.reporting.builders import mrt_comparison as mrt_comparison_builder


ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_exports_share_domain_objects():
    assert framework_config.PROVISION_WEIGHTS is domain_framework.PROVISION_WEIGHTS
    assert aliases.ESTATE_TOWN_ALIAS is domain_aliases.ESTATE_TOWN_ALIAS
    assert provision_model.W is domain_framework.PROVISION_WEIGHTS


def test_domain_modules_do_not_depend_on_application_or_reporting():
    violations = []
    for path in (ROOT / "sg_estate" / "domain").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(
                    ("sg_estate.application", "sg_estate.reporting", "scrapers")
                ):
                    violations.append(f"{path.name}: {name}")
    assert violations == []


def test_liveability_uses_shared_nonnegative_persona_weights():
    assert liveability_model.PERSONA_WEIGHTS == domain_framework.build_persona_weights()
    for weights in liveability_model.PERSONA_WEIGHTS.values():
        assert min(weights.values()) >= 0.0
        assert sum(weights.values()) == pytest.approx(1.0)


def test_report_compatibility_modules_are_import_safe():
    buyer_compat = importlib.import_module("gen_buyer_profile_html")
    comparison_compat = importlib.import_module("gen_comparison_html")
    mrt_compat = importlib.import_module("gen_mrt_comparison_html")
    diagram = importlib.import_module("gen_framework_diagram_html")
    assert callable(buyer_compat.main)
    assert callable(comparison_compat.main)
    assert callable(mrt_compat.main)
    assert callable(diagram.main)
    assert callable(buyer_profile_builder.build)
    assert callable(comparison_builder.build)
    assert callable(mrt_comparison_builder.build)


def test_dataframe_contract_rejects_duplicate_keys_and_ranges():
    contract = DataFrameContract(
        required=frozenset({"estate", "score"}),
        unique=(("estate",),),
        numeric_ranges={"score": (1.0, 5.0)},
    )
    with pytest.raises(ContractError, match="duplicate key"):
        contract.validate(
            pd.DataFrame({"estate": ["A", "A"], "score": [3.0, 4.0]})
        )
    with pytest.raises(ContractError, match="outside"):
        contract.validate(pd.DataFrame({"estate": ["A"], "score": [6.0]}))


def test_data_catalog_covers_all_committed_inputs():
    catalog = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["schema_version"] == 1
    catalogued = set(catalog["datasets"])
    result = subprocess.run(
        ("git", "ls-files", "data/inputs"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    committed = {Path(value).name for value in result.stdout.splitlines()}
    assert catalogued == committed
    for metadata in catalog["datasets"].values():
        assert metadata["zone"] in catalog["zones"]
        assert metadata["producer"]
        assert metadata["authority"]


def test_committed_data_files_stay_below_repository_limit():
    max_bytes = 50 * 1024 * 1024
    result = subprocess.run(
        ("git", "ls-files", "-z", "data"),
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    oversized = {
        relative.decode(): (ROOT / relative.decode()).stat().st_size
        for relative in result.stdout.split(b"\0")
        if relative and (ROOT / relative.decode()).is_file()
        and (ROOT / relative.decode()).stat().st_size > max_bytes
    }
    assert oversized == {}


def test_promoted_outputs_publish_current_model_version():
    for name in (
        "provision_scores.csv",
        "liveability_matrix.csv",
        "value_output.csv",
        "lease_risk.csv",
        "employment_scores_T0.csv",
        "master_output.csv",
    ):
        frame = pd.read_csv(ROOT / "data" / "outputs" / name)
        assert set(frame["model_version"].astype(str)) == {MODEL_VERSION}


def test_master_output_uses_declared_status_vocabulary():
    frame = pd.read_csv(ROOT / "data" / "outputs" / "master_output.csv")
    MASTER_OUTPUT.validate(frame, source="promoted master")
    frame.loc[0, "employment_status"] = "unknown"
    with pytest.raises(ContractError, match="invalid values"):
        MASTER_OUTPUT.validate(frame, source="invalid master")
