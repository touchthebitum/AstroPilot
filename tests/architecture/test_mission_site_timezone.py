from dataclasses import replace
from decision.mission.night_mission import NightMission
from decision.acceptance_lineage_persistence import serialize_night_mission, deserialize_night_mission


def test_site_timezone_survives_persistence_and_legacy_read():
    mission = NightMission(target="Sh2-129", confidence=None, site_timezone="Europe/Madrid")
    document = serialize_night_mission(mission)
    restored = deserialize_night_mission(document)
    assert restored.site_timezone == "Europe/Madrid"
    document["fields"].pop("site_timezone")
    assert deserialize_night_mission(document, schema_version=10).site_timezone is None
