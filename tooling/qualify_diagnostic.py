"""Run the actual diagnostic engine on synthetic evidence, never on a user profile."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from diagnostic_worker import run
from decision.weather.weather_ingress import validate_weather_payload, REQUIRED_HOURLY_UNITS

root = Path(sys.argv[1]).resolve()
root.mkdir(exist_ok=False)
now = dt.datetime.now(dt.timezone.utc)
tz = ZoneInfo('Europe/Zurich')
start = dt.datetime.combine(now.astimezone(tz).date(), dt.time(), tzinfo=tz)
timestamps = [int((start.astimezone(dt.timezone.utc) + dt.timedelta(hours=i)).timestamp()) for i in range(168)]
profile = {'location': {'name': 'Synthetic diagnostic site', 'latitude': 46.9, 'longitude': 6.5},
           'preferences': {'bortle': 4}, 'active_equipment': 'samyang_183',
           'available_equipment': ['samyang_183'], 'profile_revision': 1, 'sessions': [],
           'projects': {'Sh2-129': {'hours': 0, 'target_hours': 12, 'imaging_field_id': 'sh2-129_ou4',
             'acquisition_intent_targets': [{'acquisition_intent_id': intent, 'target_hours': 6}
                                            for intent in ('sh2-129_ha', 'ou4_oiii')],
             'acquisition_intent_progress': [{'acquisition_intent_id': intent, 'acquired_duration_manual': 0}
                                             for intent in ('sh2-129_ha', 'ou4_oiii')]}}}
findings = []
for scenario, clouds in [('clear', 0), ('cloudy', 100)]:
    work = root / scenario
    work.mkdir()
    (work / 'data').mkdir()
    (work / 'data/user_profile.json').write_text(json.dumps(profile), encoding='utf-8')
    os.environ['ASTROPILOT_DATA_DIR'] = str(work / 'data')
    os.environ['ASTROPILOT_GUARDIAN_EXPLICIT_RENEWAL'] = '0'
    hourly = {'time': timestamps}
    values = {'cloud_cover': clouds, 'cloud_cover_low': clouds, 'cloud_cover_mid': 0,
              'cloud_cover_high': 0, 'precipitation': 0, 'relative_humidity_2m': 50,
              'visibility': 20000, 'wind_speed_10m': 5, 'temperature_2m': 12}
    hourly.update({k: [v] * 168 for k, v in values.items()})
    payload = {'latitude': 46.9, 'longitude': 6.5, 'timezone': 'Europe/Zurich',
               'utc_offset_seconds': int(start.utcoffset().total_seconds()), 'elevation': 790,
               'hourly': hourly, 'hourly_units': {'time': 'unixtime', **REQUIRED_HOURLY_UNITS}}
    weather = validate_weather_payload(payload, requested_latitude=46.9, requested_longitude=6.5,
                                       requested_timezone='Europe/Zurich', retrieved_at_utc=now)
    result = run(work, start.date().isoformat(), weather_override=weather)
    assert result['threshold'] == .70 and result['minimum_continuous_minutes'] == 60
    assert result['no_confirmation_sent'] and result['thresholds_unchanged']
    assert (work / 'forecast-hourly.csv').exists()
    if scenario == 'clear':
        assert result['suggestions'], result
        assert (work / 'slice-scores.csv').exists()
        cases = json.loads((work / 'cases.json').read_text(encoding='utf-8'))
        for item in result['suggestions']:
            case = cases[item['case']]
            assert case['http'] == 200 and case['both_offered']
            assert {'sh2-129_ha', 'ou4_oiii'}.issubset(case['body']['viable_acquisition_intent_ids'])
            assert case['body']['night_date'] == item['night_date']
    else:
        assert result['status'] == 'NO_TESTABLE_WINDOW' and not result['suggestions']
    assert not (work / 'data/user_filters.json').exists()
    assert json.loads((work / 'data/user_profile.json').read_text(encoding='utf-8')) == profile
    assert not (work / 'data/decision_acceptance_lineage').exists()
    findings.append({'scenario': scenario, 'passed': True, 'status': result['status'],
                     'suggestions': len(result['suggestions']), 'cases': result['cases']})

(root / 'qualification.json').write_text(json.dumps({'passed': True, 'checks': findings,
    'python': sys.version, 'platform': sys.platform, 'profile': 'synthetic only',
    'legacy_inventory_created': False, 'no_confirmation_sent': True,
    'real_user_data_accessed': False}, indent=2), encoding='utf-8')
