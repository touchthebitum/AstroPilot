from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import astro_score
from decision.forecast.forecast_run import ForecastRun
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.weather_ingress import WeatherSnapshot


NOW = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)


def snapshot():
    return WeatherSnapshot(
        payload={"hourly": {}},
        provider="Open-Meteo",
        retrieved_at_utc=NOW,
        requested_latitude=46.7508,
        requested_longitude=6.5495,
        grid_latitude=46.75,
        grid_longitude=6.55,
        grid_distance_km=0.1,
        elevation_m=1_245.0,
        timezone="Europe/Zurich",
        timezone_source="coordinates_local",
        utc_offset_seconds=7200,
        valid_from=NOW,
        valid_until=NOW + timedelta(days=1),
        hour_count=25,
        completeness=1.0,
    )


def test_forecast_astro_builds_evidence_once_from_same_snapshot_and_rows(monkeypatch):
    weather = snapshot()
    rows = [{"time": NOW + timedelta(hours=1)}]
    evidence = DecisionForecastEvidence(())
    prepare_calls = []
    forecast_rows = []
    evidence_calls = []

    monkeypatch.setattr(
        astro_score,
        "forecast_engine",
        SimpleNamespace(
            prepare_weather=lambda lat, lon, source: (
                prepare_calls.append((lat, lon, source)) or rows
            ),
            forecast_one_night=lambda **kwargs: (
                forecast_rows.append(kwargs["rows"]) or None
            ),
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "build_decision_forecast_evidence",
        lambda source, prepared_rows: (
            evidence_calls.append((source, prepared_rows)) or evidence
        ),
    )

    run = astro_score.forecast_astro(
        46.7508,
        6.5495,
        "Buttes",
        3,
        weather=weather,
        profile={},
    )

    assert isinstance(run, ForecastRun)
    assert run.nights == ()
    assert run.evidence is evidence
    assert prepare_calls == [(46.7508, 6.5495, weather)]
    assert evidence_calls == [(weather, rows)]
    assert len(forecast_rows) == 7
    assert all(candidate is rows for candidate in forecast_rows)


def test_forecast_astro_preserves_legacy_non_snapshot_without_false_evidence(
    monkeypatch,
):
    rows = [{"time": NOW + timedelta(hours=1)}]
    monkeypatch.setattr(
        astro_score,
        "forecast_engine",
        SimpleNamespace(
            prepare_weather=lambda lat, lon, source: rows,
            forecast_one_night=lambda **kwargs: None,
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "build_decision_forecast_evidence",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("legacy payload must not create false evidence")
        ),
    )

    run = astro_score.forecast_astro(
        46.7508,
        6.5495,
        "Buttes",
        3,
        weather={"legacy": True},
        profile={},
    )

    assert run == ForecastRun(nights=(), evidence=None)


def test_forecast_astro_preserves_empty_evidence_for_valid_snapshot(monkeypatch):
    weather = snapshot()
    rows = []
    evidence = DecisionForecastEvidence(())
    evidence_calls = []

    monkeypatch.setattr(
        astro_score,
        "forecast_engine",
        SimpleNamespace(
            prepare_weather=lambda lat, lon, source: rows,
            forecast_one_night=lambda **kwargs: None,
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "build_decision_forecast_evidence",
        lambda source, prepared_rows: (
            evidence_calls.append((source, prepared_rows)) or evidence
        ),
    )

    run = astro_score.forecast_astro(
        46.7508,
        6.5495,
        "Buttes",
        3,
        weather=weather,
        profile={},
    )

    assert evidence_calls == [(weather, rows)]
    assert run.nights == ()
    assert run.evidence is evidence
    assert run.evidence is not None
    assert run.evidence.forecast_points == ()
