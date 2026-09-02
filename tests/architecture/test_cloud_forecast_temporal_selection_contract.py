from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.cloud_forecast_temporal_selection import (
    select_cloud_forecast_point,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.forecast_temporal_selection import (
    ForecastTemporalSelectionError,
)
from decision.weather.provider_reliability import (
    CANONICAL_UNITS,
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)
RETRIEVED_AT = OBSERVED_AT - timedelta(hours=2)
LOCATION = WeatherLocation(46.7508, 6.5495)


def forecast_point(offset_minutes, variable):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=OBSERVED_AT + timedelta(minutes=offset_minutes),
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=(
            WeatherValue(
                variable=variable,
                value=(50.0 if variable is WeatherVariable.CLOUD_COVER_PERCENT else 8.0),
                unit=CANONICAL_UNITS[variable],
            ),
        ),
    )


def select(*points, maximum_minutes=30):
    return select_cloud_forecast_point(
        DecisionForecastEvidence(points),
        OBSERVED_AT,
        maximum_absolute_offset=timedelta(minutes=maximum_minutes),
    )


def test_empty_evidence_returns_none():
    assert select() is None


def test_evidence_without_cloud_returns_none():
    assert (
        select(
            forecast_point(0, WeatherVariable.TEMPERATURE_C),
            forecast_point(5, WeatherVariable.RELATIVE_HUMIDITY_PERCENT),
        )
        is None
    )


def test_single_admissible_cloud_point_is_returned_by_identity():
    cloud = forecast_point(10, WeatherVariable.CLOUD_COVER_PERCENT)

    assert select(cloud) is cloud


def test_only_cloud_participates_among_variables_at_same_timestamp():
    cloud = forecast_point(0, WeatherVariable.CLOUD_COVER_PERCENT)

    assert (
        select(
            forecast_point(0, WeatherVariable.TEMPERATURE_C),
            forecast_point(0, WeatherVariable.RELATIVE_HUMIDITY_PERCENT),
            forecast_point(0, WeatherVariable.WIND_SPEED_KMH),
            cloud,
        )
        is cloud
    )


def test_nearer_non_cloud_point_is_ignored():
    cloud = forecast_point(12, WeatherVariable.CLOUD_COVER_PERCENT)

    assert select(forecast_point(0, WeatherVariable.TEMPERATURE_C), cloud) is cloud


def test_nearest_cloud_point_is_selected_by_existing_policy():
    nearest = forecast_point(-5, WeatherVariable.CLOUD_COVER_PERCENT)

    assert (
        select(
            forecast_point(-20, WeatherVariable.CLOUD_COVER_PERCENT),
            forecast_point(8, WeatherVariable.CLOUD_COVER_PERCENT),
            nearest,
        )
        is nearest
    )


def test_cloud_exactly_at_inclusive_tolerance_is_selected():
    boundary = forecast_point(30, WeatherVariable.CLOUD_COVER_PERCENT)

    assert select(boundary) is boundary


def test_all_cloud_points_outside_tolerance_return_none():
    assert (
        select(
            forecast_point(-31, WeatherVariable.CLOUD_COVER_PERCENT),
            forecast_point(45, WeatherVariable.CLOUD_COVER_PERCENT),
        )
        is None
    )


def test_equidistant_cloud_points_propagate_selection_error():
    with pytest.raises(
        ForecastTemporalSelectionError,
        match="^ambiguous_nearest_forecast$",
    ):
        select(
            forecast_point(-5, WeatherVariable.CLOUD_COVER_PERCENT),
            forecast_point(5, WeatherVariable.CLOUD_COVER_PERCENT),
        )
