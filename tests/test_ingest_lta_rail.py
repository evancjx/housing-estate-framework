from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import shapefile

from models import ingest_lta_rail as rail


def _zip_bytes(filename: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, payload)
    return buffer.getvalue()


def _codes_archive() -> bytes:
    rows = [
        {
            "stn_code": f"ZZ{index:03d}",
            "mrt_station_english": f"Base Station {index:03d}",
            "mrt_line_english": "Fixture Line",
        }
        for index in range(211)
    ]
    rows.extend(
        [
            {
                "stn_code": "CE1",
                "mrt_station_english": "Bayfront",
                "mrt_line_english": "Circle Line Extension",
            },
            {
                "stn_code": "CE2",
                "mrt_station_english": "Marina Bay",
                "mrt_line_english": "Circle Line Extension",
            },
        ]
    )
    payload = pd.DataFrame(rows).to_csv(index=False).encode()
    return _zip_bytes("fixture/station_codes.csv", payload)


def _shapefile_archive(
    shape_type: int,
    field_name: str,
    features: list[tuple[str, tuple[float, float]]],
) -> bytes:
    shp = io.BytesIO()
    shx = io.BytesIO()
    dbf = io.BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shape_type)
    writer.field(field_name, "C", size=100)
    for name, (x, y) in features:
        if shape_type == shapefile.POLYGON:
            delta = 8.0
            writer.poly(
                [[
                    [x - delta, y - delta],
                    [x - delta, y + delta],
                    [x + delta, y + delta],
                    [x + delta, y - delta],
                    [x - delta, y - delta],
                ]]
            )
        else:
            writer.point(x, y)
        writer.record(name)
    writer.close()

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fixture/stations.shp", shp.getvalue())
        archive.writestr("fixture/stations.shx", shx.getvalue())
        archive.writestr("fixture/stations.dbf", dbf.getvalue())
    return archive_buffer.getvalue()


def _station_archive() -> bytes:
    features = [
        (f"Base Station {index:03d} MRT STATION", (28_000 + index, 30_000 + index))
        for index in range(211)
    ]
    # CCL6 interchange memberships already have March polygon geometry.  A
    # deferred station is included to prove that polygon geometry stays first
    # in the source priority even when URA also has an outline.
    features.extend(
        [
            ("MARINA BAY MRT STATION", (29_000, 30_400)),
            ("BAYFRONT MRT STATION", (29_100, 30_450)),
            ("MOUNT PLEASANT MRT STATION", (28_800, 32_000)),
        ]
    )
    return _shapefile_archive(shapefile.POLYGON, "STN_NAM_DE", features)


def _exit_archive() -> bytes:
    features = []
    for index, name in enumerate(("Keppel", "Cantonment", "Prince Edward Road")):
        features.extend(
            [
                (f"{name} MRT STATION", (28_500 + index * 30, 29_500 + index * 30)),
                (f"{name} MRT STATION", (28_510 + index * 30, 29_510 + index * 30)),
            ]
        )
    return _shapefile_archive(shapefile.POINT, "stn_name", features)


def _ura_geojson(status_file: Path) -> bytes:
    status = rail.load_status_contract(status_file)
    names = sorted(
        set(status.loc[status["network_status"] != "open", "name"])
    )
    features = []
    for index, name in enumerate(names):
        lon = 103.70 + (index % 10) * 0.01
        lat = 1.25 + (index // 10) * 0.01
        delta = 0.0001
        features.append(
            {
                "type": "Feature",
                "properties": {"NAME": name},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon - delta, lat - delta],
                        [lon + delta, lat - delta],
                        [lon + delta, lat + delta],
                        [lon - delta, lat + delta],
                        [lon - delta, lat - delta],
                    ]],
                },
            }
        )
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


@pytest.fixture(scope="module")
def built_layer(tmp_path_factory: pytest.TempPathFactory) -> tuple[pd.DataFrame, dict[str, Path]]:
    directory = tmp_path_factory.mktemp("rail-ingest")
    paths = {
        "codes": directory / "codes.zip",
        "stations": directory / "stations.zip",
        "exits": directory / "exits.zip",
        "ura": directory / "ura.geojson",
        "registry": directory / "registry.json",
        "output": directory / "mrt_layer.csv",
        "names": directory / "mrt_layer_names.csv",
    }
    paths["codes"].write_bytes(_codes_archive())
    paths["stations"].write_bytes(_station_archive())
    paths["exits"].write_bytes(_exit_archive())
    paths["ura"].write_bytes(_ura_geojson(rail.DEFAULT_STATUS_FILE))
    registry = json.loads(rail.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    fixture_sources = {
        rail.SOURCE_CODES: paths["codes"],
        rail.SOURCE_POLYGONS: paths["stations"],
        rail.SOURCE_EXITS: paths["exits"],
        rail.SOURCE_URA: paths["ura"],
    }
    for key, path in fixture_sources.items():
        registry["sources"][key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    layer = rail.build_layer(
        paths["codes"],
        paths["stations"],
        paths["exits"],
        paths["ura"],
    )
    return layer, paths


def test_curated_status_contract_has_exact_reconciliation_and_overlay() -> None:
    status = rail.load_status_contract()

    assert len(status) == 50
    assert set(status.loc[status["record_action"] == "remove", "stn_code"]) == {"CE1", "CE2"}
    open_upserts = status[
        (status["record_action"] == "upsert")
        & (status["network_status"] == "open")
    ]
    assert set(open_upserts["stn_code"]) == {
        "CC30", "CC31", "CC32", "CC33", "CC34",
    }
    assert set(open_upserts["planned_opening"]) == {"2026-07-12"}
    overlay = status[
        (status["record_action"] == "upsert")
        & (status["network_status"] != "open")
    ]
    assert len(overlay) == 43
    assert overlay["network_status"].value_counts().to_dict() == {
        "planned": 36,
        "under_construction": 4,
        "deferred": 3,
    }
    assert "JR1" not in set(status["stn_code"])


def test_build_layer_preserves_memberships_and_geometry_provenance(built_layer) -> None:
    layer, _ = built_layer

    assert len(layer) == 259
    assert layer["stn_code"].is_unique
    assert layer["network_status"].value_counts().to_dict() == rail.EXPECTED_STATUS_COUNTS
    assert not layer["stn_code"].str.startswith("CE").any()
    assert set(layer.columns) == set(rail.OUTPUT_COLUMNS)

    by_code = layer.set_index("stn_code")
    assert by_code.loc["CC30", "geometry_basis"] == "derived_lta_station_exit_points_mean"
    assert by_code.loc["CC33", "geometry_basis"] == "derived_lta_station_polygon_union_centroid"
    assert by_code.loc["TE10", "geometry_basis"] == "derived_lta_station_polygon_union_centroid"
    assert by_code.loc["TE30", "geometry_basis"] == "derived_ura_station_outline_union_centroid"
    assert by_code.loc["TE31", "network_status"] == "under_construction"
    assert by_code.loc["DT37", "name"] == "Sungei Bedok"
    assert by_code.loc["JS1", "planned_opening"] == "2028"
    assert by_code.loc["CR13", "planned_opening"] == "2030"


def test_local_archive_cli_never_downloads_and_writes_atomically(
    built_layer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, paths = built_layer

    def unexpected_download(*_args, **_kwargs):
        raise AssertionError("local-archive execution must not use the network")

    monkeypatch.setattr(rail, "download_bytes", unexpected_download)
    result = rail.main(
        [
            "--codes-archive", str(paths["codes"]),
            "--station-archive", str(paths["stations"]),
            "--exit-archive", str(paths["exits"]),
            "--ura-geojson", str(paths["ura"]),
            "--registry", str(paths["registry"]),
            "--output", str(paths["output"]),
            "--names-output", str(paths["names"]),
        ]
    )

    assert result == 0
    written = pd.read_csv(paths["output"])
    names = pd.read_csv(paths["names"])
    assert list(written.columns) == rail.OUTPUT_COLUMNS
    assert list(names.columns) == [
        "stn_code", "mrt_station_english", "mrt_line_english",
    ]
    assert len(names) == 259
    assert names["stn_code"].is_unique
    assert not list(paths["output"].parent.glob("*.tmp"))


def test_validate_layer_rejects_a_duplicate_code(built_layer) -> None:
    layer, _ = built_layer
    broken = layer.copy()
    broken.loc[broken.index[1], "stn_code"] = broken.loc[broken.index[0], "stn_code"]

    with pytest.raises(rail.RailDataError, match="duplicate station codes"):
        rail.validate_layer(broken)


def test_status_contract_rejects_future_name_or_opening_drift(tmp_path) -> None:
    status = rail.load_status_contract().copy()
    status.loc[status["stn_code"] == "JS1", "planned_opening"] = "2027"
    broken = tmp_path / "status.csv"
    status.to_csv(broken, index=False)

    with pytest.raises(rail.RailDataError, match="Incorrect future membership for JS1"):
        rail.load_status_contract(broken)


def test_status_contract_rejects_an_unregistered_source_key(tmp_path) -> None:
    status = rail.load_status_contract().copy()
    status.loc[status["stn_code"] == "JS1", "source_key"] = "not_in_registry"
    broken = tmp_path / "status.csv"
    status.to_csv(broken, index=False)

    with pytest.raises(rail.RailDataError, match="source keys"):
        rail.load_status_contract(broken)


def test_status_contract_rejects_a_registered_but_wrong_source_key(tmp_path) -> None:
    status = rail.load_status_contract().copy()
    status.loc[status["stn_code"] == "JS1", "source_key"] = "lta_crl1_project"
    broken = tmp_path / "status.csv"
    status.to_csv(broken, index=False)

    with pytest.raises(rail.RailDataError, match="Incorrect status source for JS1"):
        rail.load_status_contract(broken)


def test_pinned_source_hash_rejects_mutated_upstream_bytes() -> None:
    registry = rail.load_registry()

    with pytest.raises(rail.RailDataError, match="SHA-256 changed"):
        rail.verify_source_bytes(b"changed", registry, rail.SOURCE_CODES)


def test_name_normalization_is_source_independent() -> None:
    assert rail.normalize_station_name("  Founders’ Memorial MRT Station ") == "FOUNDERS MEMORIAL"
    assert rail.normalize_station_name("Choa Chu Kang LRT Station") == "CHOA CHU KANG"
    assert rail.normalize_station_name("Bayfront Interchange") == "BAYFRONT"
