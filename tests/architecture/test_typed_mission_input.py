from datetime import timedelta
from types import SimpleNamespace

import pytest

from decision.mission.mission_assembler import MissionAssembler
from decision.mission.mission_builder import NightMissionBuilder
from decision.weather.weather_forecast import WeatherForecast


def _mission_input(frozen_time, weather, **overrides):
    from decision.mission.mission_input import MissionInput

    values = {
        "window_start": frozen_time,
        "window_end": frozen_time + timedelta(hours=2),
        "astronomical_hours": 2.0,
        "weather": weather,
        "moon_penalty": 0.35,
        "recommended_hours": 2.0,
        "expected_gain": 4.0,
    }
    values.update(overrides)
    return MissionInput(**values)


@pytest.fixture
def mission_context(
    frozen_time,
    buttes_site,
    frozen_equipment,
    frozen_portfolio,
):
    return SimpleNamespace(
        site=buttes_site,
        session=SimpleNamespace(
            start_time=frozen_time,
            end_time=frozen_time + timedelta(hours=2),
        ),
        equipment=frozen_equipment,
        portfolio=frozen_portfolio,
        weather=SimpleNamespace(
            cloud_cover=88.0,
            humidity=89.0,
            wind_speed_kmh=19.0,
            seeing_arcsec=2.8,
        ),
        sky=SimpleNamespace(target_altitude_deg=45.0),
    )


@pytest.fixture
def summary():
    return SimpleNamespace(positives=[], negatives=[], confidence=1.0)


@pytest.fixture
def isolate_assembler(monkeypatch):
    timeline = SimpleNamespace(slices=[])
    productivity = SimpleNamespace(timeline=timeline)
    captured = {}

    def evaluate(context):
        captured["context"] = context
        return productivity

    monkeypatch.setattr(
        "decision.mission.mission_assembler.NightProductivityEngine.evaluate",
        evaluate,
    )
    monkeypatch.setattr(
        "decision.mission.mission_assembler.NightScheduler.build",
        lambda productivity: None,
    )
    monkeypatch.setattr(
        "decision.mission.mission_assembler.ProjectRiskContextBuilder.build",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "decision.mission.mission_assembler.RiskEngine.evaluate",
        lambda context: None,
    )
    monkeypatch.setattr(
        "decision.mission.mission_assembler.NightPlanner.build",
        lambda productivity: [],
    )
    monkeypatch.setattr(
        "decision.mission.mission_assembler.SeasonAnalysis.analyze",
        lambda context: None,
    )
    monkeypatch.setattr(
        "decision.mission.mission_assembler."
        "DynamicSeasonEngine.target_visibility_window",
        lambda *args, **kwargs: [],
    )
    return captured


def _build_mission(
    mission_input,
    mission_context,
    summary,
    isolate_assembler,
):
    return NightMissionBuilder.build(
        target="M31",
        summary=summary,
        context=mission_context,
        mission_input=mission_input,
    )


def test_selected_window_reaches_night_mission(
    frozen_time,
    frozen_weather,
    mission_context,
    summary,
    isolate_assembler,
):
    mission = _build_mission(
        _mission_input(frozen_time, frozen_weather),
        mission_context,
        summary,
        isolate_assembler,
    )

    assert mission.window_start == frozen_time
    assert mission.window_end == frozen_time + timedelta(hours=2)


def test_two_hour_window_reaches_productivity_as_two_astronomical_hours(
    frozen_time,
    frozen_weather,
    mission_context,
    summary,
    isolate_assembler,
):
    _build_mission(
        _mission_input(frozen_time, frozen_weather),
        mission_context,
        summary,
        isolate_assembler,
    )

    assert isolate_assembler["context"].astronomical_hours == 2.0


def test_selected_window_conditions_reach_productivity_context(
    frozen_time,
    mission_context,
    summary,
    isolate_assembler,
):
    weather = WeatherForecast(
        hourly_clouds=[10.0, 30.0],
        hourly_humidity=[70.0, 80.0],
        hourly_wind=[5.0, 9.0],
        hourly_seeing=[1.1, 1.5],
        hourly_moon_penalty=[0.2, 0.5],
    )
    _build_mission(
        _mission_input(frozen_time, weather, moon_penalty=0.35),
        mission_context,
        summary,
        isolate_assembler,
    )

    context = isolate_assembler["context"]
    assert context.weather is weather
    assert context.cloud_cover == 20.0
    assert context.humidity == 75.0
    assert context.wind == 7.0
    assert context.seeing == 1.3
    assert context.moon_penalty == 0.35
    assert context.hourly_clouds == [10.0, 30.0]
    assert context.hourly_humidity == [70.0, 80.0]
    assert context.hourly_wind == [5.0, 9.0]
    assert context.hourly_seeing == [1.1, 1.5]
    assert context.hourly_moon_penalty == [0.2, 0.5]


def test_recommended_hours_matches_usable_selected_window(
    frozen_time,
    frozen_weather,
    mission_context,
    summary,
    isolate_assembler,
):
    mission = _build_mission(
        _mission_input(
            frozen_time,
            frozen_weather,
            recommended_hours=1.25,
        ),
        mission_context,
        summary,
        isolate_assembler,
    )

    assert mission.recommended_hours == 1.25


def test_expected_gain_uses_existing_session_portfolio_gain(
    monkeypatch,
    frozen_time,
    frozen_weather,
):
    import astro_score

    evaluation = {
        "catalog_key": "M31",
        "window": {
            "start": frozen_time,
            "end": frozen_time + timedelta(hours=2),
            "moon_penalty": 0.35,
        },
        "selected_window_weather": frozen_weather,
        "remaining_hours": 1.5,
    }
    monkeypatch.setattr(
        astro_score,
        "session_portfolio_gain",
        lambda target, hours: 7.5 if (target, hours) == ("M31", 1.5) else -1,
    )

    mission_input = astro_score.build_mission_input(evaluation)

    assert mission_input.recommended_hours == 1.5
    assert mission_input.expected_gain == 7.5


def test_fallback_constants_are_used_only_when_data_is_missing(
    frozen_time,
    mission_context,
    summary,
    isolate_assembler,
):
    missing_weather = WeatherForecast()
    mission_context.weather = SimpleNamespace(
        cloud_cover=None,
        humidity=None,
        wind_speed_kmh=None,
        seeing_arcsec=None,
    )
    mission_context.session = SimpleNamespace(
        start_time=None,
        end_time=None,
    )
    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=mission_context,
        equipment=[],
        timeline=[],
        alternatives=[],
        mission_input=_mission_input(
            frozen_time,
            missing_weather,
            window_start=None,
            window_end=None,
            astronomical_hours=None,
            moon_penalty=None,
        ),
    )

    context = isolate_assembler["context"]
    assert context.astronomical_hours == 6.0
    assert context.cloud_cover == 20
    assert context.humidity == 60
    assert context.wind == 5
    assert context.seeing == 1.5
    assert context.moon_penalty == 0.2
