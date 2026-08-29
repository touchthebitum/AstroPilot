from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from decision.weather.weather_ingress import (
    FUTURE_RETRIEVAL_TOLERANCE,
    MAXIMUM_SNAPSHOT_AGE,
    REQUIRED_HOURLY_UNITS,
    WeatherIngressError,
    WeatherInsufficientError,
    WeatherStaleError,
    validate_weather_payload,
    validate_weather_freshness,
)


def valid_payload(hours=48):
    start = datetime(2026, 8, 29, tzinfo=ZoneInfo("Europe/Zurich"))
    return {
        "latitude": 46.75,
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
    assert snapshot.timezone_source == "coordinates_local"
    assert snapshot.valid_from.isoformat() == "2026-08-29T00:00:00+02:00"
    assert snapshot.valid_until.isoformat() == "2026-08-30T23:00:00+02:00"
    assert snapshot.trust_transport()["validation_status"] == "validated"


@pytest.mark.parametrize(
    ("mutate", "issue"),
    [
        (lambda data: data.update(error=True), "provider_error_response"),
        (lambda data: data.pop("hourly_units"), "missing_hourly_units"),
        (
            lambda data: data["hourly_units"].update(time="iso8601"),
            "invalid_unit_time",
        ),
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
            lambda data: data["hourly"]["time"].__setitem__(1, data["hourly"]["time"][0] + 1800),
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


@pytest.mark.parametrize(
    ("age", "expected_minutes"),
    [
        (timedelta(minutes=12, seconds=30), 12.5),
        (MAXIMUM_SNAPSHOT_AGE, 90.0),
    ],
)
def test_fresh_snapshot_and_exact_age_limit_are_accepted(age, expected_minutes):
    snapshot = validate(valid_payload())

    freshness = validate_weather_freshness(
        snapshot,
        reference_time_utc=snapshot.retrieved_at_utc + age,
    )

    assert freshness.snapshot_age_minutes == expected_minutes
    assert freshness.freshness_status == "fresh"
    assert freshness.maximum_age_minutes == 90


def test_snapshot_beyond_age_limit_is_distinctly_stale():
    snapshot = validate(valid_payload())

    with pytest.raises(WeatherStaleError) as caught:
        validate_weather_freshness(
            snapshot,
            reference_time_utc=(
                snapshot.retrieved_at_utc
                + MAXIMUM_SNAPSHOT_AGE
                + timedelta(microseconds=1)
            ),
        )

    assert caught.value.code == "weather_stale"
    assert caught.value.issues == ("retrieval_time_too_old",)


def test_future_timestamp_at_tolerance_is_accepted_with_zero_display_age():
    snapshot = validate(valid_payload())

    freshness = validate_weather_freshness(
        snapshot,
        reference_time_utc=(
            snapshot.retrieved_at_utc - FUTURE_RETRIEVAL_TOLERANCE
        ),
    )

    assert freshness.snapshot_age_minutes == 0.0


def test_excessively_future_timestamp_is_invalid():
    snapshot = validate(valid_payload())

    with pytest.raises(WeatherIngressError) as caught:
        validate_weather_freshness(
            snapshot,
            reference_time_utc=(
                snapshot.retrieved_at_utc
                - FUTURE_RETRIEVAL_TOLERANCE
                - timedelta(microseconds=1)
            ),
        )

    assert not isinstance(caught.value, WeatherStaleError)
    assert caught.value.code == "weather_invalid"
    assert caught.value.issues == ("retrieval_time_in_future",)


def test_injected_reference_time_makes_freshness_deterministic():
    snapshot = validate(valid_payload())
    reference = snapshot.retrieved_at_utc + timedelta(minutes=37)

    first = validate_weather_freshness(snapshot, reference_time_utc=reference)
    second = validate_weather_freshness(snapshot, reference_time_utc=reference)

    assert first == second


def test_unix_weather_hours_cross_spring_dst_as_distinct_utc_instants():
    payload = valid_payload()
    start_utc = datetime(2026, 3, 29, tzinfo=timezone.utc)
    payload["hourly"]["time"] = [
        int((start_utc + timedelta(hours=index)).timestamp())
        for index in range(48)
    ]

    snapshot = validate(payload)

    assert snapshot.valid_from.isoformat() == "2026-03-29T01:00:00+01:00"
    assert snapshot.payload["hourly"]["time"][1] - snapshot.payload["hourly"]["time"][0] == 3600
    second = datetime.fromtimestamp(
        snapshot.payload["hourly"]["time"][1], timezone.utc
    ).astimezone(ZoneInfo(snapshot.timezone))
    assert second.isoformat() == "2026-03-29T03:00:00+02:00"
