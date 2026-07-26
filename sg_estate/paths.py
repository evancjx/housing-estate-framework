"""Repository path discovery shared by CLIs, pipelines, and reports."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPOSITORY_ROOT / "data"
INPUT_DIR = DATA_DIR / "inputs"
OUTPUT_DIR = DATA_DIR / "outputs"
RAW_DIR = DATA_DIR / "raw"
RUNS_DIR = DATA_DIR / "runs"
REPORT_CATALOG = REPOSITORY_ROOT / "site" / "reports.json"

__all__ = [
    "DATA_DIR",
    "INPUT_DIR",
    "OUTPUT_DIR",
    "RAW_DIR",
    "REPORT_CATALOG",
    "REPOSITORY_ROOT",
    "RUNS_DIR",
]
