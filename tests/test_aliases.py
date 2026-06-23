import aliases
import momentum_model
import liveability_model
import value_model
import lease_risk_model


def test_pipeline_conflicts_resolved():
    # Boon Lay / Taman Jurong belong to Jurong West (momentum previously wrongly mapped them to Jurong East)
    assert aliases.canonicalise_pipeline_name("BOON LAY") == "JURONG WEST"
    assert aliases.canonicalise_pipeline_name("TAMAN JURONG") == "JURONG WEST"
    # Buona Vista is in Queenstown planning area (liveability previously wrongly mapped it to Holland Village)
    assert aliases.canonicalise_pipeline_name("BUONA VISTA") == "QUEENSTOWN"
    # Real estates map to themselves (no stale fold)
    assert aliases.canonicalise_pipeline_name("JURONG WEST") == "JURONG WEST"
    assert aliases.canonicalise_pipeline_name("KALLANG") == "KALLANG"


def test_pipeline_alias_single_source():
    # momentum.canonical and liveability.canonicalise_estate are the SAME shared function
    assert momentum_model.canonical is liveability_model.canonicalise_estate
    assert momentum_model.canonical("BUONA VISTA") == "QUEENSTOWN"


def test_estate_town_single_source():
    assert value_model.ESTATE_TOWN_ALIAS is aliases.ESTATE_TOWN_ALIAS
    assert lease_risk_model.ESTATE_TOWN_ALIAS is aliases.ESTATE_TOWN_ALIAS
    assert value_model.PRIVATE_DOMINANT_PROXIES is aliases.PRIVATE_DOMINANT_PROXIES


def test_estate_town_unchanged_entries():
    assert aliases.ESTATE_TOWN_ALIAS["CANBERRA"] == "SEMBAWANG"
    assert aliases.ESTATE_TOWN_ALIAS["HOLLAND VILLAGE"] == "QUEENSTOWN"
    assert aliases.ESTATE_TOWN_ALIAS["LENTOR"] == "ANG MO KIO"


def test_ingest_hdb_upgrading_uses_shared_alias():
    import ingest_hdb_upgrading as ih
    assert ih.ALIAS_MAP is aliases.PIPELINE_NAME_ALIAS
    hints = dict(ih.NAME_HINTS)
    assert hints["JURONG WEST"] == "JURONG WEST"
    assert hints["BOON LAY"] == "JURONG WEST"
    assert hints["TAMAN JURONG"] == "JURONG WEST"
    assert hints["KALLANG"] == "KALLANG"
