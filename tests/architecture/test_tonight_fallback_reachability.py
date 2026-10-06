"""Exercise production ingress/services, preserving the boundary under audit."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest
from fastapi.testclient import TestClient
from astral import Observer

import astro_score
from astropilot.app import create_app
from astropilot.engines.sky_engine import SkyEngine
from decision.forecast.forecast_run import ForecastRun
from decision.services.tonight_application_service import TonightApplicationService
from decision.validation.decision_consistency import DecisionConsistencyError
from decision.weather.weather_ingress import REQUIRED_HOURLY_UNITS
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.night_productivity.night_productivity_result import NightProductivityResult
from decision.night_productivity.night_window import NightWindow
from decision.services.session_availability_windowing import evaluate_continuous_actionable_productive_window


def profile():
    return {
        "location": {"name": "Buttes", "latitude": 46.7508, "longitude": 6.5495},
        "preferences": {"bortle": 4},
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
        "projects": {"M31": {"hours": 9.0, "target_hours": 10.0, "importance": 5}},
    }


def payload():
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    values = {
        "cloud_cover": 20, "cloud_cover_low": 10, "cloud_cover_mid": 5,
        "cloud_cover_high": 5, "precipitation": 0, "relative_humidity_2m": 60,
        "visibility": 24000, "wind_speed_10m": 5, "temperature_2m": 8,
    }
    return {
        "latitude": 46.7508, "longitude": 6.5495, "timezone": "Europe/Zurich",
        "utc_offset_seconds": 7200,
        "hourly_units": {"time": "unixtime", **REQUIRED_HOURLY_UNITS},
        "hourly": {
            "time": [int((start + timedelta(hours=i)).timestamp()) for i in range(48)],
            **{key: [value] * 48 for key, value in values.items()},
        },
    }


@pytest.mark.parametrize("field", list(REQUIRED_HOURLY_UNITS))
@pytest.mark.parametrize("mutation", ["missing", "short", "null"])
def test_http_production_weather_ingress_blocks_incomplete_provider_arrays(monkeypatch, field, mutation):
    data = payload()
    if mutation == "missing":
        data["hourly"].pop(field)
    elif mutation == "short":
        data["hourly"][field].pop()
    else:
        data["hourly"][field][0] = None
    monkeypatch.setattr(astro_score.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: data,
    ))
    def forbidden_service():
        pytest.fail("invalid evidence reached Tonight evaluation")
    response = TestClient(create_app(
        profile_provider=profile, service_factory=forbidden_service,
    )).post("/v1/tonight", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "weather_invalid"
    assert "expected_gain" not in response.json()


def test_real_tonight_service_unknown_future_does_not_award_opportunity_bonus(monkeypatch):
    # The real future engine receives no observation_time from candidate building.
    # SeasonResolver therefore returns unknown before any weather request.
    captured = {}
    original = astro_score.portfolio_candidate_bonus
    def observe(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(astro_score, "portfolio_candidate_bonus", observe)
    class NoRecommendation:
        def build(self, *, candidates):
            assert len(candidates) == 1
            captured["candidate"] = candidates[0]
            return None
    service = TonightApplicationService(
        forecast_nights=lambda *args, **kwargs: ForecastRun(nights=({
            "date": "2026-10-06", "duration": 2,
            "top_objects": [{"name": "M31", "catalog_key": "M31", "global_score": 80}],
        },), evidence=None),
        build_candidates=astro_score.recommend_project_for_night,
        opportunity_recommendation_service=NoRecommendation(),
        tonight_mission_service=astro_score.tonight_mission_service,
        build_mission_input=astro_score.build_mission_input,
    )
    monkeypatch.setattr(astro_score.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=payload,
    ))
    response = TestClient(create_app(
        profile_provider=profile, service_factory=lambda: service,
    )).post("/v1/tonight", json={"availability": {"mode": "all_night"}})
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "no_recommendation"
    assert captured["opportunity_bonus"] == 0


def test_forecast_service_preserves_lunar_hours_excluded_from_target_scoring(monkeypatch):
    # Substitute only astrometry; preserve scoring, window selection, context,
    # evaluation transport and selected-window weather construction.
    start = datetime(2026, 10, 6, 22, tzinfo=timezone.utc)
    rows = [{
        "time": start + timedelta(hours=i), "cloud_cover": 20,
        "cloud_cover_low": 10, "cloud_cover_mid": 5, "cloud_cover_high": 5,
        "relative_humidity_2m": 60, "wind_speed_10m": 5,
        "temperature_2m": 8, "precipitation": 0, "visibility": 24000,
    } for i in range(2)]
    monkeypatch.setattr(SkyEngine, "hour_geometry", lambda self, hour, *args: {
        "target_altitude": 20 if hour["time"] == start else 60,
        "moon_elevation": 60 if hour["time"] == start else -20,
        "moon_target_sep": 1 if hour["time"] == start else 120,
    })
    evaluation = astro_score.evaluate_object(
            obj_name="M31", sky=SkyEngine(), hours=rows, illumination=50,
            city_info=SimpleNamespace(name="Buttes", observer=Observer(46.7508, 6.5495)),
            lat=46.7508, lon=6.5495, bortle=4, target="deep_sky",
            profile=profile(),
    )
    assert len(evaluation["window"]["details"]) == 1
    assert [detail["time"] for detail in evaluation["window"]["hourly_lunar_evidence"]] == [row["time"] for row in rows]
    assert len(evaluation["selected_window_weather"].hourly_moon_penalty) == 2
    assert evaluation["selected_window_weather"].hourly_moon_penalty == [17.5, 0]


@pytest.mark.parametrize("importance", [0, 1, 2, 5, 10])
@pytest.mark.parametrize("astro_score_value", [20, 40, 60, 80, 100])
@pytest.mark.parametrize("acquired_hours", [0, 5, 9])
def test_removing_user_importance_cannot_increase_real_candidate_score(importance, astro_score_value, acquired_hours):
    known = profile()
    known["projects"]["M31"]["importance"] = importance
    unknown = profile()
    unknown["projects"]["M31"].pop("importance")
    for snapshot in (known, unknown):
        snapshot["projects"]["M31"]["hours"] = acquired_hours
    objects = [{"name": "M31", "catalog_key": "M31", "global_score": astro_score_value}]
    known_candidate = astro_score.recommend_project_for_night(objects, available_hours=2, profile=known)[0]
    unknown_candidate = astro_score.recommend_project_for_night(objects, available_hours=2, profile=unknown)[0]
    assert unknown_candidate.priority is None
    assert unknown_candidate.final_score <= known_candidate.final_score
    assert unknown_candidate.decision_score <= known_candidate.decision_score


@pytest.mark.parametrize("details", [[], [{"moon": 3}]])
def test_new_selected_weather_refuses_missing_or_short_lunar_evidence(details):
    start = datetime(2026, 10, 6, 22, tzinfo=timezone.utc)
    with pytest.raises(DecisionConsistencyError, match="selected_window_lunar_series_unaligned"):
        astro_score.build_selected_window_weather(
            hours=[{"time": start}, {"time": start + timedelta(hours=1)}],
            best={"start": start, "end": start + timedelta(hours=2), "details": details},
            sky=SkyEngine(),
        )


@pytest.mark.parametrize("field", ["hours", "target_hours"])
def test_http_production_profile_loader_rejects_unknown_legacy_progress(monkeypatch, tmp_path, field):
    data = profile()
    data["projects"]["M31"].pop(field)
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    path = tmp_path / "user_profile.json"
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    monkeypatch.setattr(astro_score, "fetch_weather", lambda *args: pytest.fail("invalid progress reached weather"))
    response = TestClient(create_app()).post("/v1/tonight", json={})
    assert response.status_code == 503
    assert response.json()["error"] == "user_profile_unavailable"
    assert path.read_bytes() == before


def test_characterize_missing_availability_is_unconstrained_not_user_evidence():
    start = datetime(2026, 10, 6, 22, tzinfo=timezone.utc)
    assessment = ProductiveWindowAssessment(
        window_start=start, window_end=start + timedelta(hours=2),
        recommended_hours=2, expected_gain=20,
        productivity=NightProductivityResult(
            astronomical_hours=2, productive_hours=2, confidence=1,
            cloud_loss=0, moon_loss=0, altitude_loss=0, weather_loss=0,
            windows=[NightWindow(start_hour=0, end_hour=2, productivity=1,
                altitude=60, cloud_cover=0, moon_penalty=0, seeing=1.5,
                productive=True, reason="stable_conditions")],
        ),
    )
    absent = evaluate_continuous_actionable_productive_window(assessment, None)
    unavailable = evaluate_continuous_actionable_productive_window(assessment,
        SessionAvailability(mode=SessionAvailabilityMode.UNTIL, end=start))
    assert absent.window is not None
    assert unavailable.window is None
    # Characterization of an open product-policy finding, not a safety invariant.


@pytest.mark.parametrize("moon", [None, True, float("nan"), -1, 36])
def test_invalid_new_lunar_evidence_is_rejected(moon):
    start = datetime(2026, 10, 6, 22, tzinfo=timezone.utc)
    with pytest.raises(DecisionConsistencyError, match="selected_window_lunar_series_invalid"):
        astro_score.build_selected_window_weather(
            hours=[{"time": start}],
            best={"start": start, "end": start + timedelta(hours=1),
                "hourly_lunar_evidence": [{"time": start, "moon": moon}]},
            sky=SkyEngine(),
        )


def test_same_length_lunar_array_with_wrong_timestamp_is_rejected():
    start = datetime(2026, 10, 6, 22, tzinfo=timezone.utc)
    with pytest.raises(DecisionConsistencyError, match="selected_window_lunar_series_unaligned"):
        astro_score.build_selected_window_weather(
            hours=[{"time": start}],
            best={"start": start, "end": start + timedelta(hours=1),
                "hourly_lunar_evidence": [{"time": start + timedelta(hours=1), "moon": 0}]},
            sky=SkyEngine(),
        )
