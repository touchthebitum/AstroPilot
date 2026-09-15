from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

import astro_score
from astropilot.app import create_app
from decision.validation.decision_consistency import (
    DecisionConsistencyError,
    DecisionConsistencyGate,
)
from decision.weather.weather_ingress import (
    REQUIRED_HOURLY_UNITS,
    validate_weather_payload,
)


def _weather_snapshot(*, reference_time: datetime):
    start = datetime(2026, 8, 29, tzinfo=ZoneInfo("Europe/Zurich"))
    hours = 24 * 7
    payload = {
        "latitude": 46.888,
        "longitude": 6.55,
        "elevation": 837.0,
        "timezone": "Europe/Zurich",
        "utc_offset_seconds": 7200,
        "hourly_units": {"time": "unixtime", **REQUIRED_HOURLY_UNITS},
        "hourly": {
            "time": [
                int((start + timedelta(hours=index)).timestamp())
                for index in range(hours)
            ],
            "cloud_cover": [20.0] * hours,
            "cloud_cover_low": [10.0] * hours,
            "cloud_cover_mid": [5.0] * hours,
            "cloud_cover_high": [5.0] * hours,
            "precipitation": [0.0] * hours,
            "relative_humidity_2m": [65.0] * hours,
            "visibility": [24000.0] * hours,
            "wind_speed_10m": [8.0] * hours,
            "temperature_2m": [12.0] * hours,
        },
    }
    return validate_weather_payload(
        payload,
        requested_latitude=46.888,
        requested_longitude=6.55,
        requested_timezone="Europe/Zurich",
        retrieved_at_utc=reference_time - timedelta(minutes=5),
    )


def test_clean_profile_all_night_discovery_produces_consistent_decision(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    reference_time = datetime(2026, 8, 29, 18, tzinfo=timezone.utc)
    weather = _weather_snapshot(reference_time=reference_time)
    profile = {
        "location": {
            "name": "Buttes",
            "latitude": 46.888,
            "longitude": 6.55,
            "timezone": "Europe/Zurich",
        },
        "preferences": {"bortle": 4},
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
        "projects": {},
        "sessions": [],
    }
    consistency_issues = []
    validate_mission = DecisionConsistencyGate.validate_mission
    build_decision_context = astro_score.build_decision_context

    def capture_consistency_issues(mission):
        try:
            validate_mission(mission)
        except DecisionConsistencyError as exc:
            consistency_issues.extend(exc.issues)
            raise

    def capture_decision_context_issues(**kwargs):
        try:
            return build_decision_context(**kwargs)
        except DecisionConsistencyError as exc:
            consistency_issues.extend(exc.issues)
            raise

    monkeypatch.setattr(
        DecisionConsistencyGate,
        "validate_mission",
        staticmethod(capture_consistency_issues),
    )
    monkeypatch.setattr(
        astro_score,
        "build_decision_context",
        capture_decision_context_issues,
    )
    client = TestClient(
        create_app(
            service_factory=astro_score.build_durable_tonight_application_service,
            weather_provider=lambda latitude, longitude: weather,
            profile_provider=lambda: profile,
            clock=lambda: reference_time,
        )
    )

    response = client.post(
        "/v1/tonight",
        json={"availability": {"mode": "all_night"}},
    )

    assert response.status_code == 200, (
        response.json(),
        tuple(consistency_issues),
    )
    assert response.json()["status"] == "available"
    assert response.json()["decision_id"]
    assert consistency_issues == []
