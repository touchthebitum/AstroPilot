from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from decision.weather.decision_forecast_evidence import (
    DecisionForecastEvidence,
    build_decision_forecast_evidence,
)
from decision.weather.provider_reliability import WeatherVariable
from decision.weather.weather_ingress import WeatherSnapshot


RETRIEVED = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)


def snapshot() -> WeatherSnapshot:
    return WeatherSnapshot(
        payload={"hourly_units": {}},
        provider="Open-Meteo",
        retrieved_at_utc=RETRIEVED,
        requested_latitude=46.7508,
        requested_longitude=6.5495,
        grid_latitude=46.75,
        grid_longitude=6.55,
        grid_distance_km=0.1,
        elevation_m=1_245.0,
        timezone="Europe/Zurich",
        timezone_source="coordinates_local",
        utc_offset_seconds=7200,
        valid_from=RETRIEVED,
        valid_until=RETRIEVED + timedelta(hours=24),
        hour_count=25,
        completeness=1.0,
    )


def row(valid_at, *, temperature, humidity, wind, cloud, **extra):
    return {
        "time": valid_at,
        "temperature_2m": temperature,
        "relative_humidity_2m": humidity,
        "wind_speed_10m": wind,
        "cloud_cover": cloud,
        **extra,
    }


def test_builds_four_exact_points_per_admissible_row_in_deterministic_order():
    zurich = ZoneInfo("Europe/Zurich")
    later = (RETRIEVED + timedelta(hours=2)).astimezone(zurich)
    earlier = (RETRIEVED + timedelta(hours=1)).astimezone(zurich)
    rows = [
        row(later, temperature=7.5, humidity=81.0, wind=14.0, cloud=72.5),
        row(
            earlier,
            temperature=8.25,
            humidity=79.5,
            wind=12.5,
            cloud=17.25,
        ),
    ]

    evidence = build_decision_forecast_evidence(snapshot(), rows)

    assert isinstance(evidence, DecisionForecastEvidence)
    assert len(evidence.forecast_points) == 8
    assert [
        (point.forecast_for_utc, point.values[0].variable)
        for point in evidence.forecast_points
    ] == [
        (earlier.astimezone(timezone.utc), WeatherVariable.TEMPERATURE_C),
        (
            earlier.astimezone(timezone.utc),
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
        ),
        (earlier.astimezone(timezone.utc), WeatherVariable.WIND_SPEED_KMH),
        (
            earlier.astimezone(timezone.utc),
            WeatherVariable.CLOUD_COVER_PERCENT,
        ),
        (later.astimezone(timezone.utc), WeatherVariable.TEMPERATURE_C),
        (
            later.astimezone(timezone.utc),
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
        ),
        (later.astimezone(timezone.utc), WeatherVariable.WIND_SPEED_KMH),
        (
            later.astimezone(timezone.utc),
            WeatherVariable.CLOUD_COVER_PERCENT,
        ),
    ]
    assert [point.values[0].value for point in evidence.forecast_points] == [
        8.25,
        79.5,
        12.5,
        17.25,
        7.5,
        81.0,
        14.0,
        72.5,
    ]
    assert [point.values[0].unit for point in evidence.forecast_points] == [
        "°C",
        "%",
        "km/h",
        "%",
        "°C",
        "%",
        "km/h",
        "%",
    ]


def test_preserves_snapshot_provenance_without_inventing_model_or_site_altitude():
    source = snapshot()
    valid_at = RETRIEVED + timedelta(hours=3)

    evidence = build_decision_forecast_evidence(
        source,
        [
            row(
                valid_at,
                temperature=6.0,
                humidity=85.0,
                wind=9.0,
                cloud=41.5,
            )
        ],
    )

    for point in evidence.forecast_points:
        assert point.provider_id == source.provider
        assert point.model_id is None
        assert point.retrieved_at_utc == source.retrieved_at_utc
        assert point.forecast_for_utc == valid_at
        assert point.horizon == timedelta(hours=3)
        assert point.requested_location.latitude == source.requested_latitude
        assert point.requested_location.longitude == source.requested_longitude
        assert point.requested_location.altitude_m is None
        assert point.grid_location.latitude == source.grid_latitude
        assert point.grid_location.longitude == source.grid_longitude
        assert point.grid_location.altitude_m == source.elevation_m


def test_excludes_past_row_and_includes_row_exactly_at_retrieval_time():
    rows = [
        row(
            RETRIEVED - timedelta(microseconds=1),
            temperature=4.0,
            humidity=90.0,
            wind=5.0,
            cloud=90.0,
        ),
        row(
            RETRIEVED,
            temperature=5.0,
            humidity=89.0,
            wind=6.0,
            cloud=65.0,
        ),
    ]

    evidence = build_decision_forecast_evidence(snapshot(), rows)

    assert len(evidence.forecast_points) == 4
    assert all(
        point.forecast_for_utc == RETRIEVED
        for point in evidence.forecast_points
    )


def test_emits_only_temperature_humidity_mean_wind_and_cloud_cover():
    evidence = build_decision_forecast_evidence(
        snapshot(),
        [
            row(
                RETRIEVED,
                temperature=5.0,
                humidity=89.0,
                wind=6.0,
                cloud=70.0,
                precipitation=2.0,
                dew_point_2m=3.0,
                wind_gusts_10m=18.0,
                visibility=10_000.0,
                cloud_cover_low=20.0,
                cloud_cover_mid=30.0,
                cloud_cover_high=40.0,
            )
        ],
    )

    assert {
        point.values[0].variable for point in evidence.forecast_points
    } == {
        WeatherVariable.TEMPERATURE_C,
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
        WeatherVariable.WIND_SPEED_KMH,
        WeatherVariable.CLOUD_COVER_PERCENT,
    }


def test_container_and_points_are_immutable_and_inputs_are_not_mutated():
    source = snapshot()
    rows = [
        row(
            RETRIEVED,
            temperature=5.0,
            humidity=89.0,
            wind=6.0,
            cloud=70.0,
        ),
    ]
    source_before = deepcopy(source)
    rows_before = deepcopy(rows)

    evidence = build_decision_forecast_evidence(source, rows)

    assert source == source_before
    assert rows == rows_before
    with pytest.raises(FrozenInstanceError):
        evidence.forecast_points = ()
    with pytest.raises(FrozenInstanceError):
        evidence.forecast_points[0].provider_id = "changed"
