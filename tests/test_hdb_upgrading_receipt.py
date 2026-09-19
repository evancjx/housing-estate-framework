import json
import sys

import pandas as pd
import pytest

import ingest_hdb_upgrading
from sg_estate import source_receipts


def _feature(name: str, status: str, year: str) -> dict:
    return {
        "properties": {
            "NAME": name,
            "STATUS": status,
            "ESTMT_CNSTRN_CMPLTN": year,
        },
        "geometry": {
            "type": "Point",
            "coordinates": [103.85, 1.37],
        },
    }


def test_fetch_geojson_uses_valid_cache_without_network(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    payload = {"features": [_feature("ANG MO KIO NRP", "U/C", "4Q 2027")]}
    (cache_dir / f"{ingest_hdb_upgrading.NRP_DATASET}.geojson").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(ingest_hdb_upgrading, "_ACTIVE_CACHE_DIR", cache_dir)
    ingest_hdb_upgrading._LAST_FETCH_MODES.clear()
    monkeypatch.setattr(
        ingest_hdb_upgrading,
        "_http_json",
        lambda *_args, **_kwargs: pytest.fail("cache hit must not use network"),
    )

    assert ingest_hdb_upgrading.fetch_geojson(
        ingest_hdb_upgrading.NRP_DATASET
    ) == payload
    assert ingest_hdb_upgrading._LAST_FETCH_MODES == {
        ingest_hdb_upgrading.NRP_DATASET: "cached"
    }


def test_main_writes_composite_fresh_receipt_after_pipeline_merge(
    tmp_path,
    monkeypatch,
) -> None:
    estates = tmp_path / "estates.csv"
    pipeline = tmp_path / "pipeline_data.json"
    output = tmp_path / "staged-pipeline.json"
    pd.DataFrame(
        {"estate": ["ANG MO KIO"], "lat": [1.37], "lon": [103.85]}
    ).to_csv(estates, index=False)
    pipeline.write_text(
        json.dumps(
            {
                "pipeline_items": [
                    {
                        "description": "Reviewed base item",
                        "benefiting_estates": ["ANG MO KIO"],
                        "type": "MRT",
                        "significance": "HIGH",
                        "certainty": "CONFIRMED",
                        "expected_year": 2029,
                        "notes": "reviewed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payloads = {
        ingest_hdb_upgrading.NRP_DATASET: {
            "features": [_feature("ANG MO KIO NRP", "U/C", "4Q 2027")]
        },
        ingest_hdb_upgrading.LUP_DATASET: {
            "features": [_feature("ANG MO KIO LUP", "Proposed", "2999")]
        },
    }
    monkeypatch.setattr(
        ingest_hdb_upgrading,
        "fetch_geojson",
        lambda dataset_id: payloads[dataset_id],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_hdb_upgrading.py",
            "--estates", str(estates),
            "--pipeline", str(pipeline),
            "--out", str(output),
        ],
    )

    ingest_hdb_upgrading.main()

    emitted = json.loads(output.read_text(encoding="utf-8"))
    receipt = source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(output), output_path=output
    )
    expected_urls = [
        ingest_hdb_upgrading.POLL_URL.format(ds=ingest_hdb_upgrading.NRP_DATASET),
        ingest_hdb_upgrading.POLL_URL.format(ds=ingest_hdb_upgrading.LUP_DATASET),
    ]
    assert receipt["dataset_id"] == "pipeline_data.json"
    assert receipt["authority"] == "reviewed public announcements"
    assert receipt["source_url"] == expected_urls[0]
    assert receipt["source_urls"] == expected_urls
    assert receipt["cache_state"] == "mixed"
    assert receipt["fallback_state"] == "not_used"
    assert receipt["validation_status"] == "passed"
    assert receipt["retrieved_at"] is not None
    assert receipt["coverage_start"] == "2027"
    assert receipt["coverage_end"] == "2030"
    assert receipt["row_count"] == len(emitted["pipeline_items"])
    assert str(tmp_path) not in receipt["source_identity"]
