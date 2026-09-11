import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import astro_score
from astropilot.app import create_app
from decision.forecast.forecast_run import ForecastRun
from decision.weather.weather_ingress import WeatherSnapshot


WEATHER_REFERENCE_TIME = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)


def valid_weather_snapshot():
    return WeatherSnapshot(
        payload={"hourly": {}},
        provider="Open-Meteo",
        retrieved_at_utc=WEATHER_REFERENCE_TIME - timedelta(minutes=5),
        requested_latitude=47.12,
        requested_longitude=7.04,
        grid_latitude=47.12,
        grid_longitude=7.04,
        grid_distance_km=0.0,
        elevation_m=1000.0,
        timezone="Europe/Zurich",
        timezone_source="coordinates_local",
        utc_offset_seconds=7200,
        valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 9, 3, tzinfo=timezone.utc),
        hour_count=48,
        completeness=1.0,
    )


def profile():
    return {
        "location": {"name": "Mont Sujet", "latitude": 47.12, "longitude": 7.04},
        "preferences": {"bortle": 6},
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183", "fra400_2600"],
        "projects": {},
    }


@pytest.mark.parametrize("entry", ["http", "cli"])
@pytest.mark.parametrize("weather_raises", [False, True])
@pytest.mark.parametrize(
    "case, equipment_error",
    [
        ("missing_location", False),
        ("invalid_location", False),
        ("missing_bortle", False),
        ("invalid_bortle", False),
        ("unknown_override", True),
        ("unavailable_override", True),
        ("invalid_active", True),
        ("unavailable_active", True),
    ],
)
def test_invalid_local_input_stops_before_weather_and_durable_service(
    monkeypatch, capsys, entry, weather_raises, case, equipment_error
):
    persisted = profile()
    equipment = None
    if case == "missing_location":
        persisted.pop("location")
    elif case == "invalid_location":
        persisted["location"]["latitude"] = 100
    elif case == "missing_bortle":
        persisted["preferences"].pop("bortle")
    elif case == "invalid_bortle":
        persisted["preferences"]["bortle"] = True
    elif case == "unknown_override":
        equipment = "not_a_setup"
    elif case == "unavailable_override":
        equipment = "hyperstar_c8"
    elif case == "invalid_active":
        persisted["active_equipment"] = "not_a_setup"
    else:
        persisted["available_equipment"] = ["fra400_2600"]
    before = deepcopy(persisted)
    weather = Mock(side_effect=RuntimeError("weather failed") if weather_raises else None)
    durable_factory = Mock(side_effect=AssertionError("decision persistence reached"))
    save = Mock(side_effect=AssertionError("profile write reached"))
    monkeypatch.setattr(astro_score, "save_user_profile", save)

    if entry == "http":
        client = TestClient(create_app(
            profile_provider=lambda: persisted,
            weather_provider=weather,
            service_factory=durable_factory,
        ))
        response = client.post(
            "/v1/tonight", json={} if equipment is None else {"equipment": equipment}
        )
        if equipment_error:
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "invalid_tonight_equipment"
        else:
            assert response.status_code == 503
            assert response.json()["error"] == "user_profile_unavailable"
    else:
        monkeypatch.setattr(astro_score, "load_user_profile", lambda: persisted)
        monkeypatch.setattr(astro_score, "fetch_weather", weather)
        monkeypatch.setattr(astro_score, "build_durable_tonight_application_service", durable_factory)
        arguments = ["--mode", "tonight"]
        if equipment is not None:
            arguments += ["--equipment", equipment]
        with pytest.raises(SystemExit) as caught:
            astro_score.main(arguments)
        assert caught.value.code == 2
        error = capsys.readouterr().err
        if equipment_error:
            assert error == (
                "Erreur matériel : le setup demandé est inconnu ou indisponible.\n"
            )
        else:
            assert "Erreur profil utilisateur" in error

    weather.assert_not_called()
    durable_factory.assert_not_called()
    save.assert_not_called()
    assert persisted == before


@pytest.mark.parametrize(
    "overrides, missing",
    [
        ({}, None),
        ({"location": {"name": "Other site", "latitude": 45.0, "longitude": 8.0}}, None),
        ({"bortle": 2}, None),
        ({"equipment": "fra400_2600"}, None),
        ({"location": {"name": "Other site", "latitude": 45.0, "longitude": 8.0}}, "location"),
        ({"bortle": 2}, "bortle"),
    ],
)
def test_http_resolves_effective_values_without_mutating_profile(monkeypatch, overrides, missing):
    persisted = profile()
    if missing == "location":
        persisted.pop("location")
    elif missing == "bortle":
        persisted["preferences"].pop("bortle")
    before = deepcopy(persisted)
    weather_value = valid_weather_snapshot()
    weather = Mock(return_value=weather_value)
    forecast = Mock(return_value=ForecastRun(nights=(), evidence=None))
    monkeypatch.setattr(astro_score, "forecast_astro", forecast)
    client = TestClient(create_app(
        profile_provider=lambda: persisted,
        weather_provider=weather,
        clock=lambda: WEATHER_REFERENCE_TIME,
    ))

    response = client.post("/v1/tonight", json=overrides)

    assert response.status_code == 200
    assert response.json()["status"] == "no_night"
    location = overrides.get("location", before.get("location"))
    bortle = overrides.get("bortle", before["preferences"].get("bortle"))
    equipment = overrides.get("equipment", before["active_equipment"])
    weather.assert_called_once_with(location["latitude"], location["longitude"])
    assert forecast.call_args.args == (location["latitude"], location["longitude"], location["name"], bortle)
    effective = forecast.call_args.kwargs["profile"]
    assert effective["active_equipment"] == equipment
    assert effective["available_equipment"] == [equipment]
    assert effective["projects"] == {}
    assert persisted == before


@pytest.mark.parametrize("equipment", [None, "fra400_2600"])
def test_cli_resolves_persisted_inputs_without_mutation(monkeypatch, equipment):
    persisted = profile()
    before = deepcopy(persisted)
    weather = Mock(return_value=object())
    forecast = Mock(return_value=ForecastRun(nights=(), evidence=None))
    monkeypatch.setattr(astro_score, "load_user_profile", lambda: persisted)
    monkeypatch.setattr(astro_score, "fetch_weather", weather)
    monkeypatch.setattr(astro_score, "forecast_astro", forecast)
    monkeypatch.setattr(astro_score, "forecast_night_capacities", lambda *args, **kwargs: [])
    arguments = ["--mode", "tonight"]
    if equipment is not None:
        arguments += ["--equipment", equipment]

    assert astro_score.main(arguments) == 0

    weather.assert_called_once_with(47.12, 7.04)
    assert forecast.call_args.args == (47.12, 7.04, "Mont Sujet", 6)
    assert forecast.call_args.kwargs["profile"]["available_equipment"] == [equipment or "samyang_183"]
    assert persisted == before


@pytest.mark.parametrize("entry", ["http", "cli"])
@pytest.mark.parametrize("missing", ["location", "bortle"])
def test_production_loader_missing_configuration_never_reaches_weather(
    monkeypatch, tmp_path, entry, missing
):
    persisted = profile()
    if missing == "location":
        persisted.pop("location")
    else:
        persisted["preferences"].pop("bortle")
    path = tmp_path / "user_profile.json"
    path.write_text(json.dumps(persisted), encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    weather = Mock(side_effect=RuntimeError("weather must not run"))
    factory = Mock(side_effect=AssertionError("persistence must not run"))
    monkeypatch.setattr(astro_score, "fetch_weather", weather)
    monkeypatch.setattr(astro_score, "build_durable_tonight_application_service", factory)

    if entry == "http":
        response = TestClient(create_app()).post("/v1/tonight", json={})
        assert response.status_code == 503
        assert response.json()["error"] == "user_profile_unavailable"
    else:
        with pytest.raises(SystemExit) as caught:
            astro_score.main(["--mode", "tonight"])
        assert caught.value.code == 2

    weather.assert_not_called()
    factory.assert_not_called()
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
