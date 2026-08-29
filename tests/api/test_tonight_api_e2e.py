from datetime import date

import pytest
from fastapi.testclient import TestClient

import astro_score
from astropilot.app import create_app
from decision.intelligence.analysis_result import AnalysisResult
from decision.mission.night_mission import NightMission
from decision.models.candidate import Candidate
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_window import NightWindow
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.quality.astro_quality_result import AstroQualityResult
from decision.quality.dew_risk_result import DewRiskResult
from decision.recommendation.recommendation import Recommendation
from decision.risk.project_risk_context import ProjectRiskContext
from decision.risk.risk_report import RiskReport


def test_http_request_runs_real_application_composition_once(monkeypatch):
    calls = {
        "weather": [],
        "forecast": [],
        "candidates": [],
        "recommendation": [],
        "mission": [],
    }
    weather = {"hourly": True}
    selected_objects = [{"catalog_key": "M31", "name": "Andromeda"}]
    selected_night = {
        "date": date(2026, 9, 1),
        "duration": 3.5,
        "top_objects": selected_objects,
    }
    candidate = Candidate(
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
        equipment=["Widefield"],
        recommended_hours=3.5,
        astro_quality=AstroQualityResult(
            score=84.0,
            confidence=0.9,
            limiting_factor="clouds",
            metrics={"altitude": 92.0, "clouds": 70.0},
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
                    start_hour=1.0,
                    end_hour=4.0,
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
            ),
        ),
        season_analysis=AnalysisResult(
            analysis_name="season",
            conclusion="Prime autumn window",
            confidence=0.89,
            data={"peak_month": "October"},
        ),
    )

    def fetch_weather(latitude, longitude):
        calls["weather"].append((latitude, longitude))
        return weather

    def forecast(*args, **kwargs):
        calls["forecast"].append((args, kwargs))
        return [
            {"date": date(2026, 9, 2), "top_objects": []},
            selected_night,
        ]

    def build_candidates(objects, available_hours, *, profile):
        calls["candidates"].append((objects, available_hours, profile))
        return [candidate]

    class RecommendationService:
        def build(self, *, candidates):
            calls["recommendation"].append(candidates)
            return recommendation

    class MissionService:
        def create(self, **kwargs):
            calls["mission"].append(kwargs)
            return mission

    monkeypatch.setattr(astro_score, "fetch_weather", fetch_weather)
    monkeypatch.setattr(astro_score, "forecast_astro", forecast)
    monkeypatch.setattr(
        astro_score,
        "recommend_project_for_night",
        build_candidates,
    )
    monkeypatch.setattr(
        astro_score,
        "opportunity_recommendation_service",
        RecommendationService(),
    )
    monkeypatch.setattr(
        astro_score,
        "tonight_mission_service",
        MissionService(),
    )
    profile_loads = []

    def load_profile():
        profile_loads.append(True)
        return {
            "available_equipment": ["widefield"],
            "projects": {"M42": {"hours": 4}},
        }

    monkeypatch.setattr(astro_score, "load_user_profile", load_profile)
    monkeypatch.setattr(
        astro_score,
        "save_user_profile",
        lambda profile: pytest.fail("API must not persist the profile"),
    )
    monkeypatch.setattr(
        astro_score.MissionPresenter,
        "present",
        lambda mission: pytest.fail("API must not print the mission"),
    )

    response = TestClient(create_app()).post(
        "/v1/tonight",
        json={
            "location": {
                "name": "La Chaux-de-Fonds",
                "latitude": 47.1,
                "longitude": 6.8,
            },
            "profile": {"projects": {"M31": {"hours": 2}}},
            "equipment": "portable",
            "goal": "galaxies",
            "bortle": 4,
        },
    )

    assert response.status_code == 200
    assert profile_loads == [True]
    assert calls["weather"] == [(47.1, 6.8)]
    assert len(calls["forecast"]) == 1
    assert calls["candidates"] == [
        (
            selected_objects,
            3.5,
            {
                "available_equipment": ["widefield"],
                "projects": {"M31": {"hours": 2}},
                "location": {
                    "name": "La Chaux-de-Fonds",
                    "latitude": 47.1,
                    "longitude": 6.8,
                },
            },
        )
    ]
    assert calls["recommendation"] == [[candidate]]
    assert len(calls["mission"]) == 1
    assert calls["mission"][0]["winner"] is selected_night
    assert calls["mission"][0]["objects"] is selected_objects
    assert calls["mission"][0]["recommended_key"] == "M31"
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["target"] == "Andromeda"
    assert payload["catalog_key"] == "M31"
    assert payload["target_common_name"] == "Galaxie d’Andromède"
    assert payload["astro_quality"] == {
        "score": 84.0,
        "confidence": 0.9,
        "label": "very_good",
        "limiting_factor": "clouds",
        "metrics": {"altitude": 92.0, "clouds": 70.0},
    }
    assert payload["productivity"]["productive_hours"] == 3.5
    assert payload["productivity"]["windows"][0]["start_time"] == "23:00"
    assert payload["productivity"]["windows"][0]["end_time"] == "02:00"
    assert payload["dew_risk"]["level"] == "HIGH"
    assert payload["postponement_risk"]["required_nights"] == 2
    assert payload["season"] == {
        "analysis_name": "season",
        "conclusion": "Prime autumn window",
        "confidence": 0.89,
        "data": {"peak_month": "October"},
    }
