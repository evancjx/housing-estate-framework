"""Offline tests for unit-ledger run assembly, fetch helpers and failure handling."""

import json

import pandas as pd
import pytest

from scrapers.unit_ledger import build, fetch


def _raw_run(run_dir, with_edgeprop=True):
    raw = run_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "fetch.json").write_text(json.dumps({
        "project": "DEMO", "fetched_at_utc": "2026-09-26T00:00:00Z", "sources": {},
        "warnings": ["PropertyNoob page unavailable (404)"]}))
    (raw / "ura.json").write_text(json.dumps([{"project": "DEMO", "transaction": [
        {"contractDate": "0826", "price": "2469854", "area": "113", "floorRange": "06-10",
         "typeOfSale": "1", "noOfUnits": "1", "tenure": "99 yrs"}]}]))
    if with_edgeprop:
        pd.DataFrame([{"Date of Sale": "26 Aug 2026", "Street": "57 DEMO ROAD", "Address": "57 DEMO ROAD #06-XX",
                       "Price ($)": "2469854", "Area (sqm)": "112.97", "Area (sqft)": "1216", "Bedrooms": "4",
                       "Sale Type": "New Sale"}]).to_csv(raw / "edgeprop.csv", index=False)
    return run_dir


def test_build_run_writes_every_output(tmp_path):
    meta = build.build_run(_raw_run(tmp_path))
    for name in ("transactions.csv", "units.csv", "provenance.json", "README.md", "index.html"):
        assert (tmp_path / name).exists(), name
    assert meta["counts"]["dated"] == 1 and meta["counts"]["with_unit"] == 0
    assert "PropertyNoob page unavailable (404)" in (tmp_path / "README.md").read_text()
    assert "ura.json" in json.loads((tmp_path / "provenance.json").read_text())["raw_sha256"]


def test_build_run_warns_when_edgeprop_is_missing(tmp_path):
    meta = build.build_run(_raw_run(tmp_path, with_edgeprop=False))
    assert any("no matching EdgeProp record" in w for w in meta["warnings"])


def test_run_discards_partial_output_when_a_fetch_fails(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("URA batch 2 returned Status='Error'")
    monkeypatch.setattr(fetch, "fetch_all", boom)
    with pytest.raises(RuntimeError):
        build.run("DEMO", runs_root=tmp_path, today="2026-09-26")
    assert not any("2026-09-26" in p.name for p in tmp_path.rglob("*"))


def test_run_replaces_the_same_day_directory_only_after_success(tmp_path, monkeypatch):
    final = tmp_path / "demo" / "2026-09-26"
    final.mkdir(parents=True)
    (final / "old.txt").write_text("old")
    monkeypatch.setattr(fetch, "fetch_all", lambda project, raw, logs, **kwargs: _raw_run(raw.parent))
    out = build.run("DEMO", runs_root=tmp_path, today="2026-09-26")
    assert out == final and (final / "index.html").exists() and not (final / "old.txt").exists()


def test_fetch_ura_names_the_closest_projects(monkeypatch):
    monkeypatch.setattr(fetch.ura_pmi_api, "get_access_key", lambda: "key")
    monkeypatch.setattr(fetch.ura_pmi_api, "generate_token", lambda key, session: "token")
    monkeypatch.setattr(fetch.ura_pmi_api, "fetch_transactions", lambda key, token, batch, session: {
        "Status": "Success", "Result": [{"project": "CANBERRA CRESCENT RESIDENCES", "transaction": []}]})
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)
    with pytest.raises(fetch.ProjectNotFound, match="CANBERRA CRESCENT RESIDENCES"):
        fetch.fetch_ura("CANBERRA CRESCENT RESIDENCE")


def test_find_edgeprop_project_matches_names_case_insensitively(tmp_path, monkeypatch):
    listing = tmp_path / "projects.csv"
    listing.write_text("name,url,slug\nCanberra Crescent Residences,https://www.edgeprop.sg/condo-apartment/ccr,ccr\n")
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **k: pytest.fail("discovery must not run for a listed project"))
    assert fetch.find_edgeprop_project("CANBERRA CRESCENT RESIDENCES", listing, tmp_path)["slug"] == "ccr"


def test_find_edgeprop_project_runs_discovery_for_unlisted_names(tmp_path, monkeypatch):
    listing = tmp_path / "projects.csv"
    listing.write_text("name,url,slug\n")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        (tmp_path / "edgeprop_projects.csv").write_text("name,url,slug\nNEW PROJECT,https://x/new,new\n")

    monkeypatch.setattr(fetch.subprocess, "run", fake_run)
    assert fetch.find_edgeprop_project("New Project", listing, tmp_path)["slug"] == "new"
    assert "discover" in calls[0]
