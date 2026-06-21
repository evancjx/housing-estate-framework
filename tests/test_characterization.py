import pytest

from . import snapshot


@pytest.mark.snapshot
def test_capture_before():
    """Run before Phase-1 fixes: python -m pytest -m snapshot -k before"""
    captured = snapshot.capture("before")
    assert "value_output.csv" in captured
