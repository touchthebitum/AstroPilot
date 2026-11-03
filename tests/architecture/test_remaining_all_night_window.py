"""All-night requests use the remaining night without weakening productivity."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from copy import deepcopy

import pytest
import astro_score
from astropilot.engines.sky_engine import SkyEngine
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.services.remaining_night_availability import remaining_night_availability
from test_availability_window_preselection import evaluate, window

ZONE = ZoneInfo('Europe/Zurich')
ALL = SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)


def resolve(now, zone=ZONE):
    return remaining_night_availability(ALL, reference_time_utc=now,
        latitude=46.886732, longitude=6.548064, zone=zone)


@pytest.mark.parametrize('now,evening', [
    ('2026-11-02T15:00:00+01:00', '2026-11-02'),
    ('2026-11-02T21:46:07+01:00', '2026-11-02'),
    ('2026-11-03T00:30:00+01:00', '2026-11-02'),
    ('2026-11-03T04:30:00+01:00', '2026-11-02'),
    ('2026-11-03T08:00:00+01:00', '2026-11-03'),
    ('2026-10-25T02:30:00+02:00', '2026-10-24'),
    ('2026-10-25T02:30:00+01:00', '2026-10-24'),
    ('2026-03-29T03:30:00+02:00', '2026-03-28'),
])
def test_bounds_follow_actual_astronomical_night_and_absolute_clock(now, evening):
    instant = datetime.fromisoformat(now)
    dusk, dawn = SkyEngine.astronomical_night_window(
        datetime.fromisoformat(evening).date(), 46.886732, 6.548064, ZONE)
    result = resolve(instant)
    assert result.start.astimezone(timezone.utc) == max(dusk.astimezone(timezone.utc), instant.astimezone(timezone.utc))
    assert result.end == dawn
    assert result.start.astimezone(timezone.utc) < result.end.astimezone(timezone.utc)
    assert resolve(instant.astimezone(ZoneInfo('America/New_York'))) == result
    assert ALL == SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)


@pytest.mark.parametrize('mode', [None, SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
    start=datetime(2026,11,4,20,tzinfo=ZONE),end=datetime(2026,11,4,23,tzinfo=ZONE))])
def test_explicit_future_dates_and_unsupplied_commitment_are_unchanged(mode):
    assert remaining_night_availability(mode,reference_time_utc=None,latitude=None,longitude=None,zone=None) is mode


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError,match='reference_time_without_timezone'):
        resolve(datetime(2026,11,2,21,46))


def test_best_past_window_cannot_beat_future_window(monkeypatch):
    now=datetime(2026,11,2,21,46,7,tzinfo=ZONE)
    result, selected, _ = evaluate(monkeypatch, [
        window(datetime(2026,11,2,19,tzinfo=ZONE),99,0),
        window(datetime(2026,11,2,23,tzinfo=ZONE),80,0)],resolve(now))
    assert selected is not None
    assert selected.window_start == datetime(2026,11,2,23,tzinfo=ZONE)
    assert selected.window_start >= now


def test_partly_elapsed_window_is_clipped_and_minimum_is_not_lowered(monkeypatch):
    windows=[window(datetime(2026,11,2,21,tzinfo=ZONE),99,0)]
    now=datetime(2026,11,2,21,46,7,tzinfo=ZONE)
    _, selected, _=evaluate(monkeypatch,windows,resolve(now))
    assert selected.window_start == now
    assert selected.window_end == datetime(2026,11,2,23,tzinfo=ZONE)
    _, too_short, _=evaluate(monkeypatch,windows,resolve(datetime(2026,11,2,22,15,tzinfo=ZONE)))
    assert too_short is None


def test_no_future_productivity_never_reuses_past_window(monkeypatch):
    _, selected, _=evaluate(monkeypatch,[window(datetime(2026,11,2,19,tzinfo=ZONE),99,0)],
        resolve(datetime(2026,11,2,21,46,tzinfo=ZONE)))
    assert selected is None


@pytest.mark.parametrize('now,evening', [('2026-11-02T21:46:00+01:00','2026-11-02'),
                                        ('2026-11-03T01:30:00+01:00','2026-11-02'),
                                        ('2026-11-03T08:00:00+01:00','2026-11-03')])
def test_forecast_uses_current_evening_and_passes_same_bounds(monkeypatch,now,evening):
    instant=datetime.fromisoformat(now)
    monkeypatch.setattr(astro_score.forecast_engine,'prepare_weather',lambda *a:[{'time':instant}])
    calls=[]
    def forecast(**kwargs):
        calls.append(kwargs)
        return {'evaluation':None,'hours':[], 'target_refusals':{'M42':{'code':'target_window_unavailable'}}}
    monkeypatch.setattr(astro_score.forecast_engine,'forecast_one_night',forecast)
    profile={'projects':{'M42':{'hours':0,'target_hours':15}},'sessions':[]}
    before=deepcopy(profile)
    result=astro_score.forecast_session_astro(46.886732,6.548064,'Buttes',4,profile=profile,
        weather={},reference_time_utc=instant,availability=ALL)
    assert len(calls)==1
    assert str(calls[0]['night_date'])==evening
    assert calls[0]['availability']==resolve(instant)
    assert str(result.nights[0]['date'])==evening
    assert profile==before
