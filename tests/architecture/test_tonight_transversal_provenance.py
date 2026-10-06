"""Cross-boundary regressions: domain mission -> public transport models."""
import pytest

from decision.acceptance_lineage_persistence import (
    serialize_night_mission, deserialize_night_mission,
)
from astropilot.app import TonightResponseModel, _accepted_mission_response
from decision.filtering.selected_filter import SelectedFilter
from decision.mission.night_mission import NightMission
from decision.services.tonight_application_service import TonightResult
from decision.services.tonight_response import TonightResponse


@pytest.mark.parametrize("source", ["selection", "user_default", "legacy-import"])
def test_filter_source_survives_both_public_mission_transports(source):
    mission = NightMission(
        target="Sh2-129", confidence=None,
        equipment=["samyang_183"], site_name="Buttes",
        mission_id="mission-a", decision_id="decision-a", selection_id="selection-a",
        imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha",
        selected_filter=SelectedFilter("Exact hardware", "Ha", 6.5, source=source),
    )
    mission = deserialize_night_mission(serialize_night_mission(mission))
    assert mission.selected_filter.source == source
    response = TonightResponse.from_result(TonightResult({}, None, mission)).to_dict()
    tonight = TonightResponseModel.model_validate(response).model_dump()
    accepted = _accepted_mission_response(mission).model_dump()
    for payload in (response, tonight, accepted):
        assert payload["selected_filter"] == {
            "name": "Exact hardware", "filter_type": "Ha", "bandwidth_nm": 6.5,
            "source": source,
        }
    assert accepted["acquisition_intent_id"] == mission.acquisition_intent_id


def test_accepted_legacy_mission_does_not_invent_intent_or_filter():
    mission = NightMission(
        target="M31", confidence=None, equipment=["setup"], site_name="Buttes",
        mission_id="mission-a", decision_id="decision-a", selection_id="selection-a",
    )
    accepted = _accepted_mission_response(mission).model_dump()
    assert accepted["acquisition_intent_id"] is None
    assert accepted["selected_filter"] is None
