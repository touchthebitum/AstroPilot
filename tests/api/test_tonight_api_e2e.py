from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import astro_score
import astropilot.app as app_module
import decision.services.decision_acceptance_application as acceptance_module
from astropilot.app import create_app
from decision.forecast.forecast_run import ForecastRun
from decision.intelligence.analysis_result import AnalysisResult
from decision.mission.night_mission import NightMission
from decision.mission.mission_input import MissionInput
from decision.models.candidate import Candidate, CandidateProvenance
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
from decision.weather.decision_forecast_evidence import (
    build_decision_forecast_evidence,
)
from decision.weather.weather_ingress import WeatherSnapshot


def test_http_request_runs_real_application_composition_once(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    reference_time = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)
    calls = {
        "weather": [],
        "forecast": [],
        "candidates": [],
        "recommendation": [],
        "mission": [],
    }
    weather = WeatherSnapshot(
        payload={"hourly": {}},
        provider="Open-Meteo",
        retrieved_at_utc=reference_time - timedelta(minutes=5),
        requested_latitude=47.1,
        requested_longitude=6.8,
        grid_latitude=47.1,
        grid_longitude=6.8,
        grid_distance_km=0.0,
        elevation_m=1000.0,
        timezone="Europe/Zurich",
        timezone_source="coordinates_local",
        utc_offset_seconds=7200,
        valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 9, 3, tzinfo=timezone.utc),
        hour_count=48,
        completeness=1.0,
    )
    selected_objects = [{"catalog_key": "M31", "name": "Andromeda"}]
    selected_night = {
        "date": date(2026, 9, 1),
        "duration": 3.5,
        "top_objects": selected_objects,
        "object_evaluations": {
            "M31": {
                "decision_context": SimpleNamespace(
                    site=SimpleNamespace(name="Mont Sujet"),
                    session=SimpleNamespace(
                        end_time=datetime(2026, 9, 2, 4, tzinfo=timezone.utc)
                    ),
                )
            }
        },
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
    shortlist_candidate = Candidate(
        name="Orion",
        catalog_key="M42",
        priority=None,
        astro_score=76.0,
        final_score=72.0,
        decision_score=70.0,
        portfolio_score=None,
        global_score=76.0,
        setup_score=64.0,
        best_setup="widefield",
        closure_bonus=None,
        acquired_hours=None,
        provenance=CandidateProvenance.DISCOVERY,
    )
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
            shortlist_entries=(shortlist_candidate,),
        ),
        confidence=0.91,
    )
    mission = NightMission(
        target="Andromeda",
        confidence=0.87,
        equipment=["Widefield"],
        recommended_hours=3.5,
        window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 4, tzinfo=timezone.utc),
        astro_quality=AstroQualityResult(
            score=84.0,
            confidence=0.9,
            limiting_factor="clouds",
            metrics={"altitude": 92.0, "clouds": 70.0},
        ),
        productivity=NightProductivityResult(
            astronomical_hours=6.0,
            productive_hours=3.5,
            confidence=0.58,
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
        return ForecastRun(
            nights=(
                {"date": date(2026, 9, 2), "top_objects": []},
                selected_night,
            ),
            evidence=build_decision_forecast_evidence(
                weather,
                [{
                    "time": datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
                    "temperature_2m": 8.0,
                    "relative_humidity_2m": 60.0,
                    "wind_speed_10m": 5.0,
                    "cloud_cover": 20.0,
                }],
            ),
        )

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
            mission_input = kwargs["build_mission_input"](
                selected_night["object_evaluations"][kwargs["recommended_key"]]
            )
            return replace(
                mission,
                site_name="Mont Sujet",
                mission_id=mission_input.mission_id,
                decision_id=mission_input.decision_id,
                selection_id=mission_input.selection_id,
            )

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
        "build_mission_input",
        lambda evaluation, *, profile: MissionInput(
            window_start=mission.window_start,
            window_end=mission.window_end,
            astronomical_hours=6.0,
            weather=None,
            moon_penalty=None,
            recommended_hours=mission.recommended_hours,
            expected_gain=mission.expected_gain,
        ),
    )
    profile_loads = []

    def load_profile():
        profile_loads.append(True)
        return {
            "active_equipment": "samyang_183",
            "available_equipment": ["samyang_183", "fra400_2600"],
            "projects": {"M31": {"hours": 2}},
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
    monkeypatch.setattr(
        app_module,
        "validate_selected_window_weather_coverage",
        lambda mission, snapshot: None,
    )
    monkeypatch.setattr(acceptance_module, "_utc_now", lambda: reference_time)

    client = TestClient(create_app(clock=lambda: reference_time))
    response = client.post(
        "/v1/tonight",
        json={
            "location": {
                "name": "La Chaux-de-Fonds",
                "latitude": 47.1,
                "longitude": 6.8,
            },
            "equipment": "fra400_2600",
            "goal": "galaxies",
            "bortle": 4,
        },
    )

    assert response.status_code == 200
    assert profile_loads == [True]
    assert calls["weather"] == [(47.1, 6.8)]
    assert len(calls["forecast"]) == 1
    forecast_kwargs = calls["forecast"][0][1]
    assert forecast_kwargs["reference_time_utc"] is reference_time
    assert forecast_kwargs["profile"]["active_equipment"] == "fra400_2600"
    assert forecast_kwargs["profile"]["available_equipment"] == [
        "fra400_2600"
    ]
    assert "equipment" not in forecast_kwargs
    assert calls["candidates"] == [
        (
            selected_objects,
            3.5,
            {
                "active_equipment": "fra400_2600",
                "available_equipment": ["fra400_2600"],
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
    assert calls["mission"] == []
    payload = response.json()
    assert payload["status"] == "available"
    assert isinstance(payload["decision_id"], str)
    assert payload["decision_id"]
    assert payload["target"] == "Andromeda"
    assert payload["catalog_key"] == "M31"
    assert payload["provenance"] == CandidateProvenance.PROJECT.value
    assert payload["target_decision_status"] == "recommended"
    assert payload["shortlist_entries"] == [
        {
            "target": "Orion",
            "catalog_key": "M42",
            "provenance": "discovery",
            "decision_score": 70.0,
            "final_score": 72.0,
            "target_decision_status": None,
        }
    ]
    assert payload["alternatives"] == []
    assert payload["target_common_name"] == "Galaxie d’Andromède"
    assert payload["mission_confidence"] is None
    assert payload["astro_quality"] is None
    assert payload["productivity"] is None
    assert payload["dew_risk"] is None
    assert payload["postponement_risk"] is None
    assert payload["season"] is None

    accepted = client.post(
        "/v1/decision-selections",
        json={
            "decision_id": payload["decision_id"],
            "source": "primary_recommendation",
            "selected_catalog_key": "M31",
            "selected_at": "2026-09-10T20:00:00+00:00",
        },
    )

    assert accepted.status_code == 200, accepted.json()
    assert accepted.json()["catalog_key"] == "M31"
    assert accepted.json()["decision_id"] == payload["decision_id"]
    assert accepted.json()["selection_id"]
    assert accepted.json()["mission_id"]
    assert accepted.json()["mission"]["mission_id"] == accepted.json()["mission_id"]
    assert accepted.json()["mission"]["selection_id"] == accepted.json()["selection_id"]
    assert accepted.json()["mission"]["decision_id"] == payload["decision_id"]
    assert len(calls["mission"]) == 1

    created_execution = client.post(
        "/v1/executions",
        json={
            "execution_id": "execution-e2e",
            "mission_id": accepted.json()["mission_id"],
        },
    )
    started_execution = client.post(
        "/v1/execution-transitions",
        json={
            "execution_id": "execution-e2e",
            "mission_id": accepted.json()["mission_id"],
            "status": "in_progress",
            "actual_start": "2026-09-10T22:00:00+00:00",
            "actual_end": None,
            "actual_duration": None,
        },
    )
    recorded_evidence = client.post(
        "/v1/outcome-evidence",
        json={
            "evidence_id": "evidence-e2e",
            "execution_id": "execution-e2e",
            "category": "field",
            "observed_at": "2026-09-10T23:00:00+00:00",
            "source": "user",
        },
    )

    assert created_execution.status_code == 200, created_execution.json()
    assert created_execution.json()["status"] == "not_started"
    assert created_execution.json()["actual_start"] is None
    assert started_execution.status_code == 200, started_execution.json()
    assert started_execution.json()["status"] == "in_progress"
    assert started_execution.json()["execution_id"] == "execution-e2e"
    assert started_execution.json()["mission_id"] == accepted.json()["mission_id"]
    assert recorded_evidence.status_code == 200, recorded_evidence.json()
    assert recorded_evidence.json()["evidence_id"] == "evidence-e2e"
    assert recorded_evidence.json()["execution_id"] == "execution-e2e"
