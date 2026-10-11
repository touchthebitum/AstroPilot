from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import astro_score
from astropilot.app import TonightResponseModel
from decision.forecast.forecast_run import ForecastRun
from decision.mission.mission_builder import NightMissionBuilder
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.tonight_application_service import TonightApplicationService, TonightStatus
from decision.services.tonight_mission_service import TonightMissionService
from decision.services.tonight_response import TonightResponse
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.models.opportunity_alert import OpportunityAlertPolicy, OpportunityAlertStatus
from decision.services.opportunity_alert_service import OpportunityAlertService
from unittest.mock import Mock


def test_empty_project_profile_preserves_creation_refusal_through_api(monkeypatch):
    # Only forecast acquisition is fixed. Ranking, input construction and the
    # creation guard are production code; no user profile or filter file is read.
    monkeypatch.setattr(astro_score.FilterInventoryLoader, "load", lambda: ())
    start = datetime(2026, 10, 11, 19, tzinfo=timezone.utc)
    profile = {"location": {"name": "Test", "latitude": 46.2, "longitude": 6.1},
               "active_equipment": "fra400_2600", "available_equipment": ["fra400_2600"],
               "preferences": {"bortle": 4}, "projects": {}, "sessions": []}
    original = deepcopy(profile)
    target = {"name": "M31", "catalog_key": "M31", "global_score": 145,
              "best_setup": "fra400_2600", "setup_score": 45,
              "decision_context": NS(equipment=NS(setup=None)),
              "decision_summary": NS(positives=[], negatives=[])}
    evaluation = {**target, "window": {"start": start, "end": start + timedelta(hours=2)}}
    night = {"date": "2026-10-11", "top_objects": [target], "object_evaluations": {"M31": evaluation}}
    service = TonightApplicationService(
        forecast_nights=lambda *args, **kwargs: ForecastRun([night], DecisionForecastEvidence(())),
        build_candidates=astro_score.recommend_project_for_night,
        opportunity_recommendation_service=NS(build=lambda *, candidates: Recommendation(
            opportunity=Opportunity(action=Action.START_PROJECT, candidate=candidates[0]), confidence=None)),
        tonight_mission_service=TonightMissionService(
            build_mission=NightMissionBuilder.build,
            build_mission_with_actionability_diagnostic=NightMissionBuilder.build_with_actionability_diagnostic),
        build_mission_input=astro_score.build_mission_input,
    )
    result = service.evaluate(profile=profile, weather=object(), reference_time_utc=start,
                              bortle=4, availability=SessionAvailability(SessionAvailabilityMode.ALL_NIGHT))
    assert result.status is TonightStatus.NO_MISSION
    assert result.recommendation.opportunity.candidate.catalog_key == "M31"
    assert result.mission is None
    assert result.actionability_refusal is None
    assert result.creation_refusal == "modern_mission_authorization_required"
    payload = TonightResponse.from_result(result).to_dict()
    transported = TonightResponseModel.model_validate(payload).model_dump()
    assert transported["creation_refusal"] == result.creation_refusal
    assert transported["provenance"] == "discovery"
    assert transported["recommended_hours"] == 0
    assert profile == original
    ledger = Mock()
    policy = OpportunityAlertPolicy(enabled=True, site_name="Test", project_keys=("M31",),
                                    intent_ids=("test",), filter_profile_ids=("test",))
    alerts = OpportunityAlertService(ledger)
    decision = alerts.evaluate(result=result, policy=policy, logical_time=start)
    assert decision.status is OpportunityAlertStatus.NO_ALERT
    assert decision.reason_codes == ("tonight_not_admissible",)
    ledger.claim.assert_not_called()
