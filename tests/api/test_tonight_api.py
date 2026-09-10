from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import astropilot.app as app_module
import astropilot.user_profile as user_profile
import decision.services.session_availability_windowing as availability_windowing
from astropilot.app import create_app
from astropilot.user_profile import UserProfileError
from decision.mission.night_mission import NightMission
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.candidate_rejection import (
    CandidateRejection,
    CandidateRejectionBasis,
)
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.models.user_selection import UserSelectionSource
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.tonight_application_service import (
    TonightResult,
    TonightStatus,
)
from decision.services.durable_tonight_application_service import (
    DurableTonightApplicationService,
)
from decision.services.candidate_assessment import (
    CandidateAssessment,
    CandidateViabilityEvaluator,
)
import decision.services.tonight_application_service as tonight_service_module
from decision.weather.weather_ingress import (
    WeatherIngressError,
    WeatherInsufficientError,
    WeatherSnapshot,
)
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)
from decision.validation.weather_window_coverage import WeatherWindowCoverageError
from decision.validation.decision_consistency import DecisionConsistencyError
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.location.location_time import LocationTimeError


def valid_profile():
    return {
        "location": {"name": "Buttes", "latitude": 46.7508, "longitude": 6.5495},
        "preferences": {"bortle": 3},
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
    }


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


@pytest.mark.parametrize(
    "profile_error",
    [
        UserProfileError("Profil utilisateur introuvable"),
        UserProfileError("Profil utilisateur JSON invalide"),
        UserProfileError("Structure de profil invalide"),
    ],
)
def test_user_profile_error_is_a_controlled_service_error(profile_error):
    def unavailable_profile():
        raise profile_error

    app = create_app(
        service_factory=lambda: None,
        weather_provider=lambda lat, lon: object(),
        profile_provider=unavailable_profile,
    )

    response = TestClient(app).post("/v1/tonight", json={})

    assert response.status_code == 503
    assert response.json() == {
        "error": "user_profile_unavailable",
        "message": (
            "AstroPilot requires a valid user_profile.json. "
            "Check ASTROPILOT_DATA_DIR and the profile contents."
        ),
    }


def test_tonight_endpoint_delegates_inputs_and_returns_json_contract():
    weather = object()
    reference_time = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)
    weather_calls = []
    evaluation_calls = []
    persisted_profile = {
        "location": {
            "name": "Profile site",
            "latitude": 46.2,
            "longitude": 7.1,
        },
        "preferences": {"bortle": 6},
        "available_equipment": ["samyang_183"],
        "active_equipment": "samyang_183",
        "projects": {"M31": {"target_hours": 2}},
    }

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return make_result()

    app = create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: (
            weather_calls.append((lat, lon)) or weather
        ),
        profile_provider=lambda: persisted_profile,
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
            "equipment": "samyang_183",
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
                "preferences": {"bortle": 6},
                "available_equipment": ["samyang_183"],
                "active_equipment": "samyang_183",
                "projects": {"M31": {"target_hours": 2}},
                "location": {
                    "name": "La Chaux-de-Fonds",
                    "latitude": 47.1,
                    "longitude": 6.8,
                },
            },
            "weather": weather,
            "reference_time_utc": reference_time,
            "equipment": "samyang_183",
            "goal": "galaxies",
            "target": "deep_sky",
            "bortle": 4,
            "availability": None,
        }
    ]
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["night_date"] == "2026-09-01"
    assert payload["target"] == "Andromeda"
    assert payload["catalog_key"] == "M31"
    assert payload["target_common_name"] == "Galaxie d’Andromède"
    assert payload["recommended_hours"] == 3.5


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"mode": "all_night"},
            SessionAvailability(SessionAvailabilityMode.ALL_NIGHT),
        ),
        (
            {"mode": "duration", "duration": "PT2H"},
            SessionAvailability(
                SessionAvailabilityMode.DURATION,
                duration=timedelta(hours=2),
            ),
        ),
        (
            {
                "mode": "start_and_duration",
                "start": "2026-09-01T23:00:00+02:00",
                "duration": "PT90M",
            },
            SessionAvailability(
                SessionAvailabilityMode.START_AND_DURATION,
                start=datetime.fromisoformat("2026-09-01T23:00:00+02:00"),
                duration=timedelta(minutes=90),
            ),
        ),
        (
            {"mode": "until", "end": "2026-09-02T02:00:00+02:00"},
            SessionAvailability(
                SessionAvailabilityMode.UNTIL,
                end=datetime.fromisoformat("2026-09-02T02:00:00+02:00"),
            ),
        ),
        (
            {
                "mode": "fixed_window",
                "start": "2026-09-01T23:00:00+02:00",
                "end": "2026-09-02T02:00:00+02:00",
            },
            SessionAvailability(
                SessionAvailabilityMode.FIXED_WINDOW,
                start=datetime.fromisoformat("2026-09-01T23:00:00+02:00"),
                end=datetime.fromisoformat("2026-09-02T02:00:00+02:00"),
            ),
        ),
    ],
)
def test_tonight_maps_explicit_availability_to_domain(payload, expected):
    evaluation_calls = []

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return make_result()

    app = create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    )

    response = TestClient(app).post(
        "/v1/tonight",
        json={"availability": payload},
    )

    assert response.status_code == 200
    assert evaluation_calls[0]["availability"] == expected
    assert isinstance(evaluation_calls[0]["availability"], SessionAvailability)


def test_tonight_omitted_availability_remains_none_through_service_call():
    evaluation_calls = []

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return make_result()

    app = create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    )

    response = TestClient(app).post("/v1/tonight", json={})

    assert response.status_code == 200
    assert evaluation_calls[0]["availability"] is None


def test_gp04_api_exposes_only_physically_viable_actionable_alternatives(monkeypatch):
    reference = datetime(2026, 8, 29, 20, tzinfo=timezone.utc)
    weather = make_weather_snapshot(reference - timedelta(minutes=5))
    primary = make_result().recommendation.opportunity.candidate
    unavailable = replace(
        primary,
        name="Orion",
        catalog_key="M42",
        decision_score=76.0,
        final_score=77.0,
    )
    actionable = replace(
        primary,
        name="Triangulum",
        catalog_key="M33",
        decision_score=72.0,
        final_score=73.0,
    )
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=primary,
            shortlist_entries=(unavailable, actionable),
        ),
        confidence=0.91,
    )
    result = replace(make_result(), recommendation=recommendation)

    def physical_assessment(start, end):
        hours = (end - start).total_seconds() / 3600
        return CandidateAssessment(
            productive_window=ProductiveWindowAssessment(
                window_start=start,
                window_end=end,
                recommended_hours=hours,
                expected_gain=0.0,
                productivity=SimpleNamespace(
                    astronomical_hours=hours,
                    productive_hours=hours,
                    confidence=1.0,
                    windows=[SimpleNamespace(
                        start_hour=0.0,
                        end_hour=hours,
                        productivity=1.0,
                        productive=True,
                    )],
                    timeline=(SimpleNamespace(
                        start_hour=0.0,
                        end_hour=hours,
                        productivity_score=1.0,
                    ),),
                ),
            ),
            weather_decision=WeatherTrustDecision(
                evidence_quality=WeatherEvidenceQuality.SUFFICIENT,
                admissibility=WeatherDecisionAdmissibility.ADMISSIBLE,
                reasons=(),
            ),
        )

    assessments = {
        "M42": physical_assessment(
            datetime(2026, 9, 1, 20, tzinfo=timezone.utc),
            datetime(2026, 9, 1, 21, tzinfo=timezone.utc),
        ),
        "M33": physical_assessment(
            datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
            datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
        ),
    }
    monkeypatch.setattr(
        app_module,
        "_assess_shortlist_candidates",
        lambda *args, **kwargs: assessments,
    )

    class Service:
        def evaluate(self, **kwargs):
            return result

    client = TestClient(create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: weather,
        profile_provider=valid_profile,
        clock=lambda: reference,
    ))
    response = client.post(
        "/v1/tonight",
        json={
            "availability": {
                "mode": "fixed_window",
                "start": "2026-09-01T23:30:00+00:00",
                "end": "2026-09-02T00:30:00+00:00",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert CandidateViabilityEvaluator.is_viable(assessments["M42"]) is True
    assert CandidateViabilityEvaluator.is_viable(assessments["M33"]) is True
    assert [entry["catalog_key"] for entry in payload["alternatives"]] == ["M33"]
    physical_shortlist = {
        entry["catalog_key"]: entry for entry in payload["shortlist_entries"]
    }
    assert physical_shortlist["M42"]["target_decision_status"] == "viable"
    assert all(entry["catalog_key"] != "M42" for entry in payload["rejected_targets"])
    assert all(
        entry["catalog_key"] != "M42"
        for entry in payload["insufficient_evidence_targets"]
    )
    assert payload["target"] == "Andromeda"
    assert payload["catalog_key"] == "M31"


def test_tonight_availability_transport_does_not_invoke_windowing(monkeypatch):
    monkeypatch.setattr(
        availability_windowing,
        "select_duration_availability_window",
        lambda *args, **kwargs: pytest.fail("windowing must not be invoked"),
    )

    class Service:
        def evaluate(self, **kwargs):
            return make_result()

    app = create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    )

    response = TestClient(app).post(
        "/v1/tonight",
        json={"availability": {"mode": "all_night"}},
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "availability",
    [
        {"mode": "duration"},
        {"mode": "all_night", "duration": "PT1H"},
        {
            "mode": "start_and_duration",
            "start": "2026-09-01T23:00:00+02:00",
        },
        {"mode": "until", "end": "2026-09-02T02:00:00"},
        {
            "mode": "fixed_window",
            "start": "2026-09-02T02:00:00+02:00",
            "end": "2026-09-01T23:00:00+02:00",
        },
    ],
)
def test_tonight_rejects_invalid_availability_combinations(availability):
    app = create_app(
        service_factory=lambda: pytest.fail("service must not be called"),
        weather_provider=lambda lat, lon: pytest.fail("weather must not be called"),
        profile_provider=valid_profile,
    )

    response = TestClient(app).post(
        "/v1/tonight",
        json={"availability": availability},
    )

    assert response.status_code == 422


def test_tonight_uses_profile_bortle_without_request_override():
    evaluation_calls = []

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return make_result()

    app = create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=lambda: {
            **valid_profile(),
            "location": {
                "name": "Mont Sujet",
                "latitude": 47.12,
                "longitude": 7.04,
            },
            "preferences": {"bortle": 6},
        },
    )

    response = TestClient(app).post("/v1/tonight", json={})

    assert response.status_code == 200
    assert evaluation_calls[0]["bortle"] == 6


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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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


@pytest.mark.parametrize("explicit_rejection", [False, True])
def test_uncovered_mission_window_returns_refused_without_active_mission(explicit_rejection):
    reference = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
    weather = make_weather_snapshot(
        reference - timedelta(minutes=5),
        valid_until=datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
    )
    evaluation_calls = []
    rejection = CandidateRejection(
        target="Orion",
        catalog_key="M42",
        provenance=CandidateProvenance.DISCOVERY,
        basis=CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE,
        evaluation_score=0.0,
    )
    result = replace(
        make_result(),
        candidate_rejections=(rejection,) if explicit_rejection else (),
    )

    class Service:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return result

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: weather,
            profile_provider=valid_profile,
            clock=lambda: reference,
        )
    )

    response = client.post("/v1/tonight", json={})

    assert len(evaluation_calls) == 1
    assert response.status_code == 200
    payload = response.json()
    assert payload["rejected_targets"] == ([{
        "target": "Orion",
        "catalog_key": "M42",
        "provenance": "discovery",
        "basis": "non_positive_evaluation_score",
        "evaluation_score": 0.0,
        "target_decision_status": "not_recommended",
    }] if explicit_rejection else [])
    assert payload["target_decision_status"] == "insufficient_evidence"
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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
            profile_provider=valid_profile,
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


@pytest.mark.parametrize("equipment", ["fra400_2600", "not_a_setup"])
def test_invalid_tonight_equipment_is_a_stable_unprocessable_request(equipment):
    class Service:
        def evaluate(self, **kwargs):
            raise tonight_service_module.TonightEquipmentSelectionError(
                "invalid_tonight_equipment"
            )

    client = TestClient(
        create_app(
            service_factory=lambda: Service(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=lambda: {
                "location": {
                    "name": "Buttes",
                    "latitude": 46.7508,
                    "longitude": 6.5495,
                },
                "preferences": {"bortle": 3},
                "active_equipment": "samyang_183",
                "available_equipment": ["samyang_183"],
            },
        )
    )

    response = client.post("/v1/tonight", json={"equipment": equipment})

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "invalid_tonight_equipment",
            "message": "The requested equipment is unknown or unavailable.",
        }
    }


def test_explicit_location_requires_an_explicit_name():
    client = make_client(result=make_result())

    response = client.post(
        "/v1/tonight",
        json={"location": {"latitude": 47.1, "longitude": 6.8}},
    )

    assert response.status_code == 422


def test_unknown_profile_field_is_rejected():
    client = make_client(result=make_result())

    response = client.post(
        "/v1/tonight",
        json={"profile": {"projects": {}}},
    )

    assert response.status_code == 422


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
    request_properties = schemas["TonightRequest"]["properties"]
    assert "profile" not in request_properties
    assert "profile" not in request_example
    assert request_example["location"] == {
        "name": "Buttes",
        "latitude": 46.7508,
        "longitude": 6.5495,
    }
    assert request_example["goal"] == "balanced"
    assert request_example["target"] == "deep_sky"
    assert request_example["equipment"] == "samyang_183"

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


@pytest.mark.parametrize("count", [0, 1, 4])
@pytest.mark.parametrize("has_recommendation", [False, True])
def test_api_exposes_only_explicit_rejections_without_changing_existing_payload(count, has_recommendation):
    source = tuple(
        CandidateRejection(
            target="Orion",
            catalog_key=key,
            provenance=CandidateProvenance.DISCOVERY,
            basis=CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE,
            evaluation_score=score,
        )
        for key, score in [("Z", -2.5), ("A", 0.0), ("Z", -1.0), ("Z", -2.5)][:count]
    )
    original = make_result() if has_recommendation else TonightResult(
        None, None, None, status=TonightStatus.NO_CANDIDATE,
    )
    baseline = make_client(result=original).post("/v1/tonight", json={})
    result = replace(original, candidate_rejections=source)
    response = make_client(result=result).post("/v1/tonight", json={})

    assert baseline.status_code == response.status_code == 200
    baseline_payload = baseline.json()
    assert baseline_payload.pop("rejected_targets") == []
    payload = response.json()
    assert payload.pop("rejected_targets") == [
        {
            "target": rejection.target,
            "catalog_key": rejection.catalog_key,
            "provenance": "discovery",
            "basis": "non_positive_evaluation_score",
            "evaluation_score": rejection.evaluation_score,
            "target_decision_status": "not_recommended",
        }
        for rejection in source
    ]
    assert payload == baseline_payload
    assert result.recommendation is original.recommendation
    assert result.mission is original.mission


def test_openapi_exposes_dedicated_rejected_target_contract():
    schemas = make_client(result=make_result()).get("/openapi.json").json()["components"]["schemas"]
    response = schemas["TonightResponseModel"]
    field = response["properties"]["rejected_targets"]
    assert field["type"] == "array"
    assert "rejected_targets" not in response.get("required", [])
    entry = schemas[field["items"]["$ref"].split("/")[-1]]
    assert set(entry["properties"]) == {
        "target", "catalog_key", "provenance", "basis",
        "evaluation_score", "target_decision_status",
    }
    assert entry["properties"]["target_decision_status"]["const"] == "not_recommended"
    assert entry["properties"]["evaluation_score"]["type"] == "number"
    assert entry["properties"]["provenance"]["$ref"].endswith("CandidateProvenance")
    assert entry["properties"]["basis"]["$ref"].endswith("CandidateRejectionBasis")


@pytest.mark.parametrize("primary_refused", [False, True])
def test_target_insufficiency_api_binds_each_decision_to_its_own_candidate(monkeypatch, primary_refused):
    from types import SimpleNamespace
    from decision.mission.mission_assembler import ProductiveWindowAssessment
    from decision.services.candidate_assessment import CandidateAssessment
    from decision.weather.weather_trust_decision import (
        WeatherDecisionAdmissibility as Admissibility,
        WeatherEvidenceQuality as Quality,
        WeatherTrustDecision,
    )

    result = make_result()
    primary = result.recommendation.opportunity.candidate
    candidates = tuple(
        replace(primary, name=key, catalog_key=key)
        for key in ("M42", "M33", "M45", "M51", "M81")
    )
    result = replace(result, recommendation=replace(
        result.recommendation,
        opportunity=replace(result.recommendation.opportunity, shortlist_entries=candidates),
    ))
    decisions = (
        WeatherTrustDecision(Quality.INSUFFICIENT, Admissibility.REFUSED,
                             ("selected_window_uncovered", "candidate_reason", "candidate_reason")),
        WeatherTrustDecision(Quality.INSUFFICIENT, Admissibility.CAUTION,
                             ("provider_reliability_unavailable",)),
        WeatherTrustDecision(Quality.INVALID, Admissibility.REFUSED,
                             ("weather_location_mismatch",)),
        WeatherTrustDecision(Quality.SUFFICIENT, Admissibility.REFUSED, ()),
    )
    assessments = {
        candidate.catalog_key: CandidateAssessment(
            productive_window=ProductiveWindowAssessment(
                window_start=result.mission.window_start,
                window_end=result.mission.window_start + timedelta(hours=2),
                recommended_hours=1.0,
                expected_gain=0.0,
                productivity=SimpleNamespace(
                    astronomical_hours=2.0, productive_hours=1.0, confidence=0.5,
                    windows=[SimpleNamespace(
                        start_hour=0.0, end_hour=1.0, productivity=0.8, productive=True,
                    )],
                ),
            ),
            weather_decision=decision,
        )
        for candidate, decision in zip(candidates, decisions)
    }
    monkeypatch.setattr(app_module, "_assess_shortlist_candidates", lambda *a, **kw: assessments)
    reference = datetime(2026, 8, 29, 20, tzinfo=timezone.utc)
    weather = make_weather_snapshot(
        reference - timedelta(minutes=5),
        valid_until=datetime(2026, 9, 1, 23, tzinfo=timezone.utc) if primary_refused else None,
    )
    client = TestClient(create_app(
        service_factory=lambda: type("Service", (), {"evaluate": lambda self, **kw: result})(),
        weather_provider=lambda lat, lon: weather,
        profile_provider=valid_profile,
        clock=lambda: reference,
    ))
    response = client.post("/v1/tonight", json={})
    assert response.status_code == 200, response.json()
    payload = response.json()
    entries = payload["insufficient_evidence_targets"]
    assert [entry["catalog_key"] for entry in entries] == (
        ["M31", "M42"] if primary_refused else ["M42"]
    )
    assert entries[-1]["weather_decision"]["reasons"] == list(decisions[0].reasons)
    assert all(entry["target_decision_status"] == "insufficient_evidence" for entry in entries)
    if primary_refused:
        assert entries[0]["weather_decision"]["reasons"] == ["selected_window_uncovered"]
        assert payload["target_decision_status"] == "insufficient_evidence"
        assert payload["target"] is None
        assert payload["shortlist_entries"] == []
        assert payload["alternatives"] == []
    else:
        assert payload["target_decision_status"] == "recommended"
        assert payload["target"] == "Andromeda"
        assert [entry["catalog_key"] for entry in payload["alternatives"]] == ["M33"]
        assert [entry["target_decision_status"] for entry in payload["shortlist_entries"]] == [
            None, "viable", None, None, None,
        ]
        assert [entry["catalog_key"] for entry in payload["shortlist_entries"]] == [
            candidate.catalog_key for candidate in candidates
        ]
    assert payload["rejected_targets"] == []
    assert result.recommendation.opportunity.candidate is primary
    assert assessments["M42"].weather_decision is decisions[0]


def test_target_insufficiency_api_defaults_and_openapi_contract():
    result = TonightResult(None, None, None, status=TonightStatus.NO_RECOMMENDATION)
    client = make_client(result=result)
    payload = client.post("/v1/tonight", json={}).json()
    assert payload["insufficient_evidence_targets"] == []
    assert payload["target_decision_status"] is None
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    response = schemas["TonightResponseModel"]
    field = response["properties"]["insufficient_evidence_targets"]
    assert field["type"] == "array"
    assert "insufficient_evidence_targets" not in response.get("required", [])
    entry = schemas[field["items"]["$ref"].split("/")[-1]]
    assert set(entry["properties"]) == {
        "target", "catalog_key", "provenance", "weather_decision", "target_decision_status",
    }
    assert entry["properties"]["target_decision_status"]["const"] == "insufficient_evidence"
    weather = schemas[entry["properties"]["weather_decision"]["$ref"].split("/")[-1]]
    assert set(weather["properties"]) == {"evidence_quality", "admissibility", "reasons"}


def test_gp01_tonight_then_explicit_selection_creates_bound_mission():
    result = replace(make_result(decision_id="decision-123"), mission=None)

    class Service:
        def __init__(self):
            self.registered = []
            self.selections = []

        def evaluate(self, **kwargs):
            return result

        def register_decision_context(self, **kwargs):
            self.registered.append(kwargs)

        def accept(self, user_selection):
            self.selections.append(user_selection)
            return NightMission(
                target=user_selection.selected_catalog_key,
                confidence="HIGH",
                equipment=["widefield"],
                site_name="Mont Sujet",
                mission_id="mission-123",
                decision_id=user_selection.decision_id,
                selection_id=user_selection.selection_id,
            )

    service = Service()
    client = TestClient(create_app(
        service_factory=lambda: service,
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    ))

    tonight = client.post("/v1/tonight", json={})
    accepted = client.post(
        "/v1/decision-selections",
        json={
            "decision_id": "decision-123",
            "selection_id": "selection-123",
            "source": "primary_recommendation",
            "selected_catalog_key": "M31",
            "selected_at": "2026-09-10T20:00:00+00:00",
        },
    )

    assert tonight.status_code == 200
    assert tonight.json()["decision_id"] == "decision-123"
    assert result.mission is None
    assert len(service.registered) == 1
    assert accepted.status_code == 200
    assert accepted.json() == {
        "status": "accepted",
        "mission_id": "mission-123",
        "decision_id": "decision-123",
        "selection_id": "selection-123",
        "catalog_key": "M31",
    }
    assert service.selections[0].source is UserSelectionSource.PRIMARY_RECOMMENDATION


def test_gp11_selection_endpoint_rejects_unknown_decision_without_fallback():
    class Service:
        def accept(self, user_selection):
            from decision.services.decision_acceptance_application import (
                DecisionAcceptanceError,
            )

            raise DecisionAcceptanceError("decision_context_not_found")

    client = TestClient(create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    ))
    response = client.post(
        "/v1/decision-selections",
        json={
            "decision_id": "unknown-decision",
            "selection_id": "selection-123",
            "source": "primary_recommendation",
            "selected_catalog_key": "M31",
            "selected_at": "2026-09-10T20:00:00+00:00",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "decision_context_not_found"


def test_gp08_execution_transition_and_evidence_command_path():
    class Service:
        def __init__(self):
            self.execution = None
            self.evidence = None

        def create_execution(self, *, execution_id, mission_id):
            self.execution = Execution(
                execution_id,
                mission_id,
                ExecutionStatus.NOT_STARTED,
                None,
                None,
                None,
            )
            return self.execution

        def transition_execution(self, execution):
            self.execution = execution
            return execution

        def record_outcome_evidence(self, *, execution_id, evidence):
            self.evidence = evidence
            return evidence

    from decision.models.execution import Execution, ExecutionStatus

    service = Service()
    client = TestClient(create_app(
        service_factory=lambda: service,
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    ))
    created = client.post(
        "/v1/executions",
        json={"execution_id": "execution-1", "mission_id": "mission-1"},
    )
    transitioned = client.post(
        "/v1/execution-transitions",
        json={
            "execution_id": "execution-1",
            "mission_id": "mission-1",
            "status": "in_progress",
            "actual_start": "2026-09-10T22:00:00+00:00",
            "actual_end": None,
            "actual_duration": None,
        },
    )
    recorded = client.post(
        "/v1/outcome-evidence",
        json={
            "evidence_id": "evidence-1",
            "execution_id": "execution-1",
            "category": "acquisition",
            "observed_at": "2026-09-11T02:00:00+00:00",
            "source": "user",
            "actual_capture_duration": "PT2H",
            "usable_integration_duration": "PT90M",
        },
    )

    assert created.status_code == 200
    assert created.json()["status"] == "not_started"
    assert created.json()["actual_start"] is None
    assert transitioned.status_code == 200
    assert transitioned.json()["status"] == "in_progress"
    assert recorded.status_code == 200
    assert recorded.json()["evidence_id"] == "evidence-1"
    assert recorded.json()["category"] == "acquisition"
    assert service.execution.status is ExecutionStatus.IN_PROGRESS
    assert service.evidence.execution_id == "execution-1"


def test_execution_creation_payload_rejects_state_and_hidden_timing_shortcuts():
    client = TestClient(create_app(
        service_factory=lambda: object(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    ))

    response = client.post(
        "/v1/executions",
        json={
            "execution_id": "execution-1",
            "mission_id": "mission-1",
            "status": "in_progress",
            "actual_start": "2026-09-10T22:00:00+00:00",
        },
    )

    assert response.status_code == 422


def test_portfolio_credit_application_command_preserves_explicit_provenance():
    calls = []

    class Service:
        def apply_portfolio_credit(self, application, credit):
            calls.append((application, credit))
            from decision.models.portfolio_credit_application import (
                PortfolioCreditApplicationOutcome,
                PortfolioCreditApplicationResult,
            )

            return PortfolioCreditApplicationResult(
                application,
                PortfolioCreditApplicationOutcome.APPLIED,
            )

    client = TestClient(create_app(
        service_factory=lambda: Service(),
        weather_provider=lambda lat, lon: object(),
        profile_provider=valid_profile,
    ))
    response = client.post(
        "/v1/portfolio-credit-applications",
        json={
            "credit": {
                "credit_id": "credit-1",
                "execution_id": "execution-1",
                "evidence_ids": ["evidence-1"],
                "usable_integration_duration": "PT1H12M",
                "credited_at": "2026-09-10T23:12:00+00:00",
            },
            "application": {
                "application_id": "application-1",
                "credit_id": "credit-1",
                "object_name": "M31",
                "destination_kind": "project",
                "applied_duration": "PT1H12M",
                "applied_at": "2026-09-11T01:00:00+00:00",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "outcome": "applied",
        "application_id": "application-1",
        "credit_id": "credit-1",
        "object_name": "M31",
        "destination_kind": "project",
        "applied_duration": "PT1H12M",
        "applied_at": "2026-09-11T01:00:00Z",
    }
    recorded_application, recorded_credit = calls[0]
    assert recorded_credit.usable_integration_duration == timedelta(hours=1, minutes=12)
    assert recorded_application.applied_duration == timedelta(hours=1, minutes=12)


GP08_START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
GP08_END = datetime(2026, 9, 10, 23, 12, tzinfo=timezone.utc)


class GP08MissionStore:
    def __init__(self, mission):
        self.mission = mission

    def load_mission(self, mission_id):
        if mission_id == self.mission.mission_id:
            return self.mission
        return None


def gp08_mission():
    return NightMission(
        target="M31",
        confidence="HIGH",
        equipment=["widefield"],
        window_start=GP08_START,
        window_end=GP08_START + timedelta(hours=4),
        recommended_hours=4.0,
        site_name="Mont Sujet",
        mission_id="mission-gp08",
        decision_id="decision-gp08",
        selection_id="selection-gp08",
    )


def gp08_profile():
    return {
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
        "projects": {
            "M31": {
                "hours": 2.0,
                "target_hours": 20.0,
                "importance": 8,
            }
        },
        "sessions": [],
    }


def gp08_service(mission):
    return DurableTonightApplicationService(
        application_service=object(),
        evidence_store=object(),
        decision_id_factory=lambda: "unused",
        acceptance_service=GP08MissionStore(mission),
        profile_loader=user_profile.load_user_profile,
        profile_saver=user_profile.save_user_profile,
    )


def gp08_client(mission):
    return TestClient(
        create_app(
            service_factory=lambda: gp08_service(mission),
            weather_provider=lambda lat, lon: object(),
            profile_provider=valid_profile,
        )
    )


def gp08_credit_command(
    *,
    object_name="M31",
    credit_duration="PT1H12M",
    application_duration="PT1H12M",
    applied_at="2026-09-11T01:00:00+00:00",
):
    return {
        "credit": {
            "credit_id": "credit-gp08",
            "execution_id": "execution-gp08",
            "evidence_ids": ["evidence-gp08"],
            "usable_integration_duration": credit_duration,
            "credited_at": "2026-09-10T23:12:00+00:00",
        },
        "application": {
            "application_id": "application-gp08",
            "credit_id": "credit-gp08",
            "object_name": object_name,
            "destination_kind": "project",
            "applied_duration": application_duration,
            "applied_at": applied_at,
        },
    }


def create_gp08_execution(client):
    response = client.post(
        "/v1/executions",
        json={
            "execution_id": "execution-gp08",
            "mission_id": "mission-gp08",
        },
    )
    assert response.status_code == 200, response.json()
    return response


def transition_gp08_in_progress(client):
    response = client.post(
        "/v1/execution-transitions",
        json={
            "execution_id": "execution-gp08",
            "mission_id": "mission-gp08",
            "status": "in_progress",
            "actual_start": GP08_START.isoformat(),
            "actual_end": None,
            "actual_duration": None,
        },
    )
    assert response.status_code == 200, response.json()
    return response


def transition_gp08_interrupted(client):
    response = client.post(
        "/v1/execution-transitions",
        json={
            "execution_id": "execution-gp08",
            "mission_id": "mission-gp08",
            "status": "interrupted",
            "actual_start": GP08_START.isoformat(),
            "actual_end": GP08_END.isoformat(),
            "actual_duration": "PT1H12M",
        },
    )
    assert response.status_code == 200, response.json()
    return response


def record_gp08_evidence(client):
    response = client.post(
        "/v1/outcome-evidence",
        json={
            "evidence_id": "evidence-gp08",
            "execution_id": "execution-gp08",
            "category": "acquisition",
            "observed_at": "2026-09-10T23:20:00+00:00",
            "source": "user",
            "actual_capture_duration": "PT2H",
            "usable_integration_duration": "PT1H12M",
        },
    )
    assert response.status_code == 200, response.json()
    return response


def prepare_creditable_gp08(client):
    created = create_gp08_execution(client)
    in_progress = transition_gp08_in_progress(client)
    interrupted = transition_gp08_interrupted(client)
    evidence = record_gp08_evidence(client)
    return created, in_progress, interrupted, evidence


def test_gp08_planned_four_hours_interrupted_and_credits_only_one_hour_twelve(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    user_profile.save_user_profile(gp08_profile())

    def forbidden_record_session(*args, **kwargs):
        pytest.fail("GP-08 must not call legacy record_session")

    monkeypatch.setattr(user_profile, "record_session", forbidden_record_session)
    mission = gp08_mission()
    client = gp08_client(mission)
    created, in_progress, interrupted, evidence = prepare_creditable_gp08(client)

    applied = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(),
    )
    persisted_after_apply = user_profile.load_user_profile()

    reconstructed_client = gp08_client(mission)
    replay = reconstructed_client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(),
    )
    persisted_after_replay = user_profile.load_user_profile()

    assert mission.recommended_hours == 4.0
    assert mission.window_end - mission.window_start == timedelta(hours=4)
    assert (mission.mission_id, mission.decision_id, mission.selection_id) == (
        "mission-gp08",
        "decision-gp08",
        "selection-gp08",
    )
    assert created.json()["status"] == "not_started"
    assert in_progress.json()["status"] == "in_progress"
    assert interrupted.json()["status"] == "interrupted"
    assert interrupted.json()["actual_duration"] == "PT1H12M"
    assert evidence.json()["usable_integration_duration"] == "PT1H12M"
    assert applied.status_code == 200, applied.json()
    assert applied.json()["outcome"] == "applied"
    assert persisted_after_apply["projects"]["M31"]["hours"] == 3.2
    assert persisted_after_apply["projects"]["M31"]["hours"] != 6.0
    assert persisted_after_apply["projects"]["M31"]["hours"] != 4.0
    assert persisted_after_apply["sessions"] == []
    assert replay.status_code == 200, replay.json()
    assert replay.json()["outcome"] == "already_applied"
    assert persisted_after_replay == persisted_after_apply


def test_portfolio_credit_api_unknown_execution_and_evidence_fail_closed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    user_profile.save_user_profile(gp08_profile())
    client = gp08_client(gp08_mission())

    missing_execution = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(),
    )
    create_gp08_execution(client)
    transition_gp08_in_progress(client)
    transition_gp08_interrupted(client)
    missing_evidence = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(),
    )

    assert missing_execution.status_code == 404
    assert missing_execution.json()["detail"]["code"] == "execution_not_found"
    assert missing_evidence.status_code == 404
    assert missing_evidence.json()["detail"]["code"] == "evidence_not_found"
    assert user_profile.load_user_profile()["projects"]["M31"]["hours"] == 2.0


def test_portfolio_credit_api_ineligible_execution_fails_closed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    user_profile.save_user_profile(gp08_profile())
    client = gp08_client(gp08_mission())
    create_gp08_execution(client)
    record_gp08_evidence(client)

    response = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "execution_status_ineligible"
    assert user_profile.load_user_profile()["projects"]["M31"]["hours"] == 2.0


def test_portfolio_credit_api_rejects_evidenced_duration_mismatch(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    user_profile.save_user_profile(gp08_profile())
    client = gp08_client(gp08_mission())
    prepare_creditable_gp08(client)

    response = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(
            credit_duration="PT1H",
            application_duration="PT1H",
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "usable_integration_total_mismatch"
    assert user_profile.load_user_profile()["projects"]["M31"]["hours"] == 2.0


def test_portfolio_credit_api_unresolved_project_fails_closed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    user_profile.save_user_profile(gp08_profile())
    client = gp08_client(gp08_mission())
    prepare_creditable_gp08(client)

    response = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(object_name="NGC7000"),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_destination_unresolved"
    assert set(user_profile.load_user_profile()["projects"]) == {"M31"}


def test_portfolio_credit_api_rejects_timezone_naive_applied_at():
    client = TestClient(
        create_app(
            service_factory=lambda: object(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=valid_profile,
        )
    )

    response = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(applied_at="2026-09-11T01:00:00"),
    )

    assert response.status_code == 422


def test_portfolio_credit_api_persistence_failure_is_not_success():
    class FailingService:
        def apply_portfolio_credit(self, application, credit):
            raise OSError("replace failed")

    client = TestClient(
        create_app(
            service_factory=lambda: FailingService(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=valid_profile,
        )
    )

    response = client.post(
        "/v1/portfolio-credit-applications",
        json=gp08_credit_command(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "portfolio_credit_persistence_unavailable"
    )
