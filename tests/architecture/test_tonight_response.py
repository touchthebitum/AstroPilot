from datetime import date, datetime, timezone

import pytest

from decision.filtering.selected_filter import SelectedFilter
from decision.mission.night_mission import MissionReason, NightMission
from decision.models.candidate import Candidate
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.tonight_application_service import (
    TonightResult,
    TonightStatus,
)
from decision.services.tonight_response import TonightResponse


def make_candidate():
    return Candidate(
        name="Andromeda",
        catalog_key="M31",
        priority=1.0,
        astro_score=82.0,
        final_score=79.0,
        decision_score=77.0,
        portfolio_score=75.0,
        global_score=81.0,
        setup_score=68.0,
        best_setup="widefield",
        closure_bonus=0.0,
    )


@pytest.mark.parametrize(
    "status",
    [
        TonightStatus.FORECAST_UNAVAILABLE,
        TonightStatus.NO_NIGHT,
        TonightStatus.NO_CANDIDATE,
        TonightStatus.NO_RECOMMENDATION,
    ],
)
def test_partial_results_produce_stable_transport_status(status):
    response = TonightResponse.from_result(
        TonightResult(None, None, None, status=status)
    )

    assert response.to_dict() == {
        "status": status.value,
        "night_date": None,
        "target": None,
        "catalog_key": None,
        "action": None,
        "recommendation_confidence": None,
        "mission_confidence": None,
        "scores": {},
        "window_start": None,
        "window_end": None,
        "recommended_hours": 0.0,
        "expected_gain": 0.0,
        "equipment": [],
        "selected_filter": None,
        "reasons": [],
    }


def test_complete_result_maps_only_json_compatible_values():
    candidate = make_candidate()
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=0.91,
    )
    mission = NightMission(
        target="Andromeda",
        confidence=0.87,
        reasons=[MissionReason("Excellent altitude", "success", "72°")],
        equipment=["Widefield", "ASI2600MC"],
        window_start=datetime(2026, 9, 1, 22, 30, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 2, 0, tzinfo=timezone.utc),
        recommended_hours=3.5,
        expected_gain=12.0,
        selected_filter=SelectedFilter("L-Pro", "broadband", 50.0),
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=mission,
        )
    ).to_dict()

    assert response["status"] == "available"
    assert response["night_date"] == "2026-09-01"
    assert response["target"] == "Andromeda"
    assert response["catalog_key"] == "M31"
    assert response["action"] == "start_project"
    assert response["recommendation_confidence"] == 0.91
    assert response["scores"] == {
        "astro_score": 82.0,
        "decision_score": 77.0,
        "final_score": 79.0,
        "portfolio_score": 75.0,
        "global_score": 81.0,
        "setup_score": 68.0,
    }
    assert response["window_start"] == "2026-09-01T22:30:00+00:00"
    assert response["selected_filter"] == {
        "name": "L-Pro",
        "filter_type": "broadband",
        "bandwidth_nm": 50.0,
    }
    assert response["reasons"] == [
        {
            "title": "Excellent altitude",
            "severity": "success",
            "value": "72°",
        }
    ]
