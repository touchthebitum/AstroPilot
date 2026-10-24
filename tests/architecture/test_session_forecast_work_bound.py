"""A one-session request must not evaluate six additional unused evenings."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from copy import deepcopy
import pytest
import astro_score
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode

REF = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)


def engine_stub(monkeypatch, missing=()):
    calls = []
    monkeypatch.setattr(astro_score.forecast_engine, 'prepare_weather',
        lambda *args: [{'time': REF}])
    def one_night(**kwargs):
        day = kwargs['night_date']; calls.append(day)
        if day in missing:
            return None
        return {'evaluation': object(), 'date': day, 'weather': 'unfavourable'}
    monkeypatch.setattr(astro_score.forecast_engine, 'forecast_one_night', one_night)
    monkeypatch.setattr(astro_score.portfolio_engine, 'enrich', lambda **kwargs: kwargs['night_evaluation'])
    monkeypatch.setattr(astro_score, 'build_forecast_result', lambda **kwargs:
        {'date': kwargs['night_date'], 'weather': kwargs['night_context']['weather']})
    return calls


def run(function, **kwargs):
    return function(46.888, 6.55, 'Synthetic', 4, profile={'projects': {}},
        weather={}, reference_time_utc=REF, **kwargs)


def test_session_stops_after_same_first_result_even_in_bad_weather(monkeypatch):
    calls = engine_stub(monkeypatch)
    full = run(astro_score.forecast_astro)
    assert len(full.nights) == len(calls) == 7
    calls.clear()
    session = run(astro_score.forecast_session_astro)
    assert session.nights == full.nights[:1]
    assert session.evidence == full.evidence
    assert calls == [REF.date()]


def test_session_retains_earliest_existing_evening_if_first_is_absent(monkeypatch):
    calls = engine_stub(monkeypatch, missing={REF.date()})
    full = run(astro_score.forecast_astro)
    calls.clear()
    session = run(astro_score.forecast_session_astro)
    assert session.nights == full.nights[:1]
    assert calls == [REF.date(), REF.date() + timedelta(days=1)]


@pytest.mark.parametrize('offset', [0, 1, 6, 7])
def test_dated_session_never_changes_to_a_different_evening(monkeypatch, offset):
    calls = engine_stub(monkeypatch)
    start = REF + timedelta(days=offset, hours=2)
    availability = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
        start=start, end=start + timedelta(hours=2))
    full = run(astro_score.forecast_astro, availability=availability)
    calls.clear()
    session = run(astro_score.forecast_session_astro, availability=availability)
    assert session.nights == full.nights
    assert calls == ([start.date()] if offset < 7 else [])


def test_no_evening_remains_no_result(monkeypatch):
    calls = engine_stub(monkeypatch, missing={REF.date() + timedelta(days=d) for d in range(7)})
    assert run(astro_score.forecast_session_astro).nights == ()
    assert len(calls) == 7


def test_selected_project_does_not_mutate_forecast_input(monkeypatch):
    engine_stub(monkeypatch)
    profile = {'projects': {'IC1848': {'hours': 0, 'target_hours': 10}}, 'sessions': []}
    before = deepcopy(profile)
    astro_score.forecast_session_astro(46.888, 6.55, 'Synthetic', 4, profile=profile,
        weather={}, reference_time_utc=REF)
    assert profile == before
