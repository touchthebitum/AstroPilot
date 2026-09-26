from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from decision.mission.mission_presenter import MissionPresenter
from decision.mission.night_mission import NightMission
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_window import NightWindow
from decision.runners.report_runner import ReportRunner
from decision.runners.tonight_runner import TonightRunner
from decision.season.dynamic_season_engine import DynamicSeasonEngine
from decision.services.tonight_application_service import TonightResult
from decision.services.tonight_mission_service import TonightMissionService
from decision.services.tonight_response import TonightResponse


ZONE = ZoneInfo("Europe/Zurich")

TRANSITION_WINDOWS = (
    (
        datetime(2026, 10, 25, 1, 50, tzinfo=ZONE),
        datetime(2026, 10, 25, 3, 10, tzinfo=ZONE),
    ),
    (
        datetime(2026, 3, 29, 1, 50, tzinfo=ZONE),
        datetime(2026, 3, 29, 3, 10, tzinfo=ZONE),
    ),
    (
        datetime(2026, 2, 15, 1, 50, tzinfo=ZONE),
        datetime(2026, 2, 15, 3, 10, tzinfo=ZONE),
    ),
)


def _assert_elapsed_cadence(samples, minutes):
    utc_samples = [sample.astimezone(timezone.utc) for sample in samples]
    assert all(
        later - earlier == timedelta(minutes=minutes)
        for earlier, later in zip(utc_samples, utc_samples[1:])
    )


def _assert_transition_representation(samples, start):
    if start.month == 10:
        repeated = [
            sample
            for sample in samples
            if sample.hour == 2 and sample.minute == 0
        ]
        assert [sample.fold for sample in repeated] == [0, 1]
        assert [sample.utcoffset() for sample in repeated] == [
            timedelta(hours=2),
            timedelta(hours=1),
        ]
    elif start.month == 3:
        assert not any(sample.hour == 2 for sample in samples)


@pytest.mark.parametrize(("start", "end"), TRANSITION_WINDOWS)
def test_five_minute_season_samples_follow_elapsed_time(
    monkeypatch,
    start,
    end,
):
    monkeypatch.setattr(
        DynamicSeasonEngine,
        "target_altitude_at_time",
        lambda *_args, **_kwargs: 45.0,
    )

    samples = DynamicSeasonEngine.target_visibility_window(
        {},
        46.75,
        6.55,
        start,
        end,
    )
    sample_times = [sample_time for sample_time, _altitude in samples]

    _assert_elapsed_cadence(sample_times, 5)
    _assert_transition_representation(sample_times, start)


@pytest.mark.parametrize(("start", "end"), TRANSITION_WINDOWS)
def test_ten_minute_season_samples_follow_elapsed_time(
    monkeypatch,
    start,
    end,
):
    captured = []
    monkeypatch.setattr(
        "decision.season.dynamic_season_engine."
        "SkyEngine.astronomical_night_window",
        lambda **_kwargs: (start, end),
    )

    def target_altitudes(
        _self,
        _ra,
        _dec,
        sample_times,
        _latitude,
        _longitude,
    ):
        captured.extend(sample_times)
        return [45.0] * len(sample_times)

    monkeypatch.setattr(
        "decision.season.dynamic_season_engine."
        "SkyEngine.target_altitudes",
        target_altitudes,
    )
    context = SimpleNamespace(
        target="M31",
        latitude=46.75,
        longitude=6.55,
        observation_time=start,
    )

    DynamicSeasonEngine.summary(
        context,
        horizon_days=0,
        min_altitude=30,
        min_useful_hours=0,
    )

    _assert_elapsed_cadence(captured, 10)
    _assert_transition_representation(captured, start)


def _productivity(timeline_start, start_offset, end_offset):
    return NightProductivityResult(
        astronomical_hours=2.0,
        productive_hours=1.0,
        confidence=0.5,
        cloud_loss=0.0,
        moon_loss=0.0,
        altitude_loss=0.0,
        weather_loss=0.0,
        display_start_hour=timeline_start.hour,
        windows=[
            NightWindow(
                start_hour=start_offset,
                end_hour=end_offset,
                productivity=0.9,
                altitude=60.0,
                cloud_cover=10.0,
                moon_penalty=0.0,
                seeing=1.2,
                productive=True,
                reason="stable_conditions",
            )
        ],
    )


def _mission(productivity):
    return NightMission(
        target="M31",
        confidence=0.9,
        productivity=productivity,
    )


def _run_historical_tonight_path(mission, timeline_start):
    forecast_engine = SimpleNamespace(
        simulate_dynamic_portfolio_roadmap=lambda **_kwargs: [],
    )
    report_runner = ReportRunner(
        portfolio_forecast_engine=forecast_engine,
        show_multi_night_portfolio_roadmap=lambda _roadmap: None,
        show_portfolio_completion_forecast=lambda _roadmap: None,
        present_mission=MissionPresenter.present,
        tonight_mission_service=TonightMissionService(
            build_mission=lambda **_kwargs: mission,
        ),
    )
    recommendation = SimpleNamespace(
        opportunity=SimpleNamespace(
            candidate={"catalog_key": "M31"},
        ),
    )
    runner = TonightRunner(
        report_runner=report_runner,
        portfolio_forecast_engine=forecast_engine,
        build_mission_input=lambda _evaluation: SimpleNamespace(
            window_start=timeline_start,
        ),
        recommend_project_for_night=lambda *_args, **_kwargs: [
            {"catalog_key": "M31"},
        ],
        opportunity_recommendation_service=SimpleNamespace(
            build=lambda **_kwargs: recommendation,
        ),
    )
    winner = {
        "duration": 2.0,
        "top_objects": [
            {
                "catalog_key": "M31",
                "name": "M31",
                "decision_summary": "summary",
                "decision_context": "context",
            }
        ],
        "object_evaluations": {"M31": {}},
    }

    runner.run(
        top_nights=[winner],
        night_capacities=[],
    )


def test_tonight_response_distinguishes_the_two_fall_hours():
    productivity = _productivity(
        datetime(2026, 10, 25, 1, 50, tzinfo=ZONE),
        10 / 60,
        70 / 60,
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 10, 25)},
            recommendation=None,
            mission=_mission(productivity),
            timeline_start=datetime(2026, 10, 25, 1, 50, tzinfo=ZONE),
        )
    )

    window = response.productivity.windows[0]
    assert window.start_time == "02:00 (UTC+02)"
    assert window.end_time == "02:00 (UTC+01)"


def test_presenter_distinguishes_the_two_fall_hours(monkeypatch, capsys):
    monkeypatch.setattr(
        "decision.mission.mission_presenter.NightAdvisor.build",
        lambda _mission: [],
    )
    productivity = _productivity(
        datetime(2026, 10, 25, 1, 50, tzinfo=ZONE),
        10 / 60,
        70 / 60,
    )

    MissionPresenter.present(
        _mission(productivity),
        timeline_start=datetime(2026, 10, 25, 1, 50, tzinfo=ZONE),
    )

    output = capsys.readouterr().out
    assert "02:00 (UTC+02) → 02:00 (UTC+01)" in output


def test_historical_tonight_runner_propagates_fall_dst_anchor(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "decision.mission.mission_presenter.NightAdvisor.build",
        lambda _mission: [],
    )
    timeline_start = datetime(2026, 10, 25, 1, 50, tzinfo=ZONE)
    mission = _mission(
        _productivity(
            timeline_start,
            10 / 60,
            70 / 60,
        )
    )

    _run_historical_tonight_path(mission, timeline_start)

    output = capsys.readouterr().out
    assert "02:00 (UTC+02) → 02:00 (UTC+01)" in output


def test_historical_tonight_runner_keeps_ordinary_labels_unchanged(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "decision.mission.mission_presenter.NightAdvisor.build",
        lambda _mission: [],
    )
    timeline_start = datetime(2026, 9, 24, 22, 30, tzinfo=ZONE)
    mission = _mission(
        _productivity(
            timeline_start,
            1.0,
            2.5,
        )
    )

    _run_historical_tonight_path(mission, timeline_start)

    output = capsys.readouterr().out
    assert "23:30 → 01:00" in output
    assert "UTC" not in output


def test_ordinary_window_labels_remain_plain_hhmm(monkeypatch, capsys):
    monkeypatch.setattr(
        "decision.mission.mission_presenter.NightAdvisor.build",
        lambda _mission: [],
    )
    productivity = _productivity(
        datetime(2026, 9, 24, 22, 30, tzinfo=ZONE),
        1.0,
        2.5,
    )
    mission = _mission(productivity)

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 24)},
            recommendation=None,
            mission=mission,
            timeline_start=datetime(2026, 9, 24, 22, 30, tzinfo=ZONE),
        )
    )
    MissionPresenter.present(
        mission,
        timeline_start=datetime(2026, 9, 24, 22, 30, tzinfo=ZONE),
    )

    window = response.productivity.windows[0]
    assert (window.start_time, window.end_time) == ("23:30", "01:00")
    output = capsys.readouterr().out
    assert "23:30 → 01:00" in output
    assert "UTC" not in output
