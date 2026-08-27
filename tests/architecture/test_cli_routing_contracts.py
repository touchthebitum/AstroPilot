from types import SimpleNamespace

import pytest

import astro_score


@pytest.fixture
def isolated_cli(monkeypatch):
    monkeypatch.setattr(astro_score, "get_active_equipment", lambda: "setup")
    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: {
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
        lambda value: calls.append(value),
    )
    monkeypatch.setattr(
        astro_score,
        "get_default_location",
        lambda: pytest.fail("location must not be resolved"),
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
    capacities = [
        {"date": "2026-08-27", "hours": 2.0, "quality": 80.0},
    ]
    nights = [
        {"date": "2026-08-28", "score": 70.0},
        {"date": "2026-08-27", "score": 90.0},
    ]

    monkeypatch.setattr(
        astro_score,
        "get_default_location",
        lambda: {"latitude": 46.5, "longitude": 6.6, "name": "Buttes"},
    )
    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda lat, lon: {"weather": True},
    )
    monkeypatch.setattr(
        astro_score,
        "forecast_astro",
        lambda *args, **kwargs: nights,
    )
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
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "tonight_runner",
        SimpleNamespace(
            run=lambda **kwargs: calls.append(("tonight", kwargs)),
        ),
    )

    return SimpleNamespace(calls=calls, capacities=capacities, nights=nights)


@pytest.mark.parametrize("mode", ["portfolio", "calendar", "full"])
def test_report_modes_route_to_exactly_one_runner(mode, forecast_cli):
    result = astro_score.main(["--mode", mode])

    assert result == 0
    assert len(forecast_cli.calls) == 1
    called_mode, kwargs = forecast_cli.calls[0]
    assert called_mode == mode
    assert kwargs["night_capacities"] is forecast_cli.capacities

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


def test_tonight_mode_sorts_nights_by_date_before_routing(forecast_cli):
    result = astro_score.main(["--mode", "tonight"])

    assert result == 0
    assert len(forecast_cli.calls) == 1
    called_mode, kwargs = forecast_cli.calls[0]
    assert called_mode == "tonight"
    assert kwargs["night_capacities"] is forecast_cli.capacities
    assert [night["date"] for night in kwargs["top_nights"]] == [
        "2026-08-27",
        "2026-08-28",
    ]
