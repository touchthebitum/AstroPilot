"""Observe the committed engine in an isolated process; never confirm a mission."""
import csv
import dataclasses
import datetime as dt
import enum
import json
import os
from pathlib import Path
import sys
import time
import traceback
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
INTENTS = ('sh2-129_ha', 'ou4_oiii')


def encode(value):
    if dataclasses.is_dataclass(value):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    if hasattr(value, 'slices'):
        return {'slices': encode(value.slices)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def save(root, name, value):
    (root / name).write_text(json.dumps(encode(value), indent=2, ensure_ascii=False), encoding='utf-8')


def observe(client, availability):
    """The only endpoint this diagnostic may call."""
    return client.post('/v1/tonight', json={'availability': availability})


def run(root, first_night, weather_override=None):
    root = Path(root).resolve()
    if Path(os.environ['ASTROPILOT_DATA_DIR']).resolve() != root / 'data':
        raise RuntimeError('Diagnostic data must be the isolated working-directory/data copy.')
    import astro_score
    import astropilot.app as app
    from fastapi.testclient import TestClient
    import decision.services.acquisition_intent_eligibility as eligibility
    import decision.services.acquisition_intent_composition as composition
    from decision.night_productivity.night_timeline_builder import NightTimelineBuilder
    from decision.night_productivity.productivity_diagnostics import PRODUCTIVE_SLICE_THRESHOLD
    from decision.services.session_availability_windowing import MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW

    profile = json.loads((root / 'data/user_profile.json').read_text(encoding='utf-8'))
    attempts = []
    weather = weather_override
    original_get = astro_score.requests.get

    def captured_get(*args, **kwargs):
        item = {'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
        attempts.append(item)
        started = time.monotonic()
        try:
            response = original_get(*args, **kwargs)
            item.update(http=response.status_code,
                        retry_after=response.headers.get('Retry-After'),
                        response_excerpt=response.text[:1000] if response.status_code != 200 else None)
            return response
        except Exception as exc:
            item.update(error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            item['seconds'] = time.monotonic() - started

    if weather is None:
        astro_score.requests.get = captured_get
        try:
            for attempt in range(3):
                try:
                    weather = astro_score.fetch_weather(profile['location']['latitude'], profile['location']['longitude'])
                except Exception as exc:
                    attempts.append({'validation_error': str(exc), 'error_type': type(exc).__name__})
                save(root, 'weather-attempts.json', attempts)
                if weather is not None:
                    break
                if attempt < 2:
                    time.sleep(5)
        finally:
            astro_score.requests.get = original_get
    if weather is None:
        result = {'status': 'WEATHER_UNAVAILABLE', 'attempts': attempts, 'suggestions': [],
                  'no_confirmation_sent': True, 'thresholds_unchanged': True}
        save(root, 'diagnostic.json', result)
        return result

    save(root, 'forecast-snapshot.json', weather)
    save(root, 'forecast-raw.json', weather.payload)
    tz = ZoneInfo(weather.timezone)
    hourly = weather.payload['hourly']
    names = ['time', *[name for name in hourly if name != 'time']]
    with (root / 'forecast-hourly.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['time_local', 'time_utc', *names[1:]])
        for index, value in enumerate(hourly['time']):
            instant = dt.datetime.fromtimestamp(value, dt.timezone.utc) if isinstance(value, (int, float)) else dt.datetime.fromisoformat(value)
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=tz)
            writer.writerow([instant.astimezone(tz).isoformat(), instant.astimezone(dt.timezone.utc).isoformat(),
                             *[hourly[name][index] for name in names[1:]]])

    records, timelines, cases, slices = [], [], [], []
    active_intent = None
    original_eligibility = eligibility.evaluate_acquisition_intent_eligibility
    original_window = eligibility.evaluate_physical_productive_window
    original_timeline = NightTimelineBuilder.build_with_evaluations

    def capture_eligibility(**kwargs):
        nonlocal active_intent
        previous = active_intent
        active_intent = kwargs['acquisition_intent'].acquisition_intent_id
        try:
            return original_eligibility(**kwargs)
        finally:
            active_intent = previous

    def capture_window(assessment, availability):
        result = original_window(assessment, availability)
        records.append({'intent': active_intent, 'assessment': encode(assessment),
                        'availability': encode(availability), 'selection': encode(result)})
        return result

    def capture_timeline(context):
        result = original_timeline(context)
        timeline, evaluations = result
        anchor = context.observation_time
        rows = []
        for item, evaluation in zip(timeline.slices, evaluations):
            begin = (anchor.astimezone(dt.timezone.utc) + dt.timedelta(hours=item.start_hour)).astimezone(tz)
            end = (anchor.astimezone(dt.timezone.utc) + dt.timedelta(hours=item.end_hour)).astimezone(tz)
            row = {'start_local': begin.isoformat(), 'end_local': end.isoformat(),
                   'score': evaluation.score, 'threshold': PRODUCTIVE_SLICE_THRESHOLD,
                   'productive': evaluation.score >= PRODUCTIVE_SLICE_THRESHOLD,
                   'cloud_cover': item.cloud_cover, 'humidity': item.humidity,
                   'wind_kmh': item.wind, 'target_altitude': item.target_altitude,
                   'moon_penalty': item.moon_penalty, **{'loss_' + k: v for k, v in encode(evaluation.losses).items()}}
            rows.append(row)
        timelines.append({'context': encode(context), 'slices': rows})
        return result

    eligibility.evaluate_acquisition_intent_eligibility = capture_eligibility
    composition.evaluate_acquisition_intent_eligibility = capture_eligibility
    eligibility.evaluate_physical_productive_window = capture_window
    NightTimelineBuilder.build_with_evaluations = staticmethod(capture_timeline)
    candidates, candidate_keys = [], set()
    now = dt.datetime.now(tz)
    first = max(dt.date.fromisoformat(first_night), now.date())

    def evaluate(client, start, end, label):
        records.clear()
        timelines.clear()
        availability = {'mode': 'fixed_window', 'start_local': start.replace(tzinfo=None).isoformat(timespec='minutes'),
                        'end_local': end.replace(tzinfo=None).isoformat(timespec='minutes')}
        began = time.monotonic()
        response = observe(client, availability)
        case = {'index': len(cases), 'label': label, 'availability': availability,
                'http': response.status_code, 'seconds': time.monotonic() - began,
                'body': response.json(), 'intent_diagnostics': list(records), 'timelines': list(timelines)}
        cases.append(case)
        save(root, 'cases.json', cases)
        for timeline_index, timeline in enumerate(timelines):
            for row in timeline['slices']:
                slices.append({'case': case['index'], 'label': label, 'timeline': timeline_index, **row})
        offered = set(case['body'].get('viable_acquisition_intent_ids', []))
        expected = (start.date() - dt.timedelta(days=1) if start.hour < 12 else start.date()).isoformat()
        case['both_offered'] = (response.status_code == 200 and set(INTENTS).issubset(offered)
                                and case['body'].get('night_date') == expected
                                and case['body'].get('acquisition_intent_choice_available') is True)
        print(label, availability, 'HTTP', response.status_code, 'both offered', case['both_offered'], flush=True)
        return case

    try:
        # Actual clock and standard freshness validation remain active. Only the provider
        # returns the one just-acquired snapshot for comparable, reproducible calculations.
        with TestClient(app.create_app(weather_provider=lambda *args: weather)) as client:
            baseline_start = dt.datetime.combine(first + dt.timedelta(days=1), dt.time(2, 45), tzinfo=tz)
            if baseline_start > now and baseline_start + dt.timedelta(minutes=90) <= weather.valid_until:
                evaluate(client, baseline_start, baseline_start + dt.timedelta(minutes=90), 'previous-test-window')
            for offset in range(7):
                day = first + dt.timedelta(days=offset)
                start = dt.datetime.combine(day, dt.time(18), tzinfo=tz)
                end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(9), tzinfo=tz)
                if end > weather.valid_until or end <= now:
                    continue
                start = max(start, now + dt.timedelta(minutes=5)).replace(second=0, microsecond=0)
                case = evaluate(client, start, end, 'full-night-' + day.isoformat())
                # Derive proposals from the engine's real, unchanged quarter-hour scores.
                # A proposal is never reported testable until a second API preparation offers both.
                for timeline in case['timelines']:
                    block = []
                    for row in [*timeline['slices'], {'productive': False}]:
                        if row['productive']:
                            block.append(row)
                            continue
                        if len(block) >= 4:
                            block_start = dt.datetime.fromisoformat(block[0]['start_local'])
                            block_end = dt.datetime.fromisoformat(block[-1]['end_local'])
                            for begin, finish in [(block_start, block_end), (block_start, block_start + dt.timedelta(hours=1))]:
                                begin = max(start, begin - dt.timedelta(minutes=15))
                                finish = min(end, finish + dt.timedelta(minutes=15))
                                key = (begin.isoformat(), finish.isoformat())
                                if key not in candidate_keys:
                                    candidate_keys.add(key)
                                    candidates.append((begin, finish))
                        block = []
            for start, end in candidates[:24]:
                evaluate(client, start, end, 'candidate-window')
    finally:
        eligibility.evaluate_acquisition_intent_eligibility = original_eligibility
        composition.evaluate_acquisition_intent_eligibility = original_eligibility
        eligibility.evaluate_physical_productive_window = original_window
        NightTimelineBuilder.build_with_evaluations = staticmethod(original_timeline)

    save(root, 'cases.json', cases)
    if slices:
        with (root / 'slice-scores.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(slices[0]))
            writer.writeheader()
            writer.writerows(slices)
    suggestions = [{'availability': c['availability'], 'night_date': c['body']['night_date'],
                    'case': c['index'], 'label': c['label']} for c in cases if c['both_offered']]
    suggestions.sort(key=lambda item: (item['night_date'], item['label'].startswith('full-night'),
        dt.datetime.fromisoformat(item['availability']['end_local']) - dt.datetime.fromisoformat(item['availability']['start_local']),
        item['availability']['start_local']))
    result = {'status': 'TESTABLE_WINDOW_FOUND' if suggestions else 'NO_TESTABLE_WINDOW',
              'suggestions': suggestions, 'cases': len(cases), 'candidate_windows_considered': len(candidates),
              'candidate_search_limit': 24, 'search_is_exhaustive': False,
              'forecast_retrieved_at_utc': weather.retrieved_at_utc.isoformat(),
              'threshold': PRODUCTIVE_SLICE_THRESHOLD,
              'minimum_continuous_minutes': MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW.total_seconds() / 60,
              'thresholds_unchanged': True, 'no_confirmation_sent': True,
              'source_sha': 'a29513447355b05cbcceda85a10d6dc1f90da3fb',
              'snapshot_scope': 'one freshly acquired snapshot; real current clock; no historical freshness bypass'}
    save(root, 'diagnostic.json', result)
    summary = ['Diagnostic Hα/OIII : ' + result['status'],
               'Scores : seuil inchangé 0,70 ; durée continue minimale inchangée 60 minutes.',
               'Aucune mission confirmée. Une proposition doit être retestée avec le binaire et la météo actuelle.',
               'La recherche est bornée, sans garantie d’exhaustivité.']
    for item in suggestions[:5]:
        summary.append('Nuit ' + item['night_date'] + ' : ' + item['availability']['start_local'] + ' à ' + item['availability']['end_local'])
    (root / 'Resume.txt').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    root = Path.cwd().resolve()
    with (root / 'worker.log').open('w', encoding='utf-8') as log:
        sys.stdout = sys.stderr = log
        try:
            run(root, sys.argv[1])
        except BaseException as exc:
            save(root, 'diagnostic.json', {'status': 'ERROR', 'error': type(exc).__name__ + ': ' + str(exc),
                                         'no_confirmation_sent': True})
            traceback.print_exc()
            raise
