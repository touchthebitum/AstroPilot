from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import astro_score
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.night_productivity.night_conditions_provider import NightConditionsProvider
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.services.session_availability_windowing import select_physical_productive_window

ZONE = ZoneInfo('Europe/Zurich')


def stamp(day, hour):
    return datetime(2026, 10, day, hour, tzinfo=ZONE)


def window(start, score, clouds):
    return {'start': start, 'end': start + timedelta(hours=2), 'score': score,
            'clouds': clouds, 'humidity': 70, 'wind': 5, 'seeing': 1.5, 'visibility': 20000,
            'moon_penalty': 0, 'moon_impact': 'low', 'moon_sep': 180,
            'target_altitude': 70, 'sqm': 21,
            'details': [{'moon': 0}, {'moon': 0}],
            'hourly_lunar_evidence': [{'time': start + timedelta(hours=i), 'moon': 0} for i in range(2)]}


class Sky:
    def __init__(self, windows):
        self.windows = windows
        self.limit = 'not called'

    def best_windows(self, **kwargs):
        self.limit = kwargs['limit']
        return self.windows[:self.limit]

    def estimate_seeing(self, wind, humidity):
        return 1.5


def evaluate(monkeypatch, windows, availability):
    # Deterministic geometry only; productivity thresholds and window selection are real.
    monkeypatch.setattr(NightConditionsProvider, 'altitude', lambda hour, context: 70)
    sky = Sky(windows)
    hours = {}
    for item in windows:
        for i in range(2):
            time = item['start'] + timedelta(hours=i)
            hours[time] = {'time': time, 'cloud_cover': item['clouds'],
                          'relative_humidity_2m': 70, 'wind_speed_10m': 5,
                          'temperature_2m': 12, 'visibility': 20000}
    profile = {'active_equipment': 'samyang_183', 'available_equipment': ['samyang_183'],
               'preferences': {'bortle': 4},
               'projects': {'Sh2-129': {'hours': 0, 'target_hours': 12, 'imaging_field_id': 'sh2-129_ou4',
                  'acquisition_intent_targets': [{'acquisition_intent_id': intent, 'target_hours': 6}
                     for intent in ('sh2-129_ha', 'ou4_oiii')],
                  'acquisition_intent_progress': [{'acquisition_intent_id': intent, 'acquired_duration_manual': 0}
                     for intent in ('sh2-129_ha', 'ou4_oiii')]}}}
    original = deepcopy(profile)
    result = astro_score.evaluate_object('Sh2-129', sky, list(hours.values()), 0,
        SimpleNamespace(name='Synthetic site', observer=object()), 46.9, 6.5, 4,
        'deep_sky', profile, availability=availability)
    assert profile == original
    if result is None:
        return result, None, sky
    value = astro_score.build_mission_input(result, profile=profile, for_intent_selection=True)
    assessment = ProductiveWindowAssessment.build(target='Sh2-129',
        context=result['decision_context'], mission_input=value)
    return result, select_physical_productive_window(assessment, availability), sky


def test_after_midnight_availability_excludes_higher_ranked_evening(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
        start=stamp(16, 2), end=stamp(16, 4))
    result, physical, sky = evaluate(monkeypatch,
        [window(stamp(15, 21), 99, 0), window(stamp(16, 2), 80, 0)], availability)
    assert sky.limit is None
    assert result['window']['start'] == stamp(16, 2)
    assert physical.window_start == availability.start
    assert physical.window_end == availability.end


def test_productive_window_beyond_top_three_is_not_discarded(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)
    windows = [window(stamp(15, hour), score, 100) for hour, score in [(18, 99), (20, 98), (22, 97)]]
    windows.append(window(stamp(16, 2), 75, 0))
    result, physical, sky = evaluate(monkeypatch, windows, availability)
    assert sky.limit is None
    assert result['window']['start'] == stamp(16, 2)
    assert physical.window_start == stamp(16, 2)


@pytest.mark.parametrize('availability', [
    SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW, start=stamp(16, 2), end=stamp(16, 4)),
    SessionAvailability(SessionAvailabilityMode.START_AND_DURATION, start=stamp(16, 2), duration=timedelta(minutes=90)),
    SessionAvailability(SessionAvailabilityMode.UNTIL, end=stamp(16, 4)),
    SessionAvailability(SessionAvailabilityMode.DURATION, duration=timedelta(hours=2)),
])
def test_all_dated_and_duration_bounds_use_normal_physical_guards(monkeypatch, availability):
    result, physical, _ = evaluate(monkeypatch,
        [window(stamp(16, 0), 95, 100), window(stamp(16, 2), 80, 0)], availability)
    assert result['window']['start'] == stamp(16, 2)
    assert physical is not None
    if availability.start is not None:
        assert physical.window_start >= availability.start
    if availability.end is not None:
        assert physical.window_end <= availability.end
    if availability.duration is not None:
        assert physical.window_end - physical.window_start <= availability.duration


def test_short_availability_is_not_promoted_to_one_hour(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.START_AND_DURATION,
        start=stamp(16, 2), duration=timedelta(minutes=45))
    result, physical, _ = evaluate(monkeypatch, [window(stamp(16, 2), 95, 0)], availability)
    assert result is not None
    assert physical is None


def test_bad_weather_remains_refused(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
        start=stamp(16, 2), end=stamp(16, 4))
    result, physical, _ = evaluate(monkeypatch, [window(stamp(16, 2), 99, 100)], availability)
    assert result is not None
    assert physical is None


def test_no_overlap_does_not_fall_back_to_evening(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
        start=stamp(16, 2), end=stamp(16, 4))
    result, physical, _ = evaluate(monkeypatch, [window(stamp(15, 21), 99, 0)], availability)
    assert result is None and physical is None


def test_ambiguous_duration_ranking_is_not_silently_authorized(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.DURATION, duration=timedelta(hours=1))
    with pytest.raises(ValueError, match='ambiguous_best_duration_window'):
        evaluate(monkeypatch, [window(stamp(16, 2), 95, 0)], availability)
