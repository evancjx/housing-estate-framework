import json
import sys
from pathlib import Path

import pandas as pd
import pytest

import data_ingest
import fetch_chas
import ingest_nea_air
from sg_estate import source_receipts


DATA_INGEST_OUTPUTS = {
    "parks.csv",
    "markets.csv",
    "schools.csv",
    "polyclinics.csv",
    "hdb_resale.csv",
}


def _skip_other_data_ingest_outputs(directory: Path, target: str | None) -> None:
    for name in DATA_INGEST_OUTPUTS - ({target} if target else set()):
        (directory / name).write_text("placeholder\n1\n", encoding="utf-8")


def _run_data_ingest(monkeypatch, directory: Path) -> None:
    monkeypatch.setattr(data_ingest.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["data_ingest.py", "--out-dir", str(directory)],
    )
    data_ingest.main()


def _read_receipt(output: Path) -> dict[str, object]:
    return source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(output),
        output_path=output,
    )


def test_data_ingest_parks_receipt_tracks_selected_dataset_not_signed_url(
    tmp_path,
    monkeypatch,
):
    _skip_other_data_ingest_outputs(tmp_path, "parks.csv")
    raw = json.dumps(
        {
            "features": [
                {
                    "geometry": {"coordinates": [103.8, 1.3]},
                    "properties": {"Name": "Test Park"},
                }
            ]
        }
    ).encode()
    monkeypatch.setattr(data_ingest, "poll_download", lambda _dataset_id: raw)

    _run_data_ingest(monkeypatch, tmp_path)

    output = tmp_path / "parks.csv"
    receipt = _read_receipt(output)
    selected_id = data_ingest.DATASETS["parks"]["ids"][0]
    assert receipt["authority"] == "NParks / data.gov.sg"
    assert receipt["source_identity"] == f"data.gov.sg:{selected_id}"
    assert receipt["source_url"] == data_ingest.POLL_BASE.format(
        dataset_id=selected_id
    )
    assert "X-Amz" not in str(receipt)
    assert receipt["cache_state"] == "fresh"
    assert receipt["fallback_state"] == "not_used"
    assert receipt["row_count"] == 1


def test_data_ingest_school_geocoding_records_fresh_onemap_fallback(
    tmp_path,
    monkeypatch,
):
    _skip_other_data_ingest_outputs(tmp_path, "schools.csv")
    raw = (
        "school_name,postal_code,address,telephone,type_code\n"
        "Example School,123456,1 Example Road,61234567,PRIMARY\n"
    ).encode()
    monkeypatch.setattr(data_ingest, "poll_download", lambda _dataset_id: raw)
    monkeypatch.setattr(
        data_ingest,
        "onemap_geocode_single",
        lambda _query: (1.31, 103.81),
    )

    _run_data_ingest(monkeypatch, tmp_path)

    receipt = _read_receipt(tmp_path / "schools.csv")
    selected_id = data_ingest.DATASETS["schools"]["ids"][0]
    primary_url = data_ingest.POLL_BASE.format(dataset_id=selected_id)
    assert receipt["authority"] == (
        "MOE / data.gov.sg + OneMap geocoding fallback"
    )
    assert receipt["source_identity"] == (
        f"data.gov.sg:{selected_id} + OneMap Search geocoding"
    )
    assert receipt["source_urls"] == [primary_url, data_ingest.ONEMAP_SEARCH]
    assert receipt["cache_state"] == "fresh"
    assert receipt["fallback_state"] == "used"


def test_data_ingest_hdb_receipt_uses_winning_id_and_actual_month_coverage(
    tmp_path,
    monkeypatch,
):
    _skip_other_data_ingest_outputs(tmp_path, "hdb_resale.csv")
    ids = data_ingest.DATASETS["hdb_resale"]["ids"]
    raw = (
        "town,resale_price,floor_area_sqm,flat_type,storey_range,"
        "remaining_lease,month\n"
        "BEDOK,500000,90,4 ROOM,04 TO 06,80 years 00 months,2026-02\n"
        "BEDOK,510000,91,4 ROOM,07 TO 09,79 years 00 months,2026-05\n"
    ).encode()

    def fake_poll(dataset_id):
        return raw if dataset_id == ids[1] else None

    monkeypatch.setattr(data_ingest, "poll_download", fake_poll)

    _run_data_ingest(monkeypatch, tmp_path)

    receipt = _read_receipt(tmp_path / "hdb_resale.csv")
    assert receipt["source_identity"] == f"data.gov.sg:{ids[1]}"
    assert receipt["coverage_start"] == "2026-02"
    assert receipt["coverage_end"] == "2026-05"
    assert receipt["row_count"] == 2


def test_data_ingest_existing_outputs_are_skipped_without_new_receipts(
    tmp_path,
    monkeypatch,
):
    _skip_other_data_ingest_outputs(tmp_path, None)
    monkeypatch.setattr(
        data_ingest,
        "poll_download",
        lambda _dataset_id: pytest.fail("a skipped layer must not be fetched"),
    )

    _run_data_ingest(monkeypatch, tmp_path)

    assert not list(tmp_path.glob("*.receipt.json"))


def test_data_ingest_failed_fetch_writes_no_receipt(tmp_path, monkeypatch):
    _skip_other_data_ingest_outputs(tmp_path, "parks.csv")
    monkeypatch.setattr(data_ingest, "poll_download", lambda _dataset_id: None)

    with pytest.raises(SystemExit):
        _run_data_ingest(monkeypatch, tmp_path)

    assert not source_receipts.receipt_path_for(tmp_path / "parks.csv").exists()


def _chas_rows(count: int = 200) -> list[dict[str, object]]:
    return [
        {"lat": 1.2 + index / 100000, "lon": 103.8, "name": f"Clinic {index}"}
        for index in range(count)
    ]


def _chas_metadata(*, onemap: bool) -> dict[str, object]:
    if onemap:
        url = (
            f"{fetch_chas.ONEMAP_SEARCH}?searchVal=CHAS%20clinic"
            "&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        )
        return {
            "source_url": url,
            "source_urls": [url],
            "source_identity": "OneMap Search queries: CHAS clinic",
            "cache_state": "fresh",
            "fallback_state": "used",
        }
    return fetch_chas._datagov_metadata(fetch_chas.CHAS_DATASET_ID)


def test_chas_primary_writes_fresh_receipt_with_stable_dataset_url(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "chas.csv"
    monkeypatch.setattr(fetch_chas, "OUT", str(output))
    monkeypatch.setattr(
        fetch_chas,
        "try_datagov_known",
        lambda: (_chas_rows(), _chas_metadata(onemap=False)),
    )
    monkeypatch.setattr(
        fetch_chas,
        "try_datagov",
        lambda: pytest.fail("known dataset should win"),
    )
    monkeypatch.setattr(
        fetch_chas,
        "try_onemap_search",
        lambda: pytest.fail("OneMap should not be used"),
    )

    fetch_chas.main([])

    receipt = _read_receipt(output)
    assert receipt["authority"] == fetch_chas.CHAS_AUTHORITY
    assert receipt["source_url"] == fetch_chas.POLL_BASE.format(
        fetch_chas.CHAS_DATASET_ID
    )
    assert receipt["source_identity"] == (
        f"data.gov.sg:{fetch_chas.CHAS_DATASET_ID}"
    )
    assert receipt["cache_state"] == "fresh"
    assert receipt["fallback_state"] == "not_used"
    assert receipt["retrieved_at"] is not None


def test_chas_onemap_strategy_is_explicit_fallback(tmp_path, monkeypatch):
    output = tmp_path / "chas.csv"
    monkeypatch.setattr(fetch_chas, "OUT", str(output))
    monkeypatch.setattr(fetch_chas, "try_datagov_known", lambda: (None, None))
    monkeypatch.setattr(fetch_chas, "try_datagov", lambda: (None, None))
    monkeypatch.setattr(
        fetch_chas,
        "try_onemap_search",
        lambda: (_chas_rows(), _chas_metadata(onemap=True)),
    )

    fetch_chas.main([])

    receipt = _read_receipt(output)
    assert receipt["fallback_state"] == "used"
    assert receipt["cache_state"] == "fresh"
    assert receipt["source_url"].startswith(fetch_chas.ONEMAP_SEARCH)


def test_chas_rejected_small_result_writes_no_output_or_receipt(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "chas.csv"
    monkeypatch.setattr(fetch_chas, "OUT", str(output))
    monkeypatch.setattr(
        fetch_chas,
        "try_datagov_known",
        lambda: (_chas_rows(10), _chas_metadata(onemap=False)),
    )

    with pytest.raises(SystemExit):
        fetch_chas.main([])

    assert not output.exists()
    assert not source_receipts.receipt_path_for(output).exists()


def _air_inputs(tmp_path: Path, *, estate: str = "BEDOK") -> tuple[Path, Path, Path]:
    estates = tmp_path / "estates.csv"
    expressways = tmp_path / "expressways.csv"
    output = tmp_path / "air_quality.csv"
    pd.DataFrame(
        {"estate": [estate], "lat": [1.31], "lon": [103.91]}
    ).to_csv(estates, index=False)
    pd.DataFrame({"lat": [1.0], "lon": [103.0]}).to_csv(
        expressways,
        index=False,
    )
    return estates, expressways, output


def _air_payload(*, include_no2: bool = True) -> dict[str, object]:
    readings = {
        "pm25_twenty_four_hourly": {
            region: 15 for region in ingest_nea_air.REGIONS
        },
        "psi_twenty_four_hourly": {
            region: 50 for region in ingest_nea_air.REGIONS
        },
    }
    if include_no2:
        readings["no2_one_hour_max"] = {
            region: 12 for region in ingest_nea_air.REGIONS
        }
    return {"items": [{"readings": readings}]}


def _run_air(
    monkeypatch,
    estates: Path,
    expressways: Path,
    output: Path,
    *extra_args: str,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_nea_air.py",
            "--estates",
            str(estates),
            "--expressways",
            str(expressways),
            "--out",
            str(output),
            *extra_args,
        ],
    )
    ingest_nea_air.main()


def test_nea_stub_receipt_is_offline_fallback_without_invented_retrieval(
    tmp_path,
    monkeypatch,
):
    estates, expressways, output = _air_inputs(tmp_path)

    _run_air(monkeypatch, estates, expressways, output, "--stub")

    receipt = _read_receipt(output)
    assert receipt["authority"] == ingest_nea_air.AIR_AUTHORITY
    assert receipt["cache_state"] == "offline"
    assert receipt["fallback_state"] == "used"
    assert receipt["retrieved_at"] is None
    assert receipt["coverage_start"] is None
    assert receipt["coverage_end"] is None


def test_nea_receipt_tracks_actual_mixed_sample_coverage(
    tmp_path,
    monkeypatch,
):
    estates, expressways, output = _air_inputs(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    end = ingest_nea_air.dt.date.today()
    start = end - ingest_nea_air.dt.timedelta(days=365)
    (cache_dir / f"psi_{start.isoformat()}.json").write_text(
        "{}",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ingest_nea_air,
        "fetch_day",
        lambda _ymd, _cache_dir: _air_payload(),
    )

    _run_air(
        monkeypatch,
        estates,
        expressways,
        output,
        "--cache-dir",
        str(cache_dir),
        "--sample-days",
        "365",
    )

    receipt = _read_receipt(output)
    assert receipt["cache_state"] == "mixed"
    assert receipt["fallback_state"] == "not_used"
    assert receipt["retrieved_at"] is not None
    assert receipt["coverage_start"] == start.isoformat()
    assert receipt["coverage_end"] == end.isoformat()
    assert receipt["source_urls"] == [
        ingest_nea_air.PSI_URL.format(ymd=start.isoformat()),
        ingest_nea_air.PSI_URL.format(ymd=end.isoformat()),
    ]


def test_nea_missing_no2_and_unmapped_estate_mark_climatology_fallback(
    tmp_path,
    monkeypatch,
):
    estates, expressways, output = _air_inputs(
        tmp_path,
        estate="HOLLAND VILLAGE",
    )
    monkeypatch.setattr(
        ingest_nea_air,
        "fetch_day",
        lambda _ymd, _cache_dir: _air_payload(include_no2=False),
    )

    _run_air(
        monkeypatch,
        estates,
        expressways,
        output,
        "--sample-days",
        "365",
    )

    receipt = _read_receipt(output)
    assert receipt["cache_state"] == "fresh"
    assert receipt["fallback_state"] == "used"
    assert receipt["retrieved_at"] is not None
    assert pd.read_csv(output).iloc[0]["no2_annual_mean"] == (
        ingest_nea_air.CLIMATOLOGY["central"]["no2"]
    )


def test_nea_zero_accepted_samples_uses_offline_fallback_receipt(
    tmp_path,
    monkeypatch,
):
    estates, expressways, output = _air_inputs(tmp_path)
    monkeypatch.setattr(
        ingest_nea_air,
        "fetch_day",
        lambda _ymd, _cache_dir: {"items": []},
    )

    _run_air(
        monkeypatch,
        estates,
        expressways,
        output,
        "--sample-days",
        "365",
    )

    receipt = _read_receipt(output)
    assert receipt["cache_state"] == "offline"
    assert receipt["fallback_state"] == "used"
    assert receipt["retrieved_at"] is None
    assert receipt["coverage_start"] is None
    assert receipt["coverage_end"] is None
