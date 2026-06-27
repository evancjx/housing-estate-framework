import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
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
    _run([f"{MODELS}/provision_model.py", "--estates", f"{DATA}/estates.csv",
          "--mrt", f"{DATA}/mrt_layer.csv", "--bus", f"{DATA}/bus_routes.csv",
          "--clinics", f"{DATA}/chas.csv", "--polyclinics", f"{DATA}/polyclinics.csv",
          "--schools", f"{DATA}/schools.csv", "--parks", f"{DATA}/parks.csv",
          "--markets", f"{DATA}/markets.csv", "--supermarkets", f"{DATA}/supermarkets.csv",
          "--childcare", f"{DATA}/childcare.csv", "--community", f"{DATA}/community.csv",
          "--sport", f"{DATA}/sport.csv", "--flood", f"{DATA}/flood_risk.csv",
          "--noise", f"{DATA}/expressways.csv", "--air_noise", f"{DATA}/air_noise_corridors.csv",
          "--eldercare", f"{DATA}/eldercare.csv", "--covered_linkway", f"{DATA}/covered_linkway.csv",
          "--jtc_industrial", f"{DATA}/jtc_industrial.csv", "--air_quality", f"{DATA}/air_quality.csv",
          "--tree_canopy", f"{DATA}/tree_canopy.csv", "--hdb_density", f"{DATA}/hdb_density.csv",
          "--hawker_v2", f"{DATA}/hawker_v2.csv", "--coastal", f"{DATA}/coastal.csv",
          "--tcmr", f"{DATA}/town_council_kpi.json", "--judged", f"{DATA}/judged_inputs.csv",
          "--out", out])
    _same(out, f"{DATA}/provision_scores.csv")


@pytest.mark.integration
def test_liveability_reproduces(tmp_path):
    out = str(tmp_path / "live.csv")
    _run([f"{MODELS}/liveability_model.py", "--scores", f"{DATA}/provision_scores.csv",
          "--pipeline", f"{DATA}/pipeline_data.json", "--archetypes", f"{DATA}/archetype_assignments.csv",
          "--bca", f"{DATA}/bca_permits.csv",
          "--out", out])
    _same(out, f"{DATA}/liveability_matrix.csv")


@pytest.mark.integration
def test_value_reproduces(tmp_path):
    pytest.importorskip("statsmodels")
    out = str(tmp_path / "value.csv")
    _run([f"{MODELS}/value_model.py", "--scores", f"{DATA}/provision_scores.csv",
          "--hdb", f"{DATA}/hdb_resale.csv", "--out", out])
    _same(out, f"{DATA}/value_output.csv")
