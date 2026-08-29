from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from decision.validation.weather_window_coverage import (
    WeatherWindowCoverageError,
    validate_selected_window_weather_coverage,
)
from decision.weather.weather_ingress import WeatherSnapshot


START = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
END = datetime(2026, 9, 2, 5, tzinfo=timezone.utc)


def snapshot(valid_from=START, valid_until=END):
    return WeatherSnapshot(
        payload={},
        provider="Open-Meteo",
        retrieved_at_utc=START - timedelta(minutes=5),
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
        valid_until=valid_until,
        hour_count=24,
        completeness=1.0,
    )


def mission(start=START + timedelta(hours=1), end=END - timedelta(hours=1)):
    return SimpleNamespace(window_start=start, window_end=end)


def test_window_fully_inside_weather_coverage_is_accepted():
    validate_selected_window_weather_coverage(mission(), snapshot())


def test_exact_weather_boundaries_are_inclusive():
    validate_selected_window_weather_coverage(
        mission(start=START, end=END),
        snapshot(),
    )


@pytest.mark.parametrize(
    ("start", "end", "issues"),
    [
        (
            START - timedelta(microseconds=1),
            END - timedelta(hours=1),
            ("window_starts_before_weather",),
        ),
        (
            START + timedelta(hours=1),
            END + timedelta(microseconds=1),
            ("window_ends_after_weather",),
        ),
        (
            START - timedelta(hours=3),
            START - timedelta(hours=1),
            ("window_starts_before_weather",),
        ),
        (
            END + timedelta(hours=1),
            END + timedelta(hours=3),
            ("window_ends_after_weather",),
        ),
        (
            START - timedelta(hours=1),
            END + timedelta(hours=1),
            (
                "window_starts_before_weather",
                "window_ends_after_weather",
            ),
        ),
    ],
)
def test_partial_and_total_coverage_fail_closed(start, end, issues):
    with pytest.raises(WeatherWindowCoverageError) as caught:
        validate_selected_window_weather_coverage(
            mission(start=start, end=end),
            snapshot(),
        )

    assert caught.value.code == "weather_window_uncovered"
    assert caught.value.issues == issues


def test_window_crossing_midnight_is_compared_as_forward_instants():
    validate_selected_window_weather_coverage(
        mission(
            start=datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
            end=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        ),
        snapshot(),
    )


def test_equivalent_instants_in_different_timezones_match_boundaries():
    zurich = ZoneInfo("Europe/Zurich")

    validate_selected_window_weather_coverage(
        mission(
            start=START.astimezone(zurich),
            end=END.astimezone(zurich),
        ),
        snapshot(),
    )


def test_naive_weather_coverage_boundary_fails_closed():
    invalid = snapshot(valid_from=START.replace(tzinfo=None))

    with pytest.raises(WeatherWindowCoverageError) as caught:
        validate_selected_window_weather_coverage(mission(), invalid)

    assert caught.value.issues == ("invalid_weather_coverage",)
