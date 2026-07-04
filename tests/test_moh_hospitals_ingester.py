import pytest

import ingest_moh_hospitals


def test_ae_allowlist_flags_only_curated_24h_emergency_hospitals():
    assert ingest_moh_hospitals.has_ae_24h("Singapore General Hospital")
    assert ingest_moh_hospitals.has_ae_24h("KK Women's and Children's Hospital")
    assert not ingest_moh_hospitals.has_ae_24h("Alexandra Hospital")
    assert not ingest_moh_hospitals.has_ae_24h("Jurong Community Hospital")


def test_min_expected_acute_guard_hard_fails_below_threshold():
    rows = [
        {"name": f"Acute {i}", "tier": "acute", "lat": 1.3, "lon": 103.8}
        for i in range(7)
    ]

    with pytest.raises(SystemExit) as exc:
        ingest_moh_hospitals.require_min_acute(rows, "data/hospitals.csv")

    assert "only 7 acute public hospitals resolved/geocoded" in str(exc.value)
    assert "refusing to write data/hospitals.csv" in str(exc.value)
