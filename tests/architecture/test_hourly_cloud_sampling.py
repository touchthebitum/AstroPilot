from datetime import datetime, timedelta

import pytest

from decision.night_productivity.night_productivity_context import (
    NightProductivityContext,
)
from decision.night_productivity.night_productivity_engine import (
    NightProductivityEngine,
)
from decision.weather.weather_forecast import WeatherForecast


def _context(hourly_clouds, observation_time):
    weather = WeatherForecast(
        hourly_clouds=hourly_clouds,
        hourly_humidity=[50.0] * len(hourly_clouds),
        hourly_wind=[5.0] * len(hourly_clouds),
    )
    return NightProductivityContext(
        astronomical_hours=float(len(hourly_clouds)),
        cloud_cover=sum(hourly_clouds) / len(hourly_clouds),
        moon_penalty=0.0,
        altitude_score=8,
        humidity=50.0,
        wind=5.0,
        seeing=1.5,
        weather=weather,
        target={"ra": 10.0, "dec": 20.0},
        latitude=46.7508,
        longitude=6.5495,
        observation_time=observation_time,
    )


@pytest.fixture(autouse=True)
def fixed_target_altitude(monkeypatch):
    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 60.0,
    )


def test_hourly_cloud_sample_is_kept_for_four_quarter_hour_slices():
    result = NightProductivityEngine.evaluate(
        _context([10.0, 80.0], datetime(2026, 8, 26, 22, 0))
    )

    assert [item.cloud_cover for item in result.timeline.slices] == [
        10.0,
        10.0,
        10.0,
        10.0,
        80.0,
        80.0,
        80.0,
        80.0,
    ]


@pytest.mark.parametrize(
    ("hourly_clouds", "expected_offsets", "expected_clock_window"),
    [
        (
            [10.0, 80.0],
            (0.0, 1.0),
            (datetime(2026, 8, 26, 22, 0), datetime(2026, 8, 26, 23, 0)),
        ),
        (
            [80.0, 10.0],
            (1.0, 2.0),
            (datetime(2026, 8, 26, 23, 0), datetime(2026, 8, 27, 0, 0)),
        ),
    ],
)
def test_cloud_trend_around_22_to_midnight_sets_expected_window(
    hourly_clouds,
    expected_offsets,
    expected_clock_window,
):
    observation_time = datetime(2026, 8, 26, 22, 0)
    result = NightProductivityEngine.evaluate(
        _context(hourly_clouds, observation_time)
    )

    assert len(result.windows) == 1
    window = result.windows[0]
    assert (window.start_hour, window.end_hour) == expected_offsets
    assert (
        observation_time + timedelta(hours=window.start_hour),
        observation_time + timedelta(hours=window.end_hour),
    ) == expected_clock_window


def test_hourly_cloud_sampling_rolls_over_from_23_to_01_exactly():
    observation_time = datetime(2026, 8, 26, 23, 0)
    result = NightProductivityEngine.evaluate(
        _context([23.0, 1.0], observation_time)
    )

    assert [
        (
            int(item.start_hour),
            item.start_hour,
            item.end_hour,
            observation_time + timedelta(hours=item.start_hour),
            observation_time + timedelta(hours=item.end_hour),
            item.cloud_cover,
        )
        for item in result.timeline.slices
    ] == [
        (
            0,
            0.0,
            0.25,
            datetime(2026, 8, 26, 23, 0),
            datetime(2026, 8, 26, 23, 15),
            23.0,
        ),
        (
            0,
            0.25,
            0.5,
            datetime(2026, 8, 26, 23, 15),
            datetime(2026, 8, 26, 23, 30),
            23.0,
        ),
        (
            0,
            0.5,
            0.75,
            datetime(2026, 8, 26, 23, 30),
            datetime(2026, 8, 26, 23, 45),
            23.0,
        ),
        (
            0,
            0.75,
            1.0,
            datetime(2026, 8, 26, 23, 45),
            datetime(2026, 8, 27, 0, 0),
            23.0,
        ),
        (
            1,
            1.0,
            1.25,
            datetime(2026, 8, 27, 0, 0),
            datetime(2026, 8, 27, 0, 15),
            1.0,
        ),
        (
            1,
            1.25,
            1.5,
            datetime(2026, 8, 27, 0, 15),
            datetime(2026, 8, 27, 0, 30),
            1.0,
        ),
        (
            1,
            1.5,
            1.75,
            datetime(2026, 8, 27, 0, 30),
            datetime(2026, 8, 27, 0, 45),
            1.0,
        ),
        (
            1,
            1.75,
            2.0,
            datetime(2026, 8, 27, 0, 45),
            datetime(2026, 8, 27, 1, 0),
            1.0,
        ),
    ]
