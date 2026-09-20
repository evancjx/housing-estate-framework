"""data/catalog.json is the provenance ground truth, so its producer claims
must hold. Four layers named models/data_ingest.py as their producer while
that script never mentions them, which made hand-curated files look
refreshable."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))


def _script_producers():
    for name, meta in sorted(CATALOG["datasets"].items()):
        producer = meta.get("producer", "")
        if "/" in producer and producer.endswith(".py"):
            yield name, producer


def test_every_script_producer_exists():
    missing = [(name, producer) for name, producer in _script_producers()
               if not (ROOT / producer).exists()]
    assert missing == []


def test_every_script_producer_names_the_dataset_it_claims_to_write():
    offenders = []
    for name, producer in _script_producers():
        if name not in (ROOT / producer).read_text(encoding="utf-8"):
            offenders.append((name, producer))
    assert offenders == []


def test_every_dataset_declares_a_known_zone():
    zones = set(CATALOG["zones"])
    unknown = {name: meta.get("zone") for name, meta in CATALOG["datasets"].items()
               if meta.get("zone") not in zones}
    assert unknown == {}


def test_catalog_covers_every_committed_input():
    on_disk = {p.name for p in (ROOT / "data" / "inputs").iterdir()
               if p.is_file() and p.suffix in {".csv", ".json"}}
    assert on_disk - set(CATALOG["datasets"]) == set()
