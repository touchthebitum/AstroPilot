from datetime import date

from fastapi.testclient import TestClient

from astropilot.app import create_app
from decision.mission.night_mission import NightMission
from decision.models.candidate import Candidate
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.tonight_application_service import (
    TonightResult,
    TonightStatus,
)


def make_result():
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
    return TonightResult(
        night={"date": date(2026, 9, 1)},
        recommendation=recommendation,
        mission=NightMission(
            target="Andromeda",
            confidence=0.87,
            equipment=["Widefield"],
            recommended_hours=3.5,
        ),
    )


def test_tonight_endpoint_delegates_inputs_and_returns_json_contract():
    weather = object()
    weather_calls = []
    evaluation_calls = []

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return make_result()

    app = create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: (
            weather_calls.append((lat, lon)) or weather
        ),
    )

    response = TestClient(app).post(
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
            "target": "deep_sky",
            "bortle": 4,
        },
    )

    assert response.status_code == 200
    assert weather_calls == [(47.1, 6.8)]
    assert evaluation_calls == [
        {
            "profile": {
                "projects": {"M31": {"hours": 2}},
                "location": {
                    "name": "La Chaux-de-Fonds",
                    "latitude": 47.1,
                    "longitude": 6.8,
                },
            },
            "weather": weather,
            "equipment": "portable",
            "goal": "galaxies",
            "target": "deep_sky",
            "bortle": 4,
        }
    ]
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["night_date"] == "2026-09-01"
    assert payload["target"] == "Andromeda"
    assert payload["catalog_key"] == "M31"
    assert payload["recommended_hours"] == 3.5


DEFAULT_WEATHER = {"weather": True}


def make_client(*, result, weather=DEFAULT_WEATHER):
    class Service:
        def evaluate(self, **kwargs):
            return result

    return TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: weather,
        )
    )


def test_weather_unavailable_is_a_service_error_before_evaluation():
    class Service:
        def evaluate(self, **kwargs):
            raise AssertionError("service must not run without weather")

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: None,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "weather_unavailable"


def test_forecast_unavailable_is_a_service_error():
    client = make_client(
        result=TonightResult(
            None,
            None,
            None,
            status=TonightStatus.FORECAST_UNAVAILABLE,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "forecast_unavailable"


def test_empty_product_results_remain_successful_business_responses():
    client = make_client(
        result=TonightResult(
            None,
            None,
            None,
            status=TonightStatus.NO_NIGHT,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "no_night"


def test_request_coordinates_and_bortle_are_validated():
    client = make_client(result=make_result())

    response = client.post(
        "/v1/tonight",
        json={
            "location": {
                "name": "Invalid",
                "latitude": 120,
                "longitude": 6.8,
            },
            "bortle": 12,
        },
    )

    assert response.status_code == 422


def test_invalid_location_embedded_in_profile_is_rejected():
    client = make_client(result=make_result())

    response = client.post(
        "/v1/tonight",
        json={"profile": {"location": {"name": "Incomplete"}}},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_profile_location"
