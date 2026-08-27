from datetime import timedelta
from types import SimpleNamespace

import pytest

import decision.mission.mission_assembler as assembler_module
from decision.forecast.forecast_engine import ForecastEngine
from decision.mission.mission_assembler import MissionAssembler
from decision.mission.mission_input import MissionInput


def _forecast_engine():
    return ForecastEngine(
        fetch_weather=lambda lat, lon: None,
        parse_hourly_weather=lambda weather: [],
        evaluate_object=lambda **kwargs: None,
        target_objects=[],
        moon_phase=lambda date: 0,
        night_hours_rough=lambda *args: [],
        timezone="Europe/Zurich",
        decision_engine_factory=lambda: object(),
        altitude_rule_factory=lambda: object(),
    )


@pytest.fixture
def isolated_peripheral_analyses(monkeypatch):
    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 60.0,
    )
    monkeypatch.setattr(
        assembler_module.ProjectRiskContextBuilder,
        "build",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        assembler_module.RiskEngine,
        "evaluate",
        lambda context: None,
    )
    monkeypatch.setattr(
        assembler_module.ImageQualityEngine,
        "evaluate",
        lambda context: SimpleNamespace(score=8.0),
    )
    monkeypatch.setattr(
        assembler_module.AstroQualityEngine,
        "evaluate",
        lambda context: SimpleNamespace(score=80.0),
    )
    monkeypatch.setattr(
        assembler_module.DewRiskEngine,
        "evaluate",
        lambda **kwargs: SimpleNamespace(score=70.0),
    )
    monkeypatch.setattr(
        assembler_module.SeasonAnalysis,
        "analyze",
        lambda context: None,
    )
    monkeypatch.setattr(
        assembler_module.DynamicSeasonEngine,
        "target_visibility_window",
        lambda *args: [],
    )


def _build_mission(rows, frozen_time, buttes_site):
    weather = _forecast_engine().build_weather_forecast(rows)
    mission_input = MissionInput(
        window_start=frozen_time,
        window_end=frozen_time + timedelta(hours=1),
        astronomical_hours=1.0,
        weather=weather,
        moon_penalty=0.1,
        recommended_hours=0.75,
        expected_gain=2.0,
    )
    context = SimpleNamespace(
        site=buttes_site,
        session=SimpleNamespace(
            start_time=frozen_time,
            end_time=frozen_time + timedelta(hours=1),
        ),
        weather=SimpleNamespace(
            cloud_cover=99.0,
            humidity=99.0,
            wind_speed_kmh=99.0,
            seeing_arcsec=1.5,
            temperature_c=0.0,
        ),
        sky=SimpleNamespace(target_altitude_deg=60.0),
    )
    summary = SimpleNamespace(
        positives=[],
        negatives=[],
        confidence=1.0,
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input,
    )

    return mission, weather


def test_hourly_weather_flows_through_productivity_into_the_mission(
    frozen_time,
    buttes_site,
    isolated_peripheral_analyses,
):
    rows = [
        {
            "cloud_cover": cloud_cover,
            "relative_humidity_2m": 50.0,
            "wind_speed_10m": 5.0,
            "temperature_2m": 4.0,
        }
        for cloud_cover in (0.0, 20.0, 40.0, 60.0)
    ]

    mission, weather = _build_mission(rows, frozen_time, buttes_site)

    assert mission.productivity.astronomical_hours == 1.0
    assert mission.productivity.productive_hours == pytest.approx(0.77)
    assert mission.productivity.confidence == pytest.approx(0.77)
    assert mission.night_slices is mission.productivity.timeline.slices
    assert [night_slice.cloud_cover for night_slice in mission.night_slices] == [
        0.0,
        20.0,
        40.0,
        60.0,
    ]
    assert [
        night_slice.productivity_score
        for night_slice in mission.night_slices
    ] == pytest.approx([0.98, 0.84, 0.70, 0.56])
    assert len(mission.productivity.windows) == 1
    assert mission.productivity.windows[0].start_hour == 0.0
    assert mission.productivity.windows[0].end_hour == 0.75
    assert mission.productivity.windows[0].productivity == pytest.approx(0.84)
    assert mission.recommended_hours == 0.75
    assert mission.tasks[0].title == "Installer le matériel"
    assert weather.hourly_clouds == [0.0, 20.0, 40.0, 60.0]


def test_degraded_weather_removes_productive_windows_from_the_mission(
    frozen_time,
    buttes_site,
    isolated_peripheral_analyses,
):
    rows = [
        {
            "cloud_cover": 100.0,
            "relative_humidity_2m": 90.0,
            "wind_speed_10m": 25.0,
            "temperature_2m": 4.0,
        }
        for _ in range(4)
    ]

    mission, _ = _build_mission(rows, frozen_time, buttes_site)

    assert mission.productivity.productive_hours == 0.0
    assert mission.productivity.confidence == 0.0
    assert mission.productivity.windows == []
    assert all(
        night_slice.productivity_score == 0.0
        for night_slice in mission.night_slices
    )
