from datetime import timedelta
from types import SimpleNamespace

import pytest

import decision.mission.mission_assembler as module
from decision.mission.mission_assembler import MissionAssembler
from decision.mission.mission_input import MissionInput
from decision.mission.night_mission import MissionReason
from decision.weather.weather_forecast import WeatherForecast


@pytest.fixture
def summary():
    return SimpleNamespace(
        positives=["Bonne altitude", "Projet prioritaire"],
        negatives=["Lune présente"],
        confidence=0.85,
    )


@pytest.fixture
def context(frozen_time, buttes_site):
    return SimpleNamespace(
        site=buttes_site,
        session=SimpleNamespace(
            start_time=frozen_time,
            end_time=frozen_time + timedelta(hours=4),
        ),
        weather=SimpleNamespace(
            cloud_cover=55.0,
            humidity=70.0,
            wind_speed_kmh=8.0,
            seeing_arcsec=1.8,
            temperature_c=5.0,
        ),
        sky=SimpleNamespace(target_altitude_deg=42.0),
    )


@pytest.fixture
def isolated_dependencies(monkeypatch):
    captured = {}
    productivity = SimpleNamespace(
        timeline=SimpleNamespace(slices=["slice"]),
    )
    risk = SimpleNamespace(level="LOW")
    season = SimpleNamespace(conclusion="favorable")
    image_quality = SimpleNamespace(score=8.0)
    astro_quality = SimpleNamespace(score=82.0)
    dew_risk = SimpleNamespace(score=60.0)
    tasks = [SimpleNamespace(title="Capture")]

    def evaluate_productivity(productivity_context):
        captured["productivity_context"] = productivity_context
        return productivity

    def evaluate_astro(astro_context):
        captured["astro_context"] = astro_context
        return astro_quality

    monkeypatch.setattr(
        module.NightProductivityEngine,
        "evaluate",
        evaluate_productivity,
    )
    monkeypatch.setattr(
        module.ProjectRiskContextBuilder,
        "build",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(module.RiskEngine, "evaluate", lambda value: risk)
    monkeypatch.setattr(module.NightPlanner, "build", lambda value: tasks)
    monkeypatch.setattr(
        module.ImageQualityEngine,
        "evaluate",
        lambda value: image_quality,
    )
    monkeypatch.setattr(
        module.AstroQualityEngine,
        "evaluate",
        evaluate_astro,
    )
    monkeypatch.setattr(
        module.DewRiskEngine,
        "evaluate",
        lambda **kwargs: dew_risk,
    )
    monkeypatch.setattr(
        module.SeasonAnalysis,
        "analyze",
        lambda value: season,
    )
    monkeypatch.setattr(
        module.DynamicSeasonEngine,
        "target_visibility_window",
        lambda *args: [],
    )

    return SimpleNamespace(
        captured=captured,
        productivity=productivity,
        risk=risk,
        season=season,
        astro_quality=astro_quality,
        dew_risk=dew_risk,
        tasks=tasks,
    )


def mission_input(frozen_time, weather, **overrides):
    values = {
        "window_start": frozen_time,
        "window_end": frozen_time + timedelta(hours=2),
        "astronomical_hours": 2.0,
        "weather": weather,
        "moon_penalty": 0.3,
        "recommended_hours": 1.5,
        "expected_gain": 4.5,
        "selected_filter": None,
    }
    values.update(overrides)
    return MissionInput(**values)


def test_mission_preserves_reasons_and_computed_results(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    selected_filter = object()
    input_data = mission_input(
        frozen_time,
        WeatherForecast(),
        selected_filter=selected_filter,
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=["setup"],
        alternatives=[],
        mission_input=input_data,
    )

    assert mission.reasons == [
        MissionReason("Bonne altitude", "success"),
        MissionReason("Projet prioritaire", "success"),
        MissionReason("Lune présente", "warning"),
    ]
    assert mission.confidence == 0.85
    assert mission.window_start == input_data.window_start
    assert mission.window_end == input_data.window_end
    assert mission.recommended_hours == 1.5
    assert mission.expected_gain == 4.5
    assert mission.selected_filter is selected_filter
    assert mission.productivity is isolated_dependencies.productivity
    assert mission.risk_report is isolated_dependencies.risk
    assert mission.season_analysis is isolated_dependencies.season
    assert mission.tasks is isolated_dependencies.tasks
    assert mission.night_slices == ["slice"]
    assert mission.astro_quality is isolated_dependencies.astro_quality
    assert mission.dew_risk is isolated_dependencies.dew_risk


def test_mission_input_weather_takes_precedence_over_explicit_weather(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    explicit_weather = WeatherForecast(hourly_clouds=[90.0])
    selected_weather = WeatherForecast(
        hourly_clouds=[10.0, 30.0],
        hourly_humidity=[60.0, 80.0],
        hourly_wind=[4.0, 8.0],
        hourly_seeing=[1.0, 1.4],
        hourly_temperature=[2.0, 6.0],
    )

    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        weather=explicit_weather,
        mission_input=mission_input(frozen_time, selected_weather),
    )

    productivity_context = isolated_dependencies.captured[
        "productivity_context"
    ]
    assert productivity_context.weather is selected_weather
    assert productivity_context.cloud_cover == 20.0
    assert productivity_context.humidity == 70.0
    assert productivity_context.wind == 6.0
    assert productivity_context.seeing == 1.2


def test_window_duration_fills_missing_astronomical_hours(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    input_data = mission_input(
        frozen_time,
        WeatherForecast(),
        astronomical_hours=None,
        window_end=frozen_time + timedelta(hours=2, minutes=30),
    )

    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=input_data,
    )

    productivity_context = isolated_dependencies.captured[
        "productivity_context"
    ]
    assert productivity_context.astronomical_hours == 2.5


def test_context_session_fills_hours_without_mission_input(
    summary,
    context,
    isolated_dependencies,
):
    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
    )

    productivity_context = isolated_dependencies.captured[
        "productivity_context"
    ]
    assert productivity_context.astronomical_hours == 4.0
    assert productivity_context.observation_time == context.session.start_time


def test_missing_target_altitude_skips_astro_quality(
    monkeypatch,
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    context.sky.target_altitude_deg = None
    monkeypatch.setattr(
        module.AstroQualityEngine,
        "evaluate",
        lambda value: pytest.fail("astro quality must not be evaluated"),
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(frozen_time, WeatherForecast()),
    )

    assert mission.astro_quality is None


def test_build_does_not_mutate_context(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    original = {
        "start_time": context.session.start_time,
        "end_time": context.session.end_time,
        "cloud_cover": context.weather.cloud_cover,
        "humidity": context.weather.humidity,
        "wind_speed_kmh": context.weather.wind_speed_kmh,
        "seeing_arcsec": context.weather.seeing_arcsec,
        "temperature_c": context.weather.temperature_c,
        "target_altitude_deg": context.sky.target_altitude_deg,
    }

    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(frozen_time, WeatherForecast()),
    )

    assert {
        "start_time": context.session.start_time,
        "end_time": context.session.end_time,
        "cloud_cover": context.weather.cloud_cover,
        "humidity": context.weather.humidity,
        "wind_speed_kmh": context.weather.wind_speed_kmh,
        "seeing_arcsec": context.weather.seeing_arcsec,
        "temperature_c": context.weather.temperature_c,
        "target_altitude_deg": context.sky.target_altitude_deg,
    } == original


def test_operational_duration_and_gain_are_limited_by_productive_capacity(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 0.75
    isolated_dependencies.productivity.windows = [object()]
    input_data = mission_input(
        frozen_time,
        WeatherForecast(),
        recommended_hours=1.5,
        expected_gain=6.0,
    )

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=input_data,
    )

    assert result.recommended_hours == 0.75
    assert result.expected_gain == 3.0


def test_no_productive_window_exposes_no_recommended_duration_or_gain(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 0.75
    isolated_dependencies.productivity.windows = []

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(
            frozen_time,
            WeatherForecast(),
            recommended_hours=1.5,
            expected_gain=6.0,
        ),
    )

    assert result.recommended_hours == 0.0
    assert result.expected_gain == 0.0
