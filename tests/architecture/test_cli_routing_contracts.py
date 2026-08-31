from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import astro_score
from decision.forecast.forecast_run import ForecastRun
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


def test_direct_command_loads_profile_once(monkeypatch):
    calls = []
    profile = {"active_equipment": "setup"}

    def load_profile():
        calls.append(None)
        return profile

    monkeypatch.setattr(astro_score, "load_user_profile", load_profile)
    monkeypatch.setattr(
        astro_score,
        "FilterTargetConfigurationService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        astro_score,
        "compare_equipment_for_object",
        lambda object_name, supplied_profile: None,
    )

    assert astro_score.main(["--object", "M31"]) == 0
    assert len(calls) == 1


def test_help_does_not_load_user_profile(monkeypatch):
    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: pytest.fail("profile must not be loaded"),
    )

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--help"])

    assert exit_info.value.code == 0


@pytest.fixture
def isolated_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: {
            "active_equipment": "setup",
            "location": {
                "latitude": 46.5,
                "longitude": 6.6,
                "name": "Buttes",
            },
            "preferences": {
                "productive_hours_per_night": 3.5,
                "observing_nights_per_week": 2.0,
            },
            "sessions": [],
        },
    )
    monkeypatch.setattr(
        astro_score,
        "FilterTargetConfigurationService",
        lambda **kwargs: object(),
    )


@pytest.mark.parametrize(
    ("argument", "function_name", "target"),
    [
        ("--object", "compare_equipment_for_object", "M31"),
        ("--target-object", "show_target_object_analysis", "M42"),
    ],
)
def test_direct_object_commands_return_before_location_and_weather(
    monkeypatch,
    isolated_cli,
    argument,
    function_name,
    target,
):
    calls = []
    monkeypatch.setattr(
        astro_score,
        function_name,
        lambda value, profile: calls.append(value),
    )
    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda *args: pytest.fail("weather must not be fetched"),
    )

    result = astro_score.main([argument, target])

    assert result == 0
    assert calls == [target]


@pytest.fixture
def forecast_cli(monkeypatch, isolated_cli):
    calls = []
    forecast_calls = []
    clock_calls = []
    reference_time = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            clock_calls.append(tz)
            return reference_time

    capacities = [
        {"date": "2026-08-27", "hours": 2.0, "quality": 80.0},
    ]
    nights = [
        {"date": "2026-08-28", "score": 70.0},
        {"date": "2026-08-27", "score": 90.0},
    ]

    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda lat, lon: {"weather": True},
    )
    monkeypatch.setattr(astro_score, "datetime", FixedDateTime)
    def forecast(*args, **kwargs):
        forecast_calls.append((args, kwargs))
        return ForecastRun(
            nights=nights,
            evidence=DecisionForecastEvidence(()),
        )

    monkeypatch.setattr(astro_score, "forecast_astro", forecast)
    monkeypatch.setattr(
        astro_score,
        "forecast_night_capacities",
        lambda *args, **kwargs: capacities,
    )
    monkeypatch.setattr(
        astro_score.HistoricalNightCapacityEstimator,
        "estimate",
        lambda **kwargs: SimpleNamespace(
            productive_hours_per_night=3.5,
            source="profile",
            historical_nights=0,
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "report_runner",
        SimpleNamespace(
            run_portfolio=lambda **kwargs: calls.append(("portfolio", kwargs)),
            run_calendar=lambda **kwargs: calls.append(("calendar", kwargs)),
            run_full=lambda **kwargs: calls.append(("full", kwargs)),
            present_mission=lambda mission: calls.append(
                ("mission", mission)
            ),
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "tonight_runner",
        SimpleNamespace(
            show_completion_forecast=lambda capacities, profile: calls.append(
                (
                    "tonight_completion",
                    {"night_capacities": capacities, "profile": profile},
                )
            ),
        ),
    )

    return SimpleNamespace(
        calls=calls,
        capacities=capacities,
        nights=nights,
        forecast_calls=forecast_calls,
        clock_calls=clock_calls,
        reference_time=reference_time,
    )


@pytest.mark.parametrize("mode", ["portfolio", "calendar", "full"])
def test_report_modes_route_to_exactly_one_runner(mode, forecast_cli):
    result = astro_score.main(["--mode", mode])

    assert result == 0
    assert len(forecast_cli.forecast_calls) == 1
    reference_time = forecast_cli.forecast_calls[0][1]["reference_time_utc"]
    assert reference_time is forecast_cli.reference_time
    assert forecast_cli.clock_calls == [timezone.utc]
    assert len(forecast_cli.calls) == 1
    called_mode, kwargs = forecast_cli.calls[0]
    assert called_mode == mode
    assert kwargs["night_capacities"] is forecast_cli.capacities
    assert kwargs.pop("profile")["active_equipment"] == "setup"

    if mode in {"portfolio", "full"}:
        assert kwargs == {
            "night_capacities": forecast_cli.capacities,
            "productive_hours_per_night": 3.5,
            "observing_nights_per_week": 2.0,
            "night_capacity_source": "profile",
            "historical_nights": 0,
        }
    else:
        assert kwargs == {"night_capacities": forecast_cli.capacities}


def test_tonight_mode_routes_application_result_without_second_forecast(
    monkeypatch,
    forecast_cli,
):
    evaluation_calls = []
    mission = object()
    reference_time = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)
    clock_calls = []

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            clock_calls.append(tz)
            return reference_time

    class ApplicationService:
        def evaluate(self, **kwargs):
            evaluation_calls.append(kwargs)
            return SimpleNamespace(
                forecast_available=True,
                night=forecast_cli.nights[1],
                mission=mission,
            )

    monkeypatch.setattr(
        astro_score,
        "build_durable_tonight_application_service",
        lambda: ApplicationService(),
    )
    monkeypatch.setattr(astro_score, "datetime", FixedDateTime)
    monkeypatch.setattr(
        astro_score,
        "forecast_astro",
        lambda *args, **kwargs: pytest.fail(
            "CLI must delegate tonight forecast to the application service"
        ),
    )

    result = astro_score.main(["--mode", "tonight"])

    assert result == 0
    assert clock_calls == [timezone.utc]
    assert evaluation_calls == [
        {
            "profile": {
                "active_equipment": "setup",
                "location": {
                    "latitude": 46.5,
                    "longitude": 6.6,
                    "name": "Buttes",
                },
                "preferences": {
                    "productive_hours_per_night": 3.5,
                    "observing_nights_per_week": 2.0,
                },
                "sessions": [],
            },
            "weather": {"weather": True},
            "reference_time_utc": reference_time,
            "equipment": None,
            "goal": "balanced",
            "target": astro_score.TARGET,
            "bortle": 3,
        }
    ]
    assert forecast_cli.calls[0] == ("mission", mission)
    called_mode, kwargs = forecast_cli.calls[1]
    assert called_mode == "tonight_completion"
    assert kwargs["night_capacities"] is forecast_cli.capacities
    assert kwargs["profile"]["active_equipment"] == "setup"
