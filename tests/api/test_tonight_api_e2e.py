from datetime import date

import pytest
from fastapi.testclient import TestClient

import astro_score
from astropilot.app import create_app
from decision.mission.night_mission import NightMission
from decision.models.candidate import Candidate
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation


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
    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: pytest.fail("API must not load the CLI profile"),
    )
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
    assert calls["weather"] == [(47.1, 6.8)]
    assert len(calls["forecast"]) == 1
    assert calls["candidates"] == [
        (
            selected_objects,
            3.5,
            {
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
    assert response.json()["status"] == "available"
    assert response.json()["target"] == "Andromeda"
    assert response.json()["catalog_key"] == "M31"
