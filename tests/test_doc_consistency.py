import os
import re

import provision_model
import framework_config as fc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_provision_weight_table_matches_config():
    """frameworks/1 public weight table (| # | `key` | weight | PROVENANCE |) must match
    framework_config — the load-bearing doc<->code numeric invariant, previously unguarded."""
    md = _read("frameworks/1-provision-framework.md")
    row = re.compile(
        r"^\|\s*\d+\s*\|\s*`([a-z_]+)`\s*\|\s*([\d.]+)\s*\|\s*(MEASURED|PARTLY_MEASURED|JUDGED)\s*\|",
        re.M,
    )
    found = {k: (float(w), prov) for k, w, prov in row.findall(md)}
    assert len(found) == 20, f"expected 20 weight rows in frameworks/1, parsed {len(found)}"
    assert set(found) == set(fc.PROVISION_WEIGHTS)
    for k, (w, prov) in found.items():
        assert abs(w - fc.PROVISION_WEIGHTS[k]) < 1e-9, f"{k}: doc {w} != config {fc.PROVISION_WEIGHTS[k]}"
        assert prov == fc.PROVENANCE[k], f"{k}: doc provenance {prov} != config {fc.PROVENANCE[k]}"


def test_private_weight_table_matches_config():
    """frameworks/1 W_PRIVATE table (| `key` | public | private | delta |) must match
    framework_config.PROVISION_WEIGHTS_PRIVATE."""
    md = _read("frameworks/1-provision-framework.md")
    row = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", re.M)
    found = {k: float(priv) for k, _pub, priv in row.findall(md)}
    assert len(found) == 20, f"expected 20 private-weight rows, parsed {len(found)}"
    assert set(found) == set(fc.PROVISION_WEIGHTS_PRIVATE)
    for k, priv in found.items():
        assert abs(priv - fc.PROVISION_WEIGHTS_PRIVATE[k]) < 1e-9, \
            f"{k}: doc {priv} != config {fc.PROVISION_WEIGHTS_PRIVATE[k]}"


def test_rail_slip_premium_doc_matches_code():
    """The rail 0.85 slip premium must be stated in frameworks/2 and equal the code constant."""
    import liveability_model
    md = _read("frameworks/2-liveability-matrix.md")
    assert "rail 0.85" in md, "frameworks/2 §1.1 must document the rail 0.85 slip premium"
    assert liveability_model.RAIL_SLIP_PREMIUM == 0.85


def test_w_has_20_components():
    assert len(provision_model.W) == 20


def test_provenance_keys_match_w():
    assert set(provision_model.PROVENANCE) == set(provision_model.W)


def test_w_private_same_keys_as_w():
    assert set(provision_model.W_PRIVATE) == set(provision_model.W)


from collections import Counter


def test_provenance_split_counts():
    c = Counter(provision_model.PROVENANCE.values())
    assert c["MEASURED"] == 14
    assert c["PARTLY_MEASURED"] == 6
    assert c["JUDGED"] == 0


def test_new_v2_components_provenance():
    prov = provision_model.PROVENANCE
    assert prov["jtc_industrial"] == "MEASURED"
    assert prov["air_quality"] == "PARTLY_MEASURED"
    assert prov["stewardship"] == "PARTLY_MEASURED"
    assert prov["hawker"] == "PARTLY_MEASURED"
