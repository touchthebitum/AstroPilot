from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.forecast_temporal_candidates import (
    ForecastTemporalCandidate,
    build_forecast_temporal_candidates,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


RETRIEVED_AT = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
OBSERVED_AT = datetime(2026, 9, 1, 21, 5, tzinfo=timezone.utc)
LOCATION = WeatherLocation(46.7508, 6.5495)


def forecast_point(forecast_for_utc):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=forecast_for_utc,
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=(
            WeatherValue(
                variable=WeatherVariable.TEMPERATURE_C,
                value=8.0,
                unit="°C",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("forecast_for_utc", "expected_offset"),
    [
        (OBSERVED_AT - timedelta(minutes=5), timedelta(minutes=-5)),
        (OBSERVED_AT, timedelta(0)),
        (OBSERVED_AT + timedelta(minutes=2), timedelta(minutes=2)),
    ],
)
def test_builds_signed_temporal_offset_and_preserves_point_identity(
    forecast_for_utc,
    expected_offset,
):
    point = forecast_point(forecast_for_utc)

    candidates = build_forecast_temporal_candidates((point,), OBSERVED_AT)

    assert len(candidates) == 1
    assert isinstance(candidates[0], ForecastTemporalCandidate)
    assert candidates[0].forecast_point is point
    assert candidates[0].temporal_offset == expected_offset


def test_preserves_input_order_without_temporal_sorting():
    first = forecast_point(OBSERVED_AT + timedelta(minutes=10))
    second = forecast_point(OBSERVED_AT - timedelta(minutes=5))
    third = forecast_point(OBSERVED_AT + timedelta(minutes=2))

    candidates = build_forecast_temporal_candidates(
        (first, second, third),
        OBSERVED_AT,
    )

    assert tuple(candidate.forecast_point for candidate in candidates) == (
        first,
        second,
        third,
    )
    assert tuple(candidate.temporal_offset for candidate in candidates) == (
        timedelta(minutes=10),
        timedelta(minutes=-5),
        timedelta(minutes=2),
    )


def test_empty_forecast_points_return_empty_tuple():
    assert build_forecast_temporal_candidates((), OBSERVED_AT) == ()


def test_forecast_temporal_candidate_is_immutable():
    candidate = build_forecast_temporal_candidates(
        (forecast_point(OBSERVED_AT),),
        OBSERVED_AT,
    )[0]

    with pytest.raises(FrozenInstanceError):
        candidate.temporal_offset = timedelta(minutes=1)


@pytest.mark.parametrize("invalid", [None, "2026-09-01T21:05:00Z", datetime(2026, 9, 1, 21, 5)])
def test_rejects_invalid_observation_timestamp(invalid):
    with pytest.raises(ValueError, match="^invalid_observed_at_utc$"):
        build_forecast_temporal_candidates((), invalid)


def test_accepts_non_utc_observation_timestamp_as_same_instant():
    offset = timezone(timedelta(hours=2))
    point = forecast_point(OBSERVED_AT)

    candidate = build_forecast_temporal_candidates(
        (point,),
        OBSERVED_AT.astimezone(offset),
    )[0]

    assert candidate.temporal_offset == timedelta(0)
