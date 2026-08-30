from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import astro_score
from decision.forecast.forecast_run import ForecastRun


REFERENCE = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def selected_dates(monkeypatch, reference_time_utc, *, row_zone=timezone.utc):
    dates = []
    rows = [{"time": datetime(2026, 8, 30, 18, tzinfo=row_zone)}]
    monkeypatch.setattr(
        astro_score,
        "forecast_engine",
        SimpleNamespace(
            prepare_weather=lambda lat, lon, weather: rows,
            forecast_one_night=lambda **kwargs: (
                dates.append(kwargs["night_date"]) or None
            ),
        ),
    )

    run = astro_score.forecast_astro(
        46.7508,
        6.5495,
        "Buttes",
        3,
        weather={"legacy": True},
        profile={},
        reference_time_utc=reference_time_utc,
    )

    assert isinstance(run, ForecastRun)
    return dates


def test_explicit_reference_time_selects_exactly_seven_dates(monkeypatch):
    dates = selected_dates(monkeypatch, REFERENCE)

    assert dates == [date(2026, 8, 30) + timedelta(days=offset) for offset in range(7)]


def test_same_reference_time_selects_same_dates(monkeypatch):
    first = selected_dates(monkeypatch, REFERENCE)
    second = selected_dates(monkeypatch, REFERENCE)

    assert first == second


def test_reference_time_is_converted_to_forecast_timezone_near_midnight(monkeypatch):
    zurich = ZoneInfo("Europe/Zurich")
    reference = datetime(2026, 8, 30, 22, 30, tzinfo=timezone.utc)

    dates = selected_dates(monkeypatch, reference, row_zone=zurich)

    assert dates[0] == date(2026, 8, 31)


def test_naive_reference_time_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="reference_time_without_timezone"):
        selected_dates(monkeypatch, datetime(2026, 8, 30, 12))


def test_non_datetime_reference_time_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="invalid_reference_time"):
        selected_dates(monkeypatch, "2026-08-30T12:00:00Z")


def test_changing_reference_time_can_advance_first_date(monkeypatch):
    zurich = ZoneInfo("Europe/Zurich")
    before_local_midnight = datetime(2026, 8, 30, 21, 30, tzinfo=timezone.utc)
    after_local_midnight = datetime(2026, 8, 30, 22, 30, tzinfo=timezone.utc)

    before = selected_dates(monkeypatch, before_local_midnight, row_zone=zurich)
    after = selected_dates(monkeypatch, after_local_midnight, row_zone=zurich)

    assert before[0] == date(2026, 8, 30)
    assert after[0] == date(2026, 8, 31)


def test_forecast_date_selection_does_not_read_datetime_now(monkeypatch):
    class NoNowDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("forecast date selection must not read the clock")

    reference = NoNowDateTime(2026, 8, 30, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(astro_score, "datetime", NoNowDateTime)

    dates = selected_dates(monkeypatch, reference)

    assert dates[0] == date(2026, 8, 30)
