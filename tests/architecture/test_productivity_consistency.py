from datetime import timedelta

import pytest

from decision.night_productivity.night_productivity_context import (
    NightProductivityContext,
)
from decision.night_productivity.night_productivity_engine import (
    NightProductivityEngine,
)
from decision.weather.weather_forecast import WeatherForecast


def test_sky_moon_score_is_normalized_before_productivity(
    monkeypatch,
    frozen_time,
):
    import astro_score

    weather = WeatherForecast(
        hourly_clouds=[0.0, 0.0],
        hourly_humidity=[50.0, 50.0],
        hourly_wind=[5.0, 5.0],
        hourly_seeing=[1.5, 1.5],
        hourly_moon_penalty=[35.0, 35.0],
    )
    mission_input = astro_score.build_mission_input(
        {
            "catalog_key": "M31",
            "window": {
                "start": frozen_time,
                "end": frozen_time + timedelta(hours=2),
                "moon_penalty": 35.0,
            },
            "selected_window_weather": weather,
            "remaining_hours": 2.0,
        }
    )

    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 60.0,
    )

    productivity = NightProductivityEngine.evaluate(
        NightProductivityContext(
            astronomical_hours=mission_input.astronomical_hours,
            cloud_cover=0.0,
            moon_penalty=mission_input.moon_penalty,
            altitude_score=8,
            humidity=50.0,
            wind=5.0,
            seeing=1.5,
            weather=mission_input.weather,
            hourly_seeing=mission_input.weather.hourly_seeing,
            hourly_moon_penalty=mission_input.weather.hourly_moon_penalty,
            target={"ra": 10.0, "dec": 20.0},
            latitude=46.7508,
            longitude=6.5495,
            observation_time=frozen_time,
        )
    )

    assert mission_input.moon_penalty == pytest.approx(1.0)
    assert mission_input.weather.hourly_moon_penalty == [1.0, 1.0]
    assert productivity.astronomical_hours == 2.0
    assert productivity.productive_hours > 0
    assert productivity.confidence > 0


def test_valid_selected_window_seeing_is_not_replaced_by_fallback(
    monkeypatch,
    frozen_time,
):
    weather = WeatherForecast(
        hourly_clouds=[0.0],
        hourly_humidity=[50.0],
        hourly_wind=[5.0],
        hourly_seeing=[2.6],
        hourly_moon_penalty=[0.0],
    )
    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 60.0,
    )

    productivity = NightProductivityEngine.evaluate(
        NightProductivityContext(
            astronomical_hours=1.0,
            cloud_cover=0.0,
            moon_penalty=0.0,
            altitude_score=8,
            humidity=50.0,
            wind=5.0,
            seeing=1.5,
            weather=weather,
            hourly_seeing=weather.hourly_seeing,
            hourly_moon_penalty=weather.hourly_moon_penalty,
            target={"ra": 10.0, "dec": 20.0},
            latitude=46.7508,
            longitude=6.5495,
            observation_time=frozen_time,
        )
    )

    assert {night_slice.seeing for night_slice in productivity.timeline.slices} == {
        2.6
    }
