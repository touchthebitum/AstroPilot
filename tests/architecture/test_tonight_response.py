from datetime import date, datetime, timezone

import pytest

from decision.filtering.selected_filter import SelectedFilter
from decision.mission.night_mission import MissionReason, NightMission
from decision.models.candidate import Candidate
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_window import NightWindow
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.quality.astro_quality_result import AstroQualityResult
from decision.recommendation.recommendation import Recommendation
from decision.quality.dew_risk_result import DewRiskResult
from decision.risk.project_risk_context import ProjectRiskContext
from decision.risk.risk_report import RiskReport
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
        "astro_quality": None,
        "productivity": None,
        "dew_risk": None,
        "postponement_risk": None,
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
        astro_quality=AstroQualityResult(
            score=78.0,
            confidence=0.84,
            limiting_factor="clouds",
            metrics={"altitude": 91.0, "clouds": 64.0},
        ),
        productivity=NightProductivityResult(
            astronomical_hours=6.0,
            productive_hours=3.5,
            confidence=0.82,
            cloud_loss=1.0,
            moon_loss=0.5,
            altitude_loss=0.25,
            weather_loss=0.75,
            display_start_hour=22,
            windows=[
                NightWindow(
                    start_hour=1.5,
                    end_hour=4.25,
                    productivity=0.88,
                    altitude=67.0,
                    cloud_cover=12.0,
                    moon_penalty=0.1,
                    seeing=1.4,
                    productive=True,
                    reason="stable_conditions",
                )
            ],
        ),
        dew_risk=DewRiskResult(
            dew_point_c=7.2,
            spread_c=1.8,
            risk="HIGH",
            score=82.0,
        ),
        risk_report=RiskReport(
            level="MEDIUM",
            score=63,
            explanation=["Only two favorable nights remain"],
            context=ProjectRiskContext(
                priority=8.0,
                remaining_hours=5.5,
                completion=0.45,
                season_remaining_days=21,
                favorable_nights=2,
                required_nights=2,
                productive_hours_per_night=3.5,
                night_capacity_source="history",
                historical_nights=6,
            ),
        ),
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
    assert response["astro_quality"] == {
        "score": 78.0,
        "confidence": 0.84,
        "label": "very_good",
        "limiting_factor": "clouds",
        "metrics": {"altitude": 91.0, "clouds": 64.0},
    }
    assert response["productivity"] == {
        "astronomical_hours": 6.0,
        "productive_hours": 3.5,
        "confidence": 0.82,
        "cloud_loss": 1.0,
        "moon_loss": 0.5,
        "altitude_loss": 0.25,
        "weather_loss": 0.75,
        "display_start_hour": 22,
        "windows": [
            {
                "start_offset_hours": 1.5,
                "end_offset_hours": 4.25,
                "start_time": "23:30",
                "end_time": "02:15",
                "productivity": 0.88,
                "productive": True,
                "reason": "stable_conditions",
                "altitude": 67.0,
                "cloud_cover": 12.0,
                "moon_penalty": 0.1,
                "seeing": 1.4,
            }
        ],
    }
    assert response["dew_risk"] == {
        "level": "HIGH",
        "score": 82.0,
        "dew_point_c": 7.2,
        "spread_c": 1.8,
    }
    assert response["postponement_risk"] == {
        "level": "MEDIUM",
        "score": 63,
        "explanations": ["Only two favorable nights remain"],
        "required_nights": 2,
        "productive_hours_per_night": 3.5,
        "capacity_source": "history",
        "historical_nights": 6,
        "remaining_hours": 5.5,
        "favorable_nights": 2,
        "season_remaining_days": 21,
    }
    assert response["reasons"] == [
        {
            "title": "Excellent altitude",
            "severity": "success",
            "value": "72°",
        }
    ]


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (90.0, "excellent"),
        (75.0, "very_good"),
        (60.0, "good"),
        (40.0, "average"),
        (39.9, "low"),
    ],
)
def test_astro_quality_labels_are_stable(score, label):
    mission = NightMission(
        target="Andromeda",
        confidence=0.8,
        astro_quality=AstroQualityResult(score=score, confidence=0.9),
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=None,
            mission=mission,
        )
    )

    assert response.astro_quality.label == label
