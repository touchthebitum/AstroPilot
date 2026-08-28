from types import SimpleNamespace

import pytest

import astro_score


@pytest.fixture
def isolated_cli_failures(monkeypatch):
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
            "preferences": {},
            "sessions": [],
        },
    )
    monkeypatch.setattr(
        astro_score,
        "save_user_profile",
        lambda profile: pytest.fail("profile must not be saved"),
    )
    monkeypatch.setattr(
        astro_score,
        "FilterTargetConfigurationService",
        lambda **kwargs: object(),
    )


@pytest.mark.parametrize("weather", [None, {"weather": True}])
def test_missing_forecast_stops_before_capacity_and_runners(
    monkeypatch,
    capsys,
    isolated_cli_failures,
    weather,
):
    forecast_calls = []
    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda lat, lon: weather,
    )

    def forecast(*args, **kwargs):
        forecast_calls.append(kwargs)
        return None

    monkeypatch.setattr(astro_score, "forecast_astro", forecast)
    monkeypatch.setattr(
        astro_score,
        "forecast_night_capacities",
        lambda *args, **kwargs: pytest.fail("capacity must not be computed"),
    )
    monkeypatch.setattr(
        astro_score,
        "report_runner",
        SimpleNamespace(
            run_portfolio=lambda **kwargs: pytest.fail("runner must not run"),
            run_calendar=lambda **kwargs: pytest.fail("runner must not run"),
            run_full=lambda **kwargs: pytest.fail("runner must not run"),
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "tonight_runner",
        SimpleNamespace(
            run=lambda **kwargs: pytest.fail("runner must not run"),
        ),
    )

    result = astro_score.main(["--mode", "tonight"])
    output = capsys.readouterr().out

    assert result == 0
    assert len(forecast_calls) == 1
    assert forecast_calls[0]["weather"] is weather
    assert "ERREUR: forecast_astro a retourné None" in output
    if weather is None:
        assert "Prévisions météo indisponibles." in output
    else:
        assert "Prévisions météo indisponibles." not in output


def test_empty_night_list_keeps_capacity_report_but_skips_tonight_runner(
    monkeypatch,
    capsys,
    isolated_cli_failures,
):
    capacities = [
        {"date": "2026-08-27", "hours": 1.5, "quality": 75.0},
    ]
    capacity_calls = []
    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda lat, lon: {"weather": True},
    )
    monkeypatch.setattr(
        astro_score,
        "forecast_astro",
        lambda *args, **kwargs: [],
    )

    def forecast_capacities(lat, lon, *, weather):
        capacity_calls.append((lat, lon, weather))
        return capacities

    monkeypatch.setattr(
        astro_score,
        "forecast_night_capacities",
        forecast_capacities,
    )
    monkeypatch.setattr(
        astro_score.HistoricalNightCapacityEstimator,
        "estimate",
        lambda **kwargs: SimpleNamespace(
            productive_hours_per_night=4.0,
            source="profile",
            historical_nights=0,
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "tonight_runner",
        SimpleNamespace(
            run=lambda **kwargs: pytest.fail("tonight runner must not run"),
        ),
    )

    result = astro_score.main(["--mode", "tonight"])
    output = capsys.readouterr().out

    assert result == 0
    assert capacity_calls == [(46.5, 6.6, {"weather": True})]
    assert "===== CAPACITÉ À VENIR =====" in output
    assert "2026-08-27 : 1.5 h qualité=75" in output
    assert "Total prévisionnel : 1.5 h" in output


def test_invalid_filter_target_name_fails_before_profile_write():
    with pytest.raises(ValueError, match="Invalid filter target"):
        astro_score.parse_filter_target_assignments([" =5"])


def test_duplicate_filter_target_uses_last_cli_value():
    assert astro_score.parse_filter_target_assignments(
        ["Ha=5", "Ha=6.5"],
    ) == {"Ha": 6.5}
