from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import astropilot.app as app_module
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
from decision.weather.weather_ingress import (
    WeatherIngressError,
    WeatherInsufficientError,
    WeatherSnapshot,
)
from decision.validation.weather_window_coverage import WeatherWindowCoverageError
from decision.validation.decision_consistency import DecisionConsistencyError
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.location.location_time import LocationTimeError


def make_result(*, decision_id=None):
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
            window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
            window_end=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
            recommended_hours=3.5,
        ),
        decision_id=decision_id,
    )


def test_tonight_endpoint_delegates_inputs_and_returns_json_contract():
    weather = object()
    reference_time = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)
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
        clock=lambda: reference_time,
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
            "reference_time_utc": reference_time,
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


def test_tonight_endpoint_preserves_durable_decision_id():
    client = make_client(result=make_result(decision_id="decision-123"))

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 200
    assert response.json()["decision_id"] == "decision-123"


def test_partial_tonight_result_preserves_durable_decision_id():
    client = make_client(
        result=TonightResult(
            None,
            None,
            None,
            status=TonightStatus.NO_MISSION,
            decision_id="partial-123",
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 200
    assert response.json()["decision_id"] == "partial-123"


@pytest.mark.parametrize(
    "error",
    [
        DecisionForecastEvidencePersistenceError("storage_failed"),
        OSError("filesystem unavailable"),
    ],
)
def test_persistence_failure_is_a_controlled_service_error(error):
    class Service:
        def evaluate(self, **kwargs):
            raise error

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=lambda: {},
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "decision_persistence_unavailable",
        "message": "Durable decision persistence is temporarily unavailable.",
    }


DEFAULT_WEATHER = {"weather": True}


def make_weather_snapshot(retrieved_at_utc, *, valid_until=None):
    valid_from = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return WeatherSnapshot(
        payload={"hourly": {}},
        provider="Open-Meteo",
        retrieved_at_utc=retrieved_at_utc,
        requested_latitude=46.7508,
        requested_longitude=6.5495,
        grid_latitude=46.75,
        grid_longitude=6.55,
        grid_distance_km=0.1,
        elevation_m=837.0,
        timezone="Europe/Zurich",
        timezone_source="coordinates_local",
        utc_offset_seconds=7200,
        valid_from=valid_from,
        valid_until=valid_until or valid_from + timedelta(hours=47),
        hour_count=48,
        completeness=1.0,
    )


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


def test_invalid_weather_is_rejected_before_evaluation():
    class Service:
        def evaluate(self, **kwargs):
            raise AssertionError("service must not run with invalid weather")

    def invalid_weather(lat, lon):
        raise WeatherIngressError(["invalid_unit_wind_speed_10m"])

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=invalid_weather,
            profile_provider=lambda: {},
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "weather_invalid",
        "message": "Weather data failed validation.",
    }


def test_insufficient_weather_has_a_distinct_service_error():
    def insufficient_weather(lat, lon):
        raise WeatherInsufficientError(["hourly_coverage_below_24"])

    client = TestClient(
        create_app(
            service_factory=lambda: None,
            weather_provider=insufficient_weather,
            profile_provider=lambda: {},
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "weather_insufficient"


def test_stale_weather_is_rejected_before_evaluation_with_injected_clock():
    reference = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
    weather = make_weather_snapshot(reference - timedelta(minutes=91))

    class Service:
        def evaluate(self, **kwargs):
            raise AssertionError("service must not run with stale weather")

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: weather,
            profile_provider=lambda: {},
            clock=lambda: reference,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "weather_stale",
        "message": "Weather data is too old for a reliable decision.",
    }


def test_fresh_weather_transport_exposes_server_calculated_age(monkeypatch):
    reference = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
    weather = make_weather_snapshot(reference - timedelta(minutes=42, seconds=30))
    result = make_result()
    evaluations = []
    service_calls = []
    clock_calls = []
    evaluate = app_module.WeatherTrustDecisionEvaluator.evaluate

    def record_evaluation(evidence, *, context):
        evaluations.append((evidence, context))
        return evaluate(evidence, context=context)

    monkeypatch.setattr(
        app_module.WeatherTrustDecisionEvaluator,
        "evaluate",
        record_evaluation,
    )

    class Service:
        def evaluate(self, **kwargs):
            service_calls.append(kwargs)
            return result

    def clock():
        clock_calls.append(None)
        return reference

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: weather,
            profile_provider=lambda: {},
            clock=clock,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 200
    trust = response.json()["weather_trust"]
    assert trust["snapshot_age_minutes"] == 42.5
    assert trust["freshness_status"] == "fresh"
    assert trust["maximum_age_minutes"] == 90
    assert response.json()["weather_decision"] == {
        "evidence_quality": "insufficient",
        "admissibility": "caution",
        "reasons": ["provider_reliability_unavailable"],
        "presentation": {
            "label": "Validation météo partielle",
            "summary": (
                "Certaines preuves historiques de fiabilité ne sont pas encore "
                "disponibles ; cela ne signifie pas que la météo est mauvaise."
            ),
        },
    }
    assert response.json()["status"] == "available"
    assert response.json()["target"] == "Andromeda"
    assert result.recommendation is not None
    assert result.mission is not None
    assert len(evaluations) == 1
    evidence, context = evaluations[0]
    assert evidence.snapshot is weather
    assert evidence.freshness.snapshot_age_minutes == 42.5
    assert evidence.selected_window_covered is True
    assert evidence.provider_reliability is None
    assert context.provider_id == weather.provider
    assert context.decision_location.latitude == 46.7508
    assert context.decision_location.longitude == 6.5495
    assert context.reliability_context is None
    assert clock_calls == [None]
    assert service_calls[0]["reference_time_utc"] is reference


def test_uncovered_mission_window_returns_refused_without_active_mission():
    reference = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
    weather = make_weather_snapshot(
        reference - timedelta(minutes=5),
        valid_until=datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
    )
    evaluation_calls = []

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return make_result()

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: weather,
            profile_provider=lambda: {},
            clock=lambda: reference,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert len(evaluation_calls) == 1
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "weather_refused"
    assert payload["weather_decision"] == {
        "evidence_quality": "insufficient",
        "admissibility": "refused",
        "reasons": ["selected_window_uncovered"],
        "presentation": {
            "label": "Mission non confirmée",
            "summary": (
                "La fenêtre calculée dépasse la période couverte par les données "
                "météo disponibles."
            ),
        },
    }
    assert payload["target"] is None
    assert payload["catalog_key"] is None
    assert payload["action"] is None
    assert payload["recommendation_confidence"] is None
    assert payload["mission_confidence"] is None
    assert payload["scores"] == {}
    assert payload["window_start"] is None
    assert payload["window_end"] is None
    assert payload["recommended_hours"] == 0.0
    assert payload["expected_gain"] == 0.0
    assert payload["equipment"] == []
    assert payload["selected_filter"] is None
    assert payload["productivity"] is None
    assert payload["tasks"] == []
    assert payload["advices"] == []


@pytest.mark.parametrize(
    ("issue", "code"),
    [
        ("invalid_mission_window", "decision_invalid"),
        ("invalid_weather_coverage", "weather_invalid"),
        ("unexpected_window_issue", "decision_invalid"),
    ],
)
def test_structural_or_unknown_window_issue_remains_technical(
    monkeypatch,
    issue,
    code,
):
    reference = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
    weather = make_weather_snapshot(reference - timedelta(minutes=5))

    def fail_coverage(mission, snapshot):
        raise WeatherWindowCoverageError([issue])

    monkeypatch.setattr(
        app_module,
        "validate_selected_window_weather_coverage",
        fail_coverage,
    )
    client = TestClient(
        create_app(
            service_factory=lambda: type(
                "Service", (), {"evaluate": lambda self, **kwargs: make_result()}
            )(),
            weather_provider=lambda lat, lon: weather,
            profile_provider=lambda: {},
            clock=lambda: reference,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == code


def test_internally_inconsistent_decision_is_rejected_before_transport():
    class Service:
        def evaluate(self, **kwargs):
            raise DecisionConsistencyError(["recommended_hours_exceed_productive_hours"])

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=lambda: {},
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "decision_invalid",
        "message": "The decision failed consistency validation.",
    }


def test_unresolved_location_timezone_stops_before_evaluation():
    def unresolved_timezone(lat, lon):
        raise LocationTimeError("timezone_not_found")

    client = TestClient(
        create_app(
            service_factory=lambda: None,
            weather_provider=unresolved_timezone,
            profile_provider=lambda: {},
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "location_timezone_unresolved"


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


@pytest.mark.parametrize(
    "status",
    [
        TonightStatus.NO_NIGHT,
        TonightStatus.NO_CANDIDATE,
        TonightStatus.NO_RECOMMENDATION,
        TonightStatus.NO_MISSION,
        TonightStatus.NO_PRODUCTIVE_WINDOW,
    ],
)
def test_empty_product_results_remain_successful_business_responses(status):
    client = make_client(
        result=TonightResult(
            None,
            None,
            None,
            status=status,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert response.status_code == 200
    assert response.json()["status"] == status.value
    assert response.json()["weather_decision"] is None


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
        "TonightWeatherTrustModel",
        "TonightWeatherDecisionModel",
        "WeatherEvidenceQuality",
        "WeatherDecisionAdmissibility",
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
    assert tonight_response["weather_trust"]["anyOf"][0]["$ref"].endswith(
        "TonightWeatherTrustModel"
    )
    assert tonight_response["weather_decision"]["anyOf"][0]["$ref"].endswith(
        "TonightWeatherDecisionModel"
    )
    weather_decision = schemas["TonightWeatherDecisionModel"]["properties"]
    assert weather_decision["evidence_quality"]["$ref"].endswith(
        "WeatherEvidenceQuality"
    )
    assert weather_decision["admissibility"]["$ref"].endswith(
        "WeatherDecisionAdmissibility"
    )
    assert weather_decision["reasons"]["items"]["type"] == "string"
    assert weather_decision["presentation"]["$ref"].endswith(
        "TonightWeatherDecisionPresentationModel"
    )
    weather_trust = schemas["TonightWeatherTrustModel"]["properties"]
    assert weather_trust["snapshot_age_minutes"]["minimum"] == 0.0
    assert weather_trust["freshness_status"]["const"] == "fresh"
    assert weather_trust["maximum_age_minutes"]["exclusiveMinimum"] == 0


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
    assert response_example["weather_decision"] == {
        "evidence_quality": "insufficient",
        "admissibility": "caution",
        "reasons": ["provider_reliability_unavailable"],
        "presentation": {
            "label": "Validation météo partielle",
            "summary": (
                "Certaines preuves historiques de fiabilité ne sont pas encore "
                "disponibles ; cela ne signifie pas que la météo est mauvaise."
            ),
        },
    }


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
    error_examples = operation["responses"]["503"]["content"][
        "application/json"
    ]["examples"]
    assert error_examples["weather_invalid"]["value"]["detail"]["code"] == (
        "weather_invalid"
    )
    assert error_examples["weather_insufficient"]["value"]["detail"][
        "code"
    ] == "weather_insufficient"
    assert error_examples["weather_stale"]["value"]["detail"]["code"] == (
        "weather_stale"
    )
    assert "weather_window_uncovered" not in error_examples
    assert error_examples["decision_invalid"]["value"]["detail"]["code"] == (
        "decision_invalid"
    )
    assert error_examples["location_timezone_unresolved"]["value"]["detail"][
        "code"
    ] == "location_timezone_unresolved"
