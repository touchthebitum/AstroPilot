from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import astro_score
import astropilot.engines.sky_engine as sky_engine_module
from astropilot.engines.sky_engine import SkyEngine
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.mission.mission_input import MissionInput
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.night_productivity.night_conditions_provider import (
    NightConditionsProvider,
)
from decision.time_math import add_elapsed_time, elapsed_hours
from decision.validation.decision_consistency import DecisionConsistencyGate


ZONE = ZoneInfo("Europe/Zurich")


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (
            datetime(2026, 10, 24, 22, tzinfo=ZONE),
            datetime(2026, 10, 25, 3, tzinfo=ZONE),
        ),
        (
            datetime(2026, 3, 28, 22, tzinfo=ZONE),
            datetime(2026, 3, 29, 5, tzinfo=ZONE),
        ),
    ),
)
def test_transition_nights_use_six_elapsed_hours(monkeypatch, start, end):
    monkeypatch.setattr(astro_score.FilterInventoryLoader, "load", lambda: ())

    assert elapsed_hours(start, end) == 6.0
    mission_input = astro_score.build_mission_input(
        {
            "catalog_key": "M31",
            "window": {
                "start": start,
                "end": end,
                "moon_penalty": 0.0,
            },
            "remaining_hours": 10.0,
        }
    )
    assert mission_input.astronomical_hours == 6.0
    assert mission_input.recommended_hours == 6.0


def test_repeated_fall_hour_is_one_elapsed_hour_and_a_forward_window():
    first = datetime(2026, 10, 25, 2, tzinfo=ZONE, fold=0)
    second = datetime(2026, 10, 25, 2, tzinfo=ZONE, fold=1)

    assert elapsed_hours(first, second) == 1.0
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.FIXED_WINDOW,
        start=first,
        end=second,
    )
    assert availability.start.fold == 0
    assert availability.end.fold == 1

    mission = SimpleNamespace(
        window_start=first,
        window_end=second,
        recommended_hours=0.0,
        expected_gain=0.0,
        productivity=SimpleNamespace(
            astronomical_hours=1.0,
            productive_hours=0.0,
            confidence=0.0,
            windows=[],
        ),
    )
    DecisionConsistencyGate.validate_mission(mission)


def test_selected_weather_distinguishes_the_two_fall_folds():
    first = datetime(2026, 10, 25, 2, tzinfo=ZONE, fold=0)
    second = datetime(2026, 10, 25, 2, tzinfo=ZONE, fold=1)
    hours = [
        {
            "time": first,
            "cloud_cover": 10.0,
            "relative_humidity_2m": 60.0,
            "wind_speed_10m": 5.0,
        },
        {
            "time": second,
            "cloud_cover": 90.0,
            "relative_humidity_2m": 80.0,
            "wind_speed_10m": 15.0,
        },
    ]

    weather = astro_score.build_selected_window_weather(
        hours=hours,
        best={"start": first, "end": second, "details": []},
        sky=SimpleNamespace(estimate_seeing=lambda *_args: 1.5),
    )

    assert weather.hourly == [hours[0]]
    assert weather.hourly_clouds == [10.0]


def test_altitude_sample_uses_the_correct_elapsed_instant(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: captured.update(kwargs) or 42.0,
    )
    context = SimpleNamespace(
        observation_time=datetime(2026, 10, 24, 22, tzinfo=ZONE),
        target={},
        latitude=46.75,
        longitude=6.55,
    )

    assert NightConditionsProvider.altitude(5.25, context) == 42.0
    sampled = captured["obs_time"]
    assert sampled.isoformat() == "2026-10-25T02:15:00+01:00"
    assert sampled.fold == 1
    assert sampled.astimezone(timezone.utc) == datetime(
        2026,
        10,
        25,
        1,
        15,
        tzinfo=timezone.utc,
    )


def test_sky_window_end_adds_one_real_hour_across_fall_fold(monkeypatch):
    first = datetime(2026, 10, 25, 2, tzinfo=ZONE, fold=0)
    engine = SkyEngine()
    monkeypatch.setattr(
        engine,
        "hour_geometry",
        lambda *_args: {"target_altitude": 60.0},
    )
    monkeypatch.setattr(
        engine,
        "score_hour",
        lambda *_args, **_kwargs: {
            "score": 80.0,
            "details": {
                "target_altitude": 60.0,
                "moon_sep": 120.0,
                "sqm": 20.0,
            },
            "moon_impact": 0.0,
            "moon_penalty": 0.0,
        },
    )
    monkeypatch.setattr(sky_engine_module.moon, "elevation", lambda *_args: 0.0)
    hour = {
        "time": first,
        "relative_humidity_2m": 60.0,
        "wind_speed_10m": 5.0,
        "cloud_cover_low": 0.0,
        "cloud_cover_mid": 0.0,
        "cloud_cover_high": 0.0,
        "visibility": 20_000.0,
    }

    result = engine.best_windows(
        [hour],
        0.0,
        object(),
        46.75,
        6.55,
        target_obj={"type": "galaxy"},
        window_size=1,
    )

    assert result[0]["start"] == first
    assert result[0]["end"].fold == 1
    assert elapsed_hours(result[0]["start"], result[0]["end"]) == 1.0


def test_productive_assessment_derives_elapsed_astronomical_hours(monkeypatch):
    start = datetime(2026, 10, 24, 22, tzinfo=ZONE)
    end = datetime(2026, 10, 25, 3, tzinfo=ZONE)
    captured = {}

    def evaluate(context):
        captured["context"] = context
        return SimpleNamespace(
            result=SimpleNamespace(
                productive_hours=0.0,
                windows=[],
            ),
            breakdown=None,
        )

    monkeypatch.setattr(
        "decision.mission.mission_assembler."
        "NightProductivityEngine.evaluate_with_breakdown",
        evaluate,
    )
    mission_input = MissionInput(
        window_start=start,
        window_end=end,
        astronomical_hours=None,
        weather=None,
        moon_penalty=0.0,
        recommended_hours=0.0,
        expected_gain=0.0,
    )
    context = SimpleNamespace(
        site=SimpleNamespace(latitude=46.75, longitude=6.55),
        session=SimpleNamespace(start_time=start, end_time=end),
        weather=SimpleNamespace(
            cloud_cover=20.0,
            humidity=60.0,
            wind_speed_kmh=5.0,
            seeing_arcsec=1.5,
        ),
    )

    ProductiveWindowAssessment.build(
        target="M31",
        context=context,
        mission_input=mission_input,
    )

    assert captured["context"].astronomical_hours == 6.0


def test_ordinary_night_matches_wall_arithmetic_and_midnight_rollover():
    start = datetime(2026, 9, 24, 23, tzinfo=ZONE)
    end = datetime(2026, 9, 25, 1, tzinfo=ZONE)

    assert elapsed_hours(start, end) == (end - start).total_seconds() / 3600
    assert add_elapsed_time(start, timedelta(hours=2)) == end
