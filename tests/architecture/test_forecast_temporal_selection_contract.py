from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.forecast_temporal_candidates import (
    ForecastTemporalCandidate,
)
from decision.weather.forecast_temporal_selection import (
    ForecastTemporalSelectionError,
    select_forecast_temporal_candidate,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)
RETRIEVED_AT = OBSERVED_AT - timedelta(hours=2)
LOCATION = WeatherLocation(46.7508, 6.5495)


def candidate(offset_minutes):
    offset = timedelta(minutes=offset_minutes)
    point = WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=OBSERVED_AT + offset,
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
    return ForecastTemporalCandidate(
        forecast_point=point,
        temporal_offset=offset,
    )


def select(candidates, maximum_minutes=30):
    return select_forecast_temporal_candidate(
        candidates,
        maximum_absolute_offset=timedelta(minutes=maximum_minutes),
    )


def test_empty_candidates_return_none():
    assert select(()) is None


def test_exact_candidate_is_selected_by_identity():
    exact = candidate(0)

    assert select((candidate(10), exact)) is exact


@pytest.mark.parametrize(
    "candidates",
    [
        lambda nearest: (candidate(-20), nearest, candidate(7)),
        lambda nearest: (candidate(7), nearest, candidate(-20)),
    ],
)
def test_unique_nearest_is_independent_of_input_order(candidates):
    nearest = candidate(-5)

    assert select(candidates(nearest)) is nearest


def test_candidate_exactly_at_inclusive_tolerance_is_selected():
    boundary = candidate(30)

    assert select((boundary,)) is boundary


def test_all_candidates_outside_tolerance_return_none():
    assert select((candidate(-45), candidate(50))) is None


@pytest.mark.parametrize(
    "candidates",
    [
        (candidate(-5), candidate(5)),
        (candidate(5), candidate(5)),
    ],
)
def test_equal_nearest_offsets_are_explicitly_ambiguous(candidates):
    with pytest.raises(
        ForecastTemporalSelectionError,
        match="^ambiguous_nearest_forecast$",
    ):
        select(candidates)


@pytest.mark.parametrize(
    ("candidates", "invalid"),
    [
        ((candidate(0),), timedelta(microseconds=-1)),
        ((candidate(0),), 30),
        ((), timedelta(microseconds=-1)),
        ((), "30 minutes"),
    ],
)
def test_rejects_invalid_tolerance_even_with_empty_candidates(
    candidates,
    invalid,
):
    with pytest.raises(
        ValueError,
        match="^invalid_maximum_absolute_offset$",
    ):
        select_forecast_temporal_candidate(
            candidates,
            maximum_absolute_offset=invalid,
        )
