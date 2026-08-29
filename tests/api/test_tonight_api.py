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
        profile_provider=lambda: {},
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
    assert payload["target_common_name"] == "Galaxie d’Andromède"
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
            profile_provider=lambda: {},
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
            profile_provider=lambda: {},
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


def test_openapi_schema_exposes_decision_intelligence_contracts():
    client = make_client(result=make_result())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert {
        "TonightAstroQualityModel",
        "TonightProductivityModel",
        "TonightProductivityWindowModel",
        "TonightDewRiskModel",
        "TonightPostponementRiskModel",
        "TonightSeasonModel",
        "TonightExplanationModel",
        "TonightTaskModel",
        "TonightAdviceModel",
    }.issubset(schemas)

    tonight_response = schemas["TonightResponseModel"]["properties"]
    assert tonight_response["astro_quality"]["anyOf"][0]["$ref"].endswith(
        "TonightAstroQualityModel"
    )
    assert tonight_response["productivity"]["anyOf"][0]["$ref"].endswith(
        "TonightProductivityModel"
    )
    assert tonight_response["postponement_risk"]["anyOf"][0][
        "$ref"
    ].endswith("TonightPostponementRiskModel")
    assert tonight_response["tasks"]["items"]["$ref"].endswith(
        "TonightTaskModel"
    )
    assert tonight_response["advices"]["items"]["$ref"].endswith(
        "TonightAdviceModel"
    )


def test_openapi_documents_tonight_request_and_available_response_examples():
    client = make_client(result=make_result())

    schema = client.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    request_example = schemas["TonightRequest"]["examples"][0]
    assert request_example["location"] == {
        "name": "Buttes",
        "latitude": 46.7508,
        "longitude": 6.5495,
    }
    assert request_example["goal"] == "balanced"
    assert request_example["target"] == "deep_sky"

    response_example = schemas["TonightResponseModel"]["examples"][0]
    assert response_example["status"] == "available"
    assert response_example["astro_quality"]["label"] == "very_good"
    assert response_example["productivity"]["windows"][0]["productive"] is True
    assert response_example["postponement_risk"]["level"] == "medium"
    assert response_example["season"]["analysis_name"] == "season_window"
    assert response_example["tasks"][0]["title"] == "Installer le matériel"
    assert response_example["advices"][0]["category"] == "weather"


def test_openapi_documents_tonight_operation_and_error_examples():
    client = make_client(result=make_result())

    operation = client.get("/openapi.json").json()["paths"]["/v1/tonight"][
        "post"
    ]

    assert operation["summary"] == "Recommend tonight's astrophotography mission"
    assert "Decision Intelligence" in operation["description"]
    assert operation["responses"]["422"]["content"]["application/json"][
        "examples"
    ]["invalid_request"]["value"]["detail"][0]["type"] == "less_than_equal"
    assert operation["responses"]["503"]["content"]["application/json"][
        "examples"
    ]["weather_unavailable"]["value"]["detail"]["code"] == (
        "weather_unavailable"
    )
