from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.weather_ingress import (
    REQUIRED_HOURLY_UNITS,
    WeatherIngressError,
    WeatherInsufficientError,
    validate_weather_payload,
)


def valid_payload(hours=48):
    start = datetime(2026, 8, 29)
    return {
        "latitude": 46.75,
        "longitude": 6.55,
        "elevation": 837.0,
        "timezone": "Europe/Zurich",
        "utc_offset_seconds": 7200,
        "hourly_units": {"time": "iso8601", **REQUIRED_HOURLY_UNITS},
        "hourly": {
            "time": [
                (start + timedelta(hours=index)).isoformat(timespec="minutes")
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


def validate(payload):
    return validate_weather_payload(
        payload,
        requested_latitude=46.7508,
        requested_longitude=6.5495,
        requested_timezone="Europe/Zurich",
        retrieved_at_utc=datetime(2026, 8, 29, 18, 5, tzinfo=timezone.utc),
    )


def test_valid_payload_becomes_an_immutable_snapshot_with_auditable_metadata():
    snapshot = validate(valid_payload())

    assert snapshot.provider == "Open-Meteo"
    assert snapshot.hour_count == 48
    assert snapshot.completeness == 1.0
    assert snapshot.valid_from.isoformat() == "2026-08-29T00:00:00+02:00"
    assert snapshot.valid_until.isoformat() == "2026-08-30T23:00:00+02:00"
    assert snapshot.trust_transport()["validation_status"] == "validated"


@pytest.mark.parametrize(
    ("mutate", "issue"),
    [
        (lambda data: data.update(error=True), "provider_error_response"),
        (lambda data: data.pop("hourly_units"), "missing_hourly_units"),
        (
            lambda data: data["hourly_units"].update(wind_speed_10m="m/s"),
            "invalid_unit_wind_speed_10m",
        ),
        (
            lambda data: data["hourly"]["cloud_cover"].pop(),
            "misaligned_series_cloud_cover",
        ),
        (
            lambda data: data["hourly"]["relative_humidity_2m"].__setitem__(0, 120),
            "out_of_range_relative_humidity_2m",
        ),
        (
            lambda data: data["hourly"]["temperature_2m"].__setitem__(0, float("nan")),
            "invalid_value_temperature_2m",
        ),
        (
            lambda data: data["hourly"]["time"].__setitem__(1, "2026-08-29T00:30"),
            "non_hourly_time_cadence",
        ),
        (lambda data: data.update(timezone="UTC"), "unexpected_timezone"),
        (lambda data: data.update(latitude=10.0), "weather_grid_too_far"),
    ],
)
def test_corrupt_provider_payloads_are_rejected(mutate, issue):
    payload = deepcopy(valid_payload())
    mutate(payload)

    with pytest.raises(WeatherIngressError) as caught:
        validate(payload)

    assert issue in caught.value.issues


def test_less_than_one_day_of_weather_is_distinctly_insufficient():
    with pytest.raises(WeatherInsufficientError) as caught:
        validate(valid_payload(hours=23))

    assert caught.value.code == "weather_insufficient"


def test_corruption_takes_precedence_over_short_coverage():
    payload = valid_payload(hours=23)
    payload["hourly_units"]["temperature_2m"] = "°F"

    with pytest.raises(WeatherIngressError) as caught:
        validate(payload)

    assert not isinstance(caught.value, WeatherInsufficientError)
    assert "invalid_unit_temperature_2m" in caught.value.issues


def test_retrieval_timestamp_must_be_timezone_aware():
    with pytest.raises(WeatherIngressError) as caught:
        validate_weather_payload(
            valid_payload(),
            requested_latitude=46.7508,
            requested_longitude=6.5495,
            requested_timezone="Europe/Zurich",
            retrieved_at_utc=datetime(2026, 8, 29, 18, 5),
        )

    assert caught.value.issues == ("retrieval_time_without_timezone",)
