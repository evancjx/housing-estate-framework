import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.path.join(ROOT, "data", "inputs")
OUTPUTS = os.path.join(ROOT, "data", "outputs")
MODELS = os.path.join(ROOT, "models")

# value_output_private.csv is excluded: its input is a combined URA file that
# requires multi-file assembly outside the simple guard scope.


def _run(args):
    subprocess.run([sys.executable] + args, cwd=ROOT, check=True, capture_output=True, text=True)


def _same(regen, committed):
    a = pd.read_csv(regen, keep_default_na=False)
    b = pd.read_csv(committed, keep_default_na=False)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.integration
def test_provision_reproduces(tmp_path):
    out = str(tmp_path / "prov.csv")
    _run([f"{MODELS}/provision_model.py", "--estates", f"{INPUTS}/estates.csv",
          "--mrt", f"{INPUTS}/mrt_layer.csv", "--bus", f"{INPUTS}/bus_routes.csv",
          "--clinics", f"{INPUTS}/chas.csv", "--polyclinics", f"{INPUTS}/polyclinics.csv",
          "--schools", f"{INPUTS}/schools.csv", "--parks", f"{INPUTS}/parks.csv",
          "--markets", f"{INPUTS}/markets.csv", "--supermarkets", f"{INPUTS}/supermarkets.csv",
          "--childcare", f"{INPUTS}/childcare.csv", "--community", f"{INPUTS}/community.csv",
          "--sport", f"{INPUTS}/sport.csv", "--flood", f"{INPUTS}/flood_risk.csv",
          "--noise", f"{INPUTS}/expressways.csv", "--air_noise", f"{INPUTS}/air_noise_corridors.csv",
          "--eldercare", f"{INPUTS}/eldercare.csv", "--covered_linkway", f"{INPUTS}/covered_linkway.csv",
          "--jtc_industrial", f"{INPUTS}/jtc_industrial.csv", "--air_quality", f"{INPUTS}/air_quality.csv",
          "--tree_canopy", f"{INPUTS}/tree_canopy.csv", "--hdb_density", f"{INPUTS}/hdb_density.csv",
          "--hawker_v2", f"{INPUTS}/hawker_v2.csv", "--coastal", f"{INPUTS}/coastal.csv",
          "--tcmr", f"{INPUTS}/town_council_kpi.json", "--judged", f"{INPUTS}/judged_inputs.csv",
          "--out", out])
    _same(out, f"{OUTPUTS}/provision_scores.csv")


@pytest.mark.integration
def test_liveability_reproduces(tmp_path):
    out = str(tmp_path / "live.csv")
    _run([f"{MODELS}/liveability_model.py", "--scores", f"{OUTPUTS}/provision_scores.csv",
          "--pipeline", f"{INPUTS}/pipeline_data.json", "--archetypes", f"{INPUTS}/archetype_assignments.csv",
          "--bca", f"{INPUTS}/bca_permits.csv",
          "--out", out])
    _same(out, f"{OUTPUTS}/liveability_matrix.csv")


@pytest.mark.integration
def test_value_reproduces(tmp_path):
    pytest.importorskip("statsmodels")
    out = str(tmp_path / "value.csv")
    _run([f"{MODELS}/value_model.py", "--scores", f"{OUTPUTS}/provision_scores.csv",
          "--hdb", f"{INPUTS}/hdb_resale.csv", "--out", out])
    _same(out, f"{OUTPUTS}/value_output.csv")
